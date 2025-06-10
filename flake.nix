{
  description = "An attempt to better support Minecraft-related content for the Nix ecosystem";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-utils.url = "github:numtide/flake-utils";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      ...
    }@inputs:
    let
      mkLib = pkgs: pkgs.lib.extend (_: _: { our = self.lib; });

      mkPackages =
        pkgs:
        let
          # Include build support functions in callPackage,
          # and include callPackage in itself so it passes to children
          callPackage = pkgs.newScope (
            {
              lib = mkLib pkgs;
              inherit callPackage;
            }
            // buildSupport
          );
          buildSupport = builtins.mapAttrs (n: v: callPackage v) (self.lib.rakeLeaves ./pkgs/build-support);
        in
        rec {
          inherit buildSupport;

          vanillaServers = callPackage ./pkgs/vanilla-servers { };
          fabricServers = callPackage ./pkgs/fabric-servers { inherit vanillaServers; };
          quiltServers = callPackage ./pkgs/quilt-servers { inherit vanillaServers; };
          legacyFabricServers = callPackage ./pkgs/legacy-fabric-servers { inherit vanillaServers; };
          paperServers = callPackage ./pkgs/paper-servers { inherit vanillaServers; };
          velocityServers = callPackage ./pkgs/velocity-servers { };
          neoforgeServers = callPackage ./pkgs/neoforge-servers { inherit vanillaServers; };
          minecraftServers =
            vanillaServers
            // fabricServers
            // quiltServers
            // legacyFabricServers
            // paperServers
            // neoforgeServers;

          vanilla-server = vanillaServers.vanilla;
          fabric-server = fabricServers.fabric;
          quilt-server = quiltServers.quilt;
          paper-server = paperServers.paper;
          velocity-server = velocityServers.velocity;
          minecraft-server = vanilla-server;
          # TODO: neoforge-server
        }
        // (builtins.mapAttrs (n: v: callPackage v { }) (self.lib.rakeLeaves ./pkgs/tools));

      mkTests =
        pkgs:
        let
          inherit (pkgs.stdenv) isLinux;
          inherit (pkgs.lib) optionalAttrs mapAttrs;
          callPackage = pkgs.newScope {
            inherit self;
            inherit (self) inputs outputs;
            lib = mkLib pkgs;
          };
        in
        optionalAttrs isLinux (mapAttrs (n: v: callPackage v { }) (self.lib.rakeLeaves ./tests));

      mkModules = path: (nixpkgs.lib.mapAttrs (_: module: import module self) (self.lib.rakeLeaves path));

      commonModules = mkModules ./modules/common;
      homeModules = mkModules ./modules/home;
      nixosModules = mkModules ./modules/nixos;
    in
    {
      lib = import ./lib { lib = flake-utils.lib // nixpkgs.lib; };

      overlay = final: prev: mkPackages prev;
      overlays.default = self.overlay;
      inherit commonModules homeModules nixosModules;

      hydraJobs = {
        checks = { inherit (self.checks) x86_64-linux; };
        packages = { inherit (self.packages) x86_64-linux; };
      };
    }
    // flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config = {
            allowUnfree = true;
          };
        };
        docs = pkgs.nixosOptionsDoc {
          inherit
            (pkgs.lib.evalModules {
              modules = [
                { _module.check = false; }
                nixosModules.minecraft-servers
              ];
            })
            options
            ;
        };
      in
      rec {
        legacyPackages = mkPackages pkgs;

        packages = {
          inherit (legacyPackages)
            vanilla-server
            fabric-server
            quilt-server
            paper-server
            velocity-server
            minecraft-server
            nix-modrinth-prefetch
            ;

          docsAsciiDoc = docs.optionsAsciiDoc;
          docsCommonMark = docs.optionsCommonMark;
        };

        checks = mkTests (pkgs.extend self.outputs.overlays.default) // packages;

        formatter = pkgs.nixfmt-rfc-style;
      }
    );
}
