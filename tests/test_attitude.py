import math
import tkinter as tk
import unittest

from pc.attitude import AttitudeIndicator, rotate


class AttitudeTests(unittest.TestCase):
    def test_rotation_preserves_model_size(self):
        point = (1.2,.3,-.7)
        rotated = rotate(point,45,30,120)
        self.assertAlmostEqual(sum(x*x for x in point),sum(x*x for x in rotated))

    def test_canvas_live_zero_calibration_and_missing_data(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            view = AttitudeIndicator(root)
            view.pack()
            root.update_idletasks()
            view.set_telemetry({'orientation_valid':True,'roll_deg':20,'pitch_deg':30,'yaw_deg':45})
            self.assertEqual(view.angles,(20,30,45))
            self.assertGreater(len(view.find_all()),20)
            view.zero_heading()
            self.assertEqual(view.yaw_zero,45)
            view.set_telemetry({'imu_calibrating':True,'imu_calibration_progress':.5})
            self.assertIsNone(view.angles)
            self.assertIn('50%',view.caption)
            view.set_telemetry({})
            self.assertIsNone(view.angles)
            view.set_telemetry({'orientation_valid':True,'roll_deg':float('nan'),'pitch_deg':0,'yaw_deg':0})
            self.assertIsNone(view.angles)
        finally:
            root.destroy()
