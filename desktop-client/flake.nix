{
  description = "Streamlined Desktop Client";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };
  outputs =
    { nixpkgs, ... }:
    let
      inherit (nixpkgs) lib;
      inherit (builtins) attrNames;
      inherit (lib.attrsets) genAttrs;
      architectures = attrNames nixpkgs.legacyPackages;
      forAllSystems = genAttrs architectures;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        rec {
          default = streamlined-client;
          streamlined-client = pkgs.callPackage ./package.nix { };
        }
      );
    };
}
