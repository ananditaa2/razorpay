# RecoverRx 🛡️💸
demo video link: https://youtu.be/4LhkY55eo94
deploy link: https://recoverrx.onrender.com/

### *The Autonomous Diagnosis-and-Treatment Engine for Revenue*
#### *Built for Razorpay Engineering & Product 6-Month Internship Evaluation*

[![Razorpay Submission](https://img.shields.io/badge/Razorpay-Internship%20Task%20Submission-0c2340?style=for-the-badge&logo=razorpay&logoColor=3395ff)](https://github.com/ananditaa2/razorpay)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Regulatory](https://img.shields.io/badge/Compliance-RBI%20%26%20TRAI%20100%25-10B981?style=for-the-badge&logo=shield&logoColor=white)](#compliance--regulatory-layer)
[![Docker Ready](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)](Dockerfile)
[![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

![RecoverRx Executive Command Center UI](assets/hero.jpg)

---

## 💼 Why Razorpay Needs RecoverRx

For merchants processing on Razorpay, payment failures represent immediate Gross Merchandise Value (GMV) loss and customer churn. Today, merchants treat failed cards, cart drop-offs, unpaid invoices, and mandate bounces across disconnected dashboards with naive, repetitive retries.

**RecoverRx solves this by providing Razorpay with a unified, causal recovery engine:**

| Razorpay Product Suite | Revenue Failure Solved | RecoverRx Causal Treatment |
|---|---|---|
| **Razorpay Optimizer** | Soft Declines & Acquirer Downtime | Routes smart retries through secondary acquiring networks during post-salary cycles (1st/5th). |
| **Razorpay Magic Checkout** | Checkout Drop-off & SMS OTP Lag | Bypasses SMS OTP barriers by delivering an instant 1-tap WhatsApp checkout link with biometric/UPI deep links. |
| **Razorpay Subscriptions** | Recurring Renewal Drops | Executes an intelligent dunning sequence (Email $\rightarrow$ SMS $\rightarrow$ WhatsApp $\rightarrow$ Voice AI) to prevent involuntary churn. |
| **RazorpayX Current Accounts & Invoices** | Overdue B2B Receivables | Differentiates first-time late payers from chronic accounts; **immediately freezes automated dunning on disputed invoices** (RBI compliant). |
| **Razorpay TokenHQ & UPI Autopay** | Mandate Debit Bounces (NPCI `E01`) | Recognizes month-end pre-salary balance dips and sequences mandate retries for salary disbursement dates rather than burning mandate quotas. |

---

## 📌 The Problem

Revenue doesn't die in one dramatic moment — it leaks through many small, disconnected failures:
1. **Card payments fail silently** (insufficient funds, expired cards, bank declines, 3DS timeouts) and no one notices until subscriptions cancel.
2. **Checkouts get abandoned** at the OTP or payment step — high buyer intent is lost to friction.
3. **Subscription renewals fail** and blind retry logic retries the same dead card at the same time until the account cancels.
4. **B2B invoices go overdue** and companies either spam generic templated emails or ignore chronic late payers until cash flow breaks.
5. **UPI Autopay / NACH mandates fail** and blind resubmissions burn the mandate instead of adapting timing to salary disbursement cycles.

Treating these as separate tickets, separate dashboards, and separate teams fails to answer the causal question: **Why did this specific revenue stop flowing, and what is the minimum, compliant action that gets it flowing again?**

---

## 🔁 The Closed-Loop Pipeline

RecoverRx unifies all 5 failure archetypes into one continuous, causal loop: **Detect → Diagnose → Decide → Act → Verify → Audit**.

```mermaid
graph TD
    A[Incoming Signals: Razorpay / Stripe / ERP / Checkout] --> B[1. Detection & Ingestion Engine]
    B --> C{A/B Holdout Split: 10% Control vs 90% Treatment}
    C -- Control Slice --> V[Holdout Control: Natural Recovery Baseline]
    C -- Treatment Slice --> D[2. Root-Cause Diagnosis: Rules + LLM CoT]
    D --> E[3. Intervention Policy Engine]
    E --> F{Compliance Guardrails Check}
    F -- Fails: DND / Max 3 Touches / Off-Hours --> G[Queued / Suppressed / Off-Hours]
    F -- High Value >₹50k / Disputed --> H[Human Escalation Queue]
    F -- Approved --> I[4. Bounded Execution Layer]
    I --> I1[Smart Retry Scheduler]
    I --> I2[WhatsApp 1-Tap UPI Nudge]
    I --> I3[Tiered Dunning Email]
    I --> I4[Hinglish Voice AI Simulator]
    I --> I5[Dynamic UPI QR / Deep-Link]
    I4 & I2 --> J[5. Promise-to-Pay PTP Tracker]
    I --> K[6. Payment Gateway Verification]
    V & K --> L[Incremental Recovery Measurement: Treatment vs Control Lift]
    E & I & K --> M[7. Immutable SHA-256 Audit Ledger: RBI & TRAI Verified]
```

---

## ⚡ Key Capabilities

### 1. Signal Ingestion (Detect)
- Ingests webhooks from **Razorpay**, **Stripe**, **PayU**, checkout session logs, and ERP receivables aging data.
- Normalizes disparate signals into a unified `RevenueAtRiskEvent` schema.
- Allocates a deterministic 10% slice to an uncontacted **A/B Holdout Control Group** using hash modulo to prevent contamination.

### 2. Root-Cause Diagnosis (Diagnose)
- Hybrid rules + LLM Chain-of-Thought (CoT) reasoning engine.
- Maps raw error codes to causal categories:
  - **Hard Decline**: Dead/stolen/expired card token $\rightarrow$ Suppress retries; prompt card update.
  - **Soft Decline**: Insufficient balance, temporary downtime $\rightarrow$ Silent smart retry at salary cycle / off-peak.
  - **Checkout Friction**: SMS OTP lag $\rightarrow$ Instant 1-tap WhatsApp checkout bypassing OTP.
  - **Invoice Disputed**: Line-item or PO contest $\rightarrow$ **Immediately freeze automated dunning** per RBI fair practices.
  - **Mandate Balance**: Month-end bounce (NPCI `E01`) $\rightarrow$ Schedule retry post-salary credit (1st/5th).

### 3. Intervention Policy Engine (Decide)
- Hard-coded, immutable stopping rules:
  - **Max Touches Cap**: Strictly $\le 3$ contact attempts per incident.
  - **Cool-off Intervals**: Minimum 24 hours between customer touches.
  - **TRAI NDNC Compliance**: Customers registered on National Do Not Call registry are automatically downgraded to non-intrusive email only.
  - **Calling Window Restrictions**: Voice AI outreach strictly restricted to 09:00 - 20:00 IST.
  - **High-Value Threshold**: Accounts $>₹50,000$ or chronic defaulters trigger Human-in-the-Loop review.

### 4. Bounded Execution Layer (Act)
The agent can only invoke strictly authorized tools:
- `Tool_SmartRetry`: Dynamic routing switch and off-peak timing.
- `Tool_WhatsAppNudge`: Verified business template with 1-click Razorpay checkout & cart reservation.
- `Tool_DunningEmail`: Professional tiered dunning with ICICI virtual account escrow details.
- `Tool_VoiceAISimulator`: Respectful, conversational **Hinglish Voice AI recovery call** (`hi-IN`) with interactive waveform and speech synthesis.
- `Tool_UPILinkGenerator`: Dynamic NPCI compliant `upi://pay?...` deep links and QR codes.
- `Tool_HumanCollectorTask`: High-priority supervisor task queue with pre-configured settlement terms.

### 5. Promise-to-Pay (PTP) Ledger
- Logs customer verbal commitments (*"Friday ko salary ke baad pay kar dunga"*).
- Monitors deadlines and auto-checks settlement.
- Calibrates dynamic **Customer Trust & Credibility Scores** (0–100%).
- Automatically escalates upon broken promises.

### 6. A/B Holdout Verification & Incremental Measurement
- Proves true causal recovery vs. natural resolution:
  $$\text{Incremental Lift (\%)} = \text{Recovery Rate}_{\text{treatment}} - \text{Recovery Rate}_{\text{control}}$$
  $$\text{True Incremental Recovered (₹)} = \text{Treatment Revenue (₹)} \times \text{Incremental Lift (\%)}`$$
- Real-time ROI multiple calculation against operational outreach costs.

### 7. Cryptographic SHA-256 Audit Trail
- Every detection, diagnosis, decision, and bounded action is cryptographically hash-chained in an SQLite ledger.
- Full tamper-evident verification ensuring compliance with **RBI Debt Recovery Fair Practices** and **TRAI Commercial Communications Regulations**.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Standard web browser (Chrome, Edge, Firefox, Safari)

### 1. Clone the Repository
```bash
git clone https://github.com/ananditaa2/razorpay.git
cd razorpay
```

### Option A: One-Command CLI Launcher (Recommended for Evaluators)
```bash
python start.py
```
*This single command checks Python runtime, verifies the database, executes the 8-test self-diagnostics suite, starts the server on port 8080, and **automatically launches the Executive Command Center in your default browser**.*

### Option B: Docker Containerization
```bash
docker compose up --build
```
*Spins up a lightweight, containerized Python 3.12 service exposing `http://localhost:8080` with pre-seeded test data and healthchecks enabled.*

### Option C: Manual Setup & Testing
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Pre-load 15 realistic multi-channel incidents
python seed_data.py

# 3. Run complete test suite (8 unit tests)
python -m unittest tests/test_pipeline.py

# 4. Start production REST server
python server.py
```
Open **[http://localhost:8080](http://localhost:8080)** in your browser!

### Option D: 1-Click Cloud Deployment (Render / Railway / Fly.io)
Deploy straight to the cloud using the pre-configured [`render.yaml`](render.yaml) blueprint and [`Procfile`](Procfile). The engine includes an active healthcheck endpoint at `/healthz`.

---

## 📁 Repository Structure

```
razorpay/
├── assets/
│   └── hero.jpg                      # Command Center UI Showcase
├── engines/
│   ├── detection.py                  # Webhook & Telemetry Normalizer + Holdouts
│   ├── diagnosis.py                  # Root-Cause Rules + LLM CoT Classifier
│   ├── policy.py                     # Intervention Policy & Regulatory Guardrails
│   ├── execution.py                  # Bounded Action Registry (WhatsApp, Voice, UPI)
│   ├── ptp.py                        # Promise-to-Pay Ledger & Credibility Tracker
│   ├── verification.py               # Incremental Lift Math & 72h Attribution
│   └── compliance.py                 # SHA-256 Chain Verifier & RBI/TRAI Auditing
├── public/
│   ├── index.html                    # Luxury Glassmorphic Command Center Dashboard
│   ├── styles.css                    # Dark Obsidian FinTech Design System
│   └── app.js                        # Real-Time Telemetry & Simulation Controller
├── tests/
│   └── test_pipeline.py              # End-to-End Automated Test Suite (8 Tests)
├── database.py                       # SQLite Persistence & Hash Chaining
├── pipeline.py                       # Master Pipeline Orchestrator
├── schemas.py                        # Unified Domain Schemas & Enums
├── seed_data.py                      # Realistic 5-Archetype Seed Dataset
├── server.py                         # Production Multithreaded REST API Server
├── start.py                          # 🚀 One-Command Evaluator CLI Launcher
├── Dockerfile                        # Multi-Stage Production Containerfile
├── docker-compose.yml                # Docker Compose Orchestration
├── Procfile                          # Cloud Worker Definition
├── render.yaml                       # 1-Click Render Cloud Blueprint
├── requirements.txt                  # Minimal Production Dependencies
├── .gitignore
└── README.md
```

---

## 📡 REST API & Webhook Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/healthz` | Platform healthcheck & service status for cloud deployments |
| `GET` | `/api/analytics` | Executive KPIs, Incremental Lift %, and ROI multiple |
| `GET` | `/api/events` | List all normalized revenue-at-risk incidents |
| `GET` | `/api/events/<id>` | Deep-dive causal trace and audit timeline for an incident |
| `POST` | `/api/events/simulate` | Trigger any of the 7 pre-built revenue failure simulations |
| `POST` | `/api/webhooks/razorpay` | Real-time Razorpay webhook receiver with HMAC-SHA256 verification |
| `POST` | `/api/webhooks/checkout` | Real-time Checkout funnel drop-off telemetry receiver |
| `POST` | `/api/webhooks/erp_invoice`| ERP Receivables Net-30/60 invoice aging ingestion |
| `POST` | `/api/webhooks/payment_success` | Ingest successful settlement & calculate attribution |
| `GET` | `/api/ptp` | Active Promise-to-Pay commitment ledger |
| `POST` | `/api/ptp/fulfill` | Mark commitment as kept and credit recovery |
| `POST` | `/api/ptp/break` | Mark commitment as broken and trigger escalation |
| `GET` | `/api/audit` | Cryptographic SHA-256 audit trail & compliance report |
| `GET` / `POST`| `/api/settings` | Configure touch caps, cool-off hours, and API keys |

---

## 🛡️ Compliance & Regulatory Layer

- **RBI Outsourcing & Debt Recovery Guidelines**:
  - Zero abusive or threatening outreach.
  - Strict touch caps ($\le 3$ contacts per incident).
  - Immediate and mandatory collection freeze on disputed invoices.
  - Automatic escalation to human supervisors for large balances.
- **TRAI NDNC Regulations**:
  - Strict 09:00 - 20:00 IST permitted calling hours.
  - National Do Not Call registry verified before any voice call or SMS.
  - 1-click STOP opt-out killswitch.

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
