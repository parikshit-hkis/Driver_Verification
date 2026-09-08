# Driver Document Verification — Implementation Plan

## 1. Project Objective

Build a **Single-Service Driver Document Verification Microservice** using FastAPI that exposes two primary endpoints:

1. **Single Driver Verification API** (`POST /api/v1/verify-driver`): Synchronously verifies a single driver payload.
2. **Concurrent Batch Verification API** (`POST /api/v1/batch-verify`): Receives multiple drivers in a single request and processes them **simultaneously** using asynchronous concurrency pools (`asyncio.gather` + `asyncio.Semaphore`) to dramatically reduce total turnaround time for high-volume partner onboarding batches.

In a modern distributed platform, this service functions as an autonomous microservice consumed by upstream clients (e.g. Partner Onboarding API, API Gateway, Admin Portals).

Each driver payload contains:

- `driver_id`
- `mobile_number`
- `vehicle_class`
- Password-protected ZIP URLs for:
  - Aadhaar
  - Driving Licence
  - PAN
  - RC

Example Driver Object:

```json
{
  "driver_id": "partner-59820",
  "mobile_number": "3335616616",
  "vehicle_class": "2 wheeler",
  "aadhaar_zip_url": "https://...",
  "licence_zip_url": "https://...",
  "pan_zip_url": "https://...",
  "rc_zip_url": "https://..."
}
```

The microservice performs the complete verification workflow:

1. Download ZIP files from the provided URLs.
2. Use `mobile_number` as the ZIP password.
3. Extract documents/images.
4. Send extracted images to **Google Cloud Vision API**.
5. Extract OCR text.
6. Identify and organize document fields.
7. Normalize extracted values.
8. Cross-verify:
   - Aadhaar name ↔ PAN name
   - Aadhaar name ↔ Driving Licence name
   - RC vehicle class ↔ API-provided vehicle class
9. Produce a final verification result.
10. Return a deterministic JSON response:
   - `VERIFIED`
   - `REJECTED`
   - `ERROR`
   - In batch mode: Return an aggregated summary (`total_count`, `verified_count`, `rejected_count`, `error_count`) plus per-driver result objects with individual failure isolation.

---

# 2. Single-Microservice Architecture

Build the system as a **Single Dedicated Microservice** (`document-verification-service`).

In a distributed backend ecosystem, this service operates as an autonomous, containerized microservice that handles driver document verification end-to-end.

> [!IMPORTANT]
> **Zero Internal Network Hops (Single-Service Runtime)**:
> While this system is a microservice within the broader ecosystem, it is **NOT internally micro-fragmented**. Avoid creating separate distributed microservices for OCR, Aadhaar parsing, PAN extraction, or validation (which introduces network latency, serialization overhead, and distributed failure points). All five processing stages (Ingestion → Vision AI OCR → Extraction → Normalization → Cross-Verification) execute within this single, unified microservice runtime.

```text
document-verification-service/
│
├── deploy/                              # Deployment & container manifests
│   ├── Dockerfile                       # Multi-stage container build
│   ├── docker-compose.yml               # Local testing environment
│   └── k8s-deployment.yaml              # Kubernetes deployment & service spec
│
├── src/                                 # Microservice application source
│   ├── main.py                          # FastAPI app initialization, middleware & events
│   │
│   ├── api/                             # Ingress layer (API Gateway / Client facing)
│   │   ├── dependencies.py              # Auth, rate limiting & request validators
│   │   └── v1/
│   │       ├── router.py                # Main v1 router
│   │       └── endpoints/
│   │           ├── verification.py      # POST /api/v1/verify-driver
│   │           └── health.py            # GET /health, GET /ready, GET /metrics
│   │
│   ├── clients/                         # External network & cloud clients
│   │   ├── vision_ai_client.py          # Google Cloud Vision API client (OCR)
│   │   └── s3_download_client.py        # Secure presigned S3 downloader
│   │
│   ├── extraction/                      # Document extraction & parsing
│   │   ├── zip_extractor.py             # Password-protected ZIP unpacker
│   │   ├── document_classifier.py       # Identifies doc type (Aadhaar, PAN, DL, RC)
│   │   └── extractors/
│   │       ├── base_extractor.py        # Abstract base parser
│   │       ├── aadhaar_extractor.py     # Aadhaar OCR text extraction & regex
│   │       ├── pan_extractor.py         # PAN OCR text extraction & regex
│   │       ├── licence_extractor.py     # Driving licence OCR text extraction
│   │       └── rc_extractor.py          # Registration Certificate (RC) extraction
│   │
│   ├── normalization/                   # Text & entity normalization
│   │   ├── name_normalizer.py           # Standardizes names (casing, initials, noise)
│   │   ├── vehicle_normalizer.py        # Maps vehicle classes (e.g. MCWG -> 2 wheeler)
│   │   └── date_normalizer.py           # Standardizes dates to ISO formats
│   │
│   ├── verification/                    # Cross-document verification engine
│   │   ├── cross_validator.py           # Orchestrates cross-verification rules
│   │   ├── matchers/
│   │   │   ├── name_matcher.py          # Multi-tiered name matching (exact, token, fuzzy)
│   │   │   └── vehicle_matcher.py       # Vehicle class cross-matching
│   │   └── decision_engine.py           # Deterministic final status (VERIFIED/REJECTED/ERROR)
│   │
│   ├── schemas/                         # Pydantic v2 Data Transfer Objects
│   │   ├── request_schemas.py           # DriverVerificationRequest schema
│   │   ├── document_schemas.py          # Internal document models & raw OCR result
│   │   └── response_schemas.py          # DriverVerificationResponse schema
│   │
│   ├── core/                            # Microservice configuration & shared infra
│   │   ├── config.py                    # pydantic-settings (.env management)
│   │   ├── security.py                  # PII masking (Aadhaar/PAN), ZIP Slip prevention
│   │   ├── logger.py                    # Structured JSON logging (zero PII leakage)
│   │   └── exceptions.py                # Domain exceptions & HTTP exception handlers
│   │
│   └── utils/
│       ├── image_utils.py               # Image validation, pre-processing, PDF-to-image
│       └── temp_manager.py              # Temporary file lifecycle & secure auto-cleanup
│
├── tests/                               # Test suite
│   ├── conftest.py                      # Test fixtures & mock Vision client
│   ├── unit/
│   │   ├── test_zip_extractor.py
│   │   ├── test_vision_client.py
│   │   ├── test_name_matcher.py
│   │   ├── test_vehicle_normalizer.py
│   │   └── test_extractors.py
│   ├── integration/
│   │   └── test_verification_flow.py
│   └── e2e/
│       └── test_api_endpoints.py
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

This single-microservice architecture provides clean internal separation of concerns while keeping operations fast, cost-effective, and deployable as a single container.

---

# 3. End-to-End Processing Flow

```text
                Driver API Payload
                       │
                       ▼
              Request Validation
                       │
                       ▼
             Download ZIP Files
                       │
                       ▼
              ZIP Password =
              mobile_number
                       │
                       ▼
                Extract Images
                       │
                       ▼
             Validate Documents
                       │
                       ▼
              Google Vision API
                       │
                       ▼
                  OCR Text
                       │
                       ▼
             Document Identification
                       │
                       ▼
              Field Extraction
                       │
                       ▼
                Normalization
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Aadhaar        PAN       Licence / RC
          │            │            │
          └────────────┼────────────┘
                       ▼
               Cross Verification
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
     Name Matching             Vehicle Class
          │                       Matching
          └────────────┬──────────┘
                       ▼
                 Final Decision
                       │
                       ▼
                  API Response
```

The processing pipeline inside the microservice executes across 5 synchronous internal stages without inter-service network overhead:

```text
1. INGESTION & UNPACKING      (HTTP payload validation, S3 download, ZIP password extraction)
        ↓
2. VISION AI OCR              (Batch image submission to Google Cloud Vision, raw OCR capture)
        ↓
3. EXTRACTION & NORMALIZATION (Document classification, regex/field parsing, standardizing entities)
        ↓
4. CROSS-VERIFICATION         (Multi-document cross checks: Aadhaar ↔ PAN, Aadhaar ↔ DL, RC ↔ vehicle class)
        ↓
5. DECISION & EGRESS          (Deterministic status calculation, PII masking, JSON response to caller)
```

---

# 4. Step 1 — Input Validation

Create Pydantic request models in `src/schemas/request_schemas.py`:

```python
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl

class DriverVerificationRequest(BaseModel):
    driver_id: str = Field(..., min_length=1, description="Unique identifier for the driver")
    mobile_number: str = Field(..., pattern=r"^[0-9]{10}$", description="10-digit mobile number, also used as ZIP password")
    vehicle_class: str = Field(..., min_length=1, description="Applied vehicle class (e.g., 2 wheeler, car)")

    aadhaar_zip_url: Optional[str] = None
    licence_zip_url: Optional[str] = None
    pan_zip_url: Optional[str] = None
    rc_zip_url: Optional[str] = None

class BatchDriverVerificationRequest(BaseModel):
    drivers: List[DriverVerificationRequest] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Array of driver verification requests to process simultaneously (max 50 per batch)"
    )
```

Validate:

- `driver_id` is not empty.
- `mobile_number` has the expected 10-digit numeric format.
- `vehicle_class` belongs to supported values.
- URLs are valid HTTPS URLs where present.
- At least the required document inputs are handled according to the project's document requirements.
- In batch requests, ensure `len(drivers)` is between 1 and `MAX_BATCH_SIZE` (default 50) to prevent denial-of-service / memory exhaustion.

Initially supported vehicle classes:

```text
2 wheeler
3 wheeler
car
truck
```

Keep supported vehicle classes configurable rather than scattering them throughout the code.

---

# 5. Step 2 — ZIP Downloading

Create:

```text
src/clients/s3_download_client.py
```

Responsibility:

```text
Presigned S3 URL
      ↓
HTTP GET
      ↓
ZIP bytes
      ↓
Temporary ZIP file
```

Requirements:

- Allow HTTPS URLs.
- Use connection and read timeouts.
- Enforce maximum download size.
- Handle HTTP errors.
- Handle expired presigned URLs.
- Do not log signed S3 URLs.
- Do not permanently store downloaded documents unless explicitly required.
- Delete temporary files after processing.

The supplied URLs are expected to be presigned S3 URLs. The application should download them while the signed URL remains valid.

---

# 6. Step 3 — Password-Protected ZIP Extraction

Create:

```text
src/extraction/zip_extractor.py
```

The ZIP password is the driver's:

```python
mobile_number
```

Example interface:

```python
extract_zip(
    zip_path=zip_path,
    password=mobile_number
)
```

The extraction layer must:

1. Verify that the downloaded file is a valid ZIP.
2. Attempt extraction using the mobile number.
3. Detect an incorrect password.
4. Protect against Zip Slip/path traversal.
5. Limit the number of extracted files.
6. Limit total extracted size.
7. Reject unsupported file types.
8. Safely handle corrupted archives.
9. Use a temporary extraction directory.

Supported formats initially:

```text
.jpg
.jpeg
.png
.webp
.pdf
```

If PDFs are provided, convert PDF pages to images before OCR so the OCR pipeline remains consistent.

---

# 7. Step 4 — Document Inventory

After extraction, create an internal representation of every document/page.

Example:

```python
DocumentFile(
    document_type="unknown",
    file_path="...",
    source="rc_zip",
    page_number=1
)
```

Do not rely entirely on filenames.

Examples of unreliable filenames:

```text
IMG_001.jpg
IMG_002.jpg
front.jpeg
back.jpeg
```

The application should determine document type using source context plus OCR/document characteristics.

---

# 8. Step 5 — Google Cloud Vision Integration

Create:

```text
src/clients/vision_ai_client.py
```

This must be the only module that directly communicates with Google Cloud Vision.

Other modules should call an abstraction such as:

```python
vision_ai_client.extract_text(image)
```

rather than importing and using the Google Vision SDK throughout the project.

Conceptual flow:

```text
Image
  ↓
Google Cloud Vision
  ↓
OCR response
  ↓
Raw extracted text
```

Store the raw OCR result internally for debugging and auditing:

```python
OCRResult(
    text="...",
    confidence=...,
    blocks=[...],
    ...
)
```

Keep raw OCR output available internally, but do not expose or log sensitive OCR data unnecessarily.

---

# 9. Step 6 — Document-Specific Extraction

Do not create one giant parser for all documents.

Create separate processors.

## Aadhaar Processor

Expected fields may include:

```text
name
date_of_birth
aadhaar_number
```

## PAN Processor

Expected fields may include:

```text
name
father_name
date_of_birth
pan_number
```

## Driving Licence Processor

Expected fields may include:

```text
name
date_of_birth
licence_number
valid_from
valid_to
vehicle_classes
```

## RC Processor

Expected fields may include:

```text
owner_name
registration_number
vehicle_class
```

Each processor should accept OCR output and return structured fields.

Example:

```python
{
    "document_type": "aadhaar",
    "name": "...",
    "dob": "...",
    "aadhaar_number": "..."
}
```

The processors should focus on **extraction**, not final driver verification.

---

# 10. Step 7 — Document Classification

Determine what document each extracted image represents.

Use multiple signals.

## Source Context

If a file came from:

```text
aadhaar_zip_url
```

then Aadhaar is strongly expected.

Likewise:

```text
pan_zip_url
licence_zip_url
rc_zip_url
```

provide strong source context.

## OCR Keywords

### Aadhaar

Possible indicators:

```text
AADHAAR
UNIQUE IDENTIFICATION AUTHORITY
GOVERNMENT OF INDIA
```

### PAN

Possible indicators:

```text
INCOME TAX DEPARTMENT
PAN
```

### Driving Licence

Possible indicators:

```text
DRIVING LICENCE
DRIVING LICENSE
DL NO
TRANSPORT
```

### RC

Possible indicators:

```text
REGISTRATION CERTIFICATE
REGISTERING AUTHORITY
REGN NO
CHASSIS
```

Return:

```text
aadhaar
pan
licence
rc
unknown
```

If classification confidence is too low, do not guess. Mark the document as invalid or unknown.

---

# 11. Step 8 — Field Normalization

OCR output may contain formatting differences.

Examples:

```text
PARIKSHIT PANCHAL
Parikshit Panchal
PARIKSHIT  PANCHAL
```

Normalize before comparison.

Example:

```text
PARIKSHIT PANCHAL
       ↓
parikshit panchal
```

Normalization should include:

- Unicode normalization.
- Lowercasing.
- Leading/trailing whitespace removal.
- Multiple whitespace collapse.
- Punctuation handling.
- Safe OCR noise cleanup.
- Consistent token formatting.

Do not perform aggressive transformations that could incorrectly change a person's identity.

---

# 12. Step 9 — Name Matching

Use multiple comparison levels.

## Level 1 — Exact Normalized Match

```text
parikshit panchal
        ==
parikshit panchal
```

Result:

```text
MATCH
```

## Level 2 — Token-Based Comparison

Handle cases such as:

```text
PARIKSHIT A PANCHAL
PARIKSHIT PANCHAL
```

Compare meaningful name tokens while accounting for middle names/initials.

## Level 3 — Fuzzy Matching

A library such as `rapidfuzz` can be used.

Example:

```text
PARIKSHIT PANCHAL
PARIKSHIT PANCHAL
       ↓
100%
```

Use configurable thresholds.

Example initial configuration:

```text
>= 95      MATCH
85–94      REVIEW / additional validation
< 85       MISMATCH
```

These thresholds must be tested against real document samples before being treated as production thresholds.

Avoid making every fuzzy match an automatic acceptance.

---

# 13. Step 10 — Required Name Verification

Required comparisons:

```text
             Aadhaar Name
                 │
          ┌──────┴──────┐
          ▼             ▼
       PAN Name      Licence Name
```

The result should contain the individual comparisons.

Example:

```json
{
  "name_verification": {
    "aadhaar_pan": {
      "match": true,
      "score": 100
    },
    "aadhaar_licence": {
      "match": true,
      "score": 98
    }
  }
}
```

Aadhaar should be the primary identity reference for these comparisons according to the defined business rule.

Do not use only PAN ↔ Licence matching.

---

# 14. Step 11 — Vehicle Class Normalization

The API may provide:

```text
2 wheeler
```

while the RC may contain:

```text
MCWG
M-CYCLE
MOTOR CYCLE
SCOOTER
```

These may represent the same business category.

Create:

```text
src/normalization/vehicle_normalizer.py
```

Maintain one centralized mapping.

Example:

```python
VEHICLE_CLASS_MAPPING = {
    "2 wheeler": [
        "motor cycle",
        "motorcycle",
        "scooter",
        "m-cycle",
        "mcwg",
    ],

    "3 wheeler": [
        "three wheeler",
        "auto",
        "autorickshaw",
        "e-rickshaw"
    ],

    "car": [
        "car",
        "lmv",
        "light motor vehicle"
    ],

    "truck": [
        "truck",
        "hgv",
        "LGV",
        "heavy goods vehicle"
    ]
}
```

This mapping is only an initial example and must be adapted to the actual RC terminology found in the project's dataset.

---

# 15. Step 12 — Vehicle Verification

Comparison flow:

```text
API vehicle_class
        ↓
Canonical vehicle class
        ↓
RC extracted vehicle class
        ↓
Canonical vehicle class
        ↓
Comparison
```

Example:

```text
API:
2 wheeler

RC:
MCWG

        ↓

2 wheeler == 2 wheeler

        ↓

MATCH
```

Response example:

```json
{
  "vehicle_verification": {
    "provided_class": "2 wheeler",
    "rc_class": "MCWG",
    "normalized_provided_class": "2 wheeler",
    "normalized_rc_class": "2 wheeler",
    "match": true
  }
}
```

---

# 16. Step 13 — Final Verification Engine

Create:

```text
src/verification/cross_validator.py
src/verification/decision_engine.py
```

This should be the **only component responsible for the final `VERIFIED` / `REJECTED` decision**.

Conceptual rule:

```text
Aadhaar successfully processed
        AND
PAN successfully processed
        AND
Licence successfully processed
        AND
RC successfully processed
        AND
Aadhaar name matches PAN name
        AND
Aadhaar name matches Licence name
        AND
RC vehicle class matches provided vehicle class
```

→ `VERIFIED`

If one or more required verification rules fail:

→ `REJECTED`

Individual processors must not independently decide the final driver status.

---

# 17. Rejection Reasons

Return machine-readable rejection reasons.

Example:

```json
{
  "status": "REJECTED",
  "reasons": [
    "AADHAAR_PAN_NAME_MISMATCH",
    "RC_VEHICLE_CLASS_MISMATCH"
  ]
}
```

Other possible reasons:

```text
AADHAAR_NOT_FOUND
PAN_NOT_FOUND
LICENCE_NOT_FOUND
RC_NOT_FOUND

AADHAAR_OCR_FAILED
PAN_OCR_FAILED
LICENCE_OCR_FAILED
RC_OCR_FAILED

AADHAAR_PAN_NAME_MISMATCH
AADHAAR_LICENCE_NAME_MISMATCH
RC_VEHICLE_CLASS_MISMATCH

INVALID_DOCUMENT
UNKNOWN_DOCUMENT_TYPE
MISSING_REQUIRED_FIELD
```

Keep reason codes centralized and consistent.

---

# 18. Rejection vs Error

This distinction is mandatory.

## REJECTED

The system successfully processed the driver's documents, but the verification rules failed.

Example:

```text
Aadhaar:
Rahul Sharma

PAN:
Amit Patel
```

The system knows the documents and comparison result, so:

```text
REJECTED
```

## ERROR

The system could not complete processing because of an infrastructure or processing failure.

Examples:

```text
Google Vision unavailable
S3 download failed
Presigned URL expired
ZIP corrupted
Unexpected internal exception
Network timeout
```

Result:

```text
ERROR
```

This distinction makes production monitoring much easier.

---

# 19. Suggested API Response

Example successful response:

```json
{
  "driver_id": "partner-59820",
  "status": "VERIFIED",

  "documents": {
    "aadhaar": {
      "processed": true,
      "name": "PARIKSHIT PANCHAL"
    },
    "pan": {
      "processed": true,
      "name": "PARIKSHIT PANCHAL"
    },
    "licence": {
      "processed": true,
      "name": "PARIKSHIT PANCHAL"
    },
    "rc": {
      "processed": true,
      "vehicle_class": "MCWG"
    }
  },

  "name_verification": {
    "aadhaar_pan": {
      "match": true,
      "score": 100
    },
    "aadhaar_licence": {
      "match": true,
      "score": 98
    }
  },

  "vehicle_verification": {
    "provided_class": "2 wheeler",
    "rc_class": "MCWG",
    "normalized_provided_class": "2 wheeler",
    "normalized_rc_class": "2 wheeler",
    "match": true
  },

  "rejection_reasons": []
}
```

For rejected verification:

```json
{
  "driver_id": "partner-59820",
  "status": "REJECTED",

  "name_verification": {
    "aadhaar_pan": {
      "match": false,
      "score": 61
    },
    "aadhaar_licence": {
      "match": true,
      "score": 97
    }
  },

  "vehicle_verification": {
    "provided_class": "2 wheeler",
    "rc_class": "LMV",
    "normalized_provided_class": "2 wheeler",
    "normalized_rc_class": "car",
    "match": false
  },

  "rejection_reasons": [
    "AADHAAR_PAN_NAME_MISMATCH",
    "RC_VEHICLE_CLASS_MISMATCH"
  ]
}
```

For batch verification (`POST /api/v1/batch-verify`):

```json
{
  "total_count": 2,
  "verified_count": 1,
  "rejected_count": 1,
  "error_count": 0,
  "processing_time_ms": 1420.5,
  "results": [
    {
      "driver_id": "partner-59820",
      "status": "VERIFIED",
      "documents": {
        "aadhaar": { "processed": true, "name": "PARIKSHIT PANCHAL" },
        "pan": { "processed": true, "name": "PARIKSHIT PANCHAL" },
        "licence": { "processed": true, "name": "PARIKSHIT PANCHAL" },
        "rc": { "processed": true, "vehicle_class": "MCWG" }
      },
      "name_verification": {
        "aadhaar_pan": { "match": true, "score": 100 },
        "aadhaar_licence": { "match": true, "score": 98 }
      },
      "vehicle_verification": {
        "provided_class": "2 wheeler",
        "rc_class": "MCWG",
        "normalized_provided_class": "2 wheeler",
        "normalized_rc_class": "2 wheeler",
        "match": true
      },
      "rejection_reasons": []
    },
    {
      "driver_id": "partner-59821",
      "status": "REJECTED",
      "documents": {
        "aadhaar": { "processed": true, "name": "RAHUL SHARMA" },
        "pan": { "processed": true, "name": "AMIT SHARMA" },
        "licence": { "processed": true, "name": "RAHUL SHARMA" },
        "rc": { "processed": true, "vehicle_class": "MCWG" }
      },
      "name_verification": {
        "aadhaar_pan": { "match": false, "score": 55 },
        "aadhaar_licence": { "match": true, "score": 100 }
      },
      "vehicle_verification": {
        "provided_class": "2 wheeler",
        "rc_class": "MCWG",
        "normalized_provided_class": "2 wheeler",
        "normalized_rc_class": "2 wheeler",
        "match": true
      },
      "rejection_reasons": [
        "AADHAAR_PAN_NAME_MISMATCH"
      ]
    }
  ]
}
```

---

# 20. Sensitive Data Protection

Do not unnecessarily return complete sensitive identity information.

Internally the system may extract:

```text
Aadhaar number
PAN number
Licence number
RC number
```

But API responses should preferably mask sensitive identifiers.

Examples:

```text
XXXX XXXX 1234
ABCDE****F
```

Never log:

- Full Aadhaar number.
- Full PAN number.
- Full licence number.
- Full mobile number.
- Complete OCR text.
- Presigned S3 URLs.
- Raw identity documents.

The system should treat OCR output as sensitive data.

---

# 21. Temporary File Lifecycle

Use temporary storage only for the duration of the request.

Preferred flow:

```text
Request
   ↓
Create temporary directory
   ↓
Download ZIP
   ↓
Extract documents
   ↓
Convert PDF pages if required
   ↓
OCR
   ↓
Verification
   ↓
Delete temporary directory
```

Prefer Python's `TemporaryDirectory` or an equivalent safe lifecycle mechanism.

The server should not accumulate identity documents over time.

Ensure cleanup occurs even if processing raises an exception.

---

# 22. Google Cloud Credentials

Never hard-code Google credentials.

Use environment/secret configuration.

Example:

```env
GOOGLE_APPLICATION_CREDENTIALS=/secure/path/service-account.json
GOOGLE_CLOUD_PROJECT=your-project-id
```

Never commit service-account credentials to GitHub.

Recommended `.gitignore` entries:

```text
.env
credentials/
secrets/
tmp/
downloads/
extracted/
*.pem
*.key
```

Only ignore JSON credential files if doing so does not accidentally ignore legitimate project configuration files.

---

# 23. Configuration

Create:

```text
src/core/config.py
```

Configuration should include values such as:

```text
GOOGLE_CLOUD_PROJECT
GOOGLE_APPLICATION_CREDENTIALS

MAX_ZIP_SIZE
MAX_EXTRACTED_SIZE
MAX_FILES_PER_ZIP

DOWNLOAD_TIMEOUT
VISION_TIMEOUT

NAME_MATCH_THRESHOLD
NAME_REVIEW_THRESHOLD

SUPPORTED_VEHICLE_CLASSES
```

Do not scatter magic numbers throughout the application.

---

# 24. Logging

Use structured logging.

Good:

```text
driver_id=partner-59820
document=rc
stage=ocr
status=success
```

Bad:

```text
OCR TEXT = ...
AADHAAR = 1234...
URL = https://signed-s3-url...
```

Track processing stages:

```text
REQUEST_RECEIVED
DOWNLOAD_STARTED
DOWNLOAD_COMPLETED
ZIP_EXTRACTION_STARTED
ZIP_EXTRACTION_COMPLETED
DOCUMENT_VALIDATION_STARTED
OCR_STARTED
OCR_COMPLETED
DOCUMENT_EXTRACTION_COMPLETED
NORMALIZATION_COMPLETED
VERIFICATION_STARTED
VERIFICATION_COMPLETED
RESPONSE_GENERATED
```

Do not put sensitive document contents into logs.

---

# 25. Error Handling

Create centralized error handling.

Handle at least:

```text
Invalid request
Invalid URL
Download timeout
HTTP download failure
Expired presigned URL
Invalid ZIP
Incorrect ZIP password
ZIP Slip/path traversal
Extraction size exceeded
Unsupported file
PDF conversion failure
Vision API authentication failure
Vision API timeout
Vision API quota/rate-limit error
OCR failure
Document parsing failure
Unexpected internal error
```

Return safe error messages to the API caller without exposing internal stack traces or credentials.

Log the detailed technical error internally.

---

# 26. Google Vision API Failure Strategy

Google Vision is an external dependency, so failures must be handled explicitly.

Possible outcomes:

```text
Vision succeeds
       ↓
continue verification
```

or:

```text
Vision fails
       ↓
processing cannot be completed
       ↓
ERROR
```

Do not interpret an API failure as:

```text
REJECTED
```

A failed OCR request does not prove that the driver's document is invalid.

If retry logic is added later, use bounded retries with exponential backoff and do not retry permanent authentication/configuration errors.

---

# 27. Concurrency Considerations & Simultaneous Batch Execution

The microservice receives both individual driver requests and high-volume batch requests where multiple drivers must be processed simultaneously.

### Key Requirements

1. **Bounded Concurrency via Semaphores**:
   - Processing 50 drivers simultaneously without concurrency bounds would unpack 200 ZIP archives and launch up to 200 concurrent HTTP calls to Google Cloud Vision, risking out-of-memory (OOM) errors, socket exhaustion, and GCP API rate-limit throttling (HTTP 429).
   - Use an `asyncio.Semaphore` with a configurable pool size (e.g., `MAX_CONCURRENT_WORKERS = 5` or `10`).
   - This ensures up to `N` drivers are actively executing heavy download, unzip, and Vision OCR tasks in parallel, while remaining drivers queue seamlessly in memory.

2. **Per-Driver Isolated Temporary Storage**:
   - Each driver within a batch must have its own unique, isolated temporary directory to prevent race conditions and file collisions:
     ```text
     /tmp/driver_verification/<batch_uuid>/<driver_id>/
     ```
   - Directories are cleaned up immediately after that individual driver finishes processing, keeping disk usage minimal throughout the batch lifecycle.

3. **Per-Driver Fault Isolation**:
   - In a batch request, failure of one driver (e.g. invalid ZIP password, expired S3 presigned URL, or corrupted document) must **never abort or fail the entire batch**.
   - Wrap each worker in a localized exception boundary so that failures produce an `ERROR` response for that specific driver while the remaining drivers continue execution uninterrupted.

### Concurrent Batch Implementation Pattern

```python
import asyncio
import time
from typing import List

async def verify_batch(
    self,
    batch_request: BatchDriverVerificationRequest,
    max_concurrency: int = 5
) -> BatchDriverVerificationResponse:
    start_time = time.perf_counter()
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _verify_driver_with_semaphore(driver_req: DriverVerificationRequest) -> DriverVerificationResponse:
        async with semaphore:
            try:
                return await self.verify_driver(driver_req)
            except Exception as exc:
                logger.error(
                    "Driver verification failed in batch",
                    extra={"driver_id": driver_req.driver_id, "error": str(exc)}
                )
                return DriverVerificationResponse(
                    driver_id=driver_req.driver_id,
                    status="ERROR",
                    rejection_reasons=[f"INTERNAL_PROCESSING_ERROR: {type(exc).__name__}"]
                )

    # Launch all driver tasks simultaneously within bounded semaphore
    tasks = [_verify_driver_with_semaphore(driver) for driver in batch_request.drivers]
    results: List[DriverVerificationResponse] = await asyncio.gather(*tasks)

    # Calculate aggregate metrics
    verified = sum(1 for r in results if r.status == "VERIFIED")
    rejected = sum(1 for r in results if r.status == "REJECTED")
    errors = sum(1 for r in results if r.status == "ERROR")
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return BatchDriverVerificationResponse(
        total_count=len(results),
        verified_count=verified,
        rejected_count=rejected,
        error_count=errors,
        processing_time_ms=elapsed_ms,
        results=results
    )
```

---

# 28. OCR Cost and Performance

Because Google Vision API usage may incur cost, avoid unnecessary duplicate calls.

For each image:

```text
Download
   ↓
Validate
   ↓
OCR once
   ↓
Reuse OCR result
```

Do not send the same image repeatedly to Vision from multiple processors.

The architecture should be:

```text
Image
  ↓
Vision OCR
  ↓
Cached/in-memory OCR result
  ↓
Aadhaar/PAN/Licence/RC parser
```

not:

```text
Image
  ↓
Aadhaar parser → Vision
PAN parser → Vision
Licence parser → Vision
RC parser → Vision
```

unless there is a specific reason to do so.

---

# 29. Image Preprocessing

Start with Google Vision directly.

Do not add unnecessary preprocessing before establishing a baseline.

After testing real documents, consider preprocessing for:

- Rotation.
- Cropping.
- Resolution enhancement.
- Contrast normalization.
- Noise reduction.
- Perspective correction.

However, preprocessing should be measured against real OCR accuracy before being enabled globally.

Avoid transformations that remove useful document information.

---

# 30. Multi-Page Documents

The system should support documents containing multiple images/pages.

Example:

```text
Licence ZIP
    ├── front.jpg
    └── back.jpg
```

or:

```text
RC ZIP
    ├── page1.jpg
    ├── page2.jpg
    └── page3.jpg
```

Processing should be:

```text
ZIP
 ↓
all supported files
 ↓
OCR each page/image
 ↓
combine document OCR
 ↓
extract fields across all pages
```

The document processor should be able to use information from multiple pages.

---

# 31. Front/Back Handling

For documents such as Aadhaar or Driving Licence, front and back images may contain different fields.

Do not assume that the first image contains everything.

Example:

```text
Licence front
    ↓
name + licence number

Licence back
    ↓
vehicle classes
```

Combine OCR results for the complete document before deciding whether required fields are missing.

---

# 32. Missing Documents

The API may contain empty URLs:

```json
{
  "aadhaar_zip_url": "",
  "licence_zip_url": "",
  "pan_zip_url": "",
  "rc_zip_url": "..."
}
```

The application must have explicit rules for missing documents.

For the current identity verification requirements, if a required document is missing:

```text
REJECTED
```

with a reason such as:

```text
AADHAAR_NOT_FOUND
```

Do not silently skip required verification.

If business requirements later allow certain documents to be optional, that should be a configuration/business rule rather than implicit behavior.

---

# 33. Document Extraction Data Model

Create typed internal models.

Example:

```python
class AadhaarData(BaseModel):
    document_type: Literal["aadhaar"]
    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    aadhaar_number: Optional[str] = None
```

Similarly:

```text
PanData
LicenceData
RcData
```

This provides predictable interfaces between OCR and verification.

---

# 34. Verification Result Model

Create a structured internal result.

Example:

```python
class VerificationResult(BaseModel):
    driver_id: str
    status: Literal["VERIFIED", "REJECTED", "ERROR"]
    documents: dict
    name_verification: dict
    vehicle_verification: dict
    rejection_reasons: list[str]
    error_code: Optional[str] = None
```

The internal model and public API model can be separated if necessary.

---

# 35. API Design

Cloud-native microservice endpoints:

## 1. Verify Single Driver

```http
POST /api/v1/verify-driver
```

Request:

```json
{
  "driver_id": "partner-59820",
  "mobile_number": "3335616616",
  "vehicle_class": "2 wheeler",
  "aadhaar_zip_url": "https://...",
  "licence_zip_url": "https://...",
  "pan_zip_url": "https://...",
  "rc_zip_url": "https://..."
}
```

Response: Returns a `DriverVerificationResponse` (`VERIFIED`, `REJECTED`, or `ERROR`).

---

## 2. Verify Drivers in Batch (Concurrent Execution)

```http
POST /api/v1/batch-verify
```

Accepts an array of driver objects and executes them **simultaneously** using an internal semaphore-controlled concurrency worker pool.

Request:

```json
{
  "drivers": [
    {
      "driver_id": "partner-59820",
      "mobile_number": "3335616616",
      "vehicle_class": "2 wheeler",
      "aadhaar_zip_url": "https://...",
      "licence_zip_url": "https://...",
      "pan_zip_url": "https://...",
      "rc_zip_url": "https://..."
    },
    {
      "driver_id": "partner-59821",
      "mobile_number": "9876543210",
      "vehicle_class": "car",
      "aadhaar_zip_url": "https://...",
      "licence_zip_url": "https://...",
      "pan_zip_url": "https://...",
      "rc_zip_url": "https://..."
    }
  ]
}
```

Response: Returns `BatchDriverVerificationResponse` containing total counts, aggregate status counts, elapsed runtime, and individual results.

---

## 3. Health & Observability Probes

```http
GET /health
```
Liveness probe for Kubernetes / container orchestrators.
```json
{
  "status": "healthy"
}
```

```http
GET /ready
```
Readiness probe verifying local temp storage access and GCP credentials presence (without making paid Vision calls).
```json
{
  "status": "ready",
  "storage": "ok",
  "credentials_configured": true
}
```

---

# 36. API Route Responsibility

Keep the FastAPI routes thin. Delegates execution entirely to the validator service.

```python
@router.post("/verify-driver", response_model=DriverVerificationResponse)
async def verify_single_driver(
    payload: DriverVerificationRequest,
    validator: CrossValidator = Depends(get_cross_validator)
):
    """Verifies a single driver payload synchronously."""
    return await validator.process_and_verify(payload)

@router.post("/batch-verify", response_model=BatchDriverVerificationResponse)
async def verify_drivers_batch(
    payload: BatchDriverVerificationRequest,
    validator: CrossValidator = Depends(get_cross_validator)
):
    """Verifies multiple drivers simultaneously with bounded concurrency."""
    return await validator.batch_process_and_verify(payload)
```

The route handles HTTP concerns (status codes, request validation, headers).
The internal modules handle business logic and concurrent orchestration.

---

# 37. Recommended Component Responsibilities

## `src/clients/s3_download_client.py`

Responsible for:
- HTTP downloading from presigned S3 URLs.
- Connection/read timeouts.
- File download size caps.
- HTTP error handling.

## `src/extraction/zip_extractor.py`

Responsible for:
- ZIP archive integrity check.
- Password-protected extraction using driver's mobile number.
- Zip Slip / path traversal protection.
- Total extraction size and file count limits.

## `src/clients/vision_ai_client.py`

Responsible for:
- Google Cloud Vision client connection.
- Batch image OCR calls.
- Raw text and block extraction.
- Vision API error and retry management.

## `src/extraction/document_classifier.py` & `src/extraction/extractors/`

Responsible for:
- Classifying document type (source hint + keyword heuristics).
- Dedicated per-document extractors (`aadhaar_extractor.py`, `pan_extractor.py`, `licence_extractor.py`, `rc_extractor.py`).
- Regex pattern matching and bounding box text parsing.

## `src/normalization/`

Responsible for:
- `name_normalizer.py`: Case folding, whitespace, punctuation, initials.
- `vehicle_normalizer.py`: Vehicle class mapping to canonical types (`2 wheeler`, `car`, etc.).
- `date_normalizer.py`: Standardizing date formats to ISO-8601.

## `src/verification/cross_validator.py` & `src/verification/decision_engine.py`

Responsible for:
- Coordinating cross-document matching rules for single driver requests (`process_and_verify`).
- Orchestrating concurrent batch verification (`batch_process_and_verify`) using `asyncio.Semaphore` bounded pools.
- Deterministic Aadhaar ↔ PAN, Aadhaar ↔ DL, RC ↔ Vehicle Class validations.
- Decision engine outputting `VERIFIED`, `REJECTED`, or `ERROR` with structured reasons.
- Formatting API responses and masking sensitive PII before egress.

---

# 38. Unit Testing Strategy

Do not wait until the entire system is finished.

Test every layer independently.

Mock the Google Vision client during all automated test runs. Do not make paid API calls during testing.

## ZIP Tests

Test:

- Valid password extraction.
- Incorrect password.
- Corrupted archive.
- Path traversal/ZIP Slip attempts.
- Large archive rejection.
- Nested directory handling.
- Unsupported file format inside archive.

## Download Tests

Test:

- Valid download.
- 404/403 HTTP response.
- Connection timeout.
- Read timeout.
- Size limit exceeded.

## Vision Tests

Test:

- Image input converted to Google Vision format.
- Successful OCR response parsed correctly.
- Empty OCR response.
- Vision API error handling.
- Retries on transient failure where appropriate.

Use saved mock responses from real Vision calls.

## Document Parser Tests

Test:

- Aadhaar field extraction.
- PAN field extraction.
- Licence field extraction.
- RC field extraction.
- Multi-page document handling.
- Missing field handling.

## Name Matching Tests

Test:

- Exact match.
- Different case.
- Trailing spaces.
- Name with initials.
- Reordered names.
- Substring names.
- Nickname vs full name where relevant.
- Completely different names.

## Vehicle Matching Tests

Test:

```text
2 wheeler ↔ MCWG
2 wheeler ↔ motorcycle
2 wheeler ↔ scooter
3 wheeler ↔ auto
car ↔ LMV
truck ↔ HGV
2 wheeler ↔ LMV
```

---

# 39. End-to-End Test Cases

Create complete driver scenarios.

## Case 1 — Fully Valid Driver

```text
Aadhaar name = PAN name
Aadhaar name = Licence name
RC class = API vehicle class
```

Expected:

```text
VERIFIED
```

## Case 2 — Aadhaar/PAN Name Mismatch

```text
Aadhaar = Rahul Sharma
PAN = Amit Patel
Licence = Rahul Sharma
RC = correct
```

Expected:

```text
REJECTED
AADHAAR_PAN_NAME_MISMATCH
```

## Case 3 — Aadhaar/Licence Name Mismatch

Expected:

```text
REJECTED
AADHAAR_LICENCE_NAME_MISMATCH
```

## Case 4 — Vehicle Mismatch

```text
API = 2 wheeler
RC = LMV
```

Expected:

```text
REJECTED
RC_VEHICLE_CLASS_MISMATCH
```

## Case 5 — Incorrect ZIP Password

Expected:

```text
ERROR
```

unless business requirements explicitly define invalid password/document access as a rejection.

## Case 6 — Vision API Failure

Expected:

```text
ERROR
```

not `REJECTED`.

## Case 7 — Simultaneous Batch Verification (Mixed Scenarios)

Payload contains 3 drivers submitted simultaneously in a single `POST /api/v1/batch-verify`:
- Driver 1: Valid credentials → `VERIFIED`
- Driver 2: Aadhaar/PAN mismatch → `REJECTED`
- Driver 3: Corrupted ZIP archive → `ERROR`

Expected:
```json
{
  "total_count": 3,
  "verified_count": 1,
  "rejected_count": 1,
  "error_count": 1,
  "results": [
    { "driver_id": "driver-1", "status": "VERIFIED" },
    { "driver_id": "driver-2", "status": "REJECTED" },
    { "driver_id": "driver-3", "status": "ERROR" }
  ]
}
```
All 3 drivers must execute concurrently within the semaphore limit; Driver 3's error must not abort Driver 1 or Driver 2.

## Case 8 — Batch Size Boundary Enforcement

- Submitting an empty `drivers: []` list → HTTP 422 Unprocessable Entity (`min_length=1`).
- Submitting 51 drivers when `MAX_BATCH_SIZE=50` → HTTP 422 Unprocessable Entity (`max_length=50`).

---

# 40. Security Requirements

The system processes identity documents, so security must be treated as a first-class requirement.

Implement:

- HTTPS-only document URLs.
- Download timeout.
- Maximum download size.
- Maximum extracted size.
- Maximum file count.
- Zip Slip protection.
- Safe temporary directories.
- Automatic temporary-file cleanup.
- No credentials in source code.
- No signed URLs in logs.
- No complete identity numbers in logs.
- No raw OCR text in logs.
- No unnecessary persistence of identity documents.
- Safe exception responses.
- Dependency version pinning where appropriate.

Also consider SSRF protection when accepting arbitrary URLs from external callers. At minimum, validate that URLs use HTTPS and consider blocking internal/private network destinations depending on the deployment environment and threat model.

---

# 41. Observability

Track non-sensitive metrics such as:

```text
total_verifications
verified_count
rejected_count
error_count

average_download_time
average_ocr_time
average_total_processing_time

vision_api_failures
zip_failures
parser_failures

rejection_reason_counts
```

These metrics will help identify whether failures are caused by:

- Poor documents.
- OCR.
- Parsing.
- Business-rule mismatches.
- Infrastructure.

Do not put sensitive document contents into metrics.

---

# 42. Performance Optimization

Start with correctness.

Then optimize.

Potential optimizations:

```text
Parallel ZIP downloads
Parallel OCR for independent images
OCR result caching within request
Connection reuse
PDF page processing optimization
Image resizing where appropriate
```

Be careful with parallel Vision API calls because API quotas, cost, and rate limits must be respected.

A reasonable initial strategy is:

```text
Download required ZIPs
       ↓
Extract
       ↓
Prepare images
       ↓
OCR images
       ↓
Parse
       ↓
Verify
```

Only introduce concurrency after measuring the baseline.

---

# 43. Dependency Suggestions

Initial dependencies may include:

```text
fastapi
uvicorn
pydantic
pydantic-settings

google-cloud-vision

httpx

rapidfuzz

python-multipart
```

For PDF/image processing, add only the libraries actually required by the chosen implementation.

Pin or constrain production dependencies after the initial prototype is stable.

---

# 44. Environment Configuration Example

Example `.env`:

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/secure/path/google-service-account.json

MAX_ZIP_SIZE=52428800
MAX_EXTRACTED_SIZE=104857600
MAX_FILES_PER_ZIP=50

DOWNLOAD_TIMEOUT=30
VISION_TIMEOUT=30

NAME_MATCH_THRESHOLD=95
NAME_REVIEW_THRESHOLD=85
```

Do not put actual credentials in `.env` committed to Git.

Use the deployment platform's secret management for production.

---

# 45. Development Workflow

Implement incrementally.

Do not generate the entire application as one giant change.

Recommended workflow:

```text
Phase 1
Foundation
   ↓
Phase 2
Download + ZIP
   ↓
Phase 3
Google Vision
   ↓
Phase 4
Document extraction
   ↓
Phase 5
Normalization
   ↓
Phase 6
Verification
   ↓
Phase 7
API integration
   ↓
Phase 8
Security
   ↓
Phase 9
Testing
   ↓
Phase 10
Deployment
```

After each phase:

1. Run tests.
2. Run the API locally.
3. Verify the new functionality.
4. Commit the working state.

---

# 46. Phase 1 — Foundation

Tasks:

1. Create FastAPI project.
2. Create directory structure.
3. Create settings/configuration.
4. Create Pydantic request models.
5. Create response models.
6. Create `/health`.
7. Create `/api/v1/verify-driver` skeleton.
8. Configure logging.
9. Create `.gitignore`.
10. Create initial README.

Deliverable:

```text
FastAPI application starts successfully.
```

---

# 47. Phase 2 — Download and ZIP Handling

Tasks:

1. Implement secure URL downloader.
2. Add timeout handling.
3. Add download-size limit.
4. Implement ZIP validation.
5. Implement password extraction.
6. Add Zip Slip protection.
7. Add extracted-size limits.
8. Add file-count limits.
9. Add temporary-directory cleanup.
10. Write ZIP/download tests.

Deliverable:

```text
Presigned ZIP URL
      ↓
secure download
      ↓
password extraction
      ↓
safe document files
```

---

# 48. Phase 3 — Google Vision

Tasks:

1. Configure Google Cloud credentials.
2. Install Google Vision SDK.
3. Implement `vision_service.py`.
4. Implement image OCR.
5. Normalize Vision response into internal `OCRResult`.
6. Add timeout/error handling.
7. Add mocked Vision tests.
8. Test with representative document images.

Deliverable:

```text
Image
 ↓
Google Vision
 ↓
OCRResult
```

---

# 49. Phase 4 — Document Extraction

Tasks:

1. Implement document classification.
2. Implement Aadhaar processor.
3. Implement PAN processor.
4. Implement Licence processor.
5. Implement RC processor.
6. Implement multi-page handling.
7. Add parser fixtures/tests.
8. Validate required fields.

Deliverable:

```text
OCR text
 ↓
Document-specific structured data
```

---

# 50. Phase 5 — Normalization

Tasks:

1. Implement Unicode normalization.
2. Implement name normalization.
3. Implement token handling.
4. Implement fuzzy matching.
5. Implement vehicle-class normalization.
6. Create centralized vehicle mapping.
7. Add unit tests.

Deliverable:

```text
Raw OCR fields
      ↓
Normalized fields
```

---

# 51. Phase 6 — Verification

Tasks:

1. Implement Aadhaar ↔ PAN name matching.
2. Implement Aadhaar ↔ Licence name matching.
3. Implement API vehicle class ↔ RC class matching.
4. Create rejection reason codes.
5. Implement final verification engine.
6. Implement `VERIFIED`.
7. Implement `REJECTED`.
8. Implement `ERROR`.
9. Add comprehensive verification tests.

Deliverable:

```text
Structured documents
        ↓
Business verification rules
        ↓
Final decision
```

---

# 52. Phase 7 — API Integration

Tasks:

1. Connect route to verification service.
2. Return structured response.
3. Mask sensitive fields.
4. Add safe error handling.
5. Add request-level logging.
6. Add processing-time metrics/logging.
7. Test complete API flow.

Deliverable:

```text
POST /api/v1/verify-driver
        ↓
Complete verification
        ↓
JSON response
```

---

# 53. Phase 8 — Security Hardening

Tasks:

1. Validate URLs.
2. Add SSRF protections.
3. Enforce download limits.
4. Enforce extraction limits.
5. Verify Zip Slip protection.
6. Review credential handling.
7. Review logs for sensitive information.
8. Review temporary-file cleanup.
9. Review exception messages.
10. Review dependencies.

Deliverable:

```text
Production-oriented secure processing pipeline
```

---

# 54. Phase 9 — Testing

Run:

```text
Unit tests
Integration tests
End-to-end tests
Security tests
Failure tests
```

Test both successful and failed processing.

The test suite should cover:

```text
Valid driver
Name mismatch
Vehicle mismatch
Missing document
Incorrect ZIP password
Corrupted ZIP
Expired URL
Vision failure
Malformed OCR
Unknown document
Large ZIP
Malicious ZIP
```

---

# 55. Phase 10 — Deployment

Before deployment verify:

```text
Environment variables configured
Google credentials securely configured
No credentials committed
Temporary storage mounts work
Health & readiness endpoints work (/health, /ready)
Logs do not expose PII
Vision API works from container environment
Timeouts are configured
Dependencies are installed
```

Microservice deployment architecture:

```text
  Upstream Gateway / Caller API
               │  HTTP POST /api/v1/verify-driver
               ▼
┌──────────────────────────────────────────────┐
│  Document Verification Microservice Container│
│                                              │
│         FastAPI Single Runtime               │
│               │                              │
│       ┌───────┴────────┐                     │
│       ▼                ▼                     │
│  Presigned S3    Google Vision AI            │
│       │                │                     │
│       └───────┬────────┘                     │
│               ▼                              │
│       Internal Pipeline:                     │
│       Extract → Normalize → Cross-Verify     │
│               │                              │
└───────────────┼──────────────────────────────┘
                ▼  HTTP 200 JSON Response
  Upstream Gateway / Caller API
```

Containerization requirements:
- Multi-stage Dockerfile (slim base image, e.g., `python:3.11-slim`).
- Run as non-root user for container security.
- Explicit health/readiness probe configuration.
- Stateless design: temporary files are purged per request, enabling horizontal auto-scaling (HPA/ECS tasks).

---

# 56. Core Design Principle

The most important architectural separation is:

```text
             ┌──────────────┐
             │   INGESTION  │
             └──────┬───────┘
                    ↓
             ┌──────────────┐
             │  VISION OCR  │
             └──────┬───────┘
                    ↓
             ┌──────────────┐
             │  EXTRACTION  │
             └──────┬───────┘
                    ↓
             ┌──────────────┐
             │NORMALIZATION │
             └──────┬───────┘
                    ↓
             ┌──────────────┐
             │VERIFICATION  │
             └──────┬───────┘
                    ↓
             ┌──────────────┐
             │   DECISION   │
             └──────────────┘
```

Google Vision should primarily answer:

> **"What text is present in this image?"**

Your application should answer:

> **"Do the extracted details satisfy the driver's verification rules?"**

This separation makes the system more deterministic, testable, auditable, and easier to improve later.

---

# 57. Future OCR Fallback Architecture

Start with Google Vision only.

If testing shows that Google Vision struggles with specific document conditions such as:

- severe rotation
- unusual layouts
- poor image quality
- difficult RC formats
- low-resolution documents

a secondary OCR/vision model can later be introduced.

The architecture should allow:

```text
                  Image
                    │
                    ▼
             Google Vision OCR
                    │
             OCR sufficient?
               /         \
             YES          NO
              │            │
              ▼            ▼
          Continue    Secondary OCR
                           │
                           ▼
                       Continue
```

The verification engine does not need to change.

This allows OCR technology to evolve without rewriting the business verification logic.

---

# 58. Important Engineering Rules

The coding agent must follow these rules:

1. **Single-Service Microservice**: Build the system as one autonomous microservice; do not micro-fragment internally into separate network services (e.g. separate OCR or Aadhaar services).
2. **Do not create one giant FastAPI route.**
3. **Keep Google Vision isolated inside `src/clients/vision_ai_client.py`.**
4. **Do not let OCR decide final verification.**
5. **Keep document processors separate.**
6. **Keep verification rules centralized.**
7. **Do not silently treat missing data as a match.**
8. **Do not use fuzzy matching as unconditional acceptance.**
9. **Do not log sensitive identity data.**
10. **Do not persist documents unnecessarily.**
11. **Clean up temporary files after every request.**
12. **Mock Google Vision in unit tests.**
13. **Distinguish `REJECTED` from `ERROR`.**
14. **Keep vehicle-class mappings centralized.**
15. **Keep thresholds configurable.**
16. **Use real document samples to validate extraction and matching thresholds.**
17. **Implement incrementally and test each phase before continuing.**

---

# 59. Final Implementation Checklist

## Foundation

- [ ] FastAPI application
- [ ] Project structure
- [ ] Configuration
- [ ] Pydantic models
- [ ] Health endpoint
- [ ] Logging

## File Processing

- [ ] HTTPS URL validation
- [ ] Secure ZIP download
- [ ] Download timeout
- [ ] Download size limit
- [ ] ZIP password extraction
- [ ] Zip Slip protection
- [ ] Extraction size limit
- [ ] File-count limit
- [ ] Temporary directory
- [ ] Automatic cleanup
- [ ] PDF-to-image handling if required

## Google Vision

- [ ] Google credentials
- [ ] Vision client
- [ ] OCR extraction
- [ ] OCR result model
- [ ] Vision error handling
- [ ] Vision timeout
- [ ] Mocked tests

## Document Extraction

- [ ] Document classification
- [ ] Aadhaar processor
- [ ] PAN processor
- [ ] Licence processor
- [ ] RC processor
- [ ] Multi-page support
- [ ] Front/back support
- [ ] Required-field validation

## Normalization

- [ ] Unicode normalization
- [ ] Name normalization
- [ ] Token matching
- [ ] Fuzzy matching
- [ ] Vehicle class normalization
- [ ] Central vehicle mapping

## Verification

- [ ] Aadhaar ↔ PAN name verification
- [ ] Aadhaar ↔ Licence name verification
- [ ] API vehicle class ↔ RC class verification
- [ ] Rejection reason codes
- [ ] VERIFIED decision
- [ ] REJECTED decision
- [ ] ERROR handling

## Security

- [ ] Credential protection
- [ ] No sensitive logs
- [ ] No presigned URL logs
- [ ] Temporary file cleanup
- [ ] SSRF protection
- [ ] ZIP security
- [ ] File limits
- [ ] Safe error messages

## Testing

- [ ] ZIP tests
- [ ] Download tests
- [ ] Vision tests
- [ ] Parser tests
- [ ] Name matching tests
- [ ] Vehicle matching tests
- [ ] Verification tests
- [ ] End-to-end tests
- [ ] Failure tests
- [ ] Security tests

## Deployment

- [ ] Environment variables
- [ ] Google credentials
- [ ] Health check
- [ ] Production logging
- [ ] Dependency management
- [ ] Deployment configuration
- [ ] README
- [ ] Production smoke test

---

# 60. Copy-Paste Prompt for the Coding Agent

> Build a new **Single-Service Driver Document Verification Microservice** (`document-verification-service`) using FastAPI.
>
> In the platform architecture, this service acts as an autonomous microservice consumed by upstream APIs (e.g., API Gateway, Partner Onboarding Service). Internally, it must execute the complete verification pipeline within a single runtime (zero internal network hops). Do NOT split it into multiple microservices (e.g. separate OCR or Aadhaar services).
>
> The microservice receives a JSON payload containing `driver_id`, `mobile_number`, `vehicle_class`, and optional password-protected ZIP URLs for Aadhaar, Driving Licence, PAN, and RC documents.
>
> The ZIP password is the driver's `mobile_number`.
>
> Implement the service with clean internal separation:
>
> 1. Ingress & API validation (`src/api/`, `src/schemas/`)
> 2. Secure S3 presigned downloading (`src/clients/s3_download_client.py`)
> 3. Password-protected ZIP extraction (`src/extraction/zip_extractor.py`)
> 4. Temporary file lifecycle management (`src/utils/temp_manager.py`)
> 5. Google Cloud Vision OCR integration (`src/clients/vision_ai_client.py`)
> 6. Document classification (`src/extraction/document_classifier.py`)
> 7. Aadhaar extraction (`src/extraction/extractors/aadhaar_extractor.py`)
> 8. PAN extraction (`src/extraction/extractors/pan_extractor.py`)
> 9. Driving Licence extraction (`src/extraction/extractors/licence_extractor.py`)
> 10. RC extraction (`src/extraction/extractors/rc_extractor.py`)
> 11. Field normalization (`src/normalization/`)
> 12. Name matching (`src/verification/matchers/name_matcher.py`)
> 13. Vehicle-class mapping & matching (`src/normalization/vehicle_normalizer.py`, `src/verification/matchers/vehicle_matcher.py`)
> 14. Deterministic cross-verification & decision engine (`src/verification/cross_validator.py`, `src/verification/decision_engine.py`)
> 15. Global error handling & domain exceptions (`src/core/exceptions.py`)
> 16. Structured JSON logging with zero PII leakage (`src/core/logger.py`)
>
> Use Google Cloud Vision primarily for OCR. Do not ask Vision or an LLM to make the final verification decision. The microservice itself must perform deterministic verification.
>
> Required verification rules:
>
> - Aadhaar name must match PAN name.
> - Aadhaar name must match Driving Licence name.
> - RC vehicle class must match the `vehicle_class` supplied by the API.
>
> Normalize names before comparison using lowercase, Unicode normalization, whitespace cleanup, punctuation handling, token comparison, and configurable fuzzy matching thresholds where appropriate.
>
> Normalize vehicle classes using a centralized configurable mapping. For example, `MCWG`, `motorcycle`, `scooter`, and similar RC terminology map to `2 wheeler`, while `LMV` maps to `car`.
>
> The final decision engine must be the only component responsible for `VERIFIED` vs `REJECTED`.
>
> Distinguish processing failures (`ERROR`) from successful processing with failed verification (`REJECTED`).
>
> Never log complete Aadhaar numbers, PAN numbers, licence numbers, OCR text, mobile numbers, or presigned S3 URLs.
>
> Downloaded ZIP files and extracted documents must be stored only temporarily and deleted after processing.
>
> Implement security protections including HTTPS validation, download size limits, extraction size limits, file-count limits, ZIP Slip/path traversal protection, timeouts, safe temporary-directory handling, and appropriate SSRF protection.
>
> Create:
>
> ```text
> document-verification-service/
> ├── deploy/ (Dockerfile, docker-compose.yml, k8s manifests)
> ├── src/
> │   ├── main.py
> │   ├── api/ (v1 router, verification endpoint, health/ready probes)
> │   ├── clients/ (vision_ai_client.py, s3_download_client.py)
> │   ├── extraction/ (zip_extractor, classifier, extractors for aadhaar, pan, licence, rc)
> │   ├── normalization/ (name, vehicle, date normalizers)
> │   ├── verification/ (cross_validator, matchers, decision_engine)
> │   ├── schemas/ (request, response, document DTOs)
> │   ├── core/ (config, security, logger, exceptions)
> │   └── utils/ (temp_manager, image_utils)
> ├── tests/ (unit, integration, e2e)
> ├── requirements.txt
> └── README.md
> ```
>
> Include:
>
> - `POST /api/v1/verify-driver` (Single driver verification)
> - `POST /api/v1/batch-verify` (Concurrent batch driver verification with `asyncio.Semaphore` pool)
> - `GET /health` (liveness) & `GET /ready` (readiness)
> - Pydantic v2 request/response models (`DriverVerificationRequest`, `BatchDriverVerificationRequest`, `DriverVerificationResponse`, `BatchDriverVerificationResponse`)
> - Environment-based configuration (`pydantic-settings` with `MAX_CONCURRENT_WORKERS`, `MAX_BATCH_SIZE`)
> - Google Cloud Vision integration isolated inside `src/clients/vision_ai_client.py`
> - Mocked Vision tests so unit tests do not make paid API calls
> - Multi-stage Dockerfile and deployment configurations
> - Comprehensive README with setup, Google Cloud credentials, API usage, architecture, and container deployment
>
> Keep API route handlers thin and delegate all processing to internal domain components.
>
> Implement incrementally in this order:
>
> **Foundation → file downloading/extraction → Vision OCR client → document extraction → normalization → cross-verification → single & batch API integration → containerization/security → tests/documentation.**
>
> Before writing code, inspect the requirements and produce a concise implementation checklist. Then implement each component with clean interfaces and automated tests.
