"""Small durable local recorder, daily usage ledger, and Influx write outbox."""

import json
import sqlite3
import threading
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Decision, Telemetry


class Recorder:
    def __init__(self, path: Path, timezone: str, gap_limit: float):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.timezone = ZoneInfo(timezone)
        self.gap_limit = gap_limit
        with self.connection:
            self.connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    flat_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    received_at REAL NOT NULL,
                    payload TEXT NOT NULL,
                    influx_sent INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(device_id, timestamp)
                );
                CREATE INDEX IF NOT EXISTS frames_device_time
                    ON frames(device_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS frames_outbox ON frames(influx_sent, id);
                CREATE TABLE IF NOT EXISTS quotas (
                    flat_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    consumed_l REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(flat_id, date)
                );
            """)

    def latest(self, device_id: str) -> dict | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT payload FROM frames WHERE device_id=? ORDER BY timestamp DESC LIMIT 1",
                (device_id,),
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def devices(self) -> list[str]:
        with self.lock:
            return [
                row[0]
                for row in self.connection.execute(
                    "SELECT DISTINCT device_id FROM frames ORDER BY device_id"
                )
            ]

    def save(self, telemetry: Telemetry, decision: Decision, received: datetime, source: str):
        snapshot = {
            "telemetry": telemetry.model_dump(mode="json"),
            "decision": decision.model_dump(mode="json"),
            "received_at": received.isoformat(),
            "source": source,
        }
        with self.lock, self.connection:
            previous = self.latest(telemetry.device_id)
            if previous:
                self._accumulate_usage(previous["telemetry"], telemetry)
            self.connection.execute(
                "INSERT INTO frames(device_id, flat_id, timestamp, received_at, payload) VALUES(?,?,?,?,?)",
                (
                    telemetry.device_id,
                    telemetry.flat_id,
                    telemetry.timestamp.timestamp(),
                    received.timestamp(),
                    json.dumps(snapshot, allow_nan=False),
                ),
            )
        return snapshot

    def _accumulate_usage(self, previous: dict, current: Telemetry):
        start = datetime.fromisoformat(previous["timestamp"])
        end = current.timestamp
        seconds = (end - start).total_seconds()
        if not 0 < seconds <= self.gap_limit or previous["flat_id"] != current.flat_id:
            return
        # Integrate delivered flow (trapezoid rule), splitting correctly at local midnight.
        cursor = start
        while cursor < end:
            day = cursor.astimezone(self.timezone).date()
            midnight = datetime.combine(day + timedelta(days=1), time.min, self.timezone)
            stop = min(end, midnight.astimezone(UTC))
            a = (cursor - start).total_seconds() / seconds
            b = (stop - start).total_seconds() / seconds
            delta = current.flow_out_lpm - previous["flow_out_lpm"]
            average = previous["flow_out_lpm"] + delta * (a + b) / 2
            liters = average * (stop - cursor).total_seconds() / 60
            self.connection.execute(
                "INSERT INTO quotas(flat_id,date,consumed_l) VALUES(?,?,?) "
                "ON CONFLICT(flat_id,date) DO UPDATE SET consumed_l=consumed_l+excluded.consumed_l",
                (current.flat_id, day.isoformat(), liters),
            )
            cursor = stop

    def quota(self, flat_id: str, allowance: float, now: datetime) -> dict:
        day = now.astimezone(self.timezone).date().isoformat()
        with self.lock:
            row = self.connection.execute(
                "SELECT consumed_l FROM quotas WHERE flat_id=? AND date=?", (flat_id, day)
            ).fetchone()
        consumed = row[0] if row else 0
        return {
            "date": day,
            "timezone": self.timezone.key,
            "consumed_l": round(consumed, 3),
            "allowance_l": allowance,
            "remaining_l": round(max(0, allowance - consumed), 3),
        }

    def recent(self, device_id: str, after: datetime, limit: int = 1500) -> list[dict]:
        with self.lock:
            ids = [
                row[0]
                for row in self.connection.execute(
                    "SELECT id FROM frames WHERE device_id=? AND timestamp>=? ORDER BY timestamp",
                    (device_id, after.timestamp()),
                )
            ]
            if not ids:
                return []
            # Sample identifiers before loading JSON, preserving both ends of the range.
            if len(ids) > limit:
                ids = [ids[round(i * (len(ids) - 1) / (limit - 1))] for i in range(limit)]
            placeholders = ",".join("?" for _ in ids)
            rows = self.connection.execute(
                f"SELECT payload FROM frames WHERE id IN ({placeholders}) ORDER BY timestamp", ids
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def pending(self, limit: int = 100) -> list[tuple[int, dict]]:
        with self.lock:
            return [
                (row[0], json.loads(row[1]))
                for row in self.connection.execute(
                    "SELECT id,payload FROM frames WHERE influx_sent=0 ORDER BY id LIMIT ?",
                    (limit,),
                )
            ]

    def mark_sent(self, ids: list[int]):
        with self.lock, self.connection:
            self.connection.executemany(
                "UPDATE frames SET influx_sent=1 WHERE id=?", [(i,) for i in ids]
            )

    def pending_count(self) -> int:
        with self.lock:
            return self.connection.execute(
                "SELECT count(*) FROM frames WHERE influx_sent=0"
            ).fetchone()[0]

    def prune(self, before: datetime):
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM frames WHERE timestamp<?", (before.timestamp(),))
            self.connection.execute("DELETE FROM quotas WHERE date<?", (before.date().isoformat(),))

    def reset(self, device_id: str):
        with self.lock, self.connection:
            flats = self.connection.execute(
                "SELECT DISTINCT flat_id FROM frames WHERE device_id=?", (device_id,)
            ).fetchall()
            self.connection.execute("DELETE FROM frames WHERE device_id=?", (device_id,))
            self.connection.executemany(
                "DELETE FROM quotas WHERE flat_id=?", [(r[0],) for r in flats]
            )

    def close(self):
        with self.lock:
            self.connection.close()
