# Prompt: Refactor Driver-by-Driver Document Processing Flow

## Objective

Refactor the existing Driver Document Verification project so that the entire extraction pipeline processes documents **driver-by-driver** instead of **document-type-by-document-type**.

Use the existing architecture and coding standards described in `PROJECT_DOCUMENTATION.md` as the reference. Do **not** rewrite the OCR engine, preprocessing pipeline, document extractors, normalizers, or document detection logic unless required for this new workflow. Preserve the current modular architecture.

Reference: fileciteturn0file0

---

# New Folder Structure

The system must support the following structure:

```text
sample_documents/
│
├── DRIVER_001/
│   ├── aadhar_card/
│   │   ├── front.jpg
│   │   └── back.jpg
│   │
│   ├── licence/
│   │   ├── front.jpg
│   │   └── back.jpg
│   │
│   ├── pan_card/
│   │   ├── front.jpg
│   │   └── back.jpg
│   │
│   └── RC_book/
│       ├── front.jpg
│       └── back.jpg
│
├── DRIVER_002/
│   ├── ...
│
└── DRIVER_003/
```

The folder name itself is the Driver ID.

---

# Required Processing Order

The program must scan the folders in this exact hierarchy:

```
sample_documents/

    ↓

Driver Folder 1

    ↓

Aadhaar

    ↓

Front

    ↓

Back

    ↓

Extract + Merge Aadhaar Result

    ↓

Licence

    ↓

Front

    ↓

Back

    ↓

Extract + Merge Licence Result

    ↓

PAN

    ↓

Front

    ↓

Back

    ↓

Extract + Merge PAN Result

    ↓

RC

    ↓

Front

    ↓

Back

    ↓

Extract + Merge RC Result

    ↓

Driver Completed

    ↓

Next Driver Folder
```

The system must **completely finish one driver** before moving to the next driver.

---

# Important Behaviour

The current project processes images independently.

This must change.

Instead:

1. Detect every driver folder.
2. Process all documents inside that driver.
3. Finish every document for that driver.
4. Produce one consolidated output for that driver.
5. Only then continue to the next driver.

Never interleave documents from different drivers.

Correct:

```
Driver1
    Aadhaar
    Licence
    PAN
    RC

Driver2
    Aadhaar
    Licence
    PAN
    RC
```

Incorrect:

```
All Aadhaar

All Licence

All PAN
```

---

# Document Order (Mandatory)

Always process in this order:

1. Aadhaar
2. Driving Licence
3. PAN
4. RC Book

Ignore missing folders gracefully.

---

# Image Order

For every document:

```
front image

↓

back image

↓

merge extracted fields
```

Both sides belong to one logical document.

The extractor should receive both OCR results (or equivalent merged data) before producing the final structured output whenever applicable.

---

# New Driver-Level Result

Create a new driver-level result model similar to:

```python
DriverVerificationResult
    driver_id
    aadhaar_result
    licence_result
    pan_result
    rc_result
```

This represents one driver's complete verification data.

---

# Directory Scanner

Create a dedicated scanner/service responsible only for directory traversal.

Responsibilities:

- discover driver folders
- discover document folders
- discover images
- preserve processing order
- validate expected structure

Do not mix traversal logic into OCR or extractors.

---

# Pipeline Changes

Update the orchestration (for example `main.py` and/or `Pipeline`) to iterate:

```
for driver_folder:

    process aadhaar

    process licence

    process pan

    process rc

    return DriverVerificationResult
```

Keep preprocessing, OCR, document detection, and extractors reusable.

---

# Missing Documents

If a document folder is missing:

- continue processing
- record that document as missing
- never stop the driver's pipeline

If one image is missing (front/back):

- process available image
- log warning
- continue

---

# Output

After every driver print something similar to:

```text
====================================

Driver : DRIVER_001

------------------------------------

AADHAAR
✓ extracted

LICENCE
✓ extracted

PAN
✓ extracted

RC
✓ extracted

====================================
```

or return the equivalent structured object.

---

# Constraints

- Preserve the existing architecture.
- Reuse existing extractors.
- Do not duplicate OCR logic.
- Do not rewrite preprocessing.
- Keep the code modular.
- Separate scanning, orchestration, extraction, and models.
- Maintain backward compatibility where practical.

The goal is to change only the orchestration and directory traversal so the system becomes driver-centric rather than image-centric.
