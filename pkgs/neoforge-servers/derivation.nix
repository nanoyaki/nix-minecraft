{
  lib,
  fetchurl,
  jre_headless,
  linkFarm,
  makeWrapper,
  minecraft-server,
  python3,
  runCommand,
  stdenvNoCC,
  udev,
  writeShellApplication,
  zip,

  build,
  gameVersion,
  libraryLocks,
}:
let
  inherit (lib)
    attrValues
    concatLists
    concatStringsSep
    elemAt
    map
    mapAttrs
    splitString
    ;
  specifierPath =
    specifier:
    let
      components = builtins.match "^([^:]+):([^:]+):([^@:]+).*" specifier;
      groupId = elemAt components 0;
      artifactId = elemAt components 1;
      version = elemAt components 2;
    in
    concatStringsSep "/" (
      (splitString "." groupId)
      ++ [
        artifactId
        version
      ]
    );
  mkLibrary = specifier: rec {
    name = "${specifierPath specifier}/${path.name}";
    path = fetchurl libraryLocks.${specifier};
  };
  repository = linkFarm "neoforge${build.version}-libraries" (
    (map mkLibrary build.libraries)
    ++ [
      {
        name = "net/minecraft/server/${minecraft-server.version}/server-${minecraft-server.version}.jar";
        path = minecraft-server.src;
      }
    ]
  );
  installer-unwrapped = fetchurl build.src;
  installer =
    let
      name = "neoforge-${build.version}-offline-installer";
      fatJar = runCommand "${name}" { nativeBuildInputs = [ zip ]; } ''
        install -m 644 -D "${installer-unwrapped}" "$out"

        # add server mappings to the classpath so we can perform an offline install
        # see the result of --generate-fat
        server_mappings="maven/minecraft/${minecraft-server.version}/server_mappings.txt"
        install -m 644 -D ${fetchurl gameVersion.mappings} "$server_mappings"

        zip "$out" "$server_mappings"
      '';
      wrapper = writeShellApplication {
        inherit name;
        runtimeInputs = [
          jre_headless
          python3
        ];
        text = ''
          mkdir -p "$1/libraries"
          cd "$1"
          cp -r --no-preserve=all ${repository}/* "libraries"
          java -jar ${fatJar} --offline --installServer .
          python ${./symlink_libraries.py} "libraries/net/neoforged/neoforge/${build.version}/unix_args.txt"
        '';
      };
    in
    wrapper;
in
stdenvNoCC.mkDerivation rec {
  pname = "neoforge";
  inherit (build) version;
  dontUnpack = true;

  preferLocalBuild = false; # unlike other loaders, the install/patching process is rather CPU intensive

  buildInputs = [ makeWrapper ];

  nativeBuildInputs = [ python3 ];

  buildPhase = ''
    ${lib.getExe installer} $out

    makeWrapper "${jre_headless}/bin/java" "$out/bin/${meta.mainProgram}" \
      --append-flags "@$args" \
      ${lib.optionalString stdenvNoCC.hostPlatform.isLinux "--prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ udev ]}"}
  '';

  passthru = {
    inherit repository installer installer-unwrapped;
    updateScript = ./update.py;
  };

  meta = with lib; {
    description = "Minecraft Server";
    homepage = "https://minecraft.net";
    license = licenses.unfreeRedistributable;
    platforms = platforms.unix;
    maintainers = with maintainers; [ infinidoge ];
    mainProgram = "minecraft-server";
  };
}
