#!/usr/bin/env nix-shell
#!nix-shell -i python3 shell.nix

import json
import re
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import requests
import requests_cache
from requests.adapters import HTTPAdapter, Retry

# https://maven.neoforged.net/releases/net/neoforged/neoforge/21.5.75/neoforge-21.5.75-installer.jar
MC_ENDPOINT = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
ENDPOINT = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
MAVEN = ENDPOINT
MC_MAVEN = ENDPOINT

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


def get_game_versions(client):
    print("Fetching game versions")
    data = client.get(MC_ENDPOINT).json()
    return data["versions"]


def get_launcher_versions(client: requests.Session):
    print("Fetching launcher versions")
    response = client.get(
        "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
    ).json()

    versions = defaultdict(list)
    for elem in response["versions"]:
        version = elem.text
        # first two digits == 1.x game version
        match = re.match(r"^(\d+\.\d+)\.\d+$", version)
        if not match:
            print(f"Skipping version: {version}")
            continue
        game_version = f"1.{match.group(1)}"
        versions[game_version].append(version)
    return dict(versions)


def get_launcher_build(client: requests.Session, version):
    print(f"Fetching launcher build: {version}")

    def fetchurl(url):
        hash = client.get(f"{url}.sha256")
        return {"url": url, "hash": f"sha256-{hash.text}"}

    return {
        "universal": fetchurl(f"{ENDPOINT}/{version}/neoforge-{version}-universal.jar"),
        "installer": fetchurl(f"{ENDPOINT}/{version}/neoforge-{version}-installer.jar"),
    }


def get_launcher_libraries(client, version):
    print("Fetching installer")
    installer = client.get(f"{MAVEN}/{version}/neoforge-${version}-installer.jar")
    libraries = []
    with ZipFile(installer) as zip:
        with zip.open("install_profile.json") as profile:
            profile_data = json.load(profile)
            libraries.extend(profile_data.libraries)
        with zip.open("version.json") as version:
            version_data = json.load(version)
            libraries.extend(version_data.libraries)
    return libraries


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

    for version, builds in launcher_manifest.items():
        for build in builds:
            if build not in launcher_versions[version]:
                launcher_build = get_launcher_build(client, build)
                print(launcher_build)

                #     launcher_versions[version][build_number] = {
                #         "type": "universal",
                #         "universalUrl": build_universal_url,
                #         "universalHash": build_universal_hash,
                #         "installUrl": build_installer_url,
                #         "installHash": build_installer_hash,
                #     }
                # if 'universal' in launcher_build['classifiers']:
                #     build_number = build
                #     build_universal_hash = launcher_build['classifiers']["universal"]["jar"]
                #     build_universal_url = f"{MAVEN}/{build}/forge-{build}-universal.jar"
                #     build_installer_hash = launcher_build['classifiers']["installer"]["jar"]
                #     build_installer_url = f"{MAVEN}/{build}/forge-{build}-installer.jar"
                #     launcher_versions[version][build_number] = {
                #         "type": "universal",
                #         "universalUrl": build_universal_url,
                #         "universalHash": build_universal_hash,
                #         "installUrl": build_installer_url,
                #         "installHash": build_installer_hash,
                #     }
                # elif 'installer' in launcher_build['classifiers']:
                #     build_sha256 = launcher_build['classifiers']["installer"]["jar"]
                #     build_number = build
                #     build_url = f"{MAVEN}/{build}/forge-{build}-installer.jar"
                #     launcher_versions[version][build_number] = {
                #         "type": "modern",
                #         "url": build_url,
                #         "hash": build_hash,
                #     }
                # elif 'client' in launcher_build['classifiers']:
                #     build_sha256 = launcher_build['classifiers']["client"]["zip"]
                #     build_number = build
                #     build_url = f"{MAVEN}/{build}/forge-{build}-client.zip"
                #     launcher_versions[version][build_number] = {
                #         "type": "ancient",
                #         "url": build_url,
                #         "hash": build_hash,
                #     }
                # else:
                #     print(f'no installer or client in {build}')
                #     print(launcher_build)

    return (launcher_versions, game_versions, library_versions)


if __name__ == "__main__":
    folder = Path(__file__).parent
    launcher_path = folder / "lock_launcher.json"
    game_path = folder / "lock_game.json"
    library_path = folder / "lock_libraries.json"
    with (
        open(launcher_path, "r") as launcher_locks,
        open(game_path, "r") as game_locks,
        open(library_path, "r") as library_locks,
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

    # with (
    #     open(launcher_path, "w") as launcher_locks,
    #     open(game_path, "w") as game_locks,
    #     open(library_path, "w") as library_locks,
    # ):
    #     json.dump(launcher_versions,launcher_locks,indent=4)
    #     json.dump(game_versions,game_locks,indent=4)
    #     json.dump(library_versions,library_locks,indent=4)
