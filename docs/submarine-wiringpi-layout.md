# Your two-driver motor layout

This preset matches the four motor-input pairs connected using the **WiringPi labels on your supplied chart**: 5/6, 12/13, 21/22 and 23/24. The V.A.M.P. program uses **BCM GPIO numbering** and saves the converted numbers below. The change is for motor inputs; your servo, sensor, token and supply settings are preserved.

| Motor | Driver inputs, in order | WiringPi chart labels | BCM values saved in the program | Motor outputs |
| --- | --- | --- | --- | --- |
| Rear left / left1 | DRV1 AIN1 / AIN2 | 5 / 6 | 24 / 25 | AO1 / AO2 |
| Vertical front / left2 | DRV1 BIN1 / BIN2 | 12 / 13 | 10 / 9 | BO1 / BO2 |
| Rear right / right1 | DRV2 AIN1 / AIN2 | 21 / 22 | 5 / 6 | AO1 / AO2 |
| Vertical rear / right2 | DRV2 BIN1 / BIN2 | 23 / 24 | 13 / 19 | BO1 / BO2 |

The repository's older submarine/breadboard diagrams illustrate the original default BCM motor map. Use this table for your changed motor wiring. Sensor and power connections still follow their existing guides. BCM9/10 have SPI functions too; keep those pins available for the driver inputs rather than assigning them to an SPI peripheral.

## Apply on the Raspberry Pi

From the existing VAMP directory:

```bash
cd ~/VAMP
sudo systemctl stop vamp &&
git pull --ff-only &&
python3 tools/configure_submarine_wiring.py &&
sudo systemctl restart vamp
```

`git pull` alone leaves your ignored `robot/config.local.json` unchanged. The setup command updates that local file, removes the unused left3/right3 channels and their profile references, and retains inversions only for installed motors. It checks the resulting configuration before writing, backs up the original file once to `robot/config.local.json.before-motor-remap.bak`, then replaces the configuration atomically. The backup contains your token and is ignored by Git. An invalid result, including a conflicting sensor/servo GPIO, leaves your existing file unchanged and reports an error.

The helper does not initialize GPIOs or run motors. It preserves `wiring_confirmed`; your existing hardware setup must already have this set after checking the actual wiring. It requires an existing `robot/config.local.json`. A preview is available with `python3 tools/configure_submarine_wiring.py --dry-run`.

In the PC app select **submarine**, leave **Pitch stabilization unchecked** for the initial test, then ARM with the mechanism supported and propellers unloaded. No new Windows executable is needed.

| Hold | Expected response |
| --- | --- |
| SPACE + W | Both rear motors |
| SPACE + A or D | Both rear motors in opposite directions |
| SPACE + R | Both vertical motors |
| SPACE + T | Both vertical motors in opposite directions |

With the crawler attachment installed, crawler mode drives **two motors per side**: left1/left2 and right1/right2. With the submarine attachment installed, select submarine: W/S and A/D operate the rear pair, while R/F and T/G operate the vertical pair. Directions can be reversed per motor with `invert_motors` after verifying the physical installation. If you applied an earlier version of this helper that only drove two crawler motors, pull the update and run it again to update your local profile.

If it fails to start, run `journalctl -u vamp -n 50 --no-pager`. To restore the original local configuration, stop the service, copy the backup over `robot/config.local.json`, then restart. Review the backup's previous GPIO assignments before using it.

Conversion reference: [WiringPi's official pin-to-BCM mapping](https://github.com/WiringPi/WiringPi/blob/master/wiringPi/wiringPi.c).
