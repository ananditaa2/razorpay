"""
RecoverRx Signal Ingestion & Detection Engine
Normalizes disparate webhook feeds, checkout session telemetry, ERP aging records,
and assigns deterministic A/B holdout control groups.
"""
import hashlib
import time
from typing import Dict, Any, Optional
from schemas import RevenueAtRiskEvent, FailureArchetype
import database

def is_assigned_to_holdout(customer_id: str, holdout_rate: float = 0.10) -> bool:
    """
    Deterministic hash-based allocation to ensure consistent holdout assignment.
    Prevents holdout contamination across repeated touches.
    """
    digest = hashlib.md5(customer_id.encode('utf-8')).hexdigest()
    int_val = int(digest[:6], 16)
    return (int_val % 1000) < (holdout_rate * 1000)

class IngestionEngine:
    def __init__(self, db_path: str = database.DB_PATH):
        self.db_path = db_path

    def ingest_razorpay_event(self, payload: Dict[str, Any]) -> RevenueAtRiskEvent:
        """
        Normalizes Razorpay webhooks (e.g. payment.failed, subscription.halted, mandate.failed)
        """
        event_name = payload.get("event", "payment.failed")
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        if not entity:
            entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})

        cust_id = entity.get("customer_id") or entity.get("email") or f"cust_{hashlib.md5(str(payload).encode()).hexdigest()[:8]}"
        cust_name = entity.get("notes", {}).get("customer_name") or entity.get("name") or "Valued Customer"
        cust_phone = entity.get("contact") or "+919876543210"
        cust_email = entity.get("email") or "customer@example.com"
        amount = float(entity.get("amount", 0)) / 100.0 if entity.get("amount") else 1999.0
        currency = entity.get("currency", "INR")
        err_code = entity.get("error_code") or entity.get("failure_reason") or "BAD_REQUEST_ERROR"
        err_desc = entity.get("error_description") or "Payment processing failed at bank"

        # Determine archetype
        if "subscription" in event_name or entity.get("invoice_id"):
            archetype = FailureArchetype.SUBSCRIPTION_RENEWAL
        elif "mandate" in err_code.lower() or "nach" in err_desc.lower() or "token" in entity:
            archetype = FailureArchetype.MANDATE_FAILURE
        else:
            archetype = FailureArchetype.CARD_FAILURE

        settings = database.get_settings(self.db_path)
        holdout_rate = float(settings.get("holdout_rate", "0.10"))
        is_holdout = is_assigned_to_holdout(cust_id, holdout_rate)

        event = RevenueAtRiskEvent(
            customer_id=cust_id,
            customer_name=cust_name,
            customer_phone=cust_phone,
            customer_email=cust_email,
            amount=amount,
            currency=currency,
            archetype=archetype,
            gateway="Razorpay",
            raw_failure_code=err_code,
            raw_failure_reason=err_desc,
            channel="gateway_webhook",
            is_holdout=is_holdout,
            customer_history=entity.get("notes", {}),
            session_telemetry={"razorpay_event": event_name, "acquirer_data": entity.get("acquirer_data", {})},
            status="holdout" if is_holdout else "detected"
        )

        database.save_event(event, self.db_path)
        database.record_audit(
            event_id=event.event_id,
            stage="DETECT",
            actor="Ingestion_RazorpayWebhook",
            action_summary=f"Ingested {archetype.value} for ₹{amount:,.2f} ({cust_name}). Holdout: {is_holdout}",
            compliance_tag="SIGNAL_VERIFIED",
            metadata={"raw_event": event_name, "failure_code": err_code, "is_holdout": is_holdout},
            db_path=self.db_path
        )
        return event

    def ingest_checkout_telemetry(self, session_data: Dict[str, Any]) -> RevenueAtRiskEvent:
        """
        Normalizes drop-offs captured during checkout flow (e.g. OTP failure, form error, UPI delay).
        """
        cust_id = session_data.get("customer_id") or f"cart_{hashlib.md5(str(session_data).encode()).hexdigest()[:8]}"
        cust_name = session_data.get("customer_name", "Shopper")
        amount = float(session_data.get("cart_total", 2499.0))

        settings = database.get_settings(self.db_path)
        holdout_rate = float(settings.get("holdout_rate", "0.10"))
        is_holdout = is_assigned_to_holdout(cust_id, holdout_rate)

        event = RevenueAtRiskEvent(
            customer_id=cust_id,
            customer_name=cust_name,
            customer_phone=session_data.get("phone", "+919812345678"),
            customer_email=session_data.get("email", "shopper@example.com"),
            amount=amount,
            currency="INR",
            archetype=FailureArchetype.CHECKOUT_ABANDONMENT,
            gateway="Checkout_Funnel",
            raw_failure_code=session_data.get("drop_step", "OTP_TIMEOUT"),
            raw_failure_reason=session_data.get("drop_reason", "Customer exited checkout at OTP verification screen after 90s delay"),
            channel="web_checkout",
            is_holdout=is_holdout,
            customer_history={"cart_items": session_data.get("items", ["Premium Subscription Plan"])},
            session_telemetry=session_data,
            status="holdout" if is_holdout else "detected"
        )

        database.save_event(event, self.db_path)
        database.record_audit(
            event_id=event.event_id,
            stage="DETECT",
            actor="Ingestion_CheckoutFunnel",
            action_summary=f"Detected cart abandonment ₹{amount:,.2f} at step {event.raw_failure_code}. Holdout: {is_holdout}",
            compliance_tag="SIGNAL_VERIFIED",
            metadata={"step": event.raw_failure_code, "telemetry": session_data},
            db_path=self.db_path
        )
        return event

    def ingest_erp_invoice(self, invoice_data: Dict[str, Any]) -> RevenueAtRiskEvent:
        """
        Normalizes ERP / Receivables invoice overdue events (Net-30, Net-60 overdue).
        """
        cust_id = invoice_data.get("customer_id") or f"corp_{invoice_data.get('invoice_no', 'INV-101')}"
        cust_name = invoice_data.get("company_name", "Enterprise Client")
        amount = float(invoice_data.get("outstanding_amount", 125000.0))

        settings = database.get_settings(self.db_path)
        holdout_rate = float(settings.get("holdout_rate", "0.10"))
        is_holdout = is_assigned_to_holdout(cust_id, holdout_rate)

        days_overdue = invoice_data.get("days_overdue", 15)
        dispute_flag = invoice_data.get("has_dispute", False)

        event = RevenueAtRiskEvent(
            customer_id=cust_id,
            customer_name=cust_name,
            customer_phone=invoice_data.get("finance_phone", "+919871122334"),
            customer_email=invoice_data.get("finance_email", "billing@enterprise.com"),
            amount=amount,
            currency="INR",
            archetype=FailureArchetype.INVOICE_OVERDUE,
            gateway="ERP_Receivables",
            raw_failure_code=f"DAYS_OVERDUE_{days_overdue}" + ("_DISPUTED" if dispute_flag else ""),
            raw_failure_reason=f"Invoice #{invoice_data.get('invoice_no', 'INV-101')} is {days_overdue} days past due date.",
            channel="b2b_receivables",
            is_holdout=is_holdout,
            customer_history={
                "previous_invoices": invoice_data.get("previous_invoices", 5),
                "avg_payment_delay_days": invoice_data.get("avg_delay_days", 12),
                "is_chronic": invoice_data.get("avg_delay_days", 12) > 20,
                "has_dispute": dispute_flag
            },
            session_telemetry=invoice_data,
            status="holdout" if is_holdout else "detected"
        )

        database.save_event(event, self.db_path)
        database.record_audit(
            event_id=event.event_id,
            stage="DETECT",
            actor="Ingestion_ERPReceivables",
            action_summary=f"Detected overdue B2B invoice ₹{amount:,.2f} ({days_overdue} days late). Holdout: {is_holdout}",
            compliance_tag="SIGNAL_VERIFIED",
            metadata={"invoice_no": invoice_data.get("invoice_no"), "days_overdue": days_overdue},
            db_path=self.db_path
        )
        return event
