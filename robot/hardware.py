"""Direct GPIO backend: drivers live in the main chassis, not in modules."""
import glob
import math
import time
from pathlib import Path


def validate_config(c):
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
        self.telemetry = {'pitch_deg': None, 'temperature_c': None, 'gas_alarm_raw': None, 'sensor_error': None}
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
            if config['imu']['enabled']:
                from smbus2 import SMBus
                self.bus = SMBus(config['imu']['bus'])
                address = config['imu']['address']
                self.bus.write_byte_data(address, 0x6B, 0)
                self.bus.write_byte_data(address, 0x1C, 0)  # +/-2g
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
        if self.simulate:
            self.telemetry.update(pitch_deg=0.0 if self.config['imu']['enabled'] else None)
            self.last_imu_sample = time.monotonic() if self.config['imu']['enabled'] else None
            return
        errors = []
        self.telemetry['pitch_deg'] = None
        if self.bus:
            try:
                data = self.bus.read_i2c_block_data(self.config['imu']['address'], 0x3B, 6)
                def signed(i):
                    v = (data[i] << 8) | data[i + 1]
                    return v - 65536 if v >= 32768 else v
                x, y, z = (signed(i) for i in (0, 2, 4))
                if x == y == z == 0:
                    raise ValueError('Invalid zero IMU sample')
                pitch = math.degrees(math.atan2(-x, math.sqrt(y*y + z*z)))
                self.telemetry['pitch_deg'] = pitch * self.config['imu']['pitch_sign'] - self.config['imu']['pitch_offset_deg']
                self.last_imu_sample = time.monotonic()
            except Exception as exc:
                errors.append('IMU: ' + str(exc))
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
        self.telemetry['sensor_error'] = '; '.join(errors) or None

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
