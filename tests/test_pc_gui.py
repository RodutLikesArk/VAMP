"""Hidden-window GUI smoke/integration test; requires a Tk display."""
import copy
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from pc.client import Client
from pc.main import App
from robot.camera import Camera
from robot.control import Controller
from robot.hardware import Hardware
from robot.main import Server, handler_for, control_loop
from test_controller import CONFIG


class DesktopTest(unittest.TestCase):
    def test_gui_drives_and_stops_simulated_robot(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest('No Tk display: ' + str(exc))
        root.withdraw()
        config = copy.deepcopy(CONFIG)
        hardware = Hardware(config, True)
        controller = Controller(hardware)
        camera = Camera(config['camera'], True)
        server = Server(('127.0.0.1', 0), handler_for(controller, camera, config['token']))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        quit_event = threading.Event()
        worker = threading.Thread(target=control_loop, args=(controller, quit_event), daemon=True)
        worker.start()
        app = App(root, Client('http://127.0.0.1:' + str(server.server_port), config['token']))
        # The hidden test window intentionally has no focus; exercise focus-stop
        # explicitly below rather than letting withdraw automatically disarm it.
        root.unbind('<FocusOut>')
        def pump(seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                root.update()
                time.sleep(0.01)
        try:
            app.arm()
            pump(0.5)
            self.assertTrue(controller.armed)
            app.press(SimpleNamespace(keysym='space'))
            app.press(SimpleNamespace(keysym='w'))
            pump(0.3)
            self.assertEqual(hardware.outputs['left1'], 0.25)
            app.release(SimpleNamespace(keysym='space'))
            pump(0.3)
            self.assertTrue(all(value == 0 for value in hardware.outputs.values()))
            app.press(SimpleNamespace(keysym='Escape'))
            pump(0.3)
            self.assertTrue(controller.estopped)
            self.assertFalse(controller.armed)
            app.stop('/api/reset')
            pump(0.2)
            app.arm()
            pump(0.4)
            self.assertTrue(controller.armed)
            with patch.object(root, 'focus_displayof', return_value=None):
                app.check_focus()
            pump(0.3)
            self.assertFalse(controller.armed)
        finally:
            app.closed.set()
            quit_event.set()
            worker.join(1)
            root.destroy()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
