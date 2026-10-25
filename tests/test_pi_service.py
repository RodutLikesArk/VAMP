import unittest

from tools.install_pi_service import quote_path, render_unit


class ServiceTests(unittest.TestCase):
    def test_hardware_uses_local_config_and_venv(self):
        unit = render_unit('/home/tudor/VAMP', 'tudor')
        self.assertIn('User=tudor\n', unit)
        self.assertIn('WorkingDirectory=/home/tudor/VAMP\n', unit)
        self.assertNotIn('WorkingDirectory="', unit)
        self.assertIn('"/home/tudor/VAMP/.venv/bin/python" -u -m robot.main', unit)
        self.assertIn('--config "/home/tudor/VAMP/robot/config.local.json"', unit)
        self.assertIn('KillSignal=SIGINT', unit)
        self.assertNotIn('--simulate', unit)

    def test_simulation_mode_and_space_in_directory(self):
        unit = render_unit('/home/pi/My Robot', 'pi', True)
        self.assertIn('WorkingDirectory=/home/pi/My Robot\n', unit)
        self.assertIn(' --simulate\n', unit)

    def test_working_directory_uses_path_not_command_escaping(self):
        unit = render_unit('/home/pi/50% $robot', 'pi')
        self.assertIn('WorkingDirectory=/home/pi/50%% $robot\n', unit)
        self.assertIn('"/home/pi/50%% $$robot/.venv/bin/python"', unit)

    def test_invalid_user_and_path_rejected(self):
        with self.assertRaises(ValueError):
            render_unit('/home/pi/VAMP', 'pi\nUser=root')
        with self.assertRaises(ValueError):
            quote_path('/home/pi/VAMP\nExecStart=/bin/false')
