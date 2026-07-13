const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

async function api(path, opts) {
  const r = await fetch(`/api${path}`, opts);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

function spark(el, seed) {
  // ponytail: no historical series yet, render a deterministic pseudo-sparkline.
  el.innerHTML = '';
  for (let i = 0; i < 16; i++) {
    const b = document.createElement('span');
    const h = 20 + ((seed * 7 + i * i * 13) % 80);
    b.style.height = `${h}%`;
    el.appendChild(b);
  }
}

function metricCards(counts) {
  $$('[data-metric]').forEach((el) => {
    const v = counts[el.dataset.metric] ?? 0;
    el.textContent = v;
  });
  $('#m-critical').classList.toggle('hot', (counts.alerts_critical ?? 0) > 0);
  $$('[data-spark]').forEach((el, i) => spark(el, i + 1));
}

function renderServices(services) {
  const grid = $('#service-grid');
  grid.innerHTML = services.map((s) => {
    const meta = Object.entries(s.metadata || {})
      .filter(([k]) => !['mock', 'id', 'error'].includes(k))
      .slice(0, 2)
      .map(([k, v]) => `${k}: ${v}`)
      .join(' · ');
    return `<div class="svc">
      <div class="svc-top">
        <span class="svc-name">${s.name}</span>
        <span class="badge ${s.status}">${s.status}</span>
      </div>
      <div class="svc-meta">${meta || s.type}</div>
    </div>`;
  }).join('') || '<div class="svc-meta">No services yet. Hit Refresh.</div>';
}

function renderTelemetry(el, rows, mapper) {
  el.innerHTML = rows.map(mapper).join('') || '<div class="svc-meta">Empty.</div>';
}

function renderAlerts(alerts) {
  renderTelemetry($('#alerts-list'), alerts, (a) => `
    <div class="tl-row tl-sev-${a.severity}">
      <span class="tl-time">${fmtTime(a.created_at)}</span>
      <span class="tl-tag">${a.severity}</span>
      <span>${a.title}</span>
    </div>`);
}

function renderActivity(items) {
  renderTelemetry($('#activity-list'), items, (a) => `
    <div class="tl-row">
      <span class="tl-time">${fmtTime(a.timestamp)}</span>
      <span class="tl-tag">${a.service}</span>
      <span>${a.event}</span>
    </div>`);
}

function renderTasks(tasks) {
  $('#task-list').innerHTML = tasks.map((t) => {
    const due = t.deadline ? new Date(t.deadline).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '';
    return `<div class="task">
      <span class="prio ${t.priority}"></span>
      <span>${t.title}</span>
      <span class="task-due label-mono">${due}</span>
    </div>`;
  }).join('') || '<div class="svc-meta">No open tasks.</div>';
}

function renderHeatmap() {
  const hm = $('#heatmap');
  hm.innerHTML = '';
  for (let i = 0; i < 98; i++) {
    const c = document.createElement('div');
    c.className = 'hm-cell';
    const lvl = Math.random();
    c.style.background = `rgba(111,210,255,${(0.05 + lvl * 0.5).toFixed(2)})`;
    hm.appendChild(c);
  }
}

async function load() {
  const data = await api('/summary/');
  metricCards(data.counts);
  $('#chip-services').textContent = data.counts.services;
  $('#chip-alerts').textContent = data.counts.alerts_critical + data.counts.alerts_warning;
  renderServices(data.services);
  renderAlerts(data.alerts);
  renderTasks(data.tasks);
  renderActivity(data.activity);
  renderHeatmap();
}

function clock() {
  $('#clock').textContent = `LIVE · ${new Date().toLocaleString([], { hour12: false })}`;
}

$('#refresh').addEventListener('click', async (e) => {
  e.target.textContent = 'Syncing…';
  try {
    await api('/refresh/', { method: 'POST' });
    await load();
  } finally {
    e.target.textContent = 'Refresh';
  }
});

$('#assistant-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#assistant-input');
  const q = input.value.trim();
  if (!q) return;
  const log = $('#assistant-log');
  log.insertAdjacentHTML('beforeend', `<div class="ai-msg user">${q}</div>`);
  input.value = '';
  log.scrollTop = log.scrollHeight;
  try {
    const { answer } = await api('/assistant/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    });
    log.insertAdjacentHTML('beforeend', `<div class="ai-msg bot">${answer}</div>`);
  } catch {
    log.insertAdjacentHTML('beforeend', `<div class="ai-msg bot">Assistant unavailable.</div>`);
  }
  log.scrollTop = log.scrollHeight;
});

$$('.nav-item').forEach((n) => n.addEventListener('click', () => {
  $$('.nav-item').forEach((x) => x.classList.remove('active'));
  n.classList.add('active');
  const map = { services: '#services-card', alerts: '#alerts-card', tasks: '#tasks-card', activity: '#activity-card' };
  const target = map[n.dataset.view];
  if (target) $(target).scrollIntoView({ behavior: 'smooth', block: 'center' });
  else window.scrollTo({ top: 0, behavior: 'smooth' });
}));

clock();
setInterval(clock, 1000);
load().catch((e) => console.error(e));
setInterval(() => load().catch(() => {}), 30000);
