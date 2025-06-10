{
  lib,
  stdenvNoCC,
  fetchurl,
  nixosTests,
  jre_headless,
  version,
  url,
  hash,
}:
stdenvNoCC.mkDerivation {
  pname = "minecraft-server-neoforge";
  inherit version;

  src = fetchurl {
    inherit url hash;
  };

  preferLocalBuild = true;

  patchPhase = '''';

  installPhase = ''
    mkdir -p $out/bin $out/lib/minecraft
    cp -v $src $out/lib/minecraft/server.jar

    chmod +x $out/bin/minecraft-server
  '';

  dontUnpack = true;

  passthru = {
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
