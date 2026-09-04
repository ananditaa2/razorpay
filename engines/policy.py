"""
RecoverRx Intervention Policy Engine
Evaluates diagnosis against hard-coded compliance rules, TRAI DND regulations,
calling window hours, touch caps, and human-in-the-loop escalation thresholds.
"""
import time
from datetime import datetime
from typing import Dict, Any, Tuple
from schemas import (
    RevenueAtRiskEvent, DiagnosisResult, PolicyDecision,
    ActionType, ComplianceStatus, RootCauseCategory
)
import database

class PolicyEngine:
    def __init__(self, db_path: str = database.DB_PATH):
        self.db_path = db_path

    def decide(self, event: RevenueAtRiskEvent, diagnosis: DiagnosisResult) -> PolicyDecision:
        """
        Determines the single bounded, compliant intervention to execute.
        Applies immutable stopping rules and safeguards.
        """
        settings = database.get_settings(self.db_path)
        max_touches = int(settings.get("max_touches", "3"))
        cooloff_hours = float(settings.get("cooloff_hours", "24"))
        call_start = int(settings.get("call_window_start_ist", "9"))
        call_end = int(settings.get("call_window_end_ist", "20"))
        high_val_thresh = float(settings.get("high_value_escalation_inr", "50000"))

        now = time.time()

        # 1. Check if customer has an active billing dispute
        if diagnosis.category == RootCauseCategory.INVOICE_DISPUTED or event.customer_history.get("has_dispute"):
            return self._build_decision(
                event=event,
                action_type=ActionType.HUMAN_ESCALATION,
                status=ComplianceStatus.SUPPRESSED_DISPUTE,
                rule="RBI_FAIR_PRACTICES_DISPUTE_FREEZE",
                reasoning="Billing is actively contested. Automated collections frozen per RBI guidelines. Incident routed to Human Collector / Account Lead.",
                requires_human=True
            )

        # 2. Check if customer previously opted out
        if event.customer_history.get("opted_out") or event.customer_history.get("dnd_active"):
            # If DND is active, only silent retries or official email receipts allowed
            if diagnosis.suggested_action in [ActionType.VOICE_AI_CALL, ActionType.WHATSAPP_NUDGE]:
                return self._build_decision(
                    event=event,
                    action_type=ActionType.DUNNING_EMAIL,
                    status=ComplianceStatus.SUPPRESSED_DND,
                    rule="TRAI_DND_TELECOM_REGULATION",
                    reasoning="Customer phone number is registered on TRAI NDNC registry. Outbound voice/WhatsApp suppressed; downgraded to non-intrusive email notification.",
                    requires_human=False
                )

        # 3. Check touch caps
        if event.touches_count >= max_touches:
            return self._build_decision(
                event=event,
                action_type=ActionType.SUPPRESS_ACTION,
                status=ComplianceStatus.SUPPRESSED_MAX_TOUCHES,
                rule="MAX_TOUCH_LIMIT_EXCEEDED",
                reasoning=f"Incident has reached maximum allowed customer contacts ({event.touches_count}/{max_touches}). Automated outreach terminated to prevent customer harassment.",
                requires_human=True
            )

        # 4. Check cool-off interval
        if event.last_touch_timestamp and (now - event.last_touch_timestamp) < (cooloff_hours * 3600):
            elapsed_hrs = round((now - event.last_touch_timestamp) / 3600.0, 1)
            # Silent retries don't harass customer, but communications do
            if diagnosis.suggested_action != ActionType.SMART_RETRY:
                return self._build_decision(
                    event=event,
                    action_type=ActionType.SUPPRESS_ACTION,
                    status=ComplianceStatus.SUPPRESSED_COOLOFF,
                    rule="COOLOFF_WINDOW_ACTIVE",
                    reasoning=f"Cool-off window active ({elapsed_hrs}h elapsed vs {cooloff_hours}h required). Outreach delayed to respect customer attention.",
                    requires_human=False
                )

        # 5. Check High-Value Threshold
        if event.amount >= high_val_thresh and diagnosis.suggested_action not in [ActionType.SMART_RETRY]:
            return self._build_decision(
                event=event,
                action_type=ActionType.HUMAN_ESCALATION,
                status=ComplianceStatus.COMPLIANT,
                rule="HIGH_VALUE_THRESHOLD_TRIGGER",
                reasoning=f"At-risk amount ₹{event.amount:,.2f} exceeds auto-action threshold (₹{high_val_thresh:,.2f}). Requires senior collector authorization.",
                requires_human=True
            )

        # 6. Check TRAI Calling Window for Voice AI Calls (09:00 - 20:00 IST)
        # Assuming server time is roughly IST or checking local hour
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        current_hour_ist = (now_utc.hour + 5 + (now_utc.minute + 30) // 60) % 24
        if diagnosis.suggested_action == ActionType.VOICE_AI_CALL:
            if current_hour_ist < call_start or current_hour_ist >= call_end:
                return self._build_decision(
                    event=event,
                    action_type=ActionType.VOICE_AI_CALL,
                    status=ComplianceStatus.QUEUED_OFF_HOURS,
                    rule="TRAI_CALLING_HOURS_COMPLIANCE",
                    reasoning=f"Current time ({current_hour_ist:02d}:00 IST) is outside TRAI permissible window ({call_start}:00 - {call_end}:00 IST). Voice AI call queued for morning release.",
                    requires_human=False
                )

        # 7. Escalation hierarchy (Least-intrusive first)
        # Touch 0 for soft decline -> Smart Retry
        # Touch 1 -> Nudge (WhatsApp or Email)
        # Touch 2+ -> Voice AI or Human
        chosen_action = diagnosis.suggested_action
        if event.touches_count == 0 and diagnosis.category in [RootCauseCategory.SOFT_DECLINE, RootCauseCategory.MANDATE_BALANCE]:
            chosen_action = ActionType.SMART_RETRY
        elif event.touches_count == 1 and chosen_action == ActionType.SMART_RETRY:
            chosen_action = ActionType.WHATSAPP_NUDGE

        return self._build_decision(
            event=event,
            action_type=chosen_action,
            status=ComplianceStatus.COMPLIANT,
            rule="POLICY_LEAST_INTRUSIVE_HIERARCHY",
            reasoning=f"Selected least-intrusive compliant channel ({chosen_action.value}) for touch #{event.touches_count + 1}.",
            requires_human=False
        )

    def _build_decision(
        self, event: RevenueAtRiskEvent, action_type: ActionType,
        status: ComplianceStatus, rule: str, reasoning: str, requires_human: bool
    ) -> PolicyDecision:
        decision = PolicyDecision(
            event_id=event.event_id,
            action_type=action_type,
            compliance_status=status,
            rule_applied=rule,
            reasoning=reasoning,
            requires_human_approval=requires_human,
            scheduled_timestamp=time.time()
        )
        database.save_decision(decision, self.db_path)
        database.record_audit(
            event_id=event.event_id,
            stage="DECIDE",
            actor="Policy_GovernanceEngine",
            action_summary=f"Decision: {action_type.value} [{status.value}] via {rule}. HumanReq: {requires_human}",
            compliance_tag="POLICY_VERIFIED",
            metadata=decision.to_dict(),
            db_path=self.db_path
        )
        return decision
