"""Apply the two-DRV8833 layout wired using the supplied WiringPi chart.

Chart labels: left1=5/6, left2=12/13, right1=21/22, right2=23/24.
The saved GPIO values are BCM. No GPIO hardware is initialized here.
Optional DRV3: chart 10/11 and 26/27 become BCM 8/7 and 12/16.
"""
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

MOTORS = {
    'left1': [24, 25],
    'left2': [10, 9],
    'right1': [5, 6],
    'right2': [13, 19],
}
EXTRA_MOTORS = {'left3': [8, 7], 'right3': [12, 16]}


def updated_config(config, six_motor_crawler=False):
    result = copy.deepcopy(config)
    result['motors'] = copy.deepcopy(MOTORS)
    if six_motor_crawler:
        result['motors'].update(copy.deepcopy(EXTRA_MOTORS))
    result['profiles'] = {
        # The two installed drivers serve either attachment: two wheel motors
        # per side in crawler mode, or rear/vertical thrusters in submarine.
        'crawler': {'left': ['left1', 'left2'], 'right': ['right1', 'right2']},
        'submarine': {'left': ['left1'], 'right': ['right1'],
                      'vertical_front': 'left2', 'vertical_rear': 'right2'},
    }
    if six_motor_crawler:
        result['profiles']['crawler']['left'].append('left3')
        result['profiles']['crawler']['right'].append('right3')
    result['invert_motors'] = [name for name in config.get('invert_motors', []) if name in result['motors']]
    validate_config(result)
    return result


def configure(path, dry_run=False, six_motor_crawler=False):
    path = Path(path)
    original = path.read_bytes()
    current = json.loads(original.decode('utf-8'))
    result = updated_config(current, six_motor_crawler)
    if dry_run or result == current:
        return None
    # Retain the original bytes, including the token, once. Both backup and
    # temporary file names are ignored for the standard local config path.
    suffix = '.before-six-motor-crawler.bak' if six_motor_crawler else '.before-motor-remap.bak'
    backup = path.with_name(path.name + suffix)
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
            stream.write(json.dumps(result, indent=2) + '\n')
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'robot/config.local.json')
    parser.add_argument('--dry-run', action='store_true', help='Validate and show the motor map without writing')
    parser.add_argument('--six-motor-crawler', action='store_true',
                        help='Add DRV3 on BCM 8/7 and 12/16 for three crawler motors per side')
    args = parser.parse_args()
    try:
        backup = configure(args.config, args.dry_run, args.six_motor_crawler)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print('Motor layout (BCM GPIO, IN1 / IN2):')
    motors = {**MOTORS, **EXTRA_MOTORS} if args.six_motor_crawler else MOTORS
    for name, pair in motors.items():
        print(f'  {name}: {pair[0]} / {pair[1]}')
    if args.dry_run:
        print('Preview only; config unchanged.')
    else:
        print('Motor layout applied (or already current). Token, sensors and servo settings preserved.')
        if backup:
            print(f'Original config backup: {backup}')
        print('Restart vamp and select crawler for wheel motors or submarine for thrusters.')


if __name__ == '__main__':
    main()
