import copy
import json
import math
from pathlib import Path
import struct
import tempfile
import time
import unittest

from robot.imu import MPU6050
from robot.hardware import Hardware, validate_config
from tools.configure_imu import configure
from test_controller import CONFIG, Clock


class Bus:
    def __init__(self, identity=0x68):
        self.identity = identity
        self.writes = []
        self.values = (0,0,16384,0,0,0,0)
        self.closed = False
        self.fail = False
    def read_byte_data(self, address, register):
        return self.identity
    def write_byte_data(self, address, register, value):
        self.writes.append((address,register,value))
    def read_i2c_block_data(self,address,register,count):
        if self.fail:
            raise OSError('I2C disconnected')
        return list(struct.pack('>7h',*self.values))
    def close(self):
        self.closed = True


class ImuTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(CONFIG['imu'])
        self.config['calibration_samples'] = 2
        self.clock, self.bus = Clock(), Bus()
        self.imu = MPU6050(self.bus,self.config,self.clock)
    def sample(self):
        self.clock.now += .02
        return self.imu.read()
    def ready(self):
        self.sample()
        return self.sample()

    def test_configured_ranges_and_level_calibration(self):
        self.assertIn((104,0x1B,0),self.bus.writes)
        first = self.sample()
        self.assertFalse(first['orientation_valid'])
        self.assertTrue(first['imu_calibrating'])
        result = self.sample()
        self.assertTrue(result['orientation_valid'])
        for axis in ('roll_deg','pitch_deg','yaw_deg'):
            self.assertAlmostEqual(result[axis],0)
        self.assertAlmostEqual(result['imu_temperature_c'],36.53)

    def test_motion_restarts_calibration(self):
        self.sample()
        self.bus.values = (0,0,16384,0,0,0,1310)
        self.assertEqual(self.sample()['imu_calibration_progress'],0)

    def test_relative_yaw_integrates_known_rate(self):
        self.ready()
        self.bus.values = (0,0,16384,0,0,0,90*131)
        for _ in range(50):
            result = self.sample()
        self.assertAlmostEqual(result['yaw_deg'],90,places=5)
        self.assertAlmostEqual(result['pitch_deg'],0)

    def test_stationary_bias_is_removed(self):
        self.bus.values = (0,0,16384,0,131,131,131)
        self.ready()
        for _ in range(50):
            result = self.sample()
        self.assertAlmostEqual(result['yaw_deg'],0)

    def test_tilt_filter_and_mounting_signs(self):
        self.config['pitch_sign'] = -1
        self.ready()
        self.bus.values = (-11585,0,11585,0,0,0,0)
        for _ in range(150):
            result = self.sample()
        self.assertAlmostEqual(result['pitch_deg'],-45,delta=.2)
        self.assertAlmostEqual(result['roll_deg'],0,delta=.2)

    def test_gap_invalidates_and_recalibrates(self):
        self.ready()
        self.clock.now += 1
        result = self.sample()
        self.assertFalse(result['orientation_valid'])
        self.assertIsNone(result['yaw_deg'])

    def test_wrong_identity_and_zero_sample_rejected(self):
        with self.assertRaises(ValueError):
            MPU6050(Bus(0x00),self.config)
        self.bus.values = (0,0,0,0,0,0,0)
        with self.assertRaises(ValueError):
            self.sample()

    def test_disconnect_clears_orientation_and_closes_bus(self):
        config = copy.deepcopy(CONFIG)
        config['imu'].update(enabled=True,calibration_samples=1)
        hw = Hardware(config,True)
        hw.simulate = False
        hw.bus = self.bus
        hw.sample_imu()
        self.assertTrue(hw.telemetry_snapshot()['orientation_valid'])
        self.bus.fail = True
        hw.sample_imu()
        result = hw.telemetry_snapshot()
        self.assertFalse(result['orientation_valid'])
        self.assertIsNone(result['pitch_deg'])
        self.assertIn('I2C disconnected',result['imu_error'])
        self.assertTrue(self.bus.closed)

    def test_stale_snapshot_hides_last_angles(self):
        config = copy.deepcopy(CONFIG)
        config['imu']['enabled'] = True
        hw = Hardware(config,True)
        hw.sample_imu()
        hw.last_imu_sample = time.monotonic()-1
        result = hw.telemetry_snapshot()
        self.assertFalse(result['orientation_valid'])
        self.assertIsNone(result['roll_deg'])

    def test_configuration_helper_preserves_existing_wiring(self):
        config = copy.deepcopy(CONFIG)
        config['custom_note'] = 'keep me'
        config['imu'].pop('roll_sign')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            path.write_text(json.dumps(config))
            configure(path,True,0x69)
            saved = json.loads(path.read_text())
        self.assertEqual(saved['motors'],config['motors'])
        self.assertEqual(saved['custom_note'],'keep me')
        self.assertEqual(saved['imu']['address'],105)
        self.assertEqual(saved['imu']['roll_sign'],1)

    def test_i2c_pins_cannot_overlap_motors(self):
        config = copy.deepcopy(CONFIG)
        config['imu']['enabled'] = True
        config['motors']['left1'] = [2,6]
        with self.assertRaises(ValueError):
            validate_config(config)
