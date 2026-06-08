from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def _open_browser(url: str) -> None:
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the Danaleo local EDA workspace")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind to")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.0, _open_browser, args=(url,)).start()

    print(f"Danaleo is running at {url}")
    uvicorn.run("danaleo.server.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
