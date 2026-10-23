#!/usr/bin/env python3
"""Native project commands for Windows, Linux, and macOS (no shell required)."""

from __future__ import annotations

import argparse
import csv
import io
import os
import secrets
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = (
    "API_KEY",
    "MQTT_PASSWORD",
    "MQTT_DEVICE_PASSWORD",
    "INFLUX_ADMIN_PASSWORD",
    "INFLUX_TOKEN",
    "GRAFANA_ADMIN_PASSWORD",
)


def windows() -> bool:
    return os.name == "nt"


def python_path(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if windows() else "bin/python")


def project_environment() -> dict[str, str]:
    env = os.environ.copy()
    temporary = ROOT / ".runtime"
    cache = ROOT / ".cache"
    temporary.mkdir(exist_ok=True)
    cache.mkdir(exist_ok=True)
    env.update(
        TEMP=str(temporary),
        TMP=str(temporary),
        TMPDIR=str(temporary),
        PIP_CACHE_DIR=str(cache / "pip"),
        XDG_CACHE_HOME=str(cache),
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


def run(command: list[str], *, env: dict[str, str] | None = None, quiet: bool = False):
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env if env is not None else project_environment(),
        check=True,
        text=True,
        capture_output=quiet,
    )


def setup() -> None:
    env = project_environment()
    (ROOT / "data").mkdir(exist_ok=True)
    interpreter = python_path(ROOT / ".venv")
    if interpreter.is_file():
        try:
            run(
                [
                    str(interpreter),
                    "-c",
                    "import sys; raise SystemExit(sys.version_info < (3, 12))",
                ],
                env=env,
                quiet=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError(
                "The existing .venv cannot run Python 3.12+. Rename it, then run setup again."
            ) from error
    else:
        run([sys.executable, "-m", "venv", str(ROOT / ".venv")], env=env)
    try:
        run([str(interpreter), "-m", "pip", "--version"], env=env, quiet=True)
    except subprocess.CalledProcessError:
        run([str(interpreter), "-m", "ensurepip", "--upgrade"], env=env)
    run(
        [str(interpreter), "-m", "pip", "install", "-c", "requirements.lock", "-e", ".[dev]"],
        env=env,
    )
    print("Ready. Run: python scripts/manage.py demo")


def demo(port: int, data_dir: Path | None = None) -> None:
    interpreter = python_path(ROOT / ".venv")
    if not interpreter.is_file():
        raise RuntimeError("Run python scripts/manage.py setup first.")
    env = project_environment()
    env.update(APP_MODE="demo", DEMO_AUTOSTART="true", MQTT_HOST="", INFLUX_URL="", API_KEY="")
    if data_dir is not None:
        env["DATA_DIR"] = str((ROOT / data_dir).resolve())
    run(
        [
            str(interpreter),
            "-m",
            "uvicorn",
            "backend.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
    )


@lru_cache(maxsize=1)
def windows_identity() -> str:
    result = run(["whoami", "/user", "/fo", "csv", "/nh"], quiet=True)
    try:
        sid = next(csv.reader(io.StringIO(result.stdout.strip())))[1]
    except (IndexError, StopIteration) as error:
        raise RuntimeError(
            "Cannot identify the current Windows account to protect secrets."
        ) from error
    if not sid.startswith("S-1-") or not all(part.isdigit() for part in sid.split("-")[1:]):
        raise RuntimeError("Cannot identify the current Windows account to protect secrets.")
    return "*" + sid


def restrict(path: Path, *, directory: bool = False) -> None:
    if windows():
        identity = windows_identity()
        if directory:
            # Replace the directory DACL in one operation: /grant:r alone would
            # retain any explicit grants left by an older bootstrap or copy.
            script = (
                "$ErrorActionPreference = 'Stop'; "
                "$acl = [System.Security.AccessControl.DirectorySecurity]::new(); "
                "$sid = [System.Security.Principal.SecurityIdentifier]::new($env:WATERWISE_ACL_SID); "
                "$rule = [System.Security.AccessControl.FileSystemAccessRule]::new("
                "$sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'); "
                "$acl.SetAccessRuleProtection($true, $false); $acl.AddAccessRule($rule); "
                "Set-Acl -LiteralPath $env:WATERWISE_ACL_PATH -AclObject $acl"
            )
            env = project_environment()
            env.update(WATERWISE_ACL_PATH=str(path), WATERWISE_ACL_SID=identity[1:])
            run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                env=env,
                quiet=True,
            )
        else:
            # Every credential file is newly created before this call, so it has
            # no previous explicit grants to retain. Remove inherited access.
            run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:F"],
                quiet=True,
            )
    else:
        path.chmod(0o700 if directory else 0o600)


def write_private(path: Path, content: str) -> None:
    descriptor, filename = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(filename)
    try:
        restrict(temporary)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def env_values(lines: list[str]) -> dict[str, str]:
    values = {}
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def bootstrap() -> None:
    # Complete daemon checks before creating or changing credentials.
    run(["docker", "compose", "version"], quiet=True)
    daemon = run(["docker", "info", "--format", "{{.OSType}}"], quiet=True)
    if daemon.stdout.strip() != "linux":
        raise RuntimeError("Start Docker Desktop and switch it to Linux containers.")

    path = ROOT / ".env"
    source = path if path.exists() else ROOT / ".env.example"
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    values = env_values(lines)
    if values.get("MQTT_USERNAME", "backend") != "backend":
        raise RuntimeError("MQTT_USERNAME must remain backend to match mosquitto/acl.")
    for key in SECRET_KEYS:
        if not values.get(key):
            values[key] = secrets.token_hex(32)
        if any(character in values[key] for character in "\r\n:$#\"' \\"):
            raise RuntimeError(
                f"{key} contains unsupported characters; use an alphanumeric password."
            )

    updated, written = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if not line.lstrip().startswith("#") and key in SECRET_KEYS:
            if key not in written:
                updated.append(f"{key}={values[key]}")
                written.add(key)
        else:
            updated.append(line)
    updated.extend(f"{key}={values[key]}" for key in SECRET_KEYS if key not in written)

    directory = ROOT / ".secrets"
    directory.mkdir(exist_ok=True)
    restrict(directory, directory=True)
    descriptor, filename = tempfile.mkstemp(prefix="mosquitto-", suffix=".pending", dir=directory)
    pending = Path(filename)
    try:
        restrict(pending)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(
                f"backend:{values['MQTT_PASSWORD']}\ntank-01:{values['MQTT_DEVICE_PASSWORD']}\n"
            )
        mount = io.StringIO()
        csv.writer(mount, lineterminator="").writerow(
            ["type=bind", f"source={directory}", "target=/work"]
        )
        command = ["docker", "run", "--rm"]
        if not windows():
            command.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
        command.extend(
            [
                "--mount",
                mount.getvalue(),
                "--entrypoint",
                "mosquitto_passwd",
                "eclipse-mosquitto:2.0",
                "-U",
                f"/work/{pending.name}",
            ]
        )
        run(command, quiet=True)
        # Do not change live credentials until the broker's hash command succeeds.
        device_path = directory / "tank-01.env"
        device_values = (
            env_values(device_path.read_text(encoding="utf-8-sig").splitlines())
            if device_path.exists()
            else {}
        )
        write_private(path, "\n".join(updated) + "\n")
        write_private(
            device_path,
            "# Copy these values into the ESP32 private configuration. Set your host LAN address.\n"
            f"MQTT_HOST={device_values.get('MQTT_HOST', 'YOUR_COMPUTER_LAN_IP')}\n"
            f"MQTT_PORT={values.get('MQTT_PORT', '1883')}\n"
            f"MQTT_USERNAME=tank-01\nMQTT_PASSWORD={values['MQTT_DEVICE_PASSWORD']}\n"
            "DEVICE_ID=tank-01\nFLAT_ID=101\n",
        )
        if not windows():
            # The private host directory remains 0700; the separately mounted hash
            # must also be readable by the broker's non-root container account.
            pending.chmod(0o644)
        os.replace(pending, directory / "mosquitto.passwd")
    finally:
        if descriptor != -1:
            os.close(descriptor)
        pending.unlink(missing_ok=True)
    run(["docker", "compose", "config", "--quiet"], quiet=True)
    print(
        "Credentials saved in .env and .secrets/tank-01.env; existing credentials were preserved."
    )
    print("Start the stack with: docker compose up --build -d")


def port_number(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535") from error
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "setup", help="create the local Python environment and install dependencies"
    )
    launcher = commands.add_parser("demo", help="run the loopback-only simulator and dashboard")
    launcher.add_argument("--port", type=port_number, default=os.environ.get("PORT", "8000"))
    launcher.add_argument("--data-dir", type=Path, help="use a separate recorder directory")
    commands.add_parser("bootstrap", help="generate and protect Docker deployment credentials")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):  # noqa: UP036 - this entry point runs before dependency setup
        parser.error("Python 3.12 or newer is required")
    try:
        if args.command == "setup":
            setup()
        elif args.command == "demo":
            demo(args.port, args.data_dir)
        else:
            bootstrap()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
