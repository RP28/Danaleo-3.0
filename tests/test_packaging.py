from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_defines_installable_package_and_cli():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["build-system"]["build-backend"] == "setuptools.build_meta"
    assert config["project"]["name"] == "danaleo"
    assert config["project"]["scripts"]["danaleo"] == "danaleo.cli:main"
    assert config["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert config["tool"]["setuptools"]["package-data"]["danaleo"] == ["server/static/**/*"]


def test_packaged_frontend_assets_and_module_entrypoint_exist():
    static_dir = ROOT / "src" / "danaleo" / "server" / "static"

    assert (ROOT / "src" / "danaleo" / "__main__.py").exists()
    assert (static_dir / "index.html").exists()
    assert list((static_dir / "assets").glob("*.js"))
    assert list((static_dir / "assets").glob("*.css"))


def test_distribution_manifest_includes_license_and_frontend():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "include LICENSE" in manifest
    assert "recursive-include src/danaleo/server/static *" in manifest
    assert "._*" in manifest
    assert "src/danaleo/server/static/*" not in gitignore


def test_generated_packaging_metadata_is_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "*.egg-info/" in gitignore


def test_release_script_stages_build_away_from_filesystem_metadata():
    script = (ROOT / "scripts" / "build_package.py").read_text(encoding="utf-8")

    assert "TemporaryDirectory" in script
    assert 'name.startswith("._")' in script
    assert 'not path.name.startswith("._")' in script
    assert '"COPYFILE_DISABLE": "1"' in script
    assert '"-m", "build"' in script
    assert '"-m", "twine", "check"' in script
