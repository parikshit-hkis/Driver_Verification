"use client";

import React from "react";
import { ShieldCheck, Layers, Database, Activity, Sparkles, Sun, Moon } from "lucide-react";

interface HeaderProps {
  activeTab: "single" | "batch" | "records" | "cluster";
  setActiveTab: (tab: "single" | "batch" | "records" | "cluster") => void;
  clusterOnline: boolean;
  theme: "dark" | "light";
  toggleTheme: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  clusterOnline,
  theme,
  toggleTheme,
}) => {
  return (
    <header style={{
      borderBottom: "1px solid var(--border-subtle)",
      background: "var(--header-bg)",
      backdropFilter: "blur(20px)",
      position: "sticky",
      top: 0,
      zIndex: 50,
      padding: "1rem 2rem",
      transition: "background 0.25s ease",
    }}>
      <div style={{
        maxWidth: "1400px",
        margin: "0 auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "1rem",
      }}>
        {/* Brand Logo & Name */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
          <div style={{
            width: "42px",
            height: "42px",
            borderRadius: "12px",
            background: "var(--accent-gradient)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "var(--shadow-glow)",
          }}>
            <ShieldCheck size={26} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <h1 style={{ fontSize: "1.25rem", fontWeight: 800, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                Driver<span style={{ color: "var(--accent-cyan)" }}>Verify</span>
              </h1>
              <span style={{
                background: "rgba(99, 102, 241, 0.15)",
                color: "var(--accent-primary)",
                border: "1px solid var(--border-accent)",
                fontSize: "0.68rem",
                fontWeight: 700,
                padding: "0.15rem 0.45rem",
                borderRadius: "6px",
              }}>
                v3.0 MICROSERVICES
              </span>
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "2px" }}>
              Enterprise Multi-Document KYC
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{
          display: "flex",
          background: "var(--bg-secondary)",
          padding: "0.3rem",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--border-subtle)",
          gap: "0.25rem",
          boxShadow: "var(--shadow-card)",
        }}>
          <button
            onClick={() => setActiveTab("single")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.55rem 1rem",
              borderRadius: "8px",
              fontSize: "0.85rem",
              fontWeight: 600,
              border: "none",
              cursor: "pointer",
              transition: "all 0.2s ease",
              background: activeTab === "single" ? "var(--accent-primary)" : "transparent",
              color: activeTab === "single" ? "#ffffff" : "var(--text-secondary)",
            }}
          >
            <Sparkles size={16} />
            Single Verification
          </button>

          <button
            onClick={() => setActiveTab("batch")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.55rem 1rem",
              borderRadius: "8px",
              fontSize: "0.85rem",
              fontWeight: 600,
              border: "none",
              cursor: "pointer",
              transition: "all 0.2s ease",
              background: activeTab === "batch" ? "var(--accent-primary)" : "transparent",
              color: activeTab === "batch" ? "#ffffff" : "var(--text-secondary)",
            }}
          >
            <Layers size={16} />
            Bulk Batch Runner
          </button>

          <button
            onClick={() => setActiveTab("records")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.55rem 1rem",
              borderRadius: "8px",
              fontSize: "0.85rem",
              fontWeight: 600,
              border: "none",
              cursor: "pointer",
              transition: "all 0.2s ease",
              background: activeTab === "records" ? "var(--accent-primary)" : "transparent",
              color: activeTab === "records" ? "#ffffff" : "var(--text-secondary)",
            }}
          >
            <Database size={16} />
            Verified Records
          </button>

          <button
            onClick={() => setActiveTab("cluster")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.55rem 1rem",
              borderRadius: "8px",
              fontSize: "0.85rem",
              fontWeight: 600,
              border: "none",
              cursor: "pointer",
              transition: "all 0.2s ease",
              background: activeTab === "cluster" ? "var(--accent-primary)" : "transparent",
              color: activeTab === "cluster" ? "#ffffff" : "var(--text-secondary)",
            }}
          >
            <Activity size={16} />
            Cluster Health
          </button>
        </nav>

        {/* Right Controls: Cluster Dot & Theme Toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {/* Cluster Status Dot */}
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "0.6rem",
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-subtle)",
            padding: "0.45rem 0.85rem",
            borderRadius: "var(--radius-full)",
            boxShadow: "var(--shadow-card)",
          }}>
            <div
              className="pulse-indicator"
              style={{
                background: clusterOnline ? "var(--status-matched)" : "var(--status-mismatch)",
                boxShadow: clusterOnline ? "0 0 10px var(--status-matched)" : "0 0 10px var(--status-mismatch)",
              }}
            />
            <span style={{ fontSize: "0.78rem", fontWeight: 600, color: clusterOnline ? "var(--status-matched)" : "var(--status-mismatch)" }}>
              {clusterOnline ? "Cluster Online" : "Gateway Offline"}
            </span>
          </div>

          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="theme-toggle-btn"
            title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
            aria-label="Toggle Theme"
          >
            {theme === "dark" ? <Sun size={18} color="#fbbf24" /> : <Moon size={18} color="#6366f1" />}
          </button>
        </div>
      </div>
    </header>
  );
};
