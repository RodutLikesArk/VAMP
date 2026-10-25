"""Install boot startup on the Pi: python3 tools/install_pi_service.py.

Run as the same regular user who normally starts V.A.M.P.; sudo is requested
only for installing/enabling the system unit. Does not modify wiring config.
"""
import argparse
import getpass
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


def quote_path(value):
    value = str(value)
    if any(c in value for c in ('\n', '\r', '\0')):
        raise ValueError('Paths cannot contain newlines or NUL')
    # systemd percent specifiers and ExecStart dollar expansion are not shell
    # quoting. Double both separately before quoting whitespace/backslashes.
    value = value.replace('%', '%%').replace('$', '$$')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def render_unit(root, username, simulate=False):
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.-]*\$?', username):
        raise ValueError('Unsupported service username')
    root = PurePosixPath(root)
    # WorkingDirectory does not perform environment-variable expansion.
    working = quote_path(root).replace('$$', '$')
    command = f'{quote_path(root / ".venv/bin/python")} -u -m robot.main --config {quote_path(root / "robot/config.local.json")}'
    if simulate:
        command += ' --simulate'
    return f'''[Unit]
Description=V.A.M.P. Raspberry Pi controller
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=exec
User={username}
WorkingDirectory={working}
ExecStart={command}
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate', action='store_true', help='Start simulation on boot instead of hardware')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run this installer on the Raspberry Pi')
    if os.geteuid() == 0:
        parser.error('Run without sudo so the service uses your normal Pi account')
    root = Path(__file__).resolve().parents[1]
    if not (root / '.venv/bin/python').is_file():
        parser.error('Create the .venv from the Raspberry Pi setup instructions first')
    config_path = root / 'robot/config.local.json'
    if not config_path.is_file():
        parser.error('Create robot/config.local.json first; see README.md')
    config = json.loads(config_path.read_text())
    if not args.simulate and config.get('wiring_confirmed') is not True:
        parser.error('Verify your wiring and set wiring_confirmed=true before enabling hardware startup')
    unit = render_unit(root, getpass.getuser(), args.simulate)
    with tempfile.TemporaryDirectory(prefix='vamp-service-') as folder:
        source = Path(folder) / 'vamp.service'
        source.write_text(unit, encoding='utf-8')
        subprocess.run(['sudo', 'install', '-m', '644', str(source), '/etc/systemd/system/vamp.service'], check=True)
    subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
    # Stop an existing unit before re-enabling so mode/path edits take effect.
    subprocess.run(['sudo', 'systemctl', 'stop', 'vamp.service'], check=True)
    subprocess.run(['sudo', 'systemctl', 'reset-failed', 'vamp.service'], check=False)
    subprocess.run(['sudo', 'systemctl', 'enable', '--now', 'vamp.service'], check=True)
    print('V.A.M.P. is enabled at boot. Startup mode: ' + ('SIMULATION' if args.simulate else 'HARDWARE'))
    print('Check: systemctl status vamp --no-pager')
    print('Logs:  journalctl -u vamp -f')


if __name__ == '__main__':
    main()
