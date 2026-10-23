#pragma once

#include <cstdint>

namespace water {

// commandFresh accepts up to this much positive backend/ESP32 clock skew.
// Recovery/session barriers include the same margin so an older delayed
// command cannot appear to have been issued after a stop or reconnect.
constexpr int64_t kCommandClockSkewMs = 2000;

// A closed contact permits transfer. An open contact (including a broken wire)
// stops immediately; permitting transfer again requires a stable closed contact
// and a command issued after that recovery. This class makes no claim about
// actual valve position or which tank carries the switch.
class TransferInterlock {
 public:
  explicit TransferInterlock(uint32_t debounceMs = 500U) : debounceMs_(debounceMs) {}

  void sample(bool permitClosed, uint32_t nowMs, int64_t utcMs) {
    permitClosed_ = permitClosed;
    if (!permitClosed) {
      debouncing_ = false;
      ready_ = false;
      readyAtMs_ = 0;
      readyAtUtcMs_ = 0;
      return;
    }
    if (!debouncing_) {
      debouncing_ = true;
      closedSinceMs_ = nowMs;
    }
    if (!ready_ && static_cast<uint32_t>(nowMs - closedSinceMs_) >= debounceMs_) {
      ready_ = true;
      readyAtMs_ = nowMs;
      readyAtUtcMs_ = utcMs > 0 ? utcMs : 0;
    }
    // A switch can finish debouncing before NTP synchronizes. Establish both
    // freshness boundaries when UTC first becomes available, without restarting
    // the physical debounce or allowing a command received before clock sync.
    if (ready_ && readyAtUtcMs_ <= 0 && utcMs > 0) {
      readyAtMs_ = nowMs;
      readyAtUtcMs_ = utcMs;
    }
  }

  bool ready() const { return ready_; }
  bool permitClosed() const { return permitClosed_; }
  uint32_t readyAtMs() const { return readyAtMs_; }
  int64_t readyAtUtcMs() const { return readyAtUtcMs_; }

  bool commandAllowed(uint32_t receivedMs, int64_t issuedAtMs) const {
    // Commands live for seconds, so a forward difference below half the millis
    // range identifies a strictly newer receipt even across counter rollover.
    const uint32_t elapsed = receivedMs - readyAtMs_;
    return ready_ && readyAtUtcMs_ > 0 && elapsed > 0 && elapsed < 0x80000000UL &&
           issuedAtMs > readyAtUtcMs_ && issuedAtMs - readyAtUtcMs_ > kCommandClockSkewMs;
  }

 private:
  const uint32_t debounceMs_;
  uint32_t closedSinceMs_ = 0;
  uint32_t readyAtMs_ = 0;
  int64_t readyAtUtcMs_ = 0;
  bool debouncing_ = false;
  bool ready_ = false;
  bool permitClosed_ = false;
};

// Recheck at queue consumption: a command accepted by the network task before
// an interlock stop or reconnect must not actuate after the condition clears.
// Expiry, ordering and payload validation are separate command checks.
inline bool actuationCommandAllowed(const TransferInterlock& interlock, bool networkOnline,
                                    uint32_t commandSession, uint32_t currentSession,
                                    int64_t sessionStartedUtcMs, uint32_t receivedMs,
                                    int64_t issuedAtMs) {
  return networkOnline && currentSession != 0 && commandSession == currentSession &&
         sessionStartedUtcMs > 0 && issuedAtMs > sessionStartedUtcMs &&
         issuedAtMs - sessionStartedUtcMs > kCommandClockSkewMs &&
         interlock.commandAllowed(receivedMs, issuedAtMs);
}

}  // namespace water
