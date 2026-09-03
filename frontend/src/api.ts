// RevenueShield AI — Phase 8 frontend API client.
// Thin fetch wrappers around the FastAPI endpoints. No decision logic lives here.

import type {
  AuditRecordListResponse,
  AuditRecordResponse,
  DecisionRequest,
  DecisionResponse,
  ApiError,
  PaymentOrderResponse,
  PaymentVerifyRequest,
  PaymentVerifyResponse,
} from "./types";

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body: ApiError = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((e) => `${e.loc.join(".")}: ${e.msg}`)
        .join("; ");
    }
    return `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function checkHealth(): Promise<{ status: string; phase: string }> {
  const response = await fetch("/health");
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  return response.json();
}

export async function postDecision(payload: DecisionRequest): Promise<DecisionResponse> {
  const response = await fetch("/api/v1/decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  return response.json();
}

export async function getRecentDecisions(limit = 20): Promise<AuditRecordListResponse> {
  const response = await fetch(`/api/v1/decisions?limit=${limit}`);
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  return response.json();
}

export async function getDecisionByTransactionId(
  transactionId: string,
): Promise<AuditRecordResponse> {
  const response = await fetch(`/api/v1/decisions/${encodeURIComponent(transactionId)}`);
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  return response.json();
}

export async function createPaymentOrder(
  payload: DecisionRequest,
): Promise<PaymentOrderResponse> {
  const response = await fetch("/api/v1/payments/order", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  return response.json();
}

export async function verifyPayment(
  payload: PaymentVerifyRequest,
): Promise<PaymentVerifyResponse> {
  const response = await fetch("/api/v1/payments/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  return response.json();
}
