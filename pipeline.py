"""
RecoverRx Master Orchestrator Pipeline
Connects the 6-stage closed loop: Detect -> Diagnose -> Decide -> Act -> Verify -> Audit.
"""
import time
import random
from typing import Dict, Any, Optional
from schemas import (
    RevenueAtRiskEvent, DiagnosisResult, PolicyDecision,
    BoundedExecution, FailureArchetype, ActionType, PTPStatus
)
import database
from engines.detection import IngestionEngine
from engines.diagnosis import DiagnosisEngine
from engines.policy import PolicyEngine
from engines.execution import ExecutionEngine
from engines.ptp import PTPTracker
from engines.verification import VerificationEngine
from engines.compliance import ComplianceEngine

class RecoverRxPipeline:
    def __init__(self, db_path: str = database.DB_PATH):
        self.db_path = db_path
        self.detection = IngestionEngine(db_path)
        self.diagnosis = DiagnosisEngine(db_path)
        self.policy = PolicyEngine(db_path)
        self.execution = ExecutionEngine(db_path)
        self.ptp = PTPTracker(db_path)
        self.verification = VerificationEngine(db_path)
        self.compliance = ComplianceEngine(db_path)

    def run_pipeline_for_event(self, event: RevenueAtRiskEvent) -> Dict[str, Any]:
        """
        Executes the full closed loop for an incoming Revenue-at-Risk event.
        """
        trace = {
            "event": event.to_dict(),
            "stage_1_detect": {
                "event_id": event.event_id,
                "amount": event.amount,
                "archetype": event.archetype.value,
                "is_holdout": event.is_holdout,
                "status": event.status
            },
            "stage_2_diagnose": None,
            "stage_3_decide": None,
            "stage_4_act": None,
            "stage_5_ptp": None
        }

        # If allocated to the Holdout Control group, preserve without intervention
        if event.is_holdout:
            database.update_event_status(event.event_id, "holdout", self.db_path)
            return trace

        # Stage 2: Diagnose
        diag_res = self.diagnosis.diagnose(event)
        trace["stage_2_diagnose"] = diag_res.to_dict()
        database.update_event_status(event.event_id, "diagnosed", self.db_path)

        # Stage 3: Decide (Policy & Compliance)
        decision = self.policy.decide(event, diag_res)
        trace["stage_3_decide"] = decision.to_dict()

        # Stage 4: Act (Bounded Execution)
        exec_res = self.execution.execute(event, decision)
        if exec_res:
            trace["stage_4_act"] = exec_res.to_dict()
            database.update_event_status(event.event_id, "actioned", self.db_path)

            # Stage 5: If Voice AI call was simulated and customer promised payment, auto-register PTP
            if exec_res.action_type == ActionType.VOICE_AI_CALL and exec_res.payload.get("ptp_detected"):
                days_ahead = exec_res.payload.get("ptp_promised_relative_days", 3)
                deadline = time.time() + (days_ahead * 86400)
                ptp_rec = self.ptp.register_ptp(
                    event_id=event.event_id,
                    customer_id=event.customer_id,
                    customer_name=event.customer_name,
                    amount=event.amount,
                    promised_timestamp=deadline,
                    notes="Automated PTP captured from Hinglish Voice AI conversation ('Friday ko payment kar dunga')"
                )
                trace["stage_5_ptp"] = ptp_rec.to_dict()

        return trace

    def simulate_scenario(self, scenario_type: str) -> Dict[str, Any]:
        """
        Synthesizes a realistic event across the 5 archetypes and runs the pipeline.
        """
        now = time.time()
        rand_id = random.randint(1000, 9999)

        if scenario_type == "card_soft_decline":
            payload = {
                "event": "payment.failed",
                "payload": {
                    "payment": {
                        "entity": {
                            "customer_id": f"cust_hdfc_{rand_id}",
                            "name": "Rohan Verma",
                            "contact": "+919820123456",
                            "email": "rohan.verma@gmail.com",
                            "amount": 349900, # ₹3,499.00
                            "currency": "INR",
                            "error_code": "BAD_REQUEST_ERROR",
                            "failure_reason": "Bank declined: Insufficient funds in debit account (Soft Decline)",
                            "notes": {"plan": "Annual SaaS Pro"}
                        }
                    }
                }
            }
            event = self.detection.ingest_razorpay_event(payload)

        elif scenario_type == "card_hard_decline":
            payload = {
                "event": "payment.failed",
                "payload": {
                    "payment": {
                        "entity": {
                            "customer_id": f"cust_axis_{rand_id}",
                            "name": "Pooja Sharma",
                            "contact": "+919871100223",
                            "email": "pooja.sharma@yahoo.com",
                            "amount": 199900, # ₹1,999.00
                            "currency": "INR",
                            "error_code": "CARD_EXPIRED",
                            "failure_reason": "Card token rejected: Card validity period has expired",
                            "notes": {"plan": "Monthly Cloud Backup"}
                        }
                    }
                }
            }
            event = self.detection.ingest_razorpay_event(payload)

        elif scenario_type == "checkout_abandonment":
            session = {
                "customer_id": f"cart_{rand_id}",
                "customer_name": "Aman Gupta",
                "phone": "+919810998877",
                "email": "aman.gupta@outlook.com",
                "cart_total": 4599.0,
                "drop_step": "OTP_DELIVERY_LAG",
                "drop_reason": "SMS OTP delivery delayed by telecom provider for 92 seconds. Buyer closed checkout tab.",
                "items": ["Ergonomic Mechanical Keyboard + Deskmat Bundle"]
            }
            event = self.detection.ingest_checkout_telemetry(session)

        elif scenario_type == "subscription_renewal":
            payload = {
                "event": "subscription.halted",
                "payload": {
                    "subscription": {
                        "entity": {
                            "customer_id": f"sub_user_{rand_id}",
                            "name": "Vikram Malhotra",
                            "contact": "+919940112233",
                            "email": "vikram.m@techcorp.in",
                            "amount": 299900, # ₹2,999.00
                            "currency": "INR",
                            "error_code": "ISSUER_DOWN",
                            "failure_reason": "State Bank of India core banking system downtime during batch run",
                            "invoice_id": f"inv_sub_{rand_id}"
                        }
                    }
                }
            }
            event = self.detection.ingest_razorpay_event(payload)

        elif scenario_type == "invoice_disputed":
            invoice = {
                "customer_id": f"corp_indus_{rand_id}",
                "company_name": "Indus Logistics Pvt Ltd",
                "invoice_no": f"INV-2026-{rand_id}",
                "outstanding_amount": 185000.0,
                "days_overdue": 24,
                "has_dispute": True,
                "dispute_notes": "Line item 4 GST calculation discrepancy contested by Accounts Payable.",
                "finance_phone": "+919822334455",
                "finance_email": "accounts@induslogistics.com",
                "previous_invoices": 8,
                "avg_delay_days": 10
            }
            event = self.detection.ingest_erp_invoice(invoice)

        elif scenario_type == "invoice_chronic_high_value":
            invoice = {
                "customer_id": f"corp_apex_{rand_id}",
                "company_name": "Apex Digital Media Corp",
                "invoice_no": f"INV-2026-{rand_id}",
                "outstanding_amount": 340000.0,
                "days_overdue": 42,
                "has_dispute": False,
                "finance_phone": "+919833445566",
                "finance_email": "billing@apexmedia.in",
                "previous_invoices": 12,
                "avg_delay_days": 35 # Chronic late
            }
            event = self.detection.ingest_erp_invoice(invoice)

        elif scenario_type == "mandate_failure":
            payload = {
                "event": "mandate.failed",
                "payload": {
                    "payment": {
                        "entity": {
                            "customer_id": f"nach_user_{rand_id}",
                            "name": "Sunita Rao",
                            "contact": "+919845012345",
                            "email": "sunita.rao@gmail.com",
                            "amount": 750000, # ₹7,500.00
                            "currency": "INR",
                            "error_code": "NPCI_E01_INSUFFICIENT_BALANCE",
                            "failure_reason": "UPI Autopay mandate debit bounce: Insufficient balance before monthly salary date",
                            "token": {"auth_type": "upi_autopay", "vpa": "sunita@okhdfcbank"}
                        }
                    }
                }
            }
            event = self.detection.ingest_razorpay_event(payload)

        else: # Generic card
            payload = {
                "event": "payment.failed",
                "payload": {
                    "payment": {
                        "entity": {
                            "customer_id": f"cust_gen_{rand_id}",
                            "name": "Karan Singhania",
                            "contact": "+919988776655",
                            "email": "karan.s@gmail.com",
                            "amount": 149900,
                            "currency": "INR",
                            "error_code": "3DS_TIMEOUT",
                            "failure_reason": "User dropped out during 3D Secure verification step"
                        }
                    }
                }
            }
            event = self.detection.ingest_razorpay_event(payload)

        return self.run_pipeline_for_event(event)
