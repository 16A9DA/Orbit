const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const C = {
  accent: 'var(--accent)', green: 'var(--green)', amber: 'var(--amber)',
  red: 'var(--red)', purple: 'var(--purple)', muted: 'var(--muted)',
};

async function api(path, opts) {
  const r = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.status === 204 ? null : r.json();
}

const fmtTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso), diff = (Date.now() - d) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
};
const money = (n) => (n == null ? '–' : `$${Number(n).toFixed(2)}`);
const esc = (s) => String(s == null ? '' : s).replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));

// ---- Tabs ----
$$('.tab').forEach((t) => t.addEventListener('click', () => {
  $$('.tab').forEach((x) => x.classList.toggle('active', x === t));
  $('#panel-overview').classList.toggle('hidden', t.dataset.tab !== 'overview');
  $('#panel-tasks').classList.toggle('hidden', t.dataset.tab !== 'tasks');
}));

function tickClock() {
  $('#now').textContent = new Date().toLocaleString('en-US',
    { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ---- Service metadata helpers ----
const byType = (services, t) => services.filter((s) => s.type === t);
const meta = (s) => s.metadata || {};

// ---- Renderers ----
function renderStatus(services, counts) {
  const degraded = counts.degraded || 0;
  const dot = $('#status-dot');
  if (degraded || (counts.alerts_critical || 0) > 0) {
    dot.classList.add('warn');
    $('#status-text').textContent = degraded ? `${degraded} service(s) degraded` : 'Active alerts';
  } else {
    dot.classList.remove('warn');
    $('#status-text').textContent = 'All systems operational';
  }
}

function renderBanner(alerts) {
  const crit = alerts.find((a) => a.severity === 'critical');
  const b = $('#alert-banner');
  if (crit) {
    b.innerHTML = `⚠ <b>${esc(crit.title)}</b> — ${esc(crit.description || '')}`;
    b.classList.add('show');
  } else b.classList.remove('show');
}

function renderKpis(services, counts) {
  const rBill = byType(services, 'render').find((s) => meta(s).monthly_cost != null);
  const gcp = byType(services, 'gcp')[0];
  const sg = byType(services, 'sendgrid')[0];
  const gh = byType(services, 'github')[0];

  const renderCost = rBill ? Number(meta(rBill).monthly_cost || 0) : 0;
  const gcpCost = gcp ? Number(meta(gcp).billing_month_usd || 0) : 0;
  const mtd = renderCost + gcpCost;

  const total = counts.services || 0;
  const healthy = total - (counts.degraded || 0);
  const delivered = sg ? (meta(sg).delivered ?? null) : null;
  const requests = sg ? (meta(sg).requests ?? null) : null;
  const deliveredPct = requests ? ((delivered / requests) * 100).toFixed(1) + '% delivered' : 'no data';
  const prs = gh ? (meta(gh).open_prs ?? null) : null;

  const kpis = [
    { label: 'MTD SPEND', value: money(mtd), delta: 'render + gcp', color: C.muted },
    { label: 'ACTIVE SERVICES', value: `${healthy}/${total}`, delta: counts.degraded ? `${counts.degraded} degraded` : 'all healthy', color: counts.degraded ? C.amber : C.green },
    { label: 'EMAILS DELIVERED', value: delivered != null ? Number(delivered).toLocaleString() : '–', delta: deliveredPct, color: C.green },
    { label: 'OPEN ALERTS', value: String((counts.alerts_critical || 0) + (counts.alerts_warning || 0)), delta: `${counts.alerts_critical || 0} critical`, color: (counts.alerts_critical ? C.red : C.muted) },
  ];
  $('#kpis').innerHTML = kpis.map((k) => `
    <div class="kpi">
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.value}</div>
      <div class="kpi-delta" style="color:${k.color}">${k.delta}</div>
    </div>`).join('');
}

function renderRenderCard(services) {
  const apps = byType(services, 'render').filter((s) => meta(s).id);
  $('#render-badge').textContent = `${apps.length} apps`;
  const dotColor = (st) => st === 'operational' ? C.green : st === 'deploying' ? C.amber : C.red;
  $('#render-list').innerHTML = apps.map((s) => {
    const m = meta(s);
    const dep = m.latest_deploy && m.latest_deploy.status ? m.latest_deploy.status : (m.service_type || 'service');
    return `<div class="svc-item" data-render-id="${esc(m.id)}">
        <span class="s-dot" style="background:${dotColor(s.status)}"></span>
        <span class="s-name">${esc(s.name)}</span>
        <span class="s-detail">${esc(dep)}</span>
      </div><div class="svc-logs hidden" data-logs-for="${esc(m.id)}"></div>`;
  }).join('') || '<div class="row"><span class="sub">No Render apps.</span></div>';
}

function bar(label, value, pct, color) {
  return `<div class="metric">
    <div class="metric-head"><span>${label}</span><b>${value}</b></div>
    <div class="bar"><i style="width:${Math.max(0, Math.min(100, pct))}%;background:${color}"></i></div>
  </div>`;
}

function renderSendgridCard(services) {
  const sg = byType(services, 'sendgrid')[0];
  const badge = $('#sendgrid-badge');
  if (!sg || meta(sg).error) {
    badge.textContent = 'no data';
    $('#sendgrid-metrics').innerHTML = `<div class="row"><span class="sub">${esc(sg ? meta(sg).error : 'Not configured')}</span></div>`;
    return;
  }
  const m = meta(sg);
  badge.textContent = sg.status;
  const req = m.requests || 0, deliv = m.delivered || 0;
  const bounces = (m.bounces || 0) + (m.blocks || 0), opens = m.opens || 0, spam = m.spam_reports || 0;
  const pct = (n) => req ? (n / req) * 100 : 0;
  $('#sendgrid-metrics').innerHTML = [
    bar('Sent', Number(req).toLocaleString(), req ? 100 : 0, C.accent),
    bar('Delivered', req ? ((deliv / req) * 100).toFixed(1) + '%' : '–', pct(deliv), C.green),
    bar('Opens', req ? ((opens / req) * 100).toFixed(1) + '%' : '–', pct(opens), C.accent),
    bar('Bounces', req ? ((bounces / req) * 100).toFixed(1) + '%' : '–', pct(bounces) * 4, C.red),
    bar('Spam', req ? ((spam / req) * 100).toFixed(1) + '%' : '–', pct(spam) * 4, C.purple),
  ].join('');
}

function renderGithubCard(services) {
  const gh = byType(services, 'github')[0];
  const badge = $('#github-badge');
  const body = $('#github-body');
  if (!gh) { badge.textContent = 'no data'; body.innerHTML = '<div class="row"><span class="sub">No GitHub service.</span></div>'; return; }
  const m = meta(gh);
  badge.textContent = gh.status;
  const repos = m.repos || m.repositories || [];
  if (repos.length) {
    body.innerHTML = repos.slice(0, 6).map((r) =>
      `<div class="gh-repo"><span>${esc(r.name)}</span><span class="c">${esc(r.commits ?? r.language ?? '')}</span></div>`).join('');
  } else {
    body.innerHTML = Object.entries(m)
      .filter(([k, v]) => typeof v !== 'object' && !['id', 'mock'].includes(k))
      .slice(0, 6).map(([k, v]) => `<div class="gh-repo"><span>${esc(k)}</span><span class="c">${esc(v)}</span></div>`).join('')
      || '<div class="row"><span class="sub">No data.</span></div>';
  }
}

function renderBilling(services) {
  const rBill = byType(services, 'render').find((s) => meta(s).monthly_cost != null);
  const gcp = byType(services, 'gcp')[0];
  const gcpOff = gcp && meta(gcp).billing_enabled === false;
  const rows = [];
  if (rBill) rows.push({ name: 'Render', amount: Number(meta(rBill).monthly_cost || 0), color: 'oklch(0.62 0.16 200)' });
  if (gcpOff) rows.push({ name: 'Google Cloud', off: true, color: 'oklch(0.5 0.02 260)' });
  else if (gcp && meta(gcp).billing_month_usd != null) rows.push({ name: 'Google Cloud', amount: Number(meta(gcp).billing_month_usd || 0), color: 'oklch(0.68 0.17 280)' });
  const total = rows.reduce((a, r) => a + (r.amount || 0), 0);
  $('#billing-total').textContent = money(total);
  $('#billing-stack').innerHTML = rows.map((r) =>
    `<i style="width:${total ? (r.amount / total) * 100 : 0}%;background:${r.color}"></i>`).join('');
  $('#billing-rows').innerHTML = rows.map((r) =>
    `<div class="bill-row"><span class="sw" style="background:${r.color}"></span><span>${r.name}</span><span class="amt">${r.off ? 'Billing off' : money(r.amount)}</span></div>`).join('')
    || '<div class="row"><span class="sub">No billing data.</span></div>';
}

function renderActivity(activity) {
  const color = { render: C.amber, github: C.green, gcp: C.purple, sendgrid: C.accent };
  $('#activity-list').innerHTML = activity.slice(0, 8).map((a) => `
    <div class="row">
      <span class="tag" style="color:${color[a.service] || C.muted}">${esc((a.service || '').toUpperCase())}</span>
      <span class="body">${esc(a.event)}</span>
      <span class="time">${fmtTime(a.timestamp)}</span>
    </div>`).join('') || '<div class="row"><span class="sub">No activity.</span></div>';
}

function renderAlerts(alerts) {
  $('#alerts-count').textContent = alerts.length;
  const color = { critical: C.red, warning: C.amber };
  $('#alerts-list').innerHTML = alerts.slice(0, 8).map((a) => `
    <div class="row">
      <div>
        <div class="body" style="color:${color[a.severity] || C.muted}">${esc(a.title)}</div>
        <div class="sub">${esc(a.description || '')}</div>
      </div>
      <span class="time">${fmtTime(a.created_at)}</span>
    </div>`).join('') || '<div class="row"><span class="sub">No open alerts.</span></div>';
}

// ---- Tasks (real API) ----
let TASKS = [];
const isDone = (t) => t.status === 'done';

function renderSuggested(tasks) {
  const open = tasks.filter((t) => !isDone(t)).slice(0, 5);
  $('#suggested-list').innerHTML = open.map((t) => `
    <div class="check">
      <span class="box" data-toggle="${t.id}"></span>
      <span class="txt">${esc(t.title)}</span>
    </div>`).join('') || '<div class="row"><span class="sub">Inbox zero.</span></div>';
}

function renderMyTasks(tasks) {
  $('#mytasks-list').innerHTML = tasks.map((t) => `
    <div class="check">
      <span class="box ${isDone(t) ? 'done' : ''}" data-toggle="${t.id}">${isDone(t) ? '✓' : ''}</span>
      <span class="txt ${isDone(t) ? 'done' : ''}">${esc(t.title)}</span>
      <span class="x" data-del="${t.id}">×</span>
    </div>`).join('') || '<div class="row"><span class="sub">No tasks yet.</span></div>';
}

async function toggleTask(id) {
  const t = TASKS.find((x) => String(x.id) === String(id));
  if (!t) return;
  const next = isDone(t) ? 'todo' : 'done';
  await api(`/tasks/${id}/`, { method: 'PATCH', body: JSON.stringify({ status: next }) });
  t.status = next;
  renderSuggested(TASKS); renderMyTasks(TASKS);
}
async function deleteTask(id) {
  await api(`/tasks/${id}/`, { method: 'DELETE' });
  TASKS = TASKS.filter((x) => String(x.id) !== String(id));
  renderSuggested(TASKS); renderMyTasks(TASKS);
}
async function addTask(title) {
  const t = await api('/tasks/', { method: 'POST', body: JSON.stringify({ title, priority: 'medium', status: 'todo' }) });
  TASKS.push(t);
  renderSuggested(TASKS); renderMyTasks(TASKS);
}

document.addEventListener('click', (e) => {
  const tog = e.target.closest('[data-toggle]');
  if (tog) return toggleTask(tog.dataset.toggle);
  const del = e.target.closest('[data-del]');
  if (del) return deleteTask(del.dataset.del);
});
$('#task-add-btn').addEventListener('click', () => {
  const v = $('#task-input').value.trim();
  if (v) { addTask(v); $('#task-input').value = ''; }
});
$('#task-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('#task-add-btn').click(); });

// ---- Render app logs (click) ----
$('#render-list').addEventListener('click', async (e) => {
  const item = e.target.closest('[data-render-id]');
  if (!item) return;
  const id = item.dataset.renderId;
  const box = $(`[data-logs-for="${id}"]`);
  if (!box) return;
  if (!box.classList.contains('hidden')) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  box.textContent = 'Loading logs…';
  try {
    const data = await api(`/render/${id}/logs/`);
    const logs = data.logs || [];
    if (data.error) { box.textContent = data.error; return; }
    box.innerHTML = logs.length
      ? logs.map((l) => `<div class="log-line">${esc(typeof l === 'string' ? l : (l.message || JSON.stringify(l)))}</div>`).join('')
      : 'No logs.';
  } catch (err) { box.textContent = `Failed: ${err.message}`; }
});

// ---- Assistant chat ----
$('#chat-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#chat-input');
  const q = input.value.trim();
  if (!q) return;
  const log = $('#chat-log');
  log.insertAdjacentHTML('beforeend', `<div class="msg me">${esc(q)}</div>`);
  input.value = '';
  const pending = document.createElement('div');
  pending.className = 'msg bot'; pending.textContent = 'Thinking…';
  log.appendChild(pending); log.scrollTop = log.scrollHeight;
  try {
    const data = await api('/assistant/', { method: 'POST', body: JSON.stringify({ question: q }) });
    pending.textContent = data.answer || 'No answer.';
  } catch (err) { pending.textContent = `Error: ${err.message}`; }
  log.scrollTop = log.scrollHeight;
});

// ---- Notes (localStorage) ----
const NOTES_KEY = 'orbit_notes';
let notes = JSON.parse(localStorage.getItem(NOTES_KEY) || 'null') || [
  { id: 1, title: 'Standup', body: '', updated: Date.now() },
];
let activeNote = notes[0] ? notes[0].id : null;
const saveNotes = () => localStorage.setItem(NOTES_KEY, JSON.stringify(notes));

function renderNotes() {
  $('#note-count').textContent = `${notes.length} NOTE${notes.length === 1 ? '' : 'S'}`;
  $('#notes-list').innerHTML = notes.map((n) => `
    <div class="note-item ${n.id === activeNote ? 'active' : ''}" data-note="${n.id}">
      <div class="nt">${esc(n.title || 'Untitled')}<span class="x" data-note-del="${n.id}">×</span></div>
      <div class="np">${esc(n.body ? n.body.slice(0, 60) : 'No content')}</div>
    </div>`).join('') || '<div class="row"><span class="sub">No notes.</span></div>';
  const a = notes.find((n) => n.id === activeNote);
  $('#note-title').value = a ? a.title : '';
  $('#note-body').value = a ? a.body : '';
  $('#note-meta').textContent = a ? `Edited ${fmtTime(a.updated)}` : '';
}
$('#notes-list').addEventListener('click', (e) => {
  const del = e.target.closest('[data-note-del]');
  if (del) {
    e.stopPropagation();
    notes = notes.filter((n) => String(n.id) !== del.dataset.noteDel);
    if (String(activeNote) === del.dataset.noteDel) activeNote = notes[0] ? notes[0].id : null;
    saveNotes(); renderNotes(); return;
  }
  const item = e.target.closest('[data-note]');
  if (item) { activeNote = Number(item.dataset.note); renderNotes(); }
});
$('#add-note').addEventListener('click', () => {
  const id = Date.now();
  notes.unshift({ id, title: 'Untitled', body: '', updated: id });
  activeNote = id; saveNotes(); renderNotes();
});
function patchActive(patch) {
  const a = notes.find((n) => n.id === activeNote);
  if (!a) return;
  Object.assign(a, patch, { updated: Date.now() });
  saveNotes();
  $('#note-count').textContent = `${notes.length} NOTE${notes.length === 1 ? '' : 'S'}`;
  const row = $(`[data-note="${a.id}"]`);
  if (row) { row.querySelector('.nt').firstChild.textContent = a.title || 'Untitled'; row.querySelector('.np').textContent = a.body ? a.body.slice(0, 60) : 'No content'; }
}
$('#note-title').addEventListener('input', (e) => patchActive({ title: e.target.value }));
$('#note-body').addEventListener('input', (e) => patchActive({ body: e.target.value }));

// ---- Briefing ----
function renderBriefing(services, counts, alerts) {
  const degraded = counts.degraded || 0;
  const crit = counts.alerts_critical || 0;
  const parts = [];
  if (crit) parts.push(`${crit} critical alert(s) need attention`);
  if (degraded) parts.push(`${degraded} service(s) degraded`);
  if (!parts.length) parts.push('All monitored services are operational');
  const warn = counts.alerts_warning || 0;
  if (warn) parts.push(`${warn} warning(s) open`);
  $('#briefing').textContent = parts.join('. ') + '.';
}

// ---- Load ----
async function load() {
  const data = await api('/summary/');
  const { services, counts, alerts, tasks, activity } = data;
  TASKS = tasks || [];
  renderStatus(services, counts);
  renderBanner(alerts);
  renderBriefing(services, counts, alerts);
  renderKpis(services, counts);
  renderRenderCard(services);
  renderSendgridCard(services);
  renderGithubCard(services);
  renderBilling(services);
  renderActivity(activity || []);
  renderAlerts(alerts || []);
  renderSuggested(TASKS);
  renderMyTasks(TASKS);
  renderNotes();
}

$('#refresh').addEventListener('click', async () => {
  $('#refresh').textContent = 'Refreshing…';
  try { await api('/refresh/', { method: 'POST' }); } catch (e) { /* ignore */ }
  await load();
  $('#refresh').textContent = 'Refresh';
});

tickClock();
setInterval(tickClock, 30000);
renderNotes();
load().catch((e) => { $('#briefing').textContent = `Failed to load: ${e.message}`; });
