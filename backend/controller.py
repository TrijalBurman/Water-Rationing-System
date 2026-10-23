"""Deterministic five-sample forecast with independent branch leak debouncing.

The two meters straddle a delivery branch. Q_in is tank withdrawal into that
branch, not a refill measurement. See docs/architecture.md for model limits.
"""

from collections import deque
from dataclasses import dataclass, field

from .models import Decision, Telemetry


@dataclass
class DeviceState:
    flows: deque = field(default_factory=lambda: deque(maxlen=5))
    leak_cycles: int = 0
    last_timestamp: float | None = None


class Controller:
    def __init__(self, capacity_l: float = 2.5, reset_gap_seconds: float = 6):
        self.capacity_l = capacity_l
        self.reset_gap_seconds = reset_gap_seconds
        self.states: dict[str, DeviceState] = {}

    def reset(self, device_id: str):
        self.states.pop(device_id, None)

    def decide(self, telemetry: Telemetry) -> Decision:
        state = self.states.setdefault(telemetry.device_id, DeviceState())
        timestamp = telemetry.timestamp.timestamp()
        if state.last_timestamp is not None:
            if timestamp <= state.last_timestamp:
                raise ValueError("Telemetry must be strictly newer than the previous reading")
            if timestamp - state.last_timestamp > self.reset_gap_seconds:
                state.flows.clear()
                state.leak_cycles = 0
        state.last_timestamp = timestamp
        state.flows.append(telemetry.flow_lpm)
        predicted = sum(state.flows) / len(state.flows)
        # Conflicting volume and level must never increase the available reserve.
        usable_volume = min(telemetry.volume_l, telemetry.level_percent * self.capacity_l / 100)
        reserve = self.capacity_l * 0.10
        available = max(0, usable_volume - reserve)
        calibration_required = (
            telemetry.hardware_profile == "two_tank_transfer"
            and telemetry.local_stop_reason == "setup_required"
        )
        fault = (
            calibration_required
            or telemetry.sensor_status == "fault"
            or telemetry.ultrasonic_distance_cm is None
            or not 20 <= telemetry.ultrasonic_distance_cm <= 600
        )
        # Placeholder geometry must not turn an uncalibrated zero into a claim
        # that the source is empty. The local commissioning gate still stops it.
        critical = not calibration_required and (
            telemetry.level_percent < 10 or usable_volume < reserve
        )
        eta = available / predicted if predicted > 1e-6 else None
        if fault:
            eta = None

        difference = telemetry.flow_lpm - telemetry.flow_out_lpm
        threshold = max(0.3, 0.15 * telemetry.flow_lpm)
        if difference > threshold + 1e-9:
            state.leak_cycles = min(3, state.leak_cycles + 1)
        else:
            state.leak_cycles = 0
        leak = state.leak_cycles >= 3
        flat_status = (
            "LEAK_ALERT" if leak else ("SUSPECTED_LEAK" if state.leak_cycles else "NORMAL")
        )

        if critical:
            tank_mode, master, priority = "CRITICAL", 0, 100
            reason = (
                "Protected source reserve reached. Transfer is stopped."
                if telemetry.hardware_profile == "two_tank_transfer"
                else "Protected reserve reached. All valves are closed."
            )
        elif fault:
            tank_mode, master, priority = "SENSOR_FAULT", 30, 90
            reason = "Ultrasonic level reading is invalid. Flow is capped at 30%."
        elif telemetry.level_percent < 25 or (eta is not None and eta < 60):
            tank_mode, master, priority = "RATIONING", max(20, telemetry.level_percent), 70
            reason = "Water is rationed to preserve the reserve."
        elif eta is not None and eta < 120:
            tank_mode, master, priority = "WARNING", 100, 40
            reason = "Less than two hours to protected reserve at the recent withdrawal rate."
        else:
            tank_mode, master, priority = "NORMAL", 100, 10
            reason = "Tank supply and branch flow are within operating limits."

        flat = 0 if critical else min(master, 25 if leak else 100)
        mode = tank_mode
        if leak:
            reason += (
                " Sustained branch imbalance: branch duty is limited to 25%."
                if not critical
                else " Branch leak remains detected."
            )
            if tank_mode in ("NORMAL", "WARNING"):
                mode, priority = "LEAK_ALERT", 60
        elif state.leak_cycles:
            reason += f" Branch imbalance observed ({state.leak_cycles}/3 readings); checking persistence."

        if telemetry.hardware_profile == "two_tank_transfer" and not telemetry.transfer_permitted:
            float_stop = (
                "Receiver is full or the float circuit is disconnected."
                if telemetry.float_switch_role == "receiver_full"
                else "Source low-level float requests a stop or its circuit is disconnected."
            )
            local_reason = {
                "setup_required": "Hardware commissioning is incomplete; source tank geometry is uncalibrated. Complete calibration, wiring, and supply checks before enabling transfer.",
                "float_stop": float_stop,
                "float_recovering": "Float circuit is recovering; waiting for a stable permitted state.",
                "clock_unsynced": "The device clock is not synchronized; command expiry cannot yet be verified.",
            }[telemetry.local_stop_reason]
            master = flat = 0
            if critical:
                reason = "Protected source reserve reached. Transfer is stopped. " + local_reason
            else:
                mode, priority = "TRANSFER_STOPPED", 95
                reason = "Transfer is stopped. " + local_reason
            if leak:
                reason += " Sustained pipe flow imbalance remains detected."
            elif state.leak_cycles:
                reason += f" Pipe imbalance observed ({state.leak_cycles}/3 readings); checking persistence."

        return Decision(
            mode=mode,
            tank_mode=tank_mode,
            flat_status=flat_status,
            master_valve_percent=master,
            flat_valve_percent=flat,
            predicted_flow_lpm=round(predicted, 4),
            eta_minutes=round(eta, 3) if eta is not None else None,
            leak_detected=leak,
            leak_rate_lpm=round(max(0, difference), 4),
            leak_threshold_lpm=round(threshold, 4),
            priority=priority,
            reason=reason,
        )
