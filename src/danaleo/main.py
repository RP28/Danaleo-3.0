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
    "nbformat": "nbformat",
    "pydantic": "pydantic",
}


def _missing_modules() -> list[str]:
    missing: list[str] = []

    for module_name, package_name in REQUIRED_MODULES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)

    return missing


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
        "Avoid running Danaleo with a different Python interpreter than the one "
        "where you installed it."
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
            "The React frontend is not built, and Danaleo could not find npm. "
            "Install Node.js/npm for development, or install a packaged Danaleo "
            "wheel that already contains the built frontend."
        ) from exc
    except subprocess.CalledProcessError as exc:
        joined = " ".join(command)
        raise RuntimeError(
            f"Command failed while preparing the Danaleo UI:\n\n"
            f"  {joined}\n\n"
            f"Working directory: {cwd}"
        ) from exc


def _ensure_frontend_built(build_if_missing: bool = True) -> None:
    if _static_ui_exists():
        return

    if not build_if_missing:
        raise RuntimeError(
            "The Danaleo React UI is not built.\n\n"
            f"Missing: {INDEX_FILE}\n\n"
            "Run this from the repo root:\n\n"
            "  cd frontend\n"
            "  npm install\n"
            "  npm run build"
        )

    repo_root = _find_repo_root()
    if repo_root is None:
        raise RuntimeError(
            "The packaged Danaleo frontend is missing, and the source "
            "frontend folder was not found.\n\n"
            "For end users, install a wheel that includes the built UI assets.\n"
            "For development, run Danaleo from the project repo so the "
            "frontend folder is available."
        )

    frontend_dir = repo_root / "frontend"
    npm = shutil.which("npm")

    if npm is None:
        raise RuntimeError(
            "The Danaleo React UI is not built, and npm is not installed.\n\n"
            "For development, install Node.js/npm, then run Danaleo again.\n"
            "For normal users, install a packaged Danaleo wheel that already "
            "contains the built frontend."
        )

    install_command = [npm, "ci"] if (frontend_dir / "package-lock.json").exists() else [npm, "install"]

    print("Danaleo frontend is missing. Installing frontend packages...")
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
) -> None:
    """
    Start the Danaleo local EDA workspace.

    This function:
    1. checks Python runtime dependencies,
    2. checks whether the built React UI exists,
    3. builds the UI in source/dev mode if it is missing,
    4. checks whether the requested port is available,
    5. launches the FastAPI server on localhost.
    """

    if check_env:
        _ensure_python_dependencies()

    _ensure_frontend_built(build_if_missing=build_ui)
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
        "--no-check-env",
        action="store_true",
        help="Skip Python dependency checks before starting",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        start(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            build_ui=not args.no_build_ui,
            check_env=not args.no_check_env,
        )
    except RuntimeError as exc:
        print(f"\nDanaleo startup failed:\n\n{exc}\n", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()