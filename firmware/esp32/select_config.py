"""Select only this project's config.h, avoiding unrelated SDK config headers."""

from pathlib import Path

Import("env")

if (Path(env.subst("$PROJECT_DIR")) / "include" / "config.h").is_file():
    env.Append(CPPDEFINES=["WATER_HAS_LOCAL_CONFIG"])
