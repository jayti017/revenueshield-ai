// RevenueShield AI — Phase 8 frontend types.
// Pure data shapes matching the backend API. No decision logic lives here.

export type Action = "do_nothing" | "retry" | "reminder" | "recovery_link";

export const ACTIONS: Action[] = [
  "do_nothing",
  "retry",
  "reminder",
  "recovery_link",
];

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

export interface SafetyInfoResponse {
  triggered: boolean;
  reasons: string[];
  original_selected_action: Action;
  final_selected_action: Action;
  overridden: boolean;
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
  safety: SafetyInfoResponse;
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

export interface PaymentOrderResponse {
  razorpay_order_id: string;
  razorpay_key_id: string;
  amount: number;
  currency: string;
  receipt: string | null;
  decision: DecisionResponse;
}

export interface PaymentVerifyRequest {
  razorpay_order_id: string;
  razorpay_payment_id?: string;
  razorpay_signature?: string;
}

export interface PaymentVerifyResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string | null;
  payment_status: string;
  signature_verified: boolean;
  amount: number;
  decision: DecisionResponse;
}
