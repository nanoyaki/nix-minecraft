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

  loaderLocks = lib.importJSON ./loader_locks.json;
  libraryLocks = lib.importJSON ./library_locks.json;
  mappingLocks = lib.importJSON ./mapping_locks.json;

  packages = mapAttrsToList (
    gameVersion: builds:
    sortBy "version" versionOlder (
      mapAttrsToList (
        buildVersion: build:
        callPackage ./derivation.nix {
          inherit libraryLocks;
          build = build // {
            version = buildVersion;
          };
          mappings = mappingLocks.${gameVersion} // {
            version = gameVersion;
          };
          minecraft-server = vanillaServers."vanilla-${escapeVersion gameVersion}";
        }
      ) builds
    )
  ) loaderLocks;

  # Latest build for each MC version
  latestBuilds = sortBy "version" versionOlder (map last packages);
in
lib.recurseIntoAttrs (
  builtins.listToAttrs (
    (map (x: nameValuePair (escapeVersion x.name) x) (flatten packages))
    ++ (map (x: nameValuePair (escapeVersion x.name) x) latestBuilds)
    ++ [ (nameValuePair "neoforge" (last latestBuilds)) ]
  )
)
