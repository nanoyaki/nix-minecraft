#!/usr/bin/env nix-shell
#!nix-shell -i python3 shell.nix

import argparse
import base64
import concurrent.futures
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

import requests
import requests_cache
from requests.adapters import HTTPAdapter, Retry

# https://maven.neoforged.net/releases/net/neoforged/neoforge/21.5.75/neoforge-21.5.75-installer.jar
MC_ENDPOINT = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

TIMEOUT = 5
RETRIES = 5
THREADS = 8


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
    http = requests_cache.CachedSession(backend="filesystem", cache_control=True)
    retries = Retry(
        total=RETRIES, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )
    http.mount("https://", TimeoutHTTPAdapter(max_retries=retries))
    return http


def get_game_versions(client: requests.Session) -> Dict[str, str]:
    print("Fetching game versions")
    response = client.get(MC_ENDPOINT)
    response.raise_for_status()
    data = response.json()
    return {v["id"]: v["url"] for v in data["versions"]}


class FetchUrl(TypedDict):
    name: Optional[str]
    url: str
    hash: str


class VersionLockLibraries(TypedDict):
    install: List[str]
    runtime: List[str]


class VersionLock(TypedDict):
    version: str
    src: FetchUrl
    libraries: VersionLockLibraries


class Libraries(TypedDict):
    install: Dict[str, FetchUrl]
    runtime: Dict[str, FetchUrl]


LoaderLocks = Dict[str, VersionLock]


def fetch_mappings_hash(client: requests.Session, url: str):
    print(f"Fetching mappings: {url}")
    response = client.get(url)
    response.raise_for_status()
    server_mappings = response.json()["downloads"]["server_mappings"]
    return FetchUrl(
        name=None,
        url=str(server_mappings["url"]),
        hash=f"sha1-{base64.b64encode(bytes.fromhex(server_mappings['sha1'])).decode('utf-8')}",
    )


def fetch_installer_hash(client: requests.Session, version: str):
    url = f"{MAVEN}/{version}/neoforge-{version}-installer.jar"
    hash_url = f"{url}.sha256"
    print(f"Fetching hash: {hash_url}")
    response = client.get(hash_url)
    response.raise_for_status()
    return FetchUrl(
        name=os.path.basename(url),
        url=url,
        hash=f"sha256-{base64.b64encode(bytes.fromhex(response.text)).decode('utf-8')}",
    )


def fetch_library_hashes(src: FetchUrl) -> Libraries:
    # the installer jar is used by the build derivation, so we might as
    # well use nix to fetch it
    out_link = f"result-{src['name']}"
    cmd = [
        "nix",
        "build",
        "--out-link",
        out_link,
        "--file",
        "fetchInstaller.nix",
        "--argstr",
        "srcJson",
        json.dumps(src),
        "--print-out-paths",
    ]
    subprocess.run(cmd, stderr=subprocess.STDOUT, check=True)
    store_path = Path(out_link)

    def library_src(library):
        artifact = library["downloads"]["artifact"]
        return FetchUrl(
            name=None,
            # name=library["name"],
            url=artifact["url"],
            hash=f"sha1-{artifact['sha1']}",
        )

    with open(store_path / "install_profile.json", "r") as f:
        profile_data = json.load(f)
        install = profile_data["libraries"]
    with open(store_path / "version.json", "r") as f:
        version_data = json.load(f)
        runtime = version_data["libraries"]
    return Libraries(
        install={str(lib["name"]): library_src(lib) for lib in install},
        runtime={str(lib["name"]): library_src(lib) for lib in runtime},
    )


def fetch_loader_versions(
    client: requests_cache.CachedSession,
) -> Dict[str, List[str]]:
    print("Fetching installer versions")
    response = client.get(API, expire_after=requests_cache.DO_NOT_CACHE)
    response.raise_for_status()

    versions = defaultdict(list)
    data = response.json()
    for version in data["versions"]:
        # first two digits == 1.x game version
        match = re.match(r"^(\d+\.\d+)\.(\d+)$", version)
        if not match:
            print(f"Skipping version: {version}")
            continue
        versions[f"1.{match.group(1)}".removesuffix(".0")].append(version)
    return versions


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


def main(
    loader_versions: Dict[str, VersionLock],
    game_versions: Dict[str, Any],
    library_versions: Dict[str, FetchUrl],
    version_regex,
    client,
):
    print("Starting fetch")

    game_manifest = get_game_versions(client)
    loader_manifest = fetch_loader_versions(client)

    to_fetch = []

    for game_version, build_versions in loader_manifest.items():
        if game_version not in game_versions:
            game_versions[game_version] = fetch_mappings_hash(
                client, game_manifest[game_version]
            )

        for build_version in build_versions:
            if re.match(version_regex, build_version) is None:
                print(f"Skip fetching build {build_version}: does not match pattern")
                continue
            if build_version not in loader_versions:
                to_fetch.append(build_version)

    print(f"Fetching {len(to_fetch)} loader versions...")

    def fetch_build(version: str):
        installer = fetch_installer_hash(client, version)
        return version, installer, fetch_library_hashes(installer)

    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as p:
        for version, src, library_srcs in p.map(fetch_build, to_fetch):
            loader_versions[version] = VersionLock(
                version=version,
                libraries=VersionLockLibraries(
                    install=sorted(library_srcs["install"].keys()),
                    runtime=sorted(library_srcs["runtime"].keys()),
                ),
                src=src,
            )
            library_versions |= library_srcs["install"]
            library_versions |= library_srcs["runtime"]

    return (loader_versions, game_versions, library_versions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", type=str, default=r"^\d+\.\d+.\d+$", required=False
    )
    args = parser.parse_args()

    folder = Path(__file__).parent
    loader_path = folder / "loader_locks.json"
    game_path = folder / "game_locks.json"
    library_path = folder / "library_locks.json"
    with (
        open(loader_path, "r") as loader_locks,
        open(game_path, "r") as game_locks,
        open(library_path, "r") as library_locks,
    ):
        loader_versions = (
            {} if loader_path.stat().st_size == 0 else json.load(loader_locks)
        )
        game_versions = {} if game_path.stat().st_size == 0 else json.load(game_locks)
        library_versions = (
            {} if library_path.stat().st_size == 0 else json.load(library_locks)
        )

    with (
        open(loader_path, "w") as loader_locks,
        open(game_path, "w") as game_locks,
        open(library_path, "w") as library_locks,
    ):
        try:
            (loader_versions, game_versions, library_versions) = main(
                loader_versions,
                game_versions,
                library_versions,
                args.version,
                make_client(),
            )
        except KeyboardInterrupt:
            print("Cancelled fetching. Writing and exiting")

        json.dump(
            loader_versions,
            loader_locks,
            indent=2,
            sort_keys=True,
        )
        json.dump(game_versions, game_locks, indent=2, sort_keys=True)
        json.dump(
            library_versions,
            library_locks,
            indent=2,
            sort_keys=True,
        )
