#!/usr/bin/env nix-shell
#!nix-shell -i python3 shell.nix

import argparse
import io
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import requests
import requests_cache
from requests.adapters import HTTPAdapter, Retry

# https://maven.neoforged.net/releases/net/neoforged/neoforge/21.5.75/neoforge-21.5.75-installer.jar
MC_ENDPOINT = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

TIMEOUT = 5
RETRIES = 5


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.timeout = TIMEOUT
        if "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
            del kwargs["timeout"]
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


def make_client():
    # TODO: XDG_CACHE_DIR?
    http = requests_cache.CachedSession(backend="filesystem")
    retries = Retry(
        total=RETRIES, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )
    http.mount("https://", TimeoutHTTPAdapter(max_retries=retries))
    return http


def get_game_versions(client: requests.Session):
    print("Fetching game versions")
    response = client.get(MC_ENDPOINT)
    response.raise_for_status()
    data = response.json()
    return data["versions"]


def get_launcher_versions(client: requests.Session):
    print("Fetching launcher versions")
    response = client.get(API)
    response.raise_for_status()

    versions = defaultdict(list)
    data = response.json()
    for version in data["versions"]:
        # first two digits == 1.x game version
        match = re.match(r"^(\d+\.\d+)\.(\d+)$", version)
        if not match:
            print(f"Skipping version: {version}")
            continue
        versions[f"1.{match.group(1)}"].append(version)
    return versions


def get_launcher_build(client: requests.Session, version: str):
    def fetchurl(url):
        hash_url = f"{url}.sha256"
        print(f"Fetching hash: {hash_url}")
        response = client.get(hash_url)
        response.raise_for_status()
        return {"url": url, "sha256": response.text}

    return {
        "universal": {
            "src": fetchurl(f"{MAVEN}/{version}/neoforge-{version}-universal.jar")
        },
        "installer": {
            "src": fetchurl(f"{MAVEN}/{version}/neoforge-{version}-installer.jar"),
            "libraries": get_launcher_libraries(client, version),
        },
    }


def library_lock(library: dict[str, Any]):
    # FIXME
    name_match = re.match(r"([^@]+)(?:@jar)?", library["name"])
    if name_match is None:
        raise Exception(f"Unknown specifier {library['name']}")
    name = name_match.group(1)
    artifact = library["downloads"]["artifact"]
    return (
        name,
        {"url": artifact["url"], "sha1": artifact["sha1"]},
    )


def launcher_lock(build: dict[str, Any]):
    return build | {
        "installer": build["installer"]
        | {"libraries": sorted(build["installer"]["libraries"].keys())}
    }


def get_launcher_libraries(client: requests.Session, version: str):
    url = f"{MAVEN}/{version}/neoforge-{version}-installer.jar"
    print(f"Fetching libraries for {url}")
    response = client.get(url, stream=True)
    response.raise_for_status()
    response.raw.decode_content = True
    libraries = []
    with ZipFile(io.BytesIO(response.content)) as zip:
        with zip.open("install_profile.json") as fprofile:
            profile_data = json.load(fprofile)
            libraries.extend(profile_data["libraries"])
        with zip.open("version.json") as fversion:
            version_data = json.load(fversion)
            libraries.extend(version_data["libraries"])
    return dict([library_lock(lib) for lib in libraries])


def get_game_libraries(client, version):
    print("Fetching installer")
    manifest = client.get(f"{MC_ENDPOINT}/")
    libraries = []
    return libraries


def library_rules_match(library):
    def rule_matches(rule):
        action = rule["action"]
        os = rule.get("os")
        # assuming only Linux for now
        if action == "allow" and os is not None:
            return os == "linux"
        print(f"Ignoring rule {rule}")
        return True

    for rule in library.get("rules", []):
        if not rule_matches(rule):
            return False
    return True


def main(launcher_versions, game_versions, library_versions, version_regex, client):
    launcher_versions = defaultdict(dict, launcher_versions)
    output = {}
    print("Starting fetch")

    game_manifest = get_game_versions(client)

    # We need all the libraries for a given game version for forge to be happy.  This might
    # be useful to port up to build-support.
    # TODO: move to game support
    for version in game_manifest:
        if version["type"] != "release":
            continue

        # if (
        #     version["id"] in game_versions
        #     and game_versions[version["id"]]["sha1"] == version["sha1"]
        # ):
        #     continue

        data = client.get(version["url"]).json()
        libraries = []
        for library in data["libraries"]:
            if "artifact" not in library["downloads"]:
                continue
            library_versions[library["name"]] = library_lock(library)[1]
            if library_rules_match(library):
                libraries.append(library["name"])
        if "server" not in data["downloads"]:
            continue
        server = data["downloads"]["server"]
        mappings = ""
        if "server_mappings" in data["downloads"]:
            mappings = data["downloads"]["server_mappings"]
        game_versions[version["id"]] = {
            "sha1": version["sha1"],
            "server": server,
            "mappings": mappings,
            "libraries": sorted(libraries),
        }

    launcher_manifest = get_launcher_versions(client)
    print(launcher_manifest, sep="\n")

    for version, builds in launcher_manifest.items():
        for build in builds:
            if re.match(version_regex, build) is None:
                print("Skip fetching build", build)
                continue

            if build not in launcher_versions[version]:
                launcher_build = get_launcher_build(client, build)
                launcher_versions[version][build] = launcher_lock(launcher_build)
                library_versions |= launcher_build["installer"]["libraries"]

    return (launcher_versions, game_versions, library_versions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A simple script to greet someone.")

    parser.add_argument("--version", type=str, default=".*", required=False)
    args = parser.parse_args()

    folder = Path(__file__).parent
    launcher_path = folder / "launcher_locks.json"
    game_path = folder / "game_locks.json"
    library_path = folder / "library_locks.json"
    with (
        open(launcher_path, "r+") as launcher_locks,
        open(game_path, "r+") as game_locks,
        open(library_path, "r+") as library_locks,
    ):
        launcher_versions = (
            {} if launcher_path.stat().st_size == 0 else json.load(launcher_locks)
        )
        game_versions = {} if game_path.stat().st_size == 0 else json.load(game_locks)
        library_versions = (
            {} if library_path.stat().st_size == 0 else json.load(library_locks)
        )
    (launcher_versions, game_versions, library_versions) = main(
        launcher_versions,
        game_versions,
        library_versions,
        args.version,
        make_client(),
    )

    with (
        open(launcher_path, "w") as launcher_locks,
        open(game_path, "w") as game_locks,
        open(library_path, "w") as library_locks,
    ):
        json.dump(launcher_versions, launcher_locks, indent=2, sort_keys=True)
        json.dump(game_versions, game_locks, indent=2, sort_keys=True)
        json.dump(library_versions, library_locks, indent=2, sort_keys=True)
