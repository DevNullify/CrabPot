"""Rich terminal dashboard (TUI) for CrabPot."""

import sys
import time
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from crabpot.utils import format_uptime


class TUI:
    """Interactive terminal dashboard using Rich."""

    def __init__(self, docker_manager=None, alert_dispatcher=None, runtime=None):
        # Accept either runtime or docker_manager for backward compatibility
        self.dm = runtime or docker_manager
        self.alerts = alert_dispatcher
        self.console = Console()
        self._running = True
        self._last_stats: Optional[dict] = None

    def run(self) -> None:
        """Run the TUI (blocking until 'q' is pressed)."""
        try:
            import select
            import termios
            import tty
        except ImportError:
            self.console.print(
                "[red]TUI requires a Unix-like terminal (Linux/macOS/WSL2).[/red]"
            )
            return

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            with Live(
                self._build_layout(),
                console=self.console,
                refresh_per_second=1,
                screen=True,
            ) as live:
                while self._running:
                    self._handle_input(select)
                    self._refresh_stats()
                    live.update(self._build_layout())
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def _handle_input(self, select_module) -> None:
        """Check for and handle keyboard input (non-blocking)."""
        if select_module.select([sys.stdin], [], [], 0.0)[0]:
            key = sys.stdin.read(1).lower()
            if key == "q":
                self._running = False
            elif key == "p":
                try:
                    self.dm.pause()
                except Exception:
                    pass
            elif key == "r":
                try:
                    self.dm.resume()
                except Exception:
                    pass
            elif key == "s":
                try:
                    self.dm.stop()
                except Exception:
                    pass

    def _refresh_stats(self) -> None:
        """Fetch the latest stats snapshot."""
        try:
            if self.dm.get_status() == "running":
                self._last_stats = self.dm.stats_snapshot()
            else:
                self._last_stats = None
        except Exception:
            self._last_stats = None

    def _build_layout(self) -> Layout:
        """Build the complete TUI layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        layout["body"].split_column(
            Layout(name="stats", size=8),
            Layout(name="alerts"),
        )

        layout["header"].update(self._build_header())
        layout["stats"].update(self._build_stats())
        layout["alerts"].update(self._build_alerts())
        layout["footer"].update(self._build_footer())

        return layout

    def _build_header(self) -> Panel:
        """Build the header panel with state and uptime."""
        status = self.dm.get_status()
        health = self.dm.get_health() or "N/A"
        uptime = format_uptime(self.dm.get_start_time())

        status_styles = {
            "running": ("bold green", "RUNNING"),
            "paused": ("bold yellow", "PAUSED"),
            "exited": ("bold red", "STOPPED"),
            "not_found": ("bold red", "NOT FOUND"),
        }
        style, label = status_styles.get(status, ("white", status.upper()))

        header = Text()
        header.append(" State: ", style="bold")
        header.append(f"● {label}", style=style)
        header.append(f"      Uptime: {uptime}", style="dim")
        header.append(f"      Health: {health}", style="dim")

        return Panel(header, title="[bold red]CrabPot TUI[/bold red]", border_style="red")

    def _build_stats(self) -> Panel:
        """Build the resource usage panel."""
        stats = self._last_stats

        table = Table.grid(padding=(0, 2))
        table.add_column("label", width=8)
        table.add_column("bar", width=30)
        table.add_column("value", width=25)

        if stats:
            cpu = stats["cpu_percent"]
            mem_pct = stats["memory_percent"]
            mem_mb = stats["memory_usage"] / (1024 * 1024)
            mem_limit_mb = stats["memory_limit"] / (1024 * 1024)
            rx_mb = stats["network_rx"] / (1024 * 1024)
            tx_mb = stats["network_tx"] / (1024 * 1024)
            pids = stats["pids"]

            table.add_row(
                "[dim]CPU[/dim]",
                self._bar(cpu / 2, 100),
                f"[cyan]{cpu:.1f}%[/cyan]  limit: 200%",
            )
            table.add_row(
                "[dim]MEM[/dim]",
                self._bar(mem_pct, 100),
                f"[cyan]{mem_mb:.0f}MB[/cyan] / {mem_limit_mb:.0f}MB",
            )
            table.add_row(
                "[dim]NET[/dim]",
                "",
                f"[dim]↓[/dim] {rx_mb:.1f}MB  [dim]↑[/dim] {tx_mb:.1f}MB",
            )
            table.add_row(
                "[dim]PIDs[/dim]",
                self._bar(pids, 200),
                f"[cyan]{pids}[/cyan] / 200",
            )
        else:
            table.add_row("[dim]CPU[/dim]", "[dim]-- no data --[/dim]", "")
            table.add_row("[dim]MEM[/dim]", "[dim]-- no data --[/dim]", "")
            table.add_row("[dim]NET[/dim]", "", "[dim]-- no data --[/dim]")
            table.add_row("[dim]PIDs[/dim]", "[dim]-- no data --[/dim]", "")

        return Panel(table, title="Resource Usage", border_style="blue")

    def _build_alerts(self) -> Panel:
        """Build the recent alerts panel."""
        recent = self.alerts.get_history(last=15)

        if not recent:
            return Panel("[dim]No alerts[/dim]", title="Recent Alerts", border_style="yellow")

        table = Table.grid(padding=(0, 1))
        table.add_column("sev", width=10)
        table.add_column("time", width=10)
        table.add_column("msg")

        for alert in reversed(recent):
            sev = alert.get("severity", "INFO")
            sev_styles = {"CRITICAL": "bold red", "WARNING": "yellow", "INFO": "blue"}
            style = sev_styles.get(sev, "white")

            table.add_row(
                f"[{style}]{sev}[/{style}]",
                f"[dim]{alert.get('timestamp', '?')}[/dim]",
                alert.get("message", ""),
            )

        return Panel(table, title="Recent Alerts", border_style="yellow")

    def _build_footer(self) -> Panel:
        """Build the footer with keyboard controls and dashboard URL."""
        footer = Text()
        footer.append(" [p]", style="bold cyan")
        footer.append("ause  ", style="dim")
        footer.append("[r]", style="bold cyan")
        footer.append("esume  ", style="dim")
        footer.append("[s]", style="bold cyan")
        footer.append("top  ", style="dim")
        footer.append("[q]", style="bold cyan")
        footer.append("uit", style="dim")
        footer.append("     Web: http://localhost:9876", style="dim")

        return Panel(footer, border_style="dim")

    @staticmethod
    def _bar(value: float, maximum: float) -> str:
        """Create a text-based progress bar."""
        if maximum <= 0:
            return "[dim]░░░░░░░░░░░░░░░░░░░░[/dim]"

        pct = min(value / maximum, 1.0)
        filled = int(pct * 20)
        empty = 20 - filled

        if pct > 0.85:
            color = "red"
        elif pct > 0.60:
            color = "yellow"
        else:
            color = "green"

        return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
