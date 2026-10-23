#!/usr/bin/env python3
"""Compile and execute the control-logic tests without ESP32 or Bash tooling."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def compiler_command(explicit):
    requested = explicit or os.environ.get("CXX")
    if requested:
        # Treat CXX/--cxx as one executable path, including paths with spaces.
        executable = shutil.which(requested)
        if executable:
            return str(Path(executable).absolute())
        raise RuntimeError(f"C++ compiler not found: {requested}")
    candidates = ("cl", "g++", "clang++", "c++") if os.name == "nt" else ("g++", "clang++", "c++")
    for name in candidates:
        executable = shutil.which(name)
        if executable:
            return str(Path(executable).absolute())
    raise RuntimeError(
        "No C++ compiler found. On Windows, open Developer PowerShell for Visual "
        "Studio with the Desktop development with C++ tools installed, or add "
        "MinGW-w64 g++/Clang to PATH. On Linux/macOS install GCC or Clang. "
        "Use --cxx PATH to select a compiler."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", help="C++ compiler executable or full path (also read from CXX)")
    options = parser.parse_args()
    try:
        compiler = compiler_command(options.cxx)
        build_dir = PROJECT_DIR / ".build"
        temporary_dir = build_dir / "tmp"
        temporary_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({name: str(temporary_dir) for name in ("TMPDIR", "TMP", "TEMP")})
        binary = build_dir / ("control_logic_test.exe" if os.name == "nt" else "control_logic_test")
        source = PROJECT_DIR / "test/native/control_logic_test.cpp"
        include = PROJECT_DIR / "include"
        if Path(compiler).name.lower() in ("cl", "cl.exe", "clang-cl", "clang-cl.exe"):
            # MSVC has no /std:c++11 switch. Its oldest supported mode is C++14.
            command = [
                compiler,
                "/nologo",
                "/std:c++14",
                "/EHsc",
                "/W4",
                "/WX",
                "/permissive-",
                "/I" + str(include),
                str(source),
                "/Fe" + str(binary),
                "/Fo" + str(build_dir / "control_logic_test.obj"),
            ]
        else:
            command = [
                compiler,
                "-std=c++11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-I",
                str(include),
                str(source),
                "-o",
                str(binary),
            ]
        result = subprocess.run(command, cwd=build_dir, env=env, check=False)
        if result.returncode:
            return result.returncode
        return subprocess.call([str(binary)], cwd=build_dir, env=env)
    except (OSError, RuntimeError) as exc:
        print(f"Native firmware tests failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
