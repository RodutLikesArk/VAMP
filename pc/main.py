"""Desktop operator GUI. Run: python -m pc.main --url http://127.0.0.1:8765"""
import argparse
import io
import logging
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from .ui import OperatorView
from .settings import load_settings, data_dir

from .client import Client, jpeg_frames


class App(OperatorView):
    def __init__(self, root, client, weights=None):
        self.root, self.client = root, client
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.jobs, self.events = queue.Queue(), queue.Queue()
        self.generation = 0
        self.allowed = False
        self.keys = set()
        self.command = dict(surge=0, yaw=0, heave=0, pitch=0, stabilize=False, light=False)
        self.pending_servo = None
        self.latest_frame, self.display_frame = None, None
        self.frame_lock = threading.Lock()
        self.weights = weights
        self.mode = tk.StringVar(value='crawler')
        self.attachment = tk.StringVar(value='none')
        self.speed = tk.DoubleVar(value=0.5)
        self.stabilize = tk.BooleanVar()
        self.light = tk.BooleanVar()
        self.status = tk.StringVar(value='Connecting...')
        self.video_status = tk.StringVar(value='Camera connecting...')
        self.servo_positions = dict(gimbal=0.0, arm=0.0, gripper=0.0)
        self.build_ui(root)
        root.bind('<KeyPress>', self.press)
        root.bind('<KeyRelease>', self.release)
        root.bind('<FocusOut>', self.focus_out)
        root.protocol('WM_DELETE_WINDOW', self.close)
        threading.Thread(target=self.network, daemon=True).start()
        threading.Thread(target=self.video, daemon=True).start()
        if weights:
            threading.Thread(target=self.detect, daemon=True).start()
        self.refresh()

    def invalidate(self):
        with self.lock:
            self.generation += 1
            self.allowed = False
            self.pending_servo = None
            self.keys.clear()
            self.command.update(surge=0, yaw=0, heave=0, pitch=0)
            while not self.jobs.empty():
                try:
                    self.jobs.get_nowait()
                except queue.Empty:
                    break
            return self.generation

    def select_modules(self):
        generation = self.invalidate()
        self.jobs.put((generation, '/api/modules', {'mode': self.mode.get(), 'attachment': self.attachment.get()}))

    def arm(self):
        generation = self.invalidate()
        # Always apply current selectors before arm, including on first connection.
        self.jobs.put((generation, '/api/modules', {'mode': self.mode.get(), 'attachment': self.attachment.get()}))
        self.jobs.put((generation, '/api/arm', {}))

    def stop(self, path):
        generation = self.invalidate()
        self.jobs.put((generation, path, {}))

    def move_servo(self, name, delta):
        with self.lock:
            if not self.allowed:
                return
            if name != 'gimbal' and self.attachment.get() != 'manipulator':
                return
            self.servo_positions[name] = max(-1, min(1, self.servo_positions[name] + delta))
            # A single slot serializes servo requests; never command two at once.
            self.pending_servo = {'name': name, 'value': self.servo_positions[name]}

    def press(self, event):
        key = event.keysym.lower()
        if key == 'escape':
            self.stop('/api/estop')
            return
        widget = getattr(event, 'widget', None)
        if widget:
            # Tk-created combobox popdowns have no Python widget wrapper;
            # tkinter may therefore supply the widget path as a plain string.
            try:
                widget_class = self.root.tk.call('winfo', 'class', str(widget))
            except tk.TclError:
                return
            if widget_class in ('Entry', 'TEntry', 'TCombobox', 'Spinbox', 'TSpinbox', 'Listbox'):
                return
        with self.lock:
            new = key not in self.keys
            self.keys.add(key)
        if new:
            mapping = {'j': ('gimbal', -0.1), 'l': ('gimbal', 0.1), 'u': ('arm', -0.1), 'o': ('arm', 0.1), 'i': ('gripper', -0.1), 'k': ('gripper', 0.1)}
            if key in mapping:
                self.move_servo(*mapping[key])

    def release(self, event):
        with self.lock:
            self.keys.discard(event.keysym.lower())

    def focus_out(self, event):
        # Child widget focus changes are normal; leaving the app stops the robot.
        self.root.after(20, self.check_focus)

    def check_focus(self):
        if not self.closed.is_set() and not self.has_app_focus():
            self.stop('/api/stop')

    def has_app_focus(self):
        # focus_displayof() resolves the returned Tcl path to a Python widget.
        # That raises KeyError('popdown') for ttk's internally created listbox.
        # We only need to know whether this Tk application still has focus.
        try:
            return bool(self.root.tk.call('focus', '-displayof', self.root._w))
        except tk.TclError:
            return False

    def network(self):
        last_error = None
        while not self.closed.is_set():
            started = time.monotonic()
            try:
                job = None
                try:
                    job = self.jobs.get_nowait()
                except queue.Empty:
                    pass
                if job:
                    generation, path, payload = job
                    with self.lock:
                        current = generation == self.generation
                    if not current:
                        continue
                    status = self.client.request(path, payload)
                    if path == '/api/arm':
                        with self.lock:
                            if generation == self.generation:
                                self.allowed = status['armed']
                else:
                    with self.lock:
                        generation = self.generation
                        allowed = self.allowed
                        payload = dict(self.command)
                        if allowed and self.pending_servo:
                            payload['servo'] = self.pending_servo
                            self.pending_servo = None
                    status = self.client.request('/api/control', payload) if allowed else self.client.request('/api/status')
                    with self.lock:
                        if generation == self.generation and not status['armed']:
                            self.allowed = False
                self.events.put(('status', status))
                last_error = None
            except Exception as exc:
                error = (type(exc).__name__, str(exc))
                if error != last_error:
                    logging.warning('Robot connection failed', exc_info=True)
                    last_error = error
                # A failed heartbeat never automatically resumes driving on reconnect.
                self.invalidate()
                self.events.put(('error', str(exc)))
                try:
                    self.client.request('/api/stop', {})
                except Exception:
                    pass
            self.closed.wait(max(0.01, 0.1 - (time.monotonic() - started)))

    def video(self):
        try:
            from PIL import Image
        except ImportError:
            self.events.put(('video', 'Install PC requirements for camera display. Control remains available.'))
            return
        last_error = None
        while not self.closed.is_set():
            try:
                with self.client.video() as stream:
                    for frame in jpeg_frames(stream):
                        if self.closed.is_set():
                            return
                        image = Image.open(io.BytesIO(frame)).convert('RGB')
                        with self.frame_lock:
                            self.latest_frame = image
                            if not self.weights:
                                self.display_frame = image.copy()
                        self.events.put(('video', 'Live camera' + (' · custom defect model enabled' if self.weights else '')))
                        last_error = None
            except Exception as exc:
                error = (type(exc).__name__, str(exc))
                if error != last_error:
                    logging.warning('Camera connection failed', exc_info=True)
                    last_error = error
                self.events.put(('video', 'Camera unavailable: ' + str(exc)))
                with self.frame_lock:
                    self.latest_frame, self.display_frame = None, None
                self.closed.wait(2)

    def detect(self):
        try:
            from PIL import Image
            from ultralytics import YOLO
            model = YOLO(str(self.weights))
            while not self.closed.is_set():
                with self.frame_lock:
                    image = self.latest_frame.copy() if self.latest_frame else None
                if image:
                    result = model.predict(image, verbose=False, conf=0.35)[0]
                    annotated = Image.fromarray(result.plot()[:, :, ::-1])
                    with self.frame_lock:
                        self.display_frame = annotated
                self.closed.wait(0.2)
        except Exception as exc:
            self.events.put(('error', 'Defect detection unavailable: ' + str(exc)))
            # Fall back to raw live video; no model download or invented detections.
            self.weights = None

    def capture(self):
        with self.frame_lock:
            image = self.display_frame.copy() if self.display_frame else None
        if image:
            folder = Path.home() / 'Pictures' / 'VAMP'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jpg')
            image.save(path)
            self.video_status.set('Saved ' + str(path.resolve()))

    def refresh(self):
        if self.closed.is_set():
            return
        self.speed_label.configure(text='%d%%' % round(self.speed.get() * 100))
        with self.lock:
            keys = set(self.keys)
            enabled = self.allowed and 'space' in keys
            def axis(positive, negative):
                return (int(positive in keys) - int(negative in keys)) * self.speed.get() if enabled else 0
            self.command = {'surge': axis('w', 's'), 'yaw': axis('d', 'a'), 'heave': axis('r', 'f'), 'pitch': axis('t', 'g'),
                            'stabilize': self.stabilize.get() and enabled, 'light': self.light.get()}
        while not self.events.empty():
            kind, data = self.events.get_nowait()
            if kind == 'status':
                self.render_status(data)
                state = 'E-STOP' if data['estopped'] else ('ARMED' if data['armed'] else 'DISARMED')
                self.status.set('%s · %s / %s · %s%s' % (state, data['mode'], data['attachment'], data.get('reason') or 'Hold SPACE to drive', ' · SIMULATION' if data['simulate'] else ''))
                telemetry = data['telemetry']
                text = 'Pitch: %s deg | Temperature: %s C | MQ-2 raw digital state: %s\n' % (telemetry['pitch_deg'], telemetry['temperature_c'], telemetry['gas_alarm_raw'])
                text += 'Motor outputs: ' + str(data['motors']) + '\nServo: ' + str(data['active_servo'])
                if telemetry['sensor_error']:
                    text += '\n' + telemetry['sensor_error']
                self.telemetry.configure(state='normal')
                self.telemetry.delete('1.0', 'end')
                self.telemetry.insert('1.0', text)
                self.telemetry.configure(state='disabled')
            elif kind == 'error':
                self.status.set('Connection: ' + data)
                self.state_badge.configure(text='●  OFFLINE', fg='#ff657a')
            elif kind == 'video':
                self.video_status.set(data)
        with self.frame_lock:
            image = self.display_frame.copy() if self.display_frame else None
        if image:
            from PIL import ImageTk
            image.thumbnail((max(1, self.camera_stage.winfo_width()), max(1, self.camera_stage.winfo_height())))
            self.photo = ImageTk.PhotoImage(image)
            self.video_label.configure(image=self.photo, text='')
            self.video_label.place(relx=0.5, rely=0.5, anchor='center')
        else:
            self.video_label.place_forget()
        self.root.after(50, self.refresh)

    def close(self):
        self.invalidate()
        self.closed.set()
        # Network stop is best effort; the robot watchdog handles lost connections.
        threading.Thread(target=self.final_stop, daemon=True).start()
        self.root.after(450, self.root.destroy)

    def final_stop(self):
        try:
            self.client.request('/api/stop', {})
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default=None)
    parser.add_argument('--token', default=None)
    parser.add_argument('--weights', type=Path, help='Your locally trained defect-model .pt file')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    while True:
        settings = load_settings()
        root = tk.Tk()
        weights = args.weights or (Path(settings['weights']) if settings['weights'] else None)
        if weights and not weights.is_file():
            messagebox.showwarning('V.A.M.P. model', 'Saved model file is unavailable. Live video will run without detection.', parent=root)
            weights = None
        app = App(root, Client(args.url or settings['url'], args.token or settings['token']), weights)
        if args.smoke_test:
            # Used by packaging verification; a normal double-click never sets this.
            root.after(1200, app.close)
        root.mainloop()
        if not getattr(app, 'restart_settings', False):
            break
        args.url, args.token, args.weights = None, None, None


if __name__ == '__main__':
    main()
