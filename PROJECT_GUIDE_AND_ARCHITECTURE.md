# Driver Document Verification Microservice — Complete Master Guide & Architecture

> **Who this document is for**: Anyone from a developer, engineer, product manager, QA, or architect to someone with **zero prior knowledge** of this project. Reading this single file will give you a complete, crystal-clear understanding of what this system does, how every single file works, how data flows end-to-end, the business verification rules, and how to run and test it.

---

## Table of Contents
1. [High-Level Story & The Problem We Solve](#1-high-level-story--the-problem-we-solve)
2. [How the System Works in 30 Seconds (The Big Picture)](#2-how-the-system-works-in-30-seconds-the-big-picture)
3. [End-to-End Data Flow Diagrams & Step-by-Step Execution](#3-end-to-end-data-flow-diagrams--step-by-step-execution)
   - [Workflow A: Direct Image File Upload (Local/Swagger Testing)](#workflow-a-direct-image-file-upload-localswagger-testing)
   - [Workflow B: Cloud Production S3 Presigned ZIP URLs](#workflow-b-cloud-production-s3-presigned-zip-urls)
   - [Workflow C: High-Throughput Batch Processing](#workflow-c-high-throughput-batch-processing)
4. [Document Field Extraction & Classification Reference](#4-document-field-extraction--classification-reference)
5. [The Verification Engine & Business Matching Rules](#5-the-verification-engine--business-matching-rules)
6. [Exhaustive File-by-File & Folder-by-Folder Guide](#6-exhaustive-file-by-file--folder-by-folder-guide)
   - [Root Files](#root-files)
   - [deploy/ (Docker & Kubernetes Deployment)](#deploy-docker--kubernetes-deployment)
   - [src/core/ (Config, Security, Logging, Exceptions)](#srccore-config-security-logging-exceptions)
   - [src/schemas/ (Data Transfer Objects & Models)](#srcschemas-data-transfer-objects--models)
   - [src/clients/ (Google Vision & S3 Clients)](#srcclients-google-vision--s3-clients)
   - [src/extraction/ (ZIP Unpacker & Document Extractors)](#srcextraction-zip-unpacker--document-extractors)
   - [src/normalization/ (Text, Date & Vehicle Normalization)](#srcnormalization-text-date--vehicle-normalization)
   - [src/verification/ (Matchers, Decision Engine & Orchestrator)](#srcverification-matchers-decision-engine--orchestrator)
   - [src/api/ (FastAPI Routing & Ingress)](#srcapi-fastapi-routing--ingress)
   - [src/utils/ (Image Rotation & Temporary Sandboxes)](#srcutils-image-rotation--temporary-sandboxes)
   - [result/ (Raw OCR Persistence)](#result-raw-ocr-persistence)
   - [tests/ (Automated Unit, Integration & E2E Test Suite)](#tests-automated-unit-integration--e2e-test-suite)
7. [Deep Technical Challenges & How They Were Solved](#7-deep-technical-challenges--how-they-were-solved)
8. [API Endpoints & Practical Usage Examples](#8-api-endpoints--practical-usage-examples)
9. [How to Run and Test Locally](#9-how-to-run-and-test-locally)
10. [Beginner's Glossary](#10-beginners-glossary)

---

## 1. High-Level Story & The Problem We Solve

### The Real-World Scenario
Imagine you are building a ride-hailing or logistics platform (like Uber, Ola, Porter, Rapido, or Zomato). Every day, thousands of new drivers sign up to deliver goods or transport passengers.

To operate legally and prevent fraud, each driver must submit 4 official Indian documents:
1. **Aadhaar Card** (Identity proof with citizen name and date of birth)
2. **PAN Card** (Tax identity issued by the Income Tax Department)
3. **Driving Licence (DL)** (Legal authority to drive vehicles, issued by State RTOs)
4. **Registration Certificate (RC)** (Vehicle ownership paper showing vehicle class and fitness)

### The Old Way (Manual Verification)
In the past, human operations teams had to open every image manually:
- **Painfully Slow**: Taking 24 to 72 hours to onboard a driver.
- **Error-Prone & Costly**: Operators often missed fake names or forged documents.
- **Safety Hazards**: A driver approved for a small motorcycle might register a 10-ton commercial truck that they are not licensed to drive.

### The New Way: Autonomous Vision AI Verification Microservice
This project is an automated, secure, production-grade **FastAPI microservice** (`document-verification-service`). 
When a driver submits their documents:
- The system reads the documents using **Google Cloud Vision OCR**.
- It extracts the driver's name, dates, vehicle types, and validity dates.
- It normalizes name spellings and vehicle categories (e.g. recognizing that `GOODS CARRIER (LGV)` means `truck`).
- It compares the names and vehicle classes across all documents using smart fuzzy matching and subset matching.
- In **under 3 seconds**, it produces a deterministic decision: **`VERIFIED`** or **`REJECTED`** with exact explanations.

---

## 2. How the System Works in 30 Seconds (The Big Picture)

```text
[ Driver Submits Images / Encrypted ZIPs ]
                    │
                    ▼
       1. INGESTION & DECRYPTION
   (Saves files to isolated temp sandbox;
    decrypts with driver's mobile number)
                    │
                    ▼
       2. IMAGE PREPROCESSING & OCR
   (Auto-corrects photo rotation with EXIF;
    sends images to Google Cloud Vision API;
    saves raw text audit to result/ folder)
                    │
                    ▼
       3. CLASSIFICATION & EXTRACTION
   (Identifies Aadhaar vs PAN vs Licence vs RC;
    extracts Name, DOB, Vehicle Class, Validity)
                    │
                    ▼
       4. NORMALIZATION & STANDARDIZATION
   (Cleans Unicode, strips honorifics 'Mr/Shri',
    maps vehicle class aliases into canonical types)
                    │
                    ▼
       5. DETERMINISTIC VERIFICATION ENGINE
   • Aadhaar Name  <──(Fuzzy/Subset Match >= 85)──>  PAN Name
   • Aadhaar Name  <──(Fuzzy/Subset Match >= 85)──>  Licence Name
   • RC Vehicle Class  <──(Canonical Equality)──>  Applied Class
                    │
                    ▼
       6. INSTANT JSON DECISION
   • If all rules pass  ──►  "status": "VERIFIED"
   • If any rule fails  ──►  "status": "REJECTED" (with failure codes)
                    │
                    ▼
       7. AUTOMATIC CLEANUP
   (Temporary images & files deleted immediately; zero disk residue)
```

---

## 3. End-to-End Data Flow Diagrams & Step-by-Step Execution

### Comprehensive Architecture Flowchart

```mermaid
graph TD
    Client[Client / Gateway / Swagger UI] -->|HTTP Request| API[FastAPI Ingress Router]
    
    subgraph Ingestion_Sandboxing["1. Ingestion & Sandboxing"]
        API -->|Direct File Upload| DirectHandler[Direct Multipart Handler]
        API -->|Presigned S3 URLs| S3Downloader[S3 Download Client]
        DirectHandler --> TempDir[TempDirectoryContext: Isolated Disk Sandbox]
        S3Downloader -->|SSRF Check + AES Decrypt| TempDir
        TempDir --> ImageUtils[ImageUtils: EXIF Orientation Transpose]
    end

    subgraph Vision_OCR["2. Vision AI OCR"]
        ImageUtils -->|Clean JPEG Bytes| VisionClient[Google Cloud Vision Client]
        VisionClient -->|document_text_detection| RawText[Raw OCR Text Extracted]
        RawText -->|Persist for Audit| ResultFolder[(result/{driver_id}_ocr_extracted.json)]
    end

    subgraph Classification_Extraction["3. Document Extraction"]
        RawText --> Classifier[Document Classifier]
        Classifier -->|Aadhaar Text| ExtAadhaar[Aadhaar Extractor]
        Classifier -->|PAN Text| ExtPAN[PAN Extractor]
        Classifier -->|Licence Text| ExtLicence[Licence Extractor]
        Classifier -->|RC Text| ExtRC[RC Extractor]
        
        ExtAadhaar --> DataAadhaar[Aadhaar: Name, DOB]
        ExtPAN --> DataPAN[PAN: Name, Father Name, DOB]
        ExtLicence --> DataLicence[DL: Name, Issue Dt, Validity, Classes]
        ExtRC --> DataRC[RC: Name, Vehicle Class, Reg Dt, Validity]
    end

    subgraph Normalization["4. Normalization"]
        DataAadhaar --> NormName[Name Normalizer: Unicode NFKC, strip Mr/Shri, sort tokens]
        DataPAN --> NormName
        DataLicence --> NormName
        DataRC --> NormVehicle[Vehicle Normalizer: Aliases to Canonical Class]
    end

    subgraph Decision_Engine["5. Cross-Verification Engine"]
        NormName --> NameMatcher[Name Matcher: Exact, Token Set, Token Subset, RapidFuzz]
        NormVehicle --> VehicleMatcher[Vehicle Matcher: Canonical Comparison]
        NameMatcher --> Decision[Decision Engine]
        VehicleMatcher --> Decision
    end

    subgraph Output["6. Decision Output & Teardown"]
        Decision --> ResultJSON{All Match Rules Pass?}
        ResultJSON -->|YES| VerifiedResp[Status: VERIFIED]
        ResultJSON -->|NO| RejectedResp[Status: REJECTED + Rejection Codes]
        VerifiedResp --> HTTPResponse[HTTP 200 JSON Response]
        RejectedResp --> HTTPResponse
        HTTPResponse --> AutoCleanup[Context Manager Deletes Temp Directory]
    end
```

---

### Workflow A: Direct Image File Upload (Local/Swagger Testing)
1. The developer or tester visits Swagger UI at `http://localhost:8000/docs`.
2. They select endpoint `POST /api/v1/verify-driver-files`.
3. They enter `driver_id`, `mobile_number`, `vehicle_class` (e.g. `truck`), and attach direct image files: `adhar_front`, `adhar_back`, `pan_front`, `licence_front`, `licence_back`, `rc_front`, `rc_back`.
4. `verification.py` creates a unique temporary folder (`temp_manager.py`).
5. `cross_validator.py` calls `image_utils.py` to auto-rotate phone photos upright.
6. The images are sent to `vision_ai_client.py` which calls Google Vision API.
7. The extracted text is saved to `result/{driver_id}_ocr_extracted.json`.
8. The extractors pull fields and matchers evaluate rules.
9. An HTTP 200 response is returned with the verification verdict.
10. The temporary directory is completely wiped from disk.

### Workflow B: Cloud Production S3 Presigned ZIP URLs
1. An upstream API Gateway sends a JSON payload to `POST /api/v1/verify-driver`.
2. The payload contains HTTPS presigned S3 URLs to password-encrypted ZIP files for each document.
3. `s3_download_client.py` validates that the URLs are secure (blocks SSRF attacks against private IP addresses or AWS metadata).
4. `s3_download_client.py` downloads the ZIP files with strict size limits (50 MB max).
5. `zip_extractor.py` unpacks the ZIPs using the driver's `mobile_number` as the password.
6. It enforces Zip Slip security checks (preventing files from unpacking outside the temporary directory).
7. Unpacked images undergo Vision AI OCR, extraction, normalization, and verification.
8. The temporary sandbox is purged.

### Workflow C: High-Throughput Batch Processing
1. Upstream services send up to 50 drivers in one call to `POST /api/v1/batch-verify`.
2. `cross_validator.py` uses an `asyncio.Semaphore(5)` concurrency pool.
3. It processes up to 5 drivers simultaneously in parallel without overloading system memory or hitting Google Vision rate limits.
4. **Fault Isolation**: If driver #3 has a corrupted ZIP or invalid password, only driver #3 receives an `ERROR` or `REJECTED` status; drivers #1, #2, #4, and #5 continue processing normally.
5. The endpoint returns an aggregated summary (`total_count`, `verified_count`, `rejected_count`, `error_count`, `processing_time_ms`) along with individual driver results.

---

## 4. Document Field Extraction & Classification Reference

The user requirements specify exact fields that must be extracted from each document:

| Document | Extracted Fields | Keywords & Patterns Used by Extractor |
|---|---|---|
| **Aadhaar Card** | • **Name**<br>• **Date of Birth (DOB)** | Keywords: `DOB:`, `Year of Birth:`, `Government of India`, `UIDAI`. Filters out headers to identify the citizen's legal name. |
| **PAN Card** | • **Name**<br>• **Father's Name**<br>• **Date of Birth (DOB)** | Keywords: `INCOME TAX DEPARTMENT`, `GOVT. OF INDIA`, `Permanent Account Number`, `Father's Name:`, `DOB:`. Distinguishes citizen name from father's name. |
| **Driving Licence** | • **Name**<br>• **Issue Date**<br>• **Validity Date**<br>• **Vehicle Classes (COV)** | Keywords: `UNION OF INDIA`, `DRIVING LICENCE`, `DOI:`, `Issue Date:`, `Validity (NT)`, `Valid Upto:`, `COV:`, `LMV`, `MCWG`, `TRANS`, `3W-CAB`. |
| **Registration Certificate (RC)** | • **Owner Name**<br>• **Vehicle Class**<br>• **Date of Registration**<br>• **Registration Validity** | Keywords: `REGISTRATION CERTIFICATE`, `Owner Name:`, `Class of Vehicle:`, `GOODS CARRIER`, `LMV`, `MCWG`, `Date of Regn:`, `Reg. Date:`, `Fitness Upto:`, `Tax Upto:`. |

---

## 5. The Verification Engine & Business Matching Rules

The decision engine applies **3 core deterministic verification rules**. All 3 must pass for a driver to achieve `VERIFIED` status:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ RULE 1: Aadhaar Name  <───>  PAN Name                                  │
│ Threshold: Match Score >= 85                                            │
│ Failure Code: PAN_NAME_MISMATCH                                         │
├─────────────────────────────────────────────────────────────────────────┤
│ RULE 2: Aadhaar Name  <───>  Licence Name                               │
│ Threshold: Match Score >= 85 (Includes Token Subset Match)              │
│ Failure Code: DL_NAME_MISMATCH                                          │
├─────────────────────────────────────────────────────────────────────────┤
│ RULE 3: RC Vehicle Class  <───>  Applied Vehicle Class                  │
│ Rule: Canonical Vehicle Match (e.g. 'GOODS CARRIER' == 'truck')         │
│ Failure Code: VEHICLE_CLASS_MISMATCH                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Multi-Tiered Name Matching Explained

Indian names present real-world variations across different identity cards:
- **Honorifics**: "Shri", "Smt", "Mr", "Dr" may appear on some cards but not others.
- **Word Order**: "Patil Jitendra Narayan" (Surname First) vs "Jitendra Narayan Patil".
- **Spelling / Transliteration**: "Jeetendra" vs "Jitendra", "Choudhary" vs "Choudhari".
- **Omission of Middle / Father's Name**: Aadhaar often includes the father's name as a middle name (`Patil Jeetendra Narayan`), while Driving Licences frequently show only First Name + Surname (`JITENDRA PATIL`).

Our name matcher (`src/verification/matchers/name_matcher.py`) evaluates 5 intelligent levels:
1. **Level 1 (Exact Match)**: Case-insensitive direct string equality (Score: 100).
2. **Level 2 (Token Set Match)**: Name tokens are identical, regardless of order (Score: 100).
3. **Level 3 (Initials-Tolerant Match)**: Matches names with abbreviated initials like `J. N. Patil` against `Jitendra Narayan Patil` (Score: 98).
4. **Level 3.5 (Token Subset Match)**: Verifies that every token in the shorter name (`JITENDRA PATIL`) is present in the longer name (`Patil Jeetendra Narayan`), tolerating minor transliteration differences (`i` vs `ee`). If all tokens match with score >= 80 and average >= 85, this passes with **Score: 91.2%**.
5. **Level 4 (RapidFuzz Token Sort Ratio)**: Levenshtein distance calculation across sorted tokens. If the score is >= 85, it passes.

### Canonical Vehicle Class Mapping Explained

Indian RTOs register commercial and private vehicles under hundreds of non-standard labels. Our configuration (`src/core/config.py`) maps them all into 4 canonical categories:
- **`truck`**: `"goods carrier"`, `"good carrier"`, `"goods vehicle"`, `"lgv"`, `"mgv"`, `"hgv"`, `"truck"`, `"tipper"`, `"tractor"`.
- **`car`**: `"lmv"`, `"light motor vehicle"`, `"lmv-nt"`, `"car"`, `"motor car"`, `"taxi"`, `"cab"`.
- **`2 wheeler`**: `"mcwg"`, `"motor cycle with gear"`, `"m/cycl"`, `"two wheeler"`, `"scooter"`, `"moped"`.
- **`3 wheeler`**: `"auto rickshaw"`, `"3w"`, `"three wheeler"`, `"3w-cab"`, `"e-rickshaw"`.

If a driver applies to drive a `truck` and their RC specifies `GOODS CARRIER (LGV)`, the system normalizes both to `truck` and records a **100% match**.

---

## 6. Exhaustive File-by-File & Folder-by-Folder Guide

Here is a complete breakdown of every file in the repository:

```text
vision_ai/
├── .env                                # Local secrets & configuration
├── .env.example                        # Template for environment configuration
├── .gitignore                          # Git file exclusion rules
├── pytest.ini                          # Testing framework configuration
├── README.md                           # Quickstart guide
├── requirements.txt                    # Pinned Python package dependencies
├── driver_document_verification_implementation_plan.md  # Final implementation plan
├── PROJECT_GUIDE_AND_ARCHITECTURE.md   # This master guide
├── r.txt                               # Sample OCR raw text
│
├── deploy/                             # Cloud & Container Deployment
│   ├── Dockerfile                      # Multi-stage secure container build
│   ├── docker-compose.yml              # Local container orchestration
│   └── k8s-deployment.yaml             # Kubernetes deployment & service spec
│
├── src/                                # Microservice Source Code
│   ├── main.py                         # FastAPI app entrypoint
│   │
│   ├── core/                           # Foundation Layer
│   │   ├── config.py                   # Pydantic Settings & vehicle mappings
│   │   ├── security.py                 # SSRF validator & PII maskers
│   │   ├── logger.py                   # Zero-PII JSON structured logger
│   │   └── exceptions.py               # Custom domain error types
│   │
│   ├── schemas/                        # Data Transfer Objects (Pydantic v2)
│   │   ├── request_schemas.py          # Input validation models
│   │   ├── document_schemas.py         # Extracted document models
│   │   └── response_schemas.py         # Output response models
│   │
│   ├── clients/                        # External Cloud Integrations
│   │   ├── vision_ai_client.py         # Google Cloud Vision OCR SDK client
│   │   └── s3_download_client.py       # Safe streaming HTTPS S3 client
│   │
│   ├── extraction/                     # File Processing & Parsers
│   │   ├── zip_extractor.py            # Password-protected ZIP unpacker
│   │   ├── document_classifier.py      # Identifies document types
│   │   └── extractors/                 # Individual document extractors
│   │       ├── base_extractor.py       # Extractor abstract base class
│   │       ├── aadhaar_extractor.py    # Extracts Name & DOB
│   │       ├── pan_extractor.py        # Extracts Name, Father Name & DOB
│   │       ├── licence_extractor.py    # Extracts Name, Dates & COV classes
│   │       └── rc_extractor.py         # Extracts Name, Vehicle Class & Dates
│   │
│   ├── normalization/                  # Entity Standardization
│   │   ├── name_normalizer.py          # Cleans Unicode, honorifics, initials
│   │   ├── vehicle_normalizer.py       # Standardizes vehicle class aliases
│   │   └── date_normalizer.py          # Standardizes dates to ISO format
│   │
│   ├── verification/                   # Decision Engine Layer
│   │   ├── matchers/
│   │   │   ├── name_matcher.py         # 5-level multi-tier name comparison
│   │   │   └── vehicle_matcher.py      # Canonical vehicle equality comparison
│   │   ├── decision_engine.py          # Deterministic rules & status evaluator
│   │   └── cross_validator.py          # Master verification orchestrator
│   │
│   ├── api/                            # HTTP Web Layer
│   │   ├── dependencies.py             # Dependency injection singletons
│   │   └── v1/
│   │       ├── router.py               # Aggregates v1 sub-routes
│   │       └── endpoints/
│   │           ├── health.py           # /health and /ready probes
│   │           └── verification.py     # Verification API routes
│   │
│   └── utils/                          # Lifecycle & Helper Utilities
│       ├── temp_manager.py             # Ephemeral temporary directory sandbox
│       └── image_utils.py              # Photo validation & EXIF auto-rotation
│
├── result/                             # Raw OCR Text Persistence
│   └── {driver_id}_ocr_extracted.json  # Raw OCR strings saved per driver
│
└── tests/                              # Automated Test Suite (50 Tests)
    ├── conftest.py                     # Mock fixtures & test clients
    ├── test_foundation.py              # Foundation config & schema sanity tests
    ├── unit/                           # Isolated unit tests
    │   ├── test_download_client.py
    │   ├── test_zip_extractor.py
    │   ├── test_vision_client.py
    │   ├── test_extractors.py
    │   ├── test_normalizers.py
    │   └── test_verification.py
    ├── integration/                    # Multi-component integration tests
    │   └── test_verification_flow.py
    └── e2e/                            # End-to-end HTTP scenario tests
        └── test_api_endpoints.py
```

---

### Root Files

#### [[requirements.txt](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/requirements.txt)]
Defines all Python dependencies with pinned version numbers:
- `fastapi` & `uvicorn`: High-performance asynchronous web framework and ASGI server.
- `pydantic` & `pydantic-settings`: Data validation, serialization, and environment configuration.
- `google-cloud-vision`: Official Google Cloud Vision API SDK.
- `httpx`: Asynchronous HTTP client for downloading files from S3.
- `rapidfuzz`: High-speed C++ Levenshtein distance string matching.
- `pyzipper`: Secure ZIP library supporting AES-256 and ZipCrypto encryption.
- `pillow`: Python Imaging Library for EXIF rotation, resizing, and format conversion.
- `pypdf`: PDF page extraction and text processing.
- `pytest` & `pytest-asyncio`: Automated test runner and asynchronous test harness.

#### [[.env](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/.env)]
Local environment configuration containing sensitive credentials (e.g. `GOOGLE_VISION_API_KEY`). **Never checked into Git**.

#### [[.env.example](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/.env.example)]
Safe example template showing all available environment variables, default values, and setup instructions.

#### [[pytest.ini](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/pytest.ini)]
Configuration file for Pytest, setting `pythonpath = .` (to allow importing from `src/`) and enabling `asyncio_mode = auto`.

#### [[README.md](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/README.md)]
The project's public README containing quickstart instructions, environment setup, Docker commands, and API overviews.

#### [[driver_document_verification_implementation_plan.md](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/driver_document_verification_implementation_plan.md)]
The finalized design document specifying the 10 implementation phases, architectural requirements, and verification criteria.

---

### deploy/ (Docker & Kubernetes Deployment)

#### [[deploy/Dockerfile](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/deploy/Dockerfile)]
Production **Multi-Stage Dockerfile**:
- **Stage 1 (Builder)**: Compiles wheel dependencies using GCC and Python build tools.
- **Stage 2 (Runner)**: Uses minimal `python:3.12-slim`. Copies only compiled packages. Creates a dedicated non-root user (`appuser` with UID 10001) for security compliance. Sets up a Docker `HEALTHCHECK` probe against `/health`. Exposes port 8000.

#### [[deploy/docker-compose.yml](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/deploy/docker-compose.yml)]
Enables running the entire microservice locally via a single command: `docker compose up`. Maps port 8000, injects environment variables, and mounts local credentials safely.

#### [[deploy/k8s-deployment.yaml](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/deploy/k8s-deployment.yaml)]
Production Kubernetes Deployment and ClusterIP Service manifests:
- Defines resource requests (`250m` CPU, `512Mi` RAM) and limits (`1000m` CPU, `1Gi` RAM).
- Configures liveness probe (`/health`) and readiness probe (`/ready`).
- Mounts Google Cloud credentials from Kubernetes Secrets.

---

### src/core/ (Config, Security, Logging, Exceptions)

#### [[src/core/config.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/core/config.py)]
Central configuration hub powered by `pydantic-settings`:
- Loads environment variables (`GOOGLE_VISION_API_KEY`, `MAX_ARCHIVE_SIZE_MB`, `HTTP_TIMEOUT_SECONDS`, `NAME_SIMILARITY_THRESHOLD`).
- Contains the authoritative **`VEHICLE_CLASS_MAPPING`** dictionary which maps dozens of vehicle strings (`goods carrier`, `lmv`, `mcwg`, etc.) to canonical categories (`truck`, `car`, `2 wheeler`, `3 wheeler`).

#### [[src/core/security.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/core/security.py)]
Guards against security threats and data leakage:
- **`validate_safe_url(url)`**: Prevents **Server-Side Request Forgery (SSRF)**. Parses URL hostnames, resolves DNS, and blocks requests to loopback addresses (`127.0.0.1`, `localhost`), private RFC1918 networks (`10.0.0.0/8`, `192.168.0.0/16`), link-local IPs, and cloud metadata endpoints (`169.254.169.254`).
- **PII Masking**: Functions `mask_aadhaar` (replaces all but last 4 digits), `mask_pan`, and `mask_mobile` to ensure sensitive driver numbers are never exposed.

#### [[src/core/logger.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/core/logger.py)]
**Zero-PII Structured JSON Logger**:
- Emits logs formatted as single-line JSON objects with timestamps, log levels, and messages.
- Uses regex filters to automatically mask phone numbers, Aadhaar numbers, and presigned query strings before writing to stdout. Guarantees zero sensitive data leakage into cloud log monitors like Datadog, AWS CloudWatch, or Google Cloud Logging.

#### [[src/core/exceptions.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/core/exceptions.py)]
Defines clean domain-specific exceptions:
- `VerificationServiceException` (Base class)
- `DownloadException` (S3 download failure or timeout)
- `ZipExtractionException` (Corrupted archive)
- `InvalidZipPasswordException` (Wrong mobile number password)
- `SecurityViolationException` (SSRF attempt or Zip Slip attack detected)
- `VisionApiException` (Google Cloud Vision network or permission error)

---

### src/schemas/ (Data Transfer Objects & Models)

#### [[src/schemas/request_schemas.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/schemas/request_schemas.py)]
Input validation models using Pydantic v2:
- **`DriverVerificationRequest`**: Validates `driver_id`, ensures `mobile_number` is exactly 10 digits, validates `vehicle_class`, and verifies that S3 URLs use the secure `https://` protocol.
- **`BatchDriverVerificationRequest`**: Validates an array of driver requests, enforcing batch sizes between 1 and 50 drivers.

#### [[src/schemas/document_schemas.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/schemas/document_schemas.py)]
Internal data structures representing OCR results and extracted fields:
- `OCRBlock`: A single text block with bounding box coordinates and confidence score.
- `OCRResult`: Full text string, list of blocks, and image dimensions.
- `AadhaarData`: `{name, dob}`.
- `PanData`: `{name, father_name, dob}`.
- `LicenceData`: `{name, issue_date, validity, vehicle_classes}`.
- `RcData`: `{name, vehicle_class, date_of_registration, registration_validity}`.

#### [[src/schemas/response_schemas.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/schemas/response_schemas.py)]
Output JSON models returned to the client:
- `MatchResult`: Boolean `match`, numerical `score` (0-100), and textual `details`.
- `AadhaarDocumentStatus`: `{processed, name, dob}`.
- `PanDocumentStatus`: `{processed, name, father_name, dob}`.
- `LicenceDocumentStatus`: `{processed, name, issue_date, validity, vehicle_classes}`.
- `RcDocumentStatus`: `{processed, name, vehicle_class, date_of_registration, registration_validity}`.
- `DriverVerificationResponse`: Full result containing `driver_id`, `status` (`VERIFIED` or `REJECTED`), `rejection_reasons`, `documents`, `name_verification`, `vehicle_verification`, and `processing_time_ms`.
- `BatchDriverVerificationResponse`: Aggregated batch response with counts and individual driver results.

---

### src/clients/ (Google Vision & S3 Clients)

#### [[src/clients/vision_ai_client.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/clients/vision_ai_client.py)]
**Google Cloud Vision SDK Client**:
- The **only** file in the codebase that communicates with Google Cloud Vision API.
- Supports two authentication methods:
  1. Direct API Key string (`GOOGLE_VISION_API_KEY`) via `google.api_core.client_options.ClientOptions`.
  2. Google Service Account credentials JSON file (`GOOGLE_APPLICATION_CREDENTIALS`).
- Loads images via Pillow, converts them into standard JPEG bytes, and calls `image_annotator_client.document_text_detection`.
- Extracts full text and bounding-box text blocks, returning a structured `OCRResult`.

#### [[src/clients/s3_download_client.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/clients/s3_download_client.py)]
**Safe Streaming S3 Downloader**:
- Downloads presigned ZIP URLs using an asynchronous `httpx.AsyncClient`.
- Validates every URL with `validate_safe_url` to prevent SSRF.
- Streams response chunks to disk while enforcing a strict maximum size limit (50 MB) to prevent denial-of-service via decompression bombs.

---

### src/extraction/ (ZIP Unpacker & Document Extractors)

#### [[src/extraction/zip_extractor.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/extraction/zip_extractor.py)]
**Secure Encrypted Archive Unpacker**:
- Uses `pyzipper` to decrypt both legacy ZipCrypto and AES-256 encrypted archives using the driver's `mobile_number` as the password.
- **Zip Slip Protection**: Checks every file path inside the archive to ensure it cannot escape into parent directories (`../`).
- Limits the number of extracted files (maximum 50) and total uncompressed size (maximum 100 MB).

#### [[src/extraction/document_classifier.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/extraction/document_classifier.py)]
**Document Type Classifier**:
- Analyzes the OCR text using regex word-boundary keyword searches:
  - Aadhaar: `AADHAAR`, `UIDAI`, `GOVERNMENT OF INDIA`.
  - PAN: `INCOME TAX DEPARTMENT`, `PERMANENT ACCOUNT NUMBER`.
  - Licence: `DRIVING LICENCE`, `UNION OF INDIA`, `TRANSPORT`.
  - RC: `REGISTRATION CERTIFICATE`, `FORM 23`, `CHASSIS`.
- Merges OCR keywords with filename/hint metadata to reliably classify front and back document images.

#### [[src/extraction/extractors/base_extractor.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/extraction/extractors/base_extractor.py)]
Abstract base class defining the standard interface `.extract(ocr_result)` that all document extractors must implement.

#### [[src/extraction/extractors/aadhaar_extractor.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/extraction/extractors/aadhaar_extractor.py)]
Extracts fields from Aadhaar Card text:
- **Name**: Scans text lines preceding the DOB line, discarding UIDAI government headers and non-name phrases.
- **DOB**: Searches for date patterns (`DD/MM/YYYY`) following keywords like `DOB:`, `Year of Birth:`, or `D.O.B`.

#### [[src/extraction/extractors/pan_extractor.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/extraction/extractors/pan_extractor.py)]
Extracts fields from PAN Card text:
- **Name**: Identifies the primary citizen's name above the father's name line.
- **Father's Name**: Scans lines following the label `Father's Name:` or identifies the second prominent capitalized line.
- **DOB**: Extracts date matching `DD/MM/YYYY` following `DOB:` or `Date of Birth:`.

#### [[src/extraction/extractors/licence_extractor.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/extraction/extractors/licence_extractor.py)]
Extracts fields from Driving Licence text:
- **Name**: Finds lines following `Name:` or identifies the holder's name below the state transport authority header.
- **Issue Date**: Extracts date associated with `DOI:` or `Date of Issue:`.
- **Validity**: Extracts non-transport (`NT`) or transport (`TR`) validity dates associated with `Valid Upto:`.
- **Vehicle Classes (COV)**: Regex search across standard classes (`LMV`, `MCWG`, `TRANS`, `3W-CAB`, `HGMV`, `PSV`).

#### [[src/extraction/extractors/rc_extractor.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/extraction/extractors/rc_extractor.py)]
Extracts fields from Registration Certificate text:
- **Owner Name**: Scans text following `Owner Name:`, `Name:`, or `Registered Owner:`.
- **Vehicle Class**: Searches for labels like `Class of Vehicle:`, `Vehicle Class:`, or matches known classes like `GOODS CARRIER`, `MOTOR CAR`, `MOTOR CYCLE`.
- **Registration Date**: Extracts date following `Reg. Date:`, `Date of Regn:`.
- **Validity**: Extracts expiration date following `Fitness Upto:`, `Tax Upto:`.

---

### src/normalization/ (Text, Date & Vehicle Normalization)

#### [[src/normalization/name_normalizer.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/normalization/name_normalizer.py)]
Cleans and standardizes names:
- Converts Unicode characters to normalized NFKC representation.
- Strips punctuation and digits.
- Removes common Indian honorifics: `Mr`, `Mrs`, `Miss`, `Shri`, `Smt`, `Dr`.
- Strips standalone single-letter initials (e.g. `J` in `J Patil`).
- Sorts name tokens alphabetically for permutation-invariant comparison.

#### [[src/normalization/vehicle_normalizer.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/normalization/vehicle_normalizer.py)]
Maps raw vehicle strings from RCs or user input into standard canonical categories:
- Matches against the `VEHICLE_CLASS_MAPPING` dictionary.
- Translates `GOODS CARRIER (LGV)` into `truck`.
- Translates `MOTOR CYCLE WITH GEAR` into `2 wheeler`.
- Translates `LIGHT MOTOR VEHICLE` into `car`.

#### [[src/normalization/date_normalizer.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/normalization/date_normalizer.py)]
Converts heterogeneous Indian date formats (`DD-MM-YYYY`, `DD/MM/YYYY`, `YYYY-MM-DD`, `DD.MM.YYYY`) into standard ISO format (`YYYY-MM-DD`).

---

### src/verification/ (Matchers, Decision Engine & Orchestrator)

#### [[src/verification/matchers/name_matcher.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/verification/matchers/name_matcher.py)]
Implements the 5-tiered name matching engine:
- Level 1: Exact equality.
- Level 2: Token set match.
- Level 3: Initials-tolerant match.
- Level 3.5: **Token Subset Match** (resolves missing middle names and transliterations like `Patil Jeetendra Narayan` vs `JITENDRA PATIL`).
- Level 4: RapidFuzz Levenshtein token sort ratio.

#### [[src/verification/matchers/vehicle_matcher.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/verification/matchers/vehicle_matcher.py)]
Compares the driver's applied vehicle class against the normalized vehicle class extracted from their RC document.

#### [[src/verification/decision_engine.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/verification/decision_engine.py)]
The final decision maker:
- Evaluates the match scores against configured thresholds (default: 85).
- Verifies that all 3 verification rules have passed.
- Produces the final status: **`VERIFIED`** or **`REJECTED`**.
- Attaches exact machine-readable rejection reason codes (`PAN_NAME_MISMATCH`, `DL_NAME_MISMATCH`, `VEHICLE_CLASS_MISMATCH`, `MISSING_DOCUMENT`, etc.).

#### [[src/verification/cross_validator.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/verification/cross_validator.py)]
The **Master Pipeline Orchestrator**:
- Connects all components together: download, decrypt, image rotate, OCR, classify, extract, normalize, match, and decide.
- Handles single driver requests (`verify_driver`).
- Manages batch concurrency using `asyncio.Semaphore(5)` (`batch_verify_drivers`).
- Handles direct multipart file uploads (`verify_driver_from_files`).
- Saves the exact raw text returned by Vision AI to `result/{driver_id}_ocr_extracted.json`.

---

### src/api/ (FastAPI Routing & Ingress)

#### [[src/main.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/main.py)]
The FastAPI application root:
- Initializes the application with metadata and Swagger OpenAPI configuration.
- Sets up CORS middleware.
- Configures global exception handlers to convert uncaught errors into clean JSON responses.
- Mounts the `/api/v1` router.

#### [[src/api/dependencies.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/api/dependencies.py)]
FastAPI dependency injection provider. Creates and injects singleton instances of `CrossValidator` into route handlers.

#### [[src/api/v1/router.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/api/v1/router.py)]
Combines the verification endpoints and health probe endpoints under the `/api/v1` namespace.

#### [[src/api/v1/endpoints/health.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/api/v1/endpoints/health.py)]
DevOps health probe endpoints:
- `GET /health`: Liveness probe verifying the service process is running.
- `GET /ready`: Readiness probe verifying external configurations and services are ready.

#### [[src/api/v1/endpoints/verification.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/api/v1/endpoints/verification.py)]
Exposes the core verification API endpoints:
- `POST /verify-driver`: Single driver verification via S3 presigned URLs.
- `POST /batch-verify`: Concurrent batch verification (1-50 drivers).
- `POST /verify-driver-files`: Direct local file upload via multipart/form-data for Swagger testing.

---

### src/utils/ (Image Rotation & Temporary Sandboxes)

#### [[src/utils/temp_manager.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/utils/temp_manager.py)]
**Ephemeral Sandbox Context Manager (`TempDirectoryContext`)**:
- Creates a dedicated, uniquely named temporary directory for each incoming request.
- Automatically deletes the entire directory and all contained files when the request finishes (even if an error or exception occurs).
- Guarantees zero sensitive document files linger on server disks.

#### [[src/utils/image_utils.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/src/utils/image_utils.py)]
Image preprocessing and orientation utilities:
- **`ImageOps.exif_transpose`**: Reads mobile camera EXIF orientation tags and rotates sideways or upside-down photos upright before sending to OCR.
- Converts palette and RGBA images into clean RGB JPEGs.
- Extracts raster images from PDF pages using `pypdf`.

---

### result/ (Raw OCR Persistence)

#### `result/{driver_id}_ocr_extracted.json`
Every time Vision AI extracts text from a driver's documents, `cross_validator.py` saves a clean JSON file containing the driver's ID, timestamp, and the **exact raw text strings** returned by Google Vision API for Aadhaar, PAN, DL, and RC.

This allows developers to inspect the raw OCR text, debug keyword patterns, and verify extraction accuracy without reading server logs.

---

### tests/ (Automated Unit, Integration & E2E Test Suite)

The repository includes a test suite with **50 automated tests** passing in under 2 seconds:

- **[[tests/conftest.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/tests/conftest.py)]**: Shared Pytest fixtures that mock Google Cloud Vision API so tests execute quickly and without requiring paid API calls or an internet connection.
- **[[tests/test_foundation.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/tests/test_foundation.py)]**: Verifies configuration loading and Pydantic schema validation.
- **`tests/unit/test_download_client.py`**: Validates S3 downloader URL safety, SSRF blocking, and size limits.
- **`tests/unit/test_zip_extractor.py`**: Tests AES/ZipCrypto password decryption, wrong password rejection, and Zip Slip prevention.
- **`tests/unit/test_vision_client.py`**: Tests Vision AI client response parsing and error handling.
- **`tests/unit/test_extractors.py`**: Tests classification and field extraction on Aadhaar, PAN, DL, and RC text.
- **`tests/unit/test_normalizers.py`**: Tests Unicode cleaning, initials stripping, token sorting, and vehicle mapping.
- **`tests/unit/test_verification.py`**: Tests all matching levels (exact, token set, token subset, RapidFuzz) and decision engine rules.
- **`tests/integration/test_verification_flow.py`**: Tests the complete pipeline from encrypted ZIPs to final JSON verdict.
- **[[tests/e2e/test_api_endpoints.py](file:///c:/Users/parik/OneDrive/Desktop/vision_ai/tests/e2e/test_api_endpoints.py)]**: End-to-end tests covering all 8 production scenarios:
  1. Valid driver (Verified 200 OK)
  2. PAN name mismatch (Rejected 200 OK)
  3. DL name mismatch (Rejected 200 OK)
  4. Vehicle class mismatch (Rejected 200 OK)
  5. Invalid ZIP password (Error 200 OK)
  6. Vision API failure handling (503 / 200 error isolation)
  7. Concurrent batch processing (200 OK)
  8. Batch boundary validation (0 or >50 items rejected with 422)
  9. Direct multipart file upload endpoint (200 OK)

---

## 7. Deep Technical Challenges & How They Were Solved

### Challenge 1: The Indian Middle Name Omission Problem
**The Problem**: In India, Aadhaar and PAN cards almost always include the person's father's name as a middle name (e.g. `Patil Jeetendra Narayan`). However, State RTOs frequently omit the middle name on Driving Licences, printing only `JITENDRA PATIL`. Furthermore, English transliterations differ (`Jeetendra` with `ee` vs `Jitendra` with `i`).

**The Solution**: Standard `token_sort_ratio` scored this around ~70%, which fell below the 85 threshold and caused legitimate drivers to be rejected. We engineered **Level 3.5 Token Subset Matching**:
- It identifies the shorter name tokens (`JITENDRA`, `PATIL`).
- It verifies that every token in the shorter name matches a token in the longer name with high similarity (>= 80) and average score (>= 85).
- Result: The match is correctly accepted with a **91.2% score**.

### Challenge 2: Commercial Vehicle Class Heterogeneity
**The Problem**: A driver registers to operate a commercial `truck`. Their RC lists the vehicle class as `GOODS CARRIER (LGV)` or `GOODS VEHICLE`. A naive string comparison fails.

**The Solution**: We built a centralized vehicle normalization table in `src/core/config.py` that maps `goods carrier`, `goods vehicle`, `truck`, `tipper`, and `hgv` to canonical category `truck`. Both user input and RC text are normalized before comparison, yielding an exact match.

### Challenge 3: Sideways & Rotated Phone Photos
**The Problem**: Drivers take photos using smartphones. Mobile cameras often save photos with EXIF orientation metadata tags rather than rotating the physical pixel matrix. Standard image decoders might display them rotated 90° or 270°.

**The Solution**: In `src/utils/image_utils.py`, every image passes through `ImageOps.exif_transpose` which physically rotates the pixel array upright according to its EXIF tag before sending it to Vision API. In addition, Google Cloud Vision's `document_text_detection` natively identifies text at 90°, 180°, and 270° angles.

### Challenge 4: Security (SSRF, Zip Slip, Zero-PII)
**The Problem**: Processing user-submitted URLs and ZIP archives creates major attack vectors:
- Malicious presigned URLs could target internal cloud metadata services (`http://169.254.169.254/latest/meta-data/`).
- Malicious ZIP files could contain paths like `../../etc/passwd` (Zip Slip).
- Cloud logs could expose sensitive citizen Aadhaar and PAN numbers.

**The Solution**:
- `src/core/security.py` resolves DNS hostnames and rejects any request targeting private, loopback, link-local, or cloud metadata IPs before initiating an HTTP connection.
- `src/extraction/zip_extractor.py` resolves the absolute canonical path of every file in the ZIP to ensure it remains inside the isolated temporary directory.
- `src/core/logger.py` uses automated regex masking so that full Aadhaar, PAN, and phone numbers are never printed to logs.

---

## 8. API Endpoints & Practical Usage Examples

### 1. Direct Local File Upload (Swagger Interactive Testing)
* **Route**: `POST /api/v1/verify-driver-files`
* **Content-Type**: `multipart/form-data`
* **Purpose**: Allows uploading image files directly from your computer using Swagger UI (`http://localhost:8000/docs`).

**Form Parameters**:
- `driver_id`: e.g. `driver001`
- `mobile_number`: e.g. `9876543210`
- `vehicle_class`: e.g. `truck`
- `adhar_front`: Image file
- `adhar_back`: Image file
- `pan_front`: Image file
- `licence_front`: Image file
- `licence_back`: Image file
- `rc_front`: Image file
- `rc_back`: Image file

**Sample JSON Response**:
```json
{
  "driver_id": "driver001",
  "status": "VERIFIED",
  "rejection_reasons": [],
  "documents": {
    "aadhaar": {
      "processed": true,
      "name": "Patil Jeetendra Narayan",
      "dob": "08/09/1976"
    },
    "pan": {
      "processed": true,
      "name": "PATIL JITENDRA NARAYAN",
      "father_name": "NARAYAN PATIL",
      "dob": "08/09/1976"
    },
    "licence": {
      "processed": true,
      "name": "JITENDRA PATIL",
      "issue_date": "12/05/2010",
      "validity": "11/05/2030",
      "vehicle_classes": ["LMV", "TRANS"]
    },
    "rc": {
      "processed": true,
      "name": "JITENDRA PATIL",
      "vehicle_class": "GOODS CARRIER",
      "date_of_registration": "15/01/2019",
      "registration_validity": "14/01/2034"
    }
  },
  "name_verification": {
    "aadhaar_pan": {
      "match": true,
      "score": 93.3,
      "details": "Fuzzy match above threshold"
    },
    "aadhaar_licence": {
      "match": true,
      "score": 91.2,
      "details": "Token subset match (all tokens matched)"
    }
  },
  "vehicle_verification": {
    "provided_class": "truck",
    "rc_class": "truck",
    "match": true,
    "details": "Vehicle class verified"
  },
  "processing_time_ms": 2840.5
}
```

---

### 2. Single Driver Verification (S3 Presigned URLs)
* **Route**: `POST /api/v1/verify-driver`
* **Content-Type**: `application/json`

**Sample Request**:
```json
{
  "driver_id": "driver_123",
  "mobile_number": "9876543210",
  "vehicle_class": "car",
  "aadhaar_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/aadhaar.zip?AWSAccessKeyId=...",
  "pan_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/pan.zip?AWSAccessKeyId=...",
  "licence_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/dl.zip?AWSAccessKeyId=...",
  "rc_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/rc.zip?AWSAccessKeyId=..."
}
```

---

### 3. Concurrent Batch Verification
* **Route**: `POST /api/v1/batch-verify`
* **Content-Type**: `application/json`

**Sample Request**:
```json
{
  "batch_id": "batch_2026_09_08_001",
  "drivers": [
    {
      "driver_id": "driver_001",
      "mobile_number": "9876543210",
      "vehicle_class": "truck",
      "aadhaar_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d1_aadhaar.zip",
      "pan_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d1_pan.zip",
      "licence_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d1_dl.zip",
      "rc_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d1_rc.zip"
    },
    {
      "driver_id": "driver_002",
      "mobile_number": "9811122233",
      "vehicle_class": "car",
      "aadhaar_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d2_aadhaar.zip",
      "pan_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d2_pan.zip",
      "licence_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d2_dl.zip",
      "rc_zip_url": "https://s3.ap-south-1.amazonaws.com/my-bucket/d2_rc.zip"
    }
  ]
}
```

---

## 9. How to Run and Test Locally

### 1. Prerequisites
- Python 3.11 or 3.12 installed.
- Google Cloud Vision API key or Service Account JSON file.

### 2. Setting Up Environment
```powershell
# 1. Clone repository and enter folder
cd c:\Users\parik\OneDrive\Desktop\vision_ai

# 2. Activate Python Virtual Environment
.\venv\Scripts\Activate.ps1

# 3. Create or check your .env file
# Ensure GOOGLE_VISION_API_KEY is configured with an active billing project
```

### 3. Starting the Server
```powershell
# Start FastAPI with live reload on port 8000
python -m uvicorn src.main:app --reload --port 8000
```

### 4. Interactive Browser UI (Swagger)
Open your browser and navigate to:
```text
http://localhost:8000/docs
```
You can test `POST /api/v1/verify-driver-files` directly by attaching your test document images.

### 5. Running the Complete Automated Test Suite
```powershell
.\venv\Scripts\pytest.exe -v tests/
```
**Expected Result**:
```text
======================= 50 passed in 1.96s =======================
```

---

## 10. Beginner's Glossary

- **OCR (Optical Character Recognition)**: Technology that converts text in images or scanned documents into machine-readable digital text. Here, powered by Google Cloud Vision API.
- **PII (Personally Identifiable Information)**: Sensitive personal data like Aadhaar numbers, PAN numbers, and phone numbers. Our system protects PII by masking it in logs and deleting temporary files immediately.
- **FastAPI**: A modern, high-speed Python web framework for building APIs.
- **Microservice**: A specialized, independent software service designed to perform one focused task (in this case, driver document verification).
- **SSRF (Server-Side Request Forgery)**: A security attack where a hacker tricks a server into making unauthorized network requests to internal systems. We prevent this using `src/core/security.py`.
- **Zip Slip**: A vulnerability where a malicious ZIP archive unpacks files outside its target directory using directory traversal characters (`../`). We prevent this in `src/extraction/zip_extractor.py`.
- **Token Sort Ratio**: A string comparison method that breaks two names into individual words (tokens), sorts them alphabetically, and calculates how similar they are.
- **NFKC Normalization**: A Unicode standard that transforms special characters, ligatures, and symbols into their standard plain text equivalents.
- **Presigned URL**: A temporary, secure URL granted by Amazon S3 that allows downloading a private file without sharing permanent cloud credentials.
