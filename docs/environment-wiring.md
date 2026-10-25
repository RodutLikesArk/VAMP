# Environment module wiring and setup

This setup uses TCA9548A channel 0 for HW-123/MPU-6050, channel 1 for AHT10, and BCM GPIO26 for the MQ-2 board's digital comparator output. It adds temperature, relative humidity, startup-delay status, and a gas-threshold indication to the PC app. No ADC is needed for the digital output; no gas concentration or gas identification is calculated.

All GPIO names here are **BCM numbers**, not positions on the Pi header. **3V3, 5V and GND are power rails, not GPIO numbers. GPIO3 is the I2C clock; it is not the 3.3 V supply.** Make connections with power off.

## Pi and multiplexer

| Connection | Destination |
| --- | --- |
| Pi GPIO2 / SDA1 | TCA9548A SDA (upstream) |
| Pi GPIO3 / SCL1 | TCA9548A SCL (upstream) |
| Regulated 3V3 rail | TCA9548A VCC/VIN, HW-123 VCC, AHT10 VCC |
| GND | Pi, TCA9548A, HW-123, AHT10, MQ-2 and regulator grounds |
| TCA9548A A0, A1, A2 | GND, selecting address 0x70; these are address straps, not extra Pi GPIOs |
| TCA9548A RESET/RST | Keep HIGH with the board's pull-up; if absent, add 10 kΩ to 3V3 |

Use the module's actual labels. Each downstream I2C channel needs pull-ups to 3V3; the sensor breakouts often include them. If a channel has none, add approximately 4.7 kΩ from its SDA to 3V3 and SCL to 3V3. Do not add pull-ups to 5 V in this arrangement. No additional Pi GPIO is needed to select mux channels: the software sends selection commands over I2C.

| Multiplexer channel | Sensor connections |
| --- | --- |
| SD0 | HW-123 SDA |
| SC0 | HW-123 SCL |
| SD1 | AHT10 SDA |
| SC1 | AHT10 SCL |

**Move the HW-123's SDA/SCL wires to SD0/SC0** when enabling this setup. Its AD0 remains GND for address 0x68, or 3V3 for 0x69. Keep its INT/XDA/XCL unused. The AHT10 uses address 0x38. TCA9548A channels are separate branches of GPIO2/3, not new GPIO numbers.

## MQ-2 breakout board

This is for a powered module labelled VCC, GND, A0/AO and D0/DO, not the bare six-legged sensor can.

| MQ-2 pin | Connection |
| --- | --- |
| VCC | Regulated **5 V BEC rail**, not 3V3, a GPIO output, raw 3S, or the 6 V motor rail |
| GND | Common GND |
| D0 / DO | BCM **GPIO26 through the divider below** |
| A0 / AO | Leave unconnected; analog measurement needs an ADC |

Do not connect a 5 V D0 output directly to the Pi. A simple proposed divider is:

```text
MQ-2 D0 ── 10 kΩ ──┬── GPIO26
                    │
                   15 kΩ
                    │
                   GND
```

For an ideal 5 V output this produces 3.0 V. Comparator-board pull-ups can lower the actual HIGH voltage; verify LOW and HIGH at the divider node before connecting it to the Pi. HIGH must be a valid 3.3 V logic input level and never exceed 3.3 V. If your module cannot produce a clean HIGH through the divider, use a suitable 5 V-to-3.3 V logic interface instead. The code disables GPIO26's internal pulls because the divider already provides a pull-down. The TCA9548A is not an ADC and does not turn MQ-2's A0 or D0 into I2C.

The default comparator polarity is active LOW. Check your board's D0 indicator/voltage and use `--active-high` only if it triggers HIGH instead. The module's potentiometer sets the comparator threshold. D0 by itself cannot detect every disconnected-board condition.

The MQ-2 heater needs 5 V and can consume up to roughly 0.95 W (about 190 mA), in addition to the Pi and other loads. Keep the AHT10 away from that heater so it measures ambient air rather than the MQ-2's local heat. Use the environment module in air, not submerged.

The app uses a configurable 120-second **startup suppression delay** before showing the interpreted comparator state. This is not sensor calibration or proof of readiness. Winsen specifies at least 48 hours of preheating under its standard test conditions; condition/stabilize the actual sensor and set its comparator threshold before interpreting results. The UI says TRIGGERED or NOT TRIGGERED relative to that setpoint, never ppm, gas identity, or a declaration that an atmosphere is safe.

## Proposed six-pin front connector

These are example contact assignments on your detachable connector, **not Pi physical header numbers**. Match both halves to the actual connector before powering it.

| Contact | Function |
| --- | --- |
| 1 | 5 V to MQ-2 VCC |
| 2 | Common GND |
| 3 | 3V3 to AHT10 VCC |
| 4 | TCA9548A SD1 to AHT10 SDA |
| 5 | TCA9548A SC1 to AHT10 SCL |
| 6 | Raw MQ-2 D0 back to the divider in the main chassis; only the divider node connects to GPIO26 |

The IMU and multiplexer stay in the main chassis. The AHT10 and MQ-2 go on the environment module. This sensor connector assignment is specific to the environment module; do not assume it is interchangeable with the manipulator's servo wiring.

## Update and enable

Download the updated Windows executable, then run these commands on the Pi from its VAMP directory:

```bash
sudo systemctl stop vamp
git pull --ff-only
sudo raspi-config nonint do_i2c 0
sudo apt install -y i2c-tools
.venv/bin/python -m pip install -r robot/requirements.txt
.venv/bin/python tools/configure_environment.py --enable --mq2-gpio 26
sudo systemctl restart vamp
```

The helper enables mux address 0x70, routes the existing IMU to channel 0, enables AHT10 on channel 1, and configures digital MQ-2. It preserves your motor wiring, token, IMU enable flag and calibration signs. If GPIO26 is already assigned in your local wiring, it reports a conflict instead of moving another output. Choose an actually free BCM pin with `--mq2-gpio`. Options also include `--mux-address`, `--imu-channel`, `--aht-channel`, `--warmup-seconds` and `--active-high`.

Select **scanner** as the front attachment in the PC app. Enabled sensors continue sampling even while disarmed; the selector does not switch sensor power. The AHT10 is polled approximately every 2 seconds. Missing/stale readings are blanked and reported instead of held as live values. The IMU keeps its separate 50 Hz reader. Sensor threads share a lock only during channel selection + an individual bus transaction, never through the AHT10's conversion delay.

To disable environment sampling, run `.venv/bin/python tools/configure_environment.py --disable` and restart vamp. This leaves mux/IMU routing intact because the IMU is still physically connected through it. It does not turn off the MQ-2 heater's physical supply.

## Check I2C routing

Stop the service while manually selecting channels; otherwise its reader will change them during the scan:

```bash
sudo systemctl stop vamp
sudo i2cdetect -y 1                  # normally sees mux 0x70
sudo i2cset -y 1 0x70 0x01          # select channel 0
sudo i2cdetect -y 1                  # HW-123 should appear as 0x68 or 0x69
sudo i2cset -y 1 0x70 0x02          # select channel 1
sudo i2cdetect -y 1                  # AHT10 should appear as 0x38
sudo i2cset -y 1 0x70 0x00          # deselect all
sudo systemctl restart vamp
journalctl -u vamp -n 40 --no-pager
```

The application deselects channels after every transaction, so a normal upstream scan may show only 0x70. That does not mean downstream sensors are absent.

Sources: [TI TCA9548A datasheet](https://www.ti.com/lit/ds/symlink/tca9548a.pdf), [Aosong AHT10 manual, mirrored manufacturer document](https://dinistor.ru/files/AOSONG_AHT10_EN.PDF), [Winsen MQ-2 specifications](https://www.winsen-sensor.com/product/mq-2.html?by=mq-sensor).
