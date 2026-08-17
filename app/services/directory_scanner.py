"""
Directory Scanner Service
========================
Scans document directories to discover driver folders, document folders,
and front/back image pairs while maintaining strict processing order:
Aadhaar → Driving Licence → PAN → RC Book.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from app.config.settings import settings
from app.services.doc_type_detector import DocumentType

SUPPORTED_IMAGE_EXTS = settings.SUPPORTED_IMAGE_EXTENSIONS

MANDATORY_DOC_ORDER = [
    DocumentType.AADHAAR,
    DocumentType.DRIVING_LICENCE,
    DocumentType.PAN,
    DocumentType.RC,
]

# Keywords used to match document subfolder names
_DOC_FOLDER_PATTERNS: Dict[DocumentType, List[str]] = {
    DocumentType.AADHAAR: ["aadhaar", "aadhar", "adhaar", "uidai"],
    DocumentType.DRIVING_LICENCE: ["licence", "license", "driving", "dl"],
    DocumentType.PAN: ["pan_card", "pan"],
    DocumentType.RC: ["rc_book", "rc_card", "rc"],
}


@dataclass
class DocumentFilesSpec:
    """Document folder details including front and back image file paths."""
    doc_type: DocumentType
    folder_path: Optional[str] = None
    front_path: Optional[str] = None
    back_path: Optional[str] = None

    @property
    def is_missing(self) -> bool:
        return self.front_path is None and self.back_path is None


@dataclass
class DriverFolderSpec:
    """Specification of a single driver directory and its documents."""
    driver_id: str
    driver_path: str
    documents: Dict[DocumentType, DocumentFilesSpec] = field(default_factory=dict)

    def get_document_spec(self, doc_type: DocumentType) -> DocumentFilesSpec:
        return self.documents.get(doc_type, DocumentFilesSpec(doc_type=doc_type))


class DirectoryScanner:
    """Discovers and validates driver directory structures."""

    def scan_all_drivers(self, base_dir: Optional[str] = None) -> List[DriverFolderSpec]:
        """
        Scan base directory for all driver folders and return specifications
        in driver-by-driver order.
        """
        target_dir = base_dir or settings.SAMPLE_DOCUMENTS_DIR
        base_path = Path(target_dir)
        if not base_path.exists() or not base_path.is_dir():
            return []

        subdirs = sorted([p for p in base_path.iterdir() if p.is_file() == False])
        driver_specs: List[DriverFolderSpec] = []

        for p in subdirs:
            # Check if this folder contains document subfolders or is a driver folder
            spec = self.scan_driver_folder(str(p))
            # Verify if spec discovered any valid documents or matches driver pattern
            if any(not d.is_missing for d in spec.documents.values()) or p.name.startswith("DRIVER_") or p.name.isdigit():
                driver_specs.append(spec)

        return driver_specs

    def scan_driver_folder(self, driver_folder_path: str) -> DriverFolderSpec:
        """
        Scan a single driver directory for document folders.
        Guarantees exact processing order: Aadhaar → Licence → PAN → RC.
        """
        driver_path = Path(driver_folder_path)
        driver_id = driver_path.name

        doc_specs: Dict[DocumentType, DocumentFilesSpec] = {}
        child_dirs = [p for p in driver_path.iterdir() if p.is_dir()]

        for doc_type in MANDATORY_DOC_ORDER:
            patterns = _DOC_FOLDER_PATTERNS[doc_type]
            matched_dir: Optional[Path] = None

            # Find matching directory for this doc_type
            for child in child_dirs:
                folder_name_lower = child.name.lower()
                if any(pat in folder_name_lower for pat in patterns):
                    matched_dir = child
                    break

            if matched_dir is not None:
                front_path, back_path = self._find_front_back_images(matched_dir)
                doc_specs[doc_type] = DocumentFilesSpec(
                    doc_type=doc_type,
                    folder_path=str(matched_dir),
                    front_path=front_path,
                    back_path=back_path,
                )
            else:
                doc_specs[doc_type] = DocumentFilesSpec(doc_type=doc_type)

        return DriverFolderSpec(
            driver_id=driver_id,
            driver_path=str(driver_path),
            documents=doc_specs,
        )

    def _find_front_back_images(self, folder: Path) -> Tuple[Optional[str], Optional[str]]:
        """Locate front and back images within a document subfolder."""
        images = sorted([
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTS
        ])

        if not images:
            return None, None

        front_img: Optional[Path] = None
        back_img: Optional[Path] = None

        # 1. Check explicitly for filenames containing 'front' or 'back'
        for img in images:
            stem = img.stem.lower()
            if "front" in stem and front_img is None:
                front_img = img
            elif "back" in stem and back_img is None:
                back_img = img

        # 2. Fallback: assign first image as front, second as back if available
        remaining = [img for img in images if img != front_img and img != back_img]

        if front_img is None and remaining:
            front_img = remaining.pop(0)

        if back_img is None and remaining:
            back_img = remaining.pop(0)

        return (
            str(front_img) if front_img else None,
            str(back_img) if back_img else None,
        )
