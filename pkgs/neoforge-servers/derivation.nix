{
  lib,
  stdenvNoCC,
  fetchurl,
  linkFarmFromDrvs,
  nixosTests,
  jre_headless,
  version,
  installer,
  libraries,
}:
let
  mkLibrary = name: fetchurl libraries.${name};
  librariesDrv = linkFarmFromDrvs "neoforge${version}-libraries" (map mkLibrary installer.libraries);
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
