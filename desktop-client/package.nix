{
  lib,
  writeText,
  python3Packages,
  mypy,
  ...
}:
let
  name = "streamlined-client";
  version = "2025.06.29";
  project_toml = writeText "${name}_pyproject" ''
    [build-system]
    requires = ["setuptools >= 61.0"]
    build-backend = "setuptools.build_meta"
    [project]
    name = "${name}"
    version = "${version}"
    requires-python = ">= 3.11"
    [project.scripts]
    ${name} = "streamlined.client.app:main"
  '';
in
python3Packages.buildPythonPackage {
  inherit name version;
  format = "pyproject";

  build-system = lib.singleton python3Packages.setuptools;

  dependencies = with python3Packages; [
    setuptools
  ];

  unpackPhase = ''
    cp ${project_toml} ./pyproject.toml
    mkdir --parent ./src/streamlined/client
    touch ./src/streamlined{,/client}/__init__.py
    cp -r ${./app.py} ./src/streamlined/client/app.py
    chmod --recursive u=rwX ./src  # required so further build steps can create wrapper files
    ${lib.getExe mypy} --strict ./src
  '';

  postInstall = ''
    mkdir --parent $out/share/applications
    STREAMLINED_DESKTOP_TEMPLATE=${./entry.desktop} $out/bin/${name} misc generate-desktop-file > $out/share/applications/${name}_uri.desktop
  '';

  meta = {
    description = "Streamlined Desktop Client";
    mainProgram = name;
  };
}
