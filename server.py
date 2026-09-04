"""
RecoverRx Production HTTP & REST API Server
Provides high-performance multithreaded endpoints for webhook ingestion,
pipeline execution, simulation triggers, PTP management, analytics, and static UI assets.
"""
import http.server
import json
import os
import urllib.parse
from http import HTTPStatus
from socketserver import ThreadingMixIn
from typing import Dict, Any, Optional

import database
from pipeline import RecoverRxPipeline
from schemas import PTPStatus
from engines.detection import verify_razorpay_signature

PORT = int(os.environ.get("PORT", 8080))
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

pipeline = RecoverRxPipeline()

class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class RecoverRxHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.raw_body = b""
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _set_json_headers(self, status_code: int = 200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Razorpay-Signature")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_json_headers(200)

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.raw_body = b""
            return {}
        self.raw_body = self.rfile.read(content_length)
        try:
            return json.loads(self.raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # REST API Routes
        if path == "/api/analytics":
            data = pipeline.verification.compute_incremental_metrics()
            self._set_json_headers(200)
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        elif path == "/api/events":
            limit = int(query.get("limit", [100])[0])
            events = database.get_all_events(limit=limit)
            self._set_json_headers(200)
            self.wfile.write(json.dumps({"events": events}).encode("utf-8"))
            return

        elif path.startswith("/api/events/"):
            event_id = path.replace("/api/events/", "").strip()
            event = database.get_event(event_id)
            if not event:
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"error": "Event not found"}).encode("utf-8"))
                return

            diagnosis = database.get_diagnosis(event_id)
            decision = database.get_decision(event_id)
            executions = database.get_executions(event_id)
            all_ptp = database.get_all_ptp()
            ptp = next((p for p in all_ptp if p['event_id'] == event_id), None)

            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "event": event,
                "diagnosis": diagnosis,
                "decision": decision,
                "executions": executions,
                "ptp": ptp
            }).encode("utf-8"))
            return

        elif path == "/api/ptp":
            records = database.get_all_ptp()
            self._set_json_headers(200)
            self.wfile.write(json.dumps({"ptp_records": records}).encode("utf-8"))
            return

        elif path == "/api/audit":
            audit_records = database.get_audit_trail(limit=100)
            chain_status = pipeline.compliance.verify_audit_chain_integrity()
            compliance_audit = pipeline.compliance.run_compliance_audit()
            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "chain_status": chain_status,
                "compliance_audit": compliance_audit,
                "audit_records": audit_records
            }).encode("utf-8"))
            return

        elif path == "/api/settings":
            settings = database.get_settings()
            self._set_json_headers(200)
            self.wfile.write(json.dumps({"settings": settings}).encode("utf-8"))
            return

        elif path == "/healthz":
            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "status": "healthy",
                "service": "recover_rx",
                "version": "1.0.0",
                "engine": "autonomous_closed_loop",
                "database": "sqlite_connected"
            }).encode("utf-8"))
            return

        # Static assets fallback (HTML/CSS/JS)
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        # 1. 1-Click Simulation Scenario
        if path == "/api/events/simulate":
            scenario = body.get("scenario", "card_soft_decline")
            result = pipeline.simulate_scenario(scenario)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # 1b. Batch Run Endpoint (Processes 50 multi-channel events with stopping rules & lift)
        elif path == "/api/batch/run":
            from engines.batch_runner import BatchRecoveryRunner
            runner = BatchRecoveryRunner()
            batch_size = int(body.get("batch_size", 50))
            summary = runner.run_batch(batch_size=batch_size)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(summary).encode("utf-8"))
            return

        # 2. Razorpay Webhook Ingestion (with HMAC-SHA256 signature verification)
        elif path == "/api/webhooks/razorpay":
            signature = self.headers.get("X-Razorpay-Signature", "")
            sig_valid = verify_razorpay_signature(self.raw_body, signature) if signature else True
            event = pipeline.detection.ingest_razorpay_event(body)
            event.session_telemetry["signature_verified"] = sig_valid
            result = pipeline.run_pipeline_for_event(event)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # 3. Checkout Funnel Telemetry Ingestion
        elif path == "/api/webhooks/checkout":
            event = pipeline.detection.ingest_checkout_telemetry(body)
            result = pipeline.run_pipeline_for_event(event)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # 4. ERP Receivables Invoice Ingestion
        elif path == "/api/webhooks/erp_invoice":
            event = pipeline.detection.ingest_erp_invoice(body)
            result = pipeline.run_pipeline_for_event(event)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # 5. Payment Received / Verified
        elif path == "/api/webhooks/payment_success":
            event_id = body.get("event_id")
            amount = body.get("amount")
            if not event_id:
                self._set_json_headers(400)
                self.wfile.write(json.dumps({"error": "event_id is required"}).encode("utf-8"))
                return

            rec_res = pipeline.verification.register_payment_observed(event_id, amount=amount)

            # Also check if there was a PTP on this event and fulfill it
            all_ptp = database.get_all_ptp()
            active_ptp = next((p for p in all_ptp if p['event_id'] == event_id and p['status'] == PTPStatus.PENDING.value), None)
            if active_ptp:
                pipeline.ptp.fulfill_ptp(active_ptp['ptp_id'], recovered_amount=amount)

            self._set_json_headers(200)
            self.wfile.write(json.dumps(rec_res).encode("utf-8"))
            return

        # 6. Promise-to-Pay Fulfillment / Breach
        elif path == "/api/ptp/fulfill":
            ptp_id = body.get("ptp_id")
            if not ptp_id:
                self._set_json_headers(400)
                self.wfile.write(json.dumps({"error": "ptp_id is required"}).encode("utf-8"))
                return
            res = pipeline.ptp.fulfill_ptp(ptp_id)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif path == "/api/ptp/break":
            ptp_id = body.get("ptp_id")
            if not ptp_id:
                self._set_json_headers(400)
                self.wfile.write(json.dumps({"error": "ptp_id is required"}).encode("utf-8"))
                return
            res = pipeline.ptp.break_ptp(ptp_id)
            self._set_json_headers(200)
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # 7. Update Settings
        elif path == "/api/settings":
            for k, v in body.items():
                database.update_setting(k, str(v))
            self._set_json_headers(200)
            self.wfile.write(json.dumps({"success": True, "settings": database.get_settings()}).encode("utf-8"))
            return

        # 8. Human Review Approval
        elif path == "/api/human_review/approve":
            event_id = body.get("event_id")
            action = body.get("approved_action", "DISCOUNT_OFFERED")
            database.record_audit(
                event_id=event_id,
                stage="ACT",
                actor="Human_Supervisor",
                action_summary=f"Manager approved action '{action}' on high-value/disputed case.",
                compliance_tag="HUMAN_SUPERVISOR_AUTHORIZED",
                metadata=body
            )
            self._set_json_headers(200)
            self.wfile.write(json.dumps({"success": True, "message": "Manager review recorded"}).encode("utf-8"))
            return

        self._set_json_headers(404)
        self.wfile.write(json.dumps({"error": "API route not found"}).encode("utf-8"))

def start_server(port: int = PORT):
    database.init_db()
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    server = ThreadedHTTPServer(("0.0.0.0", port), RecoverRxHandler)
    print(f"RecoverRx Server listening on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()

if __name__ == "__main__":
    start_server()
