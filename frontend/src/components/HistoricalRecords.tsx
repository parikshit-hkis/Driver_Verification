"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Database,
  Search,
  Trash2,
  Eye,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  X,
  User,
  Calendar,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { fetchHistoricalRecords, fetchDriverRecordDetail, deleteDriverRecord } from "../lib/api";
import { HistoricalRecordItem, VerificationResult } from "../lib/types";

interface HoverPopoverState {
  driverId: string;
  driverName?: string;
  type: "name" | "dob";
  status: string;
  x: number;
  y: number;
  jsonData: Record<string, any>;
}

export const HistoricalRecords: React.FC = () => {
  const [records, setRecords] = useState<HistoricalRecordItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<VerificationResult | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [hoverPopover, setHoverPopover] = useState<HoverPopoverState | null>(null);
  const [copied, setCopied] = useState(false);

  // ── Pagination State ──
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [jumpPageInput, setJumpPageInput] = useState("");

  // ── Global Dataset Summary Stats (Across all pages) ──
  const [serverSummary, setServerSummary] = useState<{
    total: number;
    approved: number;
    review: number;
    rejected: number;
    pass_rate: number;
  }>({
    total: 0,
    approved: 0,
    review: 0,
    rejected: 0,
    pass_rate: 0,
  });

  const hoverTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  const loadRecords = async () => {
    setLoading(true);
    try {
      const offset = (currentPage - 1) * pageSize;
      const data = await fetchHistoricalRecords(pageSize, offset, statusFilter);
      setRecords(data.drivers || []);
      setTotal(data.total || 0);
      if (data.summary) {
        setServerSummary(data.summary);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Reload when page, pageSize, or statusFilter changes
  useEffect(() => {
    loadRecords();
  }, [currentPage, pageSize, statusFilter]);

  // Reset to page 1 when filter changes
  const handleStatusFilterChange = (newFilter: string) => {
    setStatusFilter(newFilter);
    setCurrentPage(1);
  };

  // Reset to page 1 when page size changes
  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    setCurrentPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages && newPage !== currentPage) {
      setCurrentPage(newPage);
    }
  };

  const handleJumpPage = (e: React.FormEvent) => {
    e.preventDefault();
    const p = parseInt(jumpPageInput, 10);
    if (!isNaN(p) && p >= 1 && p <= totalPages) {
      setCurrentPage(p);
      setJumpPageInput("");
    }
  };

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

  /**
   * Change 1: Overall Status badge showing APPROVED / REVIEW / REJECTED
   */
  const getOverallStatusBadge = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "MATCH" || s === "MATCHED" || s === "APPROVED") {
      return (
        <span className="badge badge-matched" style={{ fontWeight: 700 }}>
          <CheckCircle2 size={13} /> APPROVED
        </span>
      );
    } else if (s === "REVIEW") {
      return (
        <span className="badge badge-review" style={{ fontWeight: 700 }}>
          <AlertTriangle size={13} /> REVIEW
        </span>
      );
    } else if (s === "MISMATCH" || s === "MISMATCHED" || s === "REJECTED" || s === "FAILED") {
      return (
        <span className="badge badge-mismatch" style={{ fontWeight: 700 }}>
          <XCircle size={13} /> REJECTED
        </span>
      );
    }
    return <span className="badge badge-neutral">{status || "UNKNOWN"}</span>;
  };

  /**
   * Field Status badge for Name and DOB columns
   */
  const getFieldStatusBadge = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "MATCH" || s === "MATCHED") {
      return (
        <span className="badge badge-matched" style={{ cursor: "pointer", transition: "transform 0.15s ease" }}>
          <CheckCircle2 size={12} /> MATCHED
        </span>
      );
    } else if (s === "REVIEW") {
      return (
        <span className="badge badge-review" style={{ cursor: "pointer", transition: "transform 0.15s ease" }}>
          <AlertTriangle size={12} /> REVIEW
        </span>
      );
    } else if (s === "MISMATCH" || s === "MISMATCHED") {
      return (
        <span className="badge badge-mismatch" style={{ cursor: "pointer", transition: "transform 0.15s ease" }}>
          <XCircle size={12} /> MISMATCH
        </span>
      );
    }
    return (
      <span className="badge badge-neutral" style={{ cursor: "pointer" }}>
        {status || "MISSING"}
      </span>
    );
  };

  /**
   * Builds the exact sub-JSON object for Name or DOB validation breakdown
   */
  const buildFieldValidationJson = (valData: any, type: "name" | "dob") => {
    if (!valData) return { message: "No validation details found for this record." };

    if (type === "dob") {
      return {
        "aadhaar_vs_pan": valData.aadhaar_vs_pan?.date_of_birth
          ? {
              "date_of_birth": {
                "doc1_key": valData.aadhaar_vs_pan.date_of_birth.doc1_key || "aadhaar",
                "doc2_key": valData.aadhaar_vs_pan.date_of_birth.doc2_key || "pan",
                "doc1_dob": valData.aadhaar_vs_pan.date_of_birth.doc1_dob ?? null,
                "doc2_dob": valData.aadhaar_vs_pan.date_of_birth.doc2_dob ?? null,
                "status": valData.aadhaar_vs_pan.date_of_birth.status ?? "MISSING",
              },
              "status": valData.aadhaar_vs_pan.date_of_birth.status ?? "MISSING",
            }
          : { "status": "MISSING" },
        "aadhaar_vs_licence": valData.aadhaar_vs_licence?.date_of_birth
          ? {
              "date_of_birth": {
                "doc1_key": valData.aadhaar_vs_licence.date_of_birth.doc1_key || "aadhaar",
                "doc2_key": valData.aadhaar_vs_licence.date_of_birth.doc2_key || "licence",
                "doc1_dob": valData.aadhaar_vs_licence.date_of_birth.doc1_dob ?? null,
                "doc2_dob": valData.aadhaar_vs_licence.date_of_birth.doc2_dob ?? null,
                "status": valData.aadhaar_vs_licence.date_of_birth.status ?? "MISSING",
              },
              "status": valData.aadhaar_vs_licence.date_of_birth.status ?? "MISSING",
            }
          : { "status": "MISSING" },
        "pan_vs_licence": valData.pan_vs_licence?.date_of_birth
          ? {
              "date_of_birth": {
                "doc1_key": valData.pan_vs_licence.date_of_birth.doc1_key || "pan",
                "doc2_key": valData.pan_vs_licence.date_of_birth.doc2_key || "licence",
                "doc1_dob": valData.pan_vs_licence.date_of_birth.doc1_dob ?? null,
                "doc2_dob": valData.pan_vs_licence.date_of_birth.doc2_dob ?? null,
                "status": valData.pan_vs_licence.date_of_birth.status ?? "MISSING",
              },
              "status": valData.pan_vs_licence.date_of_birth.status ?? "MISSING",
            }
          : { "status": "MISSING" },
      };
    } else {
      return {
        "aadhaar_vs_pan": valData.aadhaar_vs_pan?.name
          ? {
              "name": {
                "doc1_key": valData.aadhaar_vs_pan.name.doc1_key || "aadhaar",
                "doc2_key": valData.aadhaar_vs_pan.name.doc2_key || "pan",
                "doc1_name": valData.aadhaar_vs_pan.name.doc1_name ?? null,
                "doc2_name": valData.aadhaar_vs_pan.name.doc2_name ?? null,
                "similarity": valData.aadhaar_vs_pan.name.similarity ?? 0.0,
                "status": valData.aadhaar_vs_pan.name.status ?? "MISSING",
              },
            }
          : { "status": "MISSING" },
        "aadhaar_vs_licence": valData.aadhaar_vs_licence?.name
          ? {
              "name": {
                "doc1_key": valData.aadhaar_vs_licence.name.doc1_key || "aadhaar",
                "doc2_key": valData.aadhaar_vs_licence.name.doc2_key || "licence",
                "doc1_name": valData.aadhaar_vs_licence.name.doc1_name ?? null,
                "doc2_name": valData.aadhaar_vs_licence.name.doc2_name ?? null,
                "similarity": valData.aadhaar_vs_licence.name.similarity ?? 0.0,
                "status": valData.aadhaar_vs_licence.name.status ?? "MISSING",
              },
            }
          : { "status": "MISSING" },
        "pan_vs_licence": valData.pan_vs_licence?.name
          ? {
              "name": {
                "doc1_key": valData.pan_vs_licence.name.doc1_key || "pan",
                "doc2_key": valData.pan_vs_licence.name.doc2_key || "licence",
                "doc1_name": valData.pan_vs_licence.name.doc1_name ?? null,
                "doc2_name": valData.pan_vs_licence.name.doc2_name ?? null,
                "similarity": valData.pan_vs_licence.name.similarity ?? 0.0,
                "status": valData.pan_vs_licence.name.status ?? "MISSING",
              },
            }
          : { "status": "MISSING" },
      };
    }
  };

  /**
   * Handle Mouse Enter on Name or DOB badge to display medium-sized hover popover
   */
  const handleBadgeMouseEnter = (
    e: React.MouseEvent<HTMLElement>,
    row: HistoricalRecordItem,
    type: "name" | "dob"
  ) => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }

    const rect = e.currentTarget.getBoundingClientRect();
    const valData = row.validation;
    const jsonData = buildFieldValidationJson(valData, type);
    const status = type === "name" ? row.name_status : row.dob_status;

    // Calculate smart positioning (centered horizontally near target, below if space permits)
    const popoverWidth = 460;
    let x = rect.left + rect.width / 2 - popoverWidth / 2;
    if (x + popoverWidth > window.innerWidth - 20) {
      x = window.innerWidth - popoverWidth - 20;
    }
    if (x < 20) x = 20;

    let y = rect.bottom + 8;
    if (y + 360 > window.innerHeight && rect.top > 370) {
      y = rect.top - 370;
    }

    setHoverPopover({
      driverId: row.driver_id,
      driverName: row.driver_name || row.name,
      type,
      status,
      x,
      y,
      jsonData,
    });
  };

  const handleBadgeMouseLeave = () => {
    hoverTimeoutRef.current = setTimeout(() => {
      setHoverPopover(null);
      setCopied(false);
    }, 200);
  };

  const handlePopoverMouseEnter = () => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
  };

  const handlePopoverMouseLeave = () => {
    hoverTimeoutRef.current = setTimeout(() => {
      setHoverPopover(null);
      setCopied(false);
    }, 200);
  };

  const handleCopyJson = () => {
    if (!hoverPopover) return;
    navigator.clipboard.writeText(JSON.stringify(hoverPopover.jsonData, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filtered = records.filter(
    (r) =>
      r.driver_id.toLowerCase().includes(search.toLowerCase()) ||
      (r.driver_name && r.driver_name.toLowerCase().includes(search.toLowerCase())) ||
      (r.name && r.name.toLowerCase().includes(search.toLowerCase()))
  );

  const statCards = [
    {
      label: "TOTAL VERIFIED",
      value: serverSummary.total || total,
      color: "var(--accent-primary)",
      bg: "rgba(99, 102, 241, 0.08)",
      borderColor: "rgba(99, 102, 241, 0.5)",
      sub: `Page ${currentPage} of ${totalPages}`,
    },
    {
      label: "APPROVED (PASS)",
      value: serverSummary.approved,
      color: "var(--status-matched)",
      bg: "var(--status-matched-bg)",
      borderColor: "var(--status-matched-border)",
      sub: `${serverSummary.pass_rate}% overall pass rate`,
    },
    {
      label: "MANUAL REVIEW",
      value: serverSummary.review,
      color: "var(--status-review)",
      bg: "var(--status-review-bg)",
      borderColor: "var(--status-review-border)",
      sub: "Needs manual inspection",
    },
    {
      label: "REJECTED / FLAGGED",
      value: serverSummary.rejected,
      color: "var(--status-mismatch)",
      bg: "var(--status-mismatch-bg)",
      borderColor: "var(--status-mismatch-border)",
      sub: "Mismatched identity",
    },
  ];

  // Helper for generating pagination page numbers
  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      if (currentPage <= 4) {
        pages.push(1, 2, 3, 4, 5, "...", totalPages);
      } else if (currentPage >= totalPages - 3) {
        pages.push(1, "...", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
      } else {
        pages.push(1, "...", currentPage - 1, currentPage, currentPage + 1, "...", totalPages);
      }
    }
    return pages;
  };

  const startRecordIdx = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endRecordIdx = Math.min(currentPage * pageSize, total);

  return (
    <div style={{ maxWidth: "1300px", margin: "0 auto" }}>
      {/* Records Header Card */}
      <div className="glass-panel" style={{ padding: "1.75rem", marginBottom: "1.75rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <h2
              style={{
                fontSize: "1.35rem",
                fontWeight: 800,
                display: "flex",
                alignItems: "center",
                gap: "0.6rem",
              }}
            >
              <Database color="var(--accent-primary)" />
              Verified Driver KYC Records
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "4px" }}>
              Browse and inspect all persisted extraction & identity validation reports ({total} total records). Hover over Name / DOB status to inspect pairwise validation.
            </p>
          </div>

          <button onClick={loadRecords} disabled={loading} className="btn-secondary">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Summary Stats Cards ── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "1rem",
          marginBottom: "1.75rem",
        }}
      >
        {statCards.map((card) => (
          <div
            key={card.label}
            style={{
              background: card.bg,
              borderLeft: `4px solid ${card.borderColor}`,
              borderRadius: "var(--radius-md)",
              padding: "1.25rem 1.5rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.35rem",
              transition: "transform 0.2s ease, box-shadow 0.2s ease",
              cursor: "default",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)";
              (e.currentTarget as HTMLDivElement).style.boxShadow = `0 6px 20px -4px ${card.borderColor}`;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)";
              (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
            }}
          >
            <span
              style={{
                fontSize: "0.68rem",
                fontWeight: 700,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--text-secondary)",
              }}
            >
              {card.label}
            </span>
            <span
              style={{
                fontSize: "2rem",
                fontWeight: 800,
                lineHeight: 1.1,
                color: card.color,
              }}
            >
              {card.value}
            </span>
            {card.sub && (
              <span
                style={{
                  fontSize: "0.73rem",
                  fontWeight: 500,
                  color: "var(--text-muted)",
                  marginTop: "2px",
                }}
              >
                {card.sub}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Filter Bar */}
      <div className="glass-panel" style={{ padding: "1.25rem 1.75rem", marginBottom: "1.75rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div style={{ position: "relative", minWidth: "320px" }}>
            <Search
              size={16}
              style={{
                position: "absolute",
                left: "1rem",
                top: "50%",
                transform: "translateY(-50%)",
                color: "var(--text-muted)",
              }}
            />
            <input
              type="text"
              placeholder="Search by Driver ID or Aadhaar Name..."
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
            {[
              { key: "ALL", label: "ALL" },
              { key: "APPROVED", label: "APPROVED" },
              { key: "REVIEW", label: "REVIEW" },
              { key: "REJECTED", label: "REJECTED" },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => handleStatusFilterChange(tab.key)}
                style={{
                  padding: "0.45rem 0.9rem",
                  borderRadius: "var(--radius-full)",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  border: "1px solid",
                  cursor: "pointer",
                  borderColor:
                    statusFilter === tab.key
                      ? "var(--accent-primary)"
                      : "var(--border-subtle)",
                  background:
                    statusFilter === tab.key
                      ? "var(--accent-primary)"
                      : "var(--bg-secondary)",
                  color: statusFilter === tab.key ? "#ffffff" : "var(--text-secondary)",
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Records Table */}
      <div className="glass-panel" style={{ overflow: "visible" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            textAlign: "left",
            fontSize: "0.88rem",
          }}
        >
          <thead>
            <tr
              style={{
                background: "rgba(255, 255, 255, 0.03)",
                borderBottom: "1px solid var(--border-subtle)",
                color: "var(--text-secondary)",
                fontSize: "0.75rem",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              <th style={{ padding: "1rem 1.25rem" }}>Driver ID</th>
              <th style={{ padding: "1rem 1.25rem" }}>Driver Name (Aadhaar)</th>
              <th style={{ padding: "1rem 1.25rem" }}>Overall Status</th>
              <th style={{ padding: "1rem 1.25rem" }}>Name Status</th>
              <th style={{ padding: "1rem 1.25rem" }}>DOB Status</th>
              <th style={{ padding: "1rem 1.25rem", textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr
                key={row.driver_id}
                style={{
                  borderBottom: "1px solid var(--border-subtle)",
                  transition: "background 0.2s ease",
                }}
              >
                {/* Driver ID */}
                <td
                  style={{
                    padding: "1rem 1.25rem",
                    fontWeight: 700,
                    color: "var(--text-primary)",
                  }}
                >
                  {row.driver_id}
                </td>

                {/* Driver Name from Aadhaar Card */}
                <td
                  style={{
                    padding: "1rem 1.25rem",
                    fontWeight: 600,
                    color: row.driver_name && row.driver_name !== "-" ? "var(--text-primary)" : "var(--text-muted)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <User size={14} color="var(--accent-primary)" style={{ opacity: 0.8 }} />
                    <span>{row.driver_name || row.name || "—"}</span>
                  </div>
                </td>

                {/* Overall Status (APPROVED / REVIEW / REJECTED) */}
                <td style={{ padding: "1rem 1.25rem" }}>
                  {getOverallStatusBadge(row.overall_status)}
                </td>

                {/* Name Status with Hover Popover */}
                <td style={{ padding: "1rem 1.25rem" }}>
                  <div
                    onMouseEnter={(e) => handleBadgeMouseEnter(e, row, "name")}
                    onMouseLeave={handleBadgeMouseLeave}
                    style={{ display: "inline-block" }}
                  >
                    {getFieldStatusBadge(row.name_status)}
                  </div>
                </td>

                {/* DOB Status with Hover Popover */}
                <td style={{ padding: "1rem 1.25rem" }}>
                  <div
                    onMouseEnter={(e) => handleBadgeMouseEnter(e, row, "dob")}
                    onMouseLeave={handleBadgeMouseLeave}
                    style={{ display: "inline-block" }}
                  >
                    {getFieldStatusBadge(row.dob_status)}
                  </div>
                </td>

                {/* Actions */}
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
                <td
                  colSpan={6}
                  style={{
                    padding: "3rem",
                    textAlign: "center",
                    color: "var(--text-muted)",
                  }}
                >
                  {loading ? "Loading verified records..." : "No verified driver records found."}
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {/* ── Pagination Controls & Page Size Selector Bar ── */}
        <div
          style={{
            padding: "1.1rem 1.5rem",
            background: "rgba(255, 255, 255, 0.02)",
            borderTop: "1px solid var(--border-subtle)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
            fontSize: "0.82rem",
          }}
        >
          {/* Left: Range Info & Page Size Dropdown */}
          <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", flexWrap: "wrap" }}>
            <span style={{ color: "var(--text-secondary)" }}>
              Showing <strong style={{ color: "var(--text-primary)" }}>{startRecordIdx}–{endRecordIdx}</strong> of{" "}
              <strong style={{ color: "var(--text-primary)" }}>{total}</strong> drivers
            </span>

            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Rows per page:</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color: "var(--text-primary)",
                  padding: "0.3rem 0.6rem",
                  fontSize: "0.8rem",
                  outline: "none",
                  cursor: "pointer",
                }}
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>

          {/* Right: Page Navigation & Quick Jump */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            {/* Navigation Buttons */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
              {/* First Page */}
              <button
                onClick={() => handlePageChange(1)}
                disabled={currentPage === 1 || loading}
                title="First Page"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color: currentPage === 1 ? "var(--text-muted)" : "var(--text-primary)",
                  padding: "0.4rem 0.5rem",
                  cursor: currentPage === 1 ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  opacity: currentPage === 1 ? 0.5 : 1,
                }}
              >
                <ChevronsLeft size={15} />
              </button>

              {/* Previous Page */}
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1 || loading}
                title="Previous Page"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color: currentPage === 1 ? "var(--text-muted)" : "var(--text-primary)",
                  padding: "0.4rem 0.6rem",
                  cursor: currentPage === 1 ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.2rem",
                  opacity: currentPage === 1 ? 0.5 : 1,
                  fontSize: "0.78rem",
                  fontWeight: 600,
                }}
              >
                <ChevronLeft size={15} />
                <span>Prev</span>
              </button>

              {/* Numbered Page Buttons */}
              {getPageNumbers().map((pageNum, idx) =>
                typeof pageNum === "number" ? (
                  <button
                    key={idx}
                    onClick={() => handlePageChange(pageNum)}
                    disabled={loading}
                    style={{
                      background:
                        currentPage === pageNum ? "var(--accent-primary)" : "var(--bg-secondary)",
                      border: "1px solid",
                      borderColor:
                        currentPage === pageNum
                          ? "var(--accent-primary)"
                          : "var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      color: currentPage === pageNum ? "#ffffff" : "var(--text-secondary)",
                      minWidth: "32px",
                      height: "32px",
                      padding: "0 0.4rem",
                      cursor: "pointer",
                      fontSize: "0.78rem",
                      fontWeight: currentPage === pageNum ? 700 : 500,
                      transition: "all 0.15s ease",
                    }}
                  >
                    {pageNum}
                  </button>
                ) : (
                  <span
                    key={idx}
                    style={{
                      color: "var(--text-muted)",
                      padding: "0 0.3rem",
                      fontSize: "0.85rem",
                    }}
                  >
                    ...
                  </span>
                )
              )}

              {/* Next Page */}
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages || loading}
                title="Next Page"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color:
                    currentPage === totalPages
                      ? "var(--text-muted)"
                      : "var(--text-primary)",
                  padding: "0.4rem 0.6rem",
                  cursor: currentPage === totalPages ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.2rem",
                  opacity: currentPage === totalPages ? 0.5 : 1,
                  fontSize: "0.78rem",
                  fontWeight: 600,
                }}
              >
                <span>Next</span>
                <ChevronRight size={15} />
              </button>

              {/* Last Page */}
              <button
                onClick={() => handlePageChange(totalPages)}
                disabled={currentPage === totalPages || loading}
                title="Last Page"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color:
                    currentPage === totalPages
                      ? "var(--text-muted)"
                      : "var(--text-primary)",
                  padding: "0.4rem 0.5rem",
                  cursor: currentPage === totalPages ? "not-allowed" : "pointer",
                  display: "flex",
                  alignItems: "center",
                  opacity: currentPage === totalPages ? 0.5 : 1,
                }}
              >
                <ChevronsRight size={15} />
              </button>
            </div>

            {/* Quick Page Jump Form */}
            <form
              onSubmit={handleJumpPage}
              style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginLeft: "0.5rem" }}
            >
              <input
                type="number"
                min={1}
                max={totalPages}
                placeholder="Page"
                value={jumpPageInput}
                onChange={(e) => setJumpPageInput(e.target.value)}
                style={{
                  width: "55px",
                  padding: "0.3rem 0.4rem",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color: "var(--text-primary)",
                  fontSize: "0.78rem",
                  textAlign: "center",
                  outline: "none",
                }}
              />
              <button
                type="submit"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color: "var(--text-secondary)",
                  padding: "0.3rem 0.6rem",
                  fontSize: "0.78rem",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
              >
                Go
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* ── Medium-Sized Hover Popover Card ── */}
      {hoverPopover && (
        <div
          ref={popoverRef}
          onMouseEnter={handlePopoverMouseEnter}
          onMouseLeave={handlePopoverMouseLeave}
          style={{
            position: "fixed",
            left: `${hoverPopover.x}px`,
            top: `${hoverPopover.y}px`,
            width: "480px",
            maxWidth: "92vw",
            zIndex: 9999,
            background: "rgba(18, 24, 38, 0.96)",
            backdropFilter: "blur(16px)",
            border: "1px solid var(--accent-primary)",
            borderRadius: "var(--radius-md)",
            boxShadow: "0 14px 40px rgba(0, 0, 0, 0.6), 0 0 20px rgba(99, 102, 241, 0.25)",
            padding: "1rem 1.25rem",
            animation: "fadeIn 0.15s ease-out",
            pointerEvents: "auto",
          }}
        >
          {/* Popover Header */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderBottom: "1px solid var(--border-subtle)",
              paddingBottom: "0.6rem",
              marginBottom: "0.75rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              {hoverPopover.type === "name" ? (
                <User size={16} color="var(--accent-primary)" />
              ) : (
                <Calendar size={16} color="var(--accent-primary)" />
              )}
              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                {hoverPopover.type === "name" ? "Name Cross-Validation" : "DOB Cross-Validation"}
              </span>
              <span
                style={{
                  fontSize: "0.7rem",
                  color: "var(--text-muted)",
                  background: "var(--bg-secondary)",
                  padding: "0.15rem 0.45rem",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                ID: {hoverPopover.driverId}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              {getFieldStatusBadge(hoverPopover.status)}
              <button
                onClick={handleCopyJson}
                title="Copy validation JSON"
                style={{
                  background: "transparent",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  color: copied ? "var(--status-matched)" : "var(--text-muted)",
                  padding: "0.25rem 0.4rem",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.25rem",
                  fontSize: "0.7rem",
                }}
              >
                {copied ? <Check size={12} /> : <Copy size={12} />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>

          {/* Medium Sized JSON Box */}
          <div
            style={{
              background: "#0d1117",
              border: "1px solid #30363d",
              borderRadius: "var(--radius-sm)",
              padding: "0.85rem",
              maxHeight: "260px",
              overflowY: "auto",
            }}
          >
            <pre
              style={{
                fontSize: "0.76rem",
                fontFamily: "Consolas, Monaco, 'Courier New', Courier, monospace",
                lineHeight: 1.45,
                color: "#e6edf3",
                margin: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {JSON.stringify(hoverPopover.jsonData, null, 2)}
            </pre>
          </div>

          {/* Micro Footer Indicator */}
          <div
            style={{
              marginTop: "0.6rem",
              fontSize: "0.7rem",
              color: "var(--text-muted)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>Pairwise comparison: Aadhaar ↔ PAN ↔ Licence</span>
            {hoverPopover.driverName && (
              <span style={{ color: "var(--text-secondary)" }}>
                Aadhaar Name: <strong>{hoverPopover.driverName}</strong>
              </span>
            )}
          </div>
        </div>
      )}

      {/* JSON Inspector Modal */}
      {selectedRecord && (
        <div
          style={{
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
            zIndex: 10000,
            padding: "2rem",
          }}
        >
          <div
            className="glass-panel"
            style={{
              maxWidth: "900px",
              width: "100%",
              maxHeight: "85vh",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              background: "var(--bg-secondary)",
            }}
          >
            <div
              style={{
                padding: "1.25rem 1.75rem",
                borderBottom: "1px solid var(--border-subtle)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>
                Record Detail: {selectedRecord.driver_id}
              </h3>
              <button
                onClick={() => setSelectedRecord(null)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                }}
              >
                <X size={20} />
              </button>
            </div>
            <div style={{ padding: "1.5rem", overflowY: "auto", flex: 1 }}>
              <pre
                style={{
                  fontSize: "0.8rem",
                  color: "var(--text-primary)",
                  background: "var(--bg-primary)",
                  padding: "1.25rem",
                  borderRadius: "var(--radius-md)",
                }}
              >
                {JSON.stringify(selectedRecord, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
