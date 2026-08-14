"""Desktop entry point for the Engineering Stamp Placer.

This launcher starts the Streamlit server in-process and opens the default web
browser. It is the entry point for the packaged (PyInstaller) build, so a
recipient can run a single executable without installing Python or any
dependencies. Running it from source (``python desktop_app.py``) behaves the
same as ``streamlit run app.py`` but picks a free port and opens the browser.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _resource_dir() -> Path:
    """Folder containing the bundled resources (``app.py``, ``stamper/`` …).

    PyInstaller unpacks bundled data to ``sys._MEIPASS`` at runtime; when running
    from source it is simply this file's directory.
    """
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _free_port() -> int:
    """Return an available localhost TCP port chosen by the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _disable_ws_keepalive_ping() -> None:
    """Turn off uvicorn's server->client WebSocket keepalive ping.

    Streamlit 1.57 serves over uvicorn with ``ws="auto"``, which selects the
    ``websockets`` *legacy* protocol. On Python 3.14 that protocol's
    ``keepalive_ping`` task crashes with ``AssertionError`` in ``_drain_helper``
    whenever a ping fires while a large message is still draining to the browser
    (our full-page preview images do exactly that). The crash tears down the
    WebSocket, so the app appears frozen — clicks and sliders stop working and
    "remove stamp" surfaces the traceback. Reproduced and fixed in isolation:
    with the keepalive disabled the race cannot occur.

    The app is single-user on localhost, so there is no proxy/NAT idle timeout
    that a keepalive would protect against; disabling it is safe. Wrapped in
    try/except so a future Streamlit refactor can never stop the app launching.
    """
    try:
        from streamlit.web.server.starlette import starlette_server as _ss

        _orig = _ss._get_uvicorn_config_kwargs

        def _patched():
            kwargs = _orig()
            kwargs["ws_ping_interval"] = None
            kwargs["ws_ping_timeout"] = None
            return kwargs

        _ss._get_uvicorn_config_kwargs = _patched
    except Exception:
        # Best-effort hardening; never block startup if internals move.
        pass


def _open_browser_when_ready(url: str, host: str, port: int) -> None:
    """Open *url* once the server is accepting connections (or after a timeout)."""
    for _ in range(100):  # up to ~10 s
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex((host, port)) == 0:
                break
        time.sleep(0.1)
    webbrowser.open(url)


def main() -> None:
    app_path = os.path.abspath(str(_resource_dir() / "app.py"))
    host = "127.0.0.1"
    # Honour an explicit port if set (handy for a fixed bookmark); otherwise let
    # the OS pick a free one so multiple launches never collide.
    port = int(os.environ.get("STAMPER_SERVER_PORT", "0") or 0) or _free_port()
    url = f"http://localhost:{port}"

    from streamlit import config as st_config
    from streamlit.web import bootstrap

    # Must run before the server starts (see the function docstring): prevents the
    # websockets-legacy keepalive crash that otherwise freezes the app.
    _disable_ws_keepalive_ping()

    flag_options = {
        "server.address": host,
        "server.port": port,
        "server.headless": True,          # we open the browser ourselves
        "server.fileWatcherType": "none",  # nothing to hot-reload in a frozen app
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
    }

    # Mirror how ``streamlit run`` initialises configuration before launching.
    st_config._main_script_path = app_path
    bootstrap.load_config_options(flag_options=flag_options)

    threading.Thread(
        target=_open_browser_when_ready, args=(url, host, port), daemon=True
    ).start()
    print(f"Engineering Stamp Placer is running at {url}")
    print("Close this window to quit the application.")

    bootstrap.run(app_path, is_hello=False, args=[], flag_options=flag_options)


if __name__ == "__main__":
    main()
