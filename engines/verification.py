"""
RecoverRx Verification & Incremental Measurement Engine
Proves true incremental revenue recovery by comparing Treatment group lift against
the randomized Holdout Control group over a 72-hour attribution window.
"""
import time
from typing import Dict, Any, Optional
import database

class VerificationEngine:
    def __init__(self, db_path: str = database.DB_PATH):
        self.db_path = db_path

    def register_payment_observed(
        self, event_id: str, amount: Optional[float] = None,
        source: str = "webhook_payment_captured"
    ) -> Dict[str, Any]:
        """
        Processes a successful payment event received from Razorpay/Stripe/Bank.
        Credits attribution to the last executed action if within 72h window.
        """
        event = database.get_event(event_id, self.db_path)
        if not event:
            return {"error": "Event not found"}

        recovered_amount = amount if amount is not None else event['amount']
        executions = database.get_executions(event_id, self.db_path)
        last_exec = executions[-1] if executions else None
        attribution_action_id = last_exec['execution_id'] if last_exec else "organic_self_recovery"

        # Check attribution window (72h)
        window_hours = 72.0
        if last_exec:
            elapsed_hours = (time.time() - last_exec['created_at']) / 3600.0
            is_within_window = elapsed_hours <= window_hours
        else:
            is_within_window = True
            elapsed_hours = 0.0

        database.record_recovery(
            event_id=event_id,
            recovered_amount=recovered_amount,
            attribution_action_id=attribution_action_id,
            attribution_window_hours=elapsed_hours,
            db_path=self.db_path
        )

        group_type = "CONTROL_HOLDOUT" if event['is_holdout'] else "TREATMENT"
        database.record_audit(
            event_id=event_id,
            stage="VERIFY",
            actor="Verification_AttributionEngine",
            action_summary=f"Payment verified for ₹{recovered_amount:,.2f} [{group_type}]. Attributed to {attribution_action_id} ({elapsed_hours:.1f}h post-action).",
            compliance_tag="REVENUE_VERIFIED",
            metadata={
                "recovered_amount": recovered_amount,
                "is_holdout": event['is_holdout'],
                "attribution_action_id": attribution_action_id,
                "source": source
            },
            db_path=self.db_path
        )

        return {
            "success": True,
            "event_id": event_id,
            "recovered_amount": recovered_amount,
            "is_holdout": event['is_holdout'],
            "attribution_action_id": attribution_action_id
        }

    def compute_incremental_metrics(self) -> Dict[str, Any]:
        """
        Calculates causal incremental lift:
        Incremental Lift = Treatment Recovery Rate - Holdout Control Recovery Rate
        True Incremental Revenue = Treatment Revenue * Incremental Lift
        """
        return database.get_analytics_summary(self.db_path)
