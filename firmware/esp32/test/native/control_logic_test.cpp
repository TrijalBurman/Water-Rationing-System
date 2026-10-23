#include "control_logic.h"

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
}  // namespace

int main() {
  testGeometryAndMedian();
  testReserveAndFaultPriority();
  testCommandTimeoutAndDuty();
  testUtcAndReplay();
  std::puts("PASS: geometry, median, reserve priority, fault cap, duty cycle, timeout, rollover, UTC and replay tests");
}
