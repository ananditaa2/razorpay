"""
RecoverRx Database & Cryptographic Audit Ledger
Implements SQLite persistence with tamper-evident SHA-256 hash chaining for compliance.
"""
import sqlite3
import json
import hashlib
import time
from typing import Dict, Any, List, Optional
from schemas import (
    RevenueAtRiskEvent, DiagnosisResult, PolicyDecision,
    BoundedExecution, PromiseToPay, AuditRecord, PTPStatus
)

DB_PATH = "recover_rx.db"

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        customer_id TEXT,
        customer_name TEXT,
        customer_phone TEXT,
        customer_email TEXT,
        amount REAL,
        currency TEXT,
        archetype TEXT,
        gateway TEXT,
        raw_failure_code TEXT,
        raw_failure_reason TEXT,
        channel TEXT,
        is_holdout INTEGER,
        touches_count INTEGER,
        last_touch_timestamp REAL,
        created_at REAL,
        customer_history TEXT,
        session_telemetry TEXT,
        status TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diagnoses (
        diagnosis_id TEXT PRIMARY KEY,
        event_id TEXT,
        category TEXT,
        confidence_score REAL,
        rationale TEXT,
        actionable_intent TEXT,
        is_recoverable INTEGER,
        suggested_action TEXT,
        created_at REAL,
        FOREIGN KEY (event_id) REFERENCES events(event_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS decisions (
        decision_id TEXT PRIMARY KEY,
        event_id TEXT,
        action_type TEXT,
        compliance_status TEXT,
        rule_applied TEXT,
        reasoning TEXT,
        requires_human_approval INTEGER,
        scheduled_timestamp REAL,
        created_at REAL,
        FOREIGN KEY (event_id) REFERENCES events(event_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS executions (
        execution_id TEXT PRIMARY KEY,
        event_id TEXT,
        action_type TEXT,
        channel TEXT,
        payload TEXT,
        status TEXT,
        response_data TEXT,
        created_at REAL,
        FOREIGN KEY (event_id) REFERENCES events(event_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ptp_records (
        ptp_id TEXT PRIMARY KEY,
        event_id TEXT,
        customer_id TEXT,
        customer_name TEXT,
        amount REAL,
        currency TEXT,
        promised_timestamp REAL,
        status TEXT,
        resolution_timestamp REAL,
        credibility_score REAL,
        notes TEXT,
        created_at REAL,
        FOREIGN KEY (event_id) REFERENCES events(event_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS verifications (
        verification_id TEXT PRIMARY KEY,
        event_id TEXT,
        is_recovered INTEGER,
        recovered_amount REAL,
        attribution_action_id TEXT,
        attribution_window_hours REAL,
        recovered_timestamp REAL,
        created_at REAL,
        FOREIGN KEY (event_id) REFERENCES events(event_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        audit_id TEXT PRIMARY KEY,
        event_id TEXT,
        stage TEXT,
        actor TEXT,
        action_summary TEXT,
        compliance_tag TEXT,
        previous_hash TEXT,
        current_hash TEXT,
        metadata TEXT,
        created_at REAL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        description TEXT
    );
    """)

    # Seed default configuration
    default_settings = [
        ("max_touches", "3", "Maximum allowed outreach attempts per incident"),
        ("cooloff_hours", "24", "Minimum hours to wait between customer contacts"),
        ("holdout_rate", "0.10", "Proportion of events routed to holdout control group (10%)"),
        ("call_window_start_ist", "9", "TRAI compliant calling window start (09:00 IST)"),
        ("call_window_end_ist", "20", "TRAI compliant calling window end (20:00 IST)"),
        ("high_value_escalation_inr", "50000", "Amount threshold in INR requiring Human-in-the-Loop review"),
        ("gemini_api_key", "", "Optional Google Gemini API Key for dynamic LLM reasoning")
    ]
    for k, v, d in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)", (k, v, d))

    conn.commit()
    conn.close()

# ----------------- AUDIT HASH CHAINING -----------------

def get_last_audit_hash(conn: sqlite3.Connection) -> str:
    cursor = conn.cursor()
    cursor.execute("SELECT current_hash FROM audit_logs ORDER BY created_at DESC, rowid DESC LIMIT 1")
    row = cursor.fetchone()
    if row and row['current_hash']:
        return row['current_hash']
    return "0" * 64

def record_audit(event_id: str, stage: str, actor: str, action_summary: str, compliance_tag: str, metadata: Dict[str, Any], db_path: str = DB_PATH) -> AuditRecord:
    conn = get_connection(db_path)
    cursor = conn.cursor()

    prev_hash = get_last_audit_hash(conn)
    record = AuditRecord(
        event_id=event_id,
        stage=stage,
        actor=actor,
        action_summary=action_summary,
        compliance_tag=compliance_tag,
        previous_hash=prev_hash,
        metadata=metadata,
        created_at=time.time()
    )

    # Compute SHA-256 hash chaining
    raw_str = f"{record.audit_id}:{record.event_id}:{record.stage}:{record.actor}:{record.action_summary}:{record.compliance_tag}:{record.previous_hash}:{json.dumps(metadata, sort_keys=True)}:{record.created_at}"
    record.current_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

    cursor.execute("""
    INSERT INTO audit_logs (audit_id, event_id, stage, actor, action_summary, compliance_tag, previous_hash, current_hash, metadata, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.audit_id, record.event_id, record.stage, record.actor,
        record.action_summary, record.compliance_tag, record.previous_hash,
        record.current_hash, json.dumps(record.metadata), record.created_at
    ))

    conn.commit()
    conn.close()
    return record

# ----------------- EVENT OPERATIONS -----------------

def save_event(event: RevenueAtRiskEvent, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO events (
        event_id, customer_id, customer_name, customer_phone, customer_email,
        amount, currency, archetype, gateway, raw_failure_code, raw_failure_reason,
        channel, is_holdout, touches_count, last_touch_timestamp, created_at,
        customer_history, session_telemetry, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event.event_id, event.customer_id, event.customer_name, event.customer_phone,
        event.customer_email, event.amount, event.currency, event.archetype.value,
        event.gateway, event.raw_failure_code, event.raw_failure_reason, event.channel,
        1 if event.is_holdout else 0, event.touches_count, event.last_touch_timestamp,
        event.created_at, json.dumps(event.customer_history), json.dumps(event.session_telemetry),
        event.status
    ))
    conn.commit()
    conn.close()

def get_event(event_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d['customer_history'] = json.loads(d['customer_history'] or '{}')
    d['session_telemetry'] = json.loads(d['session_telemetry'] or '{}')
    d['is_holdout'] = bool(d['is_holdout'])
    return d

def update_event_status(event_id: str, status: str, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET status = ? WHERE event_id = ?", (status, event_id))
    conn.commit()
    conn.close()

def increment_event_touch(event_id: str, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE events
    SET touches_count = touches_count + 1, last_touch_timestamp = ?
    WHERE event_id = ?
    """, (time.time(), event_id))
    conn.commit()
    conn.close()

# ----------------- DIAGNOSIS OPERATIONS -----------------

def save_diagnosis(diagnosis: DiagnosisResult, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO diagnoses (
        diagnosis_id, event_id, category, confidence_score, rationale,
        actionable_intent, is_recoverable, suggested_action, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        diagnosis.diagnosis_id, diagnosis.event_id, diagnosis.category.value,
        diagnosis.confidence_score, diagnosis.rationale, diagnosis.actionable_intent,
        1 if diagnosis.is_recoverable else 0, diagnosis.suggested_action.value, diagnosis.created_at
    ))
    conn.commit()
    conn.close()

def get_diagnosis(event_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diagnoses WHERE event_id = ? ORDER BY created_at DESC LIMIT 1", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d['is_recoverable'] = bool(d['is_recoverable'])
    return d

# ----------------- DECISION OPERATIONS -----------------

def save_decision(decision: PolicyDecision, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO decisions (
        decision_id, event_id, action_type, compliance_status, rule_applied,
        reasoning, requires_human_approval, scheduled_timestamp, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        decision.decision_id, decision.event_id, decision.action_type.value,
        decision.compliance_status.value, decision.rule_applied, decision.reasoning,
        1 if decision.requires_human_approval else 0, decision.scheduled_timestamp, decision.created_at
    ))
    conn.commit()
    conn.close()

def get_decision(event_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM decisions WHERE event_id = ? ORDER BY created_at DESC LIMIT 1", (event_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d['requires_human_approval'] = bool(d['requires_human_approval'])
    return d

# ----------------- EXECUTION OPERATIONS -----------------

def save_execution(execution: BoundedExecution, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO executions (
        execution_id, event_id, action_type, channel, payload, status, response_data, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        execution.execution_id, execution.event_id, execution.action_type.value,
        execution.channel, json.dumps(execution.payload), execution.status,
        json.dumps(execution.response_data), execution.created_at
    ))
    conn.commit()
    conn.close()

def get_executions(event_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM executions WHERE event_id = ? ORDER BY created_at ASC", (event_id,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['payload'] = json.loads(d['payload'] or '{}')
        d['response_data'] = json.loads(d['response_data'] or '{}')
        results.append(d)
    return results

# ----------------- PROMISE TO PAY OPERATIONS -----------------

def save_ptp(ptp: PromiseToPay, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO ptp_records (
        ptp_id, event_id, customer_id, customer_name, amount, currency,
        promised_timestamp, status, resolution_timestamp, credibility_score, notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ptp.ptp_id, ptp.event_id, ptp.customer_id, ptp.customer_name,
        ptp.amount, ptp.currency, ptp.promised_timestamp, ptp.status.value,
        ptp.resolution_timestamp, ptp.credibility_score, ptp.notes, ptp.created_at
    ))
    conn.commit()
    conn.close()

def update_ptp_status(ptp_id: str, status: PTPStatus, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE ptp_records
    SET status = ?, resolution_timestamp = ?
    WHERE ptp_id = ?
    """, (status.value, time.time(), ptp_id))
    conn.commit()
    conn.close()

def get_all_ptp(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ptp_records ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ----------------- VERIFICATION & ANALYTICS -----------------

def record_recovery(event_id: str, recovered_amount: float, attribution_action_id: str, attribution_window_hours: float = 72.0, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    verification_id = f"ver_{hashlib.md5(f'{event_id}_{time.time()}'.encode()).hexdigest()[:10]}"
    now = time.time()
    cursor.execute("""
    INSERT INTO verifications (
        verification_id, event_id, is_recovered, recovered_amount, attribution_action_id,
        attribution_window_hours, recovered_timestamp, created_at
    ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)
    """, (verification_id, event_id, recovered_amount, attribution_action_id, attribution_window_hours, now, now))
    cursor.execute("UPDATE events SET status = 'recovered' WHERE event_id = ?", (event_id,))
    conn.commit()
    conn.close()

def get_analytics_summary(db_path: str = DB_PATH) -> Dict[str, Any]:
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Total at-risk revenue detected
    cursor.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total FROM events")
    tot_events = cursor.fetchone()

    # Total recovered
    cursor.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(recovered_amount), 0) as total FROM verifications WHERE is_recovered = 1")
    tot_recovered = cursor.fetchone()

    # Treatment Group vs Holdout Group Split
    cursor.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total FROM events WHERE is_holdout = 0")
    treatment_total = cursor.fetchone()

    cursor.execute("""
    SELECT COUNT(DISTINCT e.event_id) as cnt, COALESCE(SUM(v.recovered_amount), 0) as total
    FROM events e
    JOIN verifications v ON e.event_id = v.event_id
    WHERE e.is_holdout = 0
    """)
    treatment_recovered = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total FROM events WHERE is_holdout = 1")
    control_total = cursor.fetchone()

    cursor.execute("""
    SELECT COUNT(DISTINCT e.event_id) as cnt, COALESCE(SUM(v.recovered_amount), 0) as total
    FROM events e
    JOIN verifications v ON e.event_id = v.event_id
    WHERE e.is_holdout = 1
    """)
    control_recovered = cursor.fetchone()

    # Recovery rates
    treat_cnt = treatment_total['cnt'] or 0
    treat_rec_cnt = treatment_recovered['cnt'] or 0
    ctrl_cnt = control_total['cnt'] or 0
    ctrl_rec_cnt = control_recovered['cnt'] or 0

    treat_rate = (treat_rec_cnt / treat_cnt) if treat_cnt > 0 else 0.0
    ctrl_rate = (ctrl_rec_cnt / ctrl_cnt) if ctrl_cnt > 0 else 0.0
    incremental_lift = treat_rate - ctrl_rate

    # Archetype breakdown
    cursor.execute("""
    SELECT archetype,
           COUNT(*) as detected_count,
           COALESCE(SUM(amount), 0) as at_risk_inr,
           SUM(CASE WHEN status = 'recovered' THEN 1 ELSE 0 END) as recovered_count,
           SUM(CASE WHEN status = 'recovered' THEN amount ELSE 0 END) as recovered_inr
    FROM events
    GROUP BY archetype
    """)
    archetypes = [dict(r) for r in cursor.fetchall()]

    # Channel touches count and estimated outreach cost (e.g. ₹0.15/SMS, ₹0.60/WhatsApp, ₹2.00/Voice Call, ₹0.00/Smart Retry)
    cursor.execute("""
    SELECT action_type, COUNT(*) as touch_count
    FROM executions
    GROUP BY action_type
    """)
    action_counts = {r['action_type']: r['touch_count'] for r in cursor.fetchall()}
    costs = {
        'smart_retry': 0.0,
        'whatsapp_nudge': 0.60,
        'dunning_email': 0.05,
        'voice_ai_call': 2.20,
        'upi_payment_link': 0.10,
        'human_escalation': 50.0
    }
    total_cost = sum(action_counts.get(act, 0) * cost for act, cost in costs.items())
    recovered_inr = tot_recovered['total'] or 0.0
    roi_multiple = (recovered_inr / total_cost) if total_cost > 0 else (recovered_inr if recovered_inr > 0 else 0)

    # Active PTP counts
    cursor.execute("SELECT status, COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total FROM ptp_records GROUP BY status")
    ptp_summary = {r['status']: {'count': r['cnt'], 'amount': r['total']} for r in cursor.fetchall()}

    conn.close()
    return {
        "total_at_risk_count": tot_events['cnt'],
        "total_at_risk_amount": tot_events['total'],
        "total_recovered_count": tot_recovered['cnt'],
        "total_recovered_amount": recovered_inr,
        "treatment_group": {
            "count": treat_cnt,
            "recovered_count": treat_rec_cnt,
            "recovery_rate": round(treat_rate * 100, 2),
            "amount": treatment_total['total'],
            "recovered_amount": treatment_recovered['total']
        },
        "holdout_control_group": {
            "count": ctrl_cnt,
            "recovered_count": ctrl_rec_cnt,
            "recovery_rate": round(ctrl_rate * 100, 2),
            "amount": control_total['total'],
            "recovered_amount": control_recovered['total']
        },
        "incremental_lift_pct": round(incremental_lift * 100, 2),
        "true_incremental_recovered_amount": round(max(0, (treatment_total['total'] or 0) * incremental_lift), 2),
        "total_intervention_cost": round(total_cost, 2),
        "roi_multiple": round(roi_multiple, 1),
        "archetype_breakdown": archetypes,
        "action_counts": action_counts,
        "ptp_summary": ptp_summary
    }

def get_all_events(limit: int = 100, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT e.*, d.category as diag_category, d.rationale as diag_rationale,
           p.action_type as dec_action, p.rule_applied as dec_rule, p.compliance_status as dec_compliance
    FROM events e
    LEFT JOIN diagnoses d ON e.event_id = d.event_id
    LEFT JOIN decisions p ON e.event_id = p.event_id
    ORDER BY e.created_at DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['customer_history'] = json.loads(d['customer_history'] or '{}')
        d['session_telemetry'] = json.loads(d['session_telemetry'] or '{}')
        d['is_holdout'] = bool(d['is_holdout'])
        results.append(d)
    return results

def get_audit_trail(limit: int = 100, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['metadata'] = json.loads(d['metadata'] or '{}')
        results.append(d)
    return results

def get_settings(db_path: str = DB_PATH) -> Dict[str, str]:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    conn.close()
    return settings

def update_setting(key: str, value: str, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()
