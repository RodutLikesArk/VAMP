# V.A.M.P. prototype software

Separate programs for the **PC operator** (`pc/`) and **Raspberry Pi robot** (`robot/`). Based on Short Description.docx: manual module selection, tethered Ethernet, six crawler motors, four submarine motors, live OV5647 camera, single-axis camera gimbal, two-axis manipulator, optional MPU6050/MQ-2/DS18B20, and laptop-side defect detection.

The document also contains an earlier documentation-writing conversation. Those requests were treated as reference text, not instructions to write competition documentation. Your current prototype constraints take precedence.

## Get the code onto the Raspberry Pi

Repository: https://github.com/RodutLikesArk/VAMP (private). On the Pi, sign in as an account with access, then clone:

```bash
sudo apt update
sudo apt install git gh
gh auth login --hostname github.com --git-protocol https --web
gh repo clone RodutLikesArk/VAMP
cd VAMP
```

GitHub prints a device code and a browser link; you can complete that sign-in on your PC. Continue with **Raspberry Pi setup** below. To download later code changes, stop the robot program and run `git pull --ff-only` from this directory. Keep your wiring changes in ignored `robot/config.local.json` so updates do not overwrite them.

## Windows desktop app

Download **VAMP-Operator.exe** from [GitHub Releases](https://github.com/RodutLikesArk/VAMP/releases/latest), then double-click it. Python installation and a terminal are not needed on the PC. The dark dashboard includes a live camera view, mobility/front-module selectors, telemetry, servo buttons, and emergency stop.

Open **Connection settings**, enter the Pi address (default `http://192.168.10.2:8765`) and matching token, then choose **Save & restart**. The app remembers these settings in `%APPDATA%\VAMP\operator.json`. Camera captures go to `Pictures\VAMP`. The Pi controller still runs from its terminal as described below.

The portable release includes control and camera viewing. For YOLO inference, use the optional AI build or the Python source version; the small portable release does not bundle PyTorch/Ultralytics. Selecting weights without those dependencies leaves live video available and reports that detection is unavailable.

If using the source version with Python and the PC dependencies already installed, double-click `VAMP.pyw` to launch without a console. Developers can rebuild the standalone app with `tools/build_windows.ps1`; use `-IncludeAI` for a larger build containing the optional detector.

## Developer simulation

Use Python 3.10 or newer with Tkinter. Run commands from this repository's root directory. On Windows, `py` can replace `python`.

```powershell
python -m pip install -r pc/requirements.txt
python -m robot.main --simulate --host 127.0.0.1
```

Open another terminal in the same directory:

```powershell
python -m pc.main --url http://127.0.0.1:8765
```

Choose mobility and front modules, press **ARM**, then hold **SPACE** and movement keys. Simulation displays the actual commanded motor values. It does not synthesize camera images or pretend to measure gas or temperature.

## Controls

| Input | Action |
| --- | --- |
| SPACE held | Enable propulsion while held |
| W / S | Forward / reverse |
| A / D | Turn left / right |
| R / F | Ascend / descend in submarine mode |
| T / G | Manual pitch, submarine only |
| J / L | Camera gimbal decrement / increment |
| U / O | Manipulator arm decrement / increment |
| I / K | Gripper decrement / increment |
| Esc | Latching software emergency stop |
| STOP | Stop and disarm |
| Reset E-stop, then ARM | Resume after emergency stop |

GUI +/- buttons also control servos. The operator slider scales the robot's configured `max_speed`; with both default settings, maximum output is 0.25. Changing a module stops/disarms the robot. Loss of application focus stops/disarms it. A failed command exchange stops the PC from resuming motion automatically. The Pi independently stops/disarms after 0.6 seconds without a valid command. Status requests do not extend that deadline.

Only one servo PWM signal is enabled at a time. Its signal is detached after 0.3 seconds unless another servo command refreshes it. Detaching PWM does **not** physically cut servo power, and it removes holding torque. Tune pulse limits and release time for your mechanism.

## Raspberry Pi setup

Copy the repository onto the Pi. Use Raspberry Pi OS with camera support and Python 3.10+. These commands install dependencies on the Pi; the repository does not create a PCB or require additional controllers.

```bash
sudo apt update
sudo apt install python3-gpiozero python3-picamera2 python3-smbus python3-venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r robot/requirements.txt
cp robot/config.json robot/config.local.json
```

Edit `robot/config.local.json` to match **your actual wiring** before setting `wiring_confirmed` to `true`. The included map is an example, not a claim about your existing wiring. Set `token` identically on the robot and PC. Enable I2C through Raspberry Pi configuration only if using the MPU6050; enable 1-wire only if using DS18B20. Test the camera using the Raspberry Pi OS camera utilities first. Run:

```bash
python -m robot.main --config robot/config.local.json
```

Connect both Ethernet interfaces on the same subnet, for example PC `192.168.10.1/24`, Pi `192.168.10.2/24`; no gateway is needed for this isolated link. Permit the application through the PC firewall when prompted. On the PC:

```powershell
python -m pc.main --url http://192.168.10.2:8765 --token vamp-prototype
```

The network service uses a bearer token over plain HTTP, intended for this private tether. Run one operator application at a time; multi-operator ownership is not implemented. Camera errors are reported without stopping control. The default stream is 720p/20 fps to reduce load on the Pi; 1920x1080 can be configured, but throughput and latency must be measured on your Pi.

## Start automatically on the Pi

After a successful manual start, press Ctrl+C to stop it. From your repository directory, run the installer **without sudo**; it requests sudo only for system service installation:

```bash
python3 tools/install_pi_service.py
systemctl status vamp --no-pager
```

The installer uses your actual repository path, virtual environment, local configuration, and current Pi username. It enables `vamp.service` at boot and starts it immediately. Hardware mode requires `wiring_confirmed=true`. The controller starts disarmed; ARM is still required in the PC app. For simulation startup instead, run `python3 tools/install_pi_service.py --simulate`. Re-run without that flag to switch back to hardware.

```bash
journalctl -u vamp -f               # live program logs; Ctrl+C exits log viewing
sudo systemctl restart vamp        # restart after a code/configuration update
sudo systemctl stop vamp           # stop for this boot
sudo systemctl disable --now vamp  # stop and remove automatic boot startup
```

Do not run a second manual controller while the service is active. For code updates, stop the service, run `git pull --ff-only`, then start it again with `sudo systemctl start vamp`. Failures are retried with a delay and limited to three starts per minute. After correcting a repeated startup failure, run `sudo systemctl reset-failed vamp` followed by `sudo systemctl start vamp`.

Service installation must be performed on the Pi; it cannot be applied to the Pi from the Windows build. The unit uses systemd's [service configuration](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html) and sends SIGINT on stop to trigger the controller's cleanup.

## Attachment connectors and motor mapping

For a complete bench prototype, use the [breadboard wiring guide](docs/breadboard-prototype.md): two printable sheets cover the power/motor/servo connections and exact sensor/divider breadboard holes, including HW-123, TCA9548A, AHT10 and MQ-2. All Pi GPIO numbers are BCM.

You confirmed **all DRV8833 boards are in the main chassis**. The Pi therefore drives DRV8833 input pins; no attachment firmware, UART, CAN, or I2C command protocol is assumed. A six-pin connector has no inherent data protocol.

Each independent N20 motor needs two driver-output wires. Three independently driven crawler motors on one side need six motor-output conductors through that side's connector. Four of those conductors cannot simultaneously serve as logic-data lines. If the connector really reserves two pins for shared power and four for signals, the electrical diagram must explain where those signals terminate; this software cannot infer that from connector size. Do not wire GPIOs directly to motors or to driver output terminals.

| Example logical channel | Example BCM driver inputs | Crawler use | Submarine use |
| --- | --- | --- | --- |
| left1 | 5, 6 | Left wheel 1 | Left rear thruster |
| left2 | 12, 13 | Left wheel 2 | Front vertical thruster |
| left3 | 16, 19 | Left wheel 3 | Off |
| right1 | 20, 21 | Right wheel 1 | Right rear thruster |
| right2 | 22, 23 | Right wheel 2 | Rear vertical thruster |
| right3 | 24, 25 | Right wheel 3 | Off |

Each pair connects to one DRV8833 channel's two **input** pins; its output pair connects to the motor. Five boards can support your ten motors across interchangeable modules; this example uses only the six channels needed by the largest installed module. If you use different driver channels for the submarine, add logical motors/pins and change its profile. The six-pin side connector's physical pin order is deliberately not invented here.

The example servo GPIOs are gimbal 17, arm 27, gripper 18. Optional LED, MQ-2 digital input, and temperature are disabled by default. BCM 2/3 are reserved for I2C and BCM 4 for default DS18B20 1-wire. Driver grounds and Pi signal ground must share a reference. GPIO sensor input levels must stay within the Pi's 3.3 V input range; do not feed a 5 V MQ-2 output directly into a GPIO. Servo supply comes from your BEC, not from GPIO pins.

`invert_motors` reverses named motor channels. Match the signs experimentally with the mechanism supported and propellers unloaded. Positive surge means forward; positive yaw means right turn; positive heave means up; positive pitch means nose up. The included geometry assumes vertical thrusters are separated **front to rear**. If they are side by side, differential thrust controls roll instead; change the mixer before enabling pitch stabilization. Four fixed thrusters do not establish independent control of every axis.

## HW-123 orientation display

The [submarine and gimbal wiring diagram](docs/submarine-minimum-wiring.md) includes the camera servo: signal on BCM GPIO17, power from the regulated 5 V BEC, and common ground. Optional manipulator defaults remain GPIO27 (arm) and GPIO18 (gripper).

HW-123 is an MPU-6050 six-axis accelerometer/gyroscope board. The Pi reader supports that chip over I2C, and the Windows app shows a small rotating 3D submarine over the lower-right corner of the camera view. It includes pitch, roll and **relative** yaw; there is no magnetometer or absolute compass heading. Double-click the visual to zero its displayed heading only. This does not change the controller's sensor reference or PID.

With all power off, connect the module as follows (read your board's labels; physical pin order can vary):

| HW-123 | Raspberry Pi |
| --- | --- |
| VCC | 3.3 V, physical pin 1 |
| GND | GND, physical pin 6 |
| SDA | GPIO2 / SDA1, physical pin 3 |
| SCL | GPIO3 / SCL1, physical pin 5 |
| AD0 | GND for address 0x68; 3.3 V selects 0x69 |
| INT, XDA, XCL | Leave unconnected for this reader |

Use 3.3 V supply/logic on the Pi side; never pull SDA/SCL up to 5 V. GPIO2/3 cannot also be motor or servo outputs. The configuration validator checks that conflict. Mount the sensor rigidly with X along the hull and Z upward. Validate the pitch/roll directions with hand tilts; `pitch_sign`, `roll_sign`, `yaw_sign` can each be 1 or -1, with per-axis `_offset_deg` adjustments. The visual treats positive displayed pitch as bow-up; set `pitch_sign` to match the actual mounting before using stabilization. Do not treat the board's temperature reading as water temperature.

Update both the Pi source and the Windows executable. On the Pi, from the project directory:

```bash
sudo systemctl stop vamp
git pull --ff-only
sudo raspi-config nonint do_i2c 0
sudo apt install -y i2c-tools
.venv/bin/python -m pip install -r robot/requirements.txt
sudo i2cdetect -y 1
.venv/bin/python tools/configure_imu.py --enable --address 0x68
sudo systemctl restart vamp
```

Use `--address 0x69` if that is the address shown by i2cdetect. If `/dev/i2c-1` is not yet present after enabling I2C, reboot the Pi and resume these steps. `configure_imu.py` modifies only the existing local IMU settings, preserving motor wiring and the token. It does not automatically enable stabilization. To disable the module, run the same command with `--disable` instead of `--enable`, then restart vamp.

Keep the module still for approximately 2 seconds at startup/reconnection. The widget shows calibration progress, then live attitude. Large movement resets calibration. Reads are checked against WHO_AM_I; missing hardware is retried in the background rather than preventing manual control from starting. No sensor data is fabricated when hardware is absent. Simulation reports an explicitly simulated level attitude when its IMU configuration is enabled.

Pitch/roll use a complementary filter with gyro-bias calibration and gravity correction. Relative yaw is integrated and will drift, especially near vertical orientations; this is a prototype attitude estimate, not a navigation system. A reading gap longer than 0.5 s triggers recalibration. Sensor data older than 0.5 s is unavailable in telemetry and stops active pitch stabilization. The PC also clears its visual after 0.75 s without a status update. Temperature-sensor reads run separately so they cannot stall the 50 Hz IMU loop or the motor watchdog.

References: [HW-123 manufacturer description](https://www.szhwmake.com/prod_view.aspx?FId=t3%3A95%3A3&Id=322&TypeId=95), [TDK MPU-6050 register map](https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map.pdf).

## Environment sensing module

TCA9548A routing, AHT10 air temperature/humidity, and MQ-2 digital comparator readings are supported. The Windows dashboard includes humidity, comparator startup suppression, and triggered/not-triggered states. [Complete BCM GPIO wiring and setup](docs/environment-wiring.md) includes the six-pin front connector assignment and 5 V-to-3.3 V MQ-2 divider.

Default wiring: GPIO2 SDA / GPIO3 SCL to the mux; HW-123 on mux channel 0; AHT10 on channel 1; MQ-2 D0 through voltage reduction to GPIO26. VCC/GND connect to the rails described in the guide. The mux is not an ADC: MQ-2 A0 remains unused without an ADC, and no ppm or atmosphere-safety result is inferred.

After physically wiring the sensors, stop vamp, update the Pi source, and run `.venv/bin/python tools/configure_environment.py --enable --mq2-gpio 26`, then restart vamp. This also changes the IMU route to mux channel 0; move its SDA/SCL wires accordingly. The helper preserves motor wiring and calibration. Sensors remain disabled in the supplied default configuration until explicitly enabled.

## Sensors and stabilization

- **HW-123 / MPU6050:** see the orientation-display instructions above. The optional PID still controls zero pitch only, requires direction checks/tuning, and stays disabled until selected in the GUI. There is no depth hold, because no depth/pressure sensor is specified.
- **DS18B20:** set `temperature_device` to the exact `28-...` device ID or `auto` for the first detected sensor. Reports temperature only; DS18B20 does not measure humidity.
- **MQ-2:** use the environment-module helper/guide above. `mq2_digital_pin` remains available for the older raw-digital configuration, but cannot be enabled alongside the new MQ-2 configuration. Analog readings still require an ADC.
- **LED:** set `led_pin` for a suitable output circuit. The GUI light checkbox controls it. RGB/message patterns are not implemented because the LED hardware and messages are unspecified.

## Optional PC defect detection

Use your custom trained YOLOv8 weights. The dataset and weights were not attached, so defect detection cannot be validated here and no generic object detector is substituted.

```powershell
python -m pip install ultralytics
python -m pc.main --url http://192.168.10.2:8765 --weights C:\path\to\best.pt
```

Inference runs in a separate PC worker and annotates video. Control and robot watchdog continue independently. Without `--weights`, the GUI simply displays live camera frames. **Save camera frame** writes a timestamped image to `captures/`.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests exercise controller behavior and real loopback HTTP in simulation: both mixers, motor bounds/inversion, inactive-channel shutdown, module changes, timeout disarming, invalid commands, authorization, emergency stop/reset, single-servo serialization, stale IMU handling, and MJPEG framing. Physical GPIO timing, motor direction, actual camera latency, PID tuning, and trained-model accuracy require the robot hardware.

## Implementation references

- [GPIO Zero output API](https://gpiozero.readthedocs.io/en/stable/api_output.html): BCM numbering and Motor/Servo interfaces.
- [Raspberry Pi Picamera2](https://github.com/raspberrypi/picamera2): camera configuration, JPEG encoding, and streaming output.
- [Ultralytics prediction API](https://docs.ultralytics.com/modes/predict/): optional laptop-side inference.
