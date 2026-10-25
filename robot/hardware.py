"""Direct GPIO backend: drivers live in the main chassis, not in modules."""
import glob
import math
import time
from pathlib import Path
from .imu import MPU6050
from .i2c import I2CRouter
from .environment import AHT10, mq2_state


def validate_config(c):
    mux = c.get('i2c_mux',{})
    env = c.get('environment',{})
    aht = env.get('aht10',{})
    mq = env.get('mq2',{})
    env_enabled = env.get('enabled',False)
    for flag in (mux.get('enabled',False),env_enabled,aht.get('enabled',False),mq.get('enabled',False),mq.get('active_low',True)):
        if type(flag) is not bool:
            raise ValueError('Sensor enable/active_low flags must be booleans')
    if not 0x70 <= mux.get('address',0x70) <= 0x77:
        raise ValueError('TCA9548A address must be 0x70..0x77')
    if aht.get('address',0x38) != 0x38:
        raise ValueError('This AHT10 driver uses address 0x38')
    for name,value,minimum in [('environment interval',env.get('poll_seconds',2.0),2),('MQ-2 startup delay',mq.get('warmup_seconds',120),0)]:
        if type(value) not in (int,float) or not math.isfinite(value) or value < minimum:
            raise ValueError('Invalid '+name)
    routes = [(c['imu'].get('bus',1),c['imu'].get('mux_channel'),c['imu']['enabled'])]
    routes += [(aht.get('bus',1),aht.get('mux_channel'),env_enabled and aht.get('enabled',False))]
    for bus,channel,enabled in routes:
        if enabled and channel is not None:
            if not mux.get('enabled') or type(channel) is not int or not 0 <= channel <= 7 or bus != mux.get('bus',1):
                raise ValueError('Sensor mux routes require enabled TCA9548A, matching bus and channel 0..7')
    if all(route[2] for route in routes) and routes[0][:2] == routes[1][:2]:
        raise ValueError('Keep AHT10 on its own multiplexer channel')
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
    if env_enabled and mq.get('enabled',False):
        if c.get('mq2_digital_pin') is not None:
            raise ValueError('Use environment.mq2 or legacy mq2_digital_pin, not both')
        pins.append(mq.get('gpio',26))
    if len(pins) != len(set(pins)) or any(type(p) is not int or not 0 <= p <= 27 for p in pins):
        raise ValueError('GPIO pins must be unique BCM integers in 0..27')
    if (c['imu']['enabled'] or mux.get('enabled') or (env_enabled and aht.get('enabled'))) and (2 in pins or 3 in pins):
        raise ValueError('GPIO 2/3 are reserved for enabled I2C devices')
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
        self.i2c = I2CRouter(config.get('i2c_mux'))
        self.aht = None
        self.next_environment_sample = 0.0
        self.last_environment_sample = None
        self.environment_error = None
        self.gas_started = time.monotonic()
        self.last_gas_sample = None
        self.gas_error = None
        self.telemetry = {'pitch_deg': None, 'roll_deg': None, 'yaw_deg': None,
                          'orientation_valid': False, 'imu_calibrating': False,
                          'imu_calibration_progress': 0.0, 'imu_error': None,
                          'imu_temperature_c': None, 'temperature_c': None,
                          'gas_alarm_raw': None, 'sensor_error': None,
                          'humidity_percent':None,'environment_temperature_c':None,
                          'environment_valid':False,'environment_error':None,
                          'gas_triggered':None,'gas_warming_up':False,'gas_warmup_remaining_s':0}
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
            mq = config.get('environment',{}).get('mq2',{})
            if config.get('environment',{}).get('enabled') and mq.get('enabled'):
                # External voltage divider provides the pull-down; internal
                # pulls would alter its ratio. active_state=True keeps raw HIGH.
                self.gas = DigitalInputDevice(mq.get('gpio',26),pull_up=None,active_state=True)
            elif config.get('mq2_digital_pin') is not None:
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
                self.bus = self.i2c.route(self.config['imu']['bus'],self.config['imu'].get('mux_channel'))
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
        env = self.config.get('environment',{})
        if env.get('enabled'):
            if env.get('aht10',{}).get('enabled'):
                self.sample_environment()
                self.telemetry['temperature_c'] = self.telemetry['environment_temperature_c']
            mq = env.get('mq2',{})
            if mq.get('enabled') and self.gas is not None:
                try:
                    self.telemetry.update(mq2_state(self.gas.value,mq.get('active_low',True),
                                                   time.monotonic()-self.gas_started,mq.get('warmup_seconds',120)))
                    self.last_gas_sample = time.monotonic()
                    self.gas_error = None
                except Exception as exc:
                    self.telemetry.update(gas_alarm_raw=None,gas_triggered=None,gas_warming_up=False)
                    self.gas_error = 'MQ-2: '+str(exc)
        elif self.gas is not None:
            self.telemetry['gas_alarm_raw'] = bool(self.gas.value)
            self.last_gas_sample = time.monotonic()
        self.aux_error = '; '.join(errors) or None

    def sample_environment(self):
        if time.monotonic() < self.next_environment_sample:
            return
        settings = self.config['environment'].get('aht10',{})
        try:
            if self.aht is None:
                bus = self.i2c.route(settings.get('bus',1),settings.get('mux_channel'))
                self.aht = AHT10(bus,settings.get('address',0x38))
            reading = self.aht.read()
            if self.last_environment_sample is None:
                self.gas_started = time.monotonic()
            self.telemetry.update(environment_temperature_c=reading['temperature_c'],
                                  humidity_percent=reading['humidity_percent'],environment_valid=True)
            self.last_environment_sample = time.monotonic()
            self.environment_error = None
        except Exception as exc:
            self.telemetry.update(environment_temperature_c=None,humidity_percent=None,environment_valid=False)
            self.last_environment_sample = None
            self.environment_error = 'AHT10: '+str(exc)
            self.aht = None
        self.next_environment_sample = time.monotonic()+self.config['environment'].get('poll_seconds',2.0)

    def telemetry_snapshot(self):
        result = dict(self.telemetry)
        result['imu_enabled'] = self.config['imu']['enabled']
        age = None if self.last_imu_sample is None else time.monotonic()-self.last_imu_sample
        result['imu_age_s'] = age
        env = self.config.get('environment',{})
        result['environment_enabled'] = env.get('enabled',False)
        result['environment_error'] = self.environment_error
        result['gas_error'] = self.gas_error
        if self.last_gas_sample is None or time.monotonic()-self.last_gas_sample > 3:
            result.update(gas_alarm_raw=None,gas_triggered=None,gas_warming_up=False)
        result['environment_age_s'] = None if self.last_environment_sample is None else time.monotonic()-self.last_environment_sample
        if result['environment_age_s'] is None or result['environment_age_s'] > max(5,env.get('poll_seconds',2)*2.5):
            result.update(environment_temperature_c=None,humidity_percent=None,environment_valid=False)
            if env.get('enabled') and env.get('aht10',{}).get('enabled'):
                result['temperature_c'] = None
        if age is None or age > 0.5:
            result.update(pitch_deg=None, roll_deg=None, yaw_deg=None, orientation_valid=False)
        result['sensor_error'] = '; '.join(e for e in (result.get('imu_error'),self.environment_error,self.gas_error,self.aux_error) if e) or None
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
        for device in (self.led,self.gas,self.bus,self.i2c):
            if device is not None:
                device.close()
