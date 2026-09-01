// RevenueShield AI — Phase 6 frontend types.
//
// Mirror backend/app/schemas/decision.py and schemas/audit.py field-for-
// field. No decision logic lives here or anywhere in the frontend — these
// are pure data shapes for what the existing Phase 4/5 API already
// returns.

export type Action = "do_nothing" | "retry" | "reminder" | "recovery_link";

export const ACTIONS: Action[] = ["do_nothing", "retry", "reminder", "recovery_link"];

export const ACTION_LABELS: Record<Action, string> = {
  do_nothing: "Do nothing",
  retry: "Retry",
  reminder: "Send reminder",
  recovery_link: "Send recovery link",
};

export type CustomerType = "new" | "existing";
export type PaymentMethod = "card" | "upi" | "netbanking" | "wallet";
export type MerchantCategory =
  | "ecommerce"
  | "saas"
  | "education"
  | "travel"
  | "healthcare"
  | "subscription";

export interface MerchantConstraintsRequest {
  allowed_actions?: Action[];
  max_retry_count?: number;
}

export interface DecisionRequest {
  transaction_id?: string;
  customer_id?: string;
  customer_type: CustomerType;
  payment_method: PaymentMethod;
  merchant_category: MerchantCategory;
  customer_tenure_days: number;
  payment_amount: number;
  previous_payment_count: number;
  previous_success_count: number;
  previous_failure_count: number;
  previous_retry_count: number;
  days_since_last_payment: number;
  constraints?: MerchantConstraintsRequest;
}

export interface ConfidenceResponse {
  level: "low" | "medium" | "standard";
  basis: string;
  method: string;
}

export interface ConstraintsAppliedResponse {
  allowed_actions: string[];
  max_retry_count: number | null;
  removed_by_constraint: Record<string, string>;
}

export interface DecisionResponse {
  transaction_id: string | null;
  customer_id: string | null;
  selected_action: Action;
  predicted_failure_risk: number;
  action_success_probabilities: Record<Action, number>;
  expected_revenue: Record<Action, number>;
  permitted_actions: string[];
  constraints_applied: ConstraintsAppliedResponse;
  explanation: string;
  confidence: ConfidenceResponse;
  causal_disclaimer: string;
}

export interface AuditRecordResponse extends DecisionResponse {
  id: number;
  created_at: string;
}

export interface AuditRecordListResponse {
  count: number;
  limit: number;
  records: AuditRecordResponse[];
}

export interface ApiError {
  detail: string | { msg: string; loc: (string | number)[] }[];
}
