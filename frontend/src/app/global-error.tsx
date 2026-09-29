"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global Layout Error:", error);
  }, [error]);

  return (
    <html lang="en">
      <head>
        <title>Application Error — NexMarket AI</title>
      </head>
      <body style={{ margin: 0, fontFamily: "system-ui, -apple-system, sans-serif", background: "#f4f8fb", color: "#1e293b", display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div style={{ maxWidth: 480, margin: "0 auto", padding: 32, background: "#ffffff", borderRadius: 16, border: "1px solid #dce8ef", boxShadow: "0 4px 20px rgba(0,0,0,0.06)", textAlign: "center" }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: "#fee2e2", color: "#dc2626", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 24, marginBottom: 16 }}>
            ⚠️
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 8px 0" }}>Application Error</h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: "0 0 24px 0", lineHeight: 1.5 }}>
            {error.message || "An unexpected error occurred in the application shell."}
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button
              onClick={() => reset()}
              style={{ background: "#3b82f6", color: "#ffffff", border: "none", borderRadius: 10, padding: "10px 20px", fontSize: 14, fontWeight: 600, cursor: "pointer" }}
            >
              Try Again
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{ background: "#f1f5f9", color: "#334155", border: "1px solid #cbd5e1", borderRadius: 10, padding: "10px 20px", fontSize: 14, fontWeight: 600, cursor: "pointer" }}
            >
              Reload Page
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
