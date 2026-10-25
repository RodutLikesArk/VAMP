"""Small native-canvas 3D submarine attitude display; no OpenGL dependency."""
import math
import tkinter as tk

BG, GRID, TEXT, MUTED = '#0c1726', '#20354a', '#e8f2ff', '#8fa6c1'
CYAN, BLUE, GOLD = '#46e2ba', '#58b9ff', '#ffc76e'


def rotate(point, roll, pitch, yaw):
    x, y, z = point
    r, p, h = map(math.radians, (roll, -pitch, yaw))
    y, z = y*math.cos(r)-z*math.sin(r), y*math.sin(r)+z*math.cos(r)
    x, z = x*math.cos(p)+z*math.sin(p), -x*math.sin(p)+z*math.cos(p)
    return x*math.cos(h)-y*math.sin(h), x*math.sin(h)+y*math.cos(h), z


def submarine_faces():
    faces = []
    rings = [[(x, 0.30*math.cos(i*math.pi/4), 0.30*math.sin(i*math.pi/4)) for i in range(8)] for x in (-1.1, 0.85)]
    for i in range(8):
        j = (i+1) % 8
        faces.append(([rings[0][i], rings[0][j], rings[1][j], rings[1][i]], '#17483f', CYAN))
        faces.append(([rings[1][i], rings[1][j], (1.35, 0, 0)], '#254d6a', BLUE))
    faces.append((rings[0], '#193b3f', CYAN))
    for side in (-1, 1):
        faces.append(([(-0.9, side*.27, 0), (-1.2, side*.75, 0), (-0.45, side*.75, 0), (-0.4, side*.27, 0)], '#66502c', GOLD))
    faces.append(([(-1.0,0,.25), (-1.25,0,.75), (-.55,0,.75), (-.4,0,.25)], '#66502c', GOLD))
    return faces


class AttitudeIndicator(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=BG, height=188, width=270,
                         highlightbackground=GRID, highlightthickness=1)
        self.angles = None
        self.yaw_zero = 0.0
        self.caption = 'HW-123 · NO DATA'
        self.faces = submarine_faces()
        self.bind('<Configure>', lambda event: self.draw())
        self.bind('<Double-Button-1>', lambda event: self.zero_heading())
        self.draw()

    def set_telemetry(self, telemetry, simulate=False):
        angles = tuple(telemetry.get(k) for k in ('roll_deg', 'pitch_deg', 'yaw_deg'))
        valid = telemetry.get('orientation_valid') is True and all(type(v) in (float, int) and math.isfinite(v) for v in angles)
        self.angles = angles if valid else None
        if valid:
            self.caption = 'SIMULATED ATTITUDE' if simulate else 'HW-123 · LIVE ATTITUDE'
        elif telemetry.get('imu_calibrating'):
            progress = int(100*telemetry.get('imu_calibration_progress', 0))
            self.caption = f'KEEP STILL · CALIBRATING {progress}%'
        elif telemetry.get('imu_error'):
            self.caption = 'HW-123 · SENSOR UNAVAILABLE'
        elif telemetry.get('imu_enabled') is False:
            self.caption = 'HW-123 · DISABLED ON PI'
        else:
            self.caption = 'HW-123 · NO FRESH DATA'
        self.draw()

    def zero_heading(self):
        if self.angles:
            self.yaw_zero = self.angles[2]
            self.draw()

    def draw(self):
        self.delete('all')
        w, h = max(270, self.winfo_width()), max(188, self.winfo_height())
        self.create_text(12, 15, text=self.caption, fill=CYAN if self.angles else MUTED, anchor='w', font=('Segoe UI', 9, 'bold'))
        cx, cy = w/2, h*.47
        for dy in (-28, 0, 28):
            self.create_line(18, cy+dy, w-18, cy+dy, fill=GRID, dash=(3, 6))
        if not self.angles:
            self.create_oval(cx-24,cy-24,cx+24,cy+24,outline=GRID,width=2)
            self.create_text(cx,cy,text='—',fill=MUTED,font=('Consolas',22))
            self.create_text(cx,h-39,text='Pitch —   Roll —   Yaw —',fill=MUTED,font=('Consolas',10))
            self.create_text(cx,h-17,text='Waiting for calibrated sensor data',fill=MUTED,font=('Segoe UI',8))
            return
        roll, pitch, yaw = self.angles
        yaw = (yaw-self.yaw_zero+180)%360-180
        def transform(point):
            return rotate(point, roll, pitch, yaw)
        def project(point):
            x,y,z = point
            return cx+49*(.9*x-.55*y), cy+49*(.18*x+.30*y-.90*z)
        faces = []
        for points, fill, edge in self.faces:
            rotated = [transform(p) for p in points]
            depth = sum(.4*x+.7*y+.5*z for x,y,z in rotated)/len(rotated)
            coords = [v for p in rotated for v in project(p)]
            faces.append((depth, coords, fill, edge))
        for _, coords, fill, edge in sorted(faces, key=lambda item:item[0]):
            self.create_polygon(coords, fill=fill, outline=edge, width=1.3)
        nose = project(transform((1.6,0,0)))
        self.create_text(nose[0]+8,nose[1]-16, text='BOW', fill=BLUE, font=('Segoe UI',7,'bold'), anchor='s')
        self.create_text(cx,h-39,text=f'P {pitch:+05.1f}°  R {roll:+05.1f}°',fill=TEXT,font=('Consolas',10,'bold'))
        self.create_text(cx,h-17,text=f'Yaw {yaw:+06.1f}° rel. · Double-click to zero',fill=MUTED,font=('Segoe UI',8))
