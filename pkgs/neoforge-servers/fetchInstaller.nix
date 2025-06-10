{
  pkgs ? import <nixpkgs> { },
  srcJson,
}:
pkgs.fetchurl (builtins.fromJSON srcJson)
