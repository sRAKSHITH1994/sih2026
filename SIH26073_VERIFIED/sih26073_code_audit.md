# SIH26073 — Code and Dashboard Audit

Reviewed 26 September 2026. Inputs: `SIH26073_FINAL_LOGOB_pro.zip`, `SIH26073_MPU_POSITION_ADDITION(1).zip`, and seven dashboard screenshots.

**Assessment:** The project contains substantive firmware, trained-model artifacts, a NumPy LSTM implementation, spatial verification, storage and a working API. Its main weaknesses are misleading readiness states, incomplete validation of the complete detection path, inconsistent timing, and several reproducible decision/data-handling bugs. These should be corrected before adding more features or making field-performance claims.

This was a read-only review of the submitted project. Tests used separate temporary databases. No project fixes were applied. The three YouTube videos could not be accessed, so this report makes no claims about their implementations.

Evidence labels below distinguish **reproduced** behavior from **source-confirmed** behavior and **validation gaps**. File locations are relative to `SIH26073_FINAL_SYSTEM`.

## 1. Urgent: the frontend fallback can serve files outside its directory

**Reproduced.** `backend/app/main.py:193` joins a request-controlled path to `frontend/dist` and returns any matching file, without checking that its resolved path remains within that directory. An encoded parent-directory request returned the project's harmless `VERSION.txt` with HTTP 200 and an exact byte match. This request required no authentication. Credential files were not requested during this test.

The firmware configuration in the submitted archive contains non-placeholder Wi-Fi credential settings. A reachable server using this fallback therefore creates a concrete information-exposure risk.

**Repair:** resolve the requested path, require that it is inside the allowed static directory, and serve only intended public assets. Keep credentials outside public file-serving roots. Share a sanitized project copy; replace any credentials that have been exposed to unintended recipients.

## 2. “Normal, 97% confidence” can mean the model is not ready

**Reproduced.** In `backend/app/global_brain.py:168`, every non-alert result receives `confidence=.97`. Readiness is not a prerequisite.

| Probe | Actual result |
|---|---|
| First packet; Local Brain and LSTM both warming up | NORMAL, confidence 0.97 |
| Both model files unavailable | NORMAL, confidence 0.97 |
| Sensor claims attached/valid but contains no values | NORMAL, confidence 0.97; no active features |
| Pressure 1200 hPa, marked valid, first packet, no local alert | NORMAL even though the physical-consistency check says false |

`global_brain.py:118` excludes physical-consistency failure from the alert condition. `backend/app/schemas.py` requires a nonempty sensor dictionary but does not enforce the expected numeric values for each sensor that claims validity.

**Repair:** use explicit NO_DATA, WARMING_UP, MODEL_UNAVAILABLE and DEGRADED_EVIDENCE states. Validate required values and finite numbers at ingestion. Make physical invalidity actionable. Define confidence from available evidence; do not present a fixed fallback as a calibrated probability.

## 3. The simulator does not run the trained edge MLP

**Source-confirmed.** `backend/app/simulator.py:54` onward directly assigns fault labels, severity, confidence, risk, EWMA/CUSUM values, MLP class and MLP probability based on the chosen scenario and sample index. No edge model is evaluated there.

The simulator does pass its generated packet through the actual Global Brain and storage. Thus it is useful for dashboard and downstream integration testing. Its displayed Local Brain ML result does not demonstrate ESP32 inference.

**Repair:** distinguish “simulated local report” from “measured edge inference.” For a genuine software replica, run the same feature pipeline and exported model on injected raw streams, then verify parity with firmware output. Do not mix scenario ground truth into detector inputs.

## 4. The 97.4% benchmark does not validate the complete Local + Global system

**Reproduced and source-confirmed.** The default benchmark exactly reproduced 315 TP, 388 TN, 0 FP and 17 FN.

| Metric | Reproduced value |
|---|---:|
| Evaluated target samples | 720 |
| Accuracy | 97.6389% |
| Balanced accuracy | 97.4398% |
| Anomaly recall | 94.8795% |
| Anomaly F1 | 97.3725% |

The 17 misses are **6 drift-onset samples, 7 frozen-onset samples and 4 genuine-weather-onset samples**. All events were eventually detected, which explains the green scenario ticks. This is distinct from detecting every affected sample.

Important boundaries in `backend/app/evaluation.py`:

- `LocalRuleMirror` is a simplified Python rule implementation. The trained edge MLP and actual firmware feature/fusion path do not participate.
- At line 115, electrical, mechanical and station-power-failure scenarios inject the local anomaly answer, fault type and confidence directly. Their zero-sample delays cannot validate local fault detection or predictive warning.
- The spike is injected at one instant, but ground truth remains positive for 20 samples. State this window-based convention and also report event and pointwise results.
- `explanation_coverage=1.0` at line 161 is assigned, not measured.
- The normal scenario's `detected` flag is always true. It does not require its false-positive count to be zero.
- Throughput is calculated from mean target processing time. It excludes complete HTTP, storage, queueing and dashboard delay, so it is not an end-to-end load-test result.

**Repair:** retain this as a labelled integration benchmark; add raw-input detector evaluation, firmware replay, per-class results, rules/ML/LSTM/spatial ablations, multiple seeds and genuinely separate physical trials. Calculate explanation coverage and pass/fail criteria from actual outcomes.

## 5. LSTM training cadence differs from the live input cadence

**Source/data-confirmed.** The supplied train, validation and test CSV timestamps are one minute apart. `scripts/train_lstm.py` builds 20-row windows from their values. Firmware samples every 1000 ms and normally sends every 2000 ms; anomaly telemetry is requested at 750 ms but is produced from the roughly one-second sampling loop.

A 20-row training window spans 19 minutes between its first and last observations. A live 20-packet window ordinarily spans roughly 19–38 seconds, with further variation during recovery and backlog delivery. `GlobalBrainEngine._temporal` uses arrival order and ignores elapsed time.

There is another continuity problem: training removes anomaly rows before building windows, then joins the remaining observations as if they were consecutive. The normal-only training stream has **86 gaps over 60 seconds**, with a maximum gap of **1920 seconds**. Validation has 18 such gaps and test has 18. Sequence windows are not prevented from crossing them.

**Repair:** choose and document an intended temporal cadence. Resample/retrain accordingly, reject or mask missing intervals, and build windows only within continuous station sessions. Keep sample timestamps separate from delivery timestamps.

## 6. Hardware anomalies can be labelled as genuine weather

**Reproduced.** Three nearby packets with unchanged atmospheric values and local `MECHANICAL` alerts caused the third station to be classified `GENUINE_WEATHER_EVENT`.

`backend/app/spatial.py` stores only a generic anomaly boolean as neighbour support. The weather branch at `backend/app/global_brain.py:148` accepts any alert with corroboration and physically plausible weather values. It does not require matching atmospheric changes or exclude electrical/mechanical/degradation faults. The MPU position addition correctly adds a special exclusion for station-position alarms, but that exclusion is not generalized to other physical faults.

Also, `haversine_km` returns zero when any coordinate is missing. Two neighbours with unknown coordinates were accepted as zero kilometres away and could corroborate an event. With two candidates, one alarming neighbour meets the current 50% support threshold.

**Repair:** preserve independent equipment-fault and weather-event outputs. Spatial weather evidence should require relevant parameter changes, time alignment, trustworthy locations and enough independent supporting stations. Unknown location must not mean zero distance.

## 7. Adding humidity temporarily disables an already-ready T/P model

**Reproduced.** After 20 valid T/P samples, the TP model was ready. Adding one humidity sample immediately selected TPH and returned `TPH temporal warm-up 1/20` with `ready=false`.

At `backend/app/global_brain.py:73`, selection depends on the presence of humidity and a TPH model, not on completion of the TPH window. This contradicts the README's promise that TP remains active until 20 valid humidity samples are available.

**Repair:** continue TP inference while filling the TPH window; switch only when TPH is ready. Handle intermittent humidity without repeatedly losing temporal coverage.

## 8. Missing values can appear as real zero readings

**Reproduced.** `frontend/src/App.jsx:17` formats values through `Number(value)`. JavaScript converts `null` to zero, so the current formatter displays `null` as `0.0`. A null LSTM loss can similarly appear as `0.0000` during warm-up.

Chart inputs are also converted with `Number(...)` before filtering. Nulls therefore become plotted zeros; removing other invalid points compresses gaps, and spacing is by sample index rather than time. Metric cards do not consistently gate readings on sensor validity or freshness.

**Repair:** explicitly reject null/undefined and invalid sensor states; show an em dash or state label. Preserve time gaps and use timestamps on charts. Show anomaly/recovery markers and observed versus reconstructed traces where appropriate.

## 9. The Hardware page can describe a simulator or stale packet as healthy hardware

**Reproduced and source-confirmed.** The frontend fetches the hardware registry for the globally selected station, including `SIM_AWS_01`, and passes it into Hardware Integration. The hardware endpoint does not attach a simulation/freshness interpretation to its sensor status. `hardware_status()` treats `attached && valid` in the last packet as “Healthy” and “processed_by_ml,” regardless of age or actual inference readiness.

A five-minute-old packet produced `reporting=false` on the station endpoint but “Healthy” and `processed_by_ml=true` on its hardware endpoint.

**Repair:** make the selected station/source explicit on every view; default Hardware Integration to physical stations. Report last-seen time and stale status per sensor. Distinguish connected, valid, used by rules and actually used by a ready model.

The frontend hardcodes an endpoint address that differs from the firmware's configured dashboard host. Generate setup information from actual configuration or clearly mark it as an example.

## 10. Old or duplicate packets are treated as fresh new measurements

**Reproduced.** Submitting the same old-timestamp packet twice created two stored reports, advanced LSTM warm-up twice and marked the station as currently reporting.

Firmware `telemetry.cpp` includes sequence and uptime but no acquisition wall-clock timestamp. `backend/app/main.py:56` fills missing timestamps at receipt. The engine and spatial verifier use receipt time; there is no sequence/session deduplication or out-of-order guard. SQLite permits duplicate records.

**Repair:** define `(station, boot/session, sequence)` identity, retain acquisition and receipt times, reject/reconcile duplicates, and distinguish “link active” from “fresh measurement.” Restored queues must not manufacture current spatial evidence or compressed temporal windows.

## 11. Offline buffering is small and volatile, and can delay new alarms

**Source-confirmed.** The firmware queue holds 12 packets in RAM (`firmware/include/config.h` and `firmware/src/telemetry.cpp`). On overflow, the newest sample is skipped. Reset/power loss discards the queue. This is approximately tens of seconds of buffering, depending on normal/alert cadence and when the backlog rule activates—not durable outage storage.

Both Wi-Fi and optional LoRa inspect the oldest queued packet. A new critical event behind older normal packets is not prioritized; when full, its packet may be skipped. This is particularly relevant if LoRa is enabled later.

**Repair:** document the current bounds, record dropped-packet counts, prioritize current critical alerts separately from historical replay, and use bounded persistent storage if longer interruptions must be tolerated.

## 12. Failure-risk percentages are heuristic scores

**Source-confirmed.** `firmware/src/health_engine.cpp` combines fixed penalties, sensor-health decay, voltage thresholds and MLP probabilities. `localBrainApplyLinkState` also raises this same score for a communications backlog. These are useful rules, but no calibrated failure probability or prediction horizon is implemented.

The simulator's normal risk also grows with sample index, and its failure scenarios explicitly ramp the risk. These animations do not establish forecast lead time.

**Repair:** label the current output a station-health risk index; keep communication availability separate from physical degradation. Validate warning lead time and missed/false warnings against real labelled deterioration. Abrupt failures may have no measurable precursor.

## 13. Self-healing currently has narrower behavior than the broad claim suggests

**Source-confirmed.** Raw and fallback values are preserved separately in telemetry, with estimate flags and ages. That is a useful foundation.

However, `trustedDataUpdate` remembers any sensor-range-valid reading before the anomaly decision is made (`local_brain.cpp:52`, `trusted_data.cpp:79`). A plausible but faulty spike can therefore enter “last good” state. Fallback is a last-value hold for up to ten seconds, not an independently validated reconstruction. After fallback expiry, invalid numerical fields are zero-filled internally for feature computation, although validity masks remain zero.

`recovery_manager.cpp:20` stops reinitialization after three unsuccessful attempts. A sensor that failed initialization can remain unattached because regular reads are gated on its attached flag. Reconnecting after the retry limit may therefore require a reboot or additional recovery mechanism. `sensorVerify()` also uses presence flags/address acknowledgements rather than a sustained sequence of good measurements.

**Repair:** promote readings to trusted state only after acceptance; define fallback uncertainty/expiry and avoid mixing estimates into learning. Add controlled retry backoff, explicit recovery state and consecutive-good-sample validation.

## 14. Actual model capability and documentation need alignment

**Verified strengths:** exported 56→24→12→10 edge weights and training code exist. NumPy LSTM encoder and decoder gate training is implemented; the supplied training test changes weights and distinguishes a large shift. Exact channel-coalition Shapley computation is present. The edge training script uses a grouped sequence split and fits its scaler on training rows.

**Limitations:** edge training is explicitly synthetic. Its actual classes are NORMAL, SPIKE, DRIFT, FROZEN, ERRATIC, ELECTRICAL, MECHANICAL, RAIN_BLOCKED, WIND_SEIZED and VANE_STUCK. DATA_LOSS, COMMUNICATION_FAULT and STATION_DEGRADATION are produced by other logic, not learned output classes. Some architecture text names a different set.

The saved edge test metrics are 90.05% accuracy and 88.89% macro F1. Its confusion matrix gives **46.67% SPIKE recall (112/240)** and **71.25% FROZEN recall (114/160)**. These are synthetic edge-classifier results, distinct from the 97.4% fused integration benchmark. Rules may compensate, but that requires measuring the complete system.

The training generator labels the remainder of a sequence as SPIKE after a one-sample injection, and optional attachment profiles correlate with certain fault classes. Both deserve review when replacing the generated dataset. No model artifact alone establishes long-term seasonal learning or field performance.

**Repair:** document learned versus rule-based outputs, publish per-class results and provenance, evaluate normal and faulty examples for each supported attachment profile, and retrain using real sensor behavior at the intended cadence.

## 15. MPU addition: integrated software, physical verification still missing

**Verified:** the three position files in the main project are byte-identical to the separate addition. Calls exist in the main loop and telemetry; the backend preserves position metadata and gives position alarms priority over weather interpretation. There is no need to apply that addition a second time to this submitted main project.

Native C++ tests passed for calibration, sustained tilt/fall, alarm persistence, reboot restoration, invalid/moving samples, recovery, transient rejection, gaps, timer wraparound, arbitrary mounting and corrupt saved models. The six addition-specific backend tests also passed.

**Recorded hardware evidence:** the included database contains 5,623 AWS_01 hardware reports. None marks the MPU6050 valid. Of these, 4,322 contain position metadata reporting MPU_INVALID. The latest saved hardware packet, received 24 September 2026, reports DHT11 humidity, valid BMP280/INA219, an unavailable MPU, and an uncalibrated/unsaved position model. These are historical archive observations, not a live diagnosis of the currently connected board.

The frontend never reads `station_position`, so it lacks a dedicated tilt/tolerance/calibration display despite backend support. The simulator also lacks a position-calibration/fall scenario.

**Next physical check:** restore MPU readings, confirm the sensor is valid, mount the station in its intended pose, run MPUCAL for 30 settled samples, then record sustained tilt and return-to-position behavior. A gravity-baseline monitor verifies tilt; it does not establish translation or rotation about the gravity axis.

## 16. Source edits and the served frontend differ

**Source-confirmed.** `frontend/src/App.jsx` contains SKY GUARD AI / SUPER TECH TITANS branding, while the included production JavaScript does not. FastAPI serves `frontend/dist`, so editing source alone does not update this deployed view. Rebuild the production frontend when source edits are intended to appear there.

## Verification summary

- Existing Python tests plus addition backend tests: **17 passed, 1 failed**. The failure expects the text SIH26073 in the served HTML, which now has different title text; the route itself returned HTTP 200. This failure does not establish a broken server.
- Native MPU position test executable: **passed**.
- Default injected benchmark: exact classification counts reproduced. Timing differs by machine and should not be copied as the user's laptop performance.
- Focused probes reproduced readiness, missing-model, physical-consistency, empty-data, humidity-switch, weather-fusion, unknown-location, duplicate/stale-packet, stale-hardware and static-path issues.
- Full ESP32 cross-compilation/flashing and physical hardware tests were not performed. Native tests validate portable position logic only.
- Screenshots and code establish visibility/logic behavior; no browser interaction or video comparison was used to infer additional features.

## Recommended repair order

1. Close static-file path escape and sanitize shared configuration.
2. Correct no-data/warm-up/readiness states, physical-invalid handling and null formatting.
3. Separate physical equipment faults from weather evidence; fix spatial location requirements.
4. Align model cadence, preserve acquisition time and enforce packet identity/order.
5. Fix TP→TPH readiness, sensor-source/freshness display and current-alert prioritization.
6. Correct simulator/benchmark labels and evaluate the actual edge-plus-global path.
7. Restore MPU hardware operation and record calibration, tilt, recovery, unplug/reconnect and Wi-Fi-loss trials.
8. Validate risk scores, trusted-data promotion and sustained recovery on recorded field data.

The immediate goal should be an evidence trail from raw observation to detector evidence, decision, warning and recovery. That will strengthen the project more than additional dashboard cards.
