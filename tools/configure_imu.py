"""Enable/disable HW-123 in the Pi's local config without changing wiring."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot.hardware import validate_config


def configure(path, enabled, address=None):
    path = Path(path)
    if not path.is_file():
        raise ValueError('Create robot/config.local.json first')
    config = json.loads(path.read_text())
    imu = config.setdefault('imu', {})
    imu['enabled'] = enabled
    imu['model'] = 'HW-123 / MPU-6050'
    if address is not None:
        imu['address'] = address
    defaults = {'bus':1, 'address':104, 'calibration_samples':100,
                'filter_tau_seconds':0.5, 'roll_sign':1, 'roll_offset_deg':0,
                'yaw_sign':1, 'yaw_offset_deg':0}
    for key, value in defaults.items():
        imu.setdefault(key,value)
    validate_config(config)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(config,indent=2)+'\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--enable',action='store_true')
    flags.add_argument('--disable',action='store_true')
    parser.add_argument('--address',type=lambda value:int(value,0),choices=[104,105])
    parser.add_argument('--config',type=Path,default=ROOT/'robot/config.local.json')
    args = parser.parse_args()
    try:
        configure(args.config,args.enable,args.address)
    except (ValueError,OSError) as exc:
        parser.error(str(exc))
    print('HW-123 '+('enabled' if args.enable else 'disabled')+'. Restart vamp to apply. Keep the sensor still for 2 seconds at startup.')


if __name__ == '__main__':
    main()
