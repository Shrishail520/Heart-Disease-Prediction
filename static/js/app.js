/* ══════════════════════════════════════════════════
   HeartGuard — app.js
   Handles: Auth, Prediction, Emergency, Diet, Routine, History, ECG canvas
══════════════════════════════════════════════════ */

let csrfToken = null;
let currentUser = null;
let historyChart = null;

window.addEventListener('DOMContentLoaded', initializeSession);

function qs(id) {
  return document.getElementById(id);
}

function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[ch]));
}

// ── API helper ──
async function api(method, path, body) {
  const headers = {'Content-Type':'application/json'};
  if (method === 'POST' && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  const opts = { method, credentials: 'include', headers };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res  = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: { error: 'Network error' } };
  }
}

async function initializeSession() {
  const { ok, data } = await api('GET', '/api/me');
  if (!ok) return;
  csrfToken = data.csrf_token || null;
  if (data.user) {
    currentUser = data.user;
    setUser(data.user);
  }
}

// ── Toast ──
function toast(msg, type='info', dur=4000) {
  if (!qs('toasts')) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success:'✓', danger:'🚨', warn:'⚠', info:'ℹ' };
  el.textContent = `${icons[type] || 'i'} ${msg}`;
  qs('toasts').appendChild(el);
  setTimeout(() => { el.style.opacity='0'; el.style.transition='opacity .4s'; setTimeout(()=>el.remove(),400); }, dur);
}

// ── Live value display ──
function lv(id, val) {
  const el = qs(id);
  if (el) el.textContent = val;
}
function sanitizeNameInput(el) {
  el.value = el.value.replace(/[^A-Za-z ]+/g, '');
}
// ══════════════════════════════════════════════════
//  HEADER SCROLL
// ══════════════════════════════════════════════════
window.addEventListener('scroll', () => {
  const header = qs('header');
  if (header) header.classList.toggle('scrolled', window.scrollY > 20);
});

// ══════════════════════════════════════════════════
//  NAVIGATION
// ══════════════════════════════════════════════════
function showSection(id, btn) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const section = qs('sec-' + id);
  if (!section) return;
  section.classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const main = document.querySelector('.main');
  if (main) window.scrollTo({ top: main.offsetTop - 80, behavior: 'smooth' });

  if (id === 'diet')    loadDiet();
  if (id === 'routine') loadRoutine();
  if (id === 'history') loadHistory();
  if (id === 'doctor')  loadDoctorDashboard();
}

// ══════════════════════════════════════════════════
//  AUTH
// ══════════════════════════════════════════════════
function openAuth()  {
  const modal = qs('auth-modal');
  if (modal) modal.classList.remove('hidden');
}
function closeAuth() {
  const modal = qs('auth-modal');
  if (modal) modal.classList.add('hidden');
}

function switchAuth(tab, el) {
  document.querySelectorAll('.atab').forEach(t => t.classList.remove('active'));
  if (el) el.classList.add('active');
  document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
  const form = qs('af-' + tab);
  if (form) form.classList.add('active');
}

function openDoctorLogin() {
  window.location.href = '/doctor-login';
}

async function doLogin() {
  const username = document.getElementById('l-user').value.trim();
  const password = document.getElementById('l-pass').value;
  document.getElementById('l-err').classList.add('hidden');
  const { ok, data } = await api('POST', '/api/login', { username, password });
  if (!ok) { document.getElementById('l-err').textContent = data.error || 'Invalid credentials'; document.getElementById('l-err').classList.remove('hidden'); return; }
  closeAuth();
  setUser(data);
  toast(`Welcome back, ${data.name}! 💓`, 'success');
}

async function doDoctorLogin() {
  const username = document.getElementById('dl-user').value.trim();
  const password = document.getElementById('dl-pass').value;
  document.getElementById('dl-err').classList.add('hidden');
  const { ok, data } = await api('POST', '/api/login', { username, password });
  if (!ok) {
    document.getElementById('dl-err').textContent = data.error || 'Invalid credentials';
    document.getElementById('dl-err').classList.remove('hidden');
    return;
  }
  if (data.role !== 'doctor') {
    document.getElementById('dl-err').textContent = 'Doctor account required';
    document.getElementById('dl-err').classList.remove('hidden');
    return;
  }
  closeAuth();
  setUser(data);
  toast(`Doctor ${data.name} signed in`, 'success');
  showSection('doctor', qs('doctor-nav-btn'));
}

async function doRegister() {
  const name       = document.getElementById('r-name').value.trim();
  const username   = document.getElementById('r-user').value.trim();
  const password   = document.getElementById('r-pass').value;
  const age        = parseInt(document.getElementById('r-age').value) || 40;
  const phone      = document.getElementById('r-phone').value.trim();
  const doctorCode = document.getElementById('r-doctor-code').value.trim();
  const ec         = document.getElementById('r-ec').value.trim();
  document.getElementById('r-err').classList.add('hidden');
  if (!name || !username || !password) { toast('All required fields must be filled', 'warn'); return; }
  if (password.length < 6) { document.getElementById('r-err').textContent='Password must be 6+ characters'; document.getElementById('r-err').classList.remove('hidden'); return; }
  const { ok, status, data } = await api('POST', '/api/register', { name, username, password, age, phone, doctor_code: doctorCode, emergency_contact: ec });
  if (!ok) {
    document.getElementById('r-err').textContent = data.error || (status===409 ? 'Username taken' : 'Registration failed');
    document.getElementById('r-err').classList.remove('hidden'); return;
  }
  closeAuth();
  setUser(data);
  if (data.role === 'doctor' && !qs('auth-modal')) {
    window.location.href = '/';
    return;
  }
  toast(`Account created! Welcome, ${name} 🎉`, 'success');
}

function setUser(user) {
  currentUser = user;
  const chip = qs('user-chip');
  const btn  = qs('auth-toggle');
  if (!chip || !btn) return;
  chip.textContent = `${user.role === 'doctor' ? '👨‍⚕️ Doctor' : '💓'} ${user.name}`;
  chip.classList.remove('hidden');
  btn.textContent = 'Sign Out';
  btn.onclick = doLogout;
  const doctorButton = qs('doctor-nav-btn');
  const predictButton = document.querySelector('.nav-btn'); // Usually the first one
  const doctorLogin = qs('doctor-auth-toggle');
  if (user.role === 'doctor') {
    if (doctorButton) doctorButton.classList.remove('hidden');
    if (predictButton) predictButton.classList.add('hidden');
  } else {
    if (doctorButton) doctorButton.classList.add('hidden');
    if (predictButton) predictButton.classList.remove('hidden');
  }
  if (doctorLogin) doctorLogin.classList.add('hidden');
}

async function doLogout() {
  const { data } = await api('POST', '/api/logout');
  if (data && data.csrf_token) {
    csrfToken = data.csrf_token;
  } else {
    initializeSession(); // Fallback to full re-init
  }
  currentUser = null;
  const chip = qs('user-chip');
  if (chip) chip.classList.add('hidden');
  const btn = qs('auth-toggle');
  if (btn) {
    btn.textContent = 'Sign In';
    btn.onclick = openAuth;
  }
  const doctorButton = qs('doctor-nav-btn');
  if (doctorButton) doctorButton.classList.add('hidden');
  const doctorLogin = qs('doctor-auth-toggle');
  if (doctorLogin) doctorLogin.classList.remove('hidden');
  toast('Signed out successfully', 'info');
}

function bpUnknownChanged() {
  const checked = document.getElementById('f-bp-unknown').checked;
  const slider = document.getElementById('f-bp');
  slider.disabled = checked;
  slider.value = checked ? 120 : 125;
  lv('bp-v', checked ? '120 mmHg' : slider.value + ' mmHg');
  document.getElementById('bp-note').classList.toggle('hidden', !checked);
}

function cholUnknownChanged() {
  const checked = document.getElementById('f-chol-unknown').checked;
  const slider = document.getElementById('f-chol');
  slider.disabled = checked;
  slider.value = checked ? 200 : 212;
  lv('chol-v', checked ? '200 mg/dL' : slider.value + ' mg/dL');
  document.getElementById('chol-note').classList.toggle('hidden', !checked);
}

function showBpGuide() {
  const modal = qs('bp-guide-modal');
  if (modal) modal.classList.remove('hidden');
}
function closeBpGuide() {
  const modal = qs('bp-guide-modal');
  if (modal) modal.classList.add('hidden');
}
function openCholReminder() {
  const modal = qs('chol-guide-modal');
  if (modal) modal.classList.remove('hidden');
}
function closeCholReminder() {
  const modal = qs('chol-guide-modal');
  if (modal) modal.classList.add('hidden');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeAuth(); closeEmergency(); closeChestPain(); closeBpGuide(); closeCholReminder(); }
  const authModal = qs('auth-modal');
  if (e.key === 'Enter' && authModal && !authModal.classList.contains('hidden')) {
    if (qs('af-login')?.classList.contains('active')) doLogin();
    else doRegister();
  }
});

// ══════════════════════════════════════════════════
//  PREDICTION
// ══════════════════════════════════════════════════
async function runPredict() {
  const btn = document.querySelector('.predict-btn');
  btn.textContent = '⏳ Analysing...';
  btn.disabled = true;

const bpUnknown   = document.getElementById('f-bp-unknown').checked;
    const cholUnknown = document.getElementById('f-chol-unknown').checked;
    const firstName   = document.getElementById('f-name').value.trim();

    if (!firstName) {
      toast('Please enter your first name before running the assessment.', 'warn');
      btn.innerHTML = '<span class="predict-btn-icon">🧠</span> Analyse with ML';
      btn.disabled = false;
      return;
    }
    if (!/^[A-Za-z]+$/.test(firstName)) {
      toast('First name may only contain letters.', 'warn');
      btn.innerHTML = '<span class="predict-btn-icon">🧠</span> Analyse with ML';
      btn.disabled = false;
      return;
    }

    const payload = {
      name:     firstName,
      age:      parseInt(document.getElementById('f-age').value),
      sex:      parseInt(document.getElementById('f-sex').value),
      cp:       parseInt(document.getElementById('f-cp').value),
      trestbps: bpUnknown ? null : parseInt(document.getElementById('f-bp').value),
      chol:     cholUnknown ? null : parseInt(document.getElementById('f-chol').value),
      fbs:      parseInt(document.getElementById('f-fbs').value),
      restecg:  parseInt(document.getElementById('f-restecg').value),
      thalach:  parseInt(document.getElementById('f-thalach').value),
      exang:    parseInt(document.getElementById('f-exang').value),
      oldpeak:  parseFloat(document.getElementById('f-oldpeak').value) / 10,
      slope:    parseInt(document.getElementById('f-slope').value),
      ca:       parseInt(document.getElementById('f-ca').value),
      thal:     parseInt(document.getElementById('f-thal').value),
      algo:     (document.querySelector('input[name="algo"]:checked') || {}).value || 'ensemble'
    };

  const { ok, data } = await api('POST', '/api/predict', payload);

  btn.innerHTML = '<span class="predict-btn-icon">🧠</span> Analyse with ML';
  btn.disabled = false;

  if (!ok) { toast(data.error || 'Prediction failed', 'danger'); return; }

  if (!data.name) {
    data.name = firstName;
  }

  renderResult(data);

  // Smart alert: if high risk, highlight emergency button and show recommendation
  if (data.risk === 'HIGH') {
    document.getElementById('emergency-btn').classList.add('critical');
    toast('⚠️ High Risk detected! Please consult a cardiologist immediately.', 'danger', 8000);
  } else {
    document.getElementById('emergency-btn').classList.remove('critical');
  }
}

function renderResult(d) {
  const isHigh = d.risk === 'HIGH';
  const prob   = d.probability;
  const panel  = document.getElementById('result-panel');

  const factorsHTML = (d.factors || []).map(([name, level]) => `
    <div class="factor-item">
      <span class="fi-dot ${escapeHTML(level)}"></span>
      <span>${escapeHTML(name)}</span>
    </div>`).join('');

  const adviceHTML = (d.advice || []).map(a => `
    <div class="advice-item">${escapeHTML(a)}</div>`).join('');

  const alertHTML = isHigh ? `
    <div class="high-risk-alert">
      <div class="hra-icon">🚨</div>
      <div class="hra-text">
        <strong>Immediate medical attention recommended</strong>
        <span>Please call your cardiologist or visit the nearest cardiac centre.</span>
      </div>
    </div>` : '';

  panel.innerHTML = `
    <div class="result-card ${isHigh ? 'high' : 'low'}">
      <div class="rc-top">
        <div class="rc-icon">${isHigh ? '⚠️' : '✅'}</div>
        <div>
          <span class="rc-badge ${isHigh ? 'high' : 'low'}">${isHigh ? 'HIGH RISK' : 'LOW RISK'}</span>
          <div class="rc-title">${isHigh ? 'Heart Disease Risk Detected' : 'No Significant Risk Found'}</div>
          ${d.name ? `<div class="rc-user">Patient: <strong>${escapeHTML(d.name)}</strong></div>` : ''}
          <div class="rc-model">${escapeHTML(d.timestamp)}</div>
        </div>
      </div>
      ${alertHTML}
      <div class="prob-gauge">
        <div class="prob-label"><span>Risk Probability</span><span>${prob}%</span></div>
        <div class="prob-bar-track"><div class="prob-bar-fill ${isHigh?'high':'low'}" style="width:${prob}%"></div></div>
        <div class="prob-pct ${isHigh?'high':'low'}">${prob}%</div>
      </div>
      ${d.factors && d.factors.length ? `
      <div class="factors-block">
        <div class="factors-title">Contributing Risk Factors</div>
        ${factorsHTML}
      </div>` : ''}
      ${d.advice && d.advice.length ? `
      <div class="advice-block">
        <div class="factors-title" style="margin-bottom:8px">Clinical Recommendations</div>
        ${adviceHTML}
      </div>` : ''}
      ${d.notes && d.notes.length ? `
      <div class="notes-block">
        ${d.notes.map(n => `<div class="field-note note">${escapeHTML(n)}</div>`).join('')}
      </div>` : ''}
      <div class="rc-actions">
        ${isHigh ? `<button class="rc-btn primary" onclick="activateEmergency()">🚨 Emergency Help</button>` : ''}
        ${d.id ? `<button id="req-presc-btn-${d.id}" class="rc-btn accent" onclick="requestPrescription(${d.id})">💊 Ask for Doctor's Prescription</button>` : ''}
        <button class="rc-btn ghost" onclick="showSection('diet', document.querySelectorAll('.nav-btn')[1])">🥗 View Diet Plan</button>
        <button class="rc-btn ghost" onclick="showSection('routine', document.querySelectorAll('.nav-btn')[2])">📅 Daily Routine</button>
      </div>
    </div>`;
}

// ══════════════════════════════════════════════════
//  EMERGENCY
// ══════════════════════════════════════════════════
function activateEmergency() {
  const overlay = qs('emergency-overlay');
  const locationEl = qs('em-location');
  if (!overlay || !locationEl) return;
  overlay.classList.remove('hidden');
  locationEl.textContent = 'Fetching your location...';

  // Log to backend
  api('POST', '/api/emergency', {});

  // Get geolocation
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      pos => {
        const { latitude: lat, longitude: lng } = pos.coords;
        locationEl.innerHTML =
          `📍 Your location: <strong>${lat.toFixed(5)}, ${lng.toFixed(5)}</strong><br>
           <a href="https://maps.google.com/?q=${lat},${lng}" target="_blank" style="color:var(--red)">Open in Google Maps →</a>`;
        // Log with coordinates
        api('POST', '/api/emergency', { lat, lng });
      },
      () => {
        locationEl.textContent = 'Location unavailable. Please tell the dispatcher your address.';
      }
    );
  } else {
    locationEl.textContent = 'Location not supported on this device.';
  }

  toast('🚨 EMERGENCY ACTIVATED — Calling 108', 'danger', 10000);
}

function closeEmergency() {
  const overlay = qs('emergency-overlay');
  if (overlay) overlay.classList.add('hidden');
}

async function requestPrescription(predictionId) {
  const btn = qs(`req-presc-btn-${predictionId}`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⌛ Requesting...';
  }
  const { ok, data } = await api('POST', '/api/request-prescription', { prediction_id: predictionId });
  if (!ok) {
    toast(data.error || 'Failed to request prescription', 'danger');
    if (btn) {
      btn.disabled = false;
      btn.textContent = "💊 Ask for Doctor's Prescription";
    }
    return;
  }
  toast('Your request has been sent to the doctor! 🩺', 'success');
  if (btn) {
    btn.textContent = '✅ Prescription Requested';
    btn.classList.add('requested');
  }
  loadHistory(); // Refresh history to show status
}

// ══════════════════════════════════════════════════
//  CHEST PAIN PANEL
// ══════════════════════════════════════════════════
function openChestPain()  {
  const overlay = qs('chest-pain-overlay');
  if (overlay) overlay.classList.remove('hidden');
}
function closeChestPain() {
  const overlay = qs('chest-pain-overlay');
  if (overlay) overlay.classList.add('hidden');
}

// ══════════════════════════════════════════════════
//  DIET — loads from backend
// ══════════════════════════════════════════════════
let dietLoaded = false;
async function loadDiet() {
  if (dietLoaded) return;
  const { ok, data } = await api('GET', '/api/diet');
  if (!ok) return;
  dietLoaded = true;

  const healthy = data.healthy.map(f => `
    <div class="diet-item">
      <div class="diet-item-icon">${f.icon}</div>
      <div>
        <div class="diet-item-name">${f.name}</div>
        <div class="diet-item-detail">✓ ${f.benefit}</div>
      </div>
    </div>`).join('');

  const avoid = data.avoid.map(f => `
    <div class="diet-item">
      <div class="diet-item-icon">${f.icon}</div>
      <div>
        <div class="diet-item-name">${f.name}</div>
        <div class="diet-item-detail" style="color:var(--red)">✗ ${f.risk}</div>
      </div>
    </div>`).join('');

  document.getElementById('diet-content').innerHTML = `
    <div class="diet-card">
      <div class="diet-card-header">
        <div class="diet-item-icon">💚</div>
        <div class="diet-card-title green-text">Heart-Healthy Foods</div>
      </div>
      <div class="diet-items">${healthy}</div>
    </div>
    <div class="diet-card">
      <div class="diet-card-header">
        <div class="diet-item-icon">🚫</div>
        <div class="diet-card-title red-text">Foods to Avoid</div>
      </div>
      <div class="diet-items">${avoid}</div>
    </div>`;
}

// ══════════════════════════════════════════════════
//  ROUTINE — loads from backend
// ══════════════════════════════════════════════════
let routineLoaded = false;
let routineAll = [];

async function loadRoutine() {
  if (routineLoaded) return;
  const { ok, data } = await api('GET', '/api/routine');
  if (!ok) return;
  routineLoaded = true;
  routineAll = data.schedule;
  renderRoutine('all');
}

function renderRoutine(cat) {
  const filtered = cat === 'all' ? routineAll : routineAll.filter(r => r.category === cat);
  const items = filtered.map(r => `
    <div class="timeline-item">
      <div class="tl-time">${r.time}</div>
      <div class="tl-dot-wrap"><div class="tl-dot ${r.category}"></div></div>
      <div class="tl-card">
        <span class="tl-icon">${r.icon}</span>
        <div class="tl-activity">${r.activity}</div>
        <div class="tl-detail">${r.detail}</div>
      </div>
    </div>`).join('');

  document.getElementById('routine-content').innerHTML = `
    <div class="routine-categories">
      ${['all','morning','exercise','meal','health','rest'].map(c => `
        <button class="cat-filter ${cat===c?'active':''}" onclick="filterRoutine('${c}', this)">
          ${c.charAt(0).toUpperCase()+c.slice(1)}
        </button>`).join('')}
    </div>
    <div class="timeline">${items}</div>`;
}

function filterRoutine(cat, el) {
  document.querySelectorAll('.cat-filter').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  renderRoutine(cat);
}

// ══════════════════════════════════════════════════
//  HISTORY
// ══════════════════════════════════════════════════
async function loadHistory() {
  const { ok, data } = await api('GET', '/api/history');
  const el = document.getElementById('history-content');

  if (!ok) {
    el.innerHTML = `<div class="empty-state"><span class="empty-icon">🔒</span><p>Please sign in to view your assessment history.</p><button class="rc-btn ghost" style="max-width:200px;margin:16px auto" onclick="openAuth()">Sign In</button></div>`;
    return;
  }
  if (!data.history || data.history.length === 0) {
    el.innerHTML = `<div class="empty-state"><span class="empty-icon">📊</span><p>No assessments yet. Run your first prediction above!</p></div>`;
    return;
  }

  const rows = data.history.map(h => {
    const hasNote = !!h.doctor_comment;
    return `
    <tr>
      <td>${new Date(h.created_at).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})}</td>
      <td>${h.age}</td>
      <td>${h.trestbps}</td>
      <td>${h.chol}</td>
      <td>${h.thalach}</td>
      <td><span class="risk-badge rb-${h.risk === 'HIGH' ? 'high' : 'low'}">${h.risk}</span></td>
      <td style="font-weight:600;color:${h.risk==='HIGH'?'var(--red)':'var(--green)'}">${Math.round(h.probability*100)}%</td>
      <td>
        ${hasNote ? `
          <div class="note-pill" title="${escapeHTML(h.doctor_comment)}">
            <span class="pill-icon">📜</span> View Prescription
            <div class="note-tooltip">${escapeHTML(h.doctor_comment)}</div>
          </div>
        ` : (h.requested_prescription ? 
          '<span class="status-badge requested">🩺 Requested</span>' : 
          `<button class="mini-btn" onclick="requestPrescription(${h.id})">Request Rx</button>`
        )}
      </td>
    </tr>`;
  }).join('');

  const chartData = data.history.slice().reverse();
  const chartLabels = chartData.map(h => new Date(h.created_at).toLocaleDateString('en-IN',{day:'2-digit',month:'short'}));
  const chartValues = chartData.map(h => Math.round(h.probability * 100));
  const historyCtx = document.getElementById('history-chart');
  if (historyCtx) {
    if (historyChart) historyChart.destroy();
    historyChart = new Chart(historyCtx, {
      type: 'line',
      data: {
        labels: chartLabels,
        datasets: [{
          label: 'Risk score (%)',
          data: chartValues,
          borderColor: '#E8002D',
          backgroundColor: 'rgba(232,0,45,0.15)',
          fill: true,
          tension: 0.3,
          pointRadius: 4,
          pointBackgroundColor: '#E8002D'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false }, ticks: { color: '#475569' } },
          y: { beginAtZero: true, max: 100, ticks: { color: '#475569' } }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  el.innerHTML = `
    <table class="history-table">
      <thead><tr>
        <th>Date</th><th>Age</th><th>BP</th><th>Chol.</th><th>Max HR</th><th>Risk</th><th>Score</th><th>Model</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function loadDoctorDashboard() {
  const { ok, data } = await api('GET', '/api/doctor/predictions');
  const el = document.getElementById('doctor-content');
  if (!ok) {
    el.innerHTML = `<div class="empty-state"><span class="empty-icon">🔒</span><p>Doctor access required. Please sign in with a doctor account.</p></div>`;
    return;
  }
  if (!data.predictions || data.predictions.length === 0) {
    el.innerHTML = `<div class="empty-state"><span class="empty-icon">🩺</span><p>No patient assessments yet. Ask your patients to submit their data.</p></div>`;
    return;
  }

  const cards = data.predictions.map(pred => {
    const date = new Date(pred.created_at).toLocaleString('en-IN', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
    const predictionId = Number(pred.id);
    const risk = escapeHTML(pred.risk || '');
    const riskClass = escapeHTML(String(pred.risk || '').toLowerCase());
    const score = Number.isFinite(Number(pred.probability)) ? Math.round(Number(pred.probability) * 100) : 0;
    const lastNote = pred.doctor_comment ? `<strong>Last note:</strong> ${escapeHTML(pred.doctor_comment)}` : '<em>No notes added yet.</em>';
    const isRequested = pred.requested_prescription === 1;
    
    return `
      <div class="doctor-card ${isRequested ? 'requested-highlight' : ''}">
        <div class="doctor-card-header">
          <div>
            <h3>${escapeHTML(pred.patient_name)} <span class="meta">@${escapeHTML(pred.patient_username)}</span></h3>
            <p class="meta">${escapeHTML(date)} - ${escapeHTML(pred.model_used)}</p>
          </div>
          <div class="header-badges">
            ${isRequested ? '<div class="request-badge">PRESCRIPTION REQUESTED</div>' : ''}
            <div class="risk-pill risk-${riskClass}">${risk}</div>
          </div>
        </div>
        <div class="doctor-card-body">
          <div class="doctor-metrics">
            <span>Age: ${escapeHTML(pred.age)}</span>
            <span>BP: ${escapeHTML(pred.trestbps)}</span>
            <span>Chol: ${escapeHTML(pred.chol)}</span>
            <span>Max HR: ${escapeHTML(pred.thalach)}</span>
            <span>Score: ${score}%</span>
          </div>
          <p class="doctor-comment">${lastNote}</p>
          <div class="doctor-note-form">
            <textarea id="doctor-note-${predictionId}" placeholder="Add a recommendation or follow-up note..."></textarea>
            <button class="rc-btn primary" onclick="submitDoctorNote(${predictionId})">Save Note</button>
          </div>
        </div>
      </div>`;
  }).join('');

  el.innerHTML = `<div class="doctor-grid">${cards}</div>`;
}

async function submitDoctorNote(predictionId) {
  const noteEl = qs(`doctor-note-${predictionId}`);
  if (!noteEl) return;
  const comment = noteEl.value.trim();
  if (!comment) {
    toast('Please enter a comment before saving.', 'warn');
    return;
  }
  const { ok, data } = await api('POST', '/api/doctor/note', { prediction_id: predictionId, comment });
  if (!ok) {
    toast(data.error || 'Unable to save note', 'danger');
    return;
  }
  toast('Doctor note saved.', 'success');
  loadDoctorDashboard();
}

// ══════════════════════════════════════════════════
//  ECG CANVAS ANIMATION
// ══════════════════════════════════════════════════
(function() {
  const canvas = document.getElementById('ecg-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = 320, H = 80;
  let offset = 0;

  // ECG wave points relative to one cycle width
  const ecg = [0,0,0,0,0,2,-8,30,-6,0,0,4,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
  const cycleW = ecg.length;

  function drawECG() {
    ctx.clearRect(0, 0, W, H);

    // Grid lines
    ctx.strokeStyle = 'rgba(20,184,166,.08)';
    ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 20) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
    for (let y = 0; y < H; y += 20) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

    // ECG line
    ctx.beginPath();
    ctx.strokeStyle = '#14B8A6';
    ctx.lineWidth = 1.8;
    ctx.shadowColor = '#14B8A6';
    ctx.shadowBlur = 6;

    for (let x = 0; x < W; x++) {
      const i   = Math.floor((x + offset) % cycleW);
      const amp = ecg[i] || 0;
      const y   = H/2 - amp * 1.2;
      x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Moving dot
    const dotX = W - 4;
    const di   = Math.floor((dotX + offset) % cycleW);
    const dotY = H/2 - (ecg[di]||0) * 1.2;
    ctx.beginPath();
    ctx.arc(dotX, dotY, 3, 0, Math.PI*2);
    ctx.fillStyle = '#14B8A6';
    ctx.fill();

    offset = (offset + 0.8) % cycleW;
    requestAnimationFrame(drawECG);
  }

  drawECG();

  // Animate BPM fluctuation
  const bpmEl   = document.getElementById('hm-bpm');
  const spo2El  = document.getElementById('hm-spo2');
  let bpm = 72;
  setInterval(() => {
    bpm = Math.max(65, Math.min(82, bpm + (Math.random() > 0.5 ? 1 : -1)));
    if (bpmEl) bpmEl.textContent = bpm;
    const spo2 = 97 + Math.round(Math.random() * 2);
    if (spo2El) spo2El.textContent = spo2 + '%';
  }, 1800);
})();

// ══════════════════════════════════════════════════
//  EMERGENCY CHATBOX
// ══════════════════════════════════════════════════
let echatOpen = false;

function toggleEmergencyChat() {
  echatOpen = !echatOpen;
  const panel = qs('echat-panel');
  const toggle = qs('echat-toggle');
  if (!panel || !toggle) return;

  if (echatOpen) {
    panel.classList.remove('hidden');
    toggle.classList.add('active');
    // Focus the input
    const input = qs('echat-input');
    if (input) setTimeout(() => input.focus(), 100);
  } else {
    panel.classList.add('hidden');
    toggle.classList.remove('active');
  }
}

function handleChatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendEmergencyChat();
  }
}

function formatChatMessage(text) {
  // Convert markdown-style formatting to HTML
  let html = escapeHTML(text);

  // Bold: **text** or __text__
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');

  // Italic: *text* or _text_
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Bullet points: lines starting with - or •
  html = html.replace(/^[\-•]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/gs, '<ul>$&</ul>');

  // Numbered lists: lines starting with digits
  html = html.replace(/^\d+[\.\)]\s+(.+)$/gm, '<li>$1</li>');

  // Line breaks
  html = html.replace(/\n/g, '<br>');

  // Clean up double br in lists
  html = html.replace(/<br>\s*<li>/g, '<li>');
  html = html.replace(/<\/li>\s*<br>/g, '</li>');

  return html;
}

function addChatMessage(role, content) {
  const container = qs('echat-messages');
  if (!container) return;

  const msgDiv = document.createElement('div');
  msgDiv.className = `echat-msg ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'echat-avatar';
  avatar.textContent = role === 'bot' ? '🩺' : '👤';

  const bubble = document.createElement('div');
  bubble.className = 'echat-bubble';

  if (role === 'bot') {
    bubble.innerHTML = formatChatMessage(content);
  } else {
    bubble.innerHTML = `<p>${escapeHTML(content)}</p>`;
  }

  msgDiv.appendChild(avatar);
  msgDiv.appendChild(bubble);
  container.appendChild(msgDiv);

  // Scroll to bottom
  container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
  const container = qs('echat-messages');
  if (!container) return;

  const typingDiv = document.createElement('div');
  typingDiv.className = 'echat-msg bot';
  typingDiv.id = 'echat-typing';

  typingDiv.innerHTML = `
    <div class="echat-avatar">🩺</div>
    <div class="echat-bubble">
      <div class="echat-typing">
        <div class="echat-typing-dot"></div>
        <div class="echat-typing-dot"></div>
        <div class="echat-typing-dot"></div>
      </div>
    </div>`;

  container.appendChild(typingDiv);
  container.scrollTop = container.scrollHeight;
}

function removeTypingIndicator() {
  const typing = qs('echat-typing');
  if (typing) typing.remove();
}

async function sendEmergencyChat() {
  const input = qs('echat-input');
  const sendBtn = qs('echat-send');
  if (!input || !sendBtn) return;

  const message = input.value.trim();
  if (!message) return;

  // Add user message
  addChatMessage('user', message);
  input.value = '';
  input.style.height = 'auto';

  // Disable input while processing
  sendBtn.disabled = true;
  input.disabled = true;

  // Show typing indicator
  showTypingIndicator();

  try {
    const { ok, data } = await api('POST', '/api/emergency-chat', { message });

    removeTypingIndicator();

    if (ok && data.reply) {
      addChatMessage('bot', data.reply);
    } else if (data.error) {
      addChatMessage('bot', `⚠️ ${data.error}`);
    } else {
      addChatMessage('bot', '⚠️ Something went wrong. If this is an emergency, please call 108 immediately.');
    }
  } catch (err) {
    removeTypingIndicator();
    addChatMessage('bot', '⚠️ Network error. Please check your connection.\n\n**For emergencies, call 108 immediately.**');
  }

  // Re-enable input
  sendBtn.disabled = false;
  input.disabled = false;
  input.focus();
}

// Auto-resize textarea
document.addEventListener('DOMContentLoaded', () => {
  const chatInput = qs('echat-input');
  if (chatInput) {
    chatInput.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });
  }
});

