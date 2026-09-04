"""
RecoverRx Unified Schemas & Enums
Defines standard data contracts across the entire revenue recovery pipeline.
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
import time
import uuid

class FailureArchetype(str, Enum):
    CARD_FAILURE = "card_failure"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    INVOICE_OVERDUE = "invoice_overdue"
    MANDATE_FAILURE = "mandate_failure"

class RootCauseCategory(str, Enum):
    HARD_DECLINE = "hard_decline"               # Expired card, stolen, account closed, invalid card
    SOFT_DECLINE = "soft_decline"               # Insufficient funds, temporary bank block
    TECHNICAL_DROP = "technical_drop"           # Gateway timeout, 3DS drop-off, network error
    CHECKOUT_FRICTION = "checkout_friction"     # OTP lag, price shock, address validation error, UX drop
    INVOICE_FIRST_TIME = "invoice_first_time"   # New late payment, simple oversight
    INVOICE_CHRONIC = "invoice_chronic"         # Repeated late payer, cash-flow strain
    INVOICE_DISPUTED = "invoice_disputed"       # Billing dispute, PO mismatch, delivery contest
    MANDATE_BALANCE = "mandate_balance"         # Mandate debit bounced due to salary timing
    MANDATE_EXPIRED = "mandate_expired"         # Mandate max amount or validity expired

class ActionType(str, Enum):
    SMART_RETRY = "smart_retry"
    WHATSAPP_NUDGE = "whatsapp_nudge"
    DUNNING_EMAIL = "dunning_email"
    VOICE_AI_CALL = "voice_ai_call"
    UPI_PAYMENT_LINK = "upi_payment_link"
    HUMAN_ESCALATION = "human_escalation"
    SUPPRESS_ACTION = "suppress_action"

class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    QUEUED_OFF_HOURS = "queued_off_hours"
    SUPPRESSED_DND = "suppressed_dnd"
    SUPPRESSED_MAX_TOUCHES = "suppressed_max_touches"
    SUPPRESSED_COOLOFF = "suppressed_cooloff"
    SUPPRESSED_OPT_OUT = "suppressed_opt_out"
    SUPPRESSED_DISPUTE = "suppressed_dispute"

class PTPStatus(str, Enum):
    PENDING = "pending"
    KEPT = "kept"
    BROKEN = "broken"
    CANCELLED = "cancelled"

@dataclass
class RevenueAtRiskEvent:
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    customer_id: str = ""
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""
    amount: float = 0.0
    currency: str = "INR"
    archetype: FailureArchetype = FailureArchetype.CARD_FAILURE
    gateway: str = "Razorpay" # Razorpay, Stripe, PayU, In-House ERP
    raw_failure_code: str = ""
    raw_failure_reason: str = ""
    channel: str = "online_checkout" # web, mobile_app, recurring_engine, b2b_portal
    is_holdout: bool = False # 10% control group
    touches_count: int = 0
    last_touch_timestamp: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    customer_history: Dict[str, Any] = field(default_factory=dict)
    session_telemetry: Dict[str, Any] = field(default_factory=dict)
    status: str = "detected" # detected, diagnosed, actioned, recovered, unrecoverable, holdout

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['archetype'] = self.archetype.value
        return data

@dataclass
class DiagnosisResult:
    diagnosis_id: str = field(default_factory=lambda: f"diag_{uuid.uuid4().hex[:10]}")
    event_id: str = ""
    category: RootCauseCategory = RootCauseCategory.SOFT_DECLINE
    confidence_score: float = 0.95
    rationale: str = ""
    actionable_intent: str = ""
    is_recoverable: bool = True
    suggested_action: ActionType = ActionType.SMART_RETRY
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['category'] = self.category.value
        data['suggested_action'] = self.suggested_action.value
        return data

@dataclass
class PolicyDecision:
    decision_id: str = field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:10]}")
    event_id: str = ""
    action_type: ActionType = ActionType.SMART_RETRY
    compliance_status: ComplianceStatus = ComplianceStatus.COMPLIANT
    rule_applied: str = ""
    reasoning: str = ""
    requires_human_approval: bool = False
    scheduled_timestamp: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['action_type'] = self.action_type.value
        data['compliance_status'] = self.compliance_status.value
        return data

@dataclass
class BoundedExecution:
    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:10]}")
    event_id: str = ""
    action_type: ActionType = ActionType.SMART_RETRY
    channel: str = "direct_api"
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "executed" # executed, queued, failed, simulated
    response_data: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['action_type'] = self.action_type.value
        return data

@dataclass
class PromiseToPay:
    ptp_id: str = field(default_factory=lambda: f"ptp_{uuid.uuid4().hex[:10]}")
    event_id: str = ""
    customer_id: str = ""
    customer_name: str = ""
    amount: float = 0.0
    currency: str = "INR"
    promised_timestamp: float = 0.0 # deadline
    status: PTPStatus = PTPStatus.PENDING
    resolution_timestamp: Optional[float] = None
    credibility_score: float = 0.85 # historical PTP credibility
    notes: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['status'] = self.status.value
        return data

@dataclass
class AuditRecord:
    audit_id: str = field(default_factory=lambda: f"aud_{uuid.uuid4().hex[:10]}")
    event_id: str = ""
    stage: str = "" # DETECT, DIAGNOSE, DECIDE, ACT, VERIFY, PTP
    actor: str = "RecoverRx_Agent"
    action_summary: str = ""
    compliance_tag: str = "RBI_TRAI_COMPLIANT"
    previous_hash: str = "00000000000000000000000000000000"
    current_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
