import copy
import io
import json
import math
import threading
import time
import unittest
from pathlib import Path

from robot.hardware import Hardware, validate_config
from robot.control import Controller
from robot.camera import Camera
from robot.main import Server, handler_for, control_loop
from pc.client import Client, jpeg_frames


CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'robot/config.json').read_text())


class Clock:
    def __init__(self):
        self.now = 10.0
    def __call__(self):
        return self.now


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(CONFIG)
        self.hw = Hardware(self.config, simulate=True)
        self.clock = Clock()
        self.controller = Controller(self.hw, self.clock)

    def drive(self, **message):
        self.controller.arm()
        self.controller.command(message)
        self.controller.tick()

    def test_startup_rejects_motion(self):
        with self.assertRaises(ValueError):
            self.controller.command({'surge': 1})
        self.assertTrue(all(v == 0 for v in self.hw.outputs.values()))

    def test_crawler_all_six(self):
        self.drive(surge=1)
        self.assertEqual(list(self.hw.outputs.values()), [0.5] * 6)

    def test_turn_mixing_normalizes(self):
        self.drive(surge=1, yaw=1)
        self.assertEqual(self.hw.outputs['left1'], 0.5)
        self.assertEqual(self.hw.outputs['right1'], 0)

    def test_reverse_and_inversion(self):
        self.config['invert_motors'] = ['left1']
        self.drive(surge=-1)
        self.assertEqual(self.hw.outputs['left1'], 0.5)
        self.assertEqual(self.hw.outputs['right1'], -0.5)

    def test_submarine_unused_motors_zero(self):
        self.drive(surge=1)
        self.controller.configure({'mode': 'submarine', 'attachment': 'none'})
        self.drive(surge=1, heave=0.8, pitch=0.2)
        self.assertEqual(self.hw.outputs['left3'], 0)
        self.assertEqual(self.hw.outputs['right3'], 0)
        self.assertAlmostEqual(self.hw.outputs['left2'], 0.5)
        self.assertAlmostEqual(self.hw.outputs['right2'], 0.3)

    def test_module_change_disarms(self):
        self.drive(surge=1)
        self.controller.configure({'mode': 'submarine', 'attachment': 'scanner'})
        self.assertFalse(self.controller.armed)
        self.assertTrue(all(v == 0 for v in self.hw.outputs.values()))

    def test_timeout_disarms_without_auto_resume(self):
        self.drive(surge=1)
        self.clock.now += 0.61
        self.controller.tick()
        self.assertFalse(self.controller.armed)
        self.assertEqual(sum(self.hw.outputs.values()), 0)
        with self.assertRaises(ValueError):
            self.controller.command({'surge': 1})

    def test_invalid_numbers_do_not_refresh_watchdog(self):
        self.drive(surge=0.5)
        previous = self.controller.last_command
        self.clock.now += 0.5
        for value in [float('nan'), float('inf'), '1', True, 1.01, -2, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.controller.command({'surge': value})
        self.assertEqual(previous, self.controller.last_command)

    def test_estop_latched_across_module_selection(self):
        self.drive(surge=1)
        self.controller.halt('test', latch=True)
        self.controller.configure({'mode': 'crawler', 'attachment': 'none'})
        with self.assertRaises(ValueError):
            self.controller.arm()
        self.assertTrue(self.controller.estopped)

    def test_one_servo_and_auto_release(self):
        self.controller.configure({'mode': 'crawler', 'attachment': 'manipulator'})
        self.drive(servo={'name': 'gimbal', 'value': 0.5})
        self.controller.command({'servo': {'name': 'arm', 'value': -0.5}})
        self.assertEqual(self.hw.active_servo, 'arm')
        self.clock.now += 0.31
        self.controller.tick()
        self.assertIsNone(self.hw.active_servo)

    def test_wrong_front_attachment_rejected(self):
        self.controller.arm()
        with self.assertRaises(ValueError):
            self.controller.command({'servo': {'name': 'gripper', 'value': 0}})

    def test_stabilization_requires_imu(self):
        self.controller.configure({'mode': 'submarine', 'attachment': 'none'})
        self.controller.arm()
        with self.assertRaises(ValueError):
            self.controller.command({'stabilize': True})

    def test_stale_imu_stops_stabilization(self):
        self.config['imu']['enabled'] = True
        self.hw.sample()
        self.controller.configure({'mode': 'submarine', 'attachment': 'none'})
        self.drive(stabilize=True)
        self.hw.last_imu_sample = time.monotonic() - 1
        self.controller.tick()
        self.assertFalse(self.controller.armed)

    def test_duplicate_pin_rejected(self):
        self.config['servos']['gimbal'] = 5
        with self.assertRaises(ValueError):
            validate_config(self.config)

    def test_duplicate_profile_motor_rejected(self):
        self.config['profiles']['crawler']['right'] = ['left1']
        with self.assertRaises(ValueError):
            validate_config(self.config)

    def test_mjpeg_length_parser(self):
        frame = b'fakejpeg'
        stream = io.BytesIO(b'--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: 8\r\n\r\n' + frame + b'\r\n')
        self.assertEqual(list(jpeg_frames(stream)), [frame])


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(CONFIG)
        self.hw = Hardware(self.config, simulate=True)
        self.controller = Controller(self.hw)
        self.camera = Camera(self.config['camera'], True)
        self.server = Server(('127.0.0.1', 0), handler_for(self.controller, self.camera, self.config['token']))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client('http://127.0.0.1:' + str(self.server.server_port), self.config['token'])
        self.quit = threading.Event()
        self.loop = threading.Thread(target=control_loop, args=(self.controller, self.quit), daemon=True)
        self.loop.start()

    def tearDown(self):
        self.quit.set()
        self.loop.join(1)
        self.server.shutdown()
        self.server.server_close()

    def test_real_http_drive_stop_and_reset(self):
        self.client.request('/api/modules', {'mode': 'submarine', 'attachment': 'manipulator'})
        self.client.request('/api/arm', {})
        self.client.request('/api/control', {'surge': 1, 'heave': -0.5})
        time.sleep(0.05)
        status = self.client.request('/api/status')
        self.assertEqual(status['motors']['left1'], 0.5)
        self.assertEqual(status['motors']['left2'], -0.25)
        self.assertTrue(self.client.request('/api/estop', {})['estopped'])
        with self.assertRaises(RuntimeError):
            self.client.request('/api/arm', {})
        self.assertFalse(self.client.request('/api/reset', {})['armed'])
        self.assertTrue(self.client.request('/api/arm', {})['armed'])

    def test_http_missing_heartbeat_stops(self):
        self.client.request('/api/arm', {})
        self.client.request('/api/control', {'surge': 1})
        time.sleep(0.7)
        status = self.client.request('/api/status')
        self.assertFalse(status['armed'])
        self.assertTrue(all(v == 0 for v in status['motors'].values()))

    def test_auth_and_bad_command(self):
        bad = Client(self.client.url, 'incorrect')
        with self.assertRaises(RuntimeError):
            bad.request('/api/arm', {})
        self.client.request('/api/arm', {})
        with self.assertRaises(RuntimeError):
            self.client.request('/api/control', {'surge': 'full'})


if __name__ == '__main__':
    unittest.main()
