"""CLI entry point for CrabPot."""

import argparse
import sys

from crabpot import __version__


def main():
    parser = argparse.ArgumentParser(
        prog="crabpot",
        description="CrabPot — Secure OpenClaw Sandbox",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  crabpot init          Interactive setup wizard\n"
            "  crabpot setup         Generate configs + build image\n"
            "  crabpot start         Launch container + dashboard + monitor\n"
            "  crabpot config        Show current configuration\n"
            "  crabpot tui           Interactive terminal dashboard\n"
            "  crabpot stop          Graceful shutdown\n"
        ),
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # ── Init ──────────────────────────────────────────────
    init_p = subparsers.add_parser("init", help="Interactive setup wizard (checks prerequisites)")
    init_p.add_argument("--target", choices=["docker", "wsl2"], help="Deployment target")
    init_p.add_argument(
        "--preset", choices=["minimal", "standard", "paranoid"], help="Security preset"
    )
    init_p.add_argument("--openclaw-tag", help="OpenClaw image tag (e.g. latest, v1.2.3)")
    init_p.add_argument(
        "--non-interactive", action="store_true", help="Skip prompts, use defaults or CLI flags"
    )

    subparsers.add_parser("setup", help="Generate configs + build image based on crabpot.yml")
    subparsers.add_parser("start", help="Launch container + dashboard + security monitor")
    subparsers.add_parser("stop", help="Graceful shutdown of all components")
    subparsers.add_parser("pause", help="Freeze container (zero CPU, memory preserved)")
    subparsers.add_parser("resume", help="Unfreeze container")
    subparsers.add_parser("tui", help="Interactive terminal dashboard")
    subparsers.add_parser("status", help="Show current status")

    # ── Config ────────────────────────────────────────────
    config_p = subparsers.add_parser("config", help="Show or edit configuration")
    config_p.add_argument(
        "action",
        nargs="?",
        default="show",
        choices=["show", "edit", "reset"],
        help="Action to perform (default: show)",
    )

    logs_p = subparsers.add_parser("logs", help="Stream container logs")
    logs_p.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    logs_p.add_argument("-n", "--tail", type=int, default=100, help="Number of lines to show")

    alerts_p = subparsers.add_parser("alerts", help="View alert history")
    alerts_p.add_argument("--last", type=int, default=20, help="Number of alerts to show")
    alerts_p.add_argument(
        "--severity",
        choices=["CRITICAL", "WARNING", "INFO"],
        help="Filter by severity",
    )

    subparsers.add_parser("shell", help="Open emergency shell into container")
    subparsers.add_parser("destroy", help="Full teardown and cleanup")
    subparsers.add_parser("uninstall", help="Remove CrabPot completely")

    # ── Egress policy commands ─────────────────────────────
    policy_p = subparsers.add_parser("policy", help="Show/manage egress allowlist")
    policy_p.add_argument(
        "action",
        nargs="?",
        default="show",
        choices=["show", "add", "remove"],
        help="Action to perform (default: show)",
    )
    policy_p.add_argument("domain", nargs="?", help="Domain to add/remove")

    approve_p = subparsers.add_parser("approve", help="Approve a pending egress domain")
    approve_p.add_argument("domain", help="Domain to approve")
    approve_p.add_argument("--permanent", action="store_true", help="Add to permanent allowlist")

    deny_p = subparsers.add_parser("deny", help="Deny a pending egress domain")
    deny_p.add_argument("domain", help="Domain to deny")

    audit_p = subparsers.add_parser("audit", help="View egress audit log")
    audit_p.add_argument("--last", type=int, default=50, help="Number of entries to show")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Lazy import to keep startup fast
    from crabpot.cli import dispatch

    dispatch(args)


if __name__ == "__main__":
    main()
