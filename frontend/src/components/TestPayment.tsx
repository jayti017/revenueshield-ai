// RevenueShield AI — Phase 8: Razorpay TEST-MODE payment flow.

import { useRef, useState } from "react";
import DecisionForm from "./DecisionForm";
import DecisionResultCard from "./DecisionResultCard";
import { createPaymentOrder, verifyPayment } from "../api";
import type { DecisionRequest } from "../types";
import type { PaymentOrderResponse, PaymentVerifyResponse } from "../types";

interface RazorpaySuccessResponse {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

interface RazorpayPaymentFailedResponse {
  error?: {
    code?: string;
    description?: string;
    source?: string;
    step?: string;
    reason?: string;
    metadata?: {
      order_id?: string;
      payment_id?: string;
    };
  };
}

interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (response: RazorpaySuccessResponse) => void;
  modal?: { ondismiss?: () => void };
  theme?: { color?: string };
}

interface RazorpayInstance {
  open: () => void;
  on: (
    event: "payment.failed",
    handler: (response: RazorpayPaymentFailedResponse) => void,
  ) => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

export default function TestPayment() {
  const [order, setOrder] = useState<PaymentOrderResponse | null>(null);
  const [verification, setVerification] = useState<PaymentVerifyResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const verificationStarted = useRef(false);

  async function verifyOnce(payload: Parameters<typeof verifyPayment>[0]) {
    if (verificationStarted.current) return;
    verificationStarted.current = true;
    setIsVerifying(true);

    try {
      const result = await verifyPayment(payload);
      setVerification(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment verification failed.");
    } finally {
      setIsVerifying(false);
    }
  }

  async function handleCreatePayment(payload: DecisionRequest) {
    setIsCreating(true);
    setError(null);
    setOrder(null);
    setVerification(null);
    verificationStarted.current = false;

    try {
      if (!window.Razorpay) {
        throw new Error(
          "Razorpay Checkout.js could not be loaded. Check your internet connection and reload the page.",
        );
      }

      const created = await createPaymentOrder(payload);
      setOrder(created);

      const razorpay = new window.Razorpay({
        key: created.razorpay_key_id,
        amount: Math.round(created.amount * 100),
        currency: created.currency,
        name: "RevenueShield AI",
        description: "RevenueShield AI TEST-MODE payment",
        order_id: created.razorpay_order_id,

        handler: (response) => {
          void verifyOnce({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
        },

        modal: {
          ondismiss: () => {
            void verifyOnce({
              razorpay_order_id: created.razorpay_order_id,
            });
          },
        },
      });

      razorpay.on("payment.failed", (response) => {
        const paymentId = response.error?.metadata?.payment_id;

        if (paymentId) {
          void verifyOnce({
            razorpay_order_id: created.razorpay_order_id,
            razorpay_payment_id: paymentId,
          });
        } else {
          void verifyOnce({
            razorpay_order_id: created.razorpay_order_id,
          });
        }
      });

      razorpay.open();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not create the Razorpay test order.",
      );
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-900">
        <strong>Razorpay TEST MODE only.</strong> This flow is for the hackathon demo and does not use real money.
      </div>

      <DecisionForm
        onSubmit={handleCreatePayment}
        isSubmitting={isCreating}
        submitLabel="Create test payment & open Razorpay"
      />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-4">
          {error}
        </div>
      )}

      {order && (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 space-y-3">
          <h2 className="text-lg font-semibold text-slate-900">Razorpay test order</h2>
          <p className="text-sm text-slate-600">Order ID: {order.razorpay_order_id}</p>
          <p className="text-sm text-slate-600">
            Amount: Rs {order.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
          </p>
          <p className="text-sm text-slate-600">
            RevenueShield recommendation: <strong>{order.decision.selected_action.replace(/_/g, " ")}</strong>
          </p>
        </div>
      )}

      {order && <DecisionResultCard result={order.decision} />}

      {verification && (
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6 space-y-3">
          <h2 className="text-lg font-semibold text-slate-900">Payment result</h2>
          <p className="text-sm text-slate-700">
            Status: <strong>{verification.payment_status}</strong>
          </p>
          <p className="text-sm text-slate-700">
            Signature verified: <strong>{verification.signature_verified ? "Yes" : "No"}</strong>
          </p>
          {verification.razorpay_payment_id && (
            <p className="text-sm text-slate-600">Payment ID: {verification.razorpay_payment_id}</p>
          )}
          {isVerifying && <p className="text-xs text-slate-500">Verifying with Razorpay...</p>}
        </div>
      )}
    </div>
  );
}
