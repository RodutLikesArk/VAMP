import copy
import json
import math
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from robot.imu import MPU6050
from robot.hardware import Hardware, validate_config
from robot.i2c import I2CRouter
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

    def test_direct_only_preserves_robot_settings_and_backs_up_mux_setup(self):
        config = copy.deepcopy(CONFIG)
        config['token'] = 'private-local-value'
        config['wiring_confirmed'] = True
        config['imu'].update(enabled=True, bus=2, mux_channel=0, pitch_sign=-1, pitch_offset_deg=3)
        config['i2c_mux'].update(enabled=True, bus=2)
        config['environment']['enabled'] = True
        config['mq2_digital_pin'] = 4
        config['temperature_device'] = 'auto'
        original = json.dumps(config, indent=4).encode()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            path.write_bytes(original)
            backup = configure(path, True, 0x68, direct_only=True)
            saved = json.loads(path.read_text())
            self.assertEqual(backup.read_bytes(), original)
            self.assertTrue(saved['imu']['enabled'])
            self.assertEqual(saved['imu']['bus'], 1)
            self.assertIsNone(saved['imu']['mux_channel'])
            self.assertFalse(saved['i2c_mux']['enabled'])
            self.assertFalse(saved['environment']['enabled'])
            self.assertIsNone(saved['mq2_digital_pin'])
            self.assertIsNone(saved['temperature_device'])
            for key in config.keys() - {'imu','i2c_mux','environment','mq2_digital_pin','temperature_device'}:
                self.assertEqual(saved[key], config[key], key)
            for key in config['imu'].keys() - {'enabled','bus','address','mux_channel'}:
                self.assertEqual(saved['imu'][key], config['imu'][key], key)
            self.assertIsNone(configure(path, True, 0x68, direct_only=True))
            self.assertEqual(backup.read_bytes(), original)
            physical = Mock()
            router = I2CRouter(saved['i2c_mux'], factory=lambda n: physical)
            router.route(1, saved['imu']['mux_channel']).read_byte_data(0x68, 0x75)
            physical.read_byte_data.assert_called_once_with(0x68, 0x75)
            physical.write_byte.assert_not_called()  # No TCA9548A required.
            router.close()

    def test_direct_only_invalid_pin_leaves_original_file_untouched(self):
        config = copy.deepcopy(CONFIG)
        config['motors']['left1'] = [2, 6]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            original = json.dumps(config).encode()
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                configure(path, True, direct_only=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_direct_only_failed_write_keeps_original_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            original = json.dumps(CONFIG).encode()
            path.write_bytes(original)
            with patch.object(Path, 'replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    configure(path, True, direct_only=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.with_name(path.name+'.before-direct-imu.bak').read_bytes(), original)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_direct_only_cannot_be_combined_with_disable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            path.write_text(json.dumps(CONFIG))
            with self.assertRaisesRegex(ValueError, 'requires --enable'):
                configure(path, False, direct_only=True)

    def test_regular_enable_keeps_existing_mux_and_environment_setup(self):
        config = copy.deepcopy(CONFIG)
        config['i2c_mux']['enabled'] = True
        config['imu']['mux_channel'] = 0
        config['environment']['enabled'] = True
        config['environment']['mq2']['enabled'] = True
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            path.write_text(json.dumps(config))
            configure(path, True, 0x68)
            saved = json.loads(path.read_text())
        self.assertTrue(saved['imu']['enabled'])
        self.assertEqual(saved['imu']['mux_channel'], 0)
        self.assertEqual(saved['i2c_mux'], config['i2c_mux'])
        self.assertEqual(saved['environment'], config['environment'])
