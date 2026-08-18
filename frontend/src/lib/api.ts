import {
  VerificationResult,
  BatchVerificationResponse,
  HistoricalRecordItem,
  ClusterHealthResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function verifySingleDriver(formData: FormData): Promise<VerificationResult> {
  const res = await fetch(`${API_BASE}/api/v1/driver/verify`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: "Verification failed" }));
    throw new Error(errorData.detail || `Server returned status ${res.status}`);
  }

  const json = await res.json();
  return json.data;
}

export async function verifyFolderBatch(folderPath: string = "sample_documents", concurrency: number = 1): Promise<BatchVerificationResponse> {
  const formData = new FormData();
  formData.append("folder_path", folderPath);
  formData.append("concurrency", concurrency.toString());

  const res = await fetch(`${API_BASE}/api/v1/batch/verify-folder`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: "Batch verification failed" }));
    throw new Error(errorData.detail || `Server returned status ${res.status}`);
  }

  const json = await res.json();
  return json.data;
}

export async function fetchHistoricalRecords(limit: number = 50, offset: number = 0, statusFilter?: string): Promise<{ total: number; drivers: HistoricalRecordItem[] }> {
  let url = `${API_BASE}/api/v1/driver/records?limit=${limit}&offset=${offset}`;
  if (statusFilter && statusFilter !== "ALL") {
    url += `&status_filter=${encodeURIComponent(statusFilter)}`;
  }

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error("Failed to fetch historical records");
  }

  const json = await res.json();
  return json.data;
}

export async function fetchDriverRecordDetail(driverId: string): Promise<VerificationResult> {
  const res = await fetch(`${API_BASE}/api/v1/driver/${driverId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch record for driver ${driverId}`);
  }

  const json = await res.json();
  return json.data;
}

export async function deleteDriverRecord(driverId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/driver/${driverId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    throw new Error(`Failed to delete record for driver ${driverId}`);
  }
}

export async function fetchClusterHealth(): Promise<ClusterHealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) {
    throw new Error("Failed to fetch cluster health");
  }

  return await res.json();
}
