"""Direct GPIO backend: drivers live in the main chassis, not in modules."""
import glob
import math
import time
from pathlib import Path
from .imu import MPU6050


def validate_config(c):
    imu = c['imu']
    if type(imu.get('enabled')) is not bool:
        raise ValueError('imu.enabled must be true or false')
    if imu.get('address', 104) not in (104, 105):
        raise ValueError('MPU-6050 address must be 104 (0x68) or 105 (0x69)')
    count = imu.get('calibration_samples', 100)
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError('IMU calibration_samples must be in 1..1000')
    tau = imu.get('filter_tau_seconds', 0.5)
    if type(tau) not in (int, float) or not math.isfinite(tau) or not 0.05 <= tau <= 10:
        raise ValueError('IMU filter_tau_seconds must be in 0.05..10')
    for axis in ('pitch', 'roll', 'yaw'):
        if imu.get(axis+'_sign', 1) not in (-1, 1):
            raise ValueError('IMU axis signs must be 1 or -1')
        offset = imu.get(axis+'_offset_deg', 0)
        if type(offset) not in (int, float) or not math.isfinite(offset):
            raise ValueError('IMU offsets must be finite numbers')
    pins = [p for pair in c['motors'].values() for p in pair]
    if any(len(pair) != 2 for pair in c['motors'].values()):
        raise ValueError('Every motor needs two driver input pins')
    pins += list(c['servos'].values())
    pins += [c[k] for k in ('led_pin', 'mq2_digital_pin') if c.get(k) is not None]
    if len(pins) != len(set(pins)) or any(type(p) is not int or not 0 <= p <= 27 for p in pins):
        raise ValueError('GPIO pins must be unique BCM integers in 0..27')
    if c['imu']['enabled'] and (2 in pins or 3 in pins):
        raise ValueError('GPIO 2/3 are reserved for the enabled I2C IMU')
    if 4 in pins and c.get('temperature_device'):
        raise ValueError('GPIO 4 is reserved for the default 1-wire bus')
    for name, profile in c['profiles'].items():
        used = profile['left'] + profile['right']
        if name == 'submarine':
            used += [profile['vertical_front'], profile['vertical_rear']]
        if len(used) != len(set(used)) or any(m not in c['motors'] for m in used):
            raise ValueError('Profiles must refer to distinct configured motors')
    if not set(c.get('invert_motors', [])) <= set(c['motors']):
        raise ValueError('Unknown inverted motor')
    for key, lower, upper in [('max_speed', 0.01, 1), ('watchdog_seconds', 0.1, 2), ('servo_release_seconds', 0.05, 2)]:
        value = c[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError('Invalid ' + key)


class Hardware:
    def __init__(self, config, simulate=False):
        validate_config(config)
        self.config, self.simulate = config, simulate
        self.motors, self.servos, self.led, self.gas, self.bus = {}, {}, None, None, None
        self.outputs = dict.fromkeys(config['motors'], 0.0)
        self.active_servo = None
        self.servo_values = dict.fromkeys(config['servos'], 0.0)
        self.light = False
        self.last_imu_sample = None
        self.imu = None
        self.next_imu_retry = 0.0
        self.aux_error = None
        self.telemetry = {'pitch_deg': None, 'roll_deg': None, 'yaw_deg': None,
                          'orientation_valid': False, 'imu_calibrating': False,
                          'imu_calibration_progress': 0.0, 'imu_error': None,
                          'imu_temperature_c': None, 'temperature_c': None,
                          'gas_alarm_raw': None, 'sensor_error': None}
        if simulate:
            return
        if not config['wiring_confirmed']:
            raise ValueError('Set wiring_confirmed only after mapping config GPIOs to your actual wiring')
        from gpiozero import Motor, Servo, LED, DigitalInputDevice
        try:
            for name, pair in config['motors'].items():
                self.motors[name] = Motor(*pair, pwm=True)
            low, high = config['servo_pulse_ms']
            for name, pin in config['servos'].items():
                self.servos[name] = Servo(pin, initial_value=None, min_pulse_width=low / 1000, max_pulse_width=high / 1000)
            if config.get('led_pin') is not None:
                self.led = LED(config['led_pin'])
            if config.get('mq2_digital_pin') is not None:
                self.gas = DigitalInputDevice(config['mq2_digital_pin'], pull_up=False)
            # IMU initialization happens in its own reader thread. A missing
            # optional module must not prevent manual robot control from booting.
        except Exception:
            self.close()
            raise

    def drive(self, values):
        for name in self.outputs:
            value = values.get(name, 0.0)
            value = max(-1.0, min(1.0, value))
            if name in self.config['invert_motors']:
                value = -value
            if not self.simulate:
                self.motors[name].value = value
            self.outputs[name] = value

    def servo(self, name, value):
        self.release_servos()  # Never leave two PWM servo outputs active.
        if not self.simulate:
            self.servos[name].value = value
        self.active_servo = name
        self.servo_values[name] = value

    def release_servos(self):
        for device in self.servos.values():
            device.detach()
        self.active_servo = None

    def set_light(self, enabled):
        self.light = enabled
        if self.led:
            self.led.value = enabled

    def sample(self):
        self.sample_imu()
        self.sample_aux()

    def sample_imu(self):
        if not self.config['imu']['enabled']:
            return
        if self.simulate:
            self.telemetry.update(pitch_deg=0.0, roll_deg=0.0, yaw_deg=0.0,
                                  orientation_valid=True, imu_calibrating=False,
                                  imu_calibration_progress=1.0, imu_error=None)
            self.last_imu_sample = time.monotonic()
            return
        if time.monotonic() < self.next_imu_retry:
            return
        try:
            if self.bus is None:
                from smbus2 import SMBus
                self.bus = SMBus(self.config['imu']['bus'])
            if self.imu is None:
                self.imu = MPU6050(self.bus, self.config['imu'])
            reading = self.imu.read()
            reading['imu_error'] = None
            self.telemetry.update(reading)
            self.last_imu_sample = time.monotonic() if reading['orientation_valid'] else None
        except Exception as exc:
            self.telemetry.update(pitch_deg=None, roll_deg=None, yaw_deg=None,
                                  orientation_valid=False, imu_calibrating=False,
                                  imu_error='HW-123: '+str(exc))
            self.last_imu_sample = None
            self.imu = None
            if self.bus:
                try:
                    self.bus.close()
                except OSError:
                    pass
            self.bus = None
            self.next_imu_retry = time.monotonic() + 1.0

    def sample_aux(self):
        if self.simulate:
            return
        errors = []
        self.telemetry['temperature_c'] = None
        if self.config.get('temperature_device'):
            try:
                device = self.config['temperature_device']
                paths = glob.glob('/sys/bus/w1/devices/28-*/w1_slave') if device == 'auto' else [str(Path('/sys/bus/w1/devices') / device / 'w1_slave')]
                text = Path(paths[0]).read_text()
                if not text.splitlines()[0].endswith('YES'):
                    raise ValueError('DS18B20 CRC failed')
                self.telemetry['temperature_c'] = int(text.split('t=')[1]) / 1000
            except Exception as exc:
                errors.append('Temperature: ' + str(exc))
        self.telemetry['gas_alarm_raw'] = bool(self.gas.value) if self.gas else None
        self.aux_error = '; '.join(errors) or None

    def telemetry_snapshot(self):
        result = dict(self.telemetry)
        result['imu_enabled'] = self.config['imu']['enabled']
        age = None if self.last_imu_sample is None else time.monotonic()-self.last_imu_sample
        result['imu_age_s'] = age
        if age is None or age > 0.5:
            result.update(pitch_deg=None, roll_deg=None, yaw_deg=None, orientation_valid=False)
        result['sensor_error'] = '; '.join(e for e in (result.get('imu_error'), self.aux_error) if e) or None
        return result

    def stop(self):
        self.drive({})
        self.release_servos()

    def close(self):
        for motor in self.motors.values():
            motor.stop()
            motor.close()
        for servo in self.servos.values():
            servo.detach()
            servo.close()
        for device in (self.led, self.gas, self.bus):
            if device is not None:
                device.close()
