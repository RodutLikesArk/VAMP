"""Run from repository root: python -m robot.main --simulate."""
import argparse
import hmac
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .camera import Camera
from .control import Controller
from .hardware import Hardware


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def handler_for(controller, camera, token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def reply(self, status, message):
            payload = json.dumps(message, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.close_connection = True
                self.reply(401, {'error': 'Wrong token'})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            if self.path == '/api/status':
                status = controller.status()
                status['camera_error'] = camera.error
                self.reply(200, status)
            elif self.path == '/video.mjpg':
                if camera.error:
                    self.reply(503, {'error': camera.error})
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                sequence = -1
                try:
                    while True:
                        with camera.frames.condition:
                            if not camera.frames.condition.wait_for(lambda: camera.frames.sequence != sequence, timeout=3):
                                break
                            sequence = camera.frames.sequence
                            frame = camera.frames.frame
                        if frame:
                            self.wfile.write(b'--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n')
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass
                self.close_connection = True
            else:
                self.reply(404, {'error': 'Unknown endpoint'})

        def do_POST(self):
            if not self.authorized():
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Body must contain 1..4096 bytes')
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError('Incomplete body')
                message = json.loads(data)
                if not isinstance(message, dict):
                    raise ValueError('Expected JSON object')
                with controller.lock:
                    if self.path == '/api/modules':
                        controller.configure(message)
                    elif self.path == '/api/arm':
                        controller.arm()
                    elif self.path == '/api/control':
                        controller.command(message)
                    elif self.path == '/api/stop':
                        controller.halt('Operator stop')
                    elif self.path == '/api/estop':
                        controller.halt('Emergency stop', latch=True)
                    elif self.path == '/api/reset':
                        controller.halt('Emergency stop reset; arm to continue')
                        controller.estopped = False
                    else:
                        self.reply(404, {'error': 'Unknown endpoint'})
                        return
                self.reply(200, controller.status())
            except (ValueError, TypeError, KeyError) as exc:
                self.close_connection = True
                self.reply(400, {'error': str(exc)})
            except Exception:
                logging.exception('Request failure')
                with controller.lock:
                    controller.halt('Hardware/request failure', latch=True)
                self.close_connection = True
                self.reply(500, {'error': 'Hardware/request failure; outputs stopped'})
    return Handler


def control_loop(controller, quit_event):
    while not quit_event.is_set():
        start = time.monotonic()
        try:
            controller.tick()
        except Exception:
            logging.exception('Control loop failure')
            with controller.lock:
                controller.halt('Control loop fault', latch=True)
        quit_event.wait(max(0.001, 0.02 - (time.monotonic() - start)))


def sensor_loop(hardware, quit_event):
    # DS18B20/I2C reads must never delay motor stopping or the watchdog.
    while not quit_event.is_set():
        try:
            hardware.sample()
        except Exception:
            logging.exception('Sensor read failed')
            hardware.telemetry['pitch_deg'] = None
        quit_event.wait(0.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    parser.add_argument('--simulate', action='store_true')
    parser.add_argument('--host')
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    config = json.loads(args.config.read_text())
    if not isinstance(config.get('token'), str) or not config['token']:
        parser.error('Config token must be non-empty')
    hardware = Hardware(config, args.simulate)
    camera = Camera(config['camera'], args.simulate)
    controller = Controller(hardware)
    quit_event = threading.Event()
    worker = threading.Thread(target=control_loop, args=(controller, quit_event), daemon=True)
    sensors = threading.Thread(target=sensor_loop, args=(hardware, quit_event), daemon=True)
    server = None
    try:
        server = Server((args.host or config['host'], args.port if args.port is not None else config['port']), handler_for(controller, camera, config['token']))
        worker.start()
        sensors.start()
        print('V.A.M.P. %s on port %s' % ('SIMULATION' if args.simulate else 'GPIO', server.server_port), flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        quit_event.set()
        if worker.is_alive():
            worker.join(timeout=3)
        if sensors.is_alive():
            sensors.join(timeout=3)
        with controller.lock:
            controller.halt('Shutdown')
        if server:
            server.server_close()
        camera.close()
        hardware.close()


if __name__ == '__main__':
    main()
