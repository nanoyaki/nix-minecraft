{
  callPackage,
  vanillaServers,
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

  versions = lib.importJSON ./launcher_locks.json;
  libraries = lib.importJSON ./library_locks.json;
  game_versions = lib.importJSON ./game_locks.json;

  packages = mapAttrsToList (
    gameVersion: builds:
    sortBy "version" versionOlder (
      mapAttrsToList (
        buildVersion: build:
        callPackage ./derivation.nix {
          inherit (build) installer;
          inherit libraries;
          version = "${buildVersion}";
          gameVersion = game_versions.${gameVersion};
          minecraft-server = vanillaServers."vanilla-${escapeVersion gameVersion}";
        }
      ) builds
    )
  ) versions;

  # Latest build for each MC version
  latestBuilds = sortBy "version" versionOlder (map last packages);
in
lib.recurseIntoAttrs (
  builtins.listToAttrs (
    (map (x: nameValuePair (escapeVersion x.name) x) (flatten packages))
    ++ (map (x: nameValuePair (escapeVersion x.name) x) latestBuilds)
    ++ [ (nameValuePair "paper" (last latestBuilds)) ]
  )
)
