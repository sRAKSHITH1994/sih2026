"""Render measured evaluation tables from command-produced JSON, never invented scores."""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT / relative).read_text())


def table(headers, rows):
    return '\n'.join([
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join(['---'] * len(headers)) + ' |',
        *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows],
    ])


def percent(value):
    return f'{100 * value:.2f}%'


def mean_std(item):
    return f"{100 * item['mean']:.2f} ± {100 * item['std']:.2f}"


def main():
    edge = read('edge_training/artifacts/edge_mlp_metrics.json')
    ablation = read('edge_training/artifacts/label_ablation_metrics.json')
    pipeline = read('backend/models/evaluation_metrics.json')
    native = read('backend/models/native_metrics.json')
    lstm = read('backend/models/lstm_metrics.json')
    selected = edge['selection']['candidate']
    runs = edge['tests'][selected]
    classes = edge['classes']
    assert len(classes) == 10 and len(edge['features']) == 56 and len(runs) >= 5
    assert edge['model_npz_sha256'] == native['model_sha256']
    assert pipeline['native_rules_used'] and not pipeline['labels_reach_inference']
    model_hash = hashlib.sha256((ROOT / 'edge_training/artifacts/edge_mlp.npz').read_bytes()).hexdigest()
    assert model_hash == edge['model_npz_sha256']
    bm = pipeline['binary_metrics']
    pe = pipeline['event_detection']
    edge_events = {}
    for name in classes[1:]:
        items = [r['events'][name] for r in runs]
        delays = [v for r in items for v in r['delays_seconds']]
        edge_events[name] = dict(
            events=sum(r['events'] for r in items),
            detected=sum(r['detected'] for r in items),
            typed=sum(r['typed_detected'] for r in items),
            median=float(np.median(delays)) if delays else None,
            p95=float(np.percentile(delays, 95)) if delays else None,
        )
    caught = sum(r['detected'] for r in edge_events.values())
    total = sum(r['events'] for r in edge_events.values())
    row_count = sum(r['rows'] for r in runs)
    session_count = sum(r['sequences'] for r in runs)
    sections = ['# Measured evaluation — synthetic and supplied-data evidence',
        f'''The integrated system caught **{pe['detected']}/{pe['events']} injected events ({percent(pe['rate'])})** in independent synthetic sessions. Its per-sample binary accuracy was **{percent(bm['accuracy'])}**, with **{bm['fp']}/{bm['fp'] + bm['tn']} normal samples falsely alerted ({percent(bm['false_alarm_rate'])})**. Report these together. The high event rate does not imply high per-sample accuracy, correct fault typing, or a low false-alarm burden.

The selected ESP32 MLP alone achieved **{mean_std(edge['summary'][selected]['accuracy'])}% ten-class per-sample accuracy** across five held-out seeds and **{caught}/{total} ({percent(caught / total)}) event detection**. A >98% per-sample claim is not supported. None of these numbers establishes field accuracy or a calibrated failure probability. The old slide's 97.4%, 0/388, 67.74 ms and 27.77 KB must be replaced, not carried forward.

Re-render this report after reproducing the commands below with `python scripts/make_repair_report.py`. JSON artifacts retain full precision, per-seed results and confusion matrices. Percentages and delays in this document are calculated from those artifacts.''',
        '## Commands and splits',
        '''Run from the project root, using the environment interpreter. On PowerShell use `.\\.venv\\Scripts\\python.exe` in place of `python`. Set `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1` for comparable CPU contention.

```text
python edge_training/train_edge_mlp.py --jobs 5
python scripts/ablate_spike_labels.py --jobs 5
python scripts/train_lstm.py --threshold-percentile 97
python scripts/run_native_tests.py
python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16
python scripts/measure_native.py
python scripts/make_repair_report.py
```

The recorded final edge audit was produced with `python edge_training/train_edge_mlp.py --finalize-only` after the five-seed training comparison; this reuses the included train/validation checkpoints without fitting on test. A full run of the first command repeats both fitting and finalization. The initial exploratory run exposed test results before the stricter consistency selection rule was settled; those results are not the final reported audit. The final model choice was locked using validation, then a fresh test namespace with run-seed offset 100 was evaluated. This procedural change is disclosed rather than describing the entire development process as a pristine preregistered experiment.

For each training seed 0–4: 48 train, 16 validation and 32 final test sessions per class; ten classes; 220 raw 1 Hz observations per session. Entire sessions belong to one split. The first 19 observations warm the feature window and are excluded from MLP classification metrics, not labelled as model successes. Training, validation, test and integrated evaluation use disjoint seed namespaces. Normalization fits training only; external whole-session validation selects epochs. No onset or recovery rows are removed after warmup. The selected artifact always uses training seed 0, not whichever seed scores best on test.

Humid dry periods, calm wind and fixed vane direction are deliberate NORMAL controls. Multi-channel weather fronts remain NORMAL. Humidity includes whole-percent and fine-resolution profiles. Missing channels are zero-filled only inside the masked feature vector; they are not represented as valid zero observations. Rain, wind and vane classes remain in all model outputs and are gated when their corresponding sensor is invalid.''',
        f'Final MLP audit: {session_count} complete held-out sessions, {row_count} eligible observations across the five seeds. Split manifests are in `edge_training/artifacts/experiments/seed_*/split_manifest.json`. Raw sessions regenerate deterministically from the manifest seeds and `corpus.py`.',
        '## Ten-class per-sample results',
        table(['Model', 'Accuracy % mean ± SD', 'Balanced accuracy %', 'Macro-F1 %', 'Binary accuracy %'], [
            [name, *[mean_std(edge['summary'][name][k]) for k in ['accuracy', 'balanced_accuracy', 'macro_f1', 'binary_accuracy']]]
            for name in ['original', 'small_resample', 'large_resample', selected, 'large_regularized', 'server_boosting', 'server_blend']]),
        '''SD is the sample standard deviation across five seeds, not a confidence interval over correlated rows. `original` is the ORIGINAL exported weight/scaler arrays evaluated on the new, harder corpus through the current mask-compatible feature implementation. It is a distribution-shift baseline, not a reproduction of the ORIGINAL small-test score and not a controlled estimate of one repair's benefit. Server boosting and the 50/50 blend use the same train/validation/test sessions as the MLP. They are host models, not ESP32 models. Boosting alone scores better than the fixed blend on this audit; it is retained as a second opinion, not used to replace the embedded model based on test results.''',
        '### Per-class recall before and after',
        table(['Class', 'ORIGINAL weights on new corpus %', 'Same 64-32 model, buggy SPIKE training labels %', 'Corrected selected model % mean ± SD'], [
            [name,
             f"{100 * np.mean([r['classification'][name]['recall'] for r in edge['tests']['original']]):.2f}",
             f"{100 * ablation['per_class_recall'][name]['buggy_mean']:.2f}",
             f"{100 * np.mean([r['classification'][name]['recall'] for r in runs]):.2f} ± {100 * np.std([r['classification'][name]['recall'] for r in runs], ddof=1):.2f}"]
            for name in classes]),
        '### Changes and measured effects',
    ]
    effect = ablation['effect']
    recall = ablation['per_class_recall']
    sections += [
        f"- **Labels (kept):** the controlled train-only label ablation changes ten-class accuracy {percent(effect['accuracy']['buggy_mean'])} → {percent(effect['accuracy']['corrected_mean'])}, SPIKE recall {percent(recall['SPIKE']['buggy_mean'])} → {percent(recall['SPIKE']['corrected_mean'])}, and NORMAL recall {percent(recall['NORMAL']['buggy_mean'])} → {percent(recall['NORMAL']['corrected_mean'])}; validation and test always use correct labels.",
        f"- **64-32 weighted loss (kept):** validation macro-F1 improves in four of five seeds over 24-12 resampling; final audit macro-F1 {percent(edge['summary']['small_resample']['macro_f1']['mean'])} → {percent(edge['summary'][selected]['macro_f1']['mean'])}; balanced accuracy declines {percent(edge['summary']['small_resample']['balanced_accuracy']['mean'])} → {percent(edge['summary'][selected]['balanced_accuracy']['mean'])}. Selection optimizes macro-F1, not every metric.",
        f"- **64-32 resampling (not deployed):** validation improves in only three of five seeds; final macro-F1 {percent(edge['summary']['large_resample']['macro_f1']['mean'])}. A small mean gain did not meet the consistency rule.",
        f"- **Stronger regularization/longer patience (not deployed):** alpha .01 and patience 40 improve validation in only three of five seeds versus weighted alpha .001/patience 20; final macro-F1 {percent(edge['summary']['large_regularized']['macro_f1']['mean'])} is below the retained model. Alpha and patience were tested together, so their individual causal effects are not identified.",
        f"- **Server second opinion (kept):** the fixed 50/50 blend improves validation macro-F1 in all five seeds; final MLP/blend macro-F1 {percent(edge['summary'][selected]['macro_f1']['mean'])} → {percent(edge['summary']['server_blend']['macro_f1']['mean'])}.",
        '- **Realism and grouped splits (required):** these change the validity and difficulty of the evaluation; no isolated accuracy gain is claimed. No derived frozen-channel feature or blanket debounce was introduced. FROZEN onset/recovery ambiguity remains unresolved; do not compare its harder current recall directly with the earlier easy-corpus recall.',
        '- **Continuous LSTM fusion (implemented, operational gain unmeasured):** the short integrated sessions never warm the minute model. Unit tests verify score continuity and precedence, not an accuracy improvement. Keep this distinction in presentations.',
        '### Confusion matrix',
        'Aggregate counts across the five held-out MLP runs; rows are true labels and columns are predictions. The order is the full ten-class list.',
    ]
    confusion = np.sum([np.asarray(r['confusion_matrix']) for r in runs], axis=0)
    sections.append(table(['True / predicted', *classes], [[name, *row.tolist()] for name, row in zip(classes, confusion)]))
    sections += ['## MLP-only event detection',
        '''An event is one injected fault interval. A hit is any non-NORMAL MLP prediction during that interval; typed hits require the correct class at least once. A prediction already active at onset may count as a zero-delay hit. No post-event allowance is used. Delays are from injection onset to first hit, conditional on detected events; misses are counted separately. The MLP-only event metric uses argmax without the operational confidence threshold, rules or server fusion.''',
        table(['Fault', 'Detected / events', 'Rate', 'Correct-type hits', 'Median delay s', 'p95 delay s'], [
            [name, f"{r['detected']}/{r['events']}", percent(r['detected'] / r['events']), r['typed'], f"{r['median']:.1f}", f"{r['p95']:.1f}"]
            for name, r in edge_events.items()]),
        '## Integrated raw-stimulus benchmark',
        f'''The deployment seed-0 MLP runs on raw stimuli through the Python feature extractor whose parity is checked against C++, the actual exported float32 weights, compiled C++ firmware rules, and Global Brain including its trained second opinion. No scenario name or ground-truth label is passed to the detector. {len(pipeline['scenarios'])} scenario types × {pipeline['sessions_per_class']} sessions × {pipeline['samples_per_scenario']} observations produce {pipeline['samples']} target observations; neighbouring stations bring the total to {pipeline['latency']['total_packets_all_stations']} processed packets. Evaluation reset boundaries are whole sessions. This additional evaluation namespace is disjoint from fitting and model selection.

Binary truth means sensor/equipment fault. Genuine weather is negative. Raw power sag and missing data are included; a complete powerless radio-silent station is not simulated by the power-sag scenario. Physical ESP32 health/recovery/position behavior, storage, transport and browser time are excluded. LSTM-ready target observations: **{pipeline['lstm_ready_target_samples']}**; its separate minute-window audit follows below.''',
        table(['Binary metric', 'Value'], [
            [k, percent(bm[k])] for k in ['accuracy', 'balanced_accuracy', 'precision', 'recall', 'specificity', 'false_alarm_rate', 'f1']]),
        table(['Actual / predicted', 'Normal', 'Fault'], [['Normal', bm['tn'], bm['fp']], ['Fault', bm['fn'], bm['tp']]]),
        table(['Scenario', 'Events caught / total', 'Correct-type hits', 'Median / p95 delay s', 'False alerts / normal samples'], [
            [r['scenario'], f"{r['events_detected']}/{r['events']}" if r['events'] else 'no injected fault',
             r['typed_events_detected'] if r['events'] else '—',
             f"{r['detection_latency_samples']:.1f} / {r['p95_delay_seconds']:.1f}" if r['delay_seconds'] else '—',
             f"{r['confusion']['fp']}/{r['confusion']['fp'] + r['confusion']['tn']}"] for r in pipeline['scenarios']]),
        f"Measured explanation coverage is {pipeline['explained_alert_samples']}/{pipeline['alert_samples']} = {percent(pipeline['explanation_coverage'])}: alerts with nonempty text plus feature attribution, affected-sensor evidence, or invalid-feature evidence. This is a presence/coverage measure, not a test that explanations are causally correct. `normal.detected` is computed from false alerts, and is false in this run.",
        '''The weather test still produces false alarms despite stricter spatial confirmation. Its safeguards are verified in `test_spatial.py` and equipment-precedence tests; field discrimination quality is not established. Correct-type counts use the final decision's exact `specific_type`; composite/physical range categories may catch an event without matching its injected class name.''',
        '## LSTM threshold audit',
        '''Command: `python scripts/train_lstm.py --threshold-percentile 97`. TP and TPH use 20 completed one-minute snapshots, stride one snapshot; live inference uses the same cadence and resets on gaps. A ready TP model remains active while TPH accumulates sufficient humidity history. Training uses only contiguous normal train windows; normal validation windows set each profile's threshold. Test windows never fit weights or thresholds. Supplied CSV acquisition provenance is unverified. A window is positive if any of its original 20 rows is anomalous; overlapping windows are not independent events.

The selected percentile 97 follows the user's requested operating point before this audit; per-profile percentile overrides are supported but were not tuned on the test table. The following table is diagnostic, not an instruction to pick the best test result. Thresholds differ by profile even when the percentile is shared.''',
        table(['Profile', 'Normal train windows', 'Normal validation windows', 'All test windows', 'Threshold at selected percentile'], [
            [name, r['training_windows'], r['validation_windows'], r['test_windows'], f"{r['threshold']:.9g}"] for name, r in lstm['profiles'].items()]),
        table(['Profile', 'Percentile', 'Validation precision', 'Validation recall', 'Test precision', 'Test recall', 'Test FP / negatives'], [
            [name, r['percentile'], percent(r['validation']['precision']), percent(r['validation']['recall']), percent(r['test']['precision']), percent(r['test']['recall']), f"{r['test']['confusion']['fp']}/{r['test']['confusion']['fp'] + r['test']['confusion']['tn']}"]
            for name, p in lstm['profiles'].items() for r in p['sweep']]),
    ]
    for name, r in lstm['profiles'].items():
        before = next(v['test'] for v in r['sweep'] if v['percentile'] == 99.2)
        sections.append(f"- {name}, same retrained model: 99.2 → {r['threshold_percentile']:g} percentile changes test recall {percent(before['recall'])} → {percent(r['recall'])}, false alarms {before['confusion']['fp']} → {r['confusion']['fp']}. This is not a rerun of the old incorrectly cadenced benchmark.")
    sections += [
        '''Continuous fusion uses the reconstruction-loss/threshold ratio, maps it to `ratio/(1+ratio)`, and combines it with the edge score as `1-(1-edge)*(1-lstm)`. Its result is an uncalibrated evidence score. The fusion decision threshold is a documented heuristic, not a learned failure probability. Equipment, pose, range and missing-data evidence take precedence over weather confirmation.''',
        '## Replacement slide numbers and measurement boundaries',
        table(['Slide item', 'Measured value', 'Exact command', 'Measures', 'Does NOT measure'], [
            ['Detection', f"{pe['detected']}/{pe['events']} = {percent(pe['rate'])} event detection; {percent(bm['accuracy'])} binary sample accuracy", 'python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16', 'Held-out injected events and target samples through real MLP, compiled rules and server', 'Field accuracy, exact fault typing, ESP32 hardware, ready LSTM'],
            ['False alarms', f"{bm['fp']}/{bm['fp'] + bm['tn']} = {percent(bm['false_alarm_rate'])}", 'python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16', 'Normal target samples falsely flagged, including weather and recovery', 'False events per day or field specificity'],
            ['Host pipeline latency', f"mean {pipeline['latency']['mean_inference_ms']:.3f} ms; p95 {pipeline['latency']['p95_inference_ms']:.3f} ms", 'python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16', 'Synchronous features + MLP/rules + server CPU time', 'ESP32 or network/radio/database/browser/end-to-end delay'],
            ['Model array payload', f"{native['weight_bias_bytes']} weight/bias bytes + {native['normalization_bytes']} normalization bytes = {native['all_float_array_bytes']} bytes ({native['all_float_array_bytes']/1024:.4f} KiB)", 'python scripts/measure_native.py', 'Native sizeof the exact float arrays compiled from model_weights.h', 'Entire firmware flash image, linker padding/code/RAM or header text size'],
            ['Native firmware MLP latency', f"mean {native['mean_inference_ms']:.5f} ms; p95 {native['p95_inference_ms']:.5f} ms", 'python scripts/measure_native.py', 'Host g++ -O2 runEdgeML over independent held-out features, including scaling/masks/softmax/attribution', 'Feature extraction, transport or ESP32 timing'],
        ]),
        f"Native timing: {native['samples']} held-out feature vectors; {native['compiler']}; {native['platform']}. Header source text is {native['model_header_text_bytes']} bytes, distinct from the float-array payload. The final model NPZ SHA-256 is `{model_hash}`. Wall-clock latency varies by host/load; reproduce rather than treating these decimals as universal constants.",
        '## Verification and remaining work',
        '''See `VALIDATION.md`, `REPAIR_STATUS.md` and `verification/` for the actual logs. The ORIGINAL frontend is byte-identical, including its stale production dist. Browser checks covered its four pages, simulation and evaluation POSTs, with no JavaScript page errors. The backend serves that original dist; it does not rebuild it.

Physical work remaining: complete an ESP32 PlatformIO build/upload; measure on-device flash, stack/heap and timing; verify BMP/DHT/INA/MPU reads and electrical ranges; test persistent calibration, actual pose changes and I2C failures; exercise indefinite recovery retries with three valid reads; power-cut LittleFS writes and acknowledgements; test queue saturation, flash wear, reboot replay and LoRa gateway delivery; collect independently labelled multi-station field sessions, including difficult normal plateaus, sensor gaps and weather fronts. The native build does not certify any of these physical behaviors.

The frozen UI prevents gap-breaking/acquisition-time chart rendering and removal of hardcoded confidence/risk labels. The API provides availability, source, freshness, timestamps and honest explanations, but those visual limitations remain. No frontend byte was changed to hide them.''',
        '## Five judge questions and truthful answers',
        f"1. **Is {percent(pe['rate'])} your accuracy?** No. It is event detection on injected held-out sessions. Binary per-sample accuracy is {percent(bm['accuracy'])}; ten-class edge accuracy is {mean_std(edge['summary'][selected]['accuracy'])}% across seeds.",
        f"2. **Did you achieve zero false alarms?** No. This integrated run produced {bm['fp']} false alert samples out of {bm['fp'] + bm['tn']} normal target samples. Consecutive alerts are correlated, so this is not a false-event rate per day.",
        '3. **Were labels or rules used to fake model success?** Labels only generate stimuli and score output; inference receives raw values, masks and packet context. It runs trained weights and compiled firmware rules. Explanation coverage measures evidence presence, not causal correctness.',
        '4. **Are latency and model size measured on ESP32?** No. Native sizeof gives the float-array payload, and host C++/Python timings are reported separately. ESP32 build/download, upload and physical timing remain unverified.',
        f"5. **What is the largest remaining model weakness?** FROZEN per-sample recall is {percent(recall['FROZEN']['corrected_mean'])}; onset windows and legitimate plateaus remain ambiguous. The LSTM has limited recall too. Event detection cannot substitute for field calibration or correct sample labels.",
    ]
    (ROOT / 'docs/EVALUATION.md').write_text('\n\n'.join(sections) + '\n', encoding='utf-8')
    feature_docs = '''# Ten-class edge training

The deployed network is 56 → 64 → 32 → 10 (ReLU hidden layers, softmax output). `train_edge_mlp.py` exports the same float32 arrays to `artifacts/edge_mlp.npz` and `firmware/include/model_weights.h`. Firmware dimensions come from the generated header. `inference.py` runs those exported arrays; the simulator never substitutes scenario labels for predictions.

## Commands

```text
python -m pip install -r edge_training/requirements.txt -r backend/requirements.txt
python edge_training/train_edge_mlp.py --jobs 5
python scripts/ablate_spike_labels.py --jobs 5
python scripts/run_native_tests.py
python scripts/measure_native.py
python scripts/make_repair_report.py
```

Use `--jobs 1` if memory is limited. Default training and metrics are synthetic. The loader `real_dataset(path)` validates externally annotated `ground_truth`, `session_id`, `split`, timestamps, channel values and validity masks, but it is not exposed as a real-data training CLI. Collected detector labels are predictions, never independent truth. Add a separately reviewed field training workflow before claiming field learning.

## Labels and sensor masks

SPIKE labels only the 1–2 modified samples of each injected event. Its return transition and following tail are NORMAL. Persistent faults are labelled from onset inclusive to recovery exclusive; recovery is immediately NORMAL even while features retain window history. There is no onset grace period. This intentionally exposes detection lag and residual-window false alarms.

Profiles are core, core_humidity, wind, rain and full. BMP/MPU/INA are core; optional weather channels are absent according to profile. The feature-valid mask gates ELECTRICAL by INA, MECHANICAL by MPU, RAIN_BLOCKED by rain, WIND_SEIZED by wind and VANE_STUCK by vane. All ten output classes remain. BMP is required for a ready 20-observation feature window. Nonfinite/invalid raw channels are sanitized identically in Python/C++; a gap over 2500 ms restarts window readiness and adaptive state.

The corpus varies seeds, noise floors, levels, diurnal phase, genuine multi-channel weather fronts, humidity quantization and installed sensors. Normal calm wind, fixed vane and humid-without-rain controls deliberately overlap optional faults. No derived frozen-channel count or blanket prediction debounce was added. Full label, split, selection and measured limitation details are in `../docs/EVALUATION.md`.

## Exact output class order

'''
    feature_docs += table(['Index', 'Class'], list(enumerate(classes)))
    feature_docs += '\n\n## Exact 56-feature input order\n\n'
    feature_docs += table(['Index', 'Feature'], list(enumerate(edge['features'])))
    feature_docs += '''

The window remains 20 one-second observations. The feature formulas/order remain the ORIGINAL 56-feature design; raw mask sanitation, gap resets and numerically stable accumulators are matched in `feature_pipeline.py` and `firmware/src/feature_engine.cpp`. Native tests compare all features, predicted class, score and portable-rule output across all ten fault classes. No unreviewed feature is appended.
'''
    (ROOT / 'edge_training/README.md').write_text(feature_docs, encoding='utf-8')
    print('Updated docs/EVALUATION.md and edge_training/README.md from measured JSON.')


if __name__ == '__main__':
    main()
