"""
Driver Document Text Extractor — Version 1
==========================================
Demo runner. Tests extraction on all available sample images.

Usage:
    python main.py                          # auto-scan sample_documents/
    python main.py path/to/image.jpg        # single image, auto-detect type
    python main.py path/to/image.jpg aadhaar  # force document type
"""

import sys
import os
from pathlib import Path

from app.pipeline import Pipeline
from app.services.doc_type_detector import DocumentType

# ── Document type shorthand aliases ──────────────────────────────────────────
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

# ── Default sample paths to try ───────────────────────────────────────────────
_SAMPLE_PATHS = [
    ("sample_documents/aadhaar_card/front", DocumentType.AADHAAR),
    ("sample_documents/aadhaar_card/back",  DocumentType.AADHAAR),
    ("sample_documents/pan_card/front",     DocumentType.PAN),
    ("sample_documents/pan_card/back",      DocumentType.PAN),
    ("sample_documents/licence/front",      DocumentType.DRIVING_LICENCE),
    ("sample_documents/licence/back",       DocumentType.DRIVING_LICENCE),
    ("sample_documents/RC",                 DocumentType.RC),
]

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def run_single(pipeline: Pipeline, image_path: str, doc_type=None):
    """Run extraction on a single image and print results."""
    print(f"\n  Processing: {image_path}")
    try:
        result = pipeline.extract(image_path, doc_type=doc_type)
        print(result.display())
    except Exception as e:
        print(f"\n  [ERROR] Failed to process {image_path}: {e}\n")


def run_demo(pipeline: Pipeline):
    """Scan sample_documents/ and run on every image found."""
    base = Path(".")
    found_any = False

    for folder, doc_type in _SAMPLE_PATHS:
        folder_path = base / folder
        if not folder_path.exists():
            continue

        images = sorted(
            p for p in folder_path.iterdir()
            if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTS
        )

        if not images:
            continue

        found_any = True
        print(f"\n{'#' * 60}")
        print(f"# Folder: {folder}  [{doc_type.value}]")
        print(f"{'#' * 60}")

        for img_path in images:
            run_single(pipeline, str(img_path), doc_type=doc_type)

    if not found_any:
        print(
            "\n  No sample images found. Add images to sample_documents/ "
            "subfolders and re-run.\n"
        )


def main():
    print("\n" + "=" * 60)
    print("  Driver Document Text Extractor — Version 1")
    print("=" * 60)
    print("\n  Loading OCR engine (first load may take ~30s)...")

    pipeline = Pipeline()

    print("  OCR engine ready.\n")

    args = sys.argv[1:]

    if not args:
        # Default: scan all sample documents
        run_demo(pipeline)

    elif len(args) == 1:
        # Single image, auto-detect
        run_single(pipeline, args[0])

    elif len(args) == 2:
        # Single image + forced type
        image_path = args[0]
        type_str = args[1].lower()
        doc_type = _TYPE_ALIASES.get(type_str)
        if doc_type is None:
            print(f"\n  Unknown document type '{args[1]}'. "
                  f"Valid: {', '.join(_TYPE_ALIASES)}\n")
            sys.exit(1)
        run_single(pipeline, image_path, doc_type=doc_type)

    else:
        print("\n  Usage:")
        print("    python main.py                         # scan all samples")
        print("    python main.py <image_path>            # auto-detect type")
        print("    python main.py <image_path> <type>     # forced type")
        print(f"    Types: {', '.join(_TYPE_ALIASES)}\n")


if __name__ == "__main__":
    main()