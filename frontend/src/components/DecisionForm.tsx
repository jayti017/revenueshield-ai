// RevenueShield AI — Phase 6: new-decision form.
// Collects exactly the fields DecisionRequest (backend/app/schemas/
// decision.py) accepts. Client-side constraints mirror the API's own
// validation (Pydantic still re-validates server-side — this is a UX
// convenience, not a trust boundary).

import { useState } from "react";
import type { Action, CustomerType, DecisionRequest, MerchantCategory, PaymentMethod } from "../types";
import { ACTIONS, ACTION_LABELS } from "../types";

const DEFAULT_FORM: DecisionRequest = {
  transaction_id: "",
  customer_id: "",
  customer_type: "existing",
  payment_method: "card",
  merchant_category: "saas",
  customer_tenure_days: 240,
  payment_amount: 4999,
  previous_payment_count: 8,
  previous_success_count: 5,
  previous_failure_count: 3,
  previous_retry_count: 2,
  days_since_last_payment: 31,
};

interface Props {
  onSubmit: (payload: DecisionRequest) => void;
  isSubmitting: boolean;
}

export default function DecisionForm({ onSubmit, isSubmitting }: Props) {
  const [form, setForm] = useState<DecisionRequest>(DEFAULT_FORM);
  const [allowedActions, setAllowedActions] = useState<Set<Action>>(new Set(ACTIONS));
  const [maxRetryCount, setMaxRetryCount] = useState<string>("");

  function updateField<K extends keyof DecisionRequest>(key: K, value: DecisionRequest[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function toggleAction(action: Action) {
    setAllowedActions((prev) => {
      const next = new Set(prev);
      if (next.has(action)) next.delete(action);
      else next.add(action);
      return next;
    });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const payload: DecisionRequest = {
      ...form,
      transaction_id: form.transaction_id?.trim() || undefined,
      customer_id: form.customer_id?.trim() || undefined,
    };

    const allActionsAllowed = allowedActions.size === ACTIONS.length;
    const retryLimitSet = maxRetryCount !== "";
    if (!allActionsAllowed || retryLimitSet) {
      payload.constraints = {
        ...(allActionsAllowed ? {} : { allowed_actions: Array.from(allowedActions) }),
        ...(retryLimitSet ? { max_retry_count: Number(maxRetryCount) } : {}),
      };
    }

    onSubmit(payload);
  }

  const customerTypes: CustomerType[] = ["existing", "new"];
  const paymentMethods: PaymentMethod[] = ["card", "upi", "netbanking", "wallet"];
  const merchantCategories: MerchantCategory[] = [
    "ecommerce",
    "saas",
    "education",
    "travel",
    "healthcare",
    "subscription",
  ];

  return (
    <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-slate-600 mb-1">Transaction ID (optional)</label>
          <input
            type="text"
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.transaction_id}
            onChange={(e) => updateField("transaction_id", e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Customer ID (optional)</label>
          <input
            type="text"
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.customer_id}
            onChange={(e) => updateField("customer_id", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm text-slate-600 mb-1">Customer type</label>
          <select
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.customer_type}
            onChange={(e) => updateField("customer_type", e.target.value as CustomerType)}
          >
            {customerTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Payment method</label>
          <select
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.payment_method}
            onChange={(e) => updateField("payment_method", e.target.value as PaymentMethod)}
          >
            {paymentMethods.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-slate-600 mb-1">Merchant category</label>
          <select
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.merchant_category}
            onChange={(e) => updateField("merchant_category", e.target.value as MerchantCategory)}
          >
            {merchantCategories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Payment amount (Rs)</label>
          <input
            type="number"
            min={0.01}
            step="0.01"
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.payment_amount}
            onChange={(e) => updateField("payment_amount", Number(e.target.value))}
            required
          />
        </div>

        <div>
          <label className="block text-sm text-slate-600 mb-1">Customer tenure (days)</label>
          <input
            type="number"
            min={0}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.customer_tenure_days}
            onChange={(e) => updateField("customer_tenure_days", Number(e.target.value))}
            required
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Days since last payment</label>
          <input
            type="number"
            min={0}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.days_since_last_payment}
            onChange={(e) => updateField("days_since_last_payment", Number(e.target.value))}
            required
          />
        </div>

        <div>
          <label className="block text-sm text-slate-600 mb-1">Previous payment count</label>
          <input
            type="number"
            min={0}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.previous_payment_count}
            onChange={(e) => updateField("previous_payment_count", Number(e.target.value))}
            required
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Previous retry count</label>
          <input
            type="number"
            min={0}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.previous_retry_count}
            onChange={(e) => updateField("previous_retry_count", Number(e.target.value))}
            required
          />
        </div>

        <div>
          <label className="block text-sm text-slate-600 mb-1">Previous success count</label>
          <input
            type="number"
            min={0}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.previous_success_count}
            onChange={(e) => updateField("previous_success_count", Number(e.target.value))}
            required
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Previous failure count</label>
          <input
            type="number"
            min={0}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={form.previous_failure_count}
            onChange={(e) => updateField("previous_failure_count", Number(e.target.value))}
            required
          />
        </div>
      </div>

      <fieldset className="border border-slate-200 rounded p-4">
        <legend className="text-sm font-medium text-slate-700 px-1">
          Merchant constraints (optional)
        </legend>
        <div className="flex flex-wrap gap-4 mb-3">
          {ACTIONS.map((action) => (
            <label key={action} className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={allowedActions.has(action)}
                onChange={() => toggleAction(action)}
              />
              {ACTION_LABELS[action]}
            </label>
          ))}
        </div>
        <div className="max-w-xs">
          <label className="block text-sm text-slate-600 mb-1">
            Max retry count (blank = no limit)
          </label>
          <input
            type="number"
            min={0}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm"
            value={maxRetryCount}
            onChange={(e) => setMaxRetryCount(e.target.value)}
          />
        </div>
      </fieldset>

      <button
        type="submit"
        disabled={isSubmitting}
        className="bg-slate-900 text-white text-sm font-medium px-5 py-2.5 rounded hover:bg-slate-700 disabled:opacity-50"
      >
        {isSubmitting ? "Deciding..." : "Get decision"}
      </button>
    </form>
  );
}
