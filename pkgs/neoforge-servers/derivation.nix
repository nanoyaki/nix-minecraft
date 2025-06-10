{
  lib,
  zip,
  stdenvNoCC,
  tree,
  fetchurl,
  linkFarm,
  nixosTests,
  jre_headless,
  version,
  minecraft-server,

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
    cd $out
    cp --no-preserve=all $src installer.jar
    mkdir -p maven/minecraft/1.21.5
    cp ${fetchurl gameVersion.mappings} maven/minecraft/1.21.5/server_mappings.txt
    zip installer.jar maven/minecraft/1.21.5/server_mappings.txt
    java  -jar installer.jar  --install-server --offline
  '';

  dontUnpack = true;

  passthru = {
    inherit librariesDrv;
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
