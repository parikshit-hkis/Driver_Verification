"""
Accuracy Calculator Runner
==========================
Run this script anytime to evaluate document extraction accuracy percentages
across all driver folders without changing core codebase.

Usage:
    python -m result.calculate
    or
    python result/calculate.py [path_to_documents_folder]
"""

import sys
import os
from pathlib import Path

# Ensure root workspace directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.pipeline import Pipeline
from result.accuracy_calculator import AccuracyCalculator


def main():
    docs_dir = sys.argv[1] if len(sys.argv) > 1 else "sample_documents"
    print(f"\nEvaluating extraction accuracy for directory: '{docs_dir}'...")

    pipeline = Pipeline()
    driver_specs = pipeline._scanner.scan_all_drivers(docs_dir)

    if not driver_specs:
        print(f"No driver folders found in '{docs_dir}'.")
        return

    print(f"Discovered {len(driver_specs)} driver directory(s). Processing...")

    results = []
    for i, spec in enumerate(driver_specs, 1):
        print(f"  [{i:02d}/{len(driver_specs):02d}] Processing Driver: {spec.driver_id}...", end="", flush=True)
        res = pipeline.extract_driver(spec)
        results.append(res)
        print(" DONE")

    calculator = AccuracyCalculator()
    report = calculator.evaluate_driver_results(results)
    dashboard = calculator.format_dashboard(report)

    print(dashboard)


if __name__ == "__main__":
    main()
