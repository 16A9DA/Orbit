const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

async function api(path, opts) {
  const r = await fetch(`/api${path}`, opts);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

const fmtTime = (iso) =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

const TITLES = {
  home: ['Overview', 'Your systems at a glance'],
  services: ['Services', 'Monitored infrastructure'],
  alerts: ['Alerts', 'Active issues'],
  tasks: ['Tasks', 'What needs doing'],
  activity: ['Activity', 'Recent events'],
  assistant: ['Assistant', 'Local AI over your data'],
};

function show(view) {
  $$('.view').forEach((v) => v.classList.add('hidden'));
  $(`#view-${view}`).classList.remove('hidden');
  $$('.menu-item').forEach((m) => m.classList.toggle('active', m.dataset.view === view));
  const [t, s] = TITLES[view] || TITLES.home;
  $('#page-title').textContent = t;
  $('#page-sub').textContent = s;
  window.scrollTo({ top: 0 });
}

// Any element with data-view navigates (menu items, widgets, back buttons).
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-view]');
  if (el) show(el.dataset.view);
});

function renderWidgets(c) {
  $('[data-w="services"]').textContent = c.services;
  $('[data-w="alerts"]').textContent = c.alerts_critical + c.alerts_warning;
  $('[data-w="tasks_open"]').textContent = c.tasks_open;
  $('#w-services-foot').textContent = c.degraded ? `${c.degraded} degraded` : 'all operational';
}

function renderServices(services) {
  $('#service-grid').innerHTML = services.map((s) => {
    const meta = Object.entries(s.metadata || {})
      .filter(([k]) => !['mock', 'id', 'error'].includes(k))
      .slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(' · ');
    return `<div class="svc">
      <div class="svc-top"><span class="svc-name">${s.name}</span>
      <span class="badge ${s.status}">${s.status}</span></div>
      <div class="svc-meta">${meta || s.type}</div></div>`;
  }).join('') || '<div class="svc-meta">No services. Hit Refresh.</div>';
}

function renderRows(el, rows, mapper) {
  el.innerHTML = rows.map(mapper).join('') || '<div class="svc-meta">Nothing here.</div>';
}

function renderAll(data) {
  renderWidgets(data.counts);
  renderServices(data.services);
  renderRows($('#alerts-list'), data.alerts, (a) => `
    <div class="row sev-${a.severity}"><span class="row-time">${fmtTime(a.created_at)}</span>
    <span class="row-tag">${a.severity}</span><span>${a.title}</span></div>`);
  renderRows($('#activity-list'), data.activity, (a) => `
    <div class="row"><span class="row-time">${fmtTime(a.timestamp)}</span>
    <span class="row-tag">${a.service}</span><span>${a.event}</span></div>`);
  $('#task-list').innerHTML = data.tasks.map((t) => {
    const due = t.deadline ? new Date(t.deadline).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '';
    return `<div class="task"><span class="prio ${t.priority}"></span><span>${t.title}</span>
      <span class="task-due">${due}</span></div>`;
  }).join('') || '<div class="svc-meta">No open tasks.</div>';
}

async function load() {
  renderAll(await api('/summary/'));
}

$('#refresh').addEventListener('click', async (e) => {
  e.target.textContent = 'Syncing…';
  try { await api('/refresh/', { method: 'POST' }); await load(); }
  finally { e.target.textContent = 'Refresh'; }
});

$('#assistant-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#assistant-input');
  const q = input.value.trim();
  if (!q) return;
  const log = $('#assistant-log');
  log.insertAdjacentHTML('beforeend', `<div class="msg user">${q}</div>`);
  input.value = '';
  log.insertAdjacentHTML('beforeend', `<div class="msg bot" id="pending">Thinking…</div>`);
  log.scrollTop = log.scrollHeight;
  try {
    const { answer } = await api('/assistant/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    });
    $('#pending').textContent = answer;
  } catch {
    $('#pending').textContent = 'Assistant unavailable.';
  }
  $('#pending').removeAttribute('id');
  log.scrollTop = log.scrollHeight;
});

load().catch((e) => console.error(e));
setInterval(() => load().catch(() => {}), 30000);
