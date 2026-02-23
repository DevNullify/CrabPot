"""Embedded HTML/CSS/JS for the CrabPot web dashboard."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CrabPot Dashboard</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg-primary: #1a1a2e;
    --bg-secondary: #16213e;
    --bg-card: #0f3460;
    --accent: #e94560;
    --accent-green: #00d4aa;
    --accent-yellow: #ffc107;
    --accent-blue: #4fc3f7;
    --text-primary: #e0e0e0;
    --text-secondary: #a0a0b0;
    --border: #2a2a4a;
    --font: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font);
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    font-size: 14px;
  }

  .header {
    background: var(--bg-secondary);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 2px solid var(--accent);
  }

  .header h1 {
    font-size: 20px;
    color: var(--accent);
    letter-spacing: 2px;
  }

  .header-right {
    display: flex;
    gap: 16px;
    align-items: center;
  }

  .badge {
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .badge-running { background: var(--accent-green); color: #000; }
  .badge-paused { background: var(--accent-yellow); color: #000; }
  .badge-stopped { background: var(--accent); color: #fff; }
  .badge-unknown { background: var(--border); color: var(--text-secondary); }

  .uptime { color: var(--text-secondary); font-size: 12px; }

  .links a {
    color: var(--accent-blue);
    text-decoration: none;
    font-size: 12px;
    margin-left: 12px;
  }
  .links a:hover { text-decoration: underline; }

  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    padding: 16px 24px;
    max-width: 1400px;
    margin: 0 auto;
  }

  .card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
  }

  .card-title {
    font-size: 12px;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
  }

  .stat-row {
    display: flex;
    align-items: center;
    margin-bottom: 10px;
    gap: 12px;
  }

  .stat-label {
    width: 60px;
    color: var(--text-secondary);
    font-size: 12px;
  }

  .bar-container {
    flex: 1;
    height: 20px;
    background: var(--bg-primary);
    border-radius: 4px;
    overflow: hidden;
    position: relative;
  }

  .bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease, background 0.3s ease;
  }

  .bar-fill.green { background: var(--accent-green); }
  .bar-fill.yellow { background: var(--accent-yellow); }
  .bar-fill.red { background: var(--accent); }

  .stat-value {
    width: 120px;
    text-align: right;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .controls {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .btn {
    padding: 8px 16px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-card);
    color: var(--text-primary);
    cursor: pointer;
    font-family: var(--font);
    font-size: 12px;
    transition: all 0.2s;
  }

  .btn:hover { border-color: var(--accent-blue); color: var(--accent-blue); }
  .btn-danger { border-color: var(--accent); color: var(--accent); }
  .btn-danger:hover { background: var(--accent); color: #fff; }
  .btn-success { border-color: var(--accent-green); color: var(--accent-green); }
  .btn-success:hover { background: var(--accent-green); color: #000; }

  .alert-feed {
    max-height: 300px;
    overflow-y: auto;
    font-size: 12px;
  }

  .alert-item {
    padding: 6px 8px;
    border-left: 3px solid var(--border);
    margin-bottom: 4px;
    background: rgba(0,0,0,0.2);
    border-radius: 0 4px 4px 0;
  }

  .alert-critical { border-left-color: var(--accent); }
  .alert-warning { border-left-color: var(--accent-yellow); }
  .alert-info { border-left-color: var(--accent-blue); }

  .alert-time { color: var(--text-secondary); margin-right: 8px; }
  .alert-sev { font-weight: bold; margin-right: 8px; }
  .sev-critical { color: var(--accent); }
  .sev-warning { color: var(--accent-yellow); }
  .sev-info { color: var(--accent-blue); }

  .log-panel {
    background: #0a0a1a;
    border-radius: 4px;
    padding: 8px;
    max-height: 300px;
    overflow-y: auto;
    font-size: 11px;
    line-height: 1.6;
    color: var(--text-secondary);
  }

  .log-panel .log-line { white-space: pre-wrap; word-break: break-all; }

  .log-controls {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
  }

  .log-controls input {
    flex: 1;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 4px 8px;
    color: var(--text-primary);
    font-family: var(--font);
    font-size: 12px;
  }

  .conn-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }

  .conn-table th {
    text-align: left;
    color: var(--accent);
    border-bottom: 1px solid var(--border);
    padding: 6px 8px;
    font-size: 11px;
  }

  .conn-table td {
    padding: 4px 8px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }

  .conn-whitelisted { color: var(--accent-green); }
  .conn-unknown { color: var(--accent-yellow); }

  .sparkline-container {
    height: 60px;
    margin-top: 8px;
  }

  .full-width { grid-column: 1 / -1; }

  .connection-status {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 8px;
  }

  .ws-connected { background: var(--accent-green); }
  .ws-disconnected { background: var(--accent); }

  @media (max-width: 900px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<div class="header">
  <h1>CRABPOT</h1>
  <div class="header-right">
    <span class="connection-status ws-disconnected" id="ws-status"></span>
    <span class="badge badge-unknown" id="state-badge">CONNECTING</span>
    <span class="uptime" id="uptime">--</span>
    <span class="links">
      <a href="http://localhost:18789" target="_blank">Gateway UI</a>
    </span>
  </div>
</div>

<div class="grid">

  <!-- Stats Panel -->
  <div class="card">
    <div class="card-title">Resource Usage</div>
    <div class="stat-row">
      <span class="stat-label">CPU</span>
      <div class="bar-container">
        <div class="bar-fill green" id="cpu-bar" style="width: 0%"></div>
      </div>
      <span class="stat-value" id="cpu-val">0% / 200%</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Memory</span>
      <div class="bar-container">
        <div class="bar-fill green" id="mem-bar" style="width: 0%"></div>
      </div>
      <span class="stat-value" id="mem-val">0MB / 0MB</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Net</span>
      <div class="bar-container" style="background: transparent;">
        <span id="net-val" style="font-size:12px; color: var(--text-secondary);">RX 0MB / TX 0MB</span>
      </div>
    </div>
    <div class="stat-row">
      <span class="stat-label">PIDs</span>
      <div class="bar-container">
        <div class="bar-fill green" id="pid-bar" style="width: 0%"></div>
      </div>
      <span class="stat-value" id="pid-val">0 / 200</span>
    </div>
    <div class="sparkline-container">
      <canvas id="cpu-chart"></canvas>
    </div>
  </div>

  <!-- Controls Panel -->
  <div class="card">
    <div class="card-title">Controls</div>
    <div class="controls">
      <button class="btn btn-success" onclick="sendCmd('start')">Start</button>
      <button class="btn" onclick="sendCmd('stop')">Stop</button>
      <button class="btn" onclick="sendCmd('pause')">Pause</button>
      <button class="btn" onclick="sendCmd('resume')">Resume</button>
      <button class="btn btn-danger" onclick="sendCmd('destroy')">Destroy</button>
    </div>
    <div style="margin-top: 16px;">
      <div class="card-title">Health</div>
      <span id="health-status" style="font-size: 14px;">--</span>
    </div>
    <div style="margin-top: 16px;">
      <div class="card-title">Alert Counts</div>
      <span style="font-size: 12px;">
        <span class="sev-critical" id="count-critical">0</span> critical &nbsp;
        <span class="sev-warning" id="count-warning">0</span> warning &nbsp;
        <span class="sev-info" id="count-info">0</span> info
      </span>
    </div>
  </div>

  <!-- Alert Feed -->
  <div class="card">
    <div class="card-title">Alert Feed</div>
    <div class="alert-feed" id="alert-feed"></div>
  </div>

  <!-- Log Panel -->
  <div class="card">
    <div class="card-title">Container Logs</div>
    <div class="log-controls">
      <input type="text" id="log-filter" placeholder="Filter logs..." oninput="filterLogs()">
    </div>
    <div class="log-panel" id="log-panel"></div>
  </div>

  <!-- Connections Table -->
  <div class="card full-width">
    <div class="card-title">Network Connections</div>
    <table class="conn-table">
      <thead>
        <tr>
          <th>Proto</th><th>Local</th><th>Remote</th><th>State</th><th>Status</th>
        </tr>
      </thead>
      <tbody id="conn-tbody"></tbody>
    </table>
  </div>

</div>

<script>
const socket = io({
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionAttempts: Infinity
});

// CPU sparkline data
const cpuHistory = [];
const MAX_POINTS = 60;
let cpuChart;

function initChart() {
  const ctx = document.getElementById('cpu-chart').getContext('2d');
  cpuChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        data: cpuHistory,
        borderColor: '#e94560',
        backgroundColor: 'rgba(233, 69, 96, 0.1)',
        borderWidth: 1.5,
        fill: true,
        tension: 0.3,
        pointRadius: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { display: false, min: 0, max: 200 }
      }
    }
  });
}

function barColor(pct) {
  if (pct > 85) return 'red';
  if (pct > 60) return 'yellow';
  return 'green';
}

function fmtBytes(b) {
  if (b >= 1073741824) return (b / 1073741824).toFixed(1) + 'GB';
  if (b >= 1048576) return (b / 1048576).toFixed(1) + 'MB';
  if (b >= 1024) return (b / 1024).toFixed(1) + 'KB';
  return b + 'B';
}

function createTextEl(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

// WebSocket handlers
socket.on('connect', function() {
  document.getElementById('ws-status').className = 'connection-status ws-connected';
});

socket.on('disconnect', function() {
  document.getElementById('ws-status').className = 'connection-status ws-disconnected';
  document.getElementById('state-badge').className = 'badge badge-unknown';
  document.getElementById('state-badge').textContent = 'DISCONNECTED';
});

socket.on('stats', function(data) {
  var cpu = data.cpu_percent || 0;
  var memUsage = data.memory_usage || 0;
  var memLimit = data.memory_limit || 1;
  var memPct = data.memory_percent || 0;
  var pids = data.pids || 0;
  var rx = data.network_rx || 0;
  var tx = data.network_tx || 0;

  // CPU
  var cpuBar = document.getElementById('cpu-bar');
  cpuBar.style.width = Math.min(cpu / 2, 100) + '%';
  cpuBar.className = 'bar-fill ' + barColor(cpu / 2);
  document.getElementById('cpu-val').textContent = cpu.toFixed(1) + '% / 200%';

  // Memory
  var memBar = document.getElementById('mem-bar');
  memBar.style.width = memPct + '%';
  memBar.className = 'bar-fill ' + barColor(memPct);
  document.getElementById('mem-val').textContent = fmtBytes(memUsage) + ' / ' + fmtBytes(memLimit);

  // Network
  document.getElementById('net-val').textContent = 'RX ' + fmtBytes(rx) + ' / TX ' + fmtBytes(tx);

  // PIDs
  var pidPct = (pids / 200) * 100;
  var pidBar = document.getElementById('pid-bar');
  pidBar.style.width = pidPct + '%';
  pidBar.className = 'bar-fill ' + barColor(pidPct);
  document.getElementById('pid-val').textContent = pids + ' / 200';

  // Sparkline
  cpuHistory.push(cpu);
  if (cpuHistory.length > MAX_POINTS) cpuHistory.shift();
  if (cpuChart) {
    cpuChart.data.labels = cpuHistory.map(function(_, i) { return i; });
    cpuChart.update('none');
  }
});

socket.on('alert', function(data) {
  addAlert(data);
  updateCounts(data.severity);
});

socket.on('status', function(data) {
  var badge = document.getElementById('state-badge');
  var status = data.status || 'unknown';
  badge.textContent = status.toUpperCase();
  badge.className = 'badge badge-' + (status === 'running' ? 'running' :
    status === 'paused' ? 'paused' : status === 'exited' ? 'stopped' : 'unknown');

  if (data.health) {
    var h = document.getElementById('health-status');
    h.textContent = data.health === 'healthy' ? 'healthy' : data.health;
    h.style.color = data.health === 'healthy' ? 'var(--accent-green)' : 'var(--accent-yellow)';
  }

  if (data.uptime) {
    document.getElementById('uptime').textContent = data.uptime;
  }
});

socket.on('log', function(data) {
  var panel = document.getElementById('log-panel');
  var div = document.createElement('div');
  div.className = 'log-line';
  div.textContent = data.line;
  panel.appendChild(div);
  while (panel.children.length > 500) panel.removeChild(panel.firstChild);
  panel.scrollTop = panel.scrollHeight;
});

socket.on('connections', function(data) {
  var tbody = document.getElementById('conn-tbody');
  // Clear existing rows safely
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  (data.connections || []).forEach(function(conn) {
    var tr = document.createElement('tr');
    tr.appendChild(createTextEl('td', conn.proto));
    tr.appendChild(createTextEl('td', conn.local));
    tr.appendChild(createTextEl('td', conn.remote));
    tr.appendChild(createTextEl('td', conn.state));
    tr.appendChild(createTextEl('td', conn.whitelisted ? 'OK' : '?',
      conn.whitelisted ? 'conn-whitelisted' : 'conn-unknown'));
    tbody.appendChild(tr);
  });
});

function addAlert(alert) {
  var feed = document.getElementById('alert-feed');
  var div = document.createElement('div');
  var sev = (alert.severity || 'info').toLowerCase();
  div.className = 'alert-item alert-' + sev;

  var timeSpan = createTextEl('span', alert.timestamp || '', 'alert-time');
  var sevSpan = createTextEl('span', alert.severity || '', 'alert-sev sev-' + sev);
  var msgSpan = createTextEl('span', (alert.source || '') + ': ' + (alert.message || ''));

  div.appendChild(timeSpan);
  div.appendChild(sevSpan);
  div.appendChild(msgSpan);

  feed.insertBefore(div, feed.firstChild);
  while (feed.children.length > 100) feed.removeChild(feed.lastChild);
}

function updateCounts(severity) {
  var id = 'count-' + severity.toLowerCase();
  var el = document.getElementById(id);
  if (el) el.textContent = parseInt(el.textContent || '0') + 1;
}

function sendCmd(cmd) {
  if (cmd === 'destroy' && !confirm('Destroy CrabPot container and all data?')) return;
  socket.emit('command', { action: cmd });
}

function filterLogs() {
  var filter = document.getElementById('log-filter').value.toLowerCase();
  var lines = document.querySelectorAll('#log-panel .log-line');
  lines.forEach(function(line) {
    line.style.display = line.textContent.toLowerCase().includes(filter) ? '' : 'none';
  });
}

// Initialize
document.addEventListener('DOMContentLoaded', initChart);
</script>
</body>
</html>
"""
