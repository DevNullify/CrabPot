# Egress Protection & Prompt Injection Defense

CrabPot includes a multi-layered defense system to prevent prompt injection attacks from exfiltrating data, calling malicious endpoints, or executing unauthorized commands.

## Architecture

```
┌─────────────────── Host (CrabPot) ────────────────────────┐
│                                                            │
│  Egress Proxy (:9877)     ← enforces domain allowlist      │
│    ├── Domain gating      ← allow / deny / pending         │
│    ├── Secret scanner     ← 4-layer obfuscation-aware      │
│    └── Audit logger       ← all attempts logged             │
│                                                            │
│  Action Gate              ← human-in-the-loop              │
│    ├── Dashboard UI       ← approve/deny via WebSocket      │
│    └── CLI                ← crabpot approve <domain>        │
│                                                            │
│  Security Monitor                                          │
│    ├── Process watchdog   ← blocks shells, compilers        │
│    ├── Log scanner        ← catches curl/eval/install       │
│    └── Network auditor    ← catches proxy bypass            │
│                                                            │
│  ┌──────── Container (OpenClaw) ──────────────────────────┐│
│  │  HTTP_PROXY → host:9877                                 ││
│  │  HTTPS_PROXY → host:9877                                ││
│  │  All internet traffic → proxy → policy check            ││
│  └─────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────┘
```

## How It Works

### Layer 1: Egress Proxy (Network Level)

All HTTP/HTTPS traffic from the container is routed through CrabPot's egress proxy via `HTTP_PROXY`/`HTTPS_PROXY` environment variables.

The proxy enforces a **default-deny** domain allowlist:

| Domain Status | Behavior |
|---------------|----------|
| Allowlisted | Auto-allowed (e.g., `api.openai.com`) |
| Blocklisted | Auto-denied (e.g., `*.ngrok.io`, `webhook.site`) |
| Unknown | **Queued for human approval** |

```bash
# View the current allowlist
crabpot policy

# Add a domain permanently
crabpot policy add api.newservice.com

# Remove a domain
crabpot policy remove api.oldservice.com
```

The allowlist is at `~/.crabpot/config/egress-allowlist.txt`:

```
# One domain per line, wildcards supported
api.openai.com
*.anthropic.com
registry.npmjs.org

# Blocklist entries start with !
!*.ngrok.io
!webhook.site
```

### Layer 2: Human-in-the-Loop Approval

When the container tries to reach an unknown domain:

1. The egress proxy **blocks the request**
2. A WARNING alert fires: `"Approval needed: unknown.example.com:443"`
3. The dashboard shows an approve/deny prompt in real-time
4. You can also approve from the CLI:

```bash
# Session approval (valid until crabpot stop)
crabpot approve api.newservice.com

# Permanent approval (added to allowlist file)
crabpot approve api.newservice.com --permanent

# Deny a domain
crabpot deny suspicious-domain.com
```

If no decision is made within 60 seconds, the request is **auto-denied**.

### Layer 3: Secret Scanner (Obfuscation-Aware)

For plain HTTP requests (non-TLS), the proxy inspects request URLs and bodies. For HTTPS, domain-level blocking prevents exfiltration to unauthorized hosts.

The scanner has 4 detection layers:

| Layer | Detects | Examples |
|-------|---------|----------|
| **Pattern matching** | Known API key formats | `sk-...`, `AKIA...`, `ghp_...`, `Bearer ...` |
| **Deobfuscation** | Base64, hex, URL-encoded, reversed, dot-separated secrets | `c2stYWJjZGVm...` → decode → `sk-abcdef...` |
| **Entropy analysis** | High-entropy strings (>4.8 bits/char) | Random-looking tokens of 30+ chars |
| **Sensitive data** | Private IPs, SSH keys, /etc/passwd content, system info | `192.168.1.x`, `-----BEGIN RSA PRIVATE KEY-----` |

When a secret is detected, the request is **blocked immediately** and a CRITICAL alert fires.

### Layer 4: Log Pattern Scanner

The security monitor scans container logs in real-time for prompt injection indicators:

| Pattern | Severity | Trigger |
|---------|----------|---------|
| `curl`, `wget`, `fetch` + URL | CRITICAL | Outbound HTTP call attempted |
| `eval`, `exec`, `system`, `popen` | CRITICAL | Dynamic code execution |
| `apt install`, `pip install`, `npm install` | CRITICAL | Package installation |
| `env`, `printenv` + KEY/SECRET/TOKEN | CRITICAL | Environment variable enumeration |
| `/etc/passwd`, `/etc/shadow` | CRITICAL | Sensitive file access |
| `whoami`, `hostname`, `ifconfig` | WARNING | System reconnaissance |
| `base64 decode`, `xxd`, `openssl enc` | WARNING | Encoding/decoding tool usage |
| `chmod`, `chown` + permissions | WARNING | Permission change attempt |

CRITICAL patterns trigger **auto-pause** — the container is immediately frozen.

### Layer 5: Process Watchdog

The process monitor blocks execution of dangerous binaries:

- **Shells**: `sh`, `bash`, `dash`, `zsh`, `fish`, `csh`
- **Interpreters**: `python`, `perl`, `ruby`, `php`, `lua`
- **Network tools**: `nc`, `ncat`, `nmap`, `socat`, `telnet`
- **Build tools**: `gcc`, `cc`, `make`, `ld`

These binaries are removed from the Docker image at build time (Layer 9 of security hardening), and the process watchdog serves as a defense-in-depth check.

## Audit Trail

All egress attempts are logged:

```bash
# View the egress audit log
crabpot audit

# View last 100 entries
crabpot audit --last 100
```

The audit log shows: timestamp, domain, port, method, and decision (allow/deny/pending/blocked_secrets).

## Limitations & Defense-in-Depth

No single defense is perfect. CrabPot uses **defense-in-depth** — multiple independent layers where each catches what others might miss:

| Attack | Layer 1 (Proxy) | Layer 2 (HITL) | Layer 3 (Scanner) | Layer 4 (Logs) | Layer 5 (Process) |
|--------|:---:|:---:|:---:|:---:|:---:|
| Call attacker's webhook | Blocked | — | — | Caught | — |
| Exfil key to ngrok | Blocked | — | Caught | Caught | — |
| Base64-encode key in URL | Allowed domain only | Approved | Caught | Caught | — |
| Spawn reverse shell | — | — | — | Caught | Caught |
| Install malware via apt | — | — | — | Caught | Caught |
| DNS tunneling | Partially | — | — | — | — |
| Read /etc/passwd | — | — | — | Caught | — |

**Known limitations:**
- HTTPS payload inspection requires MITM (not implemented — would break certificate validation)
- DNS tunneling can bypass domain-level controls (mitigated by rate monitoring)
- If a prompt injection uses an already-allowed domain for exfiltration (e.g., sending secrets as an OpenAI prompt), only the secret scanner on HTTP catches this
- Proxy env vars can theoretically be unset by a process inside the container — the network auditor catches this

## Configuration Reference

### Egress allowlist format
```
# ~/.crabpot/config/egress-allowlist.txt
domain.com           # Exact match
*.example.com        # Wildcard (matches sub.example.com)
!blocked.com         # Explicit block (overrides allow rules)
```

### CLI commands
```bash
crabpot policy              # Show allowlist
crabpot policy add <domain> # Add to permanent allowlist
crabpot policy remove <domain>  # Remove from allowlist
crabpot approve <domain>    # Session-approve a pending domain
crabpot approve <domain> --permanent  # Permanently approve
crabpot deny <domain>       # Deny a domain
crabpot audit               # View egress audit log
```

### Dashboard
The web dashboard at `http://localhost:9876` shows:
- Pending approval requests (with approve/deny buttons)
- Real-time egress audit feed
- Blocked request alerts
