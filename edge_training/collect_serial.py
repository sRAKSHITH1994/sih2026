"""Collect firmware CSV telemetry for real-data retraining and field tests."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import time

import serial


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Example: COM11")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--output", default="real_station_log.csv")
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()

    output = Path(args.output)
    header = None
    started = time.time()
    with serial.Serial(args.port, args.baud, timeout=1) as connection, output.open("w", newline="", encoding="utf-8") as handle:
        writer = None
        while time.time() - started < args.seconds:
            line = connection.readline().decode("utf-8", errors="replace").strip()
            if line.startswith("CSV_HEADER,"):
                header = next(csv.reader([line[len("CSV_HEADER,"):]]))
                writer = csv.writer(handle); writer.writerow(header); handle.flush()
            elif line.startswith("CSV,") and writer and header:
                row = next(csv.reader([line[len("CSV,"):]]))
                if len(row) == len(header):
                    writer.writerow(row); handle.flush()
            if line:
                print(line)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()

