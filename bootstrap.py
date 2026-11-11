"""First-run bootstrap for the Block Story character save editor.

The launcher (``start.bat``) creates ``.venv`` and then calls this script.
It verifies every pinned package in ``requirements.txt``, installs anything
missing or outdated, and starts Streamlit on the first free local port.

Usage:
    python bootstrap.py             # check, install if needed, start
    python bootstrap.py --check     # only verify dependencies
    python bootstrap.py --no-browser
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
MIN_PYTHON = (3, 12)
DEFAULT_PORT = 8501
MIRROR = "https://mirrors.aliyun.com/pypi/simple/"


def parse_requirements(path: Path = REQUIREMENTS) -> list[tuple[str, str]]:
    """Return the pinned ``name==version`` pairs from requirements.txt."""
    if not path.is_file():
        raise FileNotFoundError(path)
    pinned: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        name, version = name.strip(), version.strip()
        if name and version:
            pinned.append((name, version))
    return pinned


def missing_requirements(pinned: list[tuple[str, str]]) -> list[str]:
    """Describe packages that are missing or do not match the pinned version."""
    problems: list[str] = []
    for name, expected in pinned:
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            problems.append(f"{name} (not installed)")
            continue
        if actual != expected:
            problems.append(f"{name} {actual} (expected {expected})")
    return problems


def install_requirements() -> bool:
    print("Installing dependencies from requirements.txt ...", flush=True)
    result = subprocess.run([
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "-r", str(REQUIREMENTS),
    ])
    return result.returncode == 0


def find_free_port(start: int = DEFAULT_PORT, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    return start


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check dependencies and start the editor.")
    parser.add_argument("--check", action="store_true", help="only verify dependencies")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = parser.parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        print(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required; "
              f"this interpreter is {sys.version.split()[0]}.")
        return 1

    try:
        pinned = parse_requirements()
    except OSError as exc:
        print(f"Cannot read requirements.txt: {exc}")
        return 1
    if not pinned:
        print("requirements.txt does not contain any pinned packages.")
        return 1

    problems = missing_requirements(pinned)
    if problems:
        print("Dependencies are missing or have the wrong version:")
        for item in problems:
            print(f"  - {item}")
        if args.check:
            return 1
        if not install_requirements():
            print("\nInstallation failed. If PyPI is slow or blocked, retry with a mirror:")
            print(f'  "{sys.executable}" -m pip install -r requirements.txt -i {MIRROR}')
            return 1
        problems = missing_requirements(pinned)
        if problems:
            print("Dependencies are still incomplete after installation:")
            for item in problems:
                print(f"  - {item}")
            return 1
    else:
        print("Dependencies OK.")

    if args.check:
        return 0

    port = find_free_port()
    url = f"http://localhost:{port}"
    print(f"\nStarting at {url}")
    print("Press Ctrl+C in this window to stop.\n", flush=True)

    if not args.no_browser:
        timer = threading.Timer(2.5, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()

    command = [
        sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.headless", "true", "--server.address", "127.0.0.1",
        "--server.port", str(port),
    ]
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
