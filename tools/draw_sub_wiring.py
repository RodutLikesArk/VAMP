"""Generate a wiring diagram matching the default submarine software profile."""
from html import escape
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs'
OUT.mkdir(exist_ok=True)
cfg = json.loads((ROOT / 'robot/config.json').read_text())
parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1850" viewBox="0 0 2000 1850">',
         '<rect width="2000" height="1850" fill="#fff"/>',
         '<style>text {font-family:Arial,sans-serif;fill:#172635} .muted {fill:#50657a}</style>']
RED, GND, SIG, MOTOR = '#cb3148', '#334155', '#1679b6', '#23836b'


def text(x, y, value, size=22, color=None, bold=False, anchor='start'):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}"' +
                 (f' style="fill:{color}"' if color else '') +
                 (' font-weight="bold"' if bold else '') + f'>{escape(value)}</text>')


def box(x, y, w, h, fill='#f6f9fc', stroke='#a5b6c6', dash=None, radius=10):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"' +
                 (f' stroke-dasharray="{dash}"' if dash else '') + '/>')


def line(points, color, width=3):
    parts.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}"/>')


def circle(x, y, r=5, color=GND, fill='white'):
    parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{color}" stroke-width="2"/>')


text(70, 70, 'V.A.M.P.  |  Submarine + servo wiring', 38, bold=True)
text(70, 110, 'Four N20 motors • Two DRV8833 boards • One camera/gimbal servo • BCM GPIO numbering', 23)
box(70, 145, 300, 130)
text(95, 185, '3S LiPo battery', 26, bold=True)
text(95, 219, '11.1 V nominal', 22)
text(95, 250, '12.6 V fully charged', 22)
box(500, 145, 320, 130)
text(525, 185, 'Existing BEC', 26, bold=True)
text(525, 220, '3S input → regulated 5 V', 22)
text(525, 251, 'Listed output rating: 3 A', 22)
line([(370,200),(500,200)], RED, 4)
line([(370,250),(500,250)], GND, 4)
text(385, 188, '+', 23, RED)
text(385, 241, '−', 23, GND)
line([(820,200),(1920,200)], RED, 4)
text(865, 180, '+5V net: Pi 5V input + servo V+ + DRV1/DRV2 VM (5 V option)', 23, RED, True)
line([(820,250),(1920,250)], GND, 4)
text(865, 285, 'Common GND: battery − / BEC − / Pi / servo / both drivers', 22, GND)
text(70, 325, 'Matching net labels are connected. GPIO numbers are BCM; +5V, 3V3 and GND denote power rails, not GPIO numbers.', 21)

box(65, 355, 1225, 800, fill='#fbfdff', stroke='#8fa5b7', dash='10 7')
text(85, 388, 'MAIN CHASSIS  •  Pi + drivers remain inside', 22, bold=True)
box(1320, 355, 615, 800, fill='#fbfffd', stroke='#8fb7a9', dash='10 7')
text(1340, 388, 'DETACHABLE SUBMARINE MODULE', 22, bold=True)

box(100, 445, 420, 700, fill='#eef6fc')
text(125, 480, 'Raspberry Pi 3', 27, bold=True)
text(125, 518, 'BCM GPIO • 3.3 V logic', 21)
text(125, 815, 'Ethernet tether to operator PC', 21, bold=True)
text(125, 849, 'Built-in port or USB Ethernet adapter', 19, '#50657a')
# Power pins are named nets, separate from the signal wiring.
for x, label, port, col in [(175,'+5V','power in',RED),(305,'GND','ground',GND),(435,'3V3','3V3 rail',SIG)]:
    line([(x,415),(x,445)],col)
    text(x,408,label,21,col,True,'middle')
    text(x,551,port,19,col,False,'middle')

servo_gpio = cfg['servos']['gimbal']
text(125, 775, f'GPIO {servo_gpio} → SERVO_PWM', 22, SIG, True)
line([(520,768),(700,768)],SIG)
circle(520,768,4,SIG)
text(600,758,'SERVO_PWM',18,SIG)
drivers = [
    ('DRV1', 460, [580,620,680,720], ['left1','left2'], 'LEFT SIDE', ['Rear left','Vertical front']),
    ('DRV2', 850, [970,1010,1070,1110], ['right1','right2'], 'RIGHT SIDE', ['Rear right','Vertical rear'])
]
for name, top, ys, channels, side, roles in drivers:
    box(820,top,360,300,fill='#f0faf6',stroke='#90b9aa')
    text(1000,top+38,f'{name} · DRV8833',24,bold=True,anchor='middle')
    # Named supply stubs avoid long, crossing power lines over the signal paths.
    for x, net, pin, col in [(875,'+5V','VM',RED),(1000,'GND','GND',GND),(1125,'3V3*','STBY',SIG)]:
        line([(x,top-25),(x,top)],col)
        text(x,top-34,net,21,col,True,'middle')
        text(x,top+71,pin,18,col,False,'middle')
    gpios = cfg['motors'][channels[0]] + cfg['motors'][channels[1]]
    for i,(y,gpio,input_name,output_name) in enumerate(zip(ys,gpios,['AIN1','AIN2','BIN1','BIN2'],['AO1','AO2','BO1','BO2'])):
        text(125,y+7,f'GPIO {gpio}',22,SIG)
        line([(520,y),(820,y)],SIG)
        circle(520,y,4,SIG)
        text(840,y+7,input_name,21,SIG)
        text(1160,y+7,output_name,21,MOTOR,anchor='end')
        # Each output remains independent; no motor terminal is tied to GND.
        line([(1180,y),(1640,y)],MOTOR)
        circle(1400,y,6,MOTOR)
        text(1420,y-9,str(i+1),18,MOTOR)
    text(600,ys[0]-24,side,20,SIG,True)
    # Each side uses four proposed connector pins for two motor pairs.
    parts.append(f'<rect x="1378" y="{ys[0]-18}" width="34" height="{ys[-1]-ys[0]+36}" rx="8" fill="none" stroke="#23836b" stroke-width="2"/>')
    text(1475,ys[0]-34,'6-pin plug',20,MOTOR,True)
    text(1475,ys[0]-8,'5, 6: unused',18,MOTOR)
    for index, (channel, role) in enumerate(zip(channels,roles)):
        y1,y2=ys[index*2:index*2+2]
        cy=(y1+y2)/2
        # Two leads terminate on opposite sides of a conventional motor symbol.
        line([(1640,y1),(1670,y1),(1670,cy-30)],MOTOR)
        line([(1640,y2),(1670,y2),(1670,cy+30)],MOTOR)
        circle(1670,cy,30,MOTOR)
        text(1670,cy+8,'M',25,MOTOR,True,'middle')
        text(1720,cy-2,role,23,bold=True)
        text(1720,cy+28,f'N20 · {channel}',20)

box(65,1185,1870,245,fill='#fbf8ff',stroke='#afa0c4',dash='10 7')
text(85,1220,'CAMERA / GIMBAL SERVO  •  Separate three-wire connection at the main chassis/front cap',23,bold=True)
text(120,1272,f'Signal source: Pi GPIO {servo_gpio} (gimbal)',24,SIG,True)
text(120,1310,f'Optional manipulator: arm GPIO {cfg["servos"]["arm"]}, gripper GPIO {cfg["servos"]["gripper"]}',21)
text(120,1400,'Matching SERVO_PWM labels join this line to the Pi output above.',20)
box(1000,1240,500,165,fill='#f2ebfc',stroke='#afa0c4')
text(1250,1272,'MG90S camera/gimbal servo',25,bold=True,anchor='middle')
for y,net,pin,col,start in [(1300,'+5V','V+',RED,740),(1335,'GND','GND',GND,740),(1370,'SERVO_PWM','SIGNAL',SIG,540)]:
    line([(start,y),(1000,y)],col)
    text(start,y-10,net,21,col,True)
    text(1020,y+7,pin,21,col)
text(1550,1280,'5 V power from the BEC',22,bold=True)
text(1550,1315,'Common ground with the Pi',21)
text(1550,1350,'No DRV8833 or TCA connection',20)
text(1550,1385,'App controls: J / L or + / −',21)

text(70, 1485, 'BUILD NOTES', 24, bold=True)
notes = [
    'Use complete DRV8833 breakout boards with their onboard capacitors; this is not a bare-chip schematic.',
    '* STBY is the carrier enable label (nSLEEP on the DRV8833 chip); keep it HIGH. Never join 3V3 and +5V rails.',
    'The drawing shows the 5 V motor option. With a separate 6 V buck, move only driver VM feeds to that motor rail.',
    'Keep the Pi and servo on regulated 5 V, not the 6 V motor rail or raw 3S. Budget for servo startup/stall current.',
    'Do not power the Pi through its 5 V header and a separate USB supply at the same time.',
    'Connector numbering is a proposed assignment, not the physical pinout of your plugs. Wire both halves identically.',
    'The environment module already uses its six connector contacts; use a separate servo plug for the gimbal.',
    'I2C sensors and camera ribbon wiring are in the other guides. Servo PWM releases after 0.3 s by default.'
]
for i,note in enumerate(notes):
    text(70,1525+i*32,'• '+note,21)
text(70,1820,'References: TI DRV8833 datasheet; TowerPro MG90S; Raspberry Pi GPIO documentation; robot/config.json.',18,'#50657a')
parts.append('</svg>')
(OUT/'submarine-minimum-wiring.svg').write_text('\n'.join(parts),encoding='utf-8')
print(OUT/'submarine-minimum-wiring.svg')
