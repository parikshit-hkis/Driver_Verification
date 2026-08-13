"""
Identity Cross-Validation Runner
================================
Standalone runner to cross-validate extracted identity details across Aadhaar,
PAN, and Driving Licence documents.

Usage:
    python cross_validate.py                  # batch validate all drivers in result/extr_result/
    python cross_validate.py 6355528465       # validate single driver ID
"""

import sys
import os
from pathlib import Path

root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.services.identity_cross_validator.cross_validator import IdentityCrossValidator


def print_driver_validation(res) -> None:
    v = res.to_dict()["validation"]
    print(f"\nProcessing: {res.driver_id}.json\n")

    for pair_key, label in [
        ("aadhaar_vs_pan", "Aadhaar ↔ PAN"),
        ("aadhaar_vs_licence", "Aadhaar ↔ Licence"),
        ("pan_vs_licence", "PAN ↔ Licence"),
    ]:
        pair_data = v[pair_key]
        name_info = pair_data["name"]
        dob_info = pair_data["date_of_birth"]

        print(f"{label}")
        print(f"Name        : {name_info['similarity']:.2f}% {name_info['status']}")
        print(f"DOB         : {dob_info['status']}")
        print(f"Status      : {pair_data['status']}\n")

    print(f"Overall     : {res.overall_status}")
    out_file = Path("result/vldt_result") / f"{res.driver_id}.json"
    print(f"\nSaved:\n{out_file.as_posix()}\n")


def main():
    validator = IdentityCrossValidator()
    extr_dir = Path("result/extr_result")

    if not extr_dir.exists():
        print(f"Directory '{extr_dir}' does not exist. Please run extraction first.")
        return

    args = sys.argv[1:]

    if args:
        target = args[0].replace(".json", "")
        target_name = Path(target).name
        json_file = extr_dir / f"{target_name}.json"

        if not json_file.exists():
            print(f"Extraction file '{json_file}' not found.")
            return

        res = validator.validate_file(str(json_file))
        print_driver_validation(res)

    else:
        json_files = sorted(extr_dir.glob("*.json"))
        if not json_files:
            print(f"No extraction JSON files found in '{extr_dir}'.")
            return

        print(f"\nFound {len(json_files)} extraction file(s) in '{extr_dir}'. Cross-validating...\n")
        matched_count = 0
        review_count = 0
        mismatch_count = 0

        for jf in json_files:
            res = validator.validate_file(str(jf))
            print_driver_validation(res)

            if res.overall_status == "MATCHED":
                matched_count += 1
            elif res.overall_status == "REVIEW":
                review_count += 1
            else:
                mismatch_count += 1

        print("=" * 55)
        print(f"IDENTITY CROSS-VALIDATION BATCH SUMMARY")
        print("=" * 55)
        print(f"Total Drivers Validated : {len(json_files)}")
        print(f"  MATCHED   : {matched_count}")
        print(f"  REVIEW    : {review_count}")
        print(f"  MISMATCH  : {mismatch_count}")
        print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
