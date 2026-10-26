"""Draw the complete BCM wiring and a labelled breadboard patch panel.

Run with Python to create SVG files. Render the SVGs to PNG, then use --pdf
with ReportLab installed to assemble the printable A3 landscape guide.
Only the patch panel has physical hole coordinates; module pins use labels.
"""
from html import escape
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs'
W, H = 2400, 1700
INK, MUTED = '#172c40', '#52677b'
P5, P3, GND, VM = '#cb3447', '#b57608', '#334155', '#a03c9d'
SIG, SDA, SCL, MOT = '#1675b6', '#008574', '#7155b5', '#18805b'
CFG = json.loads((ROOT / 'robot/config.json').read_text(encoding='utf-8'))


class Sheet:
    def __init__(self, title, subtitle, page):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
                      f'<rect width="{W}" height="{H}" fill="white"/>',
                      '<style>text {font-family:Arial,sans-serif;fill:#172c40}</style>']
        self.text(60, 65, title, 38, bold=True)
        self.text(60, 105, subtitle, 23, MUTED)
        self.line([(60, 135), (2340, 135)], '#c9d5de', 2)
        self.text(60, 1668, 'V.A.M.P. | Default robot/config.json | Module drawings use pin LABELS, not physical footprints.', 19, MUTED)
        self.text(2340, 1668, f'{page} / 2', 21, MUTED, anchor='end')

    def text(self, x, y, value, size=23, color=INK, bold=False, anchor='start'):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
                          f'style="fill:{color}"' + (' font-weight="bold"' if bold else '') + f'>{escape(str(value))}</text>')

    def box(self, x, y, w, h, fill='#f4f8fb', stroke='#aabcca', dash=False):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="2"' + (' stroke-dasharray="9 6"' if dash else '') + '/>')

    def line(self, points, color=SIG, width=4):
        self.parts.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" '
                          f'stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')

    def dot(self, x, y, color=SIG, r=6):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')

    def net(self, x, y, label, color):
        self.line([(x, y), (x, y+24)], color)
        self.text(x, y-10, label, 21, color, True, 'middle')

    def resistor(self, x, y1, y2, label, color=SIG):
        mid = (y1+y2)/2
        self.line([(x, y1), (x, mid-20)], color, 3)
        self.box(x-9, mid-20, 18, 40, '#fff4db', color)
        self.line([(x, mid+20), (x, y2)], color, 3)
        self.dot(x, y1, color, 5)
        self.dot(x, y2, color, 5)
        self.text(x+25, mid+7, label, 21, color, True)

    def save(self, name):
        path = OUT / name
        path.write_text('\n'.join(self.parts + ['</svg>']), encoding='utf-8')
        print(path)


def overview():
    s = Sheet('V.A.M.P. | Complete prototype wiring',
              'Sheet 1: power, motor drivers and servo. Sheet 2: breadboard, multiplexer and sensors. All GPIO = BCM.', 1)
    s.box(60, 160, 2280, 340, '#fffaf7', '#d9bfa9')
    s.text(85, 198, 'POWER - direct wires / distribution connectors; keep load current off the breadboard', 25, bold=True)
    s.box(90, 240, 300, 185, '#fdf0ef')
    s.text(110, 283, '3S LiPo', 30, bold=True)
    s.text(110, 325, '11.1 V nominal', 23)
    s.text(110, 364, '12.6 V charged', 23)
    s.text(110, 402, 'Regulator inputs only', 21, P5, True)
    s.box(540, 225, 440, 100)
    s.text(560, 261, 'Existing BEC -> regulated 5 V', 25, bold=True)
    s.text(560, 300, 'Input must accept a full 3S battery', 21)
    s.box(540, 365, 440, 90)
    s.text(560, 402, 'Separate motor buck -> 6 V*', 25, bold=True)
    s.text(560, 441, '*Use the actual motor rated voltage', 21)
    s.line([(390, 270), (465, 270), (465, 250), (540, 250)], P5)
    s.line([(465, 270), (465, 390), (540, 390)], P5)
    s.dot(465, 270, P5)
    s.line([(390, 410), (490, 410), (490, 306), (540, 306)], GND)
    s.line([(490, 410), (490, 450), (540, 450)], GND)
    s.dot(490, 410, GND)
    s.line([(980, 250), (1120, 250)], P5, 5)
    s.text(1150, 258, '+5V: Pi 5V input, servo V+, MQ-2 VCC', 27, P5, True)
    s.text(1150, 294, 'Pi power and servo power each get their own direct branch.', 22)
    s.line([(980, 390), (1120, 390)], VM, 5)
    s.text(1150, 398, 'VM: DRV1 + DRV2 VM; optional DRV3 VM', 27, VM, True)
    s.text(1150, 434, 'If no motor buck: 5 V motor option only if supply current is adequate.', 22)
    s.text(85, 490, 'GND: join regulator outputs, Pi, drivers, servo and sensors. Pi 3V3 supplies the sensor rail on sheet 2.', 23, GND, True)

    s.box(60, 555, 395, 820, '#edf5fc')
    s.text(85, 597, 'Raspberry Pi', 31, bold=True)
    s.text(85, 633, '3.3 V logic / BCM GPIO', 23)
    s.net(130, 531, '+5V input', P5)
    s.net(320, 531, 'GND', GND)
    for name, top, keys, roles in [
        ('DRV1', 580, ['left1', 'left2'], ['Rear LEFT / left1', 'Vertical FRONT / left2']),
        ('DRV2', 945, ['right1', 'right2'], ['Rear RIGHT / right1', 'Vertical REAR / right2'])
    ]:
        s.box(855, top, 650, 300, '#edf8f1', '#97b8a1')
        s.text(1180, top+42, f'{name} - DRV8833 breakout', 27, bold=True, anchor='middle')
        for x, label, color in [(940, 'VM', VM), (1180, 'GND', GND), (1415, 'STBY*', P3)]:
            s.net(x, top-25, label, color)
        gpios = CFG['motors'][keys[0]] + CFG['motors'][keys[1]]
        ys = [top+100, top+150, top+220, top+270]
        for y, gpio, pin, out in zip(ys, gpios, ['AIN1', 'AIN2', 'BIN1', 'BIN2'], ['AO1', 'AO2', 'BO1', 'BO2']):
            s.text(85, y+8, f'GPIO{gpio}', 26, SIG, True)
            s.dot(455, y, SIG)
            s.line([(455, y), (855, y)], SIG)
            s.text(875, y+8, pin, 24, SIG, True)
            s.text(1480, y+8, out, 24, MOT, True, 'end')
            s.line([(1505, y), (1850, y)], MOT)
        for i, role in enumerate(roles):
            y1, y2 = ys[i*2:i*2+2]
            cy = (y1+y2)/2
            s.box(1850, y1-18, 450, y2-y1+36, '#f4faf6', '#97b8a1')
            s.text(1870, cy+8, role, 25, MOT, True)
    servo_gpio = CFG['servos']['gimbal']
    s.text(85, 1308, f'GPIO{servo_gpio}', 26, SIG, True)
    s.line([(455, 1300), (1770, 1300)], SIG)
    s.box(1770, 1255, 530, 120, '#f6f1fb', '#b9a1cb')
    s.text(1795, 1295, 'Gimbal servo SIGNAL', 27, SIG, True)
    s.text(1795, 1337, 'V+ = +5V    GND = common GND', 24)
    s.text(85, 1354, 'GPIO2 / 3 / 26 -> sheet 2', 22, bold=True)
    s.text(60, 1410, '*STBY: keep enabled. If not already pulled HIGH on the carrier, use 3V3 after checking its pull-up.', 23, P3, True)

    s.box(60, 1435, 2280, 160, '#f9fafc', '#b9c5cf', True)
    s.text(85, 1472, 'OPTIONAL CRAWLER / MANIPULATOR', 24, bold=True)
    a, b = CFG['motors']['left3'], CFG['motors']['right3']
    s.text(85, 1511, f'DRV3: GPIO{a[0]} -> AIN1, GPIO{a[1]} -> AIN2, AO1/AO2 -> left3; '
           f'GPIO{b[0]} -> BIN1, GPIO{b[1]} -> BIN2, BO1/BO2 -> right3.', 23)
    s.text(85, 1547, 'DRV3 uses the same VM / GND / STBY arrangement. Submarine mode leaves left3 and right3 off.', 23)
    s.text(85, 1581, f'Arm signal GPIO{CFG["servos"]["arm"]}; gripper signal GPIO{CFG["servos"]["gripper"]}. '
           'Each servo: +5V and GND direct; only one PWM active at a time.', 23)
    s.text(60, 1631, 'Camera -> CSI ribbon port. PC -> Ethernet. No motor lead goes to GND. NC pins stay unused. Use one Pi power source.', 23, MUTED)
    s.save('breadboard-power-motors.svg')


def breadboard():
    s = Sheet('V.A.M.P. | Breadboard signal patch panel',
              'Use labelled jumper wires to each breakout. Hole names such as A3 are breadboard coordinates, never Pi header positions.', 2)
    s.text(60, 185, 'Use rows 1-30 of a standard board. A-E are joined across each row; F-J are joined separately.', 25, bold=True)
    s.text(60, 220, 'The centre trench isolates the two halves. Rail strips run vertically; bridge any midpoint split in each strip.', 23, MUTED)
    s.box(60, 250, 950, 900, '#f8f7f2', '#c2bfb0')
    xs = dict(zip('ABCDEFGHIJ', [330, 365, 400, 435, 470, 570, 605, 640, 675, 710]))
    yy = lambda row: 330 + (row-1)*24
    # Two independent rail pairs: 3V3/GND on the left, 5V/GND on the right.
    for x, label, color in [(95, '3V3', P3), (155, 'GND', GND), (875, '+5V', P5), (950, 'GND', GND)]:
        s.text(x, 292, label, 20, color, True, 'middle')
        s.line([(x, 317), (x, 1110)], color, 3)
        for row in range(1, 31):
            s.parts.append(f'<circle cx="{x}" cy="{yy(row)}" r="4" fill="white" stroke="{color}" stroke-width="1.5"/>')
    for letter, x in xs.items():
        s.text(x, 312, letter, 19, MUTED, True, 'middle')
    s.box(503, 322, 32, 716, '#e5e1d9', '#e5e1d9')
    nets = {3: ('GPIO2 / SDA', SDA), 5: ('GPIO3 / SCL', SCL), 7: ('IMU SDA', SDA), 9: ('IMU SCL', SCL),
            11: ('AHT SDA', SDA), 13: ('AHT SCL', SCL), 15: ('TCA RESET', SIG), 18: ('3V3 tap', P3)}
    for row, (label, color) in nets.items():
        s.line([(xs['A'], yy(row)), (xs['E'], yy(row))], color, 8)
        s.text(288, yy(row)-10 if row == 18 else yy(row)+6, label, 18, color, True, 'end')
    for row, label, color in [(20, 'MQ D0', SIG), (24, 'GPIO26', SIG), (28, 'GND', GND)]:
        s.line([(xs['F'], yy(row)), (xs['J'], yy(row))], color, 8)
        s.text(755, yy(row)-10 if row == 28 else yy(row)+7, label, 20, color, True)
    for row in range(1, 31):
        s.text(311, yy(row)+6, row, 15, MUTED, anchor='end')
        for x in xs.values():
            s.parts.append(f'<circle cx="{x}" cy="{yy(row)}" r="4.5" fill="#fff" stroke="#a8a79e" stroke-width="1.5"/>')
    s.line([(95, yy(18)), (xs['E'], yy(18))], P3, 3)
    s.dot(95, yy(18), P3)
    s.resistor(xs['A'], yy(15), yy(18), 'R3 10k', P3)
    s.resistor(xs['J'], yy(20), yy(24), 'R1 10k', SIG)
    s.resistor(xs['H'], yy(24), yy(28), 'R2 15k', SIG)
    s.line([(xs['J'], yy(28)), (950, yy(28))], GND, 3)
    s.dot(950, yy(28), GND)
    # The two ground rail strips must have an explicit bridge, unlike positive rails.
    s.line([(155, yy(30)), (155, 1080), (950, 1080), (950, yy(30))], GND, 3)
    s.dot(155, yy(30), GND)
    s.dot(950, yy(30), GND)
    s.text(540, 1130, 'Join GND rails only - keep 3V3 and +5V separate', 21, GND, True, 'middle')

    def card(y, h, title, lines, tint='#f4f8fb', stroke='#aabcca'):
        s.box(1070, y, 1270, h, tint, stroke)
        s.text(1095, y+36, title, 26, bold=True)
        for i, (label, color) in enumerate(lines):
            s.text(1095, y+74+i*33, label, 23, color)

    card(250, 230, 'RAIL FEEDS + Pi JUMPERS', [
        ('Pi 3V3 -> left 3V3 rail; Pi GND -> left GND rail.', P3),
        ('BEC +5V -> right +5V rail; BEC GND -> right GND rail.', P5),
        ('Pi GPIO2 -> A3; GPIO3 -> A5; GPIO26 -> F24 (divider node).', SIG),
        ('Only sensor supply current uses these rails; Pi/servo/motors use sheet 1.', INK),
        ('Each separate hole in a rail takes one wire. Check rail continuity first.', MUTED),
    ])
    card(500, 280, 'TCA9548A - upstream + downstream routing (address 0x70)', [
        ('VCC -> 3V3 rail; GND + A0 + A1 + A2 -> GND rail.', INK),
        ('SDA -> E3; SCL -> E5; RESET / RST -> E15.', SIG),
        ('SD0 -> A7; SC0 -> A9. SD1 -> A11; SC1 -> A13.', SDA),
        ('R3: A15 to A18. Jumper E18 to 3V3 rail. RST is held HIGH.', P3),
        ('R3 can be omitted if the carrier already has its own 3V3 reset pull-up.', MUTED),
        ('Channels 2-7 stay unused. GPIO2/3 drive the upstream bus only.', MUTED),
    ])
    card(800, 185, 'HW-123 / MPU-6050 - channel 0 (0x68)', [
        ('VCC -> 3V3; GND + AD0 -> GND.', INK),
        ('SDA -> E7; SCL -> E9. INT / XDA / XCL unused.', SDA),
        ('Keep the IMU still for its startup gyro calibration.', MUTED),
    ])
    card(1005, 155, 'AHT10 - channel 1 (0x38)', [
        ('VCC -> 3V3; GND -> GND; SDA -> E11; SCL -> E13.', SDA),
        ('Place away from the MQ-2 heater; measure ambient air.', MUTED),
    ])
    card(1180, 220, 'MQ-2 breakout - digital output only', [
        ('VCC -> +5V rail; GND -> GND rail; D0 / DO -> F20.', P5),
        ('R1 10k: J20 to J24. R2 15k: H24 to H28.', SIG),
        ('J28 -> GND rail; F24 -> Pi GPIO26. A0 / AO unused.', SIG),
        ('Check the node voltage with GPIO26 disconnected: valid HIGH, <= 3.3 V.', INK),
    ], '#fff9ed', '#d4b77b')

    s.text(60, 1205, 'MQ-2 divider circuit', 27, bold=True)
    s.text(60, 1244, 'D0 -> 10k -> NODE -> GPIO26', 25, SIG, True)
    s.text(60, 1283, 'NODE -> 15k -> GND', 25, SIG, True)
    s.text(60, 1325, 'Ideal 5 V HIGH becomes 3.0 V at NODE.', 23)
    s.text(60, 1363, 'Carrier pull-ups can reduce HIGH further; measure it.', 22, MUTED)
    s.text(60, 1428, 'READ THIS BEFORE POWERING', 26, bold=True)
    notes = [
        'A3 / E3 etc. refer ONLY to this breadboard. Breakouts stay beside it; wire by their printed pin labels.',
        'GPIO3 is the clock, NOT the 3V3 supply. Never connect raw MQ-2 D0, +5V or VM to a Pi signal GPIO.',
        'If a downstream I2C branch lacks pull-ups: add 4.7k from its SDA to 3V3 and from its SCL to 3V3.',
        'This is a proposed layout for your default map. Follow config.local.json if you already changed GPIO assignments.',
        '3V3 / +5V / VM are different positive nets. All GND nets share one reference. Never feed raw 3S to DRV8833 VM.',
    ]
    for i, note in enumerate(notes):
        s.text(60, 1470+i*34, note, 23, MUTED)
    s.save('breadboard-sensors.svg')


def pdf():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A3, landscape
    output = ROOT / 'output/pdf/vamp-breadboard-wiring.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    size = landscape(A3)
    c = canvas.Canvas(str(output), pagesize=size)
    c.setTitle('V.A.M.P. - Breadboard prototype wiring')
    c.setAuthor('V.A.M.P.')
    for name in ['breadboard-power-motors', 'breadboard-sensors']:
        # PNGs are rendered at 3600px wide; SVG originals remain editable.
        c.drawImage(str(OUT / f'{name}.png'), 0, 0, width=size[0], height=size[1])
        c.showPage()
    c.save()
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', action='store_true', help='Assemble existing rendered PNGs into a PDF')
    args = parser.parse_args()
    if args.pdf:
        pdf()
    else:
        overview()
        breadboard()
