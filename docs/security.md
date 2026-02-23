# Security Model

CrabPot applies **12 layers of security hardening** to ensure that even if OpenClaw is compromised, the attacker cannot escape the sandbox, persist malware, or exfiltrate data.

## Why Sandbox OpenClaw?

OpenClaw is designed to be a powerful AI assistant. By nature, it:

- Executes shell commands on your machine
- Reads and writes files
- Runs arbitrary scripts
- Makes network connections

Running it unsandboxed on a personal machine exposes you to supply chain attacks, prompt injection exploits, and unintended command execution. Security researchers at Cisco, Microsoft, Sophos, and Aikido have all published warnings about running AI agents without isolation.

## The 12 Layers

### Layer 1: Read-Only Root Filesystem

```yaml
read_only: true
tmpfs:
  - /tmp:size=256m,noexec,nosuid
  - /run:size=64m,noexec,nosuid
```

The container's root filesystem is mounted read-only. This prevents malware from writing persistent binaries. The application still gets writable `/tmp` and `/run` via tmpfs (in-memory), but these are marked `noexec` (can't execute binaries from them) and `nosuid` (can't use SUID bits).

### Layer 2: Non-Root User

```yaml
user: "1000:1000"
```

The container runs as UID 1000 (non-root). Even if an attacker gains code execution, they cannot install packages, modify system files, or access root-only resources.

### Layer 3: Dropped Capabilities

```yaml
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE
```

Linux capabilities are fine-grained root privileges. We drop ALL of them and only add back `NET_BIND_SERVICE` (needed to bind port 18789). This prevents the container from using `CAP_SYS_ADMIN`, `CAP_NET_RAW`, `CAP_SYS_PTRACE`, and other dangerous capabilities.

### Layer 4: Seccomp Profile

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "syscalls": [
    { "names": ["read", "write", ...], "action": "SCMP_ACT_ALLOW" },
    { "names": ["mount", "ptrace", "reboot", ...], "action": "SCMP_ACT_ERRNO" }
  ]
}
```

The seccomp profile uses a **whitelist approach**: the default action is to deny all system calls, and we explicitly allow only the ~120 syscalls needed for the Node.js runtime. Dangerous syscalls are explicitly blocked:

- `mount`, `umount` — Filesystem manipulation
- `ptrace` — Process debugging (used for container escapes)
- `reboot` — System reboot
- `init_module`, `finit_module` — Kernel module loading
- `personality` — Can disable ASLR
- `kexec_load` — Kernel replacement
- `bpf` — Extended Berkeley Packet Filter

### Layer 5: No New Privileges

```yaml
security_opt:
  - no-new-privileges:true
```

Prevents processes inside the container from gaining additional privileges via SUID/SGID binaries or other escalation mechanisms.

### Layer 6: Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: "2"
      memory: 2g
pids_limit: 200
```

Hard limits on CPU, memory, and process count prevent denial-of-service attacks like fork bombs or memory exhaustion.

### Layer 7: Localhost-Only Port Binding

```yaml
ports:
  - "127.0.0.1:18789:18789"
```

The OpenClaw gateway port is bound to `127.0.0.1` only. It cannot be accessed from other machines on the network or from the internet.

### Layer 8: Inter-Container Communication Disabled

```yaml
networks:
  crabpot_net:
    driver_opts:
      com.docker.network.bridge.enable_icc: "false"
```

Even if other containers are running on the same Docker host, the CrabPot container cannot communicate with them.

### Layer 9: Dangerous Binaries Removed

The Dockerfile removes tools commonly used for lateral movement and data exfiltration:

- `curl`, `wget` — HTTP clients for downloading payloads
- `netcat` (`nc`, `ncat`) — Network swiss army knife
- `ssh` — Remote access
- `apt-get`, `dpkg` — Package managers (prevents installing tools)

SUID/SGID bits are also stripped from all binaries.

### Layer 10: Log Size Caps

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

Container logs are capped at 10MB per file with 3 rotated files (30MB total). This prevents log-based disk exhaustion attacks.

### Layer 11: 6-Channel Security Monitor

The security monitor runs 6 concurrent watcher threads:

| Channel | Interval | Watches For |
|---------|----------|-------------|
| Stats | 2s | CPU/memory spikes |
| Processes | 15s | Shell spawns (sh, bash, python, nc) |
| Network | 30s | Non-whitelisted outbound connections |
| Logs | Streaming | Error/crash/injection patterns |
| Health | 30s | Docker healthcheck failures |
| Events | Streaming | Container die/oom/kill events |

See the [Monitoring Guide](monitoring.md) for full details.

### Layer 12: Auto-Pause on Critical Alerts

When a CRITICAL alert is fired (suspicious process, consecutive health failures, container die/oom/kill), the monitor **immediately freezes the container** using Docker's cgroups freezer. This:

- Stops all processes mid-execution
- Preserves memory state for forensic analysis
- Requires manual `crabpot resume` to continue

## Threat Model

| Threat | Mitigation |
|--------|------------|
| Malware persistence | Read-only rootfs (Layer 1) |
| Privilege escalation | Non-root + no-new-privileges (Layers 2, 5) |
| Container escape via ptrace | Seccomp blocks ptrace (Layer 4) |
| Fork bomb / DoS | PID limit of 200 (Layer 6) |
| Data exfiltration via curl/wget | Binaries removed (Layer 9) |
| Lateral movement to other containers | ICC disabled (Layer 8) |
| Reverse shell | Network monitor + shell detection (Layers 2, 11) |
| Log bomb filling disk | Log caps (Layer 10) |
| Undetected compromise | 6-channel monitor + auto-pause (Layers 11, 12) |

## Limitations

CrabPot significantly raises the bar for attackers, but no sandbox is perfect:

- **Kernel exploits**: If the Linux kernel has a vulnerability, a sufficiently sophisticated attacker could escape. Keep your kernel updated.
- **Docker daemon**: The Docker daemon runs as root. A Docker vulnerability could be exploited. Consider running in rootless mode for additional protection.
- **Side channels**: Timing attacks and other side channels are not mitigated.
- **Authorized network access**: OpenClaw needs to reach external APIs (OpenAI, etc.) to function. This network access could theoretically be abused, though the network monitor flags unexpected connections.
