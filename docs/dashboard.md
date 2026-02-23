# Dashboard Guide

CrabPot provides a **web dashboard** for real-time monitoring and control, accessible at `http://localhost:9876` while CrabPot is running.

## Accessing the Dashboard

The dashboard starts automatically with `crabpot start`. Open your browser to:

```
http://localhost:9876
```

The dashboard is bound to `127.0.0.1` only — it's not accessible from other machines.

## Dashboard Layout

### Header

- **State Badge** — Shows the container status (RUNNING, PAUSED, STOPPED)
- **WebSocket Indicator** — Green dot when connected, red when disconnected
- **Uptime** — How long the container has been running
- **Gateway Link** — Quick link to OpenClaw at `:18789`

### Resource Usage Panel

Real-time resource metrics with color-coded progress bars:

- **CPU** — Current percentage with sparkline chart (60-second history)
- **Memory** — Usage in MB with limit indicator
- **Network** — Total RX/TX bytes
- **PIDs** — Process count with limit indicator

Color coding:
- **Green**: < 60% utilization
- **Yellow**: 60–85% utilization
- **Red**: > 85% utilization

### Controls Panel

Buttons for container lifecycle management:

| Button | Action |
|--------|--------|
| **Start** | Start the container |
| **Stop** | Graceful shutdown |
| **Pause** | Freeze (zero CPU) |
| **Resume** | Unfreeze |
| **Destroy** | Full teardown (with confirmation) |

Also shows:
- **Health Status** — Current healthcheck result
- **Alert Counts** — Running totals by severity

### Alert Feed

Scrolling list of recent security alerts, color-coded by severity:

- **Red border** — CRITICAL alerts
- **Yellow border** — WARNING alerts
- **Blue border** — INFO alerts

Newest alerts appear at the top. The feed holds up to 100 entries.

### Log Panel

Live streaming container logs with:

- **Search/Filter** — Type in the filter box to highlight matching lines
- **Auto-scroll** — Automatically scrolls to newest entries
- **500-line buffer** — Older lines are automatically removed

### Network Connections Table

Shows active network connections inside the container:

| Column | Description |
|--------|-------------|
| Proto | TCP/UDP |
| Local | Local address:port |
| Remote | Remote address:port |
| State | Connection state (LISTEN, ESTABLISHED, etc.) |
| Status | **OK** (whitelisted) or **?** (unknown) |

## WebSocket Communication

The dashboard uses Socket.IO for real-time bidirectional communication:

| Event | Direction | Frequency | Content |
|-------|-----------|-----------|---------|
| `stats` | Server → Client | Every 2s | CPU, memory, network, PIDs |
| `alert` | Server → Client | On alert | Severity, source, message |
| `status` | Server → Client | Every 5s | Container state, health, uptime |
| `log` | Server → Client | Streaming | Log lines |
| `connections` | Server → Client | Every 30s | Network connections |
| `command` | Client → Server | On click | Control action (start/stop/etc.) |

## REST API

The dashboard also exposes a REST endpoint:

### `GET /api/status`

Returns a JSON snapshot of the current state:

```json
{
  "status": "running",
  "health": "healthy",
  "stats": {
    "cpu_percent": 12.3,
    "memory_usage": 536870912,
    "memory_limit": 2147483648,
    "memory_percent": 25.0,
    "network_rx": 1048576,
    "network_tx": 524288,
    "pids": 42
  },
  "alert_counts": {
    "CRITICAL": 0,
    "WARNING": 2,
    "INFO": 5
  },
  "uptime": "2h 34m 12s"
}
```

## Auto-Reconnect

If the WebSocket connection drops (e.g., CrabPot is restarted), the dashboard automatically reconnects. The connection indicator in the header changes to red during disconnection and back to green when reconnected.

## Browser Compatibility

The dashboard works in any modern browser that supports WebSocket:

- Chrome 49+
- Firefox 44+
- Safari 10+
- Edge 12+
