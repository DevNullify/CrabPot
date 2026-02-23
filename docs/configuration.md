# Configuration

CrabPot v2.0 uses a YAML configuration file at `~/.crabpot/crabpot.yml` to control all settings. This file is created by `crabpot init` and can be edited manually or via `crabpot config edit`.

## Config File Location

```
~/.crabpot/crabpot.yml
```

Override with the `CRABPOT_HOME` environment variable:

```bash
export CRABPOT_HOME=/opt/crabpot
# Config will be at /opt/crabpot/crabpot.yml
```

## Full Config Reference

```yaml
# Deployment target: 'docker' or 'wsl2'
target: docker

openclaw:
  source: image          # 'image' (pull from registry) or 'build' (from source)
  image_tag: latest      # Docker image tag: 'latest', 'v1.2.3', etc.
  repo_url: https://github.com/openclaw/openclaw.git
  repo_ref: main         # Branch, tag, or commit (when source=build)

security:
  preset: standard       # 'minimal', 'standard', or 'paranoid'
  overrides:             # Per-feature overrides (null = inherit from preset)
    read_only_rootfs: null
    drop_all_caps: null
    seccomp_profile: null
    no_new_privileges: null
    resource_limits: null
    pid_limit: null
    egress_proxy: null
    secret_scanner: null
    process_watchdog: null
    log_scanner: null
    network_auditor: null
    hardened_image: null
    auto_pause_on_critical: null

resources:               # Resource overrides (null = inherit from preset)
  cpu_limit: null
  memory_limit: null
  pids_limit: null

egress:
  proxy_port: 9877

dashboard:
  port: 9876

wsl2:                    # Only used when target=wsl2
  distro_name: CrabPot
  base_image: ubuntu:22.04
```

## Security Presets

Three named presets control which security layers are active:

| Feature | minimal | standard | paranoid |
|---------|---------|----------|----------|
| read_only_rootfs | off | **on** | **on** |
| drop_all_caps | off | **on** | **on** |
| seccomp_profile | off | **on** | **on** |
| no_new_privileges | off | **on** | **on** |
| resource_limits | off | **on** | **on** |
| pid_limit | off | **on** | **on** |
| egress_proxy | off | **on** | **on** |
| secret_scanner | off | **on** | **on** |
| process_watchdog | off | off | **on** |
| log_scanner | off | **on** | **on** |
| network_auditor | off | off | **on** |
| hardened_image | off | off | **on** |
| auto_pause_on_critical | off | **on** | **on** |

Default resource limits per preset:

| Resource | minimal | standard | paranoid |
|----------|---------|----------|----------|
| CPU | 4 cores | 2 cores | 1 core |
| Memory | 4 GB | 2 GB | 1 GB |
| PIDs | 500 | 200 | 100 |

### Choosing a Preset

- **minimal** — No security hardening. Fastest setup, suitable for development and testing where you trust the workload.
- **standard** — Recommended for most users. Applies filesystem, capability, seccomp, resource, and egress hardening. Monitors logs and auto-pauses on critical alerts.
- **paranoid** — Maximum security. Enables all monitoring channels (process watchdog, network auditor), strips binaries from the image, and applies the tightest resource limits.

### Per-Feature Overrides

Override individual features beyond what the preset provides:

```yaml
security:
  preset: standard
  overrides:
    process_watchdog: true    # Enable process watchdog (off in standard)
    hardened_image: true      # Enable image stripping (off in standard)
    auto_pause_on_critical: false  # Disable auto-pause
```

Set a value to `null` (or omit it) to inherit from the preset.

### Resource Overrides

Override resource limits independently of the preset:

```yaml
resources:
  cpu_limit: "3"       # Override CPU (preset standard default: "2")
  memory_limit: "4g"   # Override memory (preset standard default: "2g")
  pids_limit: null     # Inherit from preset (200 for standard)
```

## Managing Configuration

```bash
crabpot config          # Show current configuration
crabpot config edit     # Open crabpot.yml in $EDITOR
crabpot config reset    # Reset to defaults
```

## Deployment Targets

### Docker (default)

Uses Docker containers with Docker Compose. Requires Docker Engine with the Compose plugin.

```yaml
target: docker
```

### WSL2

Uses a native WSL2 distribution. Requires Windows with WSL2 enabled. Security is applied via systemd, cgroups, and iptables instead of Docker primitives.

```yaml
target: wsl2
wsl2:
  distro_name: CrabPot
  base_image: ubuntu:22.04
```

## Egress Policy

The egress proxy (when enabled) enforces a domain allowlist for all outbound network traffic. Manage it with:

```bash
crabpot policy              # Show current allowlist
crabpot policy add api.openai.com    # Add to permanent allowlist
crabpot policy remove api.openai.com # Remove from allowlist
crabpot approve example.com          # Session-only approval
crabpot deny example.com             # Session-only denial
crabpot audit                        # View egress audit log
```

The policy file is at `~/.crabpot/config/egress-allowlist.txt`.
