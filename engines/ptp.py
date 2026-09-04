"""
RecoverRx Promise-to-Pay (PTP) Tracking Engine
Logs payment commitments, monitors deadlines, calibrates customer credibility scores,
and triggers automatic policy escalations on broken commitments.
"""
import time
from typing import Dict, Any, Optional, List
from schemas import PromiseToPay, PTPStatus, RevenueAtRiskEvent
import database

class PTPTracker:
    def __init__(self, db_path: str = database.DB_PATH):
        self.db_path = db_path

    def register_ptp(
        self, event_id: str, customer_id: str, customer_name: str,
        amount: float, promised_timestamp: float, notes: str = ""
    ) -> PromiseToPay:
        """
        Logs a formal Promise-to-Pay commitment.
        """
        # Fetch existing credibility score from prior commitments if any
        all_records = database.get_all_ptp(self.db_path)
        cust_records = [r for r in all_records if r['customer_id'] == customer_id]
        if cust_records:
            kept_count = sum(1 for r in cust_records if r['status'] == PTPStatus.KEPT.value)
            credibility = round((kept_count / len(cust_records)), 2)
        else:
            credibility = 0.85 # Default initial trust score

        ptp = PromiseToPay(
            event_id=event_id,
            customer_id=customer_id,
            customer_name=customer_name,
            amount=amount,
            promised_timestamp=promised_timestamp,
            status=PTPStatus.PENDING,
            credibility_score=credibility,
            notes=notes
        )

        database.save_ptp(ptp, self.db_path)
        database.record_audit(
            event_id=event_id,
            stage="PTP",
            actor="PTP_CommitmentTracker",
            action_summary=f"PTP logged for ₹{amount:,.2f} by {customer_name}. Deadline: {time.ctime(promised_timestamp)}. Credibility: {int(credibility*100)}%",
            compliance_tag="PTP_REGISTERED",
            metadata=ptp.to_dict(),
            db_path=self.db_path
        )
        return ptp

    def fulfill_ptp(self, ptp_id: str, recovered_amount: Optional[float] = None) -> Dict[str, Any]:
        """
        Marks Promise-to-Pay as KEPT and credits recovery.
        """
        all_ptp = database.get_all_ptp(self.db_path)
        target = next((r for r in all_ptp if r['ptp_id'] == ptp_id), None)
        if not target:
            return {"error": "PTP record not found"}

        database.update_ptp_status(ptp_id, PTPStatus.KEPT, self.db_path)
        amount = recovered_amount if recovered_amount is not None else target['amount']

        # Record recovery in verifications
        database.record_recovery(
            event_id=target['event_id'],
            recovered_amount=amount,
            attribution_action_id=ptp_id,
            attribution_window_hours=72.0,
            db_path=self.db_path
        )

        database.record_audit(
            event_id=target['event_id'],
            stage="PTP",
            actor="PTP_CommitmentTracker",
            action_summary=f"PTP #{ptp_id} fulfilled! Successfully recovered ₹{amount:,.2f} from {target['customer_name']}.",
            compliance_tag="PTP_HONORED",
            metadata={"ptp_id": ptp_id, "amount": amount, "status": "kept"},
            db_path=self.db_path
        )

        return {"success": True, "status": "kept", "amount_recovered": amount}

    def break_ptp(self, ptp_id: str, reason: str = "Promise deadline passed without settlement") -> Dict[str, Any]:
        """
        Marks Promise-to-Pay as BROKEN and triggers escalation.
        """
        all_ptp = database.get_all_ptp(self.db_path)
        target = next((r for r in all_ptp if r['ptp_id'] == ptp_id), None)
        if not target:
            return {"error": "PTP record not found"}

        database.update_ptp_status(ptp_id, PTPStatus.BROKEN, self.db_path)

        database.record_audit(
            event_id=target['event_id'],
            stage="PTP",
            actor="PTP_CommitmentTracker",
            action_summary=f"PTP #{ptp_id} BROKEN by {target['customer_name']}. Deadline expired. Escalating case.",
            compliance_tag="PTP_BREACHED",
            metadata={"ptp_id": ptp_id, "reason": reason, "status": "broken"},
            db_path=self.db_path
        )

        return {"success": True, "status": "broken", "escalated": True}
