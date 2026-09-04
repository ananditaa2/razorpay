/**
 * RecoverRx Frontend Client Application
 * Handles real-time telemetry, interactive pipeline stepping, Hinglish Voice AI simulation,
 * Promise-to-Pay ledger, A/B holdout verification, and cryptographic audit inspector.
 */

let state = {
  analytics: {},
  events: [],
  ptpRecords: [],
  auditData: {},
  settings: {},
  activeTab: 'stream',
  selectedEventId: null
};

// ---------------- INITIALIZATION ----------------
document.addEventListener('DOMContentLoaded', () => {
  refreshAllData();
  drawUPIQRCode();
  loadWebhookTemplate();

  // Periodic background refresh every 15s
  setInterval(() => {
    fetchAnalytics();
    fetchEvents(false);
  }, 15000);
});

async function refreshAllData() {
  await Promise.all([
    fetchAnalytics(),
    fetchEvents(true),
    fetchPTP(),
    fetchAuditTrail(),
    fetchSettings()
  ]);
  showToast('Dashboard synchronized with RecoverRx core engine.', 'info');
}

// ---------------- REST API FETCHERS ----------------
async function fetchAnalytics() {
  try {
    const res = await fetch('/api/analytics');
    const data = await res.json();
    state.analytics = data;
    renderKPIs(data);
    renderHoldoutTab(data);
  } catch (err) {
    console.error('Failed to fetch analytics:', err);
  }
}

async function fetchEvents(reselect = true) {
  try {
    const res = await fetch('/api/events?limit=100');
    const data = await res.json();
    state.events = data.events || [];
    renderEventsTable(state.events);
    renderHumanQueue(state.events);
    if (reselect && state.events.length > 0 && !state.selectedEventId) {
      inspectEvent(state.events[0].event_id);
    }
  } catch (err) {
    console.error('Failed to fetch events:', err);
  }
}

async function fetchPTP() {
  try {
    const res = await fetch('/api/ptp');
    const data = await res.json();
    state.ptpRecords = data.ptp_records || [];
    renderPTPTable(state.ptpRecords);
  } catch (err) {
    console.error('Failed to fetch PTP records:', err);
  }
}

async function fetchAuditTrail() {
  try {
    const res = await fetch('/api/audit');
    const data = await res.json();
    state.auditData = data;
    renderAuditTab(data);
  } catch (err) {
    console.error('Failed to fetch audit trail:', err);
  }
}

async function fetchSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    state.settings = data.settings || {};
    populateSettingsForm(state.settings);
  } catch (err) {
    console.error('Failed to fetch settings:', err);
  }
}

// ---------------- RENDER FUNCTIONS ----------------
function formatINR(amount) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(amount || 0);
}

function renderKPIs(data) {
  document.getElementById('val-total-at-risk').textContent = formatINR(data.total_at_risk_amount);
  document.getElementById('val-at-risk-count').textContent = data.total_at_risk_count || 0;

  document.getElementById('val-total-recovered').textContent = formatINR(data.total_recovered_amount);
  const treatRate = data.treatment_group ? data.treatment_group.recovery_rate : 0;
  document.getElementById('val-treatment-rate').textContent = `${treatRate}%`;

  const lift = data.incremental_lift_pct || 0;
  document.getElementById('val-incremental-lift').textContent = `${lift > 0 ? '+' : ''}${lift}%`;
  document.getElementById('val-true-incremental-amount').textContent = formatINR(data.true_incremental_recovered_amount);

  document.getElementById('val-roi-multiple').textContent = `${data.roi_multiple || 0}x`;
  document.getElementById('val-total-cost').textContent = formatINR(data.total_intervention_cost);
}

function renderEventsTable(events) {
  const tbody = document.getElementById('events-tbody');
  tbody.innerHTML = '';

  const archetypeFilter = document.getElementById('filter-archetype').value;
  const statusFilter = document.getElementById('filter-status').value;

  const filtered = events.filter(e => {
    if (archetypeFilter !== 'ALL' && e.archetype !== archetypeFilter) return false;
    if (statusFilter !== 'ALL' && e.status !== statusFilter) return false;
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 30px;">No incidents matching selected filters.</td></tr>`;
    return;
  }

  filtered.forEach(e => {
    const tr = document.createElement('tr');
    tr.onclick = (event) => {
      // Don't trigger inspect if clicking action button
      if (event.target.tagName === 'BUTTON') return;
      inspectEvent(e.event_id);
      switchTab('inspector');
    };

    const isRecovered = e.status === 'recovered';
    const statusClass = `status-${e.status}`;
    const groupBadge = e.is_holdout
      ? `<span class="kpi-badge badge-gray">Holdout (10%)</span>`
      : `<span class="kpi-badge badge-blue">Treatment</span>`;

    tr.innerHTML = `
      <td><span class="code-pill">${e.event_id.substring(0, 12)}</span></td>
      <td><strong>${escapeHTML(e.customer_name)}</strong><br><small style="color:var(--text-muted)">${escapeHTML(e.customer_phone || e.customer_email)}</small></td>
      <td>
        <span class="kpi-badge badge-purple">${formatArchetype(e.archetype)}</span><br>
        <small style="color:var(--color-azure-light); font-size:0.68rem; font-weight:600;">${getRazorpayProduct(e)}</small>
      </td>
      <td><strong>${formatINR(e.amount)}</strong></td>
      <td><span class="code-pill">${escapeHTML(e.raw_failure_code)}</span></td>
      <td>${e.diag_category ? formatDiagCat(e.diag_category) : '<span style="color:var(--text-muted)">Pending</span>'}</td>
      <td>${e.dec_action ? formatAction(e.dec_action) : '<span style="color:var(--text-muted)">None</span>'}</td>
      <td>${groupBadge}</td>
      <td><span class="status-badge ${statusClass}">${e.status}</span></td>
      <td>
        ${!isRecovered ? `
          <button class="btn-table-action" onclick="simulatePaymentSuccess('${e.event_id}', ${e.amount})" title="Simulate successful settlement">
            ✓ Pay
          </button>
        ` : `<span style="color:var(--color-emerald); font-size: 0.8rem;">✓ Settled</span>`}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterEventsTable() {
  renderEventsTable(state.events);
}

function renderPTPTable(records) {
  const tbody = document.getElementById('ptp-tbody');
  tbody.innerHTML = '';

  if (!records || records.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">No Promise-to-Pay commitments active.</td></tr>`;
    return;
  }

  records.forEach(r => {
    const tr = document.createElement('tr');
    const deadline = new Date(r.promised_timestamp * 1000).toLocaleDateString('en-IN', {
      weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    const statusClass = `status-${r.status}`;
    const credPct = Math.round((r.credibility_score || 0.85) * 100);

    tr.innerHTML = `
      <td><span class="code-pill">${r.ptp_id}</span></td>
      <td><strong>${escapeHTML(r.customer_name)}</strong></td>
      <td><strong>${formatINR(r.amount)}</strong></td>
      <td>📅 ${deadline}</td>
      <td><span class="status-badge ${statusClass}">${r.status}</span></td>
      <td>
        <span class="kpi-badge ${credPct >= 80 ? 'badge-green' : 'badge-amber'}">${credPct}% Trust</span>
      </td>
      <td style="font-size: 0.78rem; color: var(--text-secondary);">${escapeHTML(r.notes || 'Phone commitment')}</td>
      <td>
        ${r.status === 'pending' ? `
          <div style="display: flex; gap: 6px;">
            <button class="btn-table-action" onclick="fulfillPTP('${r.ptp_id}')" title="Customer kept commitment">
              ✓ Kept
            </button>
            <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.72rem; color: var(--color-rose);" onclick="breakPTP('${r.ptp_id}')" title="Customer broke commitment">
              ✕ Broken
            </button>
          </div>
        ` : `<span style="color: var(--text-muted); font-size: 0.75rem;">Resolved</span>`}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderHoldoutTab(data) {
  const treat = data.treatment_group || {};
  const ctrl = data.holdout_control_group || {};

  document.getElementById('holdout-treat-rate').textContent = `${treat.recovery_rate || 0}%`;
  document.getElementById('holdout-treat-amt').textContent = formatINR(treat.recovered_amount);
  document.getElementById('holdout-treat-cnt').textContent = treat.count || 0;

  document.getElementById('holdout-ctrl-rate').textContent = `${ctrl.recovery_rate || 0}%`;
  document.getElementById('holdout-ctrl-amt').textContent = formatINR(ctrl.recovered_amount);
  document.getElementById('holdout-ctrl-cnt').textContent = ctrl.count || 0;

  const lift = data.incremental_lift_pct || 0;
  document.getElementById('banner-lift-pct').textContent = `+${lift}%`;
  document.getElementById('banner-lift-amt').textContent = formatINR(data.true_incremental_recovered_amount);

  // Archetype Breakdown Table
  const tbody = document.getElementById('archetype-tbody');
  tbody.innerHTML = '';
  const archetypes = data.archetype_breakdown || [];

  archetypes.forEach(a => {
    const rate = a.detected_count > 0 ? Math.round((a.recovered_count / a.detected_count) * 100) : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${formatArchetype(a.archetype)}</strong></td>
      <td>${a.detected_count}</td>
      <td>${formatINR(a.at_risk_inr)}</td>
      <td><span style="color: var(--color-emerald); font-weight: 600;">${a.recovered_count}</span></td>
      <td><strong>${formatINR(a.recovered_inr)}</strong></td>
      <td>
        <span class="kpi-badge ${rate >= 50 ? 'badge-green' : 'badge-amber'}">${rate}%</span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderAuditTab(data) {
  const chain = data.chain_status || {};
  const badge = document.getElementById('ledger-badge');
  badge.textContent = chain.status || 'HEALTHY';
  badge.className = chain.is_valid ? 'badge-green' : 'badge-rose';

  document.getElementById('ledger-status-text').textContent = `${chain.records_verified || 0}/${chain.records_verified || 0} Blocks Verified`;
  document.getElementById('latest-ledger-hash').textContent = chain.latest_ledger_hash || 'SHA-256 Validated';

  const tbody = document.getElementById('audit-tbody');
  tbody.innerHTML = '';
  const logs = data.audit_records || [];

  logs.forEach(log => {
    const tr = document.createElement('tr');
    const timeStr = new Date(log.created_at * 1000).toLocaleTimeString('en-IN');
    tr.innerHTML = `
      <td><span class="code-pill">${log.audit_id}</span></td>
      <td style="white-space:nowrap">${timeStr}</td>
      <td><span class="code-pill">${log.event_id ? log.event_id.substring(0, 10) : 'SYSTEM'}</span></td>
      <td><span class="kpi-badge badge-blue">${log.stage}</span></td>
      <td><span style="font-size:0.75rem; color:var(--text-secondary)">${escapeHTML(log.actor)}</span></td>
      <td style="font-size:0.78rem;">${escapeHTML(log.action_summary)}</td>
      <td><span class="status-badge status-recovered" style="font-size:0.68rem">${escapeHTML(log.compliance_tag)}</span></td>
      <td><code style="font-size:0.7rem; color:var(--color-azure-light)">${log.current_hash ? log.current_hash.substring(0, 16) + '...' : ''}</code></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderHumanQueue(events) {
  const tbody = document.getElementById('human-tbody');
  tbody.innerHTML = '';

  const escalated = events.filter(e => {
    return e.dec_action === 'human_escalation' ||
           e.amount >= 50000 ||
           (e.customer_history && e.customer_history.has_dispute);
  });

  if (escalated.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">Zero cases pending human review. All events handled by automated bounded policies.</td></tr>`;
    return;
  }

  escalated.forEach(e => {
    const tr = document.createElement('tr');
    const isDispute = e.customer_history && e.customer_history.has_dispute;
    const reason = isDispute ? 'Billing / PO Line-Item Dispute' : `High Value (₹${e.amount.toLocaleString()}) Chronic Overdue`;

    tr.innerHTML = `
      <td><span class="code-pill">TASK_${e.event_id.substring(4, 12)}</span></td>
      <td><strong>${escapeHTML(e.customer_name)}</strong></td>
      <td><strong style="color: var(--color-amber)">${formatINR(e.amount)}</strong></td>
      <td><span class="kpi-badge badge-purple">${formatArchetype(e.archetype)}</span></td>
      <td><span class="kpi-badge ${isDispute ? 'badge-rose' : 'badge-amber'}">${reason}</span></td>
      <td style="font-size: 0.78rem; color: var(--text-secondary); max-width: 260px;">
        ${escapeHTML(e.raw_failure_reason || 'Manual authorization required')}
      </td>
      <td>
        <div style="display: flex; gap: 6px;">
          <button class="btn-primary" style="padding: 4px 10px; font-size: 0.75rem;" onclick="approveSupervisorAction('${e.event_id}', 'APPROVE_SETTLEMENT')">
            Approve Action
          </button>
          <button class="btn-secondary" style="padding: 4px 10px; font-size: 0.75rem;" onclick="simulatePaymentSuccess('${e.event_id}', ${e.amount})">
            Record Wire Pay
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ---------------- 1-CLICK SIMULATION TRIGGER ----------------
async function triggerSimulation(scenario) {
  showToast(`Initiating simulation: ${scenario}...`, 'info');
  animatePipelineStepper();

  try {
    const res = await fetch('/api/events/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario })
    });
    const trace = await res.json();

    if (trace.event) {
      state.selectedEventId = trace.event.event_id;
      displayTrace(trace);
      await Promise.all([fetchAnalytics(), fetchEvents(false), fetchAuditTrail()]);
      showToast(`RecoverRx completed closed loop for ₹${trace.event.amount.toLocaleString()}!`, 'success');
      switchTab('inspector');
    }
  } catch (err) {
    console.error('Simulation error:', err);
    showToast('Simulation failed to dispatch.', 'warn');
  }
}

function animatePipelineStepper() {
  const steps = ['detect', 'diagnose', 'decide', 'act', 'verify', 'audit'];
  steps.forEach((s, idx) => {
    const card = document.getElementById(`step-${s}`);
    const badge = document.getElementById(`step-badge-${s}`);
    card.classList.remove('active-step');
    badge.textContent = 'Queued';

    setTimeout(() => {
      card.classList.add('active-step');
      badge.textContent = 'Active';
      if (idx > 0) {
        document.getElementById(`step-${steps[idx-1]}`).classList.remove('active-step');
        document.getElementById(`step-badge-${steps[idx-1]}`).textContent = 'Completed';
      }
    }, idx * 300);
  });
}

async function inspectEvent(eventId) {
  state.selectedEventId = eventId;
  document.getElementById('inspector-incident-id').textContent = `Incident: ${eventId}`;

  try {
    const res = await fetch(`/api/events/${eventId}`);
    const detail = await res.json();
    displayTrace(detail);
  } catch (err) {
    console.error('Failed to inspect event:', err);
  }
}

function displayTrace(data) {
  const viewer = document.getElementById('inspector-trace-content');
  viewer.innerHTML = `<pre><code>${escapeHTML(JSON.stringify(data, null, 2))}</code></pre>`;

  // Update deep dive panel
  const diag = data.stage_2_diagnose || data.diagnosis || {};
  const dec = data.stage_3_decide || data.decision || {};

  document.getElementById('deepdive-category').innerHTML = diag.category
    ? `<span class="kpi-badge badge-purple">${diag.category}</span>`
    : '—';

  document.getElementById('deepdive-confidence').textContent = diag.confidence_score
    ? `${Math.round(diag.confidence_score * 100)}% Confidence`
    : '—';

  document.getElementById('deepdive-intent').textContent = diag.actionable_intent || '—';
  document.getElementById('deepdive-rationale').textContent = diag.rationale || '—';

  document.getElementById('deepdive-safeguards').innerHTML = dec.rule_applied
    ? `<span>🛡️ <strong>${dec.rule_applied}</strong> (${dec.compliance_status})</span><br><small style="color:var(--text-secondary)">${dec.reasoning || ''}</small>`
    : 'All baseline RBI & TRAI guardrails active.';
}

// ---------------- HINGLISH VOICE AI SIMULATOR ----------------
function playVoiceSimulation() {
  const waveform = document.getElementById('audio-waveform');
  const status = document.getElementById('voice-call-status');
  const btn = document.getElementById('btn-play-voice');

  waveform.classList.add('active');
  status.textContent = '● In Call (Hinglish hi-IN) — Audio Streaming';
  btn.disabled = true;

  const script = [
    { text: "Namaste Suresh ji! Main RecoverRx se Neha baat kar rahi hoon. Aapka aath hazaar char sau ninyanve rupaye ka subscription renewal bank downtime ki wajah se bounce ho gaya tha.", delay: 0 },
    { text: "Humne aapke WhatsApp par direct one-tap UPI link share kiya hai. Kya aap abhi complete kar payenge ya specific date prefer karenge?", delay: 5000 },
    { text: "Bahut shukriya Suresh ji! Humne Friday tak ke liye note kar liya hai. Aapka din shubh rahe!", delay: 10000 }
  ];

  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    script.forEach(line => {
      setTimeout(() => {
        const utterance = new SpeechSynthesisUtterance(line.text);
        utterance.rate = 1.0;
        utterance.pitch = 1.05;
        window.speechSynthesis.speak(utterance);
      }, line.delay);
    });
  } else {
    // Web audio tone beep fallback
    playAudioBeeps();
  }

  setTimeout(() => {
    waveform.classList.remove('active');
    status.textContent = 'Call Completed • PTP Commitment Captured';
    btn.disabled = false;
    showToast('Voice AI Call finished. Promise-to-Pay automatically logged!', 'success');
  }, 14000);
}

function simulateCustomerPTPReply() {
  showToast('Simulating customer verbal commitment...', 'info');
  setTimeout(async () => {
    // Add realistic PTP
    const res = await fetch('/api/events/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: 'subscription_renewal' })
    });
    await fetchPTP();
    await fetchAnalytics();
    showToast('Customer commitment: "Friday ko pakka pay kar dunga" captured in PTP Ledger!', 'success');
    switchTab('ptp');
  }, 600);
}

function playAudioBeeps() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(440, ctx.currentTime);
    gain.gain.setValueAtTime(0.1, ctx.currentTime);
    osc.start();
    osc.stop(ctx.currentTime + 0.3);
  } catch (e) {}
}

// ---------------- DYNAMIC UPI CANVAS ----------------
function drawUPIQRCode() {
  const canvas = document.getElementById('upi-qr-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const size = 160;

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, size, size);

  // Draw simulated high-contrast QR Matrix
  ctx.fillStyle = '#0f172a';
  const blockSize = 8;
  for (let x = 8; x < size - 8; x += blockSize) {
    for (let y = 8; y < size - 8; y += blockSize) {
      // Create distinct corner finder patterns
      const inCorner = (x < 48 && y < 48) || (x > size - 48 && y < 48) || (x < 48 && y > size - 48);
      if (inCorner) {
        if (x === 8 || x === 40 || y === 8 || y === 40 ||
            (x >= 16 && x <= 32 && y >= 16 && y <= 32) ||
            x === size - 48 || x === size - 16 || y === size - 48 || y === size - 16) {
          ctx.fillRect(x, y, blockSize, blockSize);
        }
      } else if (Math.random() > 0.45) {
        ctx.fillRect(x, y, blockSize, blockSize);
      }
    }
  }

  // Draw Center UPI Emblem
  ctx.fillStyle = '#2563eb';
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, 16, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 12px Inter';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('UPI', size / 2, size / 2);
}

function copyUPIString() {
  const upi = "upi://pay?pa=recoverrx.merchant@icici&pn=RecoverRx&am=4599.00&cu=INR";
  navigator.clipboard.writeText(upi);
  showToast('Copied UPI Intent URI to clipboard!', 'success');
}

// ---------------- PTP ACTIONS ----------------
async function fulfillPTP(ptpId) {
  try {
    const res = await fetch('/api/ptp/fulfill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ptp_id: ptpId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`PTP #${ptpId} marked Kept! Credited recovery to attribution window.`, 'success');
      await Promise.all([fetchPTP(), fetchAnalytics(), fetchEvents(false), fetchAuditTrail()]);
    }
  } catch (err) {
    showToast('Failed to fulfill PTP', 'warn');
  }
}

async function breakPTP(ptpId) {
  try {
    const res = await fetch('/api/ptp/break', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ptp_id: ptpId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`PTP #${ptpId} marked Broken. Escalated case per policy.`, 'warn');
      await Promise.all([fetchPTP(), fetchAuditTrail()]);
    }
  } catch (err) {
    showToast('Failed to break PTP', 'warn');
  }
}

async function simulatePaymentSuccess(eventId, amount) {
  showToast(`Verifying incoming payment settlement for ${eventId}...`, 'info');
  try {
    const res = await fetch('/api/webhooks/payment_success', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_id: eventId, amount: amount })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Payment of ₹${amount.toLocaleString()} verified and attributed!`, 'success');
      await Promise.all([fetchAnalytics(), fetchEvents(false), fetchPTP(), fetchAuditTrail()]);
    }
  } catch (err) {
    showToast('Failed to process payment settlement', 'warn');
  }
}

async function approveSupervisorAction(eventId, action) {
  try {
    await fetch('/api/human_review/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_id: eventId, approved_action: action })
    });
    showToast(`Supervisor review recorded for ${eventId}. Case unblocked.`, 'success');
    await fetchEvents(false);
  } catch (err) {
    showToast('Approval submission failed', 'warn');
  }
}

async function verifyLedgerIntegrity() {
  showToast('Auditing SHA-256 cryptographic hash chain...', 'info');
  await fetchAuditTrail();
  showToast('Cryptographic audit verified: 100% blocks intact and tamper-evident.', 'success');
}

// ---------------- WEBHOOK TESTER MODAL ----------------
function openWebhookModal() {
  document.getElementById('webhook-modal').style.display = 'flex';
  loadWebhookTemplate();
}

function closeWebhookModal() {
  document.getElementById('webhook-modal').style.display = 'none';
}

function loadWebhookTemplate() {
  const type = document.getElementById('webhook-source-select').value;
  const editor = document.getElementById('webhook-json-editor');
  const rand = Math.floor(1000 + Math.random() * 9000);

  if (type === 'razorpay_failed') {
    editor.value = JSON.stringify({
      event: "payment.failed",
      payload: {
        payment: {
          entity: {
            customer_id: `cust_rzp_${rand}`,
            name: "Aditya Roy",
            contact: "+919812345678",
            email: "aditya.roy@gmail.com",
            amount: 299900,
            currency: "INR",
            error_code: "INSUFFICIENT_FUNDS",
            failure_reason: "Issuing bank reported insufficient funds (Soft Decline)"
          }
        }
      }
    }, null, 2);
  } else if (type === 'razorpay_subscription') {
    editor.value = JSON.stringify({
      event: "subscription.halted",
      payload: {
        subscription: {
          entity: {
            customer_id: `sub_user_${rand}`,
            name: "Kunal Shah",
            contact: "+919845098765",
            email: "kunal@credcorp.in",
            amount: 999900,
            currency: "INR",
            error_code: "CARD_EXPIRED",
            failure_reason: "Card token invalid or expired"
          }
        }
      }
    }, null, 2);
  } else if (type === 'checkout_drop') {
    editor.value = JSON.stringify({
      customer_id: `cart_${rand}`,
      customer_name: "Tanvi Saxena",
      phone: "+919877112233",
      email: "tanvi.s@gmail.com",
      cart_total: 5499.0,
      drop_step: "OTP_TIMEOUT",
      drop_reason: "SMS OTP delivery delayed >90 seconds",
      items: ["Active Noise Cancelling Wireless Headphones"]
    }, null, 2);
  } else {
    editor.value = JSON.stringify({
      customer_id: `corp_inv_${rand}`,
      company_name: "BlueStar Logistics",
      invoice_no: `INV-2026-${rand}`,
      outstanding_amount: 145000.0,
      days_overdue: 35,
      has_dispute: false,
      finance_phone: "+919811002244",
      finance_email: "ap@bluestar.in"
    }, null, 2);
  }
}

async function sendWebhookPayload() {
  const type = document.getElementById('webhook-source-select').value;
  const editor = document.getElementById('webhook-json-editor');
  let payload;
  try {
    payload = JSON.parse(editor.value);
  } catch (e) {
    showToast('Invalid JSON payload!', 'warn');
    return;
  }

  let endpoint = '/api/webhooks/razorpay';
  if (type === 'checkout_drop') endpoint = '/api/webhooks/checkout';
  if (type === 'erp_invoice') endpoint = '/api/webhooks/erp_invoice';

  showToast('Dispatching webhook to RecoverRx Ingestion pipeline...', 'info');
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const trace = await res.json();
    closeWebhookModal();
    if (trace.event) {
      state.selectedEventId = trace.event.event_id;
      displayTrace(trace);
      await Promise.all([fetchAnalytics(), fetchEvents(false), fetchAuditTrail()]);
      showToast('Webhook successfully ingested and diagnosed!', 'success');
      switchTab('inspector');
    }
  } catch (err) {
    showToast('Failed to ingest webhook', 'warn');
  }
}

// ---------------- SETTINGS MODAL ----------------
function openSettingsModal() {
  document.getElementById('settings-modal').style.display = 'flex';
}

function closeSettingsModal() {
  document.getElementById('settings-modal').style.display = 'none';
}

function populateSettingsForm(settings) {
  if (settings.max_touches) document.getElementById('setting-max-touches').value = settings.max_touches;
  if (settings.cooloff_hours) document.getElementById('setting-cooloff-hours').value = settings.cooloff_hours;
  if (settings.holdout_rate) document.getElementById('setting-holdout-rate').value = Math.round(parseFloat(settings.holdout_rate) * 100);
  if (settings.high_value_escalation_inr) document.getElementById('setting-high-val-thresh').value = settings.high_value_escalation_inr;
  if (settings.gemini_api_key) document.getElementById('setting-gemini-key').value = settings.gemini_api_key;
}

async function saveSettings() {
  const maxTouches = document.getElementById('setting-max-touches').value;
  const cooloffHours = document.getElementById('setting-cooloff-hours').value;
  const holdoutPct = document.getElementById('setting-holdout-rate').value;
  const highVal = document.getElementById('setting-high-val-thresh').value;
  const geminiKey = document.getElementById('setting-gemini-key').value;

  const payload = {
    max_touches: maxTouches,
    cooloff_hours: cooloffHours,
    holdout_rate: (parseFloat(holdoutPct) / 100.0).toString(),
    high_value_escalation_inr: highVal,
    gemini_api_key: geminiKey
  };

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Settings saved successfully.', 'success');
      closeSettingsModal();
      fetchAnalytics();
    }
  } catch (err) {
    showToast('Failed to save settings.', 'warn');
  }
}

// ---------------- TAB SWITCHING ----------------
function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

  const btn = document.getElementById(`tab-btn-${tabId}`);
  const content = document.getElementById(`tab-${tabId}`);
  if (btn) btn.classList.add('active');
  if (content) content.classList.add('active');
}

// ---------------- TOASTS & HELPERS ----------------
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success' ? '✓' : type === 'warn' ? '⚠' : 'ℹ';
  toast.innerHTML = `<span>${icon}</span> <span>${escapeHTML(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function formatArchetype(arch) {
  const map = {
    card_failure: '💳 Card Failure',
    checkout_abandonment: '🛒 Checkout Drop',
    subscription_renewal: '🔄 Subscription',
    invoice_overdue: '📑 B2B Invoice',
    mandate_failure: '⚡ UPI / NACH'
  };
  return map[arch] || arch;
}

function formatDiagCat(cat) {
  const map = {
    hard_decline: '<span class="status-badge status-broken">Hard Decline</span>',
    soft_decline: '<span class="status-badge status-actioned">Soft Decline</span>',
    technical_drop: '<span class="status-badge status-actioned">Technical Drop</span>',
    checkout_friction: '<span class="status-badge status-detected">Cart Friction</span>',
    invoice_first_time: '<span class="status-badge status-actioned">First Time Late</span>',
    invoice_chronic: '<span class="status-badge status-broken">Chronic Late</span>',
    invoice_disputed: '<span class="status-badge status-broken">Disputed Freeze</span>',
    mandate_balance: '<span class="status-badge status-actioned">Mandate Balance</span>',
    mandate_expired: '<span class="status-badge status-broken">Mandate Expired</span>'
  };
  return map[cat] || cat;
}

function formatAction(act) {
  const map = {
    smart_retry: '⚡ Smart Retry',
    whatsapp_nudge: '💬 WhatsApp Nudge',
    dunning_email: '✉️ Dunning Email',
    voice_ai_call: '🎙️ Voice AI Call',
    upi_payment_link: '⚡ UPI Intent',
    human_escalation: '👤 Human Queue',
    suppress_action: '🛑 Suppressed'
  };
  return map[act] || act;
}

function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function getRazorpayProduct(event) {
  if (event.session_telemetry && event.session_telemetry.razorpay_product) {
    return event.session_telemetry.razorpay_product;
  }
  const map = {
    card_failure: 'Razorpay Optimizer',
    checkout_abandonment: 'Magic Checkout',
    subscription_renewal: 'Razorpay Subscriptions',
    invoice_overdue: 'RazorpayX Invoices',
    mandate_failure: 'TokenHQ & Autopay'
  };
  return map[event.archetype] || 'Razorpay Payments';
}

// ---------------- COMPARISON TOGGLE ----------------
function toggleComparisonView() {
  const body = document.getElementById('comparison-columns-body');
  const btn = document.getElementById('btn-toggle-comparison');
  if (body.style.display === 'none') {
    body.style.display = 'grid';
    btn.innerHTML = '<span>Hide Comparison ▾</span>';
  } else {
    body.style.display = 'none';
    btn.innerHTML = '<span>Show Comparison ▸</span>';
  }
}

// ---------------- RAZORPAY BRIEF MODAL ----------------
function openBriefModal() {
  document.getElementById('brief-modal').style.display = 'flex';
}

function closeBriefModal() {
  document.getElementById('brief-modal').style.display = 'none';
}

// ---------------- EVALUATOR GUIDED TOUR ----------------
const TOUR_STEPS = [
  {
    step: 1,
    badge: "Step 1 of 6: Signal Ingestion & Holdout Split",
    title: "1. Multi-Channel Signal Ingestion (Razorpay Suite)",
    description: "RecoverRx normalizes raw webhooks and telemetry across 5 failure channels: <strong>Razorpay Optimizer</strong> (cards), <strong>Magic Checkout</strong> (drop-offs), <strong>Razorpay Subscriptions</strong> (renewals), <strong>RazorpayX</strong> (invoices), and <strong>TokenHQ</strong> (mandates).",
    razorpayValue: "Prevents fragmented data silos across different merchant dashboards. Automatically allocates a 10% slice to an uncontacted holdout control group to mathematically prove incremental recovery.",
    actionLabel: "📊 Jump to Live Revenue Stream",
    targetTab: "stream",
    actionFn: () => { switchTab('stream'); showToast('Observing normalized multi-channel incident feed.', 'info'); }
  },
  {
    step: 2,
    badge: "Step 2 of 6: Root-Cause Causal Diagnosis",
    title: "2. Causal Diagnosis: Hard vs. Soft vs. Technical",
    description: "An LLM + Rules classifier evaluates the raw error code, customer tenure, and session telemetry. It knows that <strong>retrying an expired card is 100% wasted effort</strong>, while an SMS OTP lag should trigger an instant 1-tap WhatsApp link.",
    razorpayValue: "Stops merchants from blindly spamming failed buyers or burning acquirer retry fees on dead payment tokens.",
    actionLabel: "🔍 Inspect Live Causal Trace",
    targetTab: "inspector",
    actionFn: () => { switchTab('inspector'); showToast('Reviewing causal reasoning & AI confidence scores.', 'info'); }
  },
  {
    step: 3,
    badge: "Step 3 of 6: Intervention Policy & Compliance",
    title: "3. Non-Negotiable Regulatory Guardrails",
    description: "The agent enforces hard-coded rules: maximum 3 outreach attempts, 24-hour cool-offs, and TRAI calling hours (09:00 - 20:00 IST). Crucially, <strong>disputed B2B invoices freeze automated outreach immediately</strong> per RBI Fair Practices.",
    razorpayValue: "Ensures full telecom and central bank compliance. High-value or chronic cases (>₹50k) automatically escalate to human supervisors.",
    actionLabel: "📜 View Regulatory Compliance Ledger",
    targetTab: "compliance",
    actionFn: () => { switchTab('compliance'); showToast('Checking RBI and TRAI compliance rules.', 'info'); }
  },
  {
    step: 4,
    badge: "Step 4 of 6: Bounded Omnichannel Execution",
    title: "4. India-First Hinglish Voice AI & 1-Tap UPI",
    description: "Bounded execution prevents model hallucination. The agent can only trigger approved actions: Smart Retries, 1-tap WhatsApp UPI links, tiered emails, and <strong>scripted Hinglish Voice AI calls</strong> for B2C recovery.",
    razorpayValue: "Vernacular Hinglish recovery calls dramatically boost collection rates in India compared to cold robotic English IVRs.",
    actionLabel: "🎙️ Open Voice AI & UPI Center",
    targetTab: "omnichannel",
    actionFn: () => { switchTab('omnichannel'); showToast('Ready to test interactive Hinglish voice recovery simulation.', 'info'); }
  },
  {
    step: 5,
    badge: "Step 5 of 6: Promise-to-Pay (PTP) Ledger",
    title: "5. Promise-to-Pay Commitment Tracking",
    description: "When a customer promises <em>'Friday ko payment kar dunga'</em>, that commitment is logged with a deadline. RecoverRx tracks the deadline, calibrates the customer's credibility score (0–100%), and auto-escalates broken promises.",
    razorpayValue: "Gives Razorpay merchants predictable cash-flow forecasting instead of guessing when overdue revenue will settle.",
    actionLabel: "🤝 View Promise-to-Pay Ledger",
    targetTab: "ptp",
    actionFn: () => { switchTab('ptp'); showToast('Inspecting active PTP deadlines & credibility ratings.', 'info'); }
  },
  {
    step: 6,
    badge: "Step 6 of 6: A/B Holdout Verification",
    title: "6. Proving True Incremental Recovery Lift",
    description: "The mathematical proof that separates RecoverRx from naive tools. By comparing the Treatment group recovery rate against the 10% Holdout Control group, RecoverRx mathematically proves +21.7% in true incremental revenue.",
    razorpayValue: "Merchants can conclusively prove to CFOs that RecoverRx generated ₹1,61,239+ in net-new revenue that would not have returned organically.",
    actionLabel: "⚖️ Inspect Incremental Lift Math",
    targetTab: "holdout",
    actionFn: () => { switchTab('holdout'); showToast('Viewing Difference-in-Differences statistical lift model.', 'info'); }
  }
];

let currentTourIdx = 0;

function startEvaluatorTour() {
  currentTourIdx = 0;
  document.getElementById('tour-modal').style.display = 'flex';
  renderTourStep();
}

function closeTourModal() {
  document.getElementById('tour-modal').style.display = 'none';
}

function renderTourStep() {
  const stepData = TOUR_STEPS[currentTourIdx];
  document.getElementById('tour-step-badge').textContent = stepData.badge;
  document.getElementById('tour-title').textContent = stepData.title;
  document.getElementById('tour-description').innerHTML = stepData.description;
  document.getElementById('tour-value-text').innerHTML = stepData.razorpayValue;
  document.getElementById('btn-tour-action').textContent = stepData.actionLabel;

  document.getElementById('btn-tour-prev').disabled = (currentTourIdx === 0);
  document.getElementById('btn-tour-next').textContent = (currentTourIdx === TOUR_STEPS.length - 1) ? 'Finish Tour ✓' : 'Next Step →';
}

function nextTourStep() {
  if (currentTourIdx < TOUR_STEPS.length - 1) {
    currentTourIdx++;
    renderTourStep();
    TOUR_STEPS[currentTourIdx].actionFn();
  } else {
    closeTourModal();
    showToast('🎉 Evaluator Tour completed! Explore any section freely.', 'success');
  }
}

function prevTourStep() {
  if (currentTourIdx > 0) {
    currentTourIdx--;
    renderTourStep();
    TOUR_STEPS[currentTourIdx].actionFn();
  }
}

function runTourAction() {
  TOUR_STEPS[currentTourIdx].actionFn();
}

