"use client";

import React, { useState, useEffect } from "react";
import { Database, Search, Trash2, Eye, RefreshCw, CheckCircle2, AlertTriangle, XCircle, X } from "lucide-react";
import { fetchHistoricalRecords, fetchDriverRecordDetail, deleteDriverRecord } from "../lib/api";
import { HistoricalRecordItem, VerificationResult } from "../lib/types";

export const HistoricalRecords: React.FC = () => {
  const [records, setRecords] = useState<HistoricalRecordItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<VerificationResult | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadRecords = async () => {
    setLoading(true);
    try {
      const data = await fetchHistoricalRecords(100, 0, statusFilter);
      setRecords(data.drivers || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRecords();
  }, [statusFilter]);

  const handleViewDetail = async (driverId: string) => {
    setDetailLoading(true);
    try {
      const detail = await fetchDriverRecordDetail(driverId);
      setSelectedRecord(detail);
    } catch (err) {
      console.error(err);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDelete = async (driverId: string) => {
    if (!confirm(`Are you sure you want to delete records for driver ${driverId}?`)) return;
    try {
      await deleteDriverRecord(driverId);
      loadRecords();
      if (selectedRecord?.driver_id === driverId) {
        setSelectedRecord(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case "MATCH":
      case "MATCHED":
        return <span className="badge badge-matched"><CheckCircle2 size={12} /> MATCHED</span>;
      case "REVIEW":
        return <span className="badge badge-review"><AlertTriangle size={12} /> REVIEW</span>;
      case "MISMATCH":
        return <span className="badge badge-mismatch"><XCircle size={12} /> MISMATCH</span>;
      default:
        return <span className="badge badge-neutral">{status}</span>;
    }
  };

  const filtered = records.filter((r) => r.driver_id.toLowerCase().includes(search.toLowerCase()));

  return (
    <div style={{ maxWidth: "1300px", margin: "0 auto" }}>
      {/* Records Header Card */}
      <div className="glass-panel" style={{ padding: "1.75rem", marginBottom: "1.75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, display: "flex", alignItems: "center", gap: "0.6rem" }}>
              <Database color="var(--accent-primary)" />
              Verified Driver KYC Records
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "4px" }}>
              Browse and inspect all persisted extraction & identity validation reports ({total} total records).
            </p>
          </div>

          <button onClick={loadRecords} disabled={loading} className="btn-secondary">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        {/* Filter Bar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", marginTop: "1.25rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "1.25rem" }}>
          <div style={{ position: "relative", minWidth: "300px" }}>
            <Search size={16} style={{ position: "absolute", left: "1rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input
              type="text"
              placeholder="Search driver ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: "100%",
                padding: "0.6rem 1rem 0.6rem 2.5rem",
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
            {["ALL", "MATCHED", "REVIEW", "MISMATCH"].map((tab) => (
              <button
                key={tab}
                onClick={() => setStatusFilter(tab)}
                style={{
                  padding: "0.45rem 0.9rem",
                  borderRadius: "var(--radius-full)",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  border: "1px solid",
                  cursor: "pointer",
                  borderColor: statusFilter === tab ? "var(--accent-primary)" : "var(--border-subtle)",
                  background: statusFilter === tab ? "var(--accent-primary)" : "var(--bg-secondary)",
                  color: statusFilter === tab ? "#ffffff" : "var(--text-secondary)",
                }}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Records Table */}
      <div className="glass-panel" style={{ overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.88rem" }}>
          <thead>
            <tr style={{ background: "rgba(255, 255, 255, 0.03)", borderBottom: "1px solid var(--border-subtle)", color: "var(--text-secondary)", fontSize: "0.75rem", textTransform: "uppercase" }}>
              <th style={{ padding: "1rem 1.25rem" }}>Driver ID</th>
              <th style={{ padding: "1rem 1.25rem" }}>Overall Status</th>
              <th style={{ padding: "1rem 1.25rem" }}>Name Status</th>
              <th style={{ padding: "1rem 1.25rem" }}>DOB Status</th>
              <th style={{ padding: "1rem 1.25rem", textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.driver_id} style={{ borderBottom: "1px solid var(--border-subtle)", transition: "background 0.2s ease" }}>
                <td style={{ padding: "1rem 1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>{row.driver_id}</td>
                <td style={{ padding: "1rem 1.25rem" }}>{getStatusBadge(row.overall_status)}</td>
                <td style={{ padding: "1rem 1.25rem" }}>{getStatusBadge(row.name_status)}</td>
                <td style={{ padding: "1rem 1.25rem" }}>{getStatusBadge(row.dob_status)}</td>
                <td style={{ padding: "1rem 1.25rem", textAlign: "right" }}>
                  <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                    <button
                      onClick={() => handleViewDetail(row.driver_id)}
                      className="btn-secondary"
                      style={{ padding: "0.4rem 0.75rem", fontSize: "0.78rem" }}
                    >
                      <Eye size={14} />
                      Inspect
                    </button>
                    <button
                      onClick={() => handleDelete(row.driver_id)}
                      style={{
                        padding: "0.4rem 0.75rem",
                        fontSize: "0.78rem",
                        background: "rgba(239, 68, 68, 0.1)",
                        border: "1px solid rgba(239, 68, 68, 0.3)",
                        color: "var(--status-mismatch)",
                        borderRadius: "var(--radius-md)",
                        cursor: "pointer",
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
                  No verified driver records found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* JSON Inspector Modal */}
      {selectedRecord && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(0, 0, 0, 0.8)",
          backdropFilter: "blur(8px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 100,
          padding: "2rem",
        }}>
          <div className="glass-panel" style={{
            maxWidth: "900px",
            width: "100%",
            maxHeight: "85vh",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            background: "var(--bg-secondary)",
          }}>
            <div style={{ padding: "1.25rem 1.75rem", borderBottom: "1px solid var(--border-subtle)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Record Detail: {selectedRecord.driver_id}</h3>
              <button onClick={() => setSelectedRecord(null)} style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}>
                <X size={20} />
              </button>
            </div>
            <div style={{ padding: "1.5rem", overflowY: "auto", flex: 1 }}>
              <pre style={{ fontSize: "0.8rem", color: "var(--text-primary)", background: "var(--bg-primary)", padding: "1.25rem", borderRadius: "var(--radius-md)" }}>
                {JSON.stringify(selectedRecord, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
