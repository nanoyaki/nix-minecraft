{
  lib,
  makeWrapper,
  zip,
  stdenvNoCC,
  tree,
  fetchurl,
  linkFarm,
  nixosTests,
  jre_headless,
  version,
  minecraft-server,
  runCommandLocal,

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
      {
        name =
          let
            version = "1.21.5-20250325.162830";
          in
          # "net/minecraft/server/${version}/server-${version}-mappings.txt";
          # "minecraft/1.21.5/server_mappings.txt";
          "libraries/net/minecraft/server/1.21.5-20250325.162830/server-1.21.5-20250325.162830-mappings.txt";
        path = fetchurl gameVersion.mappings;
      }
    ]
  );
  installerDrv =
    let
      name = "neoforge-${version}-installer";
      src = fetchurl installer.src;
      mappings = fetchurl gameVersion.mappings;
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
        # add server mappings to the classpath so we can perform an offline install
        # see the result of --generate-fat
        server_mappings="maven/minecraft/1.21.5/server_mappings.txt"
        mkdir -p "$(dirname "$server_mappings")"
        cp ${mappings} "$server_mappings"
        installer_jar="$out/lib/${src.name}"
        cp --no-preserve=all "${src}" "$installer_jar"
        zip "$installer_jar" "$server_mappings"

        mkdir -p $out/bin
        makeWrapper "${jre_headless}/bin/java" "$out/bin/${name}" \
          --add-flags "-cp $server_mappings" \
          --add-flags "-jar $installer_jar"
      '';
in
# TODO: symlinkJoin
stdenvNoCC.mkDerivation {
  pname = "neoforge";
  inherit version;

  # TODO: this doesn't make sense
  src = fetchurl installer.src;

  nativeBuildInputs = [
    jre_headless
    zip
  ];

  preferLocalBuild = true;

  patchPhase = '''';

  installPhase = ''
    cp -r --no-preserve=all ${librariesDrv} $out
    ${lib.getExe installerDrv} --offline --install-server $out
    exit 1
  '';

  dontUnpack = true;

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
    mainProgram = "minecraft-server";
  };
}
