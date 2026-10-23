#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace water {

constexpr float kReservePercent = 10.0f;
constexpr float kFaultMaximumPercent = 30.0f;
constexpr uint32_t kDutyPeriodMs = 30000U;

inline float clampPercent(float value) {
  return std::isfinite(value) ? std::max(0.0f, std::min(100.0f, value)) : 0.0f;
}

inline bool validDistance(float cm) {
  return std::isfinite(cm) && cm >= 20.0f && cm <= 600.0f;
}

inline float levelFromDistance(float distanceCm, float standoffCm, float heightCm) {
  if (!validDistance(distanceCm) || heightCm <= 0.0f) return 0.0f;
  return clampPercent(100.0f * (heightCm - (distanceCm - standoffCm)) / heightCm);
}

class MedianFive {
 public:
  void reset() { count_ = 0; next_ = 0; }
  bool push(float value, float& median) {
    if (!validDistance(value)) { reset(); return false; }
    values_[next_] = value;
    next_ = (next_ + 1) % 5;
    if (count_ < 5) ++count_;
    if (count_ < 5) return false;
    float sorted[5];
    std::copy(values_, values_ + 5, sorted);
    std::sort(sorted, sorted + 5);
    median = sorted[2];
    return true;
  }
 private:
  float values_[5]{};
  unsigned count_ = 0;
  unsigned next_ = 0;
};

// Local safety is evaluated continuously, independently of the network task.
class ValveController {
 public:
  explicit ValveController(uint32_t timeoutMs = 10000U) : timeoutMs_(timeoutMs) {}

  void sample(float rawDistanceCm, float standoffCm, float heightCm) {
    if (!validDistance(rawDistanceCm)) {
      sensorFault_ = true;
      filter_.reset();
      return;
    }
    // A single credible reading below reserve closes immediately; reopening
    // requires a full median window above reserve and a live command.
    const bool rawBelowReserve = levelFromDistance(rawDistanceCm, standoffCm, heightCm) < kReservePercent;
    if (rawBelowReserve)
      reserveClosed_ = true;
    float median = 0.0f;
    if (!filter_.push(rawDistanceCm, median)) return;
    distanceCm_ = median;
    levelPercent_ = levelFromDistance(median, standoffCm, heightCm);
    hasLevel_ = true;
    sensorFault_ = false;
    reserveClosed_ = rawBelowReserve || levelPercent_ < kReservePercent;
  }

  void command(float percent, uint32_t receivedAtMs, int64_t expiresAtMs) {
    requestedPercent_ = clampPercent(percent);
    receivedAtMs_ = receivedAtMs;
    expiresAtMs_ = expiresAtMs;
    hasCommand_ = true;
  }

  float effectivePercent(uint32_t nowMs, int64_t unixMs) const {
    if (!hasCommand_ || !hasLevel_ || reserveClosed_ || unixMs <= 0 ||
        unixMs >= expiresAtMs_ || static_cast<uint32_t>(nowMs - receivedAtMs_) >= timeoutMs_)
      return 0.0f;
    return sensorFault_ ? std::min(requestedPercent_, kFaultMaximumPercent) : requestedPercent_;
  }

  bool relayOpen(uint32_t nowMs, int64_t unixMs) {
    // Keep the cycle phase stable across every incoming 1Hz command. Modulo
    // elapsed time is also safe across the millis() counter rollover.
    const uint32_t elapsed = nowMs - cycleStartMs_;
    if (elapsed >= kDutyPeriodMs) cycleStartMs_ += (elapsed / kDutyPeriodMs) * kDutyPeriodMs;
    const uint32_t phaseMs = nowMs - cycleStartMs_;
    return phaseMs < static_cast<uint32_t>(kDutyPeriodMs * effectivePercent(nowMs, unixMs) / 100.0f);
  }

  float levelPercent() const { return levelPercent_; }
  float medianDistanceCm() const { return distanceCm_; }
  bool sensorFault() const { return sensorFault_; }
  bool hasLevel() const { return hasLevel_; }

 private:
  MedianFive filter_;
  const uint32_t timeoutMs_;
  float levelPercent_ = 0.0f;
  float distanceCm_ = NAN;
  float requestedPercent_ = 0.0f;
  uint32_t receivedAtMs_ = 0;
  uint32_t cycleStartMs_ = 0;
  int64_t expiresAtMs_ = 0;
  bool hasLevel_ = false;
  bool sensorFault_ = true;
  bool reserveClosed_ = true;
  bool hasCommand_ = false;
};

inline bool leapYear(int year) {
  return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
}

// UTC timestamps only: YYYY-MM-DDTHH:MM:SS[.fraction](Z|+00:00).
// Keeping parsing here makes command freshness validation testable on a PC.
inline int64_t parseUtcMillis(const char* value) {
  if (!value || std::strlen(value) < 20) return 0;
  const auto number = [value](int pos, int count) {
    int out = 0;
    for (int i = 0; i < count; ++i) {
      const char c = value[pos + i];
      if (c < '0' || c > '9') return -1;
      out = out * 10 + c - '0';
    }
    return out;
  };
  int year = number(0, 4), month = number(5, 2), day = number(8, 2);
  const int hour = number(11, 2), minute = number(14, 2), second = number(17, 2);
  if (value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
      value[13] != ':' || value[16] != ':' || year < 2024 || year > 2099 ||
      month < 1 || month > 12 || day < 1 || hour < 0 || hour > 23 ||
      minute < 0 || minute > 59 || second < 0 || second > 59) return 0;
  const int lengths[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  if (day > lengths[month - 1] + (month == 2 && leapYear(year) ? 1 : 0)) return 0;
  int pos = 19, fractionalMs = 0;
  if (value[pos] == '.') {
    ++pos;
    int digits = 0;
    while (value[pos] >= '0' && value[pos] <= '9') {
      if (digits < 3) fractionalMs = fractionalMs * 10 + value[pos] - '0';
      ++digits; ++pos;
      if (digits > 9) return 0;
    }
    if (digits == 0) return 0;
    while (digits++ < 3) fractionalMs *= 10;
  }
  if (std::strcmp(value + pos, "Z") != 0 && std::strcmp(value + pos, "+00:00") != 0) return 0;
  // Gregorian calendar to days since Unix epoch (UTC; no host timezone).
  year -= month <= 2;
  const int era = year / 400;
  const unsigned yoe = static_cast<unsigned>(year - era * 400);
  const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  const int64_t days = static_cast<int64_t>(era) * 146097 + doe - 719468;
  return (((days * 24 + hour) * 60 + minute) * 60 + second) * 1000 + fractionalMs;
}

inline bool commandFresh(int64_t issuedAt, int64_t expiresAt, int64_t now,
                         int64_t sessionStart, int64_t lastIssued,
                         int64_t maxTtlMs = 30000) {
  return now > 0 && issuedAt >= sessionStart && issuedAt > lastIssued &&
         issuedAt <= now + 2000 && expiresAt > now && expiresAt > issuedAt &&
         expiresAt - issuedAt <= maxTtlMs && now - issuedAt < maxTtlMs;
}

}  // namespace water
