{
  pkgs ? import <nixpkgs> { },
}:
pkgs.mkShellNoCC {
  packages = with pkgs; [
    (python3.withPackages (
      ps: with ps; [
        dataclasses-json
        lxml
        requests
        requests-cache
      ]
    ))
  ];
}
