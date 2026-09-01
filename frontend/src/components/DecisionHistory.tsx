// RevenueShield AI — Phase 6: decision history view.
// Reads from the EXISTING Phase 5 endpoints (GET /api/v1/decisions,
// GET /api/v1/decisions/{transaction_id}) only. No new backend behavior.

import { useEffect, useState } from "react";
import { getRecentDecisions } from "../api";
import type { AuditRecordResponse } from "../types";
import { ACTION_LABELS } from "../types";
import DecisionResultCard from "./DecisionResultCard";

export default function DecisionHistory() {
  const [records, setRecords] = useState<AuditRecordResponse[]>([]);
  const [selected, setSelected] = useState<AuditRecordResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await getRecentDecisions(20);
      setRecords(response.records);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load decision history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">Recent decisions</h2>
        <button
          onClick={load}
          className="text-sm text-slate-600 border border-slate-300 rounded px-3 py-1.5 hover:bg-slate-100"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="text-sm text-slate-500">Loading...</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {!loading && !error && records.length === 0 && (
        <p className="text-sm text-slate-500">
          No decisions recorded yet. Submit one from the "New decision" tab.
        </p>
      )}

      {records.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">Time</th>
                <th className="px-4 py-2 font-medium">Transaction</th>
                <th className="px-4 py-2 font-medium">Selected action</th>
                <th className="px-4 py-2 font-medium">Confidence</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.id} className="border-t border-slate-100">
                  <td className="px-4 py-2 text-slate-500">
                    {new Date(record.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-slate-700">{record.transaction_id ?? "—"}</td>
                  <td className="px-4 py-2 text-slate-900">
                    {ACTION_LABELS[record.selected_action]}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{record.confidence.level}</td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => setSelected(record)}
                      className="text-slate-700 underline text-xs"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-10">
          <div className="max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex justify-end mb-2">
              <button
                onClick={() => setSelected(null)}
                className="bg-white rounded px-3 py-1 text-sm text-slate-700 shadow"
              >
                Close
              </button>
            </div>
            <DecisionResultCard
              result={selected}
              meta={{ id: selected.id, created_at: selected.created_at }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
