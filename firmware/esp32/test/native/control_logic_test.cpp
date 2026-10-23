#include "control_logic.h"
#include "tank_interlock.h"

#include <cassert>
#include <cstdio>
#include <limits>

namespace {
constexpr int64_t kNow = 1790460000000LL;

void fill(water::ValveController& valve, float cm = 100.0f) {
  for (int i = 0; i < 5; ++i) valve.sample(cm, 25.0f, 150.0f);
}

void testGeometryAndMedian() {
  assert(water::levelFromDistance(25, 25, 150) == 100);
  assert(water::levelFromDistance(100, 25, 150) == 50);
  assert(water::levelFromDistance(175, 25, 150) == 0);
  assert(water::levelFromDistance(600, 25, 150) == 0);
  assert(!water::validDistance(NAN));
  assert(!water::validDistance(19.99f));
  assert(!water::validDistance(600.01f));
  water::MedianFive median;
  float result = 0;
  assert(!median.push(100, result));
  assert(!median.push(600, result));
  assert(!median.push(99, result));
  assert(!median.push(101, result));
  assert(median.push(100, result) && result == 100);
  assert(!median.push(NAN, result));
  assert(!median.push(100, result));  // A fault requires a new full window.
}

void testReserveAndFaultPriority() {
  water::ValveController valve;
  valve.command(100, 1000, kNow + 10000);
  assert(valve.effectivePercent(1000, kNow) == 0);  // Boot is closed.
  fill(valve);
  assert(valve.effectivePercent(1000, kNow) == 100);
  valve.sample(163, 25, 150);  // One raw 8% reading immediately overrides median.
  assert(valve.effectivePercent(1001, kNow + 1) == 0);
  valve.sample(NAN, 25, 150);
  assert(valve.sensorFault());
  assert(valve.effectivePercent(1002, kNow + 2) == 0);  // Fault cannot reopen reserve.
  fill(valve);
  assert(valve.effectivePercent(1100, kNow + 100) == 100);
  valve.sample(NAN, 25, 150);
  assert(valve.effectivePercent(1101, kNow + 101) == 30);
  valve.command(25, 1102, kNow + 10000);
  assert(valve.effectivePercent(1102, kNow + 102) == 25);  // Cap, never force open.
  valve.command(0, 1103, kNow + 10000);
  assert(valve.effectivePercent(1103, kNow + 103) == 0);
  fill(valve, 160);  // Exactly 10% is not below reserve.
  valve.command(100, 1200, kNow + 10000);
  assert(valve.effectivePercent(1200, kNow + 200) == 100);
}

void testCommandTimeoutAndDuty() {
  water::ValveController valve;
  fill(valve);
  valve.command(50, 1000, kNow + 30000);
  assert(valve.relayOpen(1000, kNow));
  assert(!valve.relayOpen(15000, kNow + 14000));  // Also locally expired.
  for (uint32_t now = 1000; now < 30000; now += 1000) {
    valve.command(50, now, kNow + 60000);
    assert(valve.relayOpen(now, kNow + now) == (now < 15000));
  }
  valve.command(50, 30000, kNow + 60000);
  assert(valve.relayOpen(30000, kNow + 30000));
  assert(valve.effectivePercent(31000, kNow + 60000) == 0);  // Server expiry.
  assert(valve.effectivePercent(40000, kNow + 40000) == 0);  // Local timeout.
  assert(valve.effectivePercent(30001, 0) == 0);  // Missing UTC.

  water::ValveController rollover;
  fill(rollover);
  rollover.command(100, UINT32_MAX - 5000U, kNow + 30000);
  assert(rollover.relayOpen(UINT32_MAX - 1000U, kNow));
  assert(rollover.relayOpen(1000U, kNow + 2000));
  assert(rollover.effectivePercent(5000U, kNow + 6000) == 0);
}

void testUtcAndReplay() {
  const int64_t start = water::parseUtcMillis("2026-09-26T00:00:00Z");
  assert(start == 1790380800000LL);
  assert(water::parseUtcMillis("2026-09-26T00:00:00.123456+00:00") == start + 123);
  assert(water::parseUtcMillis("2026-09-26T00:00:00.1Z") == start + 100);
  assert(water::parseUtcMillis("2026-09-26T00:00:00") == 0);
  assert(water::parseUtcMillis("2026-09-26T00:00:00+05:30") == 0);
  assert(water::parseUtcMillis("2026-02-29T00:00:00Z") == 0);
  assert(water::parseUtcMillis("2024-02-29T00:00:00Z") > 0);
  assert(water::parseUtcMillis("2026-13-01T00:00:00Z") == 0);
  assert(water::parseUtcMillis("2026-09-26T24:00:00Z") == 0);
  assert(water::parseUtcMillis("2026-09-26T00:00:00.Z") == 0);
  assert(water::parseUtcMillis(nullptr) == 0);
  assert(water::commandFresh(start + 1, start + 10000, start + 100, start, 0));
  assert(!water::commandFresh(start - 1, start + 10000, start + 100, start, 0)); // Retained from old session.
  assert(!water::commandFresh(start, start + 10000, start + 100, start, start)); // Replay.
  assert(!water::commandFresh(start, start + 100, start + 100, start, 0)); // Expired.
  assert(!water::commandFresh(start, start + 31000, start + 100, start, 0)); // TTL too long.
  assert(!water::commandFresh(start + 3000, start + 10000, start, start, 0)); // Future-dated.
}

void testTransferInterlockBootAndRecovery() {
  water::TransferInterlock interlock;
  assert(!interlock.ready());
  assert(!interlock.permitClosed());
  assert(!interlock.commandAllowed(1, kNow));
  interlock.sample(false, 0, kNow);
  interlock.sample(true, 100, kNow + 100);
  assert(interlock.permitClosed());
  interlock.sample(true, 599, kNow + 599);
  assert(!interlock.ready());
  interlock.sample(true, 600, kNow + 600);
  assert(interlock.ready());
  assert(interlock.readyAtMs() == 600);
  assert(interlock.readyAtUtcMs() == kNow + 600);
  assert(!interlock.commandAllowed(600, kNow + 2601)); // Same-ms receipt is not fresh.
  assert(!interlock.commandAllowed(2601, kNow + 2600)); // Strictly beyond the 2s margin.
  assert(!interlock.commandAllowed(599, kNow + 2601)); // Previously queued receipt.
  assert(interlock.commandAllowed(2601, kNow + 2601));

  interlock.sample(false, 2602, kNow + 2602); // Open or disconnected closes immediately.
  assert(!interlock.ready());
  assert(!interlock.permitClosed());
  assert(!interlock.commandAllowed(2603, kNow + 2603));
  interlock.sample(true, 2700, kNow + 2700);
  interlock.sample(true, 3199, kNow + 3199);
  assert(!interlock.ready());
  interlock.sample(true, 3200, kNow + 3200);
  assert(interlock.ready());
  assert(!interlock.commandAllowed(3201, kNow + 2601)); // Delayed pre-stop command.
  assert(!interlock.commandAllowed(2601, kNow + 5201)); // Even with a future issue time.
  assert(interlock.commandAllowed(5201, kNow + 5201));
}

void testTransferInterlockBounceAndClockSync() {
  water::TransferInterlock interlock;
  interlock.sample(true, 0, 0);
  interlock.sample(true, 499, 0);
  interlock.sample(false, 499, 0);
  interlock.sample(true, 500, 0);
  interlock.sample(true, 999, 0);
  assert(!interlock.ready()); // A contact bounce restarts the full debounce.
  interlock.sample(true, 1000, 0);
  assert(interlock.ready()); // Physical readiness does not imply valid UTC.
  assert(!interlock.commandAllowed(1001, kNow));
  interlock.sample(true, 1100, kNow);
  assert(interlock.readyAtMs() == 1100);
  assert(interlock.readyAtUtcMs() == kNow);
  assert(!interlock.commandAllowed(1001, kNow + 2001)); // Received before first clock sync.
  assert(!interlock.commandAllowed(1101, kNow));
  assert(!interlock.commandAllowed(3100, kNow + 2000));
  assert(interlock.commandAllowed(3101, kNow + 2001));
  interlock.sample(true, 1200, kNow + 100);
  assert(interlock.readyAtUtcMs() == kNow); // Continuous sampling preserves the boundary.
  assert(interlock.commandAllowed(3101, kNow + 2001));
}

void testTransferInterlockRolloverAndSessionGate() {
  water::TransferInterlock rollover;
  rollover.sample(true, UINT32_MAX - 600U, kNow);
  rollover.sample(true, UINT32_MAX - 101U, kNow + 499);
  assert(!rollover.ready());
  rollover.sample(true, UINT32_MAX - 100U, kNow + 500);
  assert(rollover.ready());
  assert(rollover.commandAllowed(2010U, kNow + 2611)); // Fresh receipt across rollover.
  assert(!rollover.commandAllowed(UINT32_MAX - 101U, kNow + 2611));
  rollover.sample(false, 2020U, kNow + 2621);
  assert(!rollover.ready());
  water::TransferInterlock debounceRollover;
  debounceRollover.sample(true, UINT32_MAX - 100U, kNow + 1000);
  debounceRollover.sample(true, 398U, kNow + 1499);
  assert(!debounceRollover.ready());
  debounceRollover.sample(true, 399U, kNow + 1500);
  assert(debounceRollover.ready()); // The debounce timer itself also survives rollover.

  water::TransferInterlock interlock;
  interlock.sample(true, 100, kNow + 100);
  interlock.sample(true, 600, kNow + 600);
  assert(water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 500, 2701, kNow + 2701));
  assert(!water::actuationCommandAllowed(interlock, false, 2, 2, kNow + 500, 2701, kNow + 2701));
  assert(!water::actuationCommandAllowed(interlock, true, 1, 2, kNow + 500, 2701, kNow + 2701));
  assert(!water::actuationCommandAllowed(interlock, true, 0, 0, kNow + 500, 2701, kNow + 2701));
  assert(!water::actuationCommandAllowed(interlock, true, 2, 2, 0, 2701, kNow + 2701));
  assert(!water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 2701, 2701, kNow + 2701));
  assert(!water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 701, 2701, kNow + 2701));
  assert(!water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 500, 2701, kNow + 599));
  interlock.sample(false, 2702, kNow + 2702);
  assert(!water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 500, 2703, kNow + 2703));
}

void testSmallSourceTankGeometryAndReserve() {
  // The source has an approximately 20cm usable depth, with the AJ-SR04M
  // mounted 30cm above full water: full=30cm, empty=50cm, reserve=48cm.
  assert(water::levelFromDistance(30, 30, 20) == 100);
  assert(water::levelFromDistance(40, 30, 20) == 50);
  assert(water::levelFromDistance(50, 30, 20) == 0);
  assert(water::levelFromDistance(48, 30, 20) == 10);
  assert(water::levelFromDistance(48.01f, 30, 20) < water::kReservePercent);
  assert(std::fabs(water::levelFromDistance(48, 30, 20) * 2.5f / 100 - 0.25f) < 1e-6f);

  water::ValveController valve;
  for (int i = 0; i < 5; ++i) valve.sample(30, 30, 20);
  valve.command(100, 1000, kNow + 10000);
  assert(valve.levelPercent() == 100);
  assert(valve.effectivePercent(1000, kNow) == 100);
  valve.sample(48.01f, 30, 20); // One below-reserve reading overrides a full-tank median.
  assert(valve.effectivePercent(1001, kNow + 1) == 0);
  valve.sample(NAN, 30, 20);
  assert(valve.effectivePercent(1002, kNow + 2) == 0); // Fault cap cannot undo reserve stop.
  for (int i = 0; i < 5; ++i) valve.sample(48, 30, 20);
  assert(valve.levelPercent() == 10);
  assert(valve.effectivePercent(1100, kNow + 100) == 100); // Exact reserve boundary is allowed.
  for (int i = 0; i < 5; ++i) valve.sample(50, 30, 20);
  assert(valve.levelPercent() == 0);
  assert(valve.effectivePercent(1200, kNow + 200) == 0);
}

void testSingleTransferValveHonorsBothLimits() {
  water::ValveController valve;
  for (int i = 0; i < 5; ++i) valve.sample(40, 30, 20);
  valve.command(water::transferPercent(100, 25), 1000, kNow + 10000);
  assert(valve.requestedPercent() == 25); // A leak limit reaches the only installed valve.
  assert(valve.effectivePercent(1000, kNow) == 25);
  valve.command(water::transferPercent(20, 100), 1001, kNow + 10000);
  assert(valve.effectivePercent(1001, kNow + 1) == 20); // Source rationing also reaches it.
  valve.command(water::transferPercent(0, 100), 1002, kNow + 10000);
  assert(valve.effectivePercent(1002, kNow + 2) == 0);
  valve.command(water::transferPercent(100, 0), 1003, kNow + 10000);
  assert(valve.effectivePercent(1003, kNow + 3) == 0);
  assert(water::transferPercent(NAN, 100) == 0);
  assert(water::transferPercent(100, std::numeric_limits<float>::infinity()) == 0);
  assert(water::transferPercent(-1, 100) == 0);
  assert(water::transferPercent(120, 100) == 100);
}

void testInvalidatedTransferRequiresNewCommand() {
  water::ValveController valve;
  water::TransferInterlock interlock;
  for (int i = 0; i < 5; ++i) valve.sample(40, 30, 20);
  interlock.sample(true, 0, kNow);
  interlock.sample(true, 500, kNow + 500);
  assert(water::actuationCommandAllowed(interlock, true, 1, 1, kNow, 2501, kNow + 2501));
  valve.command(100, 2501, kNow + 10000);
  assert(valve.relayOpen(2501, kNow + 2501));

  interlock.sample(false, 2502, kNow + 2502);
  valve.invalidateCommand(); // The local loop performs this on float stop or disconnect.
  assert(valve.requestedPercent() == 0);
  assert(valve.effectivePercent(2502, kNow + 2502) == 0);
  assert(!valve.relayOpen(2502, kNow + 2502));
  valve.invalidateCommand(); // Repeated stopped loops remain harmless.
  interlock.sample(true, 2600, kNow + 2600);
  interlock.sample(true, 3100, kNow + 3100);
  assert(interlock.ready());
  for (int i = 0; i < 5; ++i) valve.sample(30, 30, 20);
  assert(valve.effectivePercent(3101, kNow + 3101) == 0); // Recovery alone cannot reopen.
  assert(valve.requestedPercent() == 0);
  assert(!water::actuationCommandAllowed(interlock, true, 1, 1, kNow, 5101, kNow + 2501));
  assert(!water::actuationCommandAllowed(interlock, true, 1, 2, kNow + 3000, 5101, kNow + 5101));
  assert(!valve.relayOpen(5101, kNow + 5101)); // Neither delayed nor old-session command is applied.
  assert(water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 3000, 5102, kNow + 5102));
  valve.command(water::transferPercent(100, 25), 5102, kNow + 10000);
  assert(valve.requestedPercent() == 25);
  assert(valve.effectivePercent(5102, kNow + 5102) == 25);
  assert(valve.relayOpen(5102, kNow + 5102)); // A genuinely new permitted command can reopen.
}

void testRecoveryBarrierIncludesClockSkew() {
  water::TransferInterlock interlock;
  interlock.sample(true, 0, kNow);
  interlock.sample(true, 500, kNow + 500);
  interlock.sample(false, 3000, kNow + 3000);
  interlock.sample(true, 3100, kNow + 3100);
  interlock.sample(true, 3600, kNow + 3600);
  assert(interlock.ready());
  // Sent at ESP time 2999, just before the stop, with the backend clock 1.5s
  // ahead; delivered after the full 500ms physical recovery. Its timestamp is
  // numerically after recovery and still passes the ordinary freshness check.
  const int64_t delayedIssued = kNow + 2999 + 1500;
  assert(delayedIssued > interlock.readyAtUtcMs());
  assert(water::commandFresh(delayedIssued, kNow + 12000, kNow + 3601, kNow, 0));
  assert(!interlock.commandAllowed(3601, delayedIssued));
  assert(!water::actuationCommandAllowed(interlock, true, 1, 1, kNow, 3601, delayedIssued));
  assert(!interlock.commandAllowed(5600, kNow + 5600)); // Margin is strictly exceeded.
  assert(water::actuationCommandAllowed(interlock, true, 1, 1, kNow, 5601, kNow + 5601));

  // The same ambiguity exists across a reconnect even if the float has been
  // ready throughout. The new session's barrier independently includes skew.
  assert(!water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 6000, 6501, kNow + 7499));
  assert(!water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 6000, 8000, kNow + 8000));
  assert(water::actuationCommandAllowed(interlock, true, 2, 2, kNow + 6000, 8001, kNow + 8001));
}

void testReserveTripDiscardsPreTripMedian() {
  water::ValveController valve;
  for (int i = 0; i < 5; ++i) valve.sample(30, 30, 20);
  valve.command(100, 1000, kNow + 10000);
  assert(valve.effectivePercent(1000, kNow) == 100);
  valve.sample(48.01f, 30, 20);
  assert(valve.effectivePercent(1001, kNow + 1) == 0);
  for (int i = 0; i < 3; ++i) {
    valve.sample(30, 30, 20);
    assert(valve.effectivePercent(1002 + i, kNow + 2 + i) == 0);
  }
  valve.sample(30, 30, 20); // Five fresh post-trip samples now form a safe median.
  assert(valve.effectivePercent(1005, kNow + 5) == 100);

  for (int i = 0; i < 5; ++i) valve.sample(50, 30, 20);
  assert(!valve.sensorFault());
  assert(valve.levelPercent() == 0); // Steady low readings update; no repeated filter reset.
  assert(valve.effectivePercent(1010, kNow + 10) == 0);
}
}  // namespace

int main() {
  testGeometryAndMedian();
  testReserveAndFaultPriority();
  testCommandTimeoutAndDuty();
  testUtcAndReplay();
  testTransferInterlockBootAndRecovery();
  testTransferInterlockBounceAndClockSync();
  testTransferInterlockRolloverAndSessionGate();
  testSmallSourceTankGeometryAndReserve();
  testSingleTransferValveHonorsBothLimits();
  testInvalidatedTransferRequiresNewCommand();
  testRecoveryBarrierIncludesClockSkew();
  testReserveTripDiscardsPreTripMedian();
  std::puts("PASS: geometry, small-tank reserve, fresh median, fault cap, transfer limits, duty, timeout, rollover, UTC, replay, float interlock, clock skew, session gate and command invalidation tests");
}
