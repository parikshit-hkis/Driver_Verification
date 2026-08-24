"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, User, Calendar, ShieldAlert } from "lucide-react";
import { CrossValidationReport } from "../lib/types";

interface Props {
  report: CrossValidationReport;
}

export const CrossMatchMatrix: React.FC<Props> = ({ report }) => {
  const getStatusBadge = (status?: string) => {
    const s = (status || "").toUpperCase();
    if (s === "MATCH" || s === "MATCHED" || s === "APPROVED") {
      return (
        <span className="badge badge-matched" style={{ fontWeight: 700 }}>
          <CheckCircle2 size={13} />
          APPROVED
        </span>
      );
    } else if (s === "REVIEW") {
      return (
        <span className="badge badge-review" style={{ fontWeight: 700 }}>
          <AlertTriangle size={13} />
          REVIEW
        </span>
      );
    } else if (s === "MISMATCH" || s === "MISMATCHED" || s === "REJECTED" || s === "FAILED") {
      return (
        <span className="badge badge-mismatch" style={{ fontWeight: 700 }}>
          <XCircle size={13} />
          REJECTED
        </span>
      );
    }
    return <span className="badge badge-neutral">{status || "MISSING"}</span>;
  };

  return (
    <div className="glass-panel" style={{ padding: "1.5rem", marginBottom: "1.5rem" }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "1rem",
        marginBottom: "1.25rem",
        borderBottom: "1px solid var(--border-subtle)",
        paddingBottom: "1rem",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{
            background: "rgba(99, 102, 241, 0.15)",
            padding: "0.6rem",
            borderRadius: "10px",
            color: "var(--accent-primary)",
          }}>
            <ShieldAlert size={22} />
          </div>
          <div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Identity Cross-Validation Matrix</h3>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Multi-document fuzzy Name similarity and exact DOB cross-matching
            </p>
          </div>
        </div>

        {/* Overall Status Banner */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>
              Overall Identity Result
            </div>
            <div style={{ marginTop: "2px" }}>
              {getStatusBadge(report.overall_status)}
            </div>
          </div>
        </div>
      </div>

      {/* 3 Pairwise Rows */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1rem" }}>
        {/* Aadhaar vs PAN */}
        <div style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
          padding: "1.1rem",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <span style={{ fontWeight: 700, fontSize: "0.88rem", color: "var(--accent-primary)" }}>Aadhaar ↔ PAN</span>
            {getStatusBadge(report.aadhaar_vs_pan?.status)}
          </div>

          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "0.4rem 0.6rem", borderRadius: "6px" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><User size={13} /> Name Similarity:</span>
              <span style={{ fontWeight: 700, color: (report.aadhaar_vs_pan?.name.similarity || 0) >= 75 ? "var(--status-matched)" : "var(--status-mismatch)" }}>
                {report.aadhaar_vs_pan?.name.similarity ? `${report.aadhaar_vs_pan.name.similarity.toFixed(1)}%` : "—"}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "0.4rem 0.6rem", borderRadius: "6px" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Calendar size={13} /> DOB Match:</span>
              {getStatusBadge(report.aadhaar_vs_pan?.date_of_birth.status)}
            </div>
          </div>
        </div>

        {/* Aadhaar vs DL */}
        <div style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
          padding: "1.1rem",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <span style={{ fontWeight: 700, fontSize: "0.88rem", color: "var(--accent-primary)" }}>Aadhaar ↔ Licence</span>
            {getStatusBadge(report.aadhaar_vs_licence?.status)}
          </div>

          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "0.4rem 0.6rem", borderRadius: "6px" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><User size={13} /> Name Similarity:</span>
              <span style={{ fontWeight: 700, color: (report.aadhaar_vs_licence?.name.similarity || 0) >= 75 ? "var(--status-matched)" : "var(--status-mismatch)" }}>
                {report.aadhaar_vs_licence?.name.similarity ? `${report.aadhaar_vs_licence.name.similarity.toFixed(1)}%` : "—"}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "0.4rem 0.6rem", borderRadius: "6px" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Calendar size={13} /> DOB Match:</span>
              {getStatusBadge(report.aadhaar_vs_licence?.date_of_birth.status)}
            </div>
          </div>
        </div>

        {/* PAN vs DL */}
        <div style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
          padding: "1.1rem",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <span style={{ fontWeight: 700, fontSize: "0.88rem", color: "var(--accent-primary)" }}>PAN ↔ Licence</span>
            {getStatusBadge(report.pan_vs_licence?.status)}
          </div>

          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "0.4rem 0.6rem", borderRadius: "6px" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><User size={13} /> Name Similarity:</span>
              <span style={{ fontWeight: 700, color: (report.pan_vs_licence?.name.similarity || 0) >= 75 ? "var(--status-matched)" : "var(--status-mismatch)" }}>
                {report.pan_vs_licence?.name.similarity ? `${report.pan_vs_licence.name.similarity.toFixed(1)}%` : "—"}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "0.4rem 0.6rem", borderRadius: "6px" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Calendar size={13} /> DOB Match:</span>
              {getStatusBadge(report.pan_vs_licence?.date_of_birth.status)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
