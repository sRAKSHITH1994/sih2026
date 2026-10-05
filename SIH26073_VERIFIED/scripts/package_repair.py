"""Package the portable repair with a complete ORIGINAL-relative text diff.

No source is removed. Runtime environments, compiler outputs and caches are
excluded. The ORIGINAL tree is read-only; frontend bytes must match exactly.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {'CHANGES.md', 'CHANGESET.diff', 'docs/delivery_manifest.json'}
EXCLUDED_PARTS = {'.venv', '.pio', '__pycache__', '.pytest_cache', '.git'}


def included(relative):
    return (not EXCLUDED_PARTS.intersection(relative.parts)
            and relative.parts[:3] != ('firmware', 'tests', 'build')
            and not relative.name.endswith(('.pyc', '.db-wal', '.db-shm')))


def files(root):
    return {p.relative_to(root).as_posix(): p for p in root.rglob('*')
            if p.is_file() and included(p.relative_to(root))}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path else None


def why(name):
    exact = {
        'CHANGES.md': 'Complete file-by-file repair inventory and packaging notes.',
        'CHANGESET.diff': 'Complete unified text diff; binary artifacts are supplied in full.',
        'docs/delivery_manifest.json': 'Original/delivered SHA-256 and byte-size evidence for project files.',
        'README.md': 'Current architecture, honest scope and remaining limitations.',
        'RELEASE_NOTES.md': 'Withdraw invalid old benchmark claims and explain the actual release.',
        'REPAIR_STATUS.md': 'Evidence and fixed/partial/hardware status for every A/B finding.',
        'START_HERE_WINDOWS.md': 'PowerShell setup, retraining/tests, dashboard and hardware instructions.',
        'VERSION.txt': 'Identify the repaired ten-class version.',
        'sih26073_code_audit.md': 'Preserved historical REFERENCE audit used during inventory.',
        'pytest.ini': 'Run backend tests from the project root.',
        'start_dashboard.bat': 'Preserve BAT workflow with one-time dependency marker and error handling.',
        'start_dashboard.sh': 'Preserve shell workflow with one-time dependency marker and error handling; executable mode.',
        'backend/app/main.py': 'Safe static serving/auth, identity/order/freshness guards, additive API presentation and original routes.',
        'backend/app/schemas.py': 'Validate finite/required observations and packet identity; retain frontend request/response fields.',
        'backend/app/storage.py': 'Idempotent storage/migration, historical archive, anomaly episodes and safe acknowledgement/export.',
        'backend/app/sensor_registry.py': 'Sensor source/freshness/validity and actual processing status.',
        'backend/app/spatial.py': 'Known/fresh/source-matched multi-channel neighbour corroboration.',
        'backend/app/global_brain.py': 'Equipment priority, minute cadence/TP fallback, continuous LSTM fusion and trained second opinion.',
        'backend/app/lstm_autoencoder.py': 'Contiguous window training support and cadence/provenance persistence.',
        'backend/app/local_reference.py': 'Actual exported MLP/features and compiled portable rules with parity-tested fallback; Windows DLL lookup.',
        'backend/app/simulator.py': 'Raw channel stimuli only; retain original scenario/action contract and optional profiles.',
        'backend/app/evaluation.py': 'Independent raw-input sample/event benchmark, computed coverage, delays and timing.',
        'backend/data/global_brain.db': 'Migrate committed original records; preserve reports and backfill explicitly historical events.',
        'edge_training/corpus.py': 'Current-observation labels, recovery intervals, realistic normal variation and sensor profiles.',
        'edge_training/feature_pipeline.py': 'Preserve 56 formulas/order with mask sanitation, float32 raw input and gap resets matching C++.',
        'edge_training/inference.py': 'Run exported float32 arrays and gate all optional classes by sensor masks.',
        'edge_training/train_edge_mlp.py': 'Grouped five-seed selection/comparison, held-out metrics/events and matched exports.',
        'edge_training/README.md': 'Exact classes/features, label convention, commands and limits.',
        'firmware/include/model_weights.h': 'Generated selected 56-64-32-10 weights/scaler; same arrays as NPZ.',
        'firmware/include/detection_rules.h': 'Portable shared rule core for firmware and native benchmark.',
        'firmware/include/data_types.h': 'Carry the actual 56-feature vector for the server second opinion.',
        'firmware/include/config.h': 'Version/model dimensions, bounded queue/payload settings, nominal rail and bus defaults.',
        'firmware/include/sensor_manager.h': 'Expose checked sensor and MPU diagnostics/reset/scan interfaces.',
        'firmware/include/trusted_data.h': 'Accepted-observation baseline and separate estimate/expiry API.',
        'firmware/src/feature_engine.cpp': 'Matched masks/gap reset/stable feature accumulation without changing the 56-feature order.',
        'firmware/src/edge_mlp.cpp': 'Generated hidden dimensions, all ten classes and sensor-valid output gating.',
        'firmware/src/local_brain.cpp': 'Real rules/model fusion, explicit warmup, trust acceptance and no backlog-driven physical risk.',
        'firmware/src/recovery_manager.cpp': 'Indefinite exponential retries capped at 60 seconds and three-read recovery.',
        'firmware/src/trusted_data.cpp': 'Three accepted observations before promotion, suspect separation and expiring invalid estimates.',
        'firmware/src/telemetry.cpp': 'Acquisition identity/time, persistent acknowledged priority backlog, diagnostics and feature telemetry.',
        'firmware/src/sensor_manager.cpp': 'Checked MPU identity/reset/ranges/reads and consistent I2C recovery diagnostics.',
        'firmware/src/station_position.cpp': 'Integrate scan/reset diagnostics with persistent calibrated position workflow.',
        'firmware/src/health_engine.cpp': 'Preserve ten-class sensor attribution and describe risk as a heuristic health index.',
        'firmware/src/main.cpp': 'Current version and truthful health-index serial text.',
        'SIH26073_MPU_POSITION_ADDITION/apply_addition.py': 'Prevent the older addition from overwriting already-repaired integrated firmware.',
        'SIH26073_MPU_POSITION_ADDITION/START_HERE.md': 'Explain that the MPU addition is already integrated and must not be reapplied.',
    }
    if name in exact:
        return exact[name]
    if name.endswith('requirements.txt'):
        return 'Compatible pinned/ranged dependencies, including weighted sklearn API and pandas 2.x/3.x.'
    if name.startswith('backend/tests/'):
        return 'Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity.'
    if name.startswith('firmware/tests/'):
        return 'Plain-g++ harness/stub for actual feature/model/rule, recovery/trusted or position logic; no ESP32 claim.'
    if name.startswith('edge_training/artifacts/experiments/'):
        return 'Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only.'
    if name == 'edge_training/artifacts/original_edge_mlp.npz':
        return 'ORIGINAL header arrays parsed into NPZ for the documented shifted-corpus baseline.'
    if name.startswith('edge_training/artifacts/'):
        return 'Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics.'
    if name.startswith('backend/models/'):
        return 'Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact.'
    if name.startswith('docs/verification/'):
        return 'Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md.'
    if name.startswith('docs/'):
        return 'Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation.'
    if name.startswith('scripts/'):
        return 'Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command.'
    raise ValueError('Add an explicit change explanation for ' + name)


def text_bytes(data):
    if b'\0' in data:
        return None
    try:
        return data.decode('utf-8').splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'SIH26073_VERIFIED.zip')
    args = parser.parse_args()
    original = args.original.resolve()
    output = args.output.resolve()
    if original == ROOT or ROOT in output.parents:
        raise ValueError('Use a separate ORIGINAL tree and an output outside the project root.')
    before, after = files(original), files(ROOT)
    front_before = {n: digest(p) for n, p in before.items() if n.startswith('frontend/')}
    front_after = {n: digest(p) for n, p in after.items() if n.startswith('frontend/')}
    if not front_before or front_before != front_after:
        raise ValueError('Frozen frontend does not match ORIGINAL exactly.')
    records = []
    for name in sorted((before.keys() | after.keys()) - GENERATED):
        old, new = before.get(name), after.get(name)
        oh, nh = digest(old), digest(new)
        records.append(dict(path=name, status='unchanged' if oh == nh else 'added' if old is None else 'removed' if new is None else 'modified',
                            original_sha256=oh, delivered_sha256=nh,
                            original_bytes=old.stat().st_size if old else None,
                            delivered_bytes=new.stat().st_size if new else None))
    changed = [r for r in records if r['status'] != 'unchanged']
    manifest = dict(frontend_identical=True, frontend_files=len(front_before), files=records,
                    self_reference_exclusions=sorted(GENERATED),
                    packaging_exclusions='virtualenv, PlatformIO/compiler outputs, Python/pytest/git caches and SQLite WAL/SHM; committed database retained')
    (ROOT / 'docs/delivery_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    listing = [(r['path'], r['status']) for r in changed] + [(n, 'added') for n in GENERATED]
    lines = ['# Complete change inventory', '',
             'Built from ORIGINAL. No frontend file is changed. Every delivered text file is supplied in full and every text change is in `CHANGESET.diff`; binary files are supplied in full and hashed in `docs/delivery_manifest.json`. The diff does not recursively include itself. The manifest excludes its own hash and the two generated inventory/diff files to avoid circular hashes.', '',
             'The portable ZIP keeps the original project folders and run-script names. It excludes the old machine-specific Python environment, PlatformIO outputs, native compiler binaries, caches and SQLite WAL/SHM files. Committed original database records are retained in the migrated database; rebuild host libraries with `scripts/build_native.py`. These runtime packaging exclusions are not silently removed project source.', '',
             'Rejected model variants are retained only as reproducibility checkpoints under `artifacts/experiments`; deployed header/NPZ and server metadata identify the chosen model. The historical audit is clearly separate from the current repair status.', '',
             '| File | Change | Why |', '| --- | --- | --- |']
    lines.extend(f'| `{name}` | {status} | {why(name)} |' for name, status in sorted(listing))
    lines += ['', 'Unchanged files, including all frontend paths and preserved datasets/configuration, are listed with equal hashes in the manifest. See `REPAIR_STATUS.md` for remaining hardware/field/UI limitations and `docs/EVALUATION.md` for measurements; a file change alone is not evidence that hardware was tested.', '']
    (ROOT / 'CHANGES.md').write_text('\n'.join(lines), encoding='utf-8')
    after = files(ROOT)
    with (ROOT / 'CHANGESET.diff').open('w', encoding='utf-8', newline='\n') as patch:
        for name in sorted((before.keys() | after.keys()) - {'CHANGESET.diff'}):
            old = before[name].read_bytes() if name in before else b''
            new = after[name].read_bytes() if name in after else b''
            if old == new:
                continue
            a, b = text_bytes(old), text_bytes(new)
            source = 'a/' + name if name in before else '/dev/null'
            target = 'b/' + name if name in after else '/dev/null'
            patch.write(f'diff --git a/{name} b/{name}\n')
            if a is None or b is None:
                patch.write(f'Binary files {source} and {target} differ; full delivered bytes are in the ZIP.\n')
                continue
            for line in difflib.unified_diff(a, b, fromfile=source, tofile=target, n=3):
                patch.write(line)
                if not line.endswith('\n'):
                    patch.write('\n\\ No newline at end of file\n')
    after = files(ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(after.items()):
            archive.write(path, name)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(after)
        for name in front_before:
            assert hashlib.sha256(archive.read(name)).hexdigest() == front_before[name]
        assert {'backend', 'firmware', 'edge_training', 'scripts', 'docs', 'frontend'} <= {n.split('/')[0] for n in archive.namelist()}
    print(json.dumps(dict(output=str(output), bytes=output.stat().st_size, sha256=digest(output),
                          delivered_files=len(after), changed_files=len(listing), frontend_identical=True,
                          zip_integrity='passed'), indent=2))


if __name__ == '__main__':
    main()
