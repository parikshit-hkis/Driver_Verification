i have to make automation of checking details from image for platform like rapido,ola,uber's driver documents :
driver licence,
aadhar card,
rc book and other details filled by that driver like name,date of birth(dob),mobile number,email id in form while registering 
so help me to make full plan to make that type of automation for me,i have to cover all the details which is using in real world for that type of application 
so each document will be in image format which can have both front and back side of the document.

# so i have to extract corresponding detail from that documents and save it. after that make an automation like using that information it can check all the details. 

## details to extract from images:

1. aadhar card: full_name(with extractable format of first,last and middle name),aadhar_no,dob
2. driver licence: full_name(with extractable format of first,last and middle name),dob,license_no,issue_date,expiry_date,all Class of Vehicle(like in how many types of vehicles that person is eligible to drive after getting license)
3. rc book: owner_name,registration_number,vehicle_type,issue_date,expiry_date
and these comes from api and other details are like full_name,dob,mobile number,

### automation details:

1. after extracting all the details, check all details are correct or not by comparing and matching all three documents data with each other 
    if all are correct then save it as "verification complete", else flag it as pending, and create report/file which conatins all the missing or wrong details

2. all service should be independent.


# pipeline should be:
Driver Registration
        │
        ▼
Upload Images
(Aadhaar, DL, RC, Selfie, etc.)
        │
        ▼
Image Validation
        │
        ▼
OCR & Data Extraction
        │
        ▼
Normalization(regex,Key-Value Anchor Mapping,)
        │
        ▼
Document Validation
        │
        ▼
Cross Document Matching
        │
        ▼
Business Rule Validation
        │
        ▼
Verification Report
        │
        ▼
Approve / Manual Review / Reject



## phase 1: Input
    1.driver licence,
    2.aadhar card,
    3.rc book,
    4. other details(like name,dob,mobile number,email id in form while registering).

## Phase 2 — Image Quality Check
    validate image quality.
    if image  blury then reject and flag as documation is readable.

## Phase 3 — Document Type Detection
    Automatically determine which document is this.

## Phase 4 — OCR(Optical Character Recognition) - can use Celery with redis broker for async distributed workers
### like FastAPI + Celery + Redis (or RabbitMQ) + Postgres for job status
    1. PaddleOCR
    2. Tesseract OCR
    3. EasyOCR
    4. Google Cloud Vision API(paid - gives 300$ credits on new user)
    5. AWS Textract 
    6. Microsoft Azure AI Document Intelligence
    extract text from documents

## Phase 5 — Structured Extraction
    1. aadhar card:{
        "document_type": "AADHAAR",
        "aadhaar_number": "",
        "full_name": "",
        "dob": "",
        "gender": ""
    }

    2. driver licence:{
        "document_type": "driver licence",
        "license_number": "",
        "full_name": "",
        "dob": "",
        "issue_date": "",
        "expiry_date": "",
        "issuing_state": "",
        "vehicle_classes": [
            "MCWG",
            "LMV"
        ]
    }

    3. RC:{
        "document_type": "RC",
        "registration_number": "",
        "owner_name": "",
        "vehicle_type": "",
        "fuel_type": "",
        "manufacturer": "",
        "model": "",
        "issue_date": "",
        "expiry_date","fitness_validity","registration_Validity": ""
    }

## Phase 6 — Normalization
    for full_name: first_name,middle_name,_last_name or we can do Fuzzy Matching algorithm 
    for dob: if 12-04-2000 -> 2000-04-12 
    for licence number: GJ-01-2021-0012345 -> GJ0120210012345


## Phase 7 — Validation
    Aadhaar :   Aadhaar number format
                DOB exists
                Name exists
                Gender exists

    Driving Licence :   license format
                        expiry > today
                        issue < expiry
                        DOB present
                        name present
                        vehicle classes exist

    RC :    registration number format
            owner name
            issue date
            expiry
            vehicle type

## Phase 8 — Cross Document Matching
    Name Matching - 
        Normalize Name -> like fuzzy matching -> Similarity Score
        A name extracted at 60% confidence should route to manual review even if it "matches" --> confidence thresholding
        token_sort_ratio (RapidFuzz / RapidFuzz PyPI),
        token_set_ratio (RapidFuzz / RapidFuzz PyPI),
        Jaro-Winkler (TextDistance)
        
    DOB Matching
    License Expiry
    Vehicle Eligibility with uploaded RC of vehicle
    RC Owner name 



# new updateed pipeline :


Driver Registration
     │
     ▼
Upload Images  ── [Section 2]
     │
     ▼
Create Job (status=queued) → Return job_id immediately ── [Section 1: async]
     │
     ▼
[Celery Worker picks up job]
     │
     ▼
Image Quality Check (blur, brightness, resolution — no rotation check) ── [Section 3]
     │
     ▼
Document Type Detection
     │
     ▼
OCR (PaddleOCR, with bounding boxes) ── [Section 6]
     │
     ▼
Structured Extraction (label-proximity + Gujarat regex) ── [Section 5,6]
     │
     ▼
Normalization
     │
     ▼
Validation (format + RTO code lookup + expiry)
     │
     ▼
Cross-Document Matching (fuzzy name, exact DOB)
     │
     ▼
Decision: Approve / Pending / Reject
     │
     ▼
Update job status + save report → = notified/polls status
     │
     ▼
[If Pending] → Manual Review → Human Approve/Reject
[If Rejected] → Driver can reapply with new documents





i have some changes:
1. i have documents only for gujarat's driver
2. i'll have data image format and other data into json so don't worry about api i'll habdle that.


aadhar number of 4341 3155 9547,
name: patel jay dhansukhbhai,
dob: 18/05/1999,
address: vastral, nehru nagar,ahmedabad,gujarat,380058,
gender: male,
aadhar no. issued: 10/10/2016 ,
in english and gujarati language for gujarat state 


aadhar number of 9658 3155 6851,
name: sutariya daksh hiteshbhai,
dob: 05/02/2002,
address: bopal, dhanlaxmi society,ahmedabad,gujarat,380058,
gender: male,
aadhar no. issued: 18/02/2016,
in english and gujarati language for gujarat state 


aadhar number of 6596 4578 1352,
name: gorasiya vivek hirenbhai,
dob: 28/08/2005,
address: shivalay society,katargam,surat,gujarat,384720,
gender: male,
aadhar no. issued: 28/05/2017,
in english and gujarati language for gujarat state 

aadhar number of 8956 5623 4512,
name: parikh keval rameshbbhai,
dob: 28/07/2006,
address: maninagar,ahmedabad,gujarat,380008,
gender: male,
aadhar no. issued: 10/06/2018,
in english and gujarati language for gujarat state and diferent face 


aadhar number of 4576 8956 4562,
name: lakhani riya pankajbhai,
dob: 28/09/2000,
address: bopal,near by kalpur chokdi,ahmedabad,gujarat,380008,
gender: female,
aadhar no. issued: 10/06/2018,
in english and gujarati language for gujarat state and diferent face 
