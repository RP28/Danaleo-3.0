from __future__ import annotations

import argparse
import importlib.util
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Iterable


PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "server" / "static"
INDEX_FILE = STATIC_DIR / "index.html"

REQUIRED_MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "multipart": "python-multipart",
    "pandas": "pandas",
    "numpy": "numpy",
    "plotly": "plotly",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "nbformat": "nbformat",
    "pydantic": "pydantic",
}

APPLEDOUBLE_MAGIC = b"\x00\x05\x16\x07"


def _missing_modules() -> list[str]:
    missing: list[str] = []

    for module_name, package_name in REQUIRED_MODULES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)

    return missing


def _remove_matplotlib_appledouble_files() -> int:
    """Remove macOS metadata files that Matplotlib mistakes for style files."""
    spec = importlib.util.find_spec("matplotlib")
    if spec is None or not spec.submodule_search_locations:
        return 0

    removed = 0
    for package_dir in spec.submodule_search_locations:
        style_dir = Path(package_dir) / "mpl-data" / "stylelib"
        if not style_dir.is_dir():
            continue

        for path in style_dir.glob("._*.mplstyle"):
            try:
                with path.open("rb") as metadata_file:
                    if metadata_file.read(4) != APPLEDOUBLE_MAGIC:
                        continue
                path.unlink()
                removed += 1
            except OSError as exc:
                raise RuntimeError(
                    "macOS metadata files in Matplotlib's style directory prevent it from loading.\n\n"
                    f"Danaleo could not remove: {path}\n\n"
                    f"Remove the ._* files from this directory and try again:\n\n  {style_dir}"
                ) from exc

    return removed


def _ensure_python_dependencies() -> None:
    missing = _missing_modules()

    if not missing:
        return

    missing_text = ", ".join(sorted(set(missing)))

    raise RuntimeError(
        "Danaleo is not fully installed in this Python environment.\n\n"
        f"Missing packages: {missing_text}\n\n"
        "Install Danaleo properly with one of these commands:\n\n"
        "  python -m pip install -e .\n"
        "  python -m pip install .\n"
        "  python -m pip install danaleo\n\n"
        "Avoid running Danaleo with a different Python interpreter than the one where you installed it."
    )


def _find_repo_root() -> Path | None:
    for parent in [PACKAGE_DIR, *PACKAGE_DIR.parents]:
        if (parent / "frontend" / "package.json").exists():
            return parent

    return None


def _static_ui_exists() -> bool:
    if not INDEX_FILE.exists():
        return False

    assets_dir = STATIC_DIR / "assets"
    if not assets_dir.exists():
        return False

    return any(assets_dir.glob("*.js"))


def _run_command(command: list[str], cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Command not found: {command[0]}\n\n"
            "The React frontend is not built, and Danaleo could not find npm.\n"
            "Install Node.js/npm for development, or install a packaged Danaleo wheel "
            "that already contains the built frontend."
        ) from exc
    except subprocess.CalledProcessError as exc:
        joined = " ".join(command)
        raise RuntimeError(
            "Command failed while preparing the Danaleo UI:\n\n"
            f"  {joined}\n\n"
            f"Working directory: {cwd}"
        ) from exc


def _frontend_dir() -> Path:
    repo_root = _find_repo_root()

    if repo_root is None:
        raise RuntimeError(
            "The packaged Danaleo frontend is missing, and the source frontend folder was not found.\n\n"
            "For end users, install a wheel that includes the built UI assets.\n"
            "For development, run Danaleo from the project repo so the frontend folder is available."
        )

    frontend_dir = repo_root / "frontend"
    if not frontend_dir.exists():
        raise RuntimeError(f"Frontend folder not found: {frontend_dir}")

    return frontend_dir


def _ensure_frontend_built(
    build_if_missing: bool = True,
    force_rebuild: bool = False,
    install_dependencies: bool = True,
) -> None:
    if _static_ui_exists() and not force_rebuild:
        return

    if not build_if_missing and not force_rebuild:
        raise RuntimeError(
            "The Danaleo React UI is not built.\n\n"
            f"Missing: {INDEX_FILE}\n\n"
            "Run this from the repo root:\n\n"
            "  cd frontend\n"
            "  npm install\n"
            "  npm run build"
        )

    frontend_dir = _frontend_dir()
    npm = shutil.which("npm")

    if npm is None:
        raise RuntimeError(
            "The Danaleo React UI is not built, and npm is not installed.\n\n"
            "For development, install Node.js/npm, then run Danaleo again.\n"
            "For normal users, install a packaged Danaleo wheel that already contains the built frontend."
        )

    if install_dependencies:
        install_command = [npm, "ci"] if (frontend_dir / "package-lock.json").exists() else [npm, "install"]
        print("Installing Danaleo frontend packages...")
        _run_command(install_command, cwd=frontend_dir)

    print("Building Danaleo frontend...")
    _run_command([npm, "run", "build"], cwd=frontend_dir)

    if not _static_ui_exists():
        raise RuntimeError(
            "The frontend build finished, but Danaleo still could not find "
            f"the built UI at {INDEX_FILE}."
        )


def _check_port_available(host: str, port: int) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError as exc:
        raise RuntimeError(
            f"Port {port} is already in use on {host}.\n\n"
            f"Try another port, for example:\n\n"
            f"  danaleo --port {port + 1}"
        ) from exc


def _open_browser(url: str) -> None:
    webbrowser.open(url)


def start(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    build_ui: bool = True,
    check_env: bool = True,
    force_build_ui: bool = False,
    install_ui_dependencies: bool = True,
) -> None:
    """
    Start the Danaleo local EDA workspace.

    This function:
    1. checks Python runtime dependencies,
    2. checks whether the built React UI exists,
    3. builds the UI in source/dev mode if needed or requested,
    4. checks whether the requested port is available,
    5. launches the FastAPI server on localhost.
    """
    if check_env:
        _ensure_python_dependencies()

    _remove_matplotlib_appledouble_files()

    _ensure_frontend_built(
        build_if_missing=build_ui,
        force_rebuild=force_build_ui,
        install_dependencies=install_ui_dependencies,
    )

    _check_port_available(host, port)

    import uvicorn

    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"

    if open_browser:
        threading.Timer(1.0, _open_browser, args=(url,)).start()

    print(f"Danaleo is running at {url}")
    uvicorn.run(
        "danaleo.server.app:app",
        host=host,
        port=port,
        reload=False,
    )


def cli(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Launch the Danaleo local EDA workspace")

    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind to")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")

    parser.add_argument(
        "--no-build-ui",
        action="store_true",
        help="Do not automatically build the React UI if static files are missing",
    )
    parser.add_argument(
        "--build-ui",
        action="store_true",
        help="Force cd frontend && npm run build before starting the server",
    )
    parser.add_argument(
        "--build-ui-only",
        action="store_true",
        help="Run the frontend build and exit without starting the server",
    )
    parser.add_argument(
        "--skip-npm-install",
        action="store_true",
        help="Skip npm install/npm ci and run only npm run build",
    )
    parser.add_argument(
        "--no-check-env",
        action="store_true",
        help="Skip Python dependency checks before starting",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if not args.no_check_env:
            _ensure_python_dependencies()

        if args.build_ui_only:
            _ensure_frontend_built(
                build_if_missing=True,
                force_rebuild=True,
                install_dependencies=not args.skip_npm_install,
            )
            print("Danaleo frontend build complete.")
            return

        start(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            build_ui=not args.no_build_ui or args.build_ui,
            check_env=False,
            force_build_ui=args.build_ui,
            install_ui_dependencies=not args.skip_npm_install,
        )
    except RuntimeError as exc:
        print(f"\nDanaleo startup failed:\n\n{exc}\n", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
