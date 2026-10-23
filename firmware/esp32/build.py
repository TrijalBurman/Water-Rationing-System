#!/usr/bin/env python3
"""Build/upload the ESP32 firmware with PlatformIO on Windows, Linux or macOS."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = PROJECT_DIR.parent.parent


def build_environment():
    """Keep downloaded toolchains, caches and temporary files in this project."""
    env = os.environ.copy()
    cache_dir = PROJECT_DIR / ".cache"
    temporary_dir = cache_dir / "tmp"
    temporary_dir.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "PLATFORMIO_CORE_DIR": str(PROJECT_DIR / ".platformio"),
            "PIP_CACHE_DIR": str(cache_dir / "pip"),
            "XDG_CACHE_HOME": str(cache_dir),
            "TMPDIR": str(temporary_dir),
            "TMP": str(temporary_dir),
            "TEMP": str(temporary_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


def platformio_command(env):
    """Prefer module execution so relocated virtual environments still work."""
    python_suffix = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    candidates = [
        PROJECT_DIR / ".venv" / python_suffix,
        REPOSITORY_DIR / ".venv" / python_suffix,
        Path(sys.executable),
    ]
    seen = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        try:
            result = subprocess.run(
                [str(candidate), "-c", "import platformio"],
                cwd=PROJECT_DIR,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return [str(candidate), "-m", "platformio"]

    for name in ("pio", "platformio"):
        executable = shutil.which(name)
        if executable:
            return [str(Path(executable).absolute())]
    raise RuntimeError(
        "PlatformIO is not installed. Create firmware/esp32/.venv and install "
        "platformio==6.1.18 in that dedicated environment. "
        "See firmware/README.md for platform-specific commands."
    )


def main():
    try:
        env = build_environment()
        command = platformio_command(env)
        return subprocess.call(command + ["run"] + sys.argv[1:], cwd=PROJECT_DIR, env=env)
    except (OSError, RuntimeError) as exc:
        print(f"Firmware build failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
