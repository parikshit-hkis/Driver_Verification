import pytest
from unittest.mock import MagicMock
from PIL import Image
import io

from src.clients.vision_ai_client import VisionAIClient
from src.core.exceptions import VisionApiException
from src.utils.image_utils import validate_and_prepare_image

def create_mock_vision_response(text: str, has_blocks: bool = True, error_msg: str = ""):
    mock_response = MagicMock()
    mock_response.error.message = error_msg

    if has_blocks:
        mock_response.full_text_annotation.text = text
        mock_page = MagicMock()
        mock_block = MagicMock()
        mock_block.confidence = 0.98
        mock_block.bounding_box.vertices = [
            MagicMock(x=10, y=10),
            MagicMock(x=100, y=10),
            MagicMock(x=100, y=50),
            MagicMock(x=10, y=50),
        ]
        
        # Word symbols for block text
        mock_para = MagicMock()
        mock_word = MagicMock()
        mock_word.symbols = [MagicMock(text=c) for c in text.split()[0]] if text else []
        mock_para.words = [mock_word]
        mock_block.paragraphs = [mock_para]
        
        mock_page.blocks = [mock_block]
        mock_response.full_text_annotation.pages = [mock_page]
    else:
        mock_response.full_text_annotation = None
        mock_annotation = MagicMock()
        mock_annotation.description = text
        mock_response.text_annotations = [mock_annotation]

    return mock_response

@pytest.mark.asyncio
async def test_extract_text_success_full_text():
    mock_vision_sdk = MagicMock()
    mock_vision_sdk.document_text_detection.return_value = create_mock_vision_response(
        "GOVERNMENT OF INDIA\nPARIKSHIT PANCHAL\nDOB: 01/01/1990"
    )

    client = VisionAIClient(client=mock_vision_sdk)
    result = await client.extract_text_from_bytes(b"dummy_image_bytes")

    assert "PARIKSHIT PANCHAL" in result.raw_text
    assert result.confidence > 0.9
    assert len(result.blocks) >= 1
    assert result.blocks[0].bounding_box == [[10, 10], [100, 10], [100, 50], [10, 50]]

@pytest.mark.asyncio
async def test_extract_text_fallback_annotation():
    mock_vision_sdk = MagicMock()
    mock_vision_sdk.document_text_detection.return_value = create_mock_vision_response(
        "INCOME TAX DEPARTMENT\nPAN: ABCDE1234F",
        has_blocks=False
    )

    client = VisionAIClient(client=mock_vision_sdk)
    result = await client.extract_text_from_bytes(b"dummy_image_bytes")

    assert "ABCDE1234F" in result.raw_text

@pytest.mark.asyncio
async def test_vision_api_error_response_raises_exception():
    mock_vision_sdk = MagicMock()
    mock_vision_sdk.document_text_detection.return_value = create_mock_vision_response(
        "", error_msg="Image format not supported by Vision API"
    )

    client = VisionAIClient(client=mock_vision_sdk)
    with pytest.raises(VisionApiException) as exc_info:
        await client.extract_text_from_bytes(b"bad_bytes")
    assert "VISION_API_ERROR" in exc_info.value.error_code

@pytest.mark.asyncio
async def test_empty_bytes_raises_exception():
    mock_vision_sdk = MagicMock()
    client = VisionAIClient(client=mock_vision_sdk)
    with pytest.raises(VisionApiException) as exc_info:
        await client.extract_text_from_bytes(b"")
    assert "EMPTY_IMAGE_BYTES" in exc_info.value.error_code

def test_validate_and_prepare_image(tmp_path):
    img_path = str(tmp_path / "sample.png")
    # Create simple RGBA test image
    img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
    img.save(img_path)

    prepared_bytes = validate_and_prepare_image(img_path)
    assert len(prepared_bytes) > 0
    # Verify resulting bytes can be opened as JPEG
    with Image.open(io.BytesIO(prepared_bytes)) as result_img:
        assert result_img.format == "JPEG"
        assert result_img.mode == "RGB"
