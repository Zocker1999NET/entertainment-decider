let
  nixpkgs = import <nixpkgs> { };
in
nixpkgs.callPackage ./package.nix { }
