"""Configure HW-123 without changing motor/servo wiring or the local token."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot.hardware import validate_config


def configure(path, enabled, address=None, direct_only=False):
    path = Path(path)
    if not path.is_file():
        raise ValueError('Create robot/config.local.json first')
    if direct_only and not enabled:
        raise ValueError('--direct-only requires --enable')
    original = path.read_bytes()
    current = json.loads(original.decode('utf-8'))
    config = copy.deepcopy(current)
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
    if direct_only:
        imu.update(bus=1, mux_channel=None)
        config.setdefault('i2c_mux', {})['enabled'] = False
        config.setdefault('environment', {})['enabled'] = False
        config['mq2_digital_pin'] = None
        config['temperature_device'] = None
    validate_config(config)
    if config == current:
        return None
    backup = None
    if direct_only:
        backup = path.with_name(path.name + '.before-direct-imu.bak')
        try:
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(original)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(config, indent=2)+'\n')
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--enable',action='store_true')
    flags.add_argument('--disable',action='store_true')
    parser.add_argument('--address',type=lambda value:int(value,0),choices=[104,105])
    parser.add_argument('--direct-only', action='store_true',
                        help='Enable the IMU directly on GPIO2/3; disable mux, environment and legacy auxiliary sensor readers')
    parser.add_argument('--config',type=Path,default=ROOT/'robot/config.local.json')
    args = parser.parse_args()
    try:
        backup = configure(args.config,args.enable,args.address,args.direct_only)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.error(str(exc))
    if args.direct_only:
        print('Direct IMU-only mode: bus 1, no mux channel; mux/environment/legacy auxiliary readers disabled.')
        print('Motor wiring, servos, token and IMU calibration settings preserved.')
        if backup:
            print('Original local config backup: '+str(backup))
    print('HW-123 '+('enabled' if args.enable else 'disabled')+'. Restart vamp to apply. Keep the sensor still for 2 seconds at startup.')


if __name__ == '__main__':
    main()
