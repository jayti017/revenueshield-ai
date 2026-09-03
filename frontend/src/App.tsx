// RevenueShield AI — Phase 8 top-level app.

import { useEffect, useState } from "react";
import DecisionForm from "./components/DecisionForm";
import DecisionResultCard from "./components/DecisionResultCard";
import DecisionHistory from "./components/DecisionHistory";
import TestPayment from "./components/TestPayment";
import { checkHealth, postDecision } from "./api";
import type { DecisionRequest, DecisionResponse } from "./types";

type Tab = "new" | "payment" | "history";

export default function App() {
  const [tab, setTab] = useState<Tab>("new");
  const [result, setResult] = useState<DecisionResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<"checking" | "ok" | "unreachable">("checking");

  useEffect(() => {
    checkHealth()
      .then(() => setBackendStatus("ok"))
      .catch(() => setBackendStatus("unreachable"));
  }, []);

  async function handleSubmit(payload: DecisionRequest) {
    setIsSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const response = await postDecision(payload);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get a decision.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">RevenueShield AI</h1>
            <p className="text-xs text-slate-500">Explainable Revenue Recovery Decision Engine</p>
          </div>
          <span
            className={`text-xs px-2.5 py-1 rounded-full ${
              backendStatus === "ok"
                ? "bg-green-100 text-green-800"
                : backendStatus === "unreachable"
                  ? "bg-red-100 text-red-800"
                  : "bg-slate-100 text-slate-600"
            }`}
          >
            {backendStatus === "ok"
              ? "Backend connected"
              : backendStatus === "unreachable"
                ? "Backend unreachable"
                : "Checking backend..."}
          </span>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <div className="flex gap-2 border-b border-slate-200">
          <button
            onClick={() => setTab("new")}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === "new" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-500"
            }`}
          >
            New decision
          </button>

          <button
            onClick={() => setTab("payment")}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === "payment" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-500"
            }`}
          >
            Test payment
          </button>

          <button
            onClick={() => setTab("history")}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === "history" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-500"
            }`}
          >
            Recent decisions
          </button>
        </div>

        {tab === "new" && (
          <div className="space-y-6">
            <DecisionForm onSubmit={handleSubmit} isSubmitting={isSubmitting} />
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-4">
                {error}
              </div>
            )}
            {result && <DecisionResultCard result={result} />}
          </div>
        )}

        {tab === "payment" && <TestPayment />}
        {tab === "history" && <DecisionHistory />}
      </main>
    </div>
  );
}
