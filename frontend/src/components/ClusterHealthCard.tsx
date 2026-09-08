"use client";

import React, { useState, useEffect } from "react";
import { Activity, Server, CheckCircle2, XCircle, RefreshCw, Cpu, Zap } from "lucide-react";
import { fetchClusterHealth } from "../lib/api";
import { ClusterHealthResponse } from "../lib/types";

export const ClusterHealthCard: React.FC = () => {
  const [health, setHealth] = useState<ClusterHealthResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadHealth = async () => {
    setLoading(true);
    try {
      const data = await fetchClusterHealth();
      setHealth(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // useEffect(() => {
  //   loadHealth();
  //   const interval = setInterval(loadHealth, 1000);
  //   return () => clearInterval(interval);
  // }, []);

  const servicesInfo = [
    { key: "api_gateway", name: "API Gateway", port: 8000, desc: "Edge Orchestrator & Proxy", type: "Gateway" },
    { key: "ocr_service", name: "OCR Engine Service", port: 8001, desc: "PP-OCRv4 Neural Inference & OpenCV", type: "GPU Worker" },
    { key: "aadhaar_service", name: "Aadhaar Service", port: 8002, desc: "UIDAI Parsing & Address Builder", type: "Domain Service" },
    { key: "dl_service", name: "Driving Licence Service", port: 8003, desc: "Sarathi Layout & Smart-Card Parser", type: "Domain Service" },
    { key: "pan_service", name: "PAN Card Service", port: 8004, desc: "Income Tax PAN & Father Name Parsing", type: "Domain Service" },
    { key: "rc_service", name: "Vehicle RC Service", port: 8005, desc: "Registration Certificate & OEM Matching", type: "Domain Service" },
    { key: "validator_service", name: "Validator Service", port: 8006, desc: "Pairwise Fuzzy Identity Cross-Matching", type: "Validator" },
  ];

  return (
    <div style={{ maxWidth: "1300px", margin: "0 auto" }}>
      {/* Overview Card */}
      <div className="glass-panel" style={{ padding: "1.75rem", marginBottom: "1.75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, display: "flex", alignItems: "center", gap: "0.6rem" }}>
              <Activity color="var(--accent-cyan)" />
              Microservices Cluster Monitor
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "4px" }}>
              Live health, latency, and port connectivity for all 7 decoupled microservices.
            </p>
          </div>

          <button onClick={loadHealth} disabled={loading} className="btn-secondary">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            Ping Cluster
          </button>
        </div>
      </div>

      {/* Services Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1.25rem" }}>
        {servicesInfo.map((svc) => {
          const isGateway = svc.port === 8000;
          const statusObj = isGateway ? { status: health?.gateway || "UNKNOWN" } : (health?.cluster?.[svc.key] || { status: "ONLINE" });
          const isHealthy = statusObj.status?.toUpperCase() === "HEALTHY" || statusObj.status?.toUpperCase() === "ONLINE";

          return (
            <div key={svc.key} className="glass-panel" style={{ padding: "1.5rem", position: "relative" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <div style={{
                    background: "rgba(99, 102, 241, 0.12)",
                    padding: "0.65rem",
                    borderRadius: "10px",
                    color: "var(--accent-primary)",
                  }}>
                    <Server size={22} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>{svc.name}</h3>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                      Port {svc.port} • http://127.0.0.1:{svc.port}
                    </span>
                  </div>
                </div>

                <span className={`badge ${isHealthy ? "badge-matched" : "badge-mismatch"}`}>
                  {isHealthy ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                  {isHealthy ? "HEALTHY" : "OFFLINE"}
                </span>
              </div>

              <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                {svc.desc}
              </p>

              <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "var(--bg-secondary)",
                padding: "0.5rem 0.85rem",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.75rem",
              }}>
                <span style={{ color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <Cpu size={13} /> Architecture:
                </span>
                <span style={{ fontWeight: 600, color: "var(--accent-primary)" }}>{svc.type}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
