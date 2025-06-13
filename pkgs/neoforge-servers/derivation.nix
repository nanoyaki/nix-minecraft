{
  lib,
  fetchurl,
  jre_headless,
  linkFarm,
  makeWrapper,
  minecraft-server,
  runCommandLocal,
  stdenvNoCC,
  udev,
  zip,

  gameVersion,
  build,
  libraryLocks,
}:
let
  inherit (lib)
    splitString
    elemAt
    concatStringsSep
    ;
  specifierPath =
    specifier:
    let
      components = splitString ":" specifier;
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
    (map mkLibrary (build.libraries ++ gameVersion.libraries))
    ++ [
      {
        name = "net/minecraft/server/${minecraft-server.version}/server-${minecraft-server.version}.jar";
        path = minecraft-server.src;
      }
    ]
  );
  installer =
    let
      name = "neoforge-${build.version}-installer";
      buildSrc = fetchurl build.src;
    in
    # TODO: try use mirror?
    runCommandLocal name
      {
        nativeBuildInputs = [
          makeWrapper
          zip
        ];
        meta.mainProgram = name;
      }
      ''
        installer_jar="$out/lib/${buildSrc.name}"
        install -m 644 -D "${buildSrc}" "$installer_jar"

        # add server mappings to the classpath so we can perform an offline install
        # see the result of --generate-fat
        server_mappings="maven/minecraft/${minecraft-server.version}/server_mappings.txt"
        install -m 644 -D ${fetchurl gameVersion.mappings} "$server_mappings"

        zip "$installer_jar" "$server_mappings"

        mkdir -p $out/bin
        makeWrapper "${jre_headless}/bin/java" "$out/bin/${name}" \
          --add-flags "-jar $installer_jar"
      '';
in
stdenvNoCC.mkDerivation rec {
  pname = "neoforge";
  inherit (build) version;
  dontUnpack = true;

  preferLocalBuild = false; # unlike other servers, the install/patching process is rather CPU intensive

  buildInputs = [ makeWrapper ];

  buildPhase = ''
    mkdir -p $out/libraries
    cp -r --no-preserve=all ${repository}/* $out/libraries
    ${lib.getExe installer} --offline --install-server $out
    # rm !($out/{bin,libraries})

    args="$out/libraries/net/neoforged/neoforge/${version}/unix_args.txt"
    substituteInPlace "$args" \
      --replace-fail "-DlibraryDirectory=libraries" "-DlibraryDirectory=$out/libraries" \
      --replace-fail "libraries/" "$out/libraries/"
    makeWrapper "${jre_headless}/bin/java" "$out/bin/${meta.mainProgram}" \
      --append-flags "@$args" \
      ${lib.optionalString stdenvNoCC.hostPlatform.isLinux "--prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ udev ]}"}
  '';

  passthru = {
    inherit repository;
    libraries = repository;
    installer = installer;
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
