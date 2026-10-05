"""Apply only the MPU position addition to an existing SIH26073 project."""
from pathlib import Path
import argparse
import ast
from datetime import datetime
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent


def replace_once(text, old, new, label):
    if new in text:
        return text
    if text.count(old) != 1:
        raise ValueError(f'{label}: expected code was not found exactly once. No files changed. Send this message and the named file for an adapted patch.')
    return text.replace(old, new, 1)


def build_changes(root):
    # Repaired main firmware already integrates a newer position implementation.
    config = root / 'firmware/include/config.h'
    if config.exists() and 'SIH26073-VERIFIED-5.0' in config.read_text(encoding='utf-8'):
        return {}
    changes = {}

    def edit(relative, transform):
        path = root / relative
        old = path.read_bytes()
        newline = '\r\n' if b'\r\n' in old else '\n'
        text = old.decode('utf-8-sig').replace('\r\n', '\n')
        new = transform(text)
        if relative.endswith('.py'):
            ast.parse(new, filename=relative)
        if new != text:
            changes[path] = new.replace('\n', newline).encode('utf-8')

    def main(text):
        text = replace_once(text, '#include "telemetry.h"', '#include "telemetry.h"\n#include "station_position.h"', 'firmware/src/main.cpp include')
        text = replace_once(text, 'telemetryBegin();printCsvHeader();', 'telemetryBegin();stationPositionBegin();printCsvHeader();', 'firmware/src/main.cpp setup')
        text = replace_once(text, 'void loop(){', 'void loop(){\n  stationPositionPollSerial();', 'firmware/src/main.cpp loop')
        return replace_once(text, 'haveDecision=true;', 'stationPositionUpdate(snapshot,currentDecision);haveDecision=true;', 'firmware/src/main.cpp decision')

    edit('firmware/src/main.cpp', main)

    def telemetry(text):
        text = replace_once(text, '#include "sensor_manager.h"', '#include "sensor_manager.h"\n#include "station_position.h"', 'firmware/src/telemetry.cpp include')
        old = '  local["alarm_state"] = alarmState();'
        new = old + '''
  // MPU_POSITION_ADDITION: read on the loop task before the packet is queued.
  const auto& position = stationPositionReport();
  JsonObject pose = local["station_position"].to<JsonObject>();
  pose["state"] = position.state;
  pose["calibrated"] = position.calibrated;
  pose["calibrating"] = position.calibrating;
  pose["saved"] = stationPositionModelSaved();
  pose["sample_valid"] = position.sampleValid;
  pose["measurement_valid"] = position.measurementValid;
  pose["active"] = position.active;
  pose["critical"] = position.critical;
  if (position.measurementValid) pose["tilt_deg"] = position.tiltDeg;
  else pose["tilt_deg"] = nullptr;
  pose["tolerance_deg"] = position.toleranceDeg;
  pose["method"] = "calibrated_gravity_baseline";
'''
        return replace_once(text, old, new, 'firmware/src/telemetry.cpp report')

    edit('firmware/src/telemetry.cpp', telemetry)
    edit('firmware/src/health_engine.cpp', lambda text: replace_once(text,
         'if(ml.valid&&ml.classId!=0&&ml.probability>=ML_MIN_CONFIDENCE)',
         'if(ml.valid&&ml.classId!=0&&ml.classId!=6&&ml.probability>=ML_MIN_CONFIDENCE)',
         'firmware/src/health_engine.cpp mechanical attribution'))

    def config(text):
        match = re.search(r'(?m)^#define TELEMETRY_PAYLOAD_SIZE (\d+)\s*$', text)
        if not match:
            raise ValueError('firmware/include/config.h: cannot find telemetry size. No files changed.')
        if int(match.group(1)) < 5120:
            text = text[:match.start(1)] + '5120' + text[match.end(1):]
        return text
    edit('firmware/include/config.h', config)

    def platformio(text):
        match = re.search(r'(?m)^monitor_filters\s*=\s*([^\r\n]*)$', text)
        if not match:
            raise ValueError('firmware/platformio.ini: expected monitor_filters setting is missing. No files changed.')
        filters = [f.strip() for f in match.group(1).split(',') if f.strip() and f.strip() != 'colorize']
        if 'send_on_enter' not in filters:
            filters.append('send_on_enter')
        return text[:match.start()] + 'monitor_filters = ' + ', '.join(filters) + text[match.end():]
    edit('firmware/platformio.ini', platformio)

    edit('backend/app/schemas.py', lambda text: replace_once(text,
        '    station_state: str = "NORMAL"',
        '    station_state: str = "NORMAL"\n    station_position: dict[str, Any] = Field(default_factory=dict)',
        'backend/app/schemas.py position metadata'))

    def backend(text):
        old = '        if invalid_attached or local_fault in {"DATA_LOSS","COMMUNICATION_FAULT"}:'
        new = '''        # MPU_POSITION_ADDITION: physical mounting evidence is not a weather event.
        pose = local.get("station_position", {})
        position_alert = bool(pose.get("active")) and bool(pose.get("calibrated"))
        if position_alert:
            alert = True
            affected = list(dict.fromkeys(affected + ["station"]))
            critical = bool(pose.get("critical"))
            other_critical = bool(invalid_attached) or float(local.get("severity_score", 0)) >= 80
            decision = GlobalDecision(
                category="STATION_POSITION_FAULT",
                specific_type="STATION_FALLEN" if critical else "STATION_TILTED",
                anomaly=True, sensor_fault=bool(invalid_attached),
                confidence=float(local.get("confidence", .9)),
                severity="CRITICAL" if critical or other_critical else "HIGH",
                explanation=local.get("explanation", "The station moved outside its calibrated orientation tolerance."),
                affected_features=affected,
            )
        elif invalid_attached or local_fault in {"DATA_LOSS","COMMUNICATION_FAULT"}:'''
        return replace_once(text, old, new, 'backend/app/global_brain.py station classification')
    edit('backend/app/global_brain.py', backend)

    for source in sorted((HERE / 'files').rglob('*')):
        if not source.is_file():
            continue
        destination = root / source.relative_to(HERE / 'files')
        data = source.read_bytes()
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError(f'{destination.name} already exists with different content. No files changed.')
        if not destination.exists():
            changes[destination] = data
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path, help='Existing SIH26073_FINAL_SYSTEM folder')
    parser.add_argument('--check', action='store_true', help='Check compatibility without changing files')
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    changes = build_changes(root)
    if not changes:
        print('MPU position addition is already installed. No changes needed.')
        return
    print('Files to add/update:')
    for path in changes:
        print('  ' + str(path.relative_to(root)))
    if args.check:
        print('Compatibility check passed; no files changed.')
        return
    backup = root / 'mpu_position_backups' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    originals = {path: path.read_bytes() if path.exists() else None for path in changes}
    # Validate everything above before writing anything. Back up originals first.
    for path, data in originals.items():
        if data is not None:
            copy = backup / path.relative_to(root)
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(data)
    touched = []
    try:
        for path, data in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            touched.append(path)
            path.write_bytes(data)
    except Exception:
        for path in reversed(touched):
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(originals[path])
        raise
    print('MPU position addition installed.')
    print('Original files backed up at: ' + str(backup))
    print('Next: restart the dashboard, build/upload firmware, then calibrate using MPUCAL.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STOP: ' + str(error), file=sys.stderr)
        sys.exit(1)
