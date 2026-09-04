"""
RecoverRx Bounded Execution Layer
Executes strictly authorized tools: Smart Retries, WhatsApp Nudges, Tiered Dunning,
Hinglish Voice AI recovery dialogs, Dynamic UPI links, and Human Escalation queues.
"""
import time
import urllib.parse
from typing import Dict, Any, Optional
from schemas import (
    RevenueAtRiskEvent, PolicyDecision, BoundedExecution,
    ActionType, ComplianceStatus
)
import database

class ExecutionEngine:
    def __init__(self, db_path: str = database.DB_PATH):
        self.db_path = db_path

    def execute(self, event: RevenueAtRiskEvent, decision: PolicyDecision) -> Optional[BoundedExecution]:
        """
        Dispatches only pre-approved, policy-cleared tools.
        """
        # If suppressed or requires human approval, do not fire customer-facing comms automatically
        if decision.compliance_status in [
            ComplianceStatus.SUPPRESSED_MAX_TOUCHES,
            ComplianceStatus.SUPPRESSED_COOLOFF,
            ComplianceStatus.SUPPRESSED_OPT_OUT
        ]:
            return None

        if decision.requires_human_approval and decision.action_type != ActionType.HUMAN_ESCALATION:
            return self._dispatch_human_task(event, decision, reason="Requires Human-in-the-Loop review before dispatch")

        action_map = {
            ActionType.SMART_RETRY: self._dispatch_smart_retry,
            ActionType.WHATSAPP_NUDGE: self._dispatch_whatsapp_nudge,
            ActionType.DUNNING_EMAIL: self._dispatch_dunning_email,
            ActionType.VOICE_AI_CALL: self._dispatch_voice_ai_call,
            ActionType.UPI_PAYMENT_LINK: self._dispatch_upi_payment_link,
            ActionType.HUMAN_ESCALATION: self._dispatch_human_task
        }

        handler = action_map.get(decision.action_type)
        if not handler:
            return None

        execution = handler(event, decision)
        database.save_execution(execution, self.db_path)
        database.increment_event_touch(event.event_id, self.db_path)

        database.record_audit(
            event_id=event.event_id,
            stage="ACT",
            actor=f"Executor_{decision.action_type.value}",
            action_summary=f"Dispatched {decision.action_type.value} on channel {execution.channel}. Status: {execution.status}",
            compliance_tag="BOUNDED_ACTION_EXECUTED",
            metadata=execution.to_dict(),
            db_path=self.db_path
        )
        return execution

    def _generate_upi_url(self, event: RevenueAtRiskEvent) -> str:
        pa = "recoverrx.merchant@icici"
        pn = "RecoverRx Merchant"
        am = f"{event.amount:.2f}"
        cu = event.currency
        tr = f"REC_{event.event_id[:8]}"
        tn = f"Settlement for {event.event_id}"
        query = urllib.parse.urlencode({"pa": pa, "pn": pn, "am": am, "cu": cu, "tr": tr, "tn": tn})
        return f"upi://pay?{query}"

    def _dispatch_smart_retry(self, event: RevenueAtRiskEvent, decision: PolicyDecision) -> BoundedExecution:
        # Calculate optimal next retry window (e.g. off-peak evening or post-salary cycle)
        scheduled_delay_hours = 6
        simulated_network_route = "HDFC_PRIMARY_SWITCH" if "HDFC" in event.raw_failure_reason else "ICICI_DIRECT_ACQUIRER"

        payload = {
            "retry_timestamp": time.time() + (scheduled_delay_hours * 3600),
            "target_gateway": event.gateway,
            "routing_network": simulated_network_route,
            "card_updater_checked": True,
            "token_status": "active_refreshed"
        }

        return BoundedExecution(
            event_id=event.event_id,
            action_type=ActionType.SMART_RETRY,
            channel="gateway_smart_router",
            payload=payload,
            status="executed",
            response_data={
                "gateway_ack": "ACCEPTED_FOR_RETRY",
                "next_execution_window": f"+{scheduled_delay_hours}h (Low Traffic Window)",
                "success_probability": "74%"
            }
        )

    def _dispatch_whatsapp_nudge(self, event: RevenueAtRiskEvent, decision: PolicyDecision) -> BoundedExecution:
        upi_link = self._generate_upi_url(event)
        cart_desc = event.customer_history.get("cart_items", ["Your Pending Order"])[0]

        message_body = (
            f"Namaste {event.customer_name}! 👋\n\n"
            f"We noticed your payment of *₹{event.amount:,.2f}* for *{cart_desc}* wasn't completed due to a temporary bank delay.\n\n"
            f"Your order is safe and reserved. You can finish it in 1 tap with UPI (GPay/PhonePe/Paytm) without typing any card or OTP details:\n\n"
            f"👉 Pay instantly: {upi_link}\n\n"
            f"Need help? Reply to this message directly. [Reply STOP to unsubscribe]"
        )

        payload = {
            "recipient_phone": event.customer_phone,
            "template_name": "recoverrx_cart_nudge_v2",
            "message_body": message_body,
            "cta_buttons": [
                {"type": "UPI_INTENT", "label": "⚡ Pay via UPI App", "url": upi_link},
                {"type": "URL", "label": "💳 Pay with Card/NetBanking", "url": f"https://rzp.io/i/{event.event_id[:8]}"}
            ]
        }

        return BoundedExecution(
            event_id=event.event_id,
            action_type=ActionType.WHATSAPP_NUDGE,
            channel="whatsapp_business_api",
            payload=payload,
            status="executed",
            response_data={"message_id": f"wamid_{time.time()}", "delivery_status": "delivered"}
        )

    def _dispatch_dunning_email(self, event: RevenueAtRiskEvent, decision: PolicyDecision) -> BoundedExecution:
        subject = f"Action Required: Payment Update for {event.customer_name} (Invoice #{event.event_id[:8]})"
        body = (
            f"Dear {event.customer_name},\n\n"
            f"We were unable to process your scheduled payment of ₹{event.amount:,.2f} via {event.gateway}.\n"
            f"Reason reported by issuer: {event.raw_failure_reason}.\n\n"
            f"To ensure uninterrupted service, please update your billing details or complete the invoice settlement at your earliest convenience.\n\n"
            f"Virtual Account Details:\n"
            f"Bank: ICICI Bank\n"
            f"Account Name: RecoverRx Escrow\n"
            f"IFSC: ICIC0000104\n"
            f"Virtual A/C No: RZPREC{event.customer_id.replace('-', '')[:10]}\n\n"
            f"Or settle online immediately: https://rzp.io/i/{event.event_id[:8]}\n\n"
            f"Sincerely,\nRecoverRx Revenue Operations"
        )

        payload = {
            "recipient_email": event.customer_email,
            "subject": subject,
            "body": body,
            "touch_level": event.touches_count + 1
        }

        return BoundedExecution(
            event_id=event.event_id,
            action_type=ActionType.DUNNING_EMAIL,
            channel="sendgrid_smtp",
            payload=payload,
            status="executed",
            response_data={"message_id": f"mail_{time.time()}", "delivery_status": "sent"}
        )

    def _dispatch_voice_ai_call(self, event: RevenueAtRiskEvent, decision: PolicyDecision) -> BoundedExecution:
        # Conversational, respectful Hinglish script tailored for India B2C/B2B recovery
        dialog_script = [
            {
                "speaker": "RecoverRx_AI",
                "text": f"Namaste {event.customer_name} ji! Main RecoverRx se Neha baat kar rahi hoon. Kya meri baat {event.customer_name} se ho rahi hai?"
            },
            {
                "speaker": "Customer",
                "text": "Haan ji, boliye."
            },
            {
                "speaker": "RecoverRx_AI",
                "text": f"Thank you ji. Aapka ₹{event.amount:,.2f} ka payment bank timeout ki wajah se fail ho gaya tha. Humne aapke WhatsApp par direct UPI link share kiya hai. Kya aap abhi payment complete kar payenge ya koi specific date prefer karenge?"
            },
            {
                "speaker": "Customer",
                "text": "Haan, abhi salary aane wali hai. Main Friday ko pakka pay kar dunga."
            },
            {
                "speaker": "RecoverRx_AI",
                "text": "Bahut shukriya! Humne Friday tak ke liye note kar liya hai aur reminder set kar diya hai. Aapka din shubh rahe!"
            }
        ]

        payload = {
            "recipient_phone": event.customer_phone,
            "language": "Hinglish (hi-IN)",
            "voice_id": "hi-IN-Wavenet-D",
            "dialog_script": dialog_script,
            "ptp_detected": True,
            "ptp_promised_relative_days": 3, # Friday
            "simulated_sentiment": "COOPERATIVE"
        }

        return BoundedExecution(
            event_id=event.event_id,
            action_type=ActionType.VOICE_AI_CALL,
            channel="exotel_voice_ai",
            payload=payload,
            status="executed",
            response_data={
                "call_sid": f"call_{time.time()}",
                "duration_seconds": 45,
                "disposition": "PTP_COMMITTED",
                "transcription": "Customer promised payment by Friday post-salary."
            }
        )

    def _dispatch_upi_payment_link(self, event: RevenueAtRiskEvent, decision: PolicyDecision) -> BoundedExecution:
        upi_link = self._generate_upi_url(event)
        payload = {
            "upi_uri": upi_link,
            "qr_data": upi_link,
            "amount": event.amount,
            "channel": "instant_sms_push"
        }

        return BoundedExecution(
            event_id=event.event_id,
            action_type=ActionType.UPI_PAYMENT_LINK,
            channel="fast2sms_telecom",
            payload=payload,
            status="executed",
            response_data={"sms_id": f"sms_{time.time()}", "delivery_status": "delivered"}
        )

    def _dispatch_human_task(self, event: RevenueAtRiskEvent, decision: PolicyDecision, reason: str = "High-Value / Dispute") -> BoundedExecution:
        payload = {
            "ticket_id": f"TASK_{event.event_id[:8]}",
            "assigned_team": "Senior Receivables & Disputes Lead",
            "priority": "P1_URGENT" if event.amount > 100000 else "P2_ELEVATED",
            "customer_name": event.customer_name,
            "amount_at_risk": event.amount,
            "reason": reason,
            "dispute_notes": event.customer_history.get("dispute_notes", "Invoice review requested by customer finance department."),
            "suggested_compromise": "Offer 3% prompt-settlement waiver or 2-part milestone payment if approved."
        }

        return BoundedExecution(
            event_id=event.event_id,
            action_type=ActionType.HUMAN_ESCALATION,
            channel="internal_task_queue",
            payload=payload,
            status="queued",
            response_data={"ticket_status": "PENDING_MANAGER_REVIEW"}
        )
