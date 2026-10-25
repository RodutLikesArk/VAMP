"""Exercise the actual packaged app against a loopback robot HTTP service."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot.camera import Camera
from robot.control import Controller
from robot.hardware import Hardware
from robot.main import handler_for


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=ROOT / 'dist/VAMP-Operator.exe')
    parser.add_argument('--imu-demo', action='store_true', help='Exercise the attitude UI with explicitly simulated sensor data')
    args = parser.parse_args()
    config = json.loads((ROOT / 'robot/config.json').read_text())
    config['token'] = secrets.token_hex(16)
    config['imu']['enabled'] = args.imu_demo
    hardware = Hardware(config, True)
    controller = Controller(hardware)
    camera = Camera(config['camera'], True)
    base = handler_for(controller, camera, config['token'])
    requests = []

    class Handler(base):
        def do_GET(self):
            if self.path == '/api/status' and self.headers.get('Authorization') == 'Bearer ' + config['token']:
                if args.imu_demo:
                    hardware.sample_imu()
                    hardware.telemetry.update(roll_deg=15.0,pitch_deg=20.0,yaw_deg=30.0)
                requests.append(self.path)
            super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix='vamp-packaged-check-') as folder:
            env = dict(os.environ, APPDATA=folder)
            result = subprocess.run([str(args.exe.resolve()), '--smoke-test', '--url',
                                     f'http://127.0.0.1:{server.server_port}', '--token', config['token']],
                                    env=env, timeout=20, check=False)
            if result.returncode != 0 or not requests:
                log = Path(folder) / 'VAMP/operator.log'
                if log.exists():
                    print(log.read_text(errors='replace'))
                raise SystemExit('FAILED: packaged app never completed an authenticated robot status request')
            print(f'PASS: packaged app completed {len(requests)} authenticated status requests')
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        camera.close()
        hardware.close()


if __name__ == '__main__':
    main()
