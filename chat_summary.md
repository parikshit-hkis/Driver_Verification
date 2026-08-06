# Project Summary: Driver Document Verification Automation (Gujarat, India)

## Goal: Build an automation pipeline for a ride-hailing platform (Uber/Ola/Rapido-style) to extract and verify driver documents from images, then approve/reject/flag drivers based on data consistency.

### Scope (v1 decisions already made)
    1.Documents: Aadhaar card, Driving Licence (DL), RC book — front & back images. No selfie/face photo in this version.
    2.Region: Gujarat state only (so DL/RC formats are fixed, RTO codes known — no need for multi-state format handling).
    3.Images: Always uploaded horizontally (no rotation/skew correction needed).
    4.No liveness/fraud detection in v1 — since there's no face/selfie, that fraud vector doesn't apply. Manual review is the backstop for identity-authenticity concerns.
    5.Re-uploads: No versioning complexity — rejected drivers can simply reapply with fresh documents.
    6.Rejection flow: Pipeline flags "pending" → human manually approves or rejects.
    7.Security: Deferred to a later phase, but basic-safe upload practices (validated file type, S3 direct upload, generated filenames, size caps) agreed to add even in v1.
    8.OCR approach chosen: Alternative C — self-built, using PaddleOCR + bounding-box/label-proximity extraction (not full regex-over-blob, not LayoutLM/Donut yet — that's a future upgrade once labeled data exists).

### Finalized Pipeline (v1):
    
    Driver Registration
         │
    Upload Images
         │
    Create Job (status=queued) → return job_id immediately (async — FastAPI + Celery + Redis)
         │
    [Celery worker processes job]
         │
    Image Quality Check (blur via Laplacian variance, brightness, min resolution — no rotation check needed)
         │
    Document Type Detection (classify Aadhaar/DL/RC + front/back)
         │
    OCR (PaddleOCR, angle_cls off, returns text + bounding boxes)
         │
    Structured Extraction (label-proximity matching using bounding box positions, per document type)
         │
    Normalization (name → first/middle/last via nameparser or fuzzy whole-string; DOB → ISO format; DL/RC number → cleaned format)
         │
    Validation:
        - Aadhaar: 12-digit format + Verhoeff checksum, DOB/name presence
        - DL: GJ+RTO-code format (validated against Gujarat RTO code lookup table), expiry > today, issue < expiry
        - RC: GJ+RTO-code format, owner name, issue/expiry dates
    Cross-Document Matching:
        - Name: fuzzy match (RapidFuzz token_sort_ratio / token_set_ratio, or Jaro-Winkler) across Aadhaar/DL/Form
        - DOB: exact match across Aadhaar/DL/Form
        - RC owner name vs DL name: fuzzy match (treated as review-flag, not hard reject, since vehicle may not be owned by driver)
         │
    Decision Engine: Approve (all valid + all matched) / Pending (mismatch or low confidence) / Reject (hard failures e.g. expired DL)
         │
    Generate Verification Report (JSON: field-by-field match status, extracted values, confidence scores)
         │
    Update job status in Postgres → driver polls/gets notified
         │
    [If Pending] → Manual Review queue → human Approve/Reject
    [If Rejected] → Driver can reapply with new documents

### Tech Stack Decided

API: FastAPI
Async processing: Celery + Redis (worker pool, horizontally scalable — celery -A worker --concurrency=N), with retry logic for transient OCR failures
OCR: PaddleOCR (self-hosted, free, gives bounding boxes for positional extraction)
Fuzzy matching: RapidFuzz
Name parsing: nameparser (with caveat: doesn't split Indian names cleanly — fallback to whole-string fuzzy match)
Storage: S3 (or equivalent) with server-side encryption for images; Postgres for job/document/report records
Image validation: OpenCV (blur/brightness/resolution checks), PIL (verify actual image validity on upload)

### Not Yet Built / Next Steps (pending in conversation)

1. decide_status() function — the business-rule logic combining validation + matching results into Approve/Pending/Reject
2. cross_match() function — full implementation of fuzzy name/DOB/RC-owner matching logic
3. Postgres schema for jobs, documents, reports tables to tie the async flow together
4. Gujarat RTO code lookup table (GJ01–GJ37 mapping) — needs to be filled in from official source
5. Full structured extraction functions per document type using PaddleOCR bounding-box + label-proximity method (pattern shown, not fully built out for all fields yet)
6. Full security hardening (explicitly deferred by user, but flagged: PII masking of Aadhaar numbers, access control, audit logging, retention policy — to be addressed before real production launch)