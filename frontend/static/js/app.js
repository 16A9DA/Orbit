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
  task: ['Task', 'Open task'],
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
}

async function loadTasks() {
  const tasks = await api('/tasks/');
  $('#task-list').innerHTML = tasks.map((t) => {
    const due = t.deadline ? new Date(t.deadline).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '';
    const done = t.status === 'done';
    return `<div class="task ${done ? 'done' : ''}" data-id="${t.id}">
      <input type="checkbox" class="t-check" ${done ? 'checked' : ''} />
      <span class="prio ${t.priority}"></span>
      <span class="t-title">${t.title}</span>
      <span class="task-due">${due}</span>
      <button class="t-del" title="Delete">&times;</button>
    </div>`;
  }).join('') || '<div class="svc-meta">No tasks yet. Add one above.</div>';
}

$('#task-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  await api('/tasks/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: $('#t-title').value.trim(),
      priority: $('#t-priority').value,
      deadline: $('#t-due').value || null,
      source: 'manual',
    }),
  });
  e.target.reset();
  await Promise.all([loadTasks(), load()]);
});

$('#task-list').addEventListener('click', async (e) => {
  const row = e.target.closest('.task');
  if (!row) return;
  const id = row.dataset.id;
  if (e.target.classList.contains('t-del')) {
    await api(`/tasks/${id}/`, { method: 'DELETE' });
  } else if (e.target.classList.contains('t-check')) {
    const status = e.target.checked ? 'done' : 'todo';
    await api(`/tasks/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
  } else {
    return openTask(id);
  }
  await Promise.all([loadTasks(), load()]);
});

let currentTask = null;

async function openTask(id) {
  const t = await api(`/tasks/${id}/`);
  currentTask = t;
  $('#d-title').value = t.title;
  $('#d-priority').value = t.priority;
  $('#d-status').value = t.status;
  $('#d-due').value = t.deadline ? t.deadline.slice(0, 10) : '';
  $('#d-notes').value = t.notes || '';
  $('#d-saved').textContent = '';
  show('task');
}

$('#d-save').addEventListener('click', async () => {
  if (!currentTask) return;
  await api(`/tasks/${currentTask.id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: $('#d-title').value.trim(),
      priority: $('#d-priority').value,
      status: $('#d-status').value,
      deadline: $('#d-due').value || null,
      notes: $('#d-notes').value,
    }),
  });
  $('#d-saved').textContent = 'Saved';
  await Promise.all([loadTasks(), load()]);
});

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

Promise.all([load(), loadTasks()]).catch((e) => console.error(e));
setInterval(() => load().catch(() => {}), 30000);
