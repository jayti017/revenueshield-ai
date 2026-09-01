// RevenueShield AI — Phase 6: renders a decision result (fresh or stored).
// Pure display — every number/string here comes directly from the
// existing backend response; nothing is computed or reinterpreted here.

import type { Action, DecisionResponse } from "../types";
import { ACTIONS, ACTION_LABELS } from "../types";

const CONFIDENCE_STYLES: Record<string, string> = {
  low: "bg-red-100 text-red-800 border-red-300",
  medium: "bg-amber-100 text-amber-800 border-amber-300",
  standard: "bg-green-100 text-green-800 border-green-300",
};

function formatCurrency(amount: number): string {
  return `Rs ${amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

interface Props {
  result: DecisionResponse;
  meta?: { id: number; created_at: string };
}

export default function DecisionResultCard({ result, meta }: Props) {
  const maxRevenue = Math.max(...Object.values(result.expected_revenue));

  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm text-slate-500">Selected action</p>
          <h3 className="text-2xl font-semibold text-slate-900">
            {ACTION_LABELS[result.selected_action]}
          </h3>
          {(result.transaction_id || result.customer_id) && (
            <p className="text-xs text-slate-400 mt-1">
              {result.transaction_id && <>transaction_id: {result.transaction_id} </>}
              {result.customer_id && <>customer_id: {result.customer_id}</>}
            </p>
          )}
          {meta && (
            <p className="text-xs text-slate-400">
              #{meta.id} &middot; {new Date(meta.created_at).toLocaleString()}
            </p>
          )}
        </div>
        <span
          className={`px-3 py-1 rounded-full text-xs font-medium border ${
            CONFIDENCE_STYLES[result.confidence.level] ?? "bg-slate-100 text-slate-800 border-slate-300"
          }`}
        >
          {result.confidence.level.toUpperCase()} confidence
        </span>
      </div>

      <div>
        <p className="text-sm text-slate-500 mb-1">
          Predicted payment failure risk (pre-action)
        </p>
        <div className="w-full bg-slate-100 rounded h-2">
          <div
            className="bg-slate-500 h-2 rounded"
            style={{ width: `${result.predicted_failure_risk * 100}%` }}
          />
        </div>
        <p className="text-xs text-slate-500 mt-1">
          {formatPercent(result.predicted_failure_risk)}
        </p>
      </div>

      <div>
        <p className="text-sm text-slate-500 mb-2">
          Predicted success probability &amp; expected revenue by action
        </p>
        <div className="space-y-3">
          {ACTIONS.map((action: Action) => {
            const isSelected = action === result.selected_action;
            const isPermitted = result.permitted_actions.includes(action);
            const removedReason = result.constraints_applied.removed_by_constraint[action];
            const revenue = result.expected_revenue[action];
            const probability = result.action_success_probabilities[action];
            const widthPct = maxRevenue > 0 ? (revenue / maxRevenue) * 100 : 0;

            return (
              <div key={action} className={!isPermitted ? "opacity-50" : ""}>
                <div className="flex justify-between text-sm mb-1">
                  <span className={isSelected ? "font-semibold text-slate-900" : "text-slate-700"}>
                    {ACTION_LABELS[action]}
                    {isSelected && " \u2713"}
                  </span>
                  <span className="text-slate-600">
                    {formatCurrency(revenue)} &middot; {formatPercent(probability)} predicted success
                  </span>
                </div>
                <div className="w-full bg-slate-100 rounded h-2.5">
                  <div
                    className={`h-2.5 rounded ${isSelected ? "bg-emerald-500" : "bg-slate-400"}`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
                {removedReason && (
                  <p className="text-xs text-red-500 mt-1">Excluded: {removedReason}</p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <p className="text-sm text-slate-500 mb-1">Explanation</p>
        <p className="text-sm text-slate-800 leading-relaxed">{result.explanation}</p>
      </div>

      <div className="text-xs text-slate-400 border-t border-slate-100 pt-3">
        <p className="mb-1">
          <span className="font-medium">Confidence basis:</span> {result.confidence.basis}
        </p>
        <p className="mb-1">
          <span className="font-medium">Confidence method:</span> {result.confidence.method}
        </p>
        <p className="italic">{result.causal_disclaimer}</p>
      </div>
    </div>
  );
}
