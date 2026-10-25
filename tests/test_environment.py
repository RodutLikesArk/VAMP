import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

from robot.environment import AHT10,mq2_state
from robot.hardware import Hardware,validate_config
from robot.i2c import I2CRouter
from tools.configure_environment import configure
from test_controller import CONFIG,Clock


def frame(temperature=25,humidity=50,status=8):
    rh=round(humidity*1048576/100)
    temp=round((temperature+50)*1048576/200)
    return bytes([status,(rh>>12)&255,(rh>>4)&255,((rh&15)<<4)|((temp>>16)&15),(temp>>8)&255,temp&255])


class AhtBus:
    def __init__(self,data=None):
        self.data=frame() if data is None else data
        self.writes=[]
    def write_i2c_block_data(self,*args): self.writes.append(args)
    def read_bytes(self,*args): return self.data


class PhysicalBus:
    def __init__(self):
        self.selected=0
        self.operations=[]
        self.closed=False
        self.fail=False
    def write_byte(self,address,mask):
        self.selected=mask
        self.operations.append(('select',mask))
    def read_byte_data(self,address,register):
        expected=1 if address==0x68 else 2
        if self.selected != expected:
            raise AssertionError('Transaction used the wrong mux channel')
        time.sleep(.0001)
        if self.selected != expected:
            raise AssertionError('Channel changed during an active transaction')
        if self.fail: raise OSError('sensor disconnected')
        self.operations.append(('read',address,self.selected))
        return 0x68
    def close(self): self.closed=True


class EnvironmentTests(unittest.TestCase):
    def test_aht10_decodes_reference_values(self):
        for temperature,humidity in [(25,50),(-10,10),(70,90)]:
            reading=AHT10.decode(frame(temperature,humidity))
            self.assertAlmostEqual(reading['temperature_c'],temperature,places=3)
            self.assertAlmostEqual(reading['humidity_percent'],humidity,places=3)

    def test_aht10_initializes_and_measures(self):
        bus=AhtBus()
        sensor=AHT10(bus,sleep=lambda seconds:None)
        self.assertAlmostEqual(sensor.read()['temperature_c'],25)
        self.assertEqual(bus.writes,[(0x38,0xE1,[8,0]),(0x38,0xAC,[0x33,0])])

    def test_busy_uncalibrated_short_and_invalid_frames_rejected(self):
        for data in [frame(status=0x88),frame(status=0),b'bad',frame(temperature=-45)]:
            with self.subTest(data=data),self.assertRaises(ValueError): AHT10.decode(data)

    def test_conversion_timeout_is_bounded(self):
        clock=Clock()
        def sleep(seconds): clock.now+=seconds
        sensor=AHT10(AhtBus(frame(status=0x88)),sleep=sleep,clock=clock)
        with self.assertRaises(TimeoutError): sensor.read()
        self.assertLess(clock.now,11)

    def test_mux_selection_and_error_cleanup(self):
        physical=PhysicalBus()
        router=I2CRouter({'enabled':True,'address':0x70,'bus':1},factory=lambda n:physical)
        bus=router.route(1,0)
        self.assertEqual(bus.read_byte_data(0x68,0x75),0x68)
        self.assertEqual(physical.selected,0)
        physical.fail=True
        with self.assertRaises(OSError): bus.read_byte_data(0x68,0x75)
        self.assertEqual(physical.selected,0)
        bus.close()
        self.assertFalse(physical.closed)
        router.close()
        self.assertTrue(physical.closed)

    def test_mux_is_atomic_between_sensor_threads(self):
        physical=PhysicalBus()
        router=I2CRouter({'enabled':True,'address':0x70},factory=lambda n:physical)
        errors=[]
        def reader(channel,address):
            try:
                bus=router.route(1,channel)
                for _ in range(50): bus.read_byte_data(address,0)
            except Exception as exc: errors.append(exc)
        threads=[threading.Thread(target=reader,args=(0,0x68)),threading.Thread(target=reader,args=(1,0x38))]
        for thread in threads: thread.start()
        for thread in threads: thread.join(2)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors,[])
        self.assertEqual(len([op for op in physical.operations if op[0]=='read']),100)

    def test_mq2_warmup_and_polarity(self):
        waiting=mq2_state(False,True,10,120)
        self.assertIsNone(waiting['gas_triggered'])
        self.assertEqual(waiting['gas_warmup_remaining_s'],110)
        self.assertTrue(mq2_state(False,True,121,120)['gas_triggered'])
        self.assertFalse(mq2_state(True,True,121,120)['gas_triggered'])
        self.assertTrue(mq2_state(True,False,121,120)['gas_triggered'])

    def enabled_config(self):
        config=copy.deepcopy(CONFIG)
        config['i2c_mux']['enabled']=True
        config['environment']['enabled']=True
        config['environment']['mq2']['enabled']=True
        return config

    def test_environment_sampling_staleness_and_failure(self):
        config=self.enabled_config()
        hw=Hardware(config,True)
        hw.simulate=False
        hw.gas=SimpleNamespace(value=False)
        hw.aht=SimpleNamespace(read=lambda:{'temperature_c':24.5,'humidity_percent':48.2})
        hw.sample_aux()
        self.assertTrue(hw.telemetry_snapshot()['environment_valid'])
        self.assertAlmostEqual(hw.telemetry['temperature_c'],24.5)
        self.assertTrue(hw.telemetry['gas_warming_up'])
        hw.gas_started=time.monotonic()-121
        hw.sample_aux()
        self.assertTrue(hw.telemetry['gas_triggered'])
        hw.last_environment_sample=time.monotonic()-10
        snapshot=hw.telemetry_snapshot()
        self.assertIsNone(snapshot['humidity_percent'])
        self.assertIsNone(snapshot['temperature_c'])
        def fail(): raise OSError('module removed')
        hw.aht=SimpleNamespace(read=fail)
        hw.next_environment_sample=0
        hw.sample_aux()
        self.assertIn('module removed',hw.telemetry_snapshot()['environment_error'])
        self.assertFalse(hw.telemetry_snapshot()['environment_valid'])

    def test_config_helper_preserves_wiring_and_imu_calibration(self):
        config=copy.deepcopy(CONFIG)
        config['imu']['enabled']=True
        config['imu']['pitch_sign']=-1
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.local.json';path.write_text(json.dumps(config))
            configure(path,True)
            saved=json.loads(path.read_text())
        self.assertEqual(saved['motors'],config['motors'])
        self.assertEqual(saved['token'],config['token'])
        self.assertEqual(saved['imu']['pitch_sign'],-1)
        self.assertEqual(saved['imu']['mux_channel'],0)
        self.assertEqual(saved['environment']['aht10']['mux_channel'],1)

    def test_invalid_gpio_and_channel_overlap_rejected(self):
        config=self.enabled_config()
        config['environment']['mq2']['gpio']=5
        with self.assertRaises(ValueError): validate_config(config)
        config=self.enabled_config()
        config['imu'].update(enabled=True,mux_channel=1)
        with self.assertRaises(ValueError): validate_config(config)
