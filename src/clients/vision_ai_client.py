import os
from typing import Optional, List
from google.cloud import vision
from google.api_core.exceptions import GoogleAPICallError, RetryError

from src.core.config import settings
from src.core.logger import logger
from src.core.exceptions import VisionApiException
from src.schemas.document_schemas import OCRResult, OCRBlock
from src.utils.image_utils import validate_and_prepare_image, convert_pdf_to_images

class VisionAIClient:
    """
    Dedicated client for Google Cloud Vision API.
    Isolates all direct communication with the Google Vision SDK and provides a clean OCRResult abstraction.
    """
    def __init__(self, client: Optional[vision.ImageAnnotatorClient] = None, timeout: Optional[int] = None):
        self._client = client
        self.timeout = timeout or settings.VISION_TIMEOUT

    @property
    def client(self) -> vision.ImageAnnotatorClient:
        """Lazy-loaded Vision client instance."""
        if self._client is None:
            try:
                if settings.GOOGLE_VISION_API_KEY:
                    from google.api_core.client_options import ClientOptions
                    options = ClientOptions(api_key=settings.GOOGLE_VISION_API_KEY)
                    self._client = vision.ImageAnnotatorClient(client_options=options)
                else:
                    self._client = vision.ImageAnnotatorClient()
            except Exception as e:
                logger.error(f"Failed to initialize Google Cloud Vision client: {e}")
                raise VisionApiException(
                    f"Google Cloud Vision initialization failed: {str(e)}",
                    "VISION_AUTH_OR_CONFIG_ERROR"
                ) from e
        return self._client

    async def extract_text_from_file(self, file_path: str) -> OCRResult:
        """
        Performs OCR text detection on an image or PDF file.
        Returns a structured OCRResult with raw text and blocks.
        """
        if not os.path.exists(file_path):
            raise VisionApiException(f"File not found for OCR: {file_path}", "FILE_NOT_FOUND")

        _, ext = os.path.splitext(file_path.lower())

        # If PDF, extract image pages first
        if ext == ".pdf":
            parent_dir = os.path.dirname(file_path)
            images = convert_pdf_to_images(file_path, os.path.join(parent_dir, "pdf_pages"))
            if not images:
                raise VisionApiException(f"Could not extract images from PDF: {file_path}", "PDF_CONVERSION_FAILED")
            
            combined_texts = []
            all_blocks = []
            for img_path in images:
                res = await self.extract_text_from_file(img_path)
                combined_texts.append(res.raw_text)
                all_blocks.extend(res.blocks)
            
            return OCRResult(
                raw_text="\n".join(combined_texts),
                blocks=all_blocks,
                confidence=1.0
            )

        try:
            image_bytes = validate_and_prepare_image(file_path)
        except Exception as e:
            raise VisionApiException(f"Failed to prepare image for OCR: {e}", "IMAGE_PREPARATION_ERROR") from e

        return await self.extract_text_from_bytes(image_bytes)

    async def extract_text_from_bytes(self, image_bytes: bytes) -> OCRResult:
        """
        Sends prepared image bytes to Google Cloud Vision document_text_detection.
        """
        if not image_bytes:
            raise VisionApiException("Empty image bytes provided for OCR", "EMPTY_IMAGE_BYTES")

        image = vision.Image(content=image_bytes)

        try:
            # document_text_detection is optimized for dense text / identity cards
            response = self.client.document_text_detection(
                image=image,
                timeout=self.timeout
            )

            if response.error.message:
                logger.error(f"Vision API returned an error: {response.error.message}")
                raise VisionApiException(
                    f"Google Vision API error: {response.error.message}",
                    "VISION_API_ERROR"
                )

            raw_text = ""
            blocks: List[OCRBlock] = []
            confidences: List[float] = []

            # Check full text annotation
            if response.full_text_annotation:
                raw_text = response.full_text_annotation.text or ""
                for page in response.full_text_annotation.pages:
                    for block in page.blocks:
                        block_text = ""
                        for paragraph in block.paragraphs:
                            for word in paragraph.words:
                                word_text = "".join(symbol.text for symbol in word.symbols)
                                block_text += word_text + " "
                        
                        b_text_stripped = block_text.strip()
                        if b_text_stripped:
                            conf = getattr(block, "confidence", 1.0)
                            if conf:
                                confidences.append(conf)
                            
                            vertices = []
                            if block.bounding_box and block.bounding_box.vertices:
                                vertices = [[v.x, v.y] for v in block.bounding_box.vertices]

                            blocks.append(OCRBlock(
                                text=b_text_stripped,
                                confidence=conf,
                                bounding_box=vertices if vertices else None
                            ))

            elif response.text_annotations:
                # Fallback to standard text annotations
                raw_text = response.text_annotations[0].description or ""

            avg_confidence = (sum(confidences) / len(confidences)) if confidences else (1.0 if raw_text else 0.0)

            logger.info(f"Vision OCR completed. Extracted {len(raw_text)} characters, {len(blocks)} blocks.")
            return OCRResult(
                raw_text=raw_text,
                blocks=blocks,
                confidence=round(avg_confidence, 3)
            )

        except (GoogleAPICallError, RetryError) as e:
            logger.error(f"Google Vision API communication error: {e}")
            raise VisionApiException(
                f"Google Vision API failed: {str(e)}",
                "VISION_COMMUNICATION_ERROR"
            ) from e
        except Exception as e:
            if isinstance(e, VisionApiException):
                raise
            logger.error(f"Unexpected error during Vision OCR: {e}")
            raise VisionApiException(f"Unexpected OCR processing error: {e}", "UNEXPECTED_OCR_ERROR") from e

# Default singleton instance
vision_ai_client = VisionAIClient()
