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

from app.config.settings import settings
from app.pipeline import Pipeline
from result.accuracy_calculator import AccuracyCalculator


def main():
    args = sys.argv[1:]
    docs_dir = settings.SAMPLE_DOCUMENTS_DIR
    workers = 1

    i = 0
    clean_args = []
    while i < len(args):
        if args[i] in ("-w", "--workers") and i + 1 < len(args):
            try:
                workers = max(1, int(args[i + 1]))
                i += 2
                continue
            except ValueError:
                pass
        clean_args.append(args[i])
        i += 1

    if clean_args:
        docs_dir = clean_args[0]

    print(f"\nEvaluating extraction accuracy for directory: '{docs_dir}' (workers={workers})...\n")

    pipeline = Pipeline()
    results = pipeline.extract_all_drivers(docs_dir, max_workers=workers, show_progress=True)

    if not results:
        print(f"No driver folders found or processed in '{docs_dir}'.")
        return

    calculator = AccuracyCalculator()
    report = calculator.evaluate_driver_results(results)
    dashboard = calculator.format_dashboard(report)

    print("\n" + dashboard)


if __name__ == "__main__":
    main()
