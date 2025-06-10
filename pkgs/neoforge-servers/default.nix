{
  callPackage,
  lib,
  jre8_headless,
  jre_headless,
}:
let
  inherit (lib.our) escapeVersion;
  inherit (lib)
    nameValuePair
    flatten
    last
    versionOlder
    mapAttrsToList
    ;
  sortBy = attr: f: builtins.sort (a: b: f a.${attr} b.${attr});

  library_versions = lib.importJSON ./lock_libraries.json;
  loader_versions = lib.importJSON ./launcher_locks.json;
  game_versions = lib.importJSON ./lock_game.json;

  packages = mapAttrsToList (
    version: builds:
    sortBy "version" versionOlder (
      mapAttrsToList (
        buildNumber: value:
        callPackage ./derivation.nix {
          inherit (value.installer.src)
            url
            hash
            ;
          version = "${version}-${buildNumber}";
        }
      ) builds
    )
  ) versions;
in
lib.recurseIntoAttrs (packages)
