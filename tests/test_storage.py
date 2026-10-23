from datetime import UTC, datetime, timedelta

from backend.controller import Controller
from backend.storage import Recorder


def test_usage_splits_at_local_midnight_and_ignores_gaps(tmp_path, frame):
    recorder = Recorder(tmp_path / "test.sqlite3", "Asia/Kolkata", 6)
    controller = Controller()
    # 18:30 UTC is midnight in India. Two seconds at 60 L/min => 1 L in each day.
    start = datetime(2026, 1, 1, 18, 29, 59, tzinfo=UTC)
    for seconds in (0, 2, 60):
        reading = frame(timestamp=start + timedelta(seconds=seconds), flow_out_lpm=60)
        recorder.save(reading, controller.decide(reading), reading.timestamp, "api")
    assert recorder.quota("101", 150, start)["consumed_l"] == 1
    assert recorder.quota("101", 150, start + timedelta(seconds=2))["consumed_l"] == 1
    recorder.close()


def test_outbox_only_acknowledges_successful_ids(tmp_path, frame):
    recorder = Recorder(tmp_path / "test.sqlite3", "UTC", 6)
    controller = Controller()
    for _ in range(2):
        reading = frame()
        recorder.save(reading, controller.decide(reading), reading.timestamp, "api")
    batch = recorder.pending()
    assert len(batch) == 2
    recorder.mark_sent([batch[0][0]])
    assert recorder.pending_count() == 1
    assert recorder.pending()[0][0] == batch[1][0]
    recorder.close()


def test_history_downsampling_preserves_endpoints(tmp_path, frame):
    recorder = Recorder(tmp_path / "test.sqlite3", "UTC", 6)
    controller = Controller()
    start = datetime.now(UTC)
    for seconds in range(20):
        reading = frame(timestamp=start + timedelta(seconds=seconds))
        recorder.save(reading, controller.decide(reading), reading.timestamp, "api")
    result = recorder.recent("tank-01", start, limit=5)
    assert len(result) == 5
    assert result[0]["telemetry"]["timestamp"] == start.isoformat().replace("+00:00", "Z")
    assert datetime.fromisoformat(result[-1]["telemetry"]["timestamp"]) == start + timedelta(
        seconds=19
    )
    recorder.close()


def test_reset_does_not_reuse_pending_outbox_ids(tmp_path, frame):
    recorder = Recorder(tmp_path / "test.sqlite3", "UTC", 6)
    controller = Controller()
    first = frame()
    recorder.save(first, controller.decide(first), first.timestamp, "demo")
    old_id = recorder.pending()[0][0]
    recorder.reset(first.device_id)
    second = frame()
    recorder.save(second, controller.decide(second), second.timestamp, "demo")
    recorder.mark_sent([old_id])
    assert recorder.pending_count() == 1
    assert recorder.pending()[0][0] > old_id
    recorder.close()
