#!/usr/bin/env python3
"""Install a user systemd timer independent of GitHub cron and the Codex app.

Requires this checkout's .venv and an authenticated gh CLI. Runs while the
computer and user systemd session are active; it is not an always-on cloud service.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
UNITS = Path.home() / ".config" / "systemd" / "user"
NAME = "yougov-report-watchdog"


def main() -> None:
    if not PYTHON.exists():
        raise SystemExit("Create .venv and install requirements.txt first.")
    subprocess.run(["gh", "auth", "status"], check=True, capture_output=True)
    service = f'''[Unit]
Description=Check YouGov report freshness and repair missed GitHub checks

[Service]
Type=oneshot
Environment=MPLCONFIGDIR=/tmp/electionmodels-watchdog-mpl
WorkingDirectory={ROOT}
ExecStart="{PYTHON}" "{ROOT / 'scripts' / 'watchdog.py'}" --repair
TimeoutStartSec=300
'''
    timer = f'''[Unit]
Description=Independent half-hourly YouGov report watchdog

[Timer]
OnCalendar=*-*-* *:13,43:00
OnBootSec=2min
Persistent=true
AccuracySec=30s
Unit={NAME}.service

[Install]
WantedBy=timers.target
'''
    UNITS.mkdir(parents=True, exist_ok=True)
    (UNITS / f"{NAME}.service").write_text(service)
    (UNITS / f"{NAME}.timer").write_text(timer)
    subprocess.run(["systemd-analyze", "--user", "verify",
                    str(UNITS / f"{NAME}.service"), str(UNITS / f"{NAME}.timer")], check=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{NAME}.timer"], check=True)
    subprocess.run(["systemctl", "--user", "is-active", "--quiet", f"{NAME}.timer"], check=True)
    subprocess.run(["systemctl", "--user", "list-timers", f"{NAME}.timer"], check=True)


if __name__ == "__main__":
    main()
