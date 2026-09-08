# Driver Document Verification Microservice (`document-verification-service`)

A high-performance, single-service driver document verification microservice built with **FastAPI**. It handles secure ingestion of password-protected documents (Aadhaar, PAN, Driving Licence, and RC), executes OCR via **Google Cloud Vision API**, normalizes entities, and applies deterministic cross-verification rules with zero PII leakage.

---

## Architecture & Design Principles

### Single-Service Runtime (Zero Internal Network Hops)
This service functions as an autonomous microservice consumed by upstream onboarding platforms, API gateways, and admin portals. 

Internally, it executes all processing stages within a single, unified runtime container without micro-fragmentation. This design eliminates inter-service serialization overhead, network latency, and distributed point failures:

```text
       Driver Ingestion Payload (JSON)
                      │
                      ▼
   ┌────────────────────────────────────────────────────────┐
   │ 1. INGESTION & S3 DOWNLOAD (HTTPS, SSRF blocked)       │
   │                      │                                 │
   │ 2. PASSWORD-PROTECTED ZIP EXTRACTION (AES/ZipCrypto)   │
   │                      │                                 │
   │ 3. GOOGLE CLOUD VISION OCR (Image preparation)         │
   │                      │                                 │
   │ 4. DOCUMENT CLASSIFICATION & REGEX FIELD EXTRACTION    │
   │                      │                                 │
   │ 5. NORMALIZATION (Names, canonical vehicle classes)    │
   │                      │                                 │
   │ 6. DETERMINISTIC CROSS-VERIFICATION ENGINE             │
   └──────────────────────┼─────────────────────────────────┘
                          ▼
            Deterministic JSON Response
```

---

## Key Features

- **Single Driver Verification API**: Synchronous `POST /api/v1/verify-driver` endpoint returning verification status and match diagnostics.
- **Concurrent Batch Verification API**: High-throughput `POST /api/v1/batch-verify` endpoint executing multiple driver verifications simultaneously using an `asyncio.Semaphore` worker pool with per-driver fault isolation.
- **Security Hardening**:
  - **SSRF Protection**: Blocks requests to loopback (`127.0.0.1`), private RFC1918 subnets (`10.x`, `172.16-31.x`, `192.168.x`), and AWS cloud metadata endpoints (`169.254.169.254`).
  - **Zip Slip Protection**: Strict path validation prevents archive traversal attacks.
  - **Resource Bounds**: Download timeouts, maximum archive size (50MB), extracted size (100MB), and file count (50 files).
  - **PII Masking**: Structured JSON logs mask Aadhaar numbers, PANs, DL numbers, phone numbers, raw OCR dumps, and presigned URLs.
  - **Stateless Lifecycle**: Temporary directories are isolated per driver request and destroyed immediately upon completion.
- **Cloud-Native Probes**: `GET /health` (liveness) and `GET /ready` (readiness) for Kubernetes/ECS orchestrators.

---

## Directory Structure

```text
document-verification-service/
├── deploy/                      # Production deployment manifests
│   ├── Dockerfile               # Multi-stage, non-root, slim Python 3.12 container
│   ├── docker-compose.yml       # Local container runtime setup
│   └── k8s-deployment.yaml      # Kubernetes Deployment & ClusterIP Service spec
├── src/
│   ├── main.py                  # FastAPI initialization & lifecycle handlers
│   ├── api/                     # Ingress layer & API routes
│   │   ├── dependencies.py      # Dependency injection singletons
│   │   └── v1/
│   │       ├── router.py        # Central API v1 router
│   │       └── endpoints/
│   │           ├── verification.py  # Single & batch verification handlers
│   │           └── health.py        # Liveness & readiness probes
│   ├── clients/                 # Cloud & external network clients
│   │   ├── s3_download_client.py    # Streaming HTTPS downloader with SSRF protection
│   │   └── vision_ai_client.py      # Google Cloud Vision OCR SDK client
│   ├── extraction/              # Unpacking & document parsing
│   │   ├── zip_extractor.py         # Password-protected ZIP unpacker (pyzipper)
│   │   ├── document_classifier.py   # Heuristic document classifier
│   │   └── extractors/              # Aadhaar, PAN, Licence, RC field extractors
│   ├── normalization/           # Text & entity standardization
│   │   ├── name_normalizer.py       # NFKC Unicode, title, token, and initials cleaner
│   │   ├── vehicle_normalizer.py    # Canonical vehicle class mapper
│   │   └── date_normalizer.py       # ISO-8601 date standardizer
│   ├── verification/            # Cross-verification decision logic
│   │   ├── cross_validator.py       # Pipeline orchestrator & concurrent batch pool
│   │   ├── decision_engine.py       # Deterministic VERIFIED / REJECTED evaluator
│   │   └── matchers/                # Name matcher (exact, token, fuzzy) & vehicle matcher
│   ├── schemas/                 # Pydantic v2 request & response models
│   ├── core/                    # App settings, security, structured logger, exceptions
│   └── utils/                   # Temp directory context & image preprocessing
├── tests/                       # 49 unit, integration, and E2E test cases
│   ├── conftest.py              # Test client fixtures & mocks
│   ├── unit/                    # Isolated component unit tests
│   ├── integration/             # Pipeline integration tests
│   └── e2e/                     # End-to-end API scenario tests (Cases 1-8)
├── .env.example                 # Environment configuration template
├── requirements.txt             # Pinned project dependencies
└── pytest.ini                   # Pytest discovery configuration
```

---

## API Reference

### 1. Single Driver Verification

- **Endpoint**: `POST /api/v1/verify-driver`
- **Content-Type**: `application/json`

**Request Payload:**
```json
{
  "driver_id": "driver-59820",
  "mobile_number": "9876543210",
  "vehicle_class": "2 wheeler",
  "aadhaar_zip_url": "https://s3.amazonaws.com/bucket/aadhaar.zip",
  "pan_zip_url": "https://s3.amazonaws.com/bucket/pan.zip",
  "licence_zip_url": "https://s3.amazonaws.com/bucket/licence.zip",
  "rc_zip_url": "https://s3.amazonaws.com/bucket/rc.zip"
}
```

**Success Response (`VERIFIED`):**
```json
{
  "driver_id": "driver-59820",
  "status": "VERIFIED",
  "name_verification": {
    "aadhaar_pan": {
      "match": true,
      "score": 100.0,
      "method": "exact"
    },
    "aadhaar_licence": {
      "match": true,
      "score": 98.0,
      "method": "fuzzy"
    }
  },
  "vehicle_verification": {
    "match": true,
    "applied_class": "2 wheeler",
    "rc_class": "2 wheeler"
  },
  "rejection_reasons": []
}
```

**Mismatch Response (`REJECTED`):**
```json
{
  "driver_id": "driver-59820",
  "status": "REJECTED",
  "name_verification": {
    "aadhaar_pan": {
      "match": false,
      "score": 42.0,
      "method": "mismatch"
    },
    "aadhaar_licence": {
      "match": true,
      "score": 100.0,
      "method": "exact"
    }
  },
  "vehicle_verification": {
    "match": true,
    "applied_class": "2 wheeler",
    "rc_class": "2 wheeler"
  },
  "rejection_reasons": [
    "AADHAAR_PAN_NAME_MISMATCH"
  ]
}
```

---

### 2. Concurrent Batch Driver Verification

- **Endpoint**: `POST /api/v1/batch-verify`
- **Content-Type**: `application/json`

Submits multiple drivers simultaneously. Each driver is verified concurrently up to `MAX_CONCURRENT_WORKERS` (default: 5) using an `asyncio.Semaphore`. If one driver has an invalid password or network error, individual failure isolation guarantees that other driver verifications proceed uninterrupted.

**Request Payload:**
```json
{
  "drivers": [
    {
      "driver_id": "driver-001",
      "mobile_number": "9876543210",
      "vehicle_class": "2 wheeler",
      "aadhaar_zip_url": "https://s3.amazonaws.com/bucket/d1_aadhaar.zip",
      "pan_zip_url": "https://s3.amazonaws.com/bucket/d1_pan.zip",
      "licence_zip_url": "https://s3.amazonaws.com/bucket/d1_licence.zip",
      "rc_zip_url": "https://s3.amazonaws.com/bucket/d1_rc.zip"
    },
    {
      "driver_id": "driver-002",
      "mobile_number": "9123456780",
      "vehicle_class": "car",
      "aadhaar_zip_url": "https://s3.amazonaws.com/bucket/d2_aadhaar.zip",
      "pan_zip_url": "https://s3.amazonaws.com/bucket/d2_pan_mismatch.zip",
      "licence_zip_url": "https://s3.amazonaws.com/bucket/d2_licence.zip",
      "rc_zip_url": "https://s3.amazonaws.com/bucket/d2_rc.zip"
    }
  ]
}
```

**Batch Response:**
```json
{
  "total_count": 2,
  "verified_count": 1,
  "rejected_count": 1,
  "error_count": 0,
  "processing_time_ms": 412.5,
  "results": [
    {
      "driver_id": "driver-001",
      "status": "VERIFIED",
      "rejection_reasons": []
    },
    {
      "driver_id": "driver-002",
      "status": "REJECTED",
      "rejection_reasons": ["AADHAAR_PAN_NAME_MISMATCH"]
    }
  ]
}
```

---

### 3. Direct File Upload Verification (Interactive Testing)

- **Endpoint**: `POST /api/v1/verify-driver-files`
- **Content-Type**: `multipart/form-data`

Allows uploading raw local image files directly without requiring URLs or password encryption. You can pick files directly in the Swagger UI (`http://localhost:8000/docs`).

**Form Parameters:**
- `driver_id`: `string` (e.g. `driver-101`)
- `mobile_number`: `string` (e.g. `9876543210`)
- `vehicle_class`: `string` (e.g. `2 wheeler`, `car`, `truck`)
- `adhar_front`: File (Aadhaar front image)
- `adhar_back`: File (Aadhaar back image, optional)
- `pan_front`: File (PAN card image)
- `licence_front`: File (Driving licence front image)
- `licence_back`: File (Driving licence back image, optional)
- `rc_front`: File (RC front image)
- `rc_back`: File (RC back image, optional)

Returns the exact same deterministic `DriverVerificationResponse`.

---

## Rejection Reason Codes

| Code | Trigger |
|---|---|
| `AADHAAR_PAN_NAME_MISMATCH` | Aadhaar name fails to match PAN name below threshold |
| `AADHAAR_LICENCE_NAME_MISMATCH` | Aadhaar name fails to match Driving Licence name |
| `RC_VEHICLE_CLASS_MISMATCH` | Canonical vehicle class on RC does not match application class |
| `MISSING_REQUIRED_DOCUMENT` | One or more required documents were not provided or could not be classified |
| `INVALID_ZIP_PASSWORD` | Provided `mobile_number` failed to decrypt document archive |
| `PROCESSING_ERROR: <CODE>` | Upstream network failure, Vision API unavailable, or corrupted archive |

---

## Local Development & Testing

### 1. Prerequisites
- Python 3.12+ installed
- Active virtual environment (`.\venv\Scripts\Activate.ps1`)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Automated Tests
```bash
pytest -v tests/
```
Output:
```text
======================= 49 passed in 1.67s =======================
```

### 4. Run Service Locally
```bash
python -m uvicorn src.main:app --reload --port 8000
```
Open interactive Swagger documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Container Deployment

### 1. Build and Run with Docker
```bash
# Build multi-stage slim image
docker build -t document-verification-service:latest -f deploy/Dockerfile .

# Run container as non-root user
docker run -d -p 8000:8000 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google-service-account.json \
  -v /path/to/credentials:/app/credentials:ro \
  --name verification-service \
  document-verification-service:latest
```

### 2. Run with Docker Compose
```bash
cd deploy
docker compose up -d
```

### 3. Deploy to Kubernetes
```bash
# 1. Create Google Cloud credentials secret
kubectl create secret generic google-cloud-key \
  --from-file=google-service-account.json=/path/to/key.json

# 2. Apply deployment and service
kubectl apply -f deploy/k8s-deployment.yaml
```
