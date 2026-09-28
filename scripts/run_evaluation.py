from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))

from app.config import MODEL_PATH
from app.evaluation import run_injected_evaluation


def main():
    result=run_injected_evaluation(MODEL_PATH,samples_per_scenario=100,stations=5,seed=42)
    output=ROOT/"backend"/"models"/"evaluation_metrics.json"
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"binary_metrics":result["binary_metrics"],"category_accuracy":result["category_accuracy"],
                      "latency":result["latency"]},indent=2))
    print(f"saved {output}")


if __name__=="__main__":main()
