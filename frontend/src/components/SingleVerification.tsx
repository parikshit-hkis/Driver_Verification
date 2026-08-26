"use client";

import React, { useState } from "react";
import { Upload, FileText, CheckCircle, AlertCircle, RefreshCw, Car, CreditCard, Shield, IdCard } from "lucide-react";
import { verifySingleDriver, fetchDriverRecordDetail } from "../lib/api";
import { VerificationResult } from "../lib/types";
import { CrossMatchMatrix } from "./CrossMatchMatrix";

interface DocFileState {
  front: File | null;
  back: File | null;
}

export const SingleVerification: React.FC = () => {
  const [driverId, setDriverId] = useState("");
  const [vehicleClass, setVehicleClass] = useState("");
  const [aadhaar, setAadhaar] = useState<DocFileState>({ front: null, back: null });
  const [licence, setLicence] = useState<DocFileState>({ front: null, back: null });
  const [pan, setPan] = useState<DocFileState>({ front: null, back: null });
  const [rc, setRc] = useState<DocFileState>({ front: null, back: null });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [overallStatus, setOverallStatus] = useState<boolean | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!driverId.trim()) {
      setError("Please enter a Driver ID (phone number or identifier).");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setOverallStatus(null);

    const formData = new FormData();
    formData.append("driver_id", driverId.trim());
    formData.append("vehicle_class", vehicleClass.trim());

    if (aadhaar.front) formData.append("aadhaar_front", aadhaar.front);
    if (aadhaar.back) formData.append("aadhaar_back", aadhaar.back);
    if (licence.front) formData.append("licence_front", licence.front);
    if (licence.back) formData.append("licence_back", licence.back);
    if (pan.front) formData.append("pan_front", pan.front);
    if (pan.back) formData.append("pan_back", pan.back);
    if (rc.front) formData.append("rc_front", rc.front);
    if (rc.back) formData.append("rc_back", rc.back);

    try {
      const data: any = await verifySingleDriver(formData);
      if (data?.over_all_status !== undefined) {
        setOverallStatus(Boolean(data.over_all_status));
      }
      try {
        const fullData = await fetchDriverRecordDetail(driverId.trim());
        setResult(fullData);
      } catch {
        setResult(data);
      }
    } catch (err: any) {
      setError(err.message || "Failed to process driver verification");
    } finally {
      setLoading(false);
    }
  };

  const renderUploadBox = (
    label: string,
    icon: React.ReactNode,
    state: DocFileState,
    setState: React.Dispatch<React.SetStateAction<DocFileState>>,
    hasBack: boolean = true
  ) => {
    return (
      <div style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.85rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 700, fontSize: "0.95rem" }}>
          {icon}
          {label}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: hasBack ? "1fr 1fr" : "1fr", gap: "0.75rem" }}>
          {/* Front Image Dropzone */}
          <label className={`dropzone ${state.front ? "has-file" : ""}`}>
            <input
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0] || null;
                setState((prev) => ({ ...prev, front: file }));
              }}
            />
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.35rem" }}>
              {state.front ? <CheckCircle size={20} color="var(--status-matched)" /> : <Upload size={20} color="var(--text-muted)" />}
              <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>
                {state.front ? state.front.name.slice(0, 18) + "..." : "Front Image"}
              </span>
            </div>
          </label>

          {/* Back Image Dropzone */}
          {hasBack && (
            <label className={`dropzone ${state.back ? "has-file" : ""}`}>
              <input
                type="file"
                accept="image/*"
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0] || null;
                  setState((prev) => ({ ...prev, back: file }));
                }}
              />
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.35rem" }}>
                {state.back ? <CheckCircle size={20} color="var(--status-matched)" /> : <Upload size={20} color="var(--text-muted)" />}
                <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>
                  {state.back ? state.back.name.slice(0, 18) + "..." : "Back Image"}
                </span>
              </div>
            </label>
          )}
        </div>
      </div>
    );
  };

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
      {/* Upload Form Panel */}
      <div className="glass-panel" style={{ padding: "2rem", marginBottom: "2rem" }}>
        <h2 style={{ fontSize: "1.35rem", fontWeight: 800, marginBottom: "0.35rem" }}>
          Single Driver KYC & Document Onboarding
        </h2>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1.5rem" }}>
          Upload identity and vehicle documents. The microservices cluster will extract fields and run 3-way cross-validation.
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem", marginBottom: "1.5rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.4rem" }}>
                Driver Identification / Mobile Number *
              </label>
              <input
                type="text"
                placeholder="e.g. 7203075793 or DRV-2026-001"
                value={driverId}
                onChange={(e) => setDriverId(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.75rem 1rem",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--text-primary)",
                  fontSize: "0.95rem",
                  outline: "none",
                }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.4rem" }}>
                Expected Vehicle Class (2 wheeler, 3 wheeler, car, truck)
              </label>
              <input
                type="text"
                placeholder="e.g. 3 wheeler, 2 wheeler, car, truck"
                value={vehicleClass}
                onChange={(e) => setVehicleClass(e.target.value)}
                list="vehicle-class-list"
                style={{
                  width: "100%",
                  padding: "0.75rem 1rem",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--text-primary)",
                  fontSize: "0.95rem",
                  outline: "none",
                }}
              />
              <datalist id="vehicle-class-list">
                <option value="2 wheeler" />
                <option value="3 wheeler" />
                <option value="car" />
                <option value="truck" />
              </datalist>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "1rem", marginBottom: "1.75rem" }}>
            {renderUploadBox("Aadhaar Card", <IdCard size={18} color="var(--accent-primary)" />, aadhaar, setAadhaar, true)}
            {renderUploadBox("Driving Licence", <CreditCard size={18} color="var(--accent-cyan)" />, licence, setLicence, true)}
            {renderUploadBox("PAN Card", <Shield size={18} color="#f59e0b" />, pan, setPan, false)}
            {renderUploadBox("Vehicle RC", <Car size={18} color="#ec4899" />, rc, setRc, true)}
          </div>

          {error && (
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
              background: "var(--status-mismatch-bg)",
              border: "1px solid var(--status-mismatch-border)",
              color: "var(--status-mismatch)",
              padding: "0.85rem 1.25rem",
              borderRadius: "var(--radius-md)",
              marginBottom: "1.5rem",
              fontSize: "0.88rem",
            }}>
              <AlertCircle size={18} />
              {error}
            </div>
          )}

          <button type="submit" className="btn-primary" disabled={loading} style={{ padding: "0.85rem 2rem", fontSize: "1rem" }}>
            {loading ? (
              <>
                <RefreshCw size={18} className="animate-spin" />
                Processing Across 7 Microservices...
              </>
            ) : (
              <>
                <Shield size={18} />
                Verify Driver Documents
              </>
            )}
          </button>
        </form>
      </div>

      {/* Verification Results Display */}
      {result && (
        <div>
          {/* Status Result Header Banner */}
          {overallStatus !== null && (
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "1rem 1.5rem",
              borderRadius: "var(--radius-md)",
              marginBottom: "1.5rem",
              background: overallStatus ? "rgba(16, 185, 129, 0.12)" : "rgba(239, 68, 68, 0.12)",
              border: `1px solid ${overallStatus ? "rgba(16, 185, 129, 0.35)" : "rgba(239, 68, 68, 0.35)"}`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                {overallStatus ? (
                  <CheckCircle size={24} color="var(--status-matched)" />
                ) : (
                  <AlertCircle size={24} color="var(--status-mismatch)" />
                )}
                <div>
                  <div style={{ fontWeight: 800, fontSize: "1.05rem", color: overallStatus ? "var(--status-matched)" : "var(--status-mismatch)" }}>
                    Verification Status: {overallStatus ? "APPROVED (true)" : "REJECTED (false)"}
                  </div>
                  <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                    Driver ID: <strong>{driverId}</strong> &bull; Expected Class: <strong>{vehicleClass || "None (Mandatory)"}</strong> &bull; RC Extracted Class: <strong>{result?.extraction?.documents?.rc?.data?.vehicle_class || "None"}</strong>
                  </div>
                </div>
              </div>
              <div style={{
                fontSize: "0.85rem",
                fontWeight: 700,
                padding: "0.4rem 1rem",
                borderRadius: "var(--radius-sm)",
                background: overallStatus ? "var(--status-matched)" : "var(--status-mismatch)",
                color: "#fff",
              }}>
                over_all_status: {overallStatus ? "true" : "false"}
              </div>
            </div>
          )}

          {/* Identity Matrix */}
          <CrossMatchMatrix report={result.cross_validation} />

          {/* Document Extraction Details Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem" }}>
            {/* Aadhaar Details */}
            <div className="glass-panel" style={{ padding: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", fontWeight: 700 }}>
                <IdCard size={18} color="var(--accent-primary)" />
                Aadhaar Extraction
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.82rem" }}>
                <div><span style={{ color: "var(--text-muted)" }}>UID:</span> <strong>{result.extraction.documents.aadhaar.data?.aadhaar_number || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Name:</span> <strong>{result.extraction.documents.aadhaar.data?.full_name || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>DOB:</span> <strong>{result.extraction.documents.aadhaar.data?.date_of_birth || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Gender:</span> <strong>{result.extraction.documents.aadhaar.data?.gender || "—"}</strong></div>
              </div>
            </div>

            {/* DL Details */}
            <div className="glass-panel" style={{ padding: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", fontWeight: 700 }}>
                <CreditCard size={18} color="var(--accent-cyan)" />
                Driving Licence
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.82rem" }}>
                <div><span style={{ color: "var(--text-muted)" }}>DL No:</span> <strong>{result.extraction.documents.licence.data?.licence_number || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Name:</span> <strong>{result.extraction.documents.licence.data?.full_name || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>DOB:</span> <strong>{result.extraction.documents.licence.data?.date_of_birth || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Vehicle Classes:</span> <strong>{(result.extraction.documents.licence.data?.vehicle_classes || []).join(", ") || "—"}</strong></div>
              </div>
            </div>

            {/* PAN Details */}
            <div className="glass-panel" style={{ padding: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", fontWeight: 700 }}>
                <Shield size={18} color="#f59e0b" />
                PAN Card
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.82rem" }}>
                <div><span style={{ color: "var(--text-muted)" }}>PAN No:</span> <strong>{result.extraction.documents.pan.data?.pan_number || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Name:</span> <strong>{result.extraction.documents.pan.data?.full_name || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Father Name:</span> <strong>{result.extraction.documents.pan.data?.father_name || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>DOB:</span> <strong>{result.extraction.documents.pan.data?.date_of_birth || "—"}</strong></div>
              </div>
            </div>

            {/* RC Details */}
            <div className="glass-panel" style={{ padding: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", fontWeight: 700 }}>
                <Car size={18} color="#ec4899" />
                Vehicle RC
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.82rem" }}>
                <div><span style={{ color: "var(--text-muted)" }}>Reg No:</span> <strong>{result.extraction.documents.rc.data?.registration_number || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Owner:</span> <strong>{result.extraction.documents.rc.data?.owner_name || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Reg Date:</span> <strong>{result.extraction.documents.rc.data?.date_of_registration || "—"}</strong></div>
                <div><span style={{ color: "var(--text-muted)" }}>Validity:</span> <strong>{result.extraction.documents.rc.data?.registration_validity || "—"}</strong></div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
