from collections import defaultdict, deque
from dataclasses import dataclass

from .schemas import Decision, Telemetry
from .settings import Settings


@dataclass
class _DeviceState:
    flows: deque[float]
    prior_mode: str = "NORMAL"
    consecutive_leak_count: int = 0
    last_leak_rate: float = 0.0


class RationingController:
    """Explainable, deterministic control policy with per-device flow history and leak detection."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._states: dict[str, _DeviceState] = defaultdict(
            lambda: _DeviceState(flows=deque(maxlen=5))
        )

    def decide(self, telemetry: Telemetry) -> Decision:
        state = self._states[telemetry.device_id]
        if telemetry.sensor_status != "ok" or not 20 <= telemetry.ultrasonic_distance_cm <= 600:
            return self._decision(
                telemetry, "SENSOR_FAULT", "OK",
                master_valve=min(telemetry.valve_percent, 30),
                flat_valve=min(telemetry.valve_percent, 30),
                predicted_flow=0.0, eta=None, priority="critical",
                reason="Waterproof ultrasonic sensor reading is invalid; hold conservative flow and inspect the probe and wiring.",
            )

        state.flows.append(telemetry.flow_lpm)
        predicted_flow = sum(state.flows) / len(state.flows)
        reserve_l = self.settings.tank_capacity_l * self.settings.min_safe_percent / 100
        usable_l = max(0.0, telemetry.volume_l - reserve_l)
        eta = usable_l / predicted_flow if predicted_flow > 0.05 else None

        # 1. Central Tank Volumetric Mode Evaluation
        if telemetry.level_percent < self.settings.min_safe_percent:
            tank_mode = "CRITICAL"
            master_valve = 0.0
            priority = "critical"
            reason = f"Tank is below the {self.settings.min_safe_percent:.0f}% protected reserve."
        elif eta is not None and eta < self.settings.rationing_eta_minutes:
            tank_mode = "RATIONING"
            target_flow = usable_l / self.settings.rationing_eta_minutes
            master_valve = max(
                self.settings.minimum_rationing_percent,
                min(70.0, 100 * target_flow / max(predicted_flow, 0.05)),
            )
            priority = "high"
            reason = f"Predicted reserve depletion in {eta:.0f} min; limiting demand to protect the reserve."
        elif eta is not None and eta < self.settings.warning_eta_minutes:
            tank_mode = "WARNING"
            master_valve = 100.0
            priority = "medium"
            reason = f"Predicted reserve depletion in {eta:.0f} min; rationing will begin below {self.settings.rationing_eta_minutes:.0f} min."
        else:
            tank_mode = "RECOVERY" if state.prior_mode in {"CRITICAL", "RATIONING", "WARNING"} else "NORMAL"
            master_valve = 100.0
            priority = "low"
            reason = "Tank availability recovered above operating thresholds." if tank_mode == "RECOVERY" else "Level and predicted availability are within normal limits."

        # 2. Per-Flat Dual-Flow Leak Evaluation
        flat_status = "OK"
        leak_detected = False
        leak_rate = 0.0
        if telemetry.flow_out_lpm is not None:
            delta_flow = telemetry.flow_lpm - telemetry.flow_out_lpm
            leak_threshold = max(
                self.settings.leak_diff_threshold_lpm,
                self.settings.leak_ratio_threshold * telemetry.flow_lpm,
            )
            if delta_flow > leak_threshold and telemetry.flow_lpm > 0.1:
                state.consecutive_leak_count += 1
                leak_rate = max(0.0, round(delta_flow, 3))
                state.last_leak_rate = leak_rate
                if state.consecutive_leak_count >= self.settings.leak_confirm_samples:
                    flat_status = "LEAK_ALERT"
                    leak_detected = True
                else:
                    flat_status = "SUSPECTED_LEAK"
            else:
                state.consecutive_leak_count = 0
                state.last_leak_rate = 0.0
                flat_status = "OK"

        # 3. Branch Actuation Resolution
        if tank_mode == "CRITICAL":
            flat_valve = 0.0
        elif flat_status == "LEAK_ALERT":
            flat_valve = min(master_valve, self.settings.leak_throttle_percent)
            if priority in ("low", "medium"):
                priority = "high"
            reason = (
                f"Branch leak on {telemetry.flat_id}: delta {state.last_leak_rate:.2f} L/min "
                f"for {state.consecutive_leak_count} consecutive readings. Throttling {telemetry.flat_id} valve to {flat_valve:.0f}%. "
                + reason
            )
        else:
            flat_valve = master_valve

        return self._decision(
            telemetry=telemetry,
            tank_mode=tank_mode,
            flat_status=flat_status,
            master_valve=master_valve,
            flat_valve=flat_valve,
            predicted_flow=predicted_flow,
            eta=eta,
            priority=priority,
            reason=reason,
            leak_detected=leak_detected,
            leak_rate_lpm=state.last_leak_rate,
        )

    def _decision(self, telemetry: Telemetry, tank_mode: str, flat_status: str,
                  master_valve: float, flat_valve: float, predicted_flow: float,
                  eta: float | None, priority: str, reason: str,
                  leak_detected: bool = False, leak_rate_lpm: float = 0.0) -> Decision:
        self._states[telemetry.device_id].prior_mode = tank_mode
        return Decision(
            device_id=telemetry.device_id,
            flat_id=telemetry.flat_id,
            timestamp=telemetry.timestamp,
            mode=tank_mode,
            tank_mode=tank_mode,
            flat_status=flat_status,
            valve_percent=round(flat_valve, 1),
            master_valve_percent=round(master_valve, 1),
            flat_valve_percent=round(flat_valve, 1),
            predicted_flow_lpm=round(predicted_flow, 3),
            eta_minutes=round(eta, 1) if eta is not None else None,
            leak_detected=leak_detected,
            leak_rate_lpm=round(leak_rate_lpm, 3),
            priority=priority,
            reason=reason,
        )
