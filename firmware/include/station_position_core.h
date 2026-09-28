#pragma once
#include <cmath>
#include <cstdint>

// A fitted normal-orientation model, separate from the existing edge MLP.
// Change demo tolerances here; re-run MPUCAL after changing them.
namespace StationPosition {
constexpr unsigned CalibrationSamples = 30;
constexpr float MinimumToleranceDeg = 10.0f;
constexpr float MaximumToleranceDeg = 15.0f;
constexpr float FallenThresholdDeg = 35.0f;
constexpr uint32_t ConfirmationMs = 3000;
constexpr uint32_t RecoveryMs = 5000;
constexpr uint32_t MaximumSampleGapMs = 2500;
constexpr float RadToDeg = 57.2957795131f;

struct Model {
  uint32_t version = 1;
  float unit[3] = {0, 0, 1};
  float toleranceDeg = MinimumToleranceDeg;
  float noiseDeg = 0;
};

struct Report {
  bool calibrated = false, calibrating = false, sampleValid = false;
  bool measurementValid = false, active = false, critical = false;
  bool modelChanged = false;
  unsigned samples = 0;
  float tiltDeg = NAN, toleranceDeg = MinimumToleranceDeg;
  const char* state = "UNCALIBRATED";
};

class Monitor {
 public:
  Model model;
  Report report;

  bool restore(const Model& saved) {
    const float norm = magnitude(saved.unit);
    if (saved.version != 1 || !std::isfinite(norm) || std::fabs(norm-1.0f) > 0.01f ||
        !std::isfinite(saved.toleranceDeg) || saved.toleranceDeg < MinimumToleranceDeg ||
        saved.toleranceDeg > MaximumToleranceDeg || !std::isfinite(saved.noiseDeg) ||
        saved.noiseDeg < 0 || saved.noiseDeg > 2.0f) return false;
    model = saved; report.calibrated = true; report.toleranceDeg = model.toleranceDeg;
    report.state = "WAITING_FOR_MPU";
    return true;
  }

  void calibrate(uint32_t now) {
    report.calibrating = true; report.samples = 0; calibrationStarted = now;
    // Keep the previous model and alarms until a replacement is accepted.
  }

  void update(uint32_t now, bool configured, bool valid,
              float ax, float ay, float az, float gx, float gy, float gz) {
    report.modelChanged = false;
    report.tiltDeg = NAN;
    report.sampleValid = report.measurementValid = false;
    if (haveTime && now == lastTime) return; // Never count one sample twice.
    if (haveTime && uint32_t(now-lastTime) > MaximumSampleGapMs) {
      resetTimers(); report.samples = 0;
    }
    haveTime = true; lastTime = now;
    if (report.calibrating && uint32_t(now-calibrationStarted) > 90000) {
      report.calibrating = false; report.samples = 0;
    }
    if (!configured) { resetTimers(); report.samples = 0; report.state = "DISABLED"; return; }
    const float a[3] = {ax,ay,az}, g[3] = {gx,gy,gz};
    const float norm = magnitude(a), gyro = magnitude(g);
    valid = valid && std::isfinite(norm) && std::isfinite(gyro) && norm > 0.01f;
    report.sampleValid = valid;
    if (!valid) { resetTimers(); report.samples = 0; report.state = "MPU_INVALID"; return; }
    // Gravity-based tilt is only trustworthy after motion has settled.
    const bool settled = norm >= 8.6f && norm <= 11.0f && gyro <= 0.25f;
    if (!settled) { resetTimers(); report.samples = 0; report.state = "MOVING"; return; }
    const float unit[3] = {ax/norm, ay/norm, az/norm};
    if (report.calibrating) {
      if (gyro > 0.12f || norm < 9.0f || norm > 10.6f) report.samples = 0;
      else {
        if (report.samples && angle(unit, samples[0]) > 3.0f) report.samples = 0;
        for (int k=0;k<3;++k) samples[report.samples][k] = unit[k];
        if (++report.samples == CalibrationSamples) fit();
      }
    }
    if (!report.calibrated) {
      report.state = report.calibrating ? "CALIBRATING" : "UNCALIBRATED";
      return;
    }
    report.measurementValid = true;
    report.tiltDeg = angle(unit, model.unit);
    const bool tilted = report.tiltDeg >= model.toleranceDeg;
    const bool fallen = report.tiltDeg >= FallenThresholdDeg;
    if (held(tiltTimer, now, tilted, ConfirmationMs)) report.active = true;
    if (held(fallTimer, now, fallen, ConfirmationMs)) {
      report.active = true; report.critical = true;
    }
    const bool returned = report.tiltDeg <= model.toleranceDeg*0.6f;
    if (held(returnTimer, now, returned, RecoveryMs)) {
      report.active = false; report.critical = false;
    }
    report.state = report.critical ? "FALLEN_OR_TILTED" : report.active ? "OUT_OF_POSITION" :
                   tilted ? "TILT_PENDING" : report.calibrating ? "CALIBRATING" : "IN_POSITION";
  }

 private:
  struct Timer { bool running = false; uint32_t started = 0; };
  Timer tiltTimer, fallTimer, returnTimer;
  uint32_t lastTime = 0, calibrationStarted = 0;
  bool haveTime = false;
  float samples[CalibrationSamples][3]{};

  static float magnitude(const float* v) {
    return std::sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);
  }
  static float angle(const float* a, const float* b) {
    float dot = a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
    if (dot > 1) dot = 1;
    if (dot < -1) dot = -1;
    return std::acos(dot)*RadToDeg;
  }
  static bool held(Timer& timer, uint32_t now, bool condition, uint32_t duration) {
    if (!condition) { timer.running = false; return false; }
    if (!timer.running) { timer.running = true; timer.started = now; }
    return uint32_t(now-timer.started) >= duration;
  }
  void resetTimers() { tiltTimer = Timer{}; fallTimer = Timer{}; returnTimer = Timer{}; }
  void fit() {
    Model candidate;
    float mean[3]{};
    for (unsigned i=0;i<CalibrationSamples;++i)
      for (int k=0;k<3;++k) mean[k] += samples[i][k]/CalibrationSamples;
    const float norm = magnitude(mean);
    if (!std::isfinite(norm) || norm < 0.99f) { report.samples = 0; return; }
    for (int k=0;k<3;++k) candidate.unit[k] = mean[k]/norm;
    float errors[CalibrationSamples]{}, average = 0, variance = 0;
    for (unsigned i=0;i<CalibrationSamples;++i) {
      errors[i] = angle(samples[i], candidate.unit);
      average += errors[i]/CalibrationSamples;
    }
    for (float error : errors) variance += (error-average)*(error-average)/(CalibrationSamples-1);
    candidate.noiseDeg = std::sqrt(variance);
    const float learnedTolerance = average+6.0f*candidate.noiseDeg;
    if (candidate.noiseDeg > 2 || learnedTolerance > MaximumToleranceDeg) { report.samples = 0; return; }
    candidate.toleranceDeg = learnedTolerance > MinimumToleranceDeg ? learnedTolerance : MinimumToleranceDeg;
    model = candidate; report.calibrated = true; report.calibrating = false;
    report.modelChanged = true; report.toleranceDeg = model.toleranceDeg;
    report.active = report.critical = false; resetTimers();
  }
};
} // namespace StationPosition
