"""Desktop operator GUI. Run: python -m pc.main --url http://127.0.0.1:8765"""
import argparse
import io
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

from .client import Client, jpeg_frames


class App:
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
        root.title('V.A.M.P. Operator')
        root.geometry('1060x820')
        root.minsize(800, 650)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='V.A.M.P. — Versatile Amphibious Modular Platform', font=('Arial', 17, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=client.url).pack(anchor='w', pady=(0, 8))
        row = ttk.Frame(frame)
        row.pack(fill='x')
        ttk.Label(row, text='Mobility:').pack(side='left')
        modes = ttk.Combobox(row, textvariable=self.mode, values=['crawler', 'submarine'], state='readonly', width=12)
        modes.pack(side='left', padx=8)
        ttk.Label(row, text='Front attachment:').pack(side='left')
        attachments = ttk.Combobox(row, textvariable=self.attachment, values=['none', 'manipulator', 'scanner', 'led'], state='readonly', width=14)
        attachments.pack(side='left', padx=8)
        modes.bind('<<ComboboxSelected>>', lambda e: self.select_modules())
        attachments.bind('<<ComboboxSelected>>', lambda e: self.select_modules())
        ttk.Button(row, text='Apply modules', command=self.select_modules).pack(side='left')
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=8)
        ttk.Button(buttons, text='ARM', command=self.arm).pack(side='left', padx=3)
        ttk.Button(buttons, text='STOP', command=lambda: self.stop('/api/stop')).pack(side='left', padx=3)
        tk.Button(buttons, text='EMERGENCY STOP (Esc)', bg='#b91c1c', fg='white', command=lambda: self.stop('/api/estop')).pack(side='left', padx=3)
        ttk.Button(buttons, text='Reset E-stop', command=lambda: self.stop('/api/reset')).pack(side='left', padx=3)
        ttk.Checkbutton(buttons, text='Pitch stabilization', variable=self.stabilize).pack(side='left', padx=8)
        ttk.Checkbutton(buttons, text='Light', variable=self.light).pack(side='left')
        speed = ttk.Frame(frame)
        speed.pack(fill='x')
        ttk.Label(speed, text='Operator speed (fraction of robot max):').pack(side='left')
        ttk.Scale(speed, from_=0.1, to=1, variable=self.speed).pack(side='left', fill='x', expand=True, padx=10)
        ttk.Label(frame, text='Hold SPACE to drive · W/S forward/reverse · A/D turn · R/F ascend/descend · T/G pitch\nJ/L camera tilt · U/O arm · I/K gripper · release SPACE to stop propulsion').pack(anchor='w', pady=8)
        servos = ttk.Frame(frame)
        servos.pack(fill='x')
        for name in self.servo_positions:
            ttk.Label(servos, text=name.title()).pack(side='left', padx=(8, 2))
            for label, step in [('-', -0.1), ('+', 0.1)]:
                ttk.Button(servos, text=label, width=3, command=lambda n=name, s=step: self.move_servo(n, s)).pack(side='left')
        ttk.Button(servos, text='Save camera frame', command=self.capture).pack(side='right')
        ttk.Label(frame, textvariable=self.status, wraplength=1000).pack(anchor='w', pady=10)
        self.video_label = ttk.Label(frame, text='Live camera is unavailable in simulation.', anchor='center')
        self.video_label.pack(fill='both', expand=True)
        ttk.Label(frame, textvariable=self.video_status, wraplength=1000).pack(anchor='w')
        self.telemetry = tk.Text(frame, height=6, state='disabled', font=('Consolas', 10))
        self.telemetry.pack(fill='x', pady=(8, 0))
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
        if not self.closed.is_set() and self.root.focus_displayof() is None:
            self.stop('/api/stop')

    def network(self):
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
            except Exception as exc:
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
            except Exception as exc:
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
            Path('captures').mkdir(exist_ok=True)
            path = Path('captures') / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.jpg')
            image.save(path)
            self.video_status.set('Saved ' + str(path.resolve()))

    def refresh(self):
        if self.closed.is_set():
            return
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
                self.status.set('Error: ' + data)
            elif kind == 'video':
                self.video_status.set(data)
        with self.frame_lock:
            image = self.display_frame.copy() if self.display_frame else None
        if image:
            from PIL import ImageTk
            image.thumbnail((max(640, self.video_label.winfo_width()), max(200, self.video_label.winfo_height())))
            self.photo = ImageTk.PhotoImage(image)
            self.video_label.configure(image=self.photo, text='')
        else:
            self.video_label.configure(image='', text='No live frame available')
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
    parser.add_argument('--url', default='http://192.168.10.2:8765')
    parser.add_argument('--token', default='vamp-prototype')
    parser.add_argument('--weights', type=Path, help='Your locally trained defect-model .pt file')
    args = parser.parse_args()
    if args.weights and not args.weights.is_file():
        parser.error('Weights file does not exist; supply your trained model')
    root = tk.Tk()
    App(root, Client(args.url, args.token), args.weights)
    root.mainloop()


if __name__ == '__main__':
    main()
