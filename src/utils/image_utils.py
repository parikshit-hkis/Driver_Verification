import os
from typing import List
from PIL import Image
import io

from src.core.logger import logger

def validate_and_prepare_image(file_path: str) -> bytes:
    """
    Validates that a file is a readable image and returns bytes optimized for Vision OCR.
    Handles basic orientation (EXIF) and RGB format conversion.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Image file not found: {file_path}")

    with Image.open(file_path) as img:
        # Auto-rotate according to EXIF orientation tag if present
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Convert palette/RGBA images to RGB
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        return buffer.getvalue()

def convert_pdf_to_images(pdf_path: str, output_dir: str) -> List[str]:
    """
    Extracts pages from a PDF document and saves them as images for OCR processing.
    Falls back to pypdf embedded image extraction if pdf2image/poppler is unavailable.
    """
    image_paths: List[str] = []
    os.makedirs(output_dir, exist_ok=True)

    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        for page_idx, page in enumerate(reader.pages):
            for img_idx, image_file_object in enumerate(page.images):
                img_path = os.path.join(output_dir, f"page_{page_idx}_img_{img_idx}.png")
                with open(img_path, "wb") as fp:
                    fp.write(image_file_object.data)
                image_paths.append(img_path)
    except Exception as e:
        logger.error(f"Error extracting images from PDF {pdf_path}: {e}")

    return image_paths
