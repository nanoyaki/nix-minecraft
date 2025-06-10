#!/usr/bin/env nix-shell
#!nix-shell -i python3 shell.nix

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
        url = f"{url}.sha256"
        print(f"Fetching hash: {url}")
        response = client.get(url)
        response.raise_for_status()
        return {"url": url, "hash": f"sha256-{response.text}"}

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
    name_match = re.match(r"([^@]+)(?:@jar)?", library["name"])
    if name_match is None:
        raise Exception(f"Unknown specifier {library['name']}")
    name = name_match.group(1)
    artifact = library["downloads"]["artifact"]
    return (
        name,
        {"url": artifact["url"], "hash": artifact["sha1"]},
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


def main(launcher_versions, game_versions, library_versions, client):
    launcher_versions = defaultdict(dict, launcher_versions)
    output = {}
    print("Starting fetch")

    game_manifest = get_game_versions(client)

    # We need all the libraries for a given game version for forge to be happy.  This might
    # be useful to port up to build-support.
    for version in game_manifest:
        if version["type"] == "release":
            if (
                version["id"] in game_versions
                and game_versions[version["id"]]["sha1"] == version["sha1"]
            ):
                pass
            else:
                data = client.get(version["url"]).json()
                libraries = []
                for library in data["libraries"]:
                    if library["name"] not in library_versions:
                        # I should verify nix is happy with the hashes left in these paths.
                        # If not, I need to do something like quilt's prefetch
                        if "artifact" in library["downloads"]:
                            library_versions[library["name"]] = library["downloads"][
                                "artifact"
                            ]
                        # Some libraries are system dependent. I'm assuming there isn't gonna be
                        # support for darwin on this, so I ignore those and only grab the linux
                        # natives.  If this is a wrong assumption, this is the place to fix it.
                        elif "classifiers" in library["downloads"]:
                            if "natives-linux" in library["downloads"]["classifiers"]:
                                library_versions[library["name"]] = library[
                                    "downloads"
                                ]["classifiers"]["natives-linux"]
                        # I've got some escape hatches for when libraries somehow don't match the above
                        # I don't think any *should*, but just incase, lets get some info
                        else:
                            print(version["id"])
                            print(json.dumps(library, indent=4))
                    libraries.append(library["name"])
                mappings = ""
                server = ""
                # if we don't have a server, we might just mark the version as unavailable?
                # this is server only after all.
                if "server" in data["downloads"]:
                    server = data["downloads"]["server"]
                # mappings are only used on the modern forge builds
                if "server_mappings" in data["downloads"]:
                    mappings = data["downloads"]["server_mappings"]
                game_versions[version["id"]] = {
                    "sha1": version["sha1"],
                    "server": server,
                    "mappings": mappings,
                    "libraries": libraries,
                }

    launcher_manifest = get_launcher_versions(client)
    print(launcher_manifest, sep="\n")

    count = 0
    for version, builds in launcher_manifest.items():
        if count > 1:
            break
        for build in builds:
            if build not in launcher_versions[version]:
                count += 1
                if count > 1:
                    break
                launcher_build = get_launcher_build(client, build)
                launcher_versions[version][build] = launcher_lock(launcher_build)
                library_versions |= launcher_build["installer"]["libraries"]

    return (launcher_versions, game_versions, library_versions)


if __name__ == "__main__":
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
