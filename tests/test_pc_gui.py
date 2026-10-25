"""Hidden-window GUI smoke/integration test; requires a Tk display."""
import copy
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch, Mock
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
            # Typing in connection fields must never become propulsion input.
            entry = tk.Entry(root)
            app.press(SimpleNamespace(keysym='w', widget=entry))
            self.assertNotIn('w', app.keys)
            entry.destroy()
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
            with patch.object(app, 'has_app_focus', return_value=False):
                app.check_focus()
            pump(0.3)
            self.assertFalse(controller.armed)
            # Exercise the real dropdown callback and HTTP module change.
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            selector = next(w for w in descendants(root) if isinstance(w, ttk.Combobox) and 'submarine' in w.cget('values'))
            selector.set('submarine')
            selector.event_generate('<<ComboboxSelected>>')
            pump(0.3)
            self.assertEqual(controller.mode, 'submarine')
            self.assertFalse(controller.armed)
        finally:
            app.closed.set()
            quit_event.set()
            worker.join(1)
            root.destroy()
            server.shutdown()
            server.server_close()

    def test_native_combobox_popdown_focus_does_not_crash_or_stop(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest('No Tk display: ' + str(exc))
        root.withdraw()
        try:
            selector = ttk.Combobox(root, values=['crawler', 'submarine'])
            selector.pack()
            root.update_idletasks()
            popup = str(root.tk.call('ttk::combobox::PopdownWindow', selector._w))
            root.tk.call('wm', 'deiconify', popup)
            root.tk.call('focus', '-force', popup + '.f.l')
            root.update()
            # Reproduce the user's actual Tk popup and failing lookup, rather
            # than mocking the exception that the original code produced.
            self.assertEqual(str(root.tk.call('focus', '-displayof', root._w)), popup + '.f.l')
            with self.assertRaises(KeyError):
                root.focus_displayof()
            app = App.__new__(App)
            app.root = root
            app.closed = threading.Event()
            app.stop = Mock()
            self.assertTrue(app.has_app_focus())
            app.check_focus()
            app.stop.assert_not_called()
            app.keys = set()
            app.press(SimpleNamespace(keysym='w', widget=popup + '.f.l'))
            self.assertEqual(app.keys, set())
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
