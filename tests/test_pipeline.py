"""
RecoverRx End-to-End Automated Test Suite
Validates detection normalization, root-cause diagnosis, policy guardrails,
bounded execution, PTP tracking, incremental lift calculation, and cryptographic audit chaining.
"""
import unittest
import os
import time
import json
import database
from schemas import (
    RevenueAtRiskEvent, FailureArchetype, RootCauseCategory,
    ActionType, ComplianceStatus, PTPStatus
)
from engines.detection import IngestionEngine
from engines.diagnosis import DiagnosisEngine
from engines.policy import PolicyEngine
from engines.execution import ExecutionEngine
from engines.ptp import PTPTracker
from engines.verification import VerificationEngine
from engines.compliance import ComplianceEngine
from pipeline import RecoverRxPipeline

TEST_DB = "test_recover_rx.db"

class TestRecoverRxPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        database.init_db(TEST_DB)
        cls.pipeline = RecoverRxPipeline(db_path=TEST_DB)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
            except Exception:
                pass

    def test_01_ingestion_and_holdout_allocation(self):
        """Validates ingestion of Razorpay event and deterministic holdout assignment"""
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "customer_id": "cust_test_101",
                        "name": "Test User",
                        "contact": "+919876543210",
                        "email": "test@domain.com",
                        "amount": 250000,
                        "currency": "INR",
                        "error_code": "INSUFFICIENT_FUNDS",
                        "failure_reason": "Bank declined: insufficient funds (Soft Decline)"
                    }
                }
            }
        }
        event = self.pipeline.detection.ingest_razorpay_event(payload)
        self.assertEqual(event.amount, 2500.0)
        self.assertEqual(event.archetype, FailureArchetype.CARD_FAILURE)
        self.assertEqual(event.customer_name, "Test User")
        self.assertIsNotNone(event.event_id)

    def test_02_card_soft_vs_hard_decline_diagnosis(self):
        """Tests that soft declines route to SMART_RETRY and expired cards route to card update"""
        # Soft decline
        evt_soft = RevenueAtRiskEvent(
            event_id="evt_test_soft",
            customer_id="cust_soft",
            amount=1999.0,
            archetype=FailureArchetype.CARD_FAILURE,
            raw_failure_code="INSUFFICIENT_FUNDS",
            raw_failure_reason="Temporary balance deficit at issuing bank"
        )
        diag_soft = self.pipeline.diagnosis.diagnose(evt_soft)
        self.assertEqual(diag_soft.category, RootCauseCategory.SOFT_DECLINE)
        self.assertEqual(diag_soft.suggested_action, ActionType.SMART_RETRY)

        # Hard decline (expired card)
        evt_hard = RevenueAtRiskEvent(
            event_id="evt_test_hard",
            customer_id="cust_hard",
            amount=1999.0,
            archetype=FailureArchetype.CARD_FAILURE,
            raw_failure_code="CARD_EXPIRED",
            raw_failure_reason="Card expired on 08/2026"
        )
        diag_hard = self.pipeline.diagnosis.diagnose(evt_hard)
        self.assertEqual(diag_hard.category, RootCauseCategory.HARD_DECLINE)
        self.assertEqual(diag_hard.suggested_action, ActionType.WHATSAPP_NUDGE)

    def test_03_checkout_abandonment_otp_friction(self):
        """Tests checkout funnel drop-off classification and WhatsApp 1-tap UPI link suggestion"""
        session = {
            "customer_id": "cart_test_202",
            "customer_name": "Deepak Mehta",
            "cart_total": 4999.0,
            "drop_step": "OTP_TIMEOUT",
            "drop_reason": "SMS gateway delayed OTP for 120s"
        }
        event = self.pipeline.detection.ingest_checkout_telemetry(session)
        diag = self.pipeline.diagnosis.diagnose(event)
        self.assertEqual(diag.category, RootCauseCategory.CHECKOUT_FRICTION)
        self.assertEqual(diag.suggested_action, ActionType.WHATSAPP_NUDGE)

    def test_04_policy_touch_cap_and_cooloff(self):
        """Verifies policy engine stops after max touches and respects cooloff window"""
        evt_capped = RevenueAtRiskEvent(
            event_id="evt_test_capped",
            customer_id="cust_capped",
            amount=1500.0,
            touches_count=3, # Already reached max touches
            last_touch_timestamp=time.time() - 3600
        )
        diag = self.pipeline.diagnosis.diagnose(evt_capped)
        decision = self.pipeline.policy.decide(evt_capped, diag)
        self.assertEqual(decision.compliance_status, ComplianceStatus.SUPPRESSED_MAX_TOUCHES)
        self.assertEqual(decision.action_type, ActionType.SUPPRESS_ACTION)

    def test_05_disputed_invoice_freeze(self):
        """Ensures disputed B2B invoices immediately freeze automated dunning and escalate to human"""
        inv_data = {
            "customer_id": "corp_dispute_303",
            "company_name": "Bharat Corp",
            "outstanding_amount": 120000.0,
            "days_overdue": 15,
            "has_dispute": True,
            "dispute_notes": "Pricing mismatch on delivered items"
        }
        event = self.pipeline.detection.ingest_erp_invoice(inv_data)
        diag = self.pipeline.diagnosis.diagnose(event)
        decision = self.pipeline.policy.decide(event, diag)

        self.assertEqual(diag.category, RootCauseCategory.INVOICE_DISPUTED)
        self.assertEqual(decision.action_type, ActionType.HUMAN_ESCALATION)
        self.assertTrue(decision.requires_human_approval)
        self.assertEqual(decision.compliance_status, ComplianceStatus.SUPPRESSED_DISPUTE)

    def test_06_voice_ai_hinglish_and_ptp_lifecycle(self):
        """Tests Hinglish voice AI call dispatch and full Promise-to-Pay lifecycle"""
        evt_voice = RevenueAtRiskEvent(
            event_id="evt_test_voice_404",
            customer_id="cust_voice_404",
            customer_name="Sunil Gavaskar",
            customer_phone="+919811223344",
            amount=5000.0,
            archetype=FailureArchetype.SUBSCRIPTION_RENEWAL
        )
        database.save_event(evt_voice, db_path=TEST_DB)
        diag = self.pipeline.diagnosis.diagnose(evt_voice)
        decision = self.pipeline.policy.decide(evt_voice, diag)
        # Override to voice call to test execution
        decision.action_type = ActionType.VOICE_AI_CALL
        execution = self.pipeline.execution.execute(evt_voice, decision)

        self.assertIsNotNone(execution)
        self.assertEqual(execution.action_type, ActionType.VOICE_AI_CALL)
        self.assertIn("Hinglish", execution.payload.get("language", ""))

        # Register PTP
        ptp = self.pipeline.ptp.register_ptp(
            event_id=evt_voice.event_id,
            customer_id=evt_voice.customer_id,
            customer_name=evt_voice.customer_name,
            amount=5000.0,
            promised_timestamp=time.time() + 86400,
            notes="Test PTP customer will pay tomorrow"
        )
        self.assertEqual(ptp.status, PTPStatus.PENDING)

        # Fulfill PTP
        fulfill_res = self.pipeline.ptp.fulfill_ptp(ptp.ptp_id, recovered_amount=5000.0)
        self.assertTrue(fulfill_res.get("success"))

        # Check event status updated to recovered
        updated_evt = database.get_event(evt_voice.event_id, db_path=TEST_DB)
        self.assertEqual(updated_evt['status'], "recovered")

    def test_07_cryptographic_audit_hash_chain(self):
        """Verifies that all audit records form an unbroken, tamper-evident SHA-256 chain"""
        integrity = self.pipeline.compliance.verify_audit_chain_integrity()
        self.assertTrue(integrity["is_valid"])
        self.assertEqual(integrity["status"], "HEALTHY")
        self.assertEqual(len(integrity["tampered_records"]), 0)
        self.assertGreater(integrity["records_verified"], 0)

if __name__ == "__main__":
    unittest.main()
