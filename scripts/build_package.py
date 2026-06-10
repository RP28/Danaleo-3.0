from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"

EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
}


def _ignore(directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in EXCLUDED_DIRECTORIES
        or name.endswith(".egg-info")
        or name.startswith("._")
        or name == ".DS_Store"
        or name == "__pycache__"
    }


def _run(command: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True, env={**os.environ, "COPYFILE_DISABLE": "1"})


def main() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is required to rebuild the packaged frontend")

    _run([npm, "ci"], ROOT / "frontend")
    _run([npm, "run", "build"], ROOT / "frontend")

    with tempfile.TemporaryDirectory(prefix="danaleo-package-") as temporary:
        staged_root = Path(temporary) / "source"
        staged_dist = Path(temporary) / "dist"
        shutil.copytree(ROOT, staged_root, ignore=_ignore)
        _run([sys.executable, "-m", "build", "--outdir", str(staged_dist)], staged_root)

        DIST_DIR.mkdir(exist_ok=True)
        for artifact in staged_dist.iterdir():
            if artifact.suffix == ".whl" or artifact.name.endswith(".tar.gz"):
                shutil.copyfile(artifact, DIST_DIR / artifact.name)

    distributions = sorted(
        path
        for path in DIST_DIR.iterdir()
        if not path.name.startswith("._")
        and (path.suffix == ".whl" or path.name.endswith(".tar.gz"))
    )
    if not distributions:
        raise SystemExit("No distributions were created")

    _run([sys.executable, "-m", "twine", "check", *(str(path) for path in distributions)], ROOT)
    print(f"Built and checked Danaleo distributions in: {DIST_DIR}")


if __name__ == "__main__":
    main()
