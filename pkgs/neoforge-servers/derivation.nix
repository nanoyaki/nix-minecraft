{
  lib,
  stdenvNoCC,
  fetchurl,
  linkFarm,
  nixosTests,
  jre_headless,
  version,
  installer,
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
      groupId = head components 0;
      artifactId = tail components 1;
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
  librariesDrv = linkFarm "neoforge${version}-libraries" (map mkLibrary installer.libraries);
in
# stdenvNoCC.mkDerivation {
#   pname = "minecraft-server-neoforge";
#   inherit version;
#
#   src = fetchurl {
#     inherit url sha256;
#   };
#
#   preferLocalBuild = true;
#
#   patchPhase = '''';
#
#   installPhase = ''
#     mkdir -p $out/bin $out/lib/minecraft
#     cp -v $src $out/lib/minecraft/server.jar
#
#     chmod +x $out/bin/minecraft-server
#   '';
#
#   dontUnpack = true;
#
#   passthru = {
#     updateScript = ./update.py;
#   };
#
#   meta = with lib; {
#     description = "Minecraft Server";
#     homepage = "https://minecraft.net";
#     license = licenses.unfreeRedistributable;
#     platforms = platforms.unix;
#     maintainers = with maintainers; [ infinidoge ];
#     mainProgram = "minecraft-server";
#   };
# }
librariesDrv
