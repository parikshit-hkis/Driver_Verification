# Driver Document Verification — Text Extractor Architecture & Documentation

Welcome to the technical documentation for **Driver Document Verification System (Version 1)**.

This system is an automated text extraction and normalization pipeline designed for ride-hailing driver onboarding (Rapido, Ola, Uber style). It processes images of Indian identity and vehicle documents (**Aadhaar Card**, **PAN Card**, **Driving Licence**, and **Registration Certificate / RC**) under any real-world image condition and outputs clean, structured, standardized data.

---

## 📌 Table of Contents

1. [System Architecture & Data Flow](#1-system-architecture--data-flow)
2. [Directory & File Structure](#2-directory--file-structure)
3. [Deep-Dive File & Function Reference](#3-deep-dive-file--function-reference)
   - [3.1 Main Entry Point & Pipeline](#31-main-entry-point--pipeline)
   - [3.2 Data Models](#32-data-models)
   - [3.3 Preprocessing & OCR Engine](#33-preprocessing--ocr-engine)
   - [3.4 Utilities & Normalizers](#34-utilities--normalizers)
   - [3.5 Document Type Detector](#35-document-type-detector)
   - [3.6 Extractor Services](#36-extractor-services)
     - [Base Extractor](#base-extractor)
     - [Aadhaar Extractor](#aadhaar-extractor)
     - [PAN Extractor](#pan-extractor)
     - [Driving Licence Extractor](#driving-licence-extractor)
     - [RC Extractor](#rc-extractor)
4. [Document Extraction Specifications](#4-document-extraction-specifications)
5. [Usage & Execution Guide](#5-usage--execution-guide)

---

## 1. System Architecture & Data Flow

The pipeline operates in 5 deterministic, decoupled steps:

```
                  ┌────────────────────────────────────────┐
                  │          Input Document Image          │
                  │ (File Path / Bytes / Base64 / URL / PIL) │
                  └───────────────────┬────────────────────┘
                                      │
                                      ▼
    STEP 1: Image Preprocessing (app/ocr/preprocessor.py)
    ├── EXIF Orientation Fix (phone photos)
    ├── Document 90°/180°/270° Rotation Correction (Projection Profile Variance)
    ├── Skew Angle Correction (Hough Line Transform)
    ├── Quality Assessment (Blur, Brightness, Glare detection)
    └── Image Enhancement (CLAHE + Gamma correction for low-contrast/dark images)
                                      │
                                      ▼
    STEP 2: OCR Engine (app/ocr/paddle_ocr.py)
    ├── PaddleOCR with Text Angle Classifier (`use_angle_cls=True`)
    ├── Extracts bounding boxes (polygon points), confidence scores, text lines
    └── Sorts text boxes top-to-bottom, left-to-right
                                      │
                                      ▼
    STEP 3: Document Type Classification (app/services/doc_type_detector.py)
    └── Keyword-scoring algorithm across OCR texts -> AADHAAR | PAN | DRIVING_LICENCE | RC
                                      │
                                      ▼
    STEP 4: Structured Extraction (app/services/*_extractor/extractor.py)
    ├── Label-Proximity Bounding-Box Matching (find value boxes relative to label anchors)
    ├── Inline Label-Value Parsing (handles merged OCR text lines e.g. "Name:RAJ V CHHATRALA")
    └── Document-Specific Regex & Heuristic Fallbacks
                                      │
                                      ▼
    STEP 5: Normalization (app/utils/normalizer.py)
    ├── Standardizes Dates → ISO format (YYYY-MM-DD)
    ├── Name Parsing & Splitting → (First Name = Surname, Middle Name = Given Name, Last Name = Father/Initial)
    └── Formats Document Numbers → Aadhaar (XXXX XXXX XXXX), DL (GJ-RR-YYYY-NNNNNNN), RC (GJ-RR-XX-NNNN)
                                      │
                                      ▼
                  ┌────────────────────────────────────────┐
                  │       ExtractionResult Object          │
                  │ ├── document_type                      │
                  │ ├── data (AadhaarData/PanData/etc.)    │
                  │ ├── quality_report                     │
                  │ └── ocr_result                         │
                  └────────────────────────────────────────┘
```

---

## 2. Directory & File Structure

```
Driver_Verification/
│
├── main.py                                  # CLI runner & demo executor
├── requirements.txt                         # Dependencies (PaddleOCR, OpenCV, Pillow, etc.)
├── a.md                                     # Project plan & pipeline notes
├── chat_summary.md                          # Decisions & architectural choices summary
├── text_extract.md                          # Required document field extraction spec
├── PROJECT_DOCUMENTATION.md                 # This complete system documentation
│
└── app/                                     # Core application package
    ├── __init__.py
    ├── pipeline.py                          # Unified extraction pipeline orchestrator
    │
    ├── models/                              # Data contracts & Pydantic models
    │   └── ocr_models.py                    # Point, BoundingBox, OCRText, OCRResult, ImageQualityReport
    │
    ├── ocr/                                 # OCR & Computer Vision package
    │   ├── __init__.py
    │   ├── preprocessor.py                  # Image loading, rotation, deskew, quality, CLAHE
    │   └── paddle_ocr.py                    # PaddleOCR service wrapper
    │
    ├── utils/                               # Shared utilities
    │   ├── __init__.py
    │   └── normalizer.py                    # Date, name, and document number normalizers
    │
    └── services/                            # Extractor domain services
        ├── __init__.py
        ├── base_extractor.py                # Base class with label-proximity geometry helpers
        ├── doc_type_detector.py             # Automatic document type classifier
        │
        ├── aadhaar_extractor/               # Aadhaar Card service
        │   ├── __init__.py
        │   ├── extractor.py                 # AadhaarExtractor implementation
        │   └── models.py                    # AadhaarData model
        │
        ├── pan_extractor/                   # PAN Card service
        │   ├── __init__.py
        │   ├── extractor.py                 # PanExtractor implementation
        │   └── models.py                    # PanData model
        │
        ├── driving_license_extractor/       # Driving Licence service
        │   ├── __init__.py
        │   ├── extractor.py                 # DrivingLicenceExtractor & parse_dl_name
        │   └── models.py                    # DrivingLicenceData model
        │
        └── rc_extractor/                    # Vehicle Registration Certificate service
            ├── __init__.py
            ├── extractor.py                 # RCExtractor implementation
            └── models.py                    # RCData model
```

---

## 3. Deep-Dive File & Function Reference

### 3.1 Main Entry Point & Pipeline

#### `main.py`
The CLI runner that demonstrates image processing and extraction.
- **`run_single(pipeline: Pipeline, image_path: str, doc_type=None)`**: Executes the pipeline on a single image and prints formatted results.
- **`run_demo(pipeline: Pipeline)`**: Automatically scans `sample_documents/` directories for test images across all document types.
- **`main()`**: CLI argument parser. Accepts 0 arguments (demo run), 1 argument (image path with auto-detect), or 2 arguments (image path + forced document type alias `aadhaar`, `pan`, `dl`, `rc`).

#### `app/pipeline.py`
The central orchestrator connecting all system components.
- **`class ExtractionResult`**: Dataclass holding `document_type`, `data`, `quality_report`, and `ocr_result`. Features a `.display()` method for clean console output.
- **`class Pipeline`**: Stateful service object initializing `ImagePreprocessor`, `PaddleOCRService`, `DocTypeDetector`, and individual extractors.
  - **`extract(image_input, doc_type=None, fix_orientation=True, enhance=True) -> ExtractionResult`**: Accepts any image input (filepath, numpy array, bytes, base64, URL), executes preprocessing, runs OCR, detects document type if omitted, extracts & normalizes structured fields, and returns `ExtractionResult`.

---

### 3.2 Data Models

#### `app/models/ocr_models.py`
Defines geometric primitives, OCR contracts, and image quality evaluation structures.
- **`Point(BaseModel)`**: 2D coordinate `(x, y)`.
- **`BoundingBox(BaseModel)`**: List of 4 `Point` objects representing bounding polygon. Properties: `min_x`, `max_x`, `min_y`, `max_y`, `center_x`, `center_y`, `width`, `height`.
- **`OCRText(BaseModel)`**: Represents a single recognized text element containing `text: str`, `confidence: float`, and `bounding_box: BoundingBox`.
- **`OCRResult(BaseModel)`**: Holds `full_text: str` and `texts: List[OCRText]`.
- **`ImageQualityReport(dataclass)`**: Tracks image health metrics:
  - `blur_score`: Laplacian variance (scores < 80 flagged blurry).
  - `brightness`: Mean pixel intensity (dark < 55, overexposed > 215).
  - `glare_percentage`: % of pixels > 250 brightness.
  - `rotation_applied`: 0°, 90°, 180°, 270°.
  - `skew_corrected`: Deskew angle applied.
  - `was_enhanced`: True if CLAHE / gamma correction applied.
  - `.summary()`: Human-readable quality report output.

---

### 3.3 Preprocessing & OCR Engine

#### `app/ocr/preprocessor.py`
Implements computer vision routines to handle any real-world user photo condition.
- **`class ImagePreprocessor`**:
  - **`preprocess(image_input, fix_orientation=True, enhance=True) -> (np.ndarray, ImageQualityReport)`**: Main entry point returning preprocessed BGR numpy array and quality metrics report.
  - **`_load_image(image_input)`**: Universal loader converting file path, raw bytes, base64 string, URL, PIL Image, or BGR numpy array into a standardized BGR numpy array.
  - **`_fix_exif_orientation(original_input, img)`**: Rotates image based on camera EXIF tags (e.g. smartphone portrait/landscape orientation).
  - **`_correct_document_rotation(img) -> (np.ndarray, int)`**: Evaluates horizontal projection profile variance across 0°, 90°, 180°, 270° angles to align document text horizontally without needing OCR.
  - **`_correct_skew(img) -> (np.ndarray, float)`**: Detects small skew angles using Hough Line Transform and deskews using affine rotation warp.
  - **`_laplacian_score(img)`**: Calculates focus sharpness via Laplacian operator variance.
  - **`_mean_brightness(img)`**: Calculates average luminosity.
  - **`_glare_percent(img)`**: Calculates ratio of saturated white pixels.
  - **`_enhance(img, report)`**: Applies CLAHE (Contrast Limited Adaptive Histogram Equalization) on L channel (in LAB color space) and gamma transformation to restore dark/glared images.

#### `app/ocr/paddle_ocr.py`
- **`class PaddleOCRService`**:
  - **`__init__()`**: Instantiates PaddleOCR engine with `use_angle_cls=True` (text line angle classifier enabled) and `lang="en"`.
  - **`extract(image_input) -> OCRResult`**: Executes OCR on image path or numpy array, builds `OCRText` list with bounding boxes and confidence scores, and sorts boxes top-to-bottom, left-to-right.

---

### 3.4 Utilities & Normalizers

#### `app/utils/normalizer.py`
Standardizes extracted strings into structured formats.
- **Date Functions**:
  - **`normalize_dob(text: str)` / `normalize_date(text: str) -> Optional[str]`**: Converts DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD, DD Mon YYYY into ISO `YYYY-MM-DD`.
- **Name Functions**:
  - **`normalize_name(text: str) -> Dict[str, Optional[str]]`**: General Indian name splitter:
    - 2 words: `first_name` = Word 0, `middle_name` = Word 1, `last_name` = None
    - 3 words: `first_name` = Word 0, `middle_name` = Word 1, `last_name` = Word 2
- **Document Number Functions**:
  - **`normalize_aadhaar_number(text) -> Optional[str]`**: Formats 12 digits as `XXXX XXXX XXXX`.
  - **`normalize_pan_number(text) -> Optional[str]`**: Validates and returns uppercase 10-char `AAAAA9999A`.
  - **`normalize_dl_number(text) -> Optional[str]`**: Standardizes Gujarat DL format `GJ-RR-YYYY-NNNNNNN`.
  - **`normalize_rc_number(text) -> Optional[str]`**: Standardizes Gujarat RC format `GJ-RR-XX-NNNN`.

---

### 3.5 Document Type Detector

#### `app/services/doc_type_detector.py`
- **`enum DocumentType(str, Enum)`**: `AADHAAR`, `PAN`, `DRIVING_LICENCE`, `RC`, `UNKNOWN`.
- **`class DocTypeDetector`**:
  - **`detect(texts: List[OCRText]) -> DocumentType`**: Scores distinctive keyword hits per document type (including English, Hindi, and Gujarati Aadhaar keywords, DL vehicle class codes, RC chassis/reg labels) and returns the highest scoring document type.

---

### 3.6 Extractor Services

#### Base Extractor (`app/services/base_extractor.py`)
- **`class BaseExtractor`**: Shared base class providing spatial geometry methods.
  - **`find_value_near_label(texts, label_keywords, direction="auto", max_distance=400, same_row_tolerance=18) -> Optional[str]`**: Finds the nearest OCR text box relative to a label bounding box. `direction="right"` searches horizontally, `"below"` searches vertically, `"auto"` evaluates right first, then below.
  - **`find_values_near_label(texts, label_keywords, top_n=3)`**: Multi-value proximity search for table rows.
  - **`find_by_regex(texts, pattern)`**: Helper to search regex across text elements.
  - **`_find_label_box(texts, keywords)`**: Locates the OCR bounding box containing any of the specified target label strings.

---

#### Aadhaar Extractor (`app/services/aadhaar_extractor/`)
- **`models.py`**:
  - **`AadhaarData(BaseModel)`**: Fields: `aadhaar_number`, `full_name`, `first_name`, `middle_name`, `last_name`, `dob`, `gender`, `address`. Has `.display()` method.
- **`extractor.py`**:
  - **`class AadhaarExtractor(BaseExtractor)`**:
    - **`extract_aadhaar_number(texts)`**: Extracts 12-digit number (handles spaced, hyphenated, compact formats; ignores masked `XXXX` numbers).
    - **`extract_dob(texts)`**: Prioritizes inline `"DOB: DD/MM/YYYY"`, label proximity, and applies a plausible year range filter (1930–2015) to prevent misidentifying issue/enrollment dates.
    - **`extract_gender(texts)`**: Detects `MALE`, `FEMALE`, `TRANSGENDER` in English, Hindi (पुरुष/महिला), or Gujarati (પુરુષ/સ્ત્રી).
    - **`extract_name_raw(texts)`**: Uses label proximity near `"Name"`/`"नाम"` or multi-word alphabetic heuristic filtered against a domain blacklist.
    - **`extract_address(texts)`**: Extracts multi-line address from back side of card, filtering out metadata headers (`"Details as on:"`) and deduplicating lines.

---

#### PAN Extractor (`app/services/pan_extractor/`)
- **`models.py`**:
  - **`PanData(BaseModel)`**: Fields: `pan_number`, `full_name`, `first_name`, `middle_name`, `last_name`, `father_name`, `dob`.
- **`extractor.py`**:
  - **`class PanExtractor(BaseExtractor)`**:
    - **`extract_pan_number(texts)`**: Extracts 10-character `AAAAA9999A` pattern.
    - **`extract_name_raw(texts)`**: Uses below-label proximity (since PAN cards place values directly below `"Name"` label) and positional scanning between Name label and Father's Name section.
    - **`extract_father_name_raw(texts)`**: Extracts text below `"Father's Name"` label.
    - **`extract_dob(texts)`**: Extracts DOB date near `"Date of Birth"` label.
    - Uses **word-level blacklist matching** (preventing substring collisions such as `"pan"` matching `"PANCHAL"`).

---

#### Driving Licence Extractor (`app/services/driving_license_extractor/`)
- **`models.py`**:
  - **`DrivingLicenceData(BaseModel)`**: Fields: `licence_number`, `full_name`, `first_name`, `middle_name`, `last_name`, `dob`, `blood_group`, `issue_date`, `expiry_date`, `issuing_authority`, `vehicle_classes: List[str]`.
- **`extractor.py`**:
  - **`parse_dl_name(name_str: str) -> dict`**: Specialized name parser supporting both Smart Card and booklet DL formats. Incorporates a Gujarati surname dictionary (`CHHATRALA`, `PANCHAL`, `PARIKH`, `PATEL`, `DESAI`, etc.) and handles OCR concatenated strings (`RAIVCHHATRALA` $\rightarrow$ `Raj V Chhatrala`). Maps name fields as requested:
    - **`first_name`** = **Surname** (e.g. `Panchal` / `Chhatrala`)
    - **`middle_name`** = **Given Name** (e.g. `Parikshit` / `Raj`)
    - **`last_name`** = **Father Name / Initial** (e.g. `K` / `V` / `Kamleshbhai`)
  - **`class DrivingLicenceExtractor(BaseExtractor)`**:
    - **`extract_licence_number(texts)`**: Extracts `GJ-RR-YYYY-NNNNNNN` format.
    - **`extract_dob(texts)`**: Handles inline merged strings (e.g. `Date Of Birta8-02-2006`) and label proximity.
    - **`extract_name_raw(texts)`**: Handles single OCR boxes with inline prefixes (`Name:RAIVCHHATRALA`), label proximity, and text above `Son/Daughter/` labels. Automatically strips `Name:` prefixes.
    - **`extract_issue_date(texts)`**: Searches directly below `"Issue Date"` / `"Date Of First Issue"` label boxes.
    - **`extract_expiry_date(texts)`**: Searches directly below `"ValidityNT"` / `"Validity"` headers or selects the future date with the latest year.
    - **`extract_vehicle_classes(texts)`**: Extracts all authorized category codes (`LMV`, `MCWG`, `HMV`, `TRANS`, etc.).
    - **`extract_blood_group(texts)`**: Extracts blood groups (`A+`, `B+`, `O+`, `AB+`, etc.).
    - **`extract_issuing_authority(texts)`**: Extracts RTO/ARTO office name (e.g. `ARTO BOTAD`).

---

#### RC Extractor (`app/services/rc_extractor/`)
- **`models.py`**:
  - **`RCData(BaseModel)`**: Fields: `registration_number`, `owner_name`, `vehicle_class`, `vehicle_type`, `fuel_type`, `manufacturer`, `model`, `chassis_number`, `engine_number`, `date_of_registration`, `registration_validity`, `fitness_validity`, `insurance_validity`, `tax_validity`, `issuing_rto`.
- **`extractor.py`**:
  - **`class RCExtractor(BaseExtractor)`**:
    - **`extract_registration_number(texts)`**: Extracts Gujarat RC format `GJ-RR-XX-NNNN`.
    - **`extract_owner_name(texts)`**: Extracts owner name near `"Name of Owner"` / `"Owner Name"` labels.
    - **`extract_vehicle_class(texts)` / `extract_vehicle_type(texts)`**: Extracts vehicle class (e.g. `LMV-CAR`) and type (`MOTOR CAR`).
    - **`extract_fuel_type(texts)`**: Standardizes fuel types (`PETROL`, `DIESEL`, `CNG`, `ELECTRIC`, `PETROL+CNG`).
    - **`extract_manufacturer(texts)` / `extract_model(texts)`**: Extracts maker and model name.
    - **`extract_chassis_number(texts)` / `extract_engine_number(texts)`**: Extracts 17-char VIN chassis number and engine number.
    - **`extract_date_of_registration` / `extract_registration_validity` / `extract_fitness_validity` / `extract_insurance_validity`**: Normalizes all validity dates to ISO `YYYY-MM-DD`.

---

## 4. Document Extraction Specifications

| Document Type | Required Fields Extracted | Format / Normalization Applied |
|---|---|---|
| **Aadhaar Card** | Full Name, First Name, Middle Name, Last Name, Aadhaar Number, DOB, Gender, Address | Number: `XXXX XXXX XXXX`<br>DOB: `YYYY-MM-DD`<br>Name: Split to First, Middle, Last |
| **PAN Card** | Full Name, First Name, Middle Name, Last Name, Father Name, PAN Number, DOB | Number: `AAAAA9999A`<br>DOB: `YYYY-MM-DD` |
| **Driving Licence** | Full Name, First Name, Middle Name, Last Name, Licence Number, DOB, Issue Date, Expiry Date, Vehicle Classes, Blood Group, Issuing Authority | Number: `GJ-RR-YYYY-NNNNNNN`<br>Dates: `YYYY-MM-DD`<br>First Name: Surname<br>Middle Name: Given Name<br>Last Name: Father/Initial |
| **RC (Registration Certificate)** | Registration Number, Owner Name, Vehicle Class, Vehicle Type, Fuel Type, Manufacturer, Model, Chassis No, Engine No, Reg Date, Reg Validity, Fitness Validity, Insurance Validity, RTO | Number: `GJ-RR-XX-NNNN`<br>Dates: `YYYY-MM-DD`<br>Fuel: Standardized |

---

## 5. Usage & Execution Guide

### Prerequisites & Dependencies
Install requirements into your Python environment:
```bash
pip install paddlepaddle==2.6.2 paddleocr==2.9.1 pydantic opencv-python numpy pillow python-dateutil rapidfuzz
```

### Running CLI Commands

1. **Auto-scan sample documents**:
   ```bash
   python main.py
   ```

2. **Process a single image with auto-detection**:
   ```bash
   python main.py sample_documents/aadhaar_card/front/001.jpg
   ```

3. **Process a single image with forced document type**:
   ```bash
   python main.py sample_documents/licence/front/001.jpeg licence
   python main.py sample_documents/pan_card/front/001.jpeg pan
   python main.py sample_documents/aadhaar_card/front/001.jpg aadhaar
   python main.py sample_documents/RC/001.jpg rc
   ```

### Programmatic Python Usage

```python
from app.pipeline import Pipeline
from app.services.doc_type_detector import DocumentType

# Initialize pipeline once (loads OCR model)
pipeline = Pipeline()

# Extract from file path (auto-detect type)
result = pipeline.extract("path/to/document.jpg")

# Print formatted report
print(result.display())

# Access structured data directly
print(result.document_type)          # DocumentType.DRIVING_LICENCE
print(result.data.full_name)          # "Parikshit K Panchal"
print(result.data.first_name)         # "Panchal" (Surname)
print(result.data.middle_name)        # "Parikshit" (Given Name)
print(result.data.last_name)          # "K" (Initial)
print(result.data.licence_number)     # "GJ-33-2025-0000811"
print(result.quality_report.summary())
```
