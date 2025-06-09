{
  pkgs ? import <nixpkgs> { },
}:
pkgs.mkShellNoCC {
  packages = with pkgs; [
    (python3.withPackages (ps: [
      ps.requests
      ps.requests-cache
      ps.lxml
    ]))
    pyright
  ];
}
