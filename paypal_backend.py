from __future__ import annotations

import base64
import io
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import qrcode
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

# PayPal sandbox by default.
# Change to https://api-m.paypal.com only when you are ready for live mode.
PAYPAL_BASE = os.getenv("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")

PAYPAL_CLIENT_ID = os.environ["PAYPAL_CLIENT_ID"]
PAYPAL_CLIENT_SECRET = os.environ["PAYPAL_CLIENT_SECRET"]
PAYPAL_WEBHOOK_ID = os.environ["PAYPAL_WEBHOOK_ID"]

# Optional defaults
DEFAULT_CURRENCY = os.getenv("PAYPAL_CURRENCY", "PHP")
DEFAULT_RETURN_URL = os.getenv("PAYPAL_RETURN_URL", "https://example.com/paypal/return")
DEFAULT_CANCEL_URL = os.getenv("PAYPAL_CANCEL_URL", "https://example.com/paypal/cancel")

app = Flask(__name__)

# Demo storage for thesis/testing.
# Replace with SQLite/PostgreSQL if you want persistence across restarts.
ORDERS: Dict[str, Dict[str, Any]] = {}
PROCESSED_WEBHOOK_IDS: set[str] = set()


def get_access_token() -> str:
    """Get OAuth token from PayPal."""
    resp = requests.post(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def find_approval_url(order_json: dict) -> str:
    """Extract the buyer approval URL from PayPal's links array."""
    for link in order_json.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            return link["href"]
    raise RuntimeError("Approval URL not found in PayPal response")


def make_qr_data_url(text: str) -> str:
    """Convert a URL into a base64 PNG data URL for display in Tkinter."""
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@app.post("/api/paypal/orders")
def create_order():
    """
    Create a PayPal order for the exact amount selected in the UI.
    Returns:
      - orderId
      - status
      - approvalUrl
      - qrDataUrl
    """
    try:
        body = request.get_json(force=True, silent=True) or {}

        amount = str(body.get("amount", "0.00"))
        currency = str(body.get("currency", DEFAULT_CURRENCY))
        reference_id = str(body.get("referenceId", "vm-001"))
        description = str(body.get("description", "Fruit Shake Order"))
        return_url = str(body.get("returnUrl", DEFAULT_RETURN_URL))
        cancel_url = str(body.get("cancelUrl", DEFAULT_CANCEL_URL))

        access_token = get_access_token()
        request_id = body.get("requestId") or f"vm-order-{int(time.time() * 1000)}"

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "description": description,
                    "amount": {
                        "currency_code": currency,
                        "value": amount,
                    },
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                        "user_action": "PAY_NOW",
                        "shipping_preference": "NO_SHIPPING",
                    }
                }
            },
        }

        resp = requests.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": request_id,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        approval_url = find_approval_url(data)
        qr_data_url = make_qr_data_url(approval_url)

        ORDERS[data["id"]] = {
            "orderId": data["id"],
            "status": data.get("status", "CREATED"),
            "referenceId": reference_id,
            "amount": amount,
            "currency": currency,
            "approvalUrl": approval_url,
            "qrDataUrl": qr_data_url,
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "captureResponse": None,
            "lastWebhookEvent": None,
        }

        return jsonify(
            {
                "orderId": data["id"],
                "status": data.get("status", "CREATED"),
                "approvalUrl": approval_url,
                "qrDataUrl": qr_data_url,
            }
        )

    except Exception as e:
        return jsonify(
            {
                "error": "create_order_failed",
                "details": str(e),
            }
        ), 500


@app.post("/api/paypal/webhook")
def paypal_webhook():
    """
    Receive PayPal webhook events.
    Required events for this thesis flow:
      - CHECKOUT.ORDER.APPROVED
      - PAYMENT.CAPTURE.COMPLETED
      - PAYMENT.CAPTURE.DENIED
    """
    try:
        webhook_event = request.get_json(force=True, silent=False)

        # Verify webhook signature with PayPal's verify endpoint.
        verification_payload = {
            "transmission_id": request.headers.get("PAYPAL-TRANSMISSION-ID"),
            "transmission_time": request.headers.get("PAYPAL-TRANSMISSION-TIME"),
            "cert_url": request.headers.get("PAYPAL-CERT-URL"),
            "auth_algo": request.headers.get("PAYPAL-AUTH-ALGO"),
            "transmission_sig": request.headers.get("PAYPAL-TRANSMISSION-SIG"),
            "webhook_id": PAYPAL_WEBHOOK_ID,
            "webhook_event": webhook_event,
        }

        access_token = get_access_token()
        verify = requests.post(
            f"{PAYPAL_BASE}/v1/notifications/verify-webhook-signature",
            json=verification_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        verify.raise_for_status()

        if verify.json().get("verification_status") != "SUCCESS":
            return jsonify({"error": "invalid_webhook_signature"}), 400

        # Simple idempotency guard for repeated webhook deliveries.
        webhook_id = webhook_event.get("id")
        if webhook_id:
            if webhook_id in PROCESSED_WEBHOOK_IDS:
                return "", 200
            PROCESSED_WEBHOOK_IDS.add(webhook_id)

        event_type = webhook_event.get("event_type")
        resource = webhook_event.get("resource") or {}
        resource_id = resource.get("id")

        # Record the event in memory for debugging.
        if resource_id:
            ORDERS.setdefault(resource_id, {})
            ORDERS[resource_id]["lastWebhookEvent"] = event_type

        # On approval, capture server-side.
        if event_type == "CHECKOUT.ORDER.APPROVED" and resource_id:
            capture_resp = requests.post(
                f"{PAYPAL_BASE}/v2/checkout/orders/{resource_id}/capture",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": f"vm-capture-{resource_id}",
                },
                json={},
                timeout=30,
            )
            capture_resp.raise_for_status()
            capture_data = capture_resp.json()

            ORDERS.setdefault(resource_id, {})
            ORDERS[resource_id]["status"] = capture_data.get("status", "COMPLETED")
            ORDERS[resource_id]["captureResponse"] = capture_data

            return "", 200

        # Payment completed: this is the point where the machine may be told to vend.
        if event_type == "PAYMENT.CAPTURE.COMPLETED" and resource_id:
            ORDERS.setdefault(resource_id, {})
            ORDERS[resource_id]["status"] = "COMPLETED"
            ORDERS[resource_id]["captureCompletedAt"] = datetime.utcnow().isoformat() + "Z"
            return "", 200

        # Payment denied: fail the order.
        if event_type == "PAYMENT.CAPTURE.DENIED" and resource_id:
            ORDERS.setdefault(resource_id, {})
            ORDERS[resource_id]["status"] = "DENIED"
            ORDERS[resource_id]["captureDeniedAt"] = datetime.utcnow().isoformat() + "Z"
            return "", 200

        # Other events can be acknowledged and ignored for now.
        return "", 200

    except Exception as e:
        # Non-2xx responses can trigger retries, which is fine for testing.
        return jsonify(
            {
                "error": "webhook_handler_failed",
                "details": str(e),
            }
        ), 500


@app.get("/api/paypal/orders/<order_id>")
def get_order(order_id: str):
    """
    Optional helper for polling/debugging from the UI.
    """
    try:
        access_token = get_access_token()
        resp = requests.get(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as e:
        return jsonify(
            {
                "error": "get_order_failed",
                "details": str(e),
            }
        ), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)