from __future__ import annotations

import subprocess

import pytest

from danaleo import main


def test_missing_modules_and_dependency_error(monkeypatch):
    monkeypatch.setattr(
        main.importlib.util,
        "find_spec",
        lambda name: None if name in {"fastapi", "pandas"} else object(),
    )

    assert main._missing_modules() == ["fastapi", "pandas"]
    with pytest.raises(RuntimeError, match="Missing packages: fastapi, pandas"):
        main._ensure_python_dependencies()


def test_static_ui_exists_requires_index_assets_folder_and_javascript(tmp_path, monkeypatch):
    static = tmp_path / "static"
    monkeypatch.setattr(main, "STATIC_DIR", static)
    monkeypatch.setattr(main, "INDEX_FILE", static / "index.html")

    assert main._static_ui_exists() is False
    static.mkdir()
    (static / "index.html").write_text("ok")
    assert main._static_ui_exists() is False
    (static / "assets").mkdir()
    (static / "assets" / "style.css").write_text("css")
    assert main._static_ui_exists() is False
    (static / "assets" / "app.js").write_text("js")
    assert main._static_ui_exists() is True


def test_run_command_wraps_missing_and_failed_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(main.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(RuntimeError, match="Command not found"):
        main._run_command(["missing"], tmp_path)

    monkeypatch.setattr(
        main.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["npm"])),
    )
    with pytest.raises(RuntimeError, match="Command failed"):
        main._run_command(["npm", "run", "build"], tmp_path)


def test_ensure_frontend_built_short_circuits_or_reports_disabled(monkeypatch):
    monkeypatch.setattr(main, "_static_ui_exists", lambda: True)
    monkeypatch.setattr(main, "_frontend_dir", lambda: (_ for _ in ()).throw(AssertionError("not needed")))
    main._ensure_frontend_built()

    monkeypatch.setattr(main, "_static_ui_exists", lambda: False)
    with pytest.raises(RuntimeError, match="React UI is not built"):
        main._ensure_frontend_built(build_if_missing=False)


def test_ensure_frontend_built_uses_ci_and_build(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package-lock.json").write_text("{}")
    calls = []
    states = iter([False, True])

    monkeypatch.setattr(main, "_static_ui_exists", lambda: next(states))
    monkeypatch.setattr(main, "_frontend_dir", lambda: frontend)
    monkeypatch.setattr(main.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(main, "_run_command", lambda command, cwd: calls.append((command, cwd)))

    main._ensure_frontend_built(force_rebuild=True)

    assert calls == [
        (["/usr/bin/npm", "ci"], frontend),
        (["/usr/bin/npm", "run", "build"], frontend),
    ]


def test_ensure_frontend_built_requires_npm(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_static_ui_exists", lambda: False)
    monkeypatch.setattr(main, "_frontend_dir", lambda: tmp_path)
    monkeypatch.setattr(main.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="npm is not installed"):
        main._ensure_frontend_built()


def test_frontend_dir_reports_missing_source_layout(monkeypatch):
    monkeypatch.setattr(main, "_find_repo_root", lambda: None)

    with pytest.raises(RuntimeError, match="source frontend folder was not found"):
        main._frontend_dir()


def test_ensure_frontend_built_can_skip_install_and_detect_missing_output(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_static_ui_exists", lambda: False)
    monkeypatch.setattr(main, "_frontend_dir", lambda: tmp_path)
    monkeypatch.setattr(main.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(main, "_run_command", lambda command, cwd: calls.append(command))

    with pytest.raises(RuntimeError, match="build finished"):
        main._ensure_frontend_built(install_dependencies=False)

    assert calls == [["/usr/bin/npm", "run", "build"]]


def test_check_port_available_reports_conflict(monkeypatch):
    class BusySocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            raise OSError("busy")

    monkeypatch.setattr(main.socket, "socket", lambda *args: BusySocket())

    with pytest.raises(RuntimeError, match="Port 8765 is already in use"):
        main._check_port_available("127.0.0.1", 8765)


def test_start_orchestrates_checks_browser_and_uvicorn(monkeypatch):
    calls = []

    monkeypatch.setattr(main, "_ensure_python_dependencies", lambda: calls.append("deps"))
    monkeypatch.setattr(main, "_ensure_frontend_built", lambda **kwargs: calls.append(("ui", kwargs)))
    monkeypatch.setattr(main, "_check_port_available", lambda host, port: calls.append(("port", host, port)))
    monkeypatch.setattr(main, "_open_browser", lambda url: calls.append(("browser", url)))

    class ImmediateTimer:
        def __init__(self, _delay, fn, args):
            self.fn = fn
            self.args = args

        def start(self):
            self.fn(*self.args)

    monkeypatch.setattr(main.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: calls.append(("uvicorn", app, kwargs)),
    )

    main.start(host="0.0.0.0", port=9000, force_build_ui=True)

    assert "deps" in calls
    assert ("browser", "http://127.0.0.1:9000") in calls
    assert ("uvicorn", "danaleo.server.app:app", {"host": "0.0.0.0", "port": 9000, "reload": False}) in calls


def test_cli_build_only_and_runtime_error(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(main, "_ensure_python_dependencies", lambda: calls.append("deps"))
    monkeypatch.setattr(main, "_ensure_frontend_built", lambda **kwargs: calls.append(kwargs))

    main.cli(["--build-ui-only", "--skip-npm-install"])
    assert calls[-1]["force_rebuild"] is True
    assert calls[-1]["install_dependencies"] is False

    monkeypatch.setattr(main, "_ensure_python_dependencies", lambda: (_ for _ in ()).throw(RuntimeError("bad env")))
    with pytest.raises(SystemExit) as exc:
        main.cli([])
    assert exc.value.code == 1
    assert "bad env" in capsys.readouterr().err


def test_cli_forwards_server_options(monkeypatch):
    captured = {}
    monkeypatch.setattr(main, "_ensure_python_dependencies", lambda: None)
    monkeypatch.setattr(main, "start", lambda **kwargs: captured.update(kwargs))

    main.cli(
        [
            "--host",
            "0.0.0.0",
            "--port",
            "9999",
            "--no-browser",
            "--no-build-ui",
            "--skip-npm-install",
        ]
    )

    assert captured == {
        "host": "0.0.0.0",
        "port": 9999,
        "open_browser": False,
        "build_ui": False,
        "check_env": False,
        "force_build_ui": False,
        "install_ui_dependencies": False,
    }
