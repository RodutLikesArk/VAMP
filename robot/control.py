import math
import threading
import time


def number(value, lo=-1, hi=1):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError('Expected finite number between %s and %s' % (lo, hi))
    return float(value)


class Controller:
    def __init__(self, hardware, clock=time.monotonic):
        self.hw, self.cfg, self.clock = hardware, hardware.config, clock
        self.lock = threading.RLock()
        self.mode, self.attachment = 'crawler', 'none'
        self.armed, self.estopped = False, False
        self.reason = 'Startup: select modules and arm'
        self.axes = dict(surge=0.0, yaw=0.0, heave=0.0, pitch=0.0)
        self.last_command, self.servo_until = 0.0, 0.0
        self.stabilize = False
        self.integral, self.previous_error = 0.0, None

    def halt(self, reason, latch=False):
        self.hw.stop()
        self.armed = False
        self.axes = dict.fromkeys(self.axes, 0.0)
        self.stabilize = False
        self.integral, self.previous_error = 0.0, None
        self.reason = reason
        self.estopped |= latch

    def configure(self, message):
        mode, attachment = message.get('mode'), message.get('attachment')
        if mode not in ('crawler', 'submarine') or attachment not in ('none', 'manipulator', 'scanner', 'led'):
            raise ValueError('Unknown module selection')
        with self.lock:
            self.halt('Modules selected; arm to drive')
            self.hw.set_light(False)
            self.mode, self.attachment = mode, attachment

    def arm(self):
        with self.lock:
            if self.estopped:
                raise ValueError('Reset emergency stop before arming')
            self.axes = dict.fromkeys(self.axes, 0.0)
            self.last_command = self.clock()
            self.armed, self.reason = True, None

    def command(self, message):
        if not isinstance(message, dict):
            raise ValueError('Expected command object')
        axes = {k: number(message.get(k, 0)) for k in self.axes}
        stabilize = message.get('stabilize', False)
        light = message.get('light', False)
        if type(stabilize) is not bool or type(light) is not bool:
            raise ValueError('stabilize and light must be booleans')
        servo = message.get('servo')
        if servo is not None:
            if not isinstance(servo, dict) or servo.get('name') not in self.cfg['servos']:
                raise ValueError('Unknown servo')
            servo = {'name': servo['name'], 'value': number(servo.get('value'))}
        with self.lock:
            if not self.armed or self.estopped:
                raise ValueError('Robot is not armed')
            if servo and servo['name'] != 'gimbal' and self.attachment != 'manipulator':
                raise ValueError('Select manipulator before commanding front servos')
            if stabilize and (self.mode != 'submarine' or not self.cfg['imu']['enabled']):
                raise ValueError('Stabilization requires submarine mode and enabled IMU')
            if stabilize and (self.hw.telemetry['pitch_deg'] is None or self.hw.last_imu_sample is None or time.monotonic() - self.hw.last_imu_sample > 0.5):
                raise ValueError('No valid IMU reading')
            self.axes, self.last_command = axes, self.clock()
            if self.stabilize != stabilize:
                self.integral, self.previous_error = 0.0, None
            self.stabilize = stabilize
            self.hw.set_light(light)
            if servo:
                self.hw.servo(servo['name'], servo['value'])
                self.servo_until = self.clock() + self.cfg['servo_release_seconds']

    def tick(self, dt=0.02):
        with self.lock:
            now = self.clock()
            if self.hw.active_servo and now >= self.servo_until:
                self.hw.release_servos()
            if not self.armed:
                return
            if now - self.last_command > self.cfg['watchdog_seconds']:
                self.halt('Command timeout; re-arm required')
                return
            a, p = self.axes, self.cfg['profiles'][self.mode]
            values = {}
            left, right = a['surge'] + a['yaw'], a['surge'] - a['yaw']
            scale = max(1.0, abs(left), abs(right))
            for key, value in [('left', left / scale), ('right', right / scale)]:
                for motor in p[key]:
                    values[motor] = value * self.cfg['max_speed']
            if self.mode == 'submarine':
                pitch = a['pitch']
                if self.stabilize:
                    measured = self.hw.telemetry['pitch_deg']
                    if measured is None or self.hw.last_imu_sample is None or time.monotonic() - self.hw.last_imu_sample > 0.5:
                        self.halt('IMU unavailable during stabilization')
                        return
                    error = -measured
                    self.integral = max(-20, min(20, self.integral + error * dt))
                    derivative = 0 if self.previous_error is None else (error - self.previous_error) / dt
                    self.previous_error = error
                    imu = self.cfg['imu']
                    correction = imu['kp']*error + imu['ki']*self.integral + imu['kd']*derivative
                    pitch += max(-imu['max_correction'], min(imu['max_correction'], correction))
                front, rear = a['heave'] + pitch, a['heave'] - pitch
                scale = max(1, abs(front), abs(rear))
                values[p['vertical_front']] = front / scale * self.cfg['max_speed']
                values[p['vertical_rear']] = rear / scale * self.cfg['max_speed']
            self.hw.drive(values)

    def status(self):
        with self.lock:
            return {'mode': self.mode, 'attachment': self.attachment, 'armed': self.armed,
                    'estopped': self.estopped, 'reason': self.reason, 'simulate': self.hw.simulate,
                    'motors': dict(self.hw.outputs), 'active_servo': self.hw.active_servo,
                    'servo_values': dict(self.hw.servo_values), 'light': self.hw.light,
                    'stabilize': self.stabilize, 'telemetry': dict(self.hw.telemetry)}
