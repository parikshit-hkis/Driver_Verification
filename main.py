"""
Driver Document Text Extractor — Driver-by-Driver Flow
======================================================
Processes document verification driver-by-driver in strict hierarchy:
Aadhaar → Driving Licence → PAN → RC Book.

Usage:
    python main.py                              # scan all drivers in sample_documents/
    python main.py sample_documents/DRIVER_001  # process single driver directory
    python main.py path/to/image.jpg            # single image auto-detect (legacy)
    python main.py path/to/image.jpg aadhaar    # single image forced type (legacy)
"""

import sys
import os
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.config.settings import settings
from app.pipeline import Pipeline
from app.services.doc_type_detector import DocumentType

_TYPE_ALIASES = {
    "aadhaar": DocumentType.AADHAAR,
    "aadhar": DocumentType.AADHAAR,
    "pan": DocumentType.PAN,
    "dl": DocumentType.DRIVING_LICENCE,
    "licence": DocumentType.DRIVING_LICENCE,
    "license": DocumentType.DRIVING_LICENCE,
    "driving_licence": DocumentType.DRIVING_LICENCE,
    "rc": DocumentType.RC,
}

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def run_driver(pipeline: Pipeline, driver_folder: str):
    """Process a single driver folder completely and print driver verification summary."""
    print(f"\n  Processing Driver Directory: {driver_folder}")
    try:
        result = pipeline.extract_driver(driver_folder)
        print(result.display(detailed=True))
    except Exception as e:
        print(f"\n  [ERROR] Failed to process driver folder {driver_folder}: {e}\n")


def run_all_drivers(pipeline: Pipeline, base_dir: str | None = None, max_workers: int = 1):
    """Scan base_dir for all drivers and process driver-by-driver."""
    target_dir = base_dir or settings.SAMPLE_DOCUMENTS_DIR
    driver_specs = pipeline._scanner.scan_all_drivers(target_dir)

    if not driver_specs:
        # Fallback to single image demo if legacy flat layout is present
        print(f"  No driver folders found in {target_dir}. Checking for direct images...")
        _run_legacy_demo(pipeline, target_dir)
        return

    print(f"\n  Found {len(driver_specs)} driver(s) in '{target_dir}'. Processing (workers={max_workers})...\n")

    results = pipeline.extract_all_drivers(target_dir, max_workers=max_workers, show_progress=True)

    if max_workers <= 1:
        for result in results:
            print(result.display(detailed=True))
    else:
        print(f"\n  [COMPLETED] Processed {len(results)} driver(s). Extraction JSON files saved to '{settings.EXTRACTION_OUTPUT_DIR}'.\n")


def run_single_image(pipeline: Pipeline, image_path: str, doc_type=None):
    """Legacy runner for single image extraction."""
    print(f"\n  Processing Single Image: {image_path}")
    try:
        result = pipeline.extract(image_path, doc_type=doc_type)
        print(result.display())
    except Exception as e:
        print(f"\n  [ERROR] Failed to process {image_path}: {e}\n")


def _run_legacy_demo(pipeline: Pipeline, base_dir: str):
    base = Path(base_dir)
    if not base.exists():
        print(f"  Directory '{base_dir}' does not exist.")
        return

    sample_paths = [
        ("aadhaar_card/front", DocumentType.AADHAAR),
        ("aadhaar_card/back",  DocumentType.AADHAAR),
        ("pan_card/front",     DocumentType.PAN),
        ("pan_card/back",      DocumentType.PAN),
        ("licence/front",      DocumentType.DRIVING_LICENCE),
        ("licence/back",       DocumentType.DRIVING_LICENCE),
        ("RC",                 DocumentType.RC),
    ]

    for folder, doc_type in sample_paths:
        folder_path = base / folder
        if not folder_path.exists():
            continue

        images = sorted(
            p for p in folder_path.iterdir()
            if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTS
        )
        for img_path in images:
            run_single_image(pipeline, str(img_path), doc_type=doc_type)


def main():
    print("\n" + "=" * 60)
    print("  Driver Document Text Extractor — Driver-by-Driver Flow")
    print("=" * 60)
    print("\n  Loading OCR engine (first load may take ~30s)...")

    pipeline = Pipeline()

    print("  OCR engine ready.\n")

    args = sys.argv[1:]

    # Parse optional --workers / -w flag
    workers = 1
    clean_args = []
    i = 0
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

    if not clean_args:
        # Default: scan all driver folders in configured sample documents directory
        run_all_drivers(pipeline, settings.SAMPLE_DOCUMENTS_DIR, max_workers=workers)

    elif len(clean_args) == 1:
        target = Path(clean_args[0])
        if target.is_dir():
            # Check if this directory is a single driver folder or contains multiple driver folders
            subdirs = [p for p in target.iterdir() if p.is_dir()]
            has_driver_subdirs = any(p.name.startswith("DRIVER_") or p.name.isdigit() for p in subdirs)

            if has_driver_subdirs:
                run_all_drivers(pipeline, str(target), max_workers=workers)
            else:
                run_driver(pipeline, str(target))
        elif target.is_file():
            run_single_image(pipeline, str(target))
        else:
            print(f"\n  Path '{clean_args[0]}' does not exist.\n")

    elif len(clean_args) == 2:
        image_path = clean_args[0]
        type_str = clean_args[1].lower()
        doc_type = _TYPE_ALIASES.get(type_str)
        if doc_type is None:
            print(f"\n  Unknown document type '{clean_args[1]}'. Valid: {', '.join(_TYPE_ALIASES)}\n")
            sys.exit(1)
        run_single_image(pipeline, image_path, doc_type=doc_type)

    else:
        print("\n  Usage:")
        print("    python main.py [-w 4]                          # scan all drivers in sample_documents/ with 4 workers")
        print("    python main.py <driver_folder_path> [-w 4]     # process drivers in directory")
        print("    python main.py <image_path>                    # single image auto-detect")
        print("    python main.py <image_path> <doc_type>         # single image forced type\n")


if __name__ == "__main__":
    main()