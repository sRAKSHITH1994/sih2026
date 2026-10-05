# SIH26073 verified repair, version 5.0

Built from ORIGINAL; frontend source, dist, packages and branding are byte-identical. All ten classes and all 56 input features remain. The reference's reduced class set and changed dashboard were not adopted.

The edge trainer now uses current-observation labels, independent complete sessions, realistic normal controls and five-seed comparisons. Deployment uses the validation-selected weighted 64-32 MLP. A trained server second opinion, corrected one-minute LSTM cadence, configurable threshold sweeps and continuous evidence fusion are included. Measured results and regressions are in `docs/EVALUATION.md`; there is no >98% per-sample or field-accuracy claim.

The backend removes arbitrary static fallback, authenticates writes, exposes readiness/source/freshness/availability, rejects duplicate/old data from live inference, protects equipment faults from weather override, and evaluates actual trained weights/rules from raw stimuli. The original dashboard remains usable locally through a scoped HttpOnly session for its tokenless simulation/evaluation buttons. Hardware and remote writes require the station token.

Portable firmware verifies recovery/trusted-baseline acceptance; full sensor code adds checked MPU initialization/diagnostics, packet identity and a persistent priority backlog. Native tests and host timing are recorded. ESP32 cross-build, upload and physical testing were not completed because toolchain downloads failed.

The old nine-scenario accuracy and zero-false-alarm claims are withdrawn. New reports give event detection, per-sample errors, measured explanation coverage and separate host/native timings with their limits. The unchanged UI still has chart and label limitations. Read `REPAIR_STATUS.md` before demonstrating the system.
