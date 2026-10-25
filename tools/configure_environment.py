"""Configure TCA9548A + AHT10 + digital MQ-2, preserving motor wiring."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from robot.hardware import validate_config


def configure(path,enabled,mq2_gpio=26,mux_address=0x70,imu_channel=0,aht_channel=1,warmup_seconds=120,active_low=True):
    path = Path(path)
    config = json.loads(path.read_text())
    env = config.setdefault('environment',{})
    env['enabled'] = enabled
    if enabled:
        config['i2c_mux'] = {'enabled':True,'bus':1,'address':mux_address}
        # Existing IMU enable/sign/calibration settings remain unchanged.
        config['imu']['mux_channel'] = imu_channel
        config['imu']['bus'] = 1
        env['poll_seconds'] = 2.0
        env['aht10'] = {'enabled':True,'address':0x38,'bus':1,'mux_channel':aht_channel}
        env['mq2'] = {'enabled':True,'gpio':mq2_gpio,'active_low':active_low,'warmup_seconds':warmup_seconds}
        config['mq2_digital_pin'] = None
    validate_config(config)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(config,indent=2)+'\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--enable',action='store_true')
    flags.add_argument('--disable',action='store_true')
    parser.add_argument('--mq2-gpio',type=int,default=26)
    parser.add_argument('--mux-address',type=lambda v:int(v,0),default=0x70)
    parser.add_argument('--imu-channel',type=int,default=0)
    parser.add_argument('--aht-channel',type=int,default=1)
    parser.add_argument('--warmup-seconds',type=float,default=120)
    parser.add_argument('--active-high',action='store_true',help='Use only if your comparator triggers HIGH instead of LOW')
    parser.add_argument('--config',type=Path,default=ROOT/'robot/config.local.json')
    args = parser.parse_args()
    try:
        configure(args.config,args.enable,args.mq2_gpio,args.mux_address,args.imu_channel,args.aht_channel,args.warmup_seconds,not args.active_high)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.error(str(exc))
    print('Environment module '+('enabled' if args.enable else 'disabled')+'. Restart vamp to apply.')
    if args.enable:
        print('IMU: mux channel %d; AHT10: channel %d; MQ-2 D0: BCM GPIO%d through voltage reduction.' % (args.imu_channel,args.aht_channel,args.mq2_gpio))


if __name__ == '__main__':
    main()
