"""CLI command handlers for CrabPot."""

import os
import shutil
import signal
import subprocess
import sys
import threading

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from crabpot import __version__
from crabpot.paths import (
    CONFIG_DIR,
    CONFIG_FILE,
    CRABPOT_HOME,
    DATA_DIR,
    EGRESS_POLICY_FILE,
)

console = Console()


def dispatch(args):
    """Route parsed CLI args to the appropriate handler."""
    commands = {
        "init": cmd_init,
        "setup": cmd_setup,
        "start": cmd_start,
        "stop": cmd_stop,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "tui": cmd_tui,
        "status": cmd_status,
        "logs": cmd_logs,
        "alerts": cmd_alerts,
        "shell": cmd_shell,
        "destroy": cmd_destroy,
        "uninstall": cmd_uninstall,
        "policy": cmd_policy,
        "approve": cmd_approve,
        "deny": cmd_deny,
        "audit": cmd_audit,
        "config": cmd_config,
    }
    handler = commands.get(args.command)
    if handler is None:
        console.print(f"[red]Unknown command: {args.command}[/red]")
        sys.exit(1)
    try:
        handler(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# ── Init wizard ────────────────────────────────────────────────────────


def cmd_init(args):
    """Interactive setup wizard: choose target, preset, openclaw version, check prereqs."""
    from crabpot.config import (
        CrabPotConfig,
        OpenClawConfig,
        SecurityConfig,
        save_config,
        validate_config,
    )

    console.print(f"[cyan]CrabPot v{__version__} — Setup Wizard[/cyan]\n")

    non_interactive = getattr(args, "non_interactive", False)

    # Step 1/4: Deployment target
    target = getattr(args, "target", None)
    if not target:
        if non_interactive:
            target = "docker"
        else:
            target = Prompt.ask(
                "[bold]Step 1/4:[/bold] Deployment target",
                choices=["docker", "wsl2"],
                default="docker",
            )
    console.print(f"  Target: [cyan]{target}[/cyan]")

    # Step 2/4: OpenClaw version
    openclaw_tag = getattr(args, "openclaw_tag", None)
    if not openclaw_tag:
        if non_interactive:
            openclaw_tag = "latest"
        else:
            openclaw_tag = Prompt.ask(
                "[bold]Step 2/4:[/bold] OpenClaw image tag",
                default="latest",
            )
    console.print(f"  OpenClaw tag: [cyan]{openclaw_tag}[/cyan]")

    # Step 3/4: Security preset
    preset = getattr(args, "preset", None)
    if not preset:
        if non_interactive:
            preset = "standard"
        else:
            console.print(
                "\n[bold]Step 3/4:[/bold] Security level\n"
                "  [green]minimal[/green]  — No hardening (fastest setup, for development)\n"
                "  [yellow]standard[/yellow] — Recommended "
                "(read-only rootfs, caps, seccomp, egress proxy)\n"
                "  [red]paranoid[/red]  — Maximum "
                "(all hardening + image stripping + all monitors)\n"
            )
            preset = Prompt.ask(
                "  Choose preset",
                choices=["minimal", "standard", "paranoid"],
                default="standard",
            )
    console.print(f"  Security preset: [cyan]{preset}[/cyan]")

    # Step 4/4: Prerequisites check
    console.print("\n[bold]Step 4/4:[/bold] Checking prerequisites...")

    if target == "docker":
        _check_docker_prerequisites()
    else:
        _check_wsl2_prerequisites()

    # Build and save config
    config = CrabPotConfig(
        target=target,
        openclaw=OpenClawConfig(image_tag=openclaw_tag),
        security=SecurityConfig(preset=preset),
    )

    errors = validate_config(config)
    if errors:
        for e in errors:
            console.print(f"[red]  {e}[/red]")
        sys.exit(1)

    # Ensure home dir exists
    for d in [CONFIG_DIR, DATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Write config file
    if CONFIG_FILE.exists() and not non_interactive:
        overwrite = Confirm.ask(
            f"\n[yellow]Config file already exists at {CONFIG_FILE}. Overwrite?[/yellow]",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]Keeping existing config.[/yellow]")
            console.print("Next: [cyan]crabpot setup[/cyan]")
            return

    save_config(config, config_path=CONFIG_FILE)
    console.print(f"\n[green]Config saved:[/green] {CONFIG_FILE}")
    console.print("Next: [cyan]crabpot setup[/cyan]")


def _check_docker_prerequisites():
    """Check Docker is installed and running."""
    from crabpot.docker_manager import DockerManager

    info = DockerManager.check_docker()

    if not info["installed"]:
        console.print("[red]  Docker is not installed.[/red]")
        console.print("  Install: https://docs.docker.com/engine/install/")
        sys.exit(1)
    console.print(f"  [green]Docker:[/green] {info['version']}")

    if not info["running"]:
        console.print("[red]  Docker daemon is not running.[/red]")
        console.print("  Start it with: sudo systemctl start docker")
        sys.exit(1)
    console.print("  [green]Docker daemon:[/green] running")

    if not info["compose"]:
        console.print("[red]  Docker Compose plugin not found.[/red]")
        console.print("  Install: sudo apt install docker-compose-plugin")
        sys.exit(1)
    console.print("  [green]Docker Compose:[/green] available")

    console.print(f"  [green]CrabPot home:[/green] {CRABPOT_HOME}")
    console.print("\n[green]  All prerequisites satisfied.[/green]")


def _check_wsl2_prerequisites():
    """Check WSL2 availability (basic check)."""
    try:
        result = subprocess.run(
            ["wsl", "--status"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            console.print("  [green]WSL2:[/green] available")
        else:
            console.print("[yellow]  WSL2 may not be available (non-zero exit).[/yellow]")
    except FileNotFoundError:
        console.print("[yellow]  WSL2 command not found. WSL2 mode requires Windows/WSL2.[/yellow]")
    except subprocess.TimeoutExpired:
        console.print("[yellow]  WSL2 check timed out.[/yellow]")

    console.print(f"  [green]CrabPot home:[/green] {CRABPOT_HOME}")


# ── Setup ──────────────────────────────────────────────────────────────


def cmd_setup(args):
    """Generate configs and build image based on crabpot.yml."""
    from crabpot.config import (
        CrabPotConfig,
        SecurityConfig,
        load_config,
        save_config,
        validate_config,
    )
    from crabpot.config_generator import ConfigGenerator
    from crabpot.docker_manager import DockerManager
    from crabpot.security_presets import resolve_profile

    console.print("[cyan]CrabPot Setup[/cyan]\n")

    # v1→v2 migration: detect existing setup without crabpot.yml
    if not CONFIG_FILE.exists() and (CONFIG_DIR / "docker-compose.yml").exists():
        console.print("[yellow]Detected v1 setup without crabpot.yml — migrating...[/yellow]")
        config = CrabPotConfig(
            security=SecurityConfig(
                preset="paranoid",
                overrides={"hardened_image": True},
            ),
        )
        save_config(config, config_path=CONFIG_FILE)
        console.print(
            f"[green]Created {CONFIG_FILE} "
            "(preset: paranoid, hardened_image: true)[/green]"
        )
        console.print("[dim]This matches v1's always-on security behavior.[/dim]\n")

    # Load config
    config = load_config()
    errors = validate_config(config)
    if errors:
        console.print("[red]Configuration errors:[/red]")
        for e in errors:
            console.print(f"  [red]{e}[/red]")
        console.print(f"\nFix config at: [cyan]{CONFIG_FILE}[/cyan]")
        sys.exit(1)

    # Resolve security profile
    resource_overrides = {}
    if config.resources.cpu_limit is not None:
        resource_overrides["cpu_limit"] = config.resources.cpu_limit
    if config.resources.memory_limit is not None:
        resource_overrides["memory_limit"] = config.resources.memory_limit
    if config.resources.pids_limit is not None:
        resource_overrides["pids_limit"] = config.resources.pids_limit

    profile, resources = resolve_profile(
        config.security.preset,
        overrides=config.security.overrides or None,
        resource_overrides=resource_overrides or None,
    )

    console.print(f"  Target: [cyan]{config.target}[/cyan]")
    console.print(f"  Preset: [cyan]{config.security.preset}[/cyan]")
    console.print(f"  OpenClaw: [cyan]{config.openclaw.image_tag}[/cyan]")
    console.print(f"  Hardened image: [cyan]{profile.hardened_image}[/cyan]\n")

    if config.target == "docker":
        # Generate configs
        console.print("Generating Docker configuration...")
        generator = ConfigGenerator(
            config_dir=CONFIG_DIR,
            security_profile=profile,
            resource_profile=resources,
            openclaw_tag=config.openclaw.image_tag,
            egress_proxy_port=config.egress.proxy_port,
        )
        generator.generate_all()

        summary = generator.get_config_summary()
        console.print(f"  Config dir: [cyan]{summary['config_dir']}[/cyan]")
        console.print(f"  Files: {', '.join(summary['files'])}")
        console.print(f"  CPU limit: {summary['cpu_limit']} cores")
        console.print(f"  Memory limit: {summary['memory_limit']}")
        console.print(f"  PID limit: {summary['pids_limit']}")
        console.print("[green]Configuration generated.[/green]\n")

        # Build image (only needed if hardened or using build context)
        if profile.hardened_image:
            console.print("Building hardened Docker image (this may take a few minutes)...")
            dm = DockerManager(config_dir=CONFIG_DIR)
            dm.build()
            console.print("[green]Image built.[/green]\n")
        else:
            console.print("[dim]No custom image build needed (using upstream image).[/dim]\n")

        # Prompt for .env editing
        env_path = CONFIG_DIR / ".env"
        console.print(f"[yellow]Configure your API keys in:[/yellow] {env_path}")
        console.print("Then run: [cyan]crabpot start[/cyan]")

    elif config.target == "wsl2":
        console.print("[yellow]WSL2 setup will be available in a future update.[/yellow]")
        console.print("For now, use [cyan]--target docker[/cyan].")


# ── Config command ─────────────────────────────────────────────────────


def cmd_config(args):
    """Show, edit, or reset configuration."""
    from crabpot.config import default_config_yaml, load_config

    action = getattr(args, "action", "show")

    if action == "show":
        if not CONFIG_FILE.exists():
            console.print("[yellow]No config file found.[/yellow]")
            console.print(f"Run [cyan]crabpot init[/cyan] to create {CONFIG_FILE}")
            return

        config = load_config()
        console.print(f"[bold]CrabPot Configuration[/bold]  ({CONFIG_FILE})\n")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        table.add_row("Target", config.target)
        table.add_row("OpenClaw source", config.openclaw.source)
        table.add_row("OpenClaw tag", config.openclaw.image_tag)
        table.add_row("Security preset", config.security.preset)

        if config.security.overrides:
            active = {k: v for k, v in config.security.overrides.items() if v is not None}
            if active:
                table.add_row("Overrides", ", ".join(f"{k}={v}" for k, v in active.items()))

        if config.resources.cpu_limit:
            table.add_row("CPU limit", config.resources.cpu_limit)
        if config.resources.memory_limit:
            table.add_row("Memory limit", config.resources.memory_limit)
        if config.resources.pids_limit:
            table.add_row("PIDs limit", str(config.resources.pids_limit))

        table.add_row("Egress proxy port", str(config.egress.proxy_port))
        table.add_row("Dashboard port", str(config.dashboard.port))

        if config.target == "wsl2":
            table.add_row("WSL2 distro", config.wsl2.distro_name)
            table.add_row("WSL2 base image", config.wsl2.base_image)

        console.print(table)

    elif action == "edit":
        if not CONFIG_FILE.exists():
            console.print("[yellow]No config file found. Creating defaults...[/yellow]")
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(default_config_yaml())

        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, str(CONFIG_FILE)], check=False)

    elif action == "reset":
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(default_config_yaml())
        console.print(f"[green]Config reset to defaults:[/green] {CONFIG_FILE}")


# ── Start ──────────────────────────────────────────────────────────────


def cmd_start(args):
    """Launch container + egress proxy + dashboard + security monitor."""
    from crabpot.action_gate import ActionGate
    from crabpot.alerts import AlertDispatcher
    from crabpot.config import load_config
    from crabpot.dashboard import DashboardServer
    from crabpot.docker_manager import DockerManager
    from crabpot.egress_policy import EgressPolicy
    from crabpot.egress_proxy import EgressProxy
    from crabpot.monitor import SecurityMonitor
    from crabpot.security_presets import resolve_profile

    console.print("[cyan]Starting CrabPot...[/cyan]\n")

    # Load config and resolve profile
    config = load_config()
    resource_overrides = {}
    if config.resources.cpu_limit is not None:
        resource_overrides["cpu_limit"] = config.resources.cpu_limit
    if config.resources.memory_limit is not None:
        resource_overrides["memory_limit"] = config.resources.memory_limit
    if config.resources.pids_limit is not None:
        resource_overrides["pids_limit"] = config.resources.pids_limit

    profile, resources = resolve_profile(
        config.security.preset,
        overrides=config.security.overrides or None,
        resource_overrides=resource_overrides or None,
    )

    dm = DockerManager(config_dir=CONFIG_DIR)

    # Set up alerts
    alerts = AlertDispatcher(data_dir=DATA_DIR)

    # Start the egress proxy (must be up before container starts)
    proxy = None
    if profile.egress_proxy:
        console.print("Starting egress proxy (network policy enforcement)...")
        policy = EgressPolicy(policy_path=EGRESS_POLICY_FILE)
        gate = ActionGate(egress_policy=policy, alert_dispatcher=alerts)
        proxy = EgressProxy(policy=policy, gate=gate, port=config.egress.proxy_port)
        proxy.start()
        console.print(f"[green]Egress proxy active on :{config.egress.proxy_port}[/green]")
    else:
        policy = None
        gate = None

    # Start the container
    console.print("Starting container...")
    dm.start()
    console.print("[green]Container started.[/green]")

    # Start the security monitor (with conditional watchers)
    console.print("Starting security monitor...")
    monitor = SecurityMonitor(
        docker_manager=dm, alert_dispatcher=alerts, security_profile=profile
    )
    monitor.start()
    active_count = len(monitor._threads)
    console.print(f"[green]Security monitor active ({active_count} channels).[/green]")

    # Start the dashboard
    console.print("Starting web dashboard...")
    dashboard = DashboardServer(
        docker_manager=dm,
        alert_dispatcher=alerts,
        security_monitor=monitor,
        action_gate=gate,
        egress_policy=policy,
        port=config.dashboard.port,
        target=config.target,
        security_preset=config.security.preset,
    )
    dashboard_thread = threading.Thread(target=dashboard.run, daemon=True)
    dashboard_thread.start()
    console.print("[green]Dashboard running.[/green]\n")

    console.print("[green]CrabPot is running![/green]")
    console.print("  OpenClaw Gateway: [cyan]http://localhost:18789[/cyan]")
    console.print(f"  CrabPot Dashboard: [cyan]http://localhost:{config.dashboard.port}[/cyan]")
    if proxy:
        console.print(
            f"  Egress Proxy:     [cyan]http://localhost:{config.egress.proxy_port}[/cyan]"
        )
    console.print("  TUI: [cyan]crabpot tui[/cyan]")
    console.print(f"  Preset: [cyan]{config.security.preset}[/cyan]")
    console.print("\nPress Ctrl+C to stop.")

    # Block until interrupt
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    stop_event.wait()

    console.print("\n[yellow]Shutting down...[/yellow]")
    monitor.stop()
    dm.stop()
    if proxy:
        proxy.stop()
    console.print("[green]CrabPot stopped.[/green]")


def cmd_stop(args):
    """Graceful shutdown of container and all components."""
    from crabpot.docker_manager import DockerManager

    console.print("[yellow]Stopping CrabPot...[/yellow]")
    dm = DockerManager(config_dir=CONFIG_DIR)

    status = dm.get_status()
    if status == "not_found":
        console.print("[yellow]Container not found.[/yellow]")
        return

    dm.stop()
    console.print("[green]CrabPot stopped.[/green]")


def cmd_pause(args):
    """Freeze the container (zero CPU, memory preserved)."""
    from crabpot.docker_manager import DockerManager

    dm = DockerManager(config_dir=CONFIG_DIR)
    dm.pause()
    console.print("[yellow]CrabPot paused (frozen).[/yellow]")
    console.print("Resume with: [cyan]crabpot resume[/cyan]")


def cmd_resume(args):
    """Unfreeze a paused container."""
    from crabpot.docker_manager import DockerManager

    dm = DockerManager(config_dir=CONFIG_DIR)
    dm.resume()
    console.print("[green]CrabPot resumed.[/green]")


def cmd_tui(args):
    """Launch the interactive terminal dashboard."""
    from crabpot.alerts import AlertDispatcher
    from crabpot.docker_manager import DockerManager
    from crabpot.tui import TUI

    dm = DockerManager(config_dir=CONFIG_DIR)
    alerts = AlertDispatcher(data_dir=DATA_DIR)
    tui = TUI(docker_manager=dm, alert_dispatcher=alerts)
    tui.run()


def cmd_status(args):
    """Show a one-shot status summary."""
    from crabpot.alerts import AlertDispatcher
    from crabpot.config import load_config
    from crabpot.docker_manager import DockerManager

    dm = DockerManager(config_dir=CONFIG_DIR)
    alerts = AlertDispatcher(data_dir=DATA_DIR)
    config = load_config()

    status = dm.get_status()
    health = dm.get_health()
    start_time = dm.get_start_time()

    status_colors = {
        "running": "green",
        "paused": "yellow",
        "exited": "red",
        "not_found": "red",
    }
    color = status_colors.get(status, "white")

    console.print("\n[bold]CrabPot Status[/bold]")
    console.print(f"  State:  [{color}]{status}[/{color}]")
    console.print(f"  Health: {health or 'N/A'}")
    console.print(f"  Target: [cyan]{config.target}[/cyan]")
    console.print(f"  Preset: [cyan]{config.security.preset}[/cyan]")

    if start_time:
        console.print(f"  Started: {start_time}")

    if status == "running":
        stats = dm.stats_snapshot()
        if stats:
            console.print(f"  CPU:    {stats['cpu_percent']}%")
            mem_mb = stats['memory_usage'] / (1024 * 1024)
            mem_limit_mb = stats['memory_limit'] / (1024 * 1024)
            mem_pct = stats['memory_percent']
            console.print(f"  Memory: {mem_mb:.0f}MB / {mem_limit_mb:.0f}MB ({mem_pct}%)")
            console.print(f"  PIDs:   {stats['pids']}")
            rx_mb = stats['network_rx'] / (1024 * 1024)
            tx_mb = stats['network_tx'] / (1024 * 1024)
            console.print(f"  Net:    RX {rx_mb:.1f}MB / TX {tx_mb:.1f}MB")

    # Recent alerts
    recent = alerts.get_history(last=5)
    if recent:
        console.print(f"\n  [bold]Recent Alerts ({len(recent)}):[/bold]")
        for a in recent:
            sev_color = {"CRITICAL": "red", "WARNING": "yellow", "INFO": "blue"}.get(
                a.get("severity", ""), "white"
            )
            console.print(
                f"    [{sev_color}]{a.get('severity', '?')}[/{sev_color}] "
                f"{a.get('timestamp', '?')} — {a.get('message', '')}"
            )
    console.print()


def cmd_logs(args):
    """Stream or tail container logs."""
    from crabpot.docker_manager import DockerManager

    dm = DockerManager(config_dir=CONFIG_DIR)

    if dm.get_status() == "not_found":
        console.print("[red]Container not found. Is CrabPot running?[/red]")
        sys.exit(1)

    try:
        for line in dm.get_logs(follow=args.follow, tail=args.tail):
            console.print(line, highlight=False)
    except KeyboardInterrupt:
        pass


def cmd_alerts(args):
    """View alert history."""
    from crabpot.alerts import AlertDispatcher

    alerts = AlertDispatcher(data_dir=DATA_DIR)
    history = alerts.get_history(last=args.last, severity=args.severity)

    if not history:
        console.print("[dim]No alerts found.[/dim]")
        return

    table = Table(title="Alert History")
    table.add_column("Time", style="dim")
    table.add_column("Severity", justify="center")
    table.add_column("Source")
    table.add_column("Message")

    for alert in history:
        sev = alert.get("severity", "?")
        sev_style = {"CRITICAL": "bold red", "WARNING": "yellow", "INFO": "blue"}.get(sev, "")
        table.add_row(
            alert.get("timestamp", "?"),
            f"[{sev_style}]{sev}[/{sev_style}]",
            alert.get("source", "?"),
            alert.get("message", ""),
        )
    console.print(table)


def cmd_shell(args):
    """Open an emergency interactive shell into the container."""
    from crabpot.docker_manager import DockerManager

    dm = DockerManager(config_dir=CONFIG_DIR)
    if dm.get_status() != "running":
        console.print("[red]Container is not running.[/red]")
        sys.exit(1)

    console.print("[yellow]Opening emergency shell (type 'exit' to leave)...[/yellow]")
    subprocess.run(
        ["docker", "exec", "-it", "crabpot", "/bin/sh"],
        check=False,
    )


def cmd_destroy(args):
    """Full teardown: stop container, remove volumes, clean configs."""
    from crabpot.docker_manager import DockerManager

    console.print("[bold red]This will destroy the CrabPot container and all its data.[/bold red]")
    confirm = input("Type 'destroy' to confirm: ").strip()
    if confirm != "destroy":
        console.print("[yellow]Aborted.[/yellow]")
        return

    dm = DockerManager(config_dir=CONFIG_DIR)
    console.print("Destroying CrabPot...")
    dm.destroy()

    # Remove generated configs (but not .env to preserve API keys)
    for name in ["docker-compose.yml", "Dockerfile.crabpot", "seccomp-profile.json"]:
        path = CONFIG_DIR / name
        if path.exists():
            path.unlink()

    console.print("[green]CrabPot destroyed.[/green]")
    console.print("To start fresh: [cyan]crabpot setup && crabpot start[/cyan]")


def cmd_uninstall(args):
    """Remove CrabPot completely."""
    console.print("[bold red]This will remove CrabPot and all its data.[/bold red]")
    console.print(f"  Directory: {CRABPOT_HOME}")
    confirm = input("Type 'uninstall' to confirm: ").strip()
    if confirm != "uninstall":
        console.print("[yellow]Aborted.[/yellow]")
        return

    # Stop container if running
    try:
        from crabpot.docker_manager import DockerManager
        dm = DockerManager(config_dir=CONFIG_DIR)
        dm.destroy()
    except Exception:
        pass

    # Remove CrabPot directory
    if CRABPOT_HOME.exists():
        shutil.rmtree(CRABPOT_HOME)
        console.print(f"[green]Removed {CRABPOT_HOME}[/green]")

    # Inform about PATH cleanup
    console.print(
        "\n[yellow]Remove the following line from your shell config "
        "(~/.bashrc, ~/.zshrc):[/yellow]"
    )
    console.print('  export PATH="$HOME/.crabpot/bin:$PATH"')
    console.print("\n[green]CrabPot uninstalled.[/green]")


# ── Egress policy commands ─────────────────────────────────────────────────


def cmd_policy(args):
    """Show or manage the egress allowlist."""
    from crabpot.egress_policy import EgressPolicy

    policy = EgressPolicy(policy_path=EGRESS_POLICY_FILE)
    action = getattr(args, "action", "show")
    domain = getattr(args, "domain", None)

    if action == "show":
        allowlist = policy.get_allowlist()
        session = policy.get_session_approved()

        console.print("[bold]Egress Allowlist[/bold]")
        console.print(f"  Policy file: [cyan]{EGRESS_POLICY_FILE}[/cyan]\n")

        if allowlist:
            table = Table(title="Permanent Allowlist")
            table.add_column("Domain", style="green")
            for d in allowlist:
                table.add_row(d)
            console.print(table)
        else:
            console.print("[dim]No permanent domains configured.[/dim]")

        if session:
            console.print(f"\n[bold]Session-approved:[/bold] {', '.join(session)}")
        console.print(
            f"\n[dim]Unknown domains: {policy.unknown_action} "
            f"(approve via dashboard or 'crabpot approve <domain>')[/dim]"
        )

    elif action == "add":
        if not domain:
            console.print("[red]Usage: crabpot policy add <domain>[/red]")
            sys.exit(1)
        policy.add_permanent(domain)
        console.print(f"[green]Added '{domain}' to permanent allowlist.[/green]")

    elif action == "remove":
        if not domain:
            console.print("[red]Usage: crabpot policy remove <domain>[/red]")
            sys.exit(1)
        policy.remove_permanent(domain)
        console.print(f"[yellow]Removed '{domain}' from allowlist.[/yellow]")


def cmd_approve(args):
    """Approve a pending egress domain (session or permanent)."""
    from crabpot.egress_policy import EgressPolicy

    policy = EgressPolicy(policy_path=EGRESS_POLICY_FILE)
    domain = args.domain

    if args.permanent:
        policy.add_permanent(domain)
        console.print(f"[green]Permanently approved: {domain}[/green]")
    else:
        policy.session_approve(domain)
        console.print(f"[green]Session-approved: {domain}[/green]")
        console.print("[dim]This approval expires when CrabPot stops.[/dim]")


def cmd_deny(args):
    """Deny a domain."""
    from crabpot.egress_policy import EgressPolicy

    policy = EgressPolicy(policy_path=EGRESS_POLICY_FILE)
    policy.session_deny(args.domain)
    console.print(f"[red]Denied: {args.domain}[/red]")


def cmd_audit(args):
    """View the egress audit log."""
    from crabpot.egress_policy import EgressPolicy

    policy = EgressPolicy(policy_path=EGRESS_POLICY_FILE)
    log = policy.get_audit_log(last=args.last)

    if not log:
        console.print("[dim]No egress activity recorded this session.[/dim]")
        console.print("[dim]Audit log is populated when CrabPot is running.[/dim]")
        return

    table = Table(title="Egress Audit Log")
    table.add_column("Time", style="dim")
    table.add_column("Domain")
    table.add_column("Port", justify="right")
    table.add_column("Method")
    table.add_column("Decision")

    decision_styles = {
        "allow": "green",
        "deny": "red",
        "pending": "yellow",
        "blocked_secrets": "bold red",
    }
    for entry in log:
        decision = entry.get("decision", "?")
        style = decision_styles.get(decision, "white")
        table.add_row(
            entry.get("timestamp", "?"),
            entry.get("domain", "?"),
            str(entry.get("port", "?")),
            entry.get("method", "?"),
            f"[{style}]{decision}[/{style}]",
        )
    console.print(table)
