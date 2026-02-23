# Monitoring Guide

CrabPot runs a **6-channel security monitoring daemon** that watches the container in real-time and dispatches alerts through multiple channels.

## Monitor Channels

### 1. Stats Watcher (CPU/Memory)

- **Interval**: Every 2 seconds
- **Source**: Docker stats API
- **Alerts**:
  - `WARNING` — CPU > 80% sustained for 30 seconds
  - `WARNING` — Memory > 85% of limit
- **Data pushed**: CPU %, memory usage/limit, network I/O, PID count

Stats are streamed to the web dashboard via WebSocket for real-time visualization.

### 2. Process Watchdog

- **Interval**: Every 15 seconds
- **Source**: `docker top` (process list)
- **Alerts**:
  - `CRITICAL` — Shell process detected: `sh`, `bash`, `dash`, `zsh`
  - `CRITICAL` — Scripting runtime detected: `python`, `python3`, `perl`, `ruby`
  - `CRITICAL` — Network tool detected: `nc`, `ncat`
- **Auto-action**: CRITICAL triggers automatic container freeze

OpenClaw runs on Node.js. If a shell or scripting interpreter spawns inside the container, it indicates either a compromise or unauthorized tool execution. The monitor immediately freezes the container to contain the threat.

### 3. Network Connection Auditor

- **Interval**: Every 30 seconds
- **Source**: `ss -tunp` inside the container
- **Alerts**:
  - `WARNING` — Outbound connection to non-whitelisted address

Whitelisted addresses are:
- `127.0.0.1`, `0.0.0.0` (localhost)
- `::1`, `::` (IPv6 localhost)

Any outbound connection to an external IP triggers a warning. This helps detect C2 communication, data exfiltration, or unexpected API calls.

### 4. Log Pattern Scanner

- **Mode**: Real-time streaming
- **Source**: Container stdout/stderr
- **Patterns scanned**:
  - `ERROR`, `FATAL`, `CRITICAL` keywords → `WARNING`
  - `panic`, `segfault`, `core dump` → `WARNING`
  - `injection`, `unauthorized`, `forbidden` → `WARNING`
  - Shell spawn patterns (`exec`/`spawn` + `sh`/`bash`) → `WARNING`

The log scanner runs continuously, inspecting each log line as it's emitted. Long log lines are truncated to 200 characters in the alert.

### 5. Health Checker

- **Interval**: Every 30 seconds
- **Source**: Docker healthcheck status
- **Alerts**:
  - `CRITICAL` — Unhealthy for 2+ consecutive checks
- **Auto-action**: CRITICAL triggers automatic container freeze

The container runs a healthcheck that hits `http://localhost:18789/health` every 30 seconds. If this fails twice in a row, the application is likely crashed or unresponsive.

### 6. Docker Event Listener

- **Mode**: Real-time streaming
- **Source**: Docker daemon events (filtered to crabpot container)
- **Alerts**:
  - `CRITICAL` — Events: `die`, `oom`, `kill`
  - `WARNING` — Events: `restart`
  - `INFO` — Events: `start`

Docker events capture lifecycle changes that the other monitors can't see, like the container being killed by the OOM killer.

## Alert Dispatch Channels

When an alert fires, it's dispatched through **4 channels simultaneously**:

### Terminal

Colored output to stderr using Rich:
```
[CRITICAL] 14:23:01 processes: Suspicious process detected: /bin/bash
[WARNING]  14:23:15 stats: CPU at 92.3% for 30s
[INFO]     12:00:00 events: Container started
```

### Log File

JSON-lines format at `~/.crabpot/data/alerts.log`:
```json
{"severity":"WARNING","source":"stats","message":"CPU at 92.3% for 30s","timestamp":"14:23:15"}
```

View with:
```bash
crabpot alerts              # Recent 20 alerts
crabpot alerts --last 50    # Last 50
crabpot alerts --severity CRITICAL  # Only critical
```

### Web Dashboard

Alerts are pushed in real-time via WebSocket to the dashboard at `http://localhost:9876`. The alert feed shows severity-colored entries with timestamps.

### Windows Toast (WSL2 only)

CRITICAL alerts trigger a Windows toast notification via `powershell.exe`. This ensures you see critical events even if you're not watching the terminal or dashboard.

## Auto-Pause Behavior

When a CRITICAL alert fires, the monitor **automatically freezes the container**:

1. `docker pause crabpot` is called (cgroups freezer)
2. All processes inside the container stop executing
3. Memory state is preserved (no data loss)
4. A follow-up CRITICAL alert announces the auto-pause

**To resume after an auto-pause:**

```bash
crabpot resume
```

**Which alerts trigger auto-pause:**
- Suspicious process detected (shell, scripting runtime, network tool)
- 2+ consecutive unhealthy healthchecks
- Container die/oom/kill events (these also stop the container)

## Customizing Thresholds

The SecurityMonitor accepts these parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cpu_threshold` | 80.0 | CPU % that triggers warning |
| `memory_threshold` | 85.0 | Memory % that triggers warning |
| `cpu_sustain_seconds` | 30 | Seconds CPU must be above threshold |

Currently these are set in code. A future version will support configuration via `~/.crabpot/config/monitor.yml`.

## Pausing the Monitor

When you pause the container (`crabpot pause`), the polling-based watchers (stats, processes, network, health) pause as well. The streaming watchers (logs, events) continue to listen but won't receive data since the container is frozen.

When you resume (`crabpot resume`), all watchers resume their normal intervals.
