"""Exercise a Windows-specific startup requirement even on a Linux development host."""

import os
import subprocess
import sys
from pathlib import Path


def test_startup_without_system_timezone_database(tmp_path):
    env = os.environ.copy()
    env["PYTHONTZPATH"] = ""
    script = """
from datetime import UTC, datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
from backend.config import Settings
from backend.storage import Recorder
settings = Settings(_env_file=None, app_mode='demo', demo_autostart=False,
                    api_key='', mqtt_host='', influx_url='', quota_timezone='Asia/Kolkata')
now = datetime(2026, 1, 1, 18, 30, tzinfo=UTC)
assert now.astimezone(ZoneInfo(settings.quota_timezone)).isoformat() == '2026-01-02T00:00:00+05:30'
recorder = Recorder(Path(sys.argv[1]) / 'quota.sqlite3', settings.quota_timezone, 6)
try:
    assert recorder.quota('101', 150, now)['date'] == '2026-01-02'
finally:
    recorder.close()
"""
    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
    )
