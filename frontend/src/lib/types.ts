export interface DocumentFieldDiagnostics {
  [field: string]: string;
}

export interface AadhaarData {
  aadhaar_number?: string;
  full_name?: string;
  date_of_birth?: string;
  gender?: string;
  care_of?: string;
  address?: string;
  pincode?: string;
  field_diagnostics?: DocumentFieldDiagnostics;
}

export interface DLData {
  licence_number?: string;
  full_name?: string;
  date_of_birth?: string;
  issue_date?: string;
  expiry_date?: string;
  vehicle_classes?: string[];
  field_diagnostics?: DocumentFieldDiagnostics;
}

export interface PanData {
  pan_number?: string;
  full_name?: string;
  father_name?: string;
  date_of_birth?: string;
  field_diagnostics?: DocumentFieldDiagnostics;
}

export interface RCData {
  registration_number?: string;
  owner_name?: string;
  date_of_registration?: string;
  registration_validity?: string;
  vehicle_class?: string;
  overall_confidence?: number;
  confidence_scores?: Record<string, number>;
  field_diagnostics?: DocumentFieldDiagnostics;
}

export interface ExtractedDocument<T> {
  document_type: string;
  status: "EXTRACTED" | "PARTIAL" | "MISSING" | "FAILED";
  warning?: string | null;
  data?: T;
}

export interface DriverExtractionPayload {
  driver_id: string;
  documents: {
    aadhaar: ExtractedDocument<AadhaarData>;
    licence: ExtractedDocument<DLData>;
    pan: ExtractedDocument<PanData>;
    rc: ExtractedDocument<RCData>;
  };
}

export interface PairwiseComparison {
  name: {
    aadhaar?: string;
    licence?: string;
    pan?: string;
    similarity: number;
    status: "MATCH" | "REVIEW" | "MISMATCH" | "MISSING";
  };
  date_of_birth: {
    aadhaar?: string;
    licence?: string;
    pan?: string;
    status: "MATCH" | "MISMATCH" | "MISSING";
  };
  status: "MATCH" | "REVIEW" | "MISMATCH";
}

export interface CrossValidationReport {
  driver_id: string;
  aadhaar_vs_pan?: PairwiseComparison;
  aadhaar_vs_licence?: PairwiseComparison;
  pan_vs_licence?: PairwiseComparison;
  overall_name_status: "MATCHED" | "REVIEW" | "MISMATCH";
  overall_dob_status: "MATCHED" | "MISMATCH";
  overall_status: "MATCHED" | "REVIEW" | "MISMATCH";
  execution_time_ms?: number;
}

export interface VerificationResult {
  driver_id: string;
  extraction: DriverExtractionPayload;
  cross_validation: CrossValidationReport;
}

export interface BatchDriverSummary {
  driver_id: string;
  overall_status: "MATCHED" | "REVIEW" | "MISMATCH" | "FAILED" | "UNKNOWN";
  overall_name_status: string;
  overall_dob_status: string;
  extracted_name?: string;
  licence_number?: string;
  vehicle_classes?: string[];
  rc_number?: string;
  error?: string;
}

export interface BatchVerificationResponse {
  total_drivers: number;
  completed: number;
  statistics: {
    MATCHED: number;
    REVIEW: number;
    MISMATCH: number;
    FAILED: number;
  };
  drivers: BatchDriverSummary[];
}

export interface HistoricalRecordItem {
  driver_id: string;
  overall_status: string;
  name_status: string;
  dob_status: string;
  extraction_file: string;
}

export interface ClusterHealthResponse {
  gateway: string;
  version: string;
  cluster: Record<string, { status: string; latency_ms?: number; error?: string }>;
}
