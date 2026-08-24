"use client";

import React, { useState } from "react";
import { Layers, Play, CheckCircle2, AlertTriangle, XCircle, Search, FileText, Activity } from "lucide-react";
import { verifyFolderBatch } from "../lib/api";
import { BatchVerificationResponse, BatchDriverSummary } from "../lib/types";

export const BatchRunner: React.FC = () => {
  const [folderPath, setFolderPath] = useState("sample_documents");
  const [concurrency, setConcurrency] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [batchResult, setBatchResult] = useState<BatchVerificationResponse | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const handleRunBatch = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await verifyFolderBatch(folderPath, concurrency);
      setBatchResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to execute bulk batch verification");
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "MATCH" || s === "MATCHED" || s === "APPROVED") {
      return <span className="badge badge-matched"><CheckCircle2 size={12} /> APPROVED</span>;
    } else if (s === "REVIEW") {
      return <span className="badge badge-review"><AlertTriangle size={12} /> REVIEW</span>;
    } else if (s === "MISMATCH" || s === "MISMATCHED" || s === "REJECTED" || s === "FAILED") {
      return <span className="badge badge-mismatch"><XCircle size={12} /> REJECTED</span>;
    }
    return <span className="badge badge-neutral">{status}</span>;
  };

  const filteredDrivers = (batchResult?.drivers || []).filter((d) => {
    const matchesSearch =
      d.driver_id.toLowerCase().includes(searchFilter.toLowerCase()) ||
      (d.extracted_name && d.extracted_name.toLowerCase().includes(searchFilter.toLowerCase())) ||
      (d.licence_number && d.licence_number.toLowerCase().includes(searchFilter.toLowerCase()));

    const s = d.overall_status.toUpperCase();
    let matchesStatus = statusFilter === "ALL";
    if (statusFilter === "APPROVED") matchesStatus = s === "APPROVED" || s === "MATCHED" || s === "MATCH";
    else if (statusFilter === "REVIEW") matchesStatus = s === "REVIEW";
    else if (statusFilter === "REJECTED") matchesStatus = s === "REJECTED" || s === "MISMATCH" || s === "MISMATCHED" || s === "FAILED";
    else if (statusFilter !== "ALL") matchesStatus = s === statusFilter;

    return matchesSearch && matchesStatus;
  });

  return (
    <div style={{ maxWidth: "1300px", margin: "0 auto" }}>
      {/* Batch Control Card */}
      <div className="glass-panel" style={{ padding: "2rem", marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
          <div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, display: "flex", alignItems: "center", gap: "0.6rem" }}>
              <Layers color="var(--accent-primary)" />
              Bulk Batch Driver Verification
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "4px" }}>
              Scan local or server directory, execute asynchronous multi-document extraction, and cross-validate identity in bulk.
            </p>
          </div>

          <button
            onClick={handleRunBatch}
            disabled={loading}
            className="btn-primary"
            style={{ padding: "0.85rem 2rem", fontSize: "0.95rem" }}
          >
            {loading ? (
              <>
                <Activity size={18} className="animate-spin" />
                Running Batch Extraction...
              </>
            ) : (
              <>
                <Play size={18} fill="#ffffff" />
                Run Bulk Verification
              </>
            )}
          </button>
        </div>

        {/* Input Parameters Row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "1.25rem" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.4rem" }}>
              Source Folder Path
            </label>
            <input
              type="text"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              placeholder="e.g. sample_documents"
              style={{
                width: "100%",
                padding: "0.7rem 1rem",
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                color: "var(--text-primary)",
                fontSize: "0.9rem",
                outline: "none",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.4rem" }}>
              Worker Concurrency Pool (Safe for GPU VRAM)
            </label>
            <select
              value={concurrency}
              onChange={(e) => setConcurrency(Number(e.target.value))}
              style={{
                width: "100%",
                padding: "0.7rem 1rem",
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                color: "var(--text-primary)",
                fontSize: "0.9rem",
                outline: "none",
              }}
            >
              <option value={1}>1 Worker (Sequential / Lowest VRAM Usage)</option>
              <option value={2}>2 Concurrent Workers (Balanced)</option>
              <option value={4}>4 Concurrent Workers (High Throughput)</option>
            </select>
          </div>
        </div>

        {error && (
          <div style={{
            background: "var(--status-mismatch-bg)",
            border: "1px solid var(--status-mismatch-border)",
            color: "var(--status-mismatch)",
            padding: "0.85rem 1.25rem",
            borderRadius: "var(--radius-md)",
            marginTop: "1.5rem",
            fontSize: "0.88rem",
          }}>
            {error}
          </div>
        )}
      </div>

      {/* Results & Statistics Section */}
      {batchResult && (
        <div>
          {/* Stats Bar */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "1rem",
            marginBottom: "1.5rem",
          }}>
            <div className="glass-panel" style={{ padding: "1.25rem" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Total Verified</div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, marginTop: "4px" }}>{batchResult.total_drivers}</div>
            </div>

            <div className="glass-panel" style={{ padding: "1.25rem", borderLeft: "4px solid var(--status-matched)" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--status-matched)", textTransform: "uppercase", fontWeight: 700 }}>Approved (Pass)</div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--status-matched)", marginTop: "4px" }}>
                {batchResult.statistics.MATCHED}
              </div>
            </div>

            <div className="glass-panel" style={{ padding: "1.25rem", borderLeft: "4px solid var(--status-review)" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--status-review)", textTransform: "uppercase", fontWeight: 700 }}>Manual Review</div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--status-review)", marginTop: "4px" }}>
                {batchResult.statistics.REVIEW}
              </div>
            </div>

            <div className="glass-panel" style={{ padding: "1.25rem", borderLeft: "4px solid var(--status-mismatch)" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--status-mismatch)", textTransform: "uppercase", fontWeight: 700 }}>Rejected / Flagged</div>
              <div style={{ fontSize: "1.75rem", fontWeight: 800, color: "var(--status-mismatch)", marginTop: "4px" }}>
                {batchResult.statistics.MISMATCH}
              </div>
            </div>
          </div>

          {/* Search & Filter Controls */}
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
            marginBottom: "1.25rem",
          }}>
            <div style={{ position: "relative", minWidth: "300px" }}>
              <Search size={16} style={{ position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
              <input
                type="text"
                placeholder="Search by Driver ID, Name or DL No..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.65rem 1rem 0.65rem 2.5rem",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--text-primary)",
                  fontSize: "0.85rem",
                  outline: "none",
                }}
              />
            </div>

            <div style={{ display: "flex", gap: "0.5rem" }}>
              {[
                { key: "ALL", label: "ALL" },
                { key: "APPROVED", label: "APPROVED" },
                { key: "REVIEW", label: "REVIEW" },
                { key: "REJECTED", label: "REJECTED" },
              ].map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setStatusFilter(tab.key)}
                  style={{
                    padding: "0.45rem 0.9rem",
                    borderRadius: "var(--radius-full)",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    border: "1px solid",
                    cursor: "pointer",
                    transition: "all 0.2s ease",
                    borderColor: statusFilter === tab.key ? "var(--accent-primary)" : "var(--border-subtle)",
                    background: statusFilter === tab.key ? "var(--accent-primary)" : "var(--bg-secondary)",
                    color: statusFilter === tab.key ? "#ffffff" : "var(--text-secondary)",
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Driver Cards Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(350px, 1fr))", gap: "1rem" }}>
            {filteredDrivers.map((driver) => (
              <div key={driver.driver_id} className="glass-panel" style={{ padding: "1.25rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                  <div>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>Driver ID</span>
                    <h4 style={{ fontSize: "1.05rem", fontWeight: 700 }}>{driver.driver_id}</h4>
                  </div>
                  {getStatusBadge(driver.overall_status)}
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", fontSize: "0.82rem", color: "var(--text-secondary)", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.75rem" }}>
                  <div><span style={{ color: "var(--text-muted)" }}>Extracted Name:</span> <strong style={{ color: "#ffffff" }}>{driver.extracted_name || "—"}</strong></div>
                  <div><span style={{ color: "var(--text-muted)" }}>Licence No:</span> <strong>{driver.licence_number || "—"}</strong></div>
                  <div><span style={{ color: "var(--text-muted)" }}>Vehicle Classes:</span> <strong>{(driver.vehicle_classes || []).join(", ") || "—"}</strong></div>
                  <div><span style={{ color: "var(--text-muted)" }}>Vehicle Reg No:</span> <strong>{driver.rc_number || "—"}</strong></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
