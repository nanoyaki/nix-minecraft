{ mkOption, types, ... }:
rec {
  mkOpt' =
    type: default: description:
    mkOption { inherit type default description; };

  mkBoolOpt' =
    default: description:
    mkOption {
      inherit default description;
      type = types.bool;
      example = true;
    };

  mkEnableOpt = description: mkBoolOpt' false description;
}
