{
  pkgs ? import <nixpkgs> { },
}:
pkgs.mkShellNoCC {
  packages = with pkgs; [
    (python3.withPackages (
      ps: with ps; [
        requests
        requests-cache
      ]
    ))
  ];
}
