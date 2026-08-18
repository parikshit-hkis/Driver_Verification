"use client";

import React, { useState, useEffect } from "react";
import { Header } from "../components/Header";
import { SingleVerification } from "../components/SingleVerification";
import { BatchRunner } from "../components/BatchRunner";
import { HistoricalRecords } from "../components/HistoricalRecords";
import { ClusterHealthCard } from "../components/ClusterHealthCard";
import { fetchClusterHealth } from "../lib/api";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<"single" | "batch" | "records" | "cluster">("single");
  const [clusterOnline, setClusterOnline] = useState<boolean>(true);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  // Initialize theme from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("app_theme") as "dark" | "light" | null;
    if (saved) {
      setTheme(saved);
      document.documentElement.setAttribute("data-theme", saved);
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("app_theme", nextTheme);
    document.documentElement.setAttribute("data-theme", nextTheme);
  };

  // Run cluster check once on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        await fetchClusterHealth();
        setClusterOnline(true);
      } catch {
        setClusterOnline(false);
      }
    };
    checkHealth();
  }, []);

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        clusterOnline={clusterOnline}
        theme={theme}
        toggleTheme={toggleTheme}
      />

      <main style={{ flex: 1, padding: "2.5rem 2rem", maxWidth: "1400px", margin: "0 auto", width: "100%" }}>
        {activeTab === "single" && <SingleVerification />}
        {activeTab === "batch" && <BatchRunner />}
        {activeTab === "records" && <HistoricalRecords />}
        {activeTab === "cluster" && <ClusterHealthCard />}
      </main>

      <footer style={{
        borderTop: "1px solid var(--border-subtle)",
        padding: "1.5rem 2rem",
        textAlign: "center",
        color: "var(--text-muted)",
        fontSize: "0.78rem",
        background: "var(--bg-primary)",
      }}>
        <div style={{ maxWidth: "1400px", margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <span>Enterprise Driver KYC & Verification Microservices Suite v3.0</span>
          <span>FastAPI • PP-OCRv4 • Next.js 14 • TypeScript</span>
        </div>
      </footer>
    </div>
  );
}
