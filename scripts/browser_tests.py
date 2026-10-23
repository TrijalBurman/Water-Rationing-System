"""Install and run browser checks with an isolated demo on Windows, Linux, or macOS."""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "browser"


def environment():
    env = os.environ.copy()
    temporary = RUNTIME / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env.update(
        PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".cache" / "playwright"),
        XDG_CACHE_HOME=str(ROOT / ".cache"),
        XDG_CONFIG_HOME=str(RUNTIME / "config"),
        TMPDIR=str(temporary),
        TMP=str(temporary),
        TEMP=str(temporary),
        SCREENSHOT_DIR=str(RUNTIME / "screenshots"),
    )
    return env


def executable(name):
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f"Install Node.js LTS (including npm); {name} was not found.")
    return result


def run_command(command, env):
    subprocess.run([str(part) for part in command], cwd=ROOT, env=env, check=True)


def install():
    env = environment()
    run_command(
        [
            executable("npm"),
            "--cache",
            ROOT / ".cache" / "npm",
            "--prefix",
            RUNTIME,
            "install",
            "--no-audit",
            "--no-fund",
            "--save-exact",
            "playwright@1.63.0",
            "axe-core@4.13.0",
        ],
        env,
    )
    run_command(
        [executable("node"), RUNTIME / "node_modules/playwright/cli.js", "install", "chromium"],
        env,
    )


def run_checks():
    env = environment()
    node = executable("node")
    if not (RUNTIME / "node_modules/playwright/cli.js").is_file():
        raise RuntimeError("First run: python scripts/browser_tests.py install")
    # Select an available loopback port; each run also owns a new SQLite directory.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env.update(
        APP_MODE="demo",
        DEMO_AUTOSTART="true",
        API_KEY="",
        MQTT_HOST="",
        INFLUX_URL="",
        TEST_BASE_URL=base,
    )
    with tempfile.TemporaryDirectory(prefix="demo-", dir=RUNTIME) as data_dir:
        env["DATA_DIR"] = data_dir
        with (RUNTIME / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 60
                while True:
                    if server.poll() is not None:
                        raise RuntimeError(f"Demo exited; see {RUNTIME / 'server.log'}")
                    try:
                        with urllib.request.urlopen(base + "/health/ready", timeout=1):
                            break
                    except (OSError, urllib.error.URLError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError(
                                "Demo startup timed out; see .runtime/browser/server.log"
                            ) from None
                        time.sleep(0.2)
                run_command([node, ROOT / "tests/browser-smoke.cjs"], env)
                run_command([node, ROOT / "tests/frontend-audit.cjs"], env)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    print("Browser checks passed. Reports: .runtime/browser and .runtime/dark-review")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "run"])
    args = parser.parse_args()
    try:
        {"install": install, "run": run_checks}[args.command]()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
