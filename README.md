# V.A.M.P. prototype software

Separate programs for the **PC operator** (`pc/`) and **Raspberry Pi robot** (`robot/`). Based on Short Description.docx: manual module selection, tethered Ethernet, six crawler motors, four submarine motors, live OV5647 camera, single-axis camera gimbal, two-axis manipulator, optional MPU6050/MQ-2/DS18B20, and laptop-side defect detection.

The document also contains an earlier documentation-writing conversation. Those requests were treated as reference text, not instructions to write competition documentation. Your current prototype constraints take precedence.

## Try it on the PC first

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

## Attachment connectors and motor mapping

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

## Sensors and stabilization

- **MPU6050:** `imu.enabled=true` enables I2C accelerometer pitch readings. Align sensor X with robot forward and Z with up, set `pitch_sign`/`pitch_offset_deg`, and validate the correction direction before enabling the GUI checkbox. The optional PID aims for zero pitch; it is disabled by default and requires tuning. Pitch is accelerometer-derived and can be disturbed by acceleration; this is a starting point, not a validated attitude estimator. Missing/stale IMU data disarms stabilization. There is no depth hold, because no depth/pressure sensor is specified.
- **DS18B20:** set `temperature_device` to the exact `28-...` device ID or `auto` for the first detected sensor. Reports temperature only; DS18B20 does not measure humidity.
- **MQ-2:** set `mq2_digital_pin` to a mapped free BCM pin after confirming input voltage. Reports the raw comparator state only. Analog readings require an ADC, which was not specified. No gas concentration, gas identity, or assessment of atmosphere safety is inferred from the digital signal.
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
