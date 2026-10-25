"""HW-123 / MPU-6050 reader with stationary gyro calibration and tilt fusion.

Register units: accelerometer +/-2g (16384 LSB/g), gyro +/-250 dps
(131 LSB/dps). Yaw is integrated, relative and subject to drift: no compass.
"""
import math
import struct
import time


def wrap(angle):
    return (angle + 180) % 360 - 180


class MPU6050:
    def __init__(self, bus, config, clock=time.monotonic):
        self.bus, self.config, self.clock = bus, config, clock
        self.address = config.get('address', 0x68)
        identity = bus.read_byte_data(self.address, 0x75)
        if identity not in (0x68, 0x69):
            raise ValueError(f'Expected MPU-6050 WHO_AM_I 0x68; got 0x{identity:02x}')
        for register, value in [(0x6B, 1), (0x1A, 3), (0x19, 4), (0x1B, 0), (0x1C, 0)]:
            bus.write_byte_data(self.address, register, value)
        self.samples = int(config.get('calibration_samples', 100))
        self.count = 0
        self.total = [0.0, 0.0, 0.0]
        self.bias = None
        self.last_time = None
        self.roll = self.pitch = self.yaw = 0.0

    def read(self):
        now = self.clock()
        raw = self.bus.read_i2c_block_data(self.address, 0x3B, 14)
        if len(raw) != 14:
            raise ValueError('Incomplete MPU-6050 reading')
        ax, ay, az, temperature, gx, gy, gz = struct.unpack('>7h', bytes(raw))
        if ax == ay == az == 0:
            raise ValueError('Invalid zero accelerometer sample')
        accel = [v / 16384 for v in (ax, ay, az)]
        gyro = [v / 131 for v in (gx, gy, gz)]
        norm = math.sqrt(sum(v*v for v in accel))
        measured_roll = math.degrees(math.atan2(ay, az))
        measured_pitch = math.degrees(math.atan2(-ax, math.hypot(ay, az)))
        dt = 0 if self.last_time is None else now - self.last_time
        if dt > 0.5:
            # A read gap invalidates integrated motion. Recalibrate rather than
            # displaying an invented heading across an unobserved interval.
            self.bias, self.count, self.total = None, 0, [0.0, 0.0, 0.0]
        self.last_time = now
        if self.bias is None:
            if not 0.9 <= norm <= 1.1 or max(abs(v) for v in gyro) > 5:
                self.count, self.total = 0, [0.0, 0.0, 0.0]
            else:
                self.count += 1
                self.total = [s+v for s, v in zip(self.total, gyro)]
            if self.count < self.samples:
                return {'orientation_valid': False, 'imu_calibrating': True,
                        'imu_calibration_progress': self.count / self.samples,
                        'pitch_deg': None, 'roll_deg': None, 'yaw_deg': None,
                        'imu_temperature_c': temperature / 340 + 36.53}
            self.bias = [v/self.count for v in self.total]
            self.roll, self.pitch, self.yaw = measured_roll, measured_pitch, 0.0
        elif dt > 0:
            p, q, r = [v-b for v, b in zip(gyro, self.bias)]
            phi, theta = math.radians(self.roll), math.radians(self.pitch)
            cosine = math.cos(theta)
            # Body rates -> Euler rates away from the Euler singularity. Near
            # vertical, use body rates and gravity correction to avoid spikes.
            if abs(cosine) > 0.15:
                roll_rate = p + (q*math.sin(phi)+r*math.cos(phi))*math.tan(theta)
                pitch_rate = q*math.cos(phi)-r*math.sin(phi)
                yaw_rate = (q*math.sin(phi)+r*math.cos(phi))/cosine
            else:
                roll_rate, pitch_rate, yaw_rate = p, q, r
            alpha = math.exp(-dt / self.config.get('filter_tau_seconds', 0.5))
            self.roll = wrap(self.roll + roll_rate*dt)
            self.pitch = wrap(self.pitch + pitch_rate*dt)
            # Ignore gravity correction under large linear acceleration.
            if 0.8 <= norm <= 1.2:
                self.roll = wrap(self.roll + (1-alpha)*wrap(measured_roll-self.roll))
                self.pitch = wrap(self.pitch + (1-alpha)*wrap(measured_pitch-self.pitch))
            self.yaw = wrap(self.yaw + yaw_rate*dt)
        result = {'orientation_valid': True, 'imu_calibrating': False,
                  'imu_calibration_progress': 1.0, 'imu_temperature_c': temperature/340+36.53}
        for axis in ('pitch', 'roll', 'yaw'):
            result[axis+'_deg'] = wrap(getattr(self, axis)*self.config.get(axis+'_sign', 1) - self.config.get(axis+'_offset_deg', 0))
        return result
