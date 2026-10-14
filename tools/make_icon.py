"""Generate the geometric V.A.M.P. app mark from native drawing primitives."""
from pathlib import Path
from PIL import Image, ImageDraw

folder = Path(__file__).resolve().parents[1] / 'pc/assets'
folder.mkdir(parents=True, exist_ok=True)
image = Image.new('RGBA', (256, 256), '#090f1b')
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((12, 12, 244, 244), radius=48, fill='#111c2c', outline='#283b52', width=4)
draw.polygon([(42, 63), (91, 63), (128, 146), (165, 63), (214, 63), (128, 217)], fill='#46e2ba')
draw.line([(67, 224), (189, 224)], fill='#58b9ff', width=5)
image.save(folder / 'vamp.ico', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
image.save(folder / 'vamp.png')
