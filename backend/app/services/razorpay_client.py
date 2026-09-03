"""
RevenueShield AI — Phase 8: Razorpay TEST-MODE client.

Thin wrapper around Razorpay's REST API (Orders + Payments) using the
EXISTING httpx dependency (already in backend/requirements.txt since
Phase 1) with HTTP Basic Auth — the standard `razorpay` PyPI SDK is
deliberately NOT added, since httpx + stdlib hmac/hashlib already cover
everything Phase 8 needs (create an order, fetch a payment, verify a
payment signature).

TEST MODE ONLY. Razorpay's test-mode key ids are prefixed `rzp_test_...`;
this module does not distinguish test vs. live keys itself (Razorpay's own
API does that based on which key you configure) — it is the operator's
responsibility to put TEST keys in backend/.env, exactly as
backend/.env.example already says. No real money moves through test-mode
credentials.

Credentials: read from the RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET
environment variables (via python-dotenv, already a dependency, loading
backend/.env if present). NEVER hard-coded, NEVER logged, NEVER returned
in any response — see get_public_key_id() vs. the deliberately-private
_get_credentials().

This file contains no decision-making, audit, or safety logic — it only
talks to Razorpay's API and verifies signatures.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/app/services/razorpay_client.py -> backend/
load_dotenv(BACKEND_DIR / ".env", override=True)  # no-op if the file doesn't exist — harmless in dev/test
RAZORPAY_API_BASE = "https://api.razorpay.com/v1"
REQUEST_TIMEOUT_SECONDS = 10.0

# Razorpay orders/payments are amounts in the smallest currency unit
# (paise for INR) — 1 rupee = 100 paise.
PAISE_PER_RUPEE = 100

# Razorpay truncates/rejects receipts longer than this.
MAX_RECEIPT_LENGTH = 40


class RazorpayConfigurationError(RuntimeError):
    """Raised when RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are missing or
    empty. A subclass of RuntimeError so callers can catch it distinctly
    from a genuine Razorpay API error.
    """


class RazorpayAPIError(RuntimeError):
    """Raised when Razorpay's API returns an error response, or the
    request to it fails outright (network error, timeout, malformed
    response). Carries a sanitized, safe-to-display description — never
    the request's Authorization header or any credential.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _get_credentials() -> tuple[str, str]:
    """Reads credentials fresh from the environment on every call (not
    cached at import time) — the same "resolve at call time, not import
    time" pattern database.py uses for DEFAULT_DB_PATH, so tests can set/
    unset environment variables per-test via monkeypatch without import-
    order issues.

    Deliberately private (leading underscore): the key SECRET must never
    leave this module. See get_public_key_id() for the one credential that
    is safe to hand to the frontend (Razorpay's own Checkout.js requires
    the public key id client-side by design).
    """
    key_id = os.environ.get("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()

    if not key_id or not key_secret:
        raise RazorpayConfigurationError(
            "Razorpay is not configured on this server. Set RAZORPAY_KEY_ID "
            "and RAZORPAY_KEY_SECRET (TEST-mode keys — see backend/.env)."
        )
    return key_id, key_secret


def get_public_key_id() -> str:
    """The ONLY credential ever safe to return to a caller/frontend —
    Razorpay's key id is a public identifier by design (required by
    Checkout.js to open the payment modal). Raises RazorpayConfigurationError
    if not configured, same as any other use of the credentials.
    """
    key_id, _ = _get_credentials()
    return key_id


def _raise_for_razorpay_error(response: httpx.Response) -> None:
    """Parses Razorpay's documented error shape
    ({"error": {"code", "description", ...}}) into a sanitized
    RazorpayAPIError. Never includes request headers/credentials in the
    raised message.
    """
    try:
        body = response.json()
        description = body.get("error", {}).get("description") or f"Razorpay API error (HTTP {response.status_code})"
    except Exception:
        description = f"Razorpay API error (HTTP {response.status_code})"
    raise RazorpayAPIError(description, status_code=response.status_code)


def create_order(
    amount_rupees: float,
    *,
    currency: str = "INR",
    receipt: Optional[str] = None,
    notes: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Creates a Razorpay TEST-MODE order for `amount_rupees` and returns
    Razorpay's raw order object (a dict; the caller maps whatever fields it
    needs — this module does not reshape Razorpay's response). The
    returned dict's "id" field is the Razorpay order id.

    Raises RazorpayConfigurationError if credentials are missing, or
    RazorpayAPIError if Razorpay rejects the request or is unreachable.
    """
    if amount_rupees <= 0:
        raise ValueError(f"amount_rupees must be positive, got {amount_rupees!r}.")

    key_id, key_secret = _get_credentials()
    amount_paise = round(amount_rupees * PAISE_PER_RUPEE)

    payload: dict[str, Any] = {"amount": amount_paise, "currency": currency}
    if receipt:
        payload["receipt"] = receipt[:MAX_RECEIPT_LENGTH]
    if notes:
        payload["notes"] = notes

    try:
        with httpx.Client(auth=(key_id, key_secret), timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.post(f"{RAZORPAY_API_BASE}/orders", json=payload)
    except httpx.HTTPError as exc:
        raise RazorpayAPIError(f"Could not reach Razorpay to create the order: {exc}") from exc

    if response.status_code >= 400:
        _raise_for_razorpay_error(response)

    return response.json()


def fetch_payment(payment_id: str) -> dict[str, Any]:
    """Fetches a payment's AUTHORITATIVE current status directly from
    Razorpay's API — this is what "do not trust frontend-supplied payment
    data" means in practice: a client can claim a payment succeeded, but
    only this call (using the server-held secret) tells us what Razorpay
    itself actually recorded. Returns Razorpay's raw payment object.

    Raises RazorpayConfigurationError if credentials are missing, or
    RazorpayAPIError if Razorpay rejects the request, the payment id
    doesn't exist, or Razorpay is unreachable.
    """
    if not payment_id:
        raise ValueError("payment_id is required.")

    key_id, key_secret = _get_credentials()

    try:
        with httpx.Client(auth=(key_id, key_secret), timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.get(f"{RAZORPAY_API_BASE}/payments/{payment_id}")
    except httpx.HTTPError as exc:
        raise RazorpayAPIError(f"Could not reach Razorpay to fetch payment {payment_id!r}: {exc}") from exc

    if response.status_code >= 400:
        _raise_for_razorpay_error(response)

    return response.json()


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verifies a Razorpay Checkout success-callback signature using
    Razorpay's documented algorithm:

        expected = HMAC-SHA256(order_id + "|" + payment_id, key_secret)
        valid    = hmac.compare_digest(expected, provided_signature)

    Implemented directly with stdlib hmac/hashlib rather than the
    `razorpay` SDK — no new dependency needed for one HMAC computation.
    Uses hmac.compare_digest (constant-time comparison) rather than `==`,
    to avoid a timing side-channel on the comparison itself.

    Returns False for a genuinely invalid signature — does NOT raise for
    that case (a mismatch is an expected, valid outcome of this function,
    not an error). Still raises RazorpayConfigurationError if credentials
    are missing, since verification is meaningless without the secret.
    """
    if not order_id or not payment_id or not signature:
        return False

    _, key_secret = _get_credentials()

    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected_signature = hmac.new(key_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected_signature, signature)

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify a Razorpay webhook using the raw request body.

    Razorpay signs the exact raw request body with HMAC-SHA256 using the
    webhook secret. The webhook secret is deliberately separate from the
    API key secret.
    """
    if not signature:
        return False

    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        raise RazorpayConfigurationError(
            "RAZORPAY_WEBHOOK_SECRET is not configured."
        )

    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.strip())

