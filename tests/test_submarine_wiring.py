import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from robot.control import Controller
from robot.hardware import Hardware
from tools.configure_submarine_wiring import configure, updated_config
from test_controller import CONFIG, Clock


class SubmarineWiringTests(unittest.TestCase):
    def test_mapping_preserves_local_settings_and_original_backup(self):
        config = copy.deepcopy(CONFIG)
        config.update(token='private-local-token', wiring_confirmed=True, max_speed=0.3)
        config['imu'].update(enabled=True, pitch_sign=-1, mux_channel=0)
        config['i2c_mux']['enabled'] = True
        config['invert_motors'] = ['left1', 'left3', 'right3']
        config['environment']['enabled'] = True
        config['environment']['mq2']['enabled'] = True
        original = json.dumps(config, indent=4).encode('utf-8')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            path.write_bytes(original)
            backup = configure(path)
            self.assertEqual(backup.read_bytes(), original)
            result = json.loads(path.read_text())
            self.assertEqual(result['motors'], {
                'left1': [24, 25], 'left2': [10, 9],
                'right1': [5, 6], 'right2': [13, 19]})
            self.assertEqual(result['invert_motors'], ['left1'])
            for key in config.keys() - {'motors', 'profiles', 'invert_motors'}:
                self.assertEqual(result[key], config[key], key)
            self.assertIsNone(configure(path))
            self.assertEqual(backup.read_bytes(), original)
            # Upgrade a previously installed four-motor preset whose crawler
            # profile only contained the rear pair; keep the first backup.
            result['profiles']['crawler'] = {'left': ['left1'], 'right': ['right1']}
            path.write_text(json.dumps(result))
            configure(path)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['profiles']['crawler'], {
                'left': ['left1', 'left2'], 'right': ['right1', 'right2']})
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_conflicting_sensor_pin_leaves_file_untouched(self):
        config = copy.deepcopy(CONFIG)
        config['i2c_mux']['enabled'] = True
        config['environment']['enabled'] = True
        config['environment']['mq2'].update(enabled=True, gpio=24)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            original = json.dumps(config).encode()
            path.write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'unique BCM'):
                configure(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_preview_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            path.write_text(json.dumps(CONFIG))
            original = path.read_bytes()
            configure(path, dry_run=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_failed_replace_preserves_config_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.local.json'
            original = json.dumps(CONFIG).encode()
            path.write_bytes(original)
            with patch.object(Path, 'replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    configure(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.with_name(path.name+'.before-motor-remap.bak').read_bytes(), original)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_four_motor_yaw_and_pitch_use_separate_pairs(self):
        config = updated_config(CONFIG)
        hw = Hardware(config, simulate=True)
        controller = Controller(hw, Clock())
        controller.configure({'mode': 'submarine', 'attachment': 'none'})
        controller.arm()
        for command, expected in [
            ({'surge': 1}, {'left1': .5, 'left2': 0, 'right1': .5, 'right2': 0}),
            ({'yaw': 1}, {'left1': .5, 'left2': 0, 'right1': -.5, 'right2': 0}),
            ({'pitch': 1}, {'left1': 0, 'left2': .5, 'right1': 0, 'right2': -.5}),
            ({'heave': 1}, {'left1': 0, 'left2': .5, 'right1': 0, 'right2': .5}),
        ]:
            with self.subTest(command=command):
                controller.command(command)
                controller.tick()
                self.assertEqual(hw.outputs, expected)
        controller.configure({'mode': 'crawler', 'attachment': 'none'})
        controller.arm()
        controller.command({'surge': 1})
        controller.tick()
        self.assertEqual(hw.outputs, {'left1': .5, 'left2': .5, 'right1': .5, 'right2': .5})
        controller.halt('test stop')
        self.assertTrue(all(value == 0 for value in hw.outputs.values()))
