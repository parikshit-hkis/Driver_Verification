# AI Agent Task — Fix and Redesign RC Book Extraction

## Objective

Modify the existing Driver Document Verification project so that the RC (Registration Certificate) extractor reliably extracts the correct fields from real RC images.

The current extractor is producing many incorrect field/value associations even though PaddleOCR is recognizing much of the text correctly.

This is primarily an **OCR-to-field association and layout reasoning problem**, not simply an OCR recognition problem.

You must improve the extractor without replacing the existing OCR/preprocessing architecture.

---
a
# 1. Read the Existing Project First

Before changing code, inspect:

- `PROJECT_DOCUMENTATION.md`
- `app/services/base_extractor.py`
- `app/services/rc_extractor/extractor.py`
- `app/services/rc_extractor/models.py`
- `app/models/ocr_models.py`
- `app/ocr/preprocessor.py`
- `app/ocr/paddle_ocr.py`
- `app/utils/normalizer.py`
- `app/pipeline.py`

Understand how:

- images are preprocessed
- OCR is executed
- bounding boxes are represented
- `OCRText` and `OCRResult` work
- RC extraction is currently called
- `RCData` is structured

Do not start by rewriting the entire project.

---

# 2. Current Failure

The current RC extractor can produce output similar to:

```text
Registration No         : GJ-05-KL-2922
Owner Name              : PETROL
Vehicle Class           : 150
Vehicle Type            : MONTH &YR.OF MFG
Fuel Type               : PETROL
Manufacturer            : CERTIFICATE OFREGISTRATION
Model                   : CUBIC CAPACITY
Chassis Number          : MD2A37CZXDPM93952
Engine Number           : DISCOVER125ST
Date of Registration    : —
Registration Validity   : —
Fitness Validity        : —
Insurance Validity      : —
Issuing RTO             : FINANCER NAME
```

For the supplied RC images, the actual information is approximately:

```text
Registration No         : GJ05KL2922
Owner Name              : KAVINBHAI CHOKSI
Vehicle Class           : MOTOR CYCLE
Fuel Used               : PETROL
Chassis No              : MD2A37CZXDPM93952
Engine No               : JZPDM12069
Date of Reg.            : 13/05/2013
Reg. Validity           : 12/05/2028

Maker's Name            : BAJAJ AUTO LTD
Model Name              : DISCOVER 125 ST
Colour                  : BLK MEGAN
Body Type               : SOLO+PILL RIDER
Cubic Capacity          : 150
Month & Yr. of Mfg.     : MAY 2013
Registration Authority  : SURAT
```

The important observation is:

**Many wrong output values are real OCR text from the document, but they have been assigned to the wrong fields.**

Examples:

```text
Owner Name       → PETROL
Vehicle Class    → 150
Vehicle Type     → MONTH &YR.OF MFG
Manufacturer     → CERTIFICATE OFREGISTRATION
Model            → CUBIC CAPACITY
Engine Number    → DISCOVER125ST
Issuing RTO      → FINANCER NAME
```

This must be fixed at the extraction/layout-association level.

---

# 3. Do NOT Just Expand Hardcoded Lists

The existing implementation contains or may contain collections such as:

```python
_FUEL_TYPES
_VEHICLE_CLASSES
_KNOWN_MANUFACTURERS
_ALL_RC_LABELS
```

Do NOT solve the problem by simply adding hundreds of new hardcoded values.

That creates another bottleneck.

The extractor must be able to process values that were never present in the hardcoded lists.

For example, if an RC contains:

```text
Manufacturer: SOME NEW AUTOMOTIVE COMPANY
```

and that company is not in `_KNOWN_MANUFACTURERS`, the extractor should still be able to return it when the layout and field relationship strongly support it.

Likewise:

- unknown manufacturer
- unknown model
- uncommon fuel representation
- unknown vehicle class
- unknown RTO
- new body type

must not automatically become `None`.

---

# 4. Hardcoded Lists Must Become Hints, Not Absolute Rules

If these lists are retained:

```python
_FUEL_TYPES
_VEHICLE_CLASSES
_KNOWN_MANUFACTURERS
_ALL_RC_LABELS
```

use them as:

- normalization hints
- confidence bonuses
- aliases
- known-label references
- optional vocabulary assistance

Do NOT use them as mandatory whitelists.

Bad:

```python
if candidate not in KNOWN_MANUFACTURERS:
    return None
```

Better:

```text
known manufacturer → confidence bonus
unknown manufacturer → continue evaluating normally
```

The system should distinguish:

```text
known valid value
unknown but plausible value
invalid value
```

Do not treat:

```text
unknown = invalid
```

---

# 5. Critical Requirement: Process Front and Back Separately

The RC consists of two separate images/sides.

Do NOT blindly combine:

```text
front OCR boxes + back OCR boxes
```

and then perform global spatial nearest-neighbor extraction.

That causes cross-side contamination.

Instead use:

```text
FRONT IMAGE
    ↓
Preprocess
    ↓
OCR
    ↓
Extract front-side fields

BACK IMAGE
    ↓
Preprocess
    ↓
OCR
    ↓
Extract back-side fields

    ↓
Merge structured results

    ↓
RCData
```

The front and back have independent coordinate systems and independent layouts.

If the current pipeline receives front and back separately, preserve that separation.

If the current pipeline only receives one OCR result at a time, add a clean mechanism for combining the structured results afterward.

Do not create one giant OCR coordinate space for both images.

---

# 6. Side-Specific Field Expectations

Use side information as a **soft prior**, not a rigid rule.

For the supplied RC, front-side fields include approximately:

```text
Registration Number
Owner Name
Vehicle Class
Fuel Used
Chassis Number
Engine Number
Date of Registration
Registration Validity
Address
```

Back-side fields include approximately:

```text
Manufacturer
Model
Colour
Body Type / Vehicle Type
Cubic Capacity
Manufacturing Date
Registration Authority
```

Different RC layouts may place fields differently.

Therefore:

- prioritize expected fields on the expected side
- allow fallback to the other side when necessary
- never reject a field solely because it appears on the unexpected side

---

# 7. Replace "Nearest OCR Box = Value"

The current approach is too close to:

```text
find label
    ↓
find nearest OCR box
    ↓
return it
```

This is the main logic that must change.

Use:

```text
Find label
    ↓
Generate multiple candidates
    ↓
Analyze spatial relationship
    ↓
Reject obvious labels
    ↓
Merge related OCR boxes
    ↓
Validate candidate for this field
    ↓
Score candidates
    ↓
Select best candidate
    ↓
Normalize
```

The nearest candidate must NOT automatically win.

---

# 8. Improve Label Detection

Improve the current label detection logic.

The existing substring matching can create collisions such as:

```text
Name
Owner Name
Manufacturer Name
Model Name
```

and:

```text
Registration
Registration Date
Registration Validity
```

Use a matching hierarchy:

1. exact normalized match
2. exact match after punctuation cleanup
3. known alias
4. fuzzy similarity for OCR mistakes
5. controlled substring matching as a fallback

Normalize punctuation and common OCR variations.

Examples:

```text
Regn. No.
Regn No
Reg. No.
Registration No.
```

should be treated as related labels.

Likewise:

```text
Chasis No
Chassis No
Chassis Number
```

should be handled.

Do not blindly choose the first OCR box that contains a keyword.

---

# 9. Detect Labels Structurally

Do not depend entirely on a giant `_ALL_RC_LABELS`.

A text box is more likely to be a label when multiple signals support that conclusion:

- short field-like text
- punctuation such as `:`
- repeated label/value pattern
- located in a table label column
- visually/structurally different from values
- followed by a candidate value
- matches a known label alias
- appears in a repeated field structure

Use known labels as hints.

The extractor should still function when an unfamiliar label appears.

---

# 10. Candidate Generation

For every field, generate multiple candidate OCR boxes.

Search possible relationships such as:

- right of label
- below label
- same row
- same column
- nearby structured row
- nearby multi-line region

For each candidate, collect information such as:

```text
candidate text
OCR confidence
distance from label
horizontal alignment
vertical alignment
same-row relationship
same-column relationship
side
bounding-box size
whether it resembles another label
whether it matches field format
```

Do not immediately return the first candidate.

---

# 11. Candidate Scoring

Use a scoring approach.

Conceptually:

```text
score =
    spatial relationship score
  + row/column alignment score
  + OCR confidence score
  + field-format score
  + semantic/structural compatibility
  + known-vocabulary bonus
  + multi-box continuity bonus
  + side/layout prior
  - distance penalty
  - label penalty
  - unrelated-field penalty
```

The exact formula is up to you.

The important requirement is:

**Distance alone must not determine the result.**

A candidate that is slightly farther away but is clearly the correct type of value should beat a nearby unrelated label.

---

# 12. Reject Other Labels as Values

This is mandatory.

For example:

```text
Owner Name
Vehicle Class
KAVINBHAI CHOKSI
MOTOR CYCLE
```

When extracting Owner Name:

```text
Vehicle Class
```

must not be accepted as the owner name.

Similarly:

```text
Model Name
Cubic Capacity
DISCOVER 125 ST
150
```

When extracting Model:

```text
Cubic Capacity
```

must not become the model.

Do not solve this only by adding a huge blacklist.

Use:

- label likelihood
- spatial structure
- field relationships
- candidate scoring
- known labels as optional signals

---

# 13. Multi-Line OCR Values

PaddleOCR may split one value into multiple OCR boxes.

Examples:

```text
KAVINBHAI
CHOKSI
```

should become:

```text
KAVINBHAI CHOKSI
```

and:

```text
BAJAJ AUTO
LTD
```

should become:

```text
BAJAJ AUTO LTD
```

Implement intelligent merging based on:

- same row
- vertical adjacency
- horizontal adjacency
- alignment
- gap
- absence of an intervening label
- field plausibility

Do not concatenate every nearby OCR box.

---

# 14. Owner Name

Improve owner extraction.

Support:

```text
Name of Owner
Owner Name
Owner's Name
Owner
Registered Owner
Vehicle Owner
```

The candidate must:

- contain no meaningful digits
- not be another label
- not be a document heading
- have plausible name structure
- support multiple words
- support multiple OCR boxes

Do not require the name to exist in a predefined list.

---

# 15. Vehicle Class

Improve vehicle class extraction.

Known values can provide a score bonus, but unknown values must still be possible.

Examples include:

```text
MOTOR CYCLE
LMV
LMV-CAR
MCWG
MCWOG
HMV
MGV
HGMV
```

Do not make `_VEHICLE_CLASSES` a strict whitelist.

Use field context and structural validation.

---

# 16. Vehicle Type / Body Type

Support labels such as:

```text
Vehicle Type
Type of Vehicle
Type of Veh
Body Type
Veh Type
```

For the supplied image, the relevant value is:

```text
SOLO+PILL RIDER
```

Do not return:

```text
MONTH & YR. OF MFG
```

just because it is nearby.

Do not require vehicle types to exist in a hardcoded list.

---

# 17. Fuel Type

Support known fuels but do not make `_FUEL_TYPES` a strict whitelist.

Known values may include:

```text
PETROL
DIESEL
CNG
LPG
ELECTRIC
HYBRID
PETROL+CNG
PETROL+LPG
```

Important:

`BS6` is NOT a fuel type.

Do not return `BS6` as fuel.

If an unknown fuel representation appears, evaluate it using:

- label association
- candidate structure
- OCR text
- known-vocabulary bonus

rather than automatically rejecting it.

---

# 18. Manufacturer

Do not require `_KNOWN_MANUFACTURERS`.

For the supplied RC:

```text
Maker's Name
BAJAJ AUTO LTD
```

must produce:

```text
BAJAJ AUTO LTD
```

Do not allow:

```text
CERTIFICATE OF REGISTRATION
```

to become the manufacturer.

Known manufacturers can increase confidence, but unknown manufacturers must remain possible.

---

# 19. Model

Do not maintain a model whitelist.

Models are open-ended.

For the supplied RC:

```text
Model Name
DISCOVER 125 ST
```

must produce:

```text
DISCOVER 125 ST
```

Do not return:

```text
CUBIC CAPACITY
```

because it is a nearby label.

Use field context, layout, label detection, and candidate scoring.

---

# 20. Chassis Number

The current implementation is too permissive.

Do not use only:

```python
5 <= len(value) <= 20
```

because values such as:

```text
MANUFACTURER
VEHICLE
CERTIFICATE
```

can pass.

Use stronger structural validation:

- usually 17-character VIN-like value
- alphanumeric structure
- label association
- remove spaces/hyphens
- reject dates
- reject registration numbers
- reject known labels
- reject ordinary phrases
- allow controlled fallback for valid non-standard lengths

The existing chassis regex must either be used properly or removed if replaced by a better validator.

For the supplied RC, the correct value is:

```text
MD2A37CZXDPM93952
```

---

# 21. Engine Number

The current implementation is also too permissive.

Do not treat every 4–20 character alphanumeric string as an engine number.

For the supplied RC:

```text
Engine No.
JZPDM12069
```

must produce:

```text
JZPDM12069
```

and must NOT produce:

```text
DISCOVER125ST
```

Use:

- label relationship
- spatial association
- candidate scoring
- alphanumeric structure
- exclusion of model/manufacturer/labels
- field-specific validation

Do not use a hardcoded engine-number database.

---

# 22. Dates

Improve all date extraction methods:

```text
date_of_registration
registration_validity
fitness_validity
insurance_validity
tax_validity
```

Do not globally find a date and assign it based on order.

Each date must be associated with its own label.

For the supplied RC:

```text
Date of Reg.
13/05/2013
```

must become:

```text
2013-05-13
```

and:

```text
Reg. Validity
12/05/2028
```

must become:

```text
2028-05-12
```

Continue using the existing `normalize_date()`.

Support OCR variations and common date formats.

If a date field is genuinely absent, return `None`.

Never use an unrelated nearby date just to fill the field.

---

# 23. Registration Number

Registration number currently works well.

Preserve its behavior.

Continue supporting:

```text
GJ05KL2922
GJ 05 KL 2922
GJ-05-KL-2922
```

Keep the existing regex-based fallback unless you have a demonstrably better replacement.

Do not break registration extraction while fixing other fields.

---

# 24. Issuing / Registration Authority

Improve RTO extraction.

For the supplied RC:

```text
Registration Authority
SURAT
```

must produce:

```text
SURAT
```

Do not return:

```text
FINANCER NAME
```

Do not return only:

```text
RTO
```

if the actual authority name is available.

Do not maintain a strict city/RTO whitelist.

Unknown authorities must still be extractable.

---

# 25. Cross-Field Reasoning

Use other extracted fields as confidence signals.

For example:

```text
Manufacturer = BAJAJ AUTO LTD
Model = DISCOVER 125 ST
Vehicle Class = MOTOR CYCLE
Fuel = PETROL
```

is a structurally plausible combination.

But:

```text
Manufacturer = CERTIFICATE OF REGISTRATION
Model = CUBIC CAPACITY
Vehicle Class = 150
```

is highly suspicious.

Cross-field consistency can be used to increase/decrease confidence.

Do not require a hardcoded database of manufacturer/model combinations.

---

# 26. Open-Set vs Closed-Set Fields

Treat fields differently.

### Mostly open-set:

```text
Owner Name
Manufacturer
Model
RTO
Address
Chassis Number
Engine Number
```

Do not use strict value lists.

### Semi-closed:

```text
Fuel Type
Vehicle Class
```

Known vocabularies can help, but unknown values must remain possible.

This distinction is important.

---

# 27. Unknown Values Must Be Preserved

The extractor must follow this principle:

```text
Unknown ≠ Invalid
```

If a candidate:

- has strong label association
- has good spatial relationship
- has plausible field structure
- is not another label
- has reasonable OCR confidence

then return it even if it is not in a predefined vocabulary.

---

# 28. Do Not Overfit to the Supplied RC

Do NOT hardcode:

```text
KAVINBHAI
CHOKSI
BAJAJ
DISCOVER
SURAT
```

Do NOT hardcode coordinates.

Do NOT create rules specific to this image.

The supplied RC is a test case, not the definition of the algorithm.

The final extractor must work with different:

- owners
- manufacturers
- models
- RTOs
- vehicle classes
- fuels
- layouts
- resolutions
- OCR errors

---

# 29. Debugging / Explainability

Add optional debug logging.

For each extracted field, debug mode should show:

```text
[RC] SIDE=FRONT
[RC] FIELD=owner_name
[RC] LABEL="Owner Name"

Candidate:
    PETROL
    rejected
    reason=poor field compatibility / wrong spatial relationship

Candidate:
    KAVINBHAI CHOKSI
    accepted
    reason=strong spatial + semantic + structural match

[RC] FINAL owner_name=KAVINBHAI CHOKSI
```

For Model:

```text
[RC] FIELD=model

Candidate:
    CUBIC CAPACITY
    rejected: detected as label

Candidate:
    DISCOVER 125 ST
    accepted

[RC] FINAL model=DISCOVER 125 ST
```

Use the project's logging system.

Debug mode should be optional.

---

# 30. Data Model

Preserve the existing `RCData` interface as much as possible.

Do not break existing callers.

If the current schema does not have fields such as:

```text
colour
body_type
cubic_capacity
manufacturing_date
address
```

do not silently add them without considering backward compatibility.

If adding fields is beneficial, explain why and update all relevant documentation/callers.

Do not conflate:

```text
vehicle_type
body_type
vehicle_class
```

unless the existing project explicitly defines them as equivalent.

---

# 31. Testing

Create tests for:

### Test 1 — Supplied RC

Expected approximately:

```text
registration_number = GJ05KL2922
owner_name = KAVINBHAI CHOKSI
vehicle_class = MOTOR CYCLE
fuel_type = PETROL
chassis_number = MD2A37CZXDPM93952
engine_number = JZPDM12069
date_of_registration = 2013-05-13
registration_validity = 2028-05-12
manufacturer = BAJAJ AUTO LTD
model = DISCOVER 125 ST
vehicle_type/body_type = SOLO+PILL RIDER
issuing_rto = SURAT
```

Fields not present should remain `None`.

---

### Test 2 — Nearby labels

Input:

```text
Owner Name
Vehicle Class
KAVINBHAI CHOKSI
MOTOR CYCLE
```

Expected:

```text
owner_name = KAVINBHAI CHOKSI
vehicle_class = MOTOR CYCLE
```

---

### Test 3 — Multi-line value

Input:

```text
Owner Name
KAVINBHAI
CHOKSI
```

Expected:

```text
KAVINBHAI CHOKSI
```

---

### Test 4 — Unknown manufacturer

Input:

```text
Maker's Name
SOME UNKNOWN AUTOMOTIVE COMPANY
```

The value must still be extractable even if it is absent from `_KNOWN_MANUFACTURERS`.

---

### Test 5 — Unknown vehicle class

An unseen but structurally plausible vehicle class must not automatically return `None`.

---

### Test 6 — Unknown fuel representation

An unseen but plausible fuel value must not automatically return `None`.

---

### Test 7 — Multiple dates

Ensure:

```text
Date of Registration
13/05/2013

Registration Validity
12/05/2028
```

are not swapped.

---

### Test 8 — Wrong nearby values

Ensure:

```text
Engine No.
JZPDM12069
Model Name
DISCOVER 125 ST
```

does not produce:

```text
engine_number = DISCOVER125ST
```

---

### Test 9 — Registration regression

Verify:

```text
GJ05KL2922
GJ 05 KL 2922
GJ-05-KL-2922
```

still work.

---

# 32. Code Quality

The final implementation must:

- preserve modular architecture
- use type hints
- avoid duplicated logic
- use reusable helper methods
- avoid giant functions
- avoid magic numbers where possible
- remove dead/unused regexes
- use logging
- document non-obvious spatial reasoning
- keep RC-specific logic inside RC-related modules
- keep generic geometry helpers in `BaseExtractor`
- avoid unrelated project changes

---

# 33. Required Final Response From the AI Agent

After implementation, provide:

1. Files modified.
2. Why each file was modified.
3. Complete updated code for relevant files.
4. Explanation of the new extraction flow.
5. Explanation of front/back isolation.
6. Explanation of candidate generation.
7. Explanation of candidate scoring.
8. Explanation of multi-line OCR merging.
9. Explanation of label detection.
10. Explanation of how hardcoded vocabularies were changed from hard constraints into optional hints.
11. Explanation of how unknown values are handled.
12. Test results for the supplied RC.
13. Any fields intentionally left as `None`.
14. Confirmation that registration-number extraction still works.
15. Any limitations that remain.

Do not claim the extractor is perfect.

Do not hide uncertainty.

If a field cannot be reliably extracted, return `None` rather than an unrelated value.

---

# Final Principle

The extractor must answer:

> "Why does this OCR text belong to this field?"

rather than:

> "What is the closest OCR text?"

A correct field assignment should ideally have multiple supporting signals:

```text
Correct label
+
Correct spatial relationship
+
Correct side/layout
+
Plausible field structure
+
Not another label
+
Reasonable OCR confidence
+
Optional vocabulary support
```

The system should be robust to unknown values and new RC formats.

Do not replace one brittle hardcoded parser with a larger brittle hardcoded parser.
