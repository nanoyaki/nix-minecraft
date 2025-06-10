{
  lib,
  stdenvNoCC,
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
    name = "${specifierPath specifier}/${path.name}";
    path = fetchurl libraries.${specifier};
  };
  librariesDrv = linkFarm "neoforge${version}-libraries" (
    map mkLibrary (installer.libraries ++ gameVersion.libraries)
  );
in
# TODO: symlinkJoin
stdenvNoCC.mkDerivation {
  pname = "neoforge";
  inherit version;

  # TODO: this doesn't make sense
  src = fetchurl installer.src;

  nativeBuildInputs = [ jre_headless ];

  preferLocalBuild = true;

  patchPhase = '''';

  installPhase = ''
    mkdir -p $out/libraries
    LIBRARY_DIR="$out/libraries"
    MINECRAFT_VERSION="${minecraft-server.version}"
    mkdir -p "$LIBRARY_DIR/net/minecraft/server/$MINECRAFT_VERSION"
    install ${minecraft-server.src} "$LIBRARY_DIR/net/minecraft/server/$MINECRAFT_VERSION/server-$MINECRAFT_VERSION.jar"
    cp -r ${librariesDrv}/* $out/libraries
    cd $out
    java -jar $src --install-server --offline
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
