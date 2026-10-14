"""Dark operator dashboard built with native Tk widgets."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from .settings import save_settings, data_dir

BG = '#090f1b'
PANEL = '#111c2c'
SURFACE = '#18263a'
LINE = '#283b52'
TEXT = '#e8f2ff'
MUTED = '#8fa6c1'
ACCENT = '#46e2ba'
BLUE = '#58b9ff'
RED = '#ff657a'


class OperatorView:
    def build_ui(self, root):
        root.title('V.A.M.P. | Mission Control')
        root.geometry('1280x880')
        root.minsize(1000, 760)
        root.configure(bg=BG)
        icon = Path(__file__).with_name('assets') / 'vamp.png'
        if icon.is_file():
            self.window_icon = tk.PhotoImage(file=str(icon))
            root.iconphoto(True, self.window_icon)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('VAMP.MissionControl')
            # Windows 11 and recent Windows 10: dark native title bar.
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        except (AttributeError, OSError):
            pass
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background=PANEL, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('TFrame', background=PANEL)
        style.configure('TLabel', background=PANEL, foreground=TEXT)
        style.configure('TCombobox', fieldbackground=SURFACE, background=SURFACE, foreground=TEXT, arrowcolor=ACCENT, bordercolor=LINE, padding=7)
        style.map('TCombobox', fieldbackground=[('readonly', SURFACE)], foreground=[('readonly', TEXT)], selectbackground=[('readonly', SURFACE)], selectforeground=[('readonly', TEXT)])
        style.configure('TCheckbutton', background=PANEL, foreground=TEXT, indicatorbackground=SURFACE, indicatorforeground=ACCENT)
        style.map('TCheckbutton', background=[('active', PANEL)], indicatorbackground=[('selected', ACCENT)])
        style.configure('Horizontal.TScale', background=PANEL, troughcolor=SURFACE, bordercolor=LINE)
        root.option_add('*TCombobox*Listbox.background', SURFACE)
        root.option_add('*TCombobox*Listbox.foreground', TEXT)
        root.option_add('*TCombobox*Listbox.selectBackground', LINE)
        outer = tk.Frame(root, bg=BG, padx=22, pady=18)
        outer.pack(fill='both', expand=True)
        header = tk.Frame(outer, bg=BG)
        header.pack(fill='x', pady=(0, 18))
        logo = tk.Canvas(header, width=52, height=52, bg=BG, highlightthickness=0)
        logo.pack(side='left', padx=(0, 12))
        logo.create_polygon(4, 8, 17, 8, 26, 28, 35, 8, 48, 8, 26, 47, fill=ACCENT)
        logo.create_line(10, 48, 42, 48, fill=BLUE, width=2)
        wordmark = tk.Frame(header, bg=BG)
        wordmark.pack(side='left')
        tk.Label(wordmark, text='V.A.M.P.', font=('Segoe UI', 25, 'bold'), bg=BG, fg=TEXT).pack(anchor='w')
        tk.Label(wordmark, text='MISSION CONTROL  /  AMPHIBIOUS PLATFORM', font=('Segoe UI', 9), bg=BG, fg=MUTED).pack(anchor='w')
        self.button(header, 'Connection settings', self.connection_settings, color=SURFACE).pack(side='right', padx=(12, 0))
        self.state_badge = tk.Label(header, text='●  CONNECTING', bg=SURFACE, fg=MUTED, font=('Segoe UI', 10, 'bold'), padx=16, pady=10)
        self.state_badge.pack(side='right')
        body = tk.Frame(outer, bg=BG)
        body.pack(fill='both', expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=316)
        body.grid_rowconfigure(0, weight=1)
        camera = self.panel(body)
        camera.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        camera_header = tk.Frame(camera, bg=PANEL)
        camera_header.pack(fill='x', padx=16, pady=14)
        self.caption(camera_header, 'VISUAL FEED').pack(side='left')
        self.button(camera_header, 'Capture frame', self.capture, color=SURFACE, compact=True).pack(side='right')
        self.camera_stage = tk.Frame(camera, bg=BG)
        self.camera_stage.pack(fill='both', expand=True, padx=12)
        self.placeholder = tk.Canvas(self.camera_stage, bg=BG, highlightthickness=0)
        self.placeholder.pack(fill='both', expand=True)
        self.placeholder.bind('<Configure>', self.draw_placeholder)
        self.video_label = tk.Label(self.camera_stage, bg=BG, borderwidth=0)
        tk.Label(camera, textvariable=self.video_status, bg=PANEL, fg=MUTED, font=('Segoe UI', 9), anchor='w', wraplength=650).pack(fill='x', padx=16, pady=12)
        guide = tk.Frame(camera, bg=SURFACE, padx=12, pady=10)
        guide.pack(fill='x', padx=12, pady=(0, 12))
        tk.Label(guide, text='SPACE  +  W A S D', font=('Consolas', 12, 'bold'), bg=SURFACE, fg=ACCENT).pack(side='left')
        tk.Label(guide, text='Hold to drive • Release SPACE to stop', font=('Segoe UI', 9), bg=SURFACE, fg=MUTED).pack(side='right')
        controls = self.panel(body)
        controls.grid(row=0, column=1, sticky='nsew')
        deck = tk.Frame(controls, bg=PANEL, padx=16, pady=16)
        deck.pack(fill='both', expand=True)
        self.caption(deck, 'CONTROL DECK').pack(anchor='w', pady=(0, 12))
        self.caption(deck, 'MOBILITY MODULE', muted=True).pack(anchor='w')
        modes = ttk.Combobox(deck, textvariable=self.mode, values=['crawler', 'submarine'], state='readonly')
        modes.pack(fill='x', pady=(5, 12))
        self.caption(deck, 'FRONT ATTACHMENT', muted=True).pack(anchor='w')
        attachments = ttk.Combobox(deck, textvariable=self.attachment, values=['none', 'manipulator', 'scanner', 'led'], state='readonly')
        attachments.pack(fill='x', pady=(5, 12))
        modes.bind('<<ComboboxSelected>>', lambda e: self.select_modules())
        attachments.bind('<<ComboboxSelected>>', lambda e: self.select_modules())
        row = tk.Frame(deck, bg=PANEL)
        row.pack(fill='x', pady=(0, 8))
        self.button(row, 'ARM SYSTEM', self.arm, color=ACCENT, fg=BG).pack(side='left', fill='x', expand=True, padx=(0, 6))
        self.button(row, 'STOP', lambda: self.stop('/api/stop'), color=SURFACE).pack(side='left', fill='x', expand=True)
        self.button(deck, 'EMERGENCY STOP  /  ESC', lambda: self.stop('/api/estop'), color='#502532', fg='#ffdfe5').pack(fill='x')
        self.button(deck, 'Reset emergency stop', lambda: self.stop('/api/reset'), color=PANEL, fg=MUTED, compact=True).pack(fill='x', pady=(4, 12))
        speedrow = tk.Frame(deck, bg=PANEL)
        speedrow.pack(fill='x')
        self.caption(speedrow, 'SPEED LIMIT', muted=True).pack(side='left')
        self.speed_label = tk.Label(speedrow, text='50%', bg=PANEL, fg=ACCENT, font=('Consolas', 11, 'bold'))
        self.speed_label.pack(side='right')
        ttk.Scale(deck, from_=0.1, to=1, variable=self.speed).pack(fill='x', pady=8)
        ttk.Checkbutton(deck, text='Pitch stabilization', variable=self.stabilize).pack(anchor='w', pady=3)
        ttk.Checkbutton(deck, text='Illumination', variable=self.light).pack(anchor='w', pady=3)
        self.caption(deck, 'SERVO CONTROL', muted=True).pack(anchor='w', pady=(16, 6))
        for name, keys in [('gimbal', 'J / L'), ('arm', 'U / O'), ('gripper', 'I / K')]:
            row = tk.Frame(deck, bg=PANEL)
            row.pack(fill='x', pady=3)
            tk.Label(row, text=name.title(), bg=PANEL, fg=TEXT, font=('Segoe UI', 10)).pack(side='left')
            tk.Label(row, text=keys, bg=PANEL, fg=MUTED, font=('Consolas', 9)).pack(side='left', padx=8)
            for label, step in [('+', 0.1), ('−', -0.1)]:
                self.button(row, label, lambda n=name, s=step: self.move_servo(n, s), color=SURFACE, compact=True).pack(side='right', padx=2)
        tk.Label(deck, text='SUBMARINE  R/F: depth thrust  T/G: pitch\nOne servo signal active at a time', bg=PANEL, fg=MUTED, font=('Segoe UI', 9), justify='left').pack(anchor='w', pady=(14, 0))
        sensors = tk.Frame(outer, bg=BG)
        sensors.pack(fill='x', pady=(16, 10))
        self.sensor_vars = {}
        for column, (name, title, initial) in enumerate([('pitch', 'PITCH', '— °'), ('temperature', 'TEMPERATURE', '— °C'), ('gas', 'MQ-2 DIGITAL', 'NO SENSOR'), ('servo', 'ACTIVE SERVO', 'IDLE')]):
            sensors.grid_columnconfigure(column, weight=1, uniform='sensors')
            card = self.panel(sensors)
            card.grid(row=0, column=column, sticky='ew', padx=(0 if column == 0 else 6, 0 if column == 3 else 6))
            self.caption(card, title, muted=True).pack(anchor='w', padx=14, pady=(12, 4))
            value = tk.StringVar(value=initial)
            self.sensor_vars[name] = value
            tk.Label(card, textvariable=value, bg=PANEL, fg=BLUE if name == 'pitch' else TEXT, font=('Consolas', 17, 'bold')).pack(anchor='w', padx=14, pady=(0, 12))
        bottom = self.panel(outer)
        bottom.pack(fill='x')
        self.telemetry = tk.Text(bottom, height=2, state='disabled', bg=PANEL, fg=MUTED, insertbackground=TEXT, borderwidth=0, highlightthickness=0, font=('Consolas', 9), padx=14, pady=8)
        self.telemetry.pack(fill='x')
        tk.Label(outer, textvariable=self.status, bg=BG, fg=MUTED, font=('Segoe UI', 9), anchor='w', wraplength=1180).pack(fill='x', pady=(10, 0))

    @staticmethod
    def panel(parent):
        return tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)

    @staticmethod
    def caption(parent, text, muted=False):
        return tk.Label(parent, text=text, bg=PANEL, fg=MUTED if muted else TEXT, font=('Segoe UI', 9, 'bold'))

    @staticmethod
    def button(parent, text, command, color=SURFACE, fg=TEXT, compact=False):
        return tk.Button(parent, text=text, command=command, bg=color, fg=fg, activebackground=LINE, activeforeground=TEXT,
                         font=('Segoe UI', 9 if compact else 10, 'bold'), relief='flat', borderwidth=0,
                         cursor='hand2', padx=10 if compact else 14, pady=5 if compact else 10, takefocus=False)

    def draw_placeholder(self, event=None):
        canvas = self.placeholder
        w, h = canvas.winfo_width(), canvas.winfo_height()
        canvas.delete('all')
        for x in range(0, w, 40):
            canvas.create_line(x, 0, x, h, fill='#111e30')
        for y in range(0, h, 40):
            canvas.create_line(0, y, w, y, fill='#111e30')
        cx, cy = w / 2, h / 2 - 24
        for radius in (48, 65):
            canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, outline=LINE, width=1)
        canvas.create_line(cx-80, cy, cx-33, cy, fill=BLUE)
        canvas.create_line(cx+33, cy, cx+80, cy, fill=BLUE)
        canvas.create_line(cx, cy-80, cx, cy-33, fill=BLUE)
        canvas.create_line(cx, cy+33, cx, cy+80, fill=BLUE)
        canvas.create_oval(cx-4, cy-4, cx+4, cy+4, fill=ACCENT, outline='')
        canvas.create_text(cx, cy+106, text='WAITING FOR VISUAL FEED', fill=TEXT, font=('Segoe UI', 12, 'bold'))
        canvas.create_text(cx, cy+132, text='Camera frames appear here when the Pi is connected', fill=MUTED, font=('Segoe UI', 9))
        for x, y, dx, dy in [(18,18,1,1), (w-18,18,-1,1), (18,h-18,1,-1), (w-18,h-18,-1,-1)]:
            canvas.create_line(x, y, x+20*dx, y, fill=BLUE, width=2)
            canvas.create_line(x, y, x, y+20*dy, fill=BLUE, width=2)

    def render_status(self, data):
        state = 'E-STOP' if data['estopped'] else ('ARMED' if data['armed'] else 'STANDBY')
        self.state_badge.configure(text='●  ' + state + (' / SIM' if data['simulate'] else ''), fg=RED if data['estopped'] else (ACCENT if data['armed'] else BLUE))
        telemetry = data['telemetry']
        self.sensor_vars['pitch'].set('— °' if telemetry['pitch_deg'] is None else '%.1f °' % telemetry['pitch_deg'])
        self.sensor_vars['temperature'].set('— °C' if telemetry['temperature_c'] is None else '%.1f °C' % telemetry['temperature_c'])
        self.sensor_vars['gas'].set('NO SENSOR' if telemetry['gas_alarm_raw'] is None else ('HIGH' if telemetry['gas_alarm_raw'] else 'LOW'))
        self.sensor_vars['servo'].set((data['active_servo'] or 'idle').upper())

    def connection_settings(self):
        if getattr(self, 'settings_window', None) and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.stop('/api/stop')
        dialog = tk.Toplevel(self.root)
        self.settings_window = dialog
        dialog.title('V.A.M.P. Connection')
        dialog.configure(bg=PANEL)
        dialog.geometry('560x460')
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        body = tk.Frame(dialog, bg=PANEL, padx=24, pady=24)
        body.pack(fill='both', expand=True)
        tk.Label(body, text='Connect to your platform', bg=PANEL, fg=TEXT, font=('Segoe UI', 18, 'bold')).pack(anchor='w', pady=(0, 14))
        address = tk.StringVar(value=self.client.url)
        token = tk.StringVar(value=self.client.token)
        model = tk.StringVar(value=str(self.weights or ''))
        for label, variable, masked in [('Robot address', address, False), ('Token (must match the Pi)', token, True)]:
            self.caption(body, label, muted=True).pack(anchor='w')
            tk.Entry(body, textvariable=variable, show='•' if masked else '', bg=SURFACE, fg=TEXT, insertbackground=TEXT, relief='flat', font=('Segoe UI', 11)).pack(fill='x', ipady=7, pady=(5, 12))
        self.caption(body, 'Optional trained model', muted=True).pack(anchor='w')
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill='x', pady=(5, 10))
        tk.Entry(row, textvariable=model, bg=SURFACE, fg=TEXT, insertbackground=TEXT, relief='flat').pack(side='left', fill='x', expand=True, ipady=7)
        self.button(row, 'Browse', lambda: model.set(filedialog.askopenfilename(parent=dialog, filetypes=[('YOLO weights', '*.pt')]) or model.get()), compact=True).pack(side='right', padx=(8, 0))
        note = 'Use http://127.0.0.1:8765 for a local simulator.\nChanges are applied when the app restarts.'
        tk.Label(body, text=note, bg=PANEL, fg=MUTED, justify='left', font=('Segoe UI', 9)).pack(anchor='w', pady=6)
        def save():
            try:
                if model.get() and not Path(model.get()).is_file():
                    raise ValueError('Selected model file does not exist')
                save_settings(address.get(), token.get(), model.get())
            except (ValueError, OSError) as exc:
                messagebox.showerror('Connection settings', str(exc), parent=dialog)
                return
            self.restart_settings = True
            dialog.destroy()
            self.close()
        self.button(body, 'SAVE & RESTART', save, color=ACCENT, fg=BG).pack(anchor='e', pady=(8, 0))
