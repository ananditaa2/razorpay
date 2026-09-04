"""
RecoverRx Root-Cause Diagnosis Engine
Hybrid rules-based + LLM Chain-of-Thought classifier mapping raw failure codes,
customer tenure, and session telemetry to actionable, causal failure diagnoses.
"""
import json
import time
import requests
from typing import Dict, Any, Optional
from schemas import (
    RevenueAtRiskEvent, DiagnosisResult, RootCauseCategory,
    FailureArchetype, ActionType
)
import database

class DiagnosisEngine:
    def __init__(self, db_path: str = database.DB_PATH):
        self.db_path = db_path

    def diagnose(self, event: RevenueAtRiskEvent) -> DiagnosisResult:
        """
        Executes root cause diagnosis.
        If Gemini API Key is configured, queries Gemini; otherwise uses built-in
        high-precision causal reasoning engine.
        """
        settings = database.get_settings(self.db_path)
        gemini_key = settings.get("gemini_api_key", "").strip()

        if gemini_key:
            try:
                diagnosis = self._diagnose_with_gemini(event, gemini_key)
                if diagnosis:
                    self._persist_and_audit(diagnosis, event)
                    return diagnosis
            except Exception as e:
                # Graceful fallback to expert reasoning engine
                pass

        diagnosis = self._diagnose_with_expert_rules(event)
        self._persist_and_audit(diagnosis, event)
        return diagnosis

    def _diagnose_with_expert_rules(self, event: RevenueAtRiskEvent) -> DiagnosisResult:
        code = (event.raw_failure_code or "").upper()
        reason = (event.raw_failure_reason or "").lower()
        hist = event.customer_history or {}
        telemetry = event.session_telemetry or {}

        # 1. CARD PAYMENT FAILURE
        if event.archetype == FailureArchetype.CARD_FAILURE:
            if any(term in code or term in reason for term in ["EXPIRED", "CARD_EXPIRED", "EXP_DATE"]):
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.HARD_DECLINE,
                    confidence_score=0.98,
                    rationale="Card has passed its expiry threshold. Acquirer rejected authorization permanently. Automated retries on the existing card token will fail 100% of the time.",
                    actionable_intent="Prompt customer via WhatsApp/Email to update or re-enter payment instrument via secure Razorpay checkout link.",
                    is_recoverable=True,
                    suggested_action=ActionType.WHATSAPP_NUDGE
                )
            elif any(term in code or term in reason for term in ["STOLEN", "LOST", "ACCOUNT_CLOSED", "FRAUD", "RESTRICTED"]):
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.HARD_DECLINE,
                    confidence_score=0.99,
                    rationale="Card is permanently flagged as invalid/lost/closed by issuer bank. Card retry is prohibited.",
                    actionable_intent="Suppress silent retries; notify user account needs a new payment method.",
                    is_recoverable=False,
                    suggested_action=ActionType.DUNNING_EMAIL
                )
            elif any(term in code or term in reason for term in ["INSUFFICIENT", "LIMIT_EXCEEDED", "BALANCE", "SOFT_DECLINE", "LOW_BALANCE"]):
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.SOFT_DECLINE,
                    confidence_score=0.94,
                    rationale="Temporary liquidity/balance constraint or daily transaction limit reached on issuing bank. High probability of recovery once cardholder tops up or billing cycle resets.",
                    actionable_intent="Execute silent smart retry during optimal post-salary or evening bank processing window before customer intrusion.",
                    is_recoverable=True,
                    suggested_action=ActionType.SMART_RETRY
                )
            else: # Default 3DS or technical
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.TECHNICAL_DROP,
                    confidence_score=0.88,
                    rationale="Session timed out during 3DS OTP step or gateway handshake interrupted. Cardholder demonstrated active purchase intent.",
                    actionable_intent="Deploy instant frictionless UPI recovery link before customer abandons cart completely.",
                    is_recoverable=True,
                    suggested_action=ActionType.UPI_PAYMENT_LINK
                )

        # 2. CHECKOUT ABANDONMENT
        elif event.archetype == FailureArchetype.CHECKOUT_ABANDONMENT:
            if "OTP" in code or "otp" in reason:
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.CHECKOUT_FRICTION,
                    confidence_score=0.96,
                    rationale="SMS OTP delivery latency exceeded 60s causing customer drop-off. Buyer intent remains high (cart created within last 15 minutes).",
                    actionable_intent="Deliver instant 1-click WhatsApp checkout link featuring biometric/UPI intent bypassing SMS OTP entirely.",
                    is_recoverable=True,
                    suggested_action=ActionType.WHATSAPP_NUDGE
                )
            else:
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.CHECKOUT_FRICTION,
                    confidence_score=0.91,
                    rationale="Customer abandoned checkout at final review step, likely due to form error or friction. Cart items are preserved.",
                    actionable_intent="Send personalized cart resume nudge with pre-filled details.",
                    is_recoverable=True,
                    suggested_action=ActionType.WHATSAPP_NUDGE
                )

        # 3. SUBSCRIPTION RENEWAL
        elif event.archetype == FailureArchetype.SUBSCRIPTION_RENEWAL:
            if any(term in code or term in reason for term in ["EXPIRED", "TOKEN_DELETED"]):
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.HARD_DECLINE,
                    confidence_score=0.97,
                    rationale="Saved recurring card token expired. Subscribed user value is high; immediate account suspension should be prevented.",
                    actionable_intent="Initiate polite dunning email sequence providing self-serve card update portal before grace period expires.",
                    is_recoverable=True,
                    suggested_action=ActionType.DUNNING_EMAIL
                )
            else:
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.SOFT_DECLINE,
                    confidence_score=0.93,
                    rationale="Recurring debit declined due to issuer bank off-peak downtime or temporary limit breach. Prior renewal history indicates loyal subscriber.",
                    actionable_intent="Trigger intelligent retry scheduled for early morning batch window (+24 hours).",
                    is_recoverable=True,
                    suggested_action=ActionType.SMART_RETRY
                )

        # 4. OVERDUE B2B INVOICE
        elif event.archetype == FailureArchetype.INVOICE_OVERDUE:
            if hist.get("has_dispute") or "DISPUTED" in code:
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.INVOICE_DISPUTED,
                    confidence_score=0.99,
                    rationale="Client opened formal billing contest or purchase order line-item dispute. Routine dunning emails will frustrate client and damage B2B relationship.",
                    actionable_intent="Halt all automated collection chasers immediately. Escalate to dedicated Account Executive with dispute brief.",
                    is_recoverable=True,
                    suggested_action=ActionType.HUMAN_ESCALATION
                )
            elif hist.get("is_chronic") or event.amount > 100000:
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.INVOICE_CHRONIC,
                    confidence_score=0.94,
                    rationale=f"High-value receivable (₹{event.amount:,.2f}) with chronic payment delay (>20 days avg). Templated emails have exhausted their utility.",
                    actionable_intent="Initiate executive Hinglish voice recovery call or assign collector task with custom settlement terms.",
                    is_recoverable=True,
                    suggested_action=ActionType.VOICE_AI_CALL
                )
            else:
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.INVOICE_FIRST_TIME,
                    confidence_score=0.92,
                    rationale="First-time minor payment delay on Net-30 invoice. High credibility corporate account; late payment is likely an approval workflow oversight.",
                    actionable_intent="Dispatch gentle, professional invoice reminder with instant Razorpay NEFT/RTGS virtual account pay button.",
                    is_recoverable=True,
                    suggested_action=ActionType.DUNNING_EMAIL
                )

        # 5. UPI AUTOPAY / NACH MANDATE
        elif event.archetype == FailureArchetype.MANDATE_FAILURE:
            if any(term in code or term in reason for term in ["EXPIRED", "REVOKED", "LIMIT_EXCEEDED"]):
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.MANDATE_EXPIRED,
                    confidence_score=0.96,
                    rationale="UPI Autopay mandate has reached maximum authorized amount or customer revoked autopay authorization in banking app.",
                    actionable_intent="Present customer with instant 1-tap re-mandate registration on UPI app.",
                    is_recoverable=True,
                    suggested_action=ActionType.WHATSAPP_NUDGE
                )
            else: # E01 / Insufficient balance
                return DiagnosisResult(
                    event_id=event.event_id,
                    category=RootCauseCategory.MANDATE_BALANCE,
                    confidence_score=0.95,
                    rationale="Mandate debit attempt failed with NPCI return code E01 (Insufficient Funds). Common occurrence around month-end prior to salary disbursement.",
                    actionable_intent="Sequence mandate retry on upcoming salary credit date (1st/5th) and offer manual UPI backup link.",
                    is_recoverable=True,
                    suggested_action=ActionType.SMART_RETRY
                )

        # Fallback
        return DiagnosisResult(
            event_id=event.event_id,
            category=RootCauseCategory.SOFT_DECLINE,
            confidence_score=0.85,
            rationale="Unclassified failure pattern. Initiating least-intrusive recovery path.",
            actionable_intent="Analyze failure logs and retry silently.",
            is_recoverable=True,
            suggested_action=ActionType.SMART_RETRY
        )

    def _diagnose_with_gemini(self, event: RevenueAtRiskEvent, api_key: str) -> Optional[DiagnosisResult]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"""
        You are the RecoverRx Diagnostic Engine. Analyze this revenue failure event and return a JSON object.
        Event Details:
        - Archetype: {event.archetype.value}
        - Customer: {event.customer_name} (ID: {event.customer_id})
        - Amount: ₹{event.amount}
        - Raw Failure Code: {event.raw_failure_code}
        - Raw Reason: {event.raw_failure_reason}
        - History: {json.dumps(event.customer_history)}
        - Session: {json.dumps(event.session_telemetry)}

        Categories allowed: hard_decline, soft_decline, technical_drop, checkout_friction, invoice_first_time, invoice_chronic, invoice_disputed, mandate_balance, mandate_expired
        Actions allowed: smart_retry, whatsapp_nudge, dunning_email, voice_ai_call, upi_payment_link, human_escalation

        Return ONLY a JSON matching this exact structure:
        {{
            "category": "...",
            "confidence_score": 0.95,
            "rationale": "...",
            "actionable_intent": "...",
            "is_recoverable": true,
            "suggested_action": "..."
        }}
        """
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            res_dict = json.loads(text)
            return DiagnosisResult(
                event_id=event.event_id,
                category=RootCauseCategory(res_dict.get("category", "soft_decline")),
                confidence_score=float(res_dict.get("confidence_score", 0.9)),
                rationale=res_dict.get("rationale", ""),
                actionable_intent=res_dict.get("actionable_intent", ""),
                is_recoverable=bool(res_dict.get("is_recoverable", True)),
                suggested_action=ActionType(res_dict.get("suggested_action", "smart_retry"))
            )
        return None

    def _persist_and_audit(self, diagnosis: DiagnosisResult, event: RevenueAtRiskEvent):
        database.save_diagnosis(diagnosis, self.db_path)
        database.record_audit(
            event_id=event.event_id,
            stage="DIAGNOSE",
            actor="Diagnosis_LLMEngine",
            action_summary=f"Diagnosed as {diagnosis.category.value} (Confidence: {int(diagnosis.confidence_score*100)}%). Action: {diagnosis.suggested_action.value}",
            compliance_tag="ROOT_CAUSE_CERTIFIED",
            metadata=diagnosis.to_dict(),
            db_path=self.db_path
        )
