"""
RecoverRx Seed Data Generator
Pre-populates the database with realistic historical scenarios across all 5 revenue leakage archetypes,
active PTP commitments, holdout control group records, and verified recoveries.
"""
import time
import random
import database
from schemas import (
    RevenueAtRiskEvent, DiagnosisResult, PolicyDecision,
    BoundedExecution, PromiseToPay, FailureArchetype,
    RootCauseCategory, ActionType, ComplianceStatus, PTPStatus
)

def seed_database(db_path: str = database.DB_PATH):
    database.init_db(db_path)
    now = time.time()
    day = 86400

    # Clean existing data if desired (optional)
    conn = database.get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM events")
    if cursor.fetchone()['cnt'] > 0:
        conn.close()
        print("Database already seeded with historical records.")
        return
    conn.close()

    print("Seeding RecoverRx database with 15 rich realistic incidents...")

    incidents_spec = [
        # 1. Card Soft Decline -> Smart Retry -> Recovered
        {
            "id": "evt_card_soft_01",
            "name": "Rahul Verma", "phone": "+919820123456", "email": "rahul.verma@fintech.in",
            "amount": 4999.0, "archetype": FailureArchetype.CARD_FAILURE, "gateway": "Razorpay",
            "code": "INSUFFICIENT_FUNDS", "reason": "Issuing bank declined: temporary balance deficit (Soft Decline)",
            "is_holdout": False, "status": "recovered", "diag_cat": RootCauseCategory.SOFT_DECLINE,
            "action": ActionType.SMART_RETRY, "rule": "SMART_RETRY_POST_SALARY_CYCLE",
            "recovered": True, "created_offset": 3 * day
        },
        # 2. Card Expired -> WhatsApp Nudge -> Recovered
        {
            "id": "evt_card_exp_02",
            "name": "Pooja Sharma", "phone": "+919871100223", "email": "pooja.sharma@yahoo.com",
            "amount": 2499.0, "archetype": FailureArchetype.CARD_FAILURE, "gateway": "Razorpay",
            "code": "CARD_EXPIRED", "reason": "Acquirer rejected: Card expiry 08/26 reached",
            "is_holdout": False, "status": "recovered", "diag_cat": RootCauseCategory.HARD_DECLINE,
            "action": ActionType.WHATSAPP_NUDGE, "rule": "POLICY_LEAST_INTRUSIVE_HIERARCHY",
            "recovered": True, "created_offset": 2 * day
        },
        # 3. Checkout Drop (OTP Lag) -> WhatsApp 1-tap UPI -> Recovered
        {
            "id": "evt_cart_otp_03",
            "name": "Aman Gupta", "phone": "+919810998877", "email": "aman.gupta@outlook.com",
            "amount": 6299.0, "archetype": FailureArchetype.CHECKOUT_ABANDONMENT, "gateway": "Checkout_Funnel",
            "code": "OTP_DELIVERY_LAG", "reason": "Buyer waited 95s for SMS OTP then abandoned checkout session",
            "is_holdout": False, "status": "recovered", "diag_cat": RootCauseCategory.CHECKOUT_FRICTION,
            "action": ActionType.WHATSAPP_NUDGE, "rule": "CHECKOUT_CART_1TAP_UPI_POLICY",
            "recovered": True, "created_offset": 1.5 * day
        },
        # 4. Checkout Drop -> In Progress (Actioned)
        {
            "id": "evt_cart_step_04",
            "name": "Ritu Singhal", "phone": "+919899112233", "email": "ritu.s@gmail.com",
            "amount": 3890.0, "archetype": FailureArchetype.CHECKOUT_ABANDONMENT, "gateway": "Checkout_Funnel",
            "code": "ADDRESS_VALIDATION_ERROR", "reason": "Pincode mismatch during express delivery form step",
            "is_holdout": False, "status": "actioned", "diag_cat": RootCauseCategory.CHECKOUT_FRICTION,
            "action": ActionType.WHATSAPP_NUDGE, "rule": "POLICY_LEAST_INTRUSIVE_HIERARCHY",
            "recovered": False, "created_offset": 0.5 * day
        },
        # 5. Subscription Renewal Fail -> Dunning Email -> Recovered
        {
            "id": "evt_sub_fail_05",
            "name": "Vikram Malhotra", "phone": "+919940112233", "email": "vikram.m@techcorp.in",
            "amount": 12999.0, "archetype": FailureArchetype.SUBSCRIPTION_RENEWAL, "gateway": "Razorpay",
            "code": "ISSUER_UNAVAILABLE", "reason": "Core banking system maintenance window timeout during recurring debit",
            "is_holdout": False, "status": "recovered", "diag_cat": RootCauseCategory.SOFT_DECLINE,
            "action": ActionType.DUNNING_EMAIL, "rule": "SUBSCRIPTION_GRACE_PERIOD_DUNNING",
            "recovered": True, "created_offset": 4 * day
        },
        # 6. Subscription Renewal Fail -> Hinglish Voice AI -> PTP Registered
        {
            "id": "evt_sub_voice_06",
            "name": "Suresh Raina", "phone": "+919833441122", "email": "suresh.raina@sportslab.in",
            "amount": 8499.0, "archetype": FailureArchetype.SUBSCRIPTION_RENEWAL, "gateway": "Razorpay",
            "code": "DAILY_LIMIT_EXCEEDED", "reason": "Card daily online transaction limit exceeded",
            "is_holdout": False, "status": "actioned", "diag_cat": RootCauseCategory.SOFT_DECLINE,
            "action": ActionType.VOICE_AI_CALL, "rule": "VOICE_AI_VERNACULAR_OUTREACH",
            "recovered": False, "created_offset": 0.8 * day,
            "ptp": {"days": 2, "status": PTPStatus.PENDING, "note": "Promised payment post salary credit"}
        },
        # 7. B2B Overdue Invoice -> Disputed -> Human Escalation
        {
            "id": "evt_b2b_disp_07",
            "name": "Indus Logistics Pvt Ltd", "phone": "+919822334455", "email": "accounts@induslogistics.com",
            "amount": 185000.0, "archetype": FailureArchetype.INVOICE_OVERDUE, "gateway": "ERP_Receivables",
            "code": "DAYS_OVERDUE_28_DISPUTED", "reason": "Client opened line item GST mismatch dispute on PO #9021",
            "is_holdout": False, "status": "actioned", "diag_cat": RootCauseCategory.INVOICE_DISPUTED,
            "action": ActionType.HUMAN_ESCALATION, "rule": "RBI_FAIR_PRACTICES_DISPUTE_FREEZE",
            "recovered": False, "created_offset": 5 * day
        },
        # 8. B2B Overdue Invoice -> First Time Late -> Email Reminder -> Recovered
        {
            "id": "evt_b2b_norm_08",
            "name": "Zenith Media Works", "phone": "+919811223344", "email": "finance@zenithmedia.com",
            "amount": 65000.0, "archetype": FailureArchetype.INVOICE_OVERDUE, "gateway": "ERP_Receivables",
            "code": "DAYS_OVERDUE_12", "reason": "Net-30 invoice is 12 days past due. Internal finance approval delay",
            "is_holdout": False, "status": "recovered", "diag_cat": RootCauseCategory.INVOICE_FIRST_TIME,
            "action": ActionType.DUNNING_EMAIL, "rule": "TIERED_INVOICE_CHASER",
            "recovered": True, "created_offset": 6 * day
        },
        # 9. B2B Chronic Late -> High Value -> Voice Call -> PTP Kept & Recovered
        {
            "id": "evt_b2b_chron_09",
            "name": "Apex Digital Corp", "phone": "+919844556677", "email": "billing@apexdigital.in",
            "amount": 240000.0, "archetype": FailureArchetype.INVOICE_OVERDUE, "gateway": "ERP_Receivables",
            "code": "DAYS_OVERDUE_45", "reason": "Chronic late payer (>35 days avg). Unresponsive to templated emails",
            "is_holdout": False, "status": "recovered", "diag_cat": RootCauseCategory.INVOICE_CHRONIC,
            "action": ActionType.VOICE_AI_CALL, "rule": "CHRONIC_ACCOUNT_EXECUTIVE_VOICE",
            "recovered": True, "created_offset": 7 * day,
            "ptp": {"days": -2, "status": PTPStatus.KEPT, "note": "CFO promised payment by 2nd of month. Kept."}
        },
        # 10. UPI Autopay Mandate Bounce -> Smart Retry -> Recovered
        {
            "id": "evt_nach_bal_10",
            "name": "Sunita Rao", "phone": "+919845012345", "email": "sunita.rao@gmail.com",
            "amount": 7500.0, "archetype": FailureArchetype.MANDATE_FAILURE, "gateway": "Razorpay",
            "code": "NPCI_E01_INSUFFICIENT_BALANCE", "reason": "UPI Autopay mandate debit bounce: Insufficient balance before salary date",
            "is_holdout": False, "status": "recovered", "diag_cat": RootCauseCategory.MANDATE_BALANCE,
            "action": ActionType.SMART_RETRY, "rule": "MANDATE_NPCI_RETRY_ALIGNMENT",
            "recovered": True, "created_offset": 3 * day
        },
        # 11. UPI Mandate Revoked -> WhatsApp Re-mandate -> Actioned
        {
            "id": "evt_nach_rev_11",
            "name": "Kavita Reddy", "phone": "+919870123987", "email": "kavita.r@gmail.com",
            "amount": 4999.0, "archetype": FailureArchetype.MANDATE_FAILURE, "gateway": "Razorpay",
            "code": "MANDATE_REVOKED_BY_USER", "reason": "User paused or cancelled recurring mandate in GPay app",
            "is_holdout": False, "status": "actioned", "diag_cat": RootCauseCategory.MANDATE_EXPIRED,
            "action": ActionType.WHATSAPP_NUDGE, "rule": "POLICY_LEAST_INTRUSIVE_HIERARCHY",
            "recovered": False, "created_offset": 1 * day
        },
        # 12. HOLDOUT CONTROL 1 (Card Soft Decline) -> Naturally unrecovered
        {
            "id": "evt_holdout_ctrl_12",
            "name": "Devendra Joshi", "phone": "+919821001122", "email": "dev.joshi@gmail.com",
            "amount": 3200.0, "archetype": FailureArchetype.CARD_FAILURE, "gateway": "Razorpay",
            "code": "INSUFFICIENT_FUNDS", "reason": "Issuing bank declined: insufficient balance",
            "is_holdout": True, "status": "holdout", "diag_cat": RootCauseCategory.SOFT_DECLINE,
            "action": ActionType.SUPPRESS_ACTION, "rule": "HOLDOUT_CONTROL_GROUP_PRESERVATION",
            "recovered": False, "created_offset": 5 * day
        },
        # 13. HOLDOUT CONTROL 2 (Checkout Abandoned) -> Naturally recovered (organic)
        {
            "id": "evt_holdout_ctrl_13",
            "name": "Sneha Iyer", "phone": "+919833009988", "email": "sneha.iyer@gmail.com",
            "amount": 2199.0, "archetype": FailureArchetype.CHECKOUT_ABANDONMENT, "gateway": "Checkout_Funnel",
            "code": "OTP_DELIVERY_LAG", "reason": "SMS OTP delayed. Customer came back independently next day.",
            "is_holdout": True, "status": "recovered", "diag_cat": RootCauseCategory.CHECKOUT_FRICTION,
            "action": ActionType.SUPPRESS_ACTION, "rule": "HOLDOUT_CONTROL_GROUP_PRESERVATION",
            "recovered": True, "created_offset": 4 * day
        },
        # 14. HOLDOUT CONTROL 3 (B2B Invoice) -> Naturally unrecovered
        {
            "id": "evt_holdout_ctrl_14",
            "name": "Delta Infotech", "phone": "+919811445566", "email": "finance@deltainfo.com",
            "amount": 95000.0, "archetype": FailureArchetype.INVOICE_OVERDUE, "gateway": "ERP_Receivables",
            "code": "DAYS_OVERDUE_30", "reason": "Net-30 overdue with zero intervention",
            "is_holdout": True, "status": "holdout", "diag_cat": RootCauseCategory.INVOICE_FIRST_TIME,
            "action": ActionType.SUPPRESS_ACTION, "rule": "HOLDOUT_CONTROL_GROUP_PRESERVATION",
            "recovered": False, "created_offset": 6 * day
        },
        # 15. DND Suppressed Case (Compliant suppression)
        {
            "id": "evt_dnd_suppress_15",
            "name": "Arjun Kapoor", "phone": "+919819998877", "email": "arjun.k@gmail.com",
            "amount": 5400.0, "archetype": FailureArchetype.CARD_FAILURE, "gateway": "Razorpay",
            "code": "CARD_EXPIRED", "reason": "Card expired. Number is TRAI NDNC registered.",
            "is_holdout": False, "status": "actioned", "diag_cat": RootCauseCategory.HARD_DECLINE,
            "action": ActionType.DUNNING_EMAIL, "rule": "TRAI_DND_TELECOM_REGULATION",
            "recovered": False, "created_offset": 0.3 * day,
            "dnd_active": True
        }
    ]

    for spec in incidents_spec:
        created_time = now - spec["created_offset"]

        # 1. Event
        event = RevenueAtRiskEvent(
            event_id=spec["id"],
            customer_id=f"cust_{spec['id'][:12]}",
            customer_name=spec["name"],
            customer_phone=spec["phone"],
            customer_email=spec["email"],
            amount=spec["amount"],
            currency="INR",
            archetype=spec["archetype"],
            gateway=spec["gateway"],
            raw_failure_code=spec["code"],
            raw_failure_reason=spec["reason"],
            channel="gateway_webhook",
            is_holdout=spec["is_holdout"],
            touches_count=0 if spec["is_holdout"] else 1,
            last_touch_timestamp=created_time if not spec["is_holdout"] else None,
            created_at=created_time,
            customer_history={"dnd_active": spec.get("dnd_active", False), "cart_items": ["Pro Software Subscription"]},
            session_telemetry={"gateway_ref": spec["id"]},
            status=spec["status"]
        )
        database.save_event(event, db_path)

        database.record_audit(
            event_id=event.event_id,
            stage="DETECT",
            actor="Ingestion_Engine",
            action_summary=f"Ingested {event.archetype.value} ₹{event.amount:,.2f} ({event.customer_name}). Holdout: {event.is_holdout}",
            compliance_tag="SIGNAL_VERIFIED",
            metadata={"source": event.gateway, "is_holdout": event.is_holdout},
            db_path=db_path
        )

        if not spec["is_holdout"]:
            # 2. Diagnosis
            diag = DiagnosisResult(
                diagnosis_id=f"diag_{spec['id'][4:]}",
                event_id=event.event_id,
                category=spec["diag_cat"],
                confidence_score=0.94,
                rationale=f"Diagnosed root cause for failure {spec['code']}. Recovery plan formulated.",
                actionable_intent="Execute least-intrusive compliant recovery channel.",
                is_recoverable=True,
                suggested_action=spec["action"],
                created_at=created_time + 10
            )
            database.save_diagnosis(diag, db_path)
            database.record_audit(
                event_id=event.event_id,
                stage="DIAGNOSE",
                actor="Diagnosis_LLMEngine",
                action_summary=f"Diagnosed as {diag.category.value}. Recommended: {diag.suggested_action.value}",
                compliance_tag="ROOT_CAUSE_CERTIFIED",
                metadata=diag.to_dict(),
                db_path=db_path
            )

            # 3. Decision
            dec = PolicyDecision(
                decision_id=f"dec_{spec['id'][4:]}",
                event_id=event.event_id,
                action_type=spec["action"],
                compliance_status=ComplianceStatus.COMPLIANT,
                rule_applied=spec["rule"],
                reasoning=f"Approved under policy rule {spec['rule']}.",
                requires_human_approval=(spec["action"] == ActionType.HUMAN_ESCALATION),
                scheduled_timestamp=created_time + 20,
                created_at=created_time + 20
            )
            database.save_decision(dec, db_path)
            database.record_audit(
                event_id=event.event_id,
                stage="DECIDE",
                actor="Policy_GovernanceEngine",
                action_summary=f"Decision: {dec.action_type.value} via rule {dec.rule_applied}",
                compliance_tag="POLICY_VERIFIED",
                metadata=dec.to_dict(),
                db_path=db_path
            )

            # 4. Execution
            exe = BoundedExecution(
                execution_id=f"exec_{spec['id'][4:]}",
                event_id=event.event_id,
                action_type=spec["action"],
                channel="omnichannel_dispatch",
                payload={"action": spec["action"].value, "amount": spec["amount"]},
                status="executed",
                response_data={"status": "delivered_or_routed"},
                created_at=created_time + 30
            )
            database.save_execution(exe, db_path)
            database.record_audit(
                event_id=event.event_id,
                stage="ACT",
                actor="Execution_BoundedDispatcher",
                action_summary=f"Dispatched {exe.action_type.value} on channel {exe.channel}",
                compliance_tag="BOUNDED_ACTION_EXECUTED",
                metadata=exe.to_dict(),
                db_path=db_path
            )

            # 5. PTP if configured
            if spec.get("ptp"):
                ptp_info = spec["ptp"]
                deadline = now + (ptp_info["days"] * day)
                ptp_rec = PromiseToPay(
                    ptp_id=f"ptp_{spec['id'][4:]}",
                    event_id=event.event_id,
                    customer_id=event.customer_id,
                    customer_name=event.customer_name,
                    amount=event.amount,
                    currency="INR",
                    promised_timestamp=deadline,
                    status=ptp_info["status"],
                    resolution_timestamp=(created_time + 2 * day) if ptp_info["status"] == PTPStatus.KEPT else None,
                    credibility_score=0.92 if ptp_info["status"] == PTPStatus.KEPT else 0.85,
                    notes=ptp_info["note"],
                    created_at=created_time + 40
                )
                database.save_ptp(ptp_rec, db_path)
                database.record_audit(
                    event_id=event.event_id,
                    stage="PTP",
                    actor="PTP_CommitmentTracker",
                    action_summary=f"PTP status: {ptp_rec.status.value} for ₹{ptp_rec.amount:,.2f}",
                    compliance_tag="PTP_TRACKED",
                    metadata=ptp_rec.to_dict(),
                    db_path=db_path
                )

        # 6. Verification / Recovery if marked recovered
        if spec["recovered"]:
            database.record_recovery(
                event_id=event.event_id,
                recovered_amount=event.amount,
                attribution_action_id=f"exec_{spec['id'][4:]}" if not spec["is_holdout"] else "organic_control",
                attribution_window_hours=24.0,
                db_path=db_path
            )
            database.record_audit(
                event_id=event.event_id,
                stage="VERIFY",
                actor="Verification_AttributionEngine",
                action_summary=f"Payment verified for ₹{event.amount:,.2f}. Holdout: {event.is_holdout}",
                compliance_tag="REVENUE_VERIFIED",
                metadata={"recovered_amount": event.amount, "is_holdout": event.is_holdout},
                db_path=db_path
            )

    print("Seeding complete! 15 historical incidents loaded with full audit trail.")

if __name__ == "__main__":
    seed_database()
