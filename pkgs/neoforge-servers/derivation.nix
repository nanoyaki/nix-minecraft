{
  symlinkJoin,
  lib,
  makeWrapper,
  zip,
  stdenvNoCC,
  tree,
  fetchurl,
  linkFarm,
  nixosTests,
  jre_headless,
  minecraft-server,
  runCommandLocal,

  version,
  installer,
  gameVersion,
  libraries,
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
    name = "libraries/${specifierPath specifier}/${path.name}";
    path = fetchurl libraries.${specifier};
  };
  librariesDrv = linkFarm "neoforge${version}-libraries" (
    (map mkLibrary (installer.libraries ++ gameVersion.libraries))
    ++ [
      {
        name = "libraries/net/minecraft/server/${minecraft-server.version}/server-${minecraft-server.version}.jar";
        path = minecraft-server.src;
      }
    ]
  );
  installerDrv =
    let
      name = "neoforge-${version}-installer";
      installerJar = fetchurl installer.src;
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
        installer_jar="$out/lib/${installerJar.name}"
        install -m 644 -D "${installerJar}" "$installer_jar"

        # add server mappings to the classpath so we can perform an offline install
        # see the result of --generate-fat
        server_mappings="maven/minecraft/1.21.5/server_mappings.txt"
        install -m 644 -D ${fetchurl gameVersion.mappings} "$server_mappings"

        zip "$installer_jar" "$server_mappings"

        mkdir -p $out/bin
        makeWrapper "${jre_headless}/bin/java" "$out/bin/${name}" \
          --add-flags "-jar $installer_jar"
      '';
in
stdenvNoCC.mkDerivation rec {
  pname = "neoforge-server";
  inherit version;
  dontUnpack = true;

  preferLocalBuild = false; # unlike other servers, the install/patching process is rather CPU intensive

  buildInputs = [ makeWrapper ];

  buildPhase = ''
    cp -r --no-preserve=all ${librariesDrv} $out
    ${lib.getExe installerDrv} --offline --install-server $out

    makeWrapper "${jre_headless}/bin/java" "$out/bin/${meta.mainProgram}" \
      --add-flags "@$out/libraries/net/neoforged/neoforge/${version}/unix_args.txt"
  '';

  passthru = {
    inherit librariesDrv;
    libraries = librariesDrv;
    installer = installerDrv;
    updateScript = ./update.py;
  };

  meta = with lib; {
    description = "Minecraft Server";
    homepage = "https://minecraft.net";
    license = licenses.unfreeRedistributable;
    platforms = platforms.unix;
    maintainers = with maintainers; [ infinidoge ];
    mainProgram = "neoforge-server";
  };
}
