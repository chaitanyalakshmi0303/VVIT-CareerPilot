import os
from PIL import Image, ImageDraw, ImageFont

# Canvas setup (1000x1000 square for LinkedIn & Google OAuth)
size = (1000, 1000)
img = Image.new("RGBA", size, (255, 255, 255, 255))
draw = ImageDraw.Draw(img)

# Colors matching the VVIT identity
CORAL_RED = (232, 110, 88, 255)       # Main brand background
WHITE = (255, 255, 255, 255)
DARK_TEXT = (25, 33, 44, 255)
SUB_TEXT = (71, 85, 105, 255)
NAVY_DEEP = (14, 43, 92, 255)
CYAN_ACCENT = (56, 189, 248, 255)

# 1. Top Globe Emblem
globe_center = (500, 160)
globe_radius = 85

# Globe Base (Deep Blue to Cyan gradient effect)
for r in range(globe_radius, 0, -1):
    factor = r / globe_radius
    r_val = int(NAVY_DEEP[0] * (1 - factor) + CYAN_ACCENT[0] * factor)
    g_val = int(NAVY_DEEP[1] * (1 - factor) + CYAN_ACCENT[1] * factor)
    b_val = int(NAVY_DEEP[2] * (1 - factor) + CYAN_ACCENT[2] * factor)
    draw.ellipse(
        [globe_center[0] - r, globe_center[1] - r, globe_center[0] + r, globe_center[1] + r],
        fill=(r_val, g_val, b_val, 255)
    )

# Stylized Globe Continents / Landmass outlines
draw.pieslice([globe_center[0] - 70, globe_center[1] - 70, globe_center[0] + 50, globe_center[1] + 50], 190, 310, fill=(125, 211, 252, 180))
draw.arc([globe_center[0] - 40, globe_center[1] - 85, globe_center[0] + 40, globe_center[1] + 85], 0, 360, fill=(255, 255, 255, 140), width=3)
draw.line([globe_center[0] - 85, globe_center[1], globe_center[0] + 85, globe_center[1]], fill=(255, 255, 255, 140), width=3)

# 2. Main VVIT Coral Block
draw.rounded_rectangle([130, 260, 870, 520], radius=16, fill=CORAL_RED)

# 3. Middle White Separator
draw.rectangle([130, 525, 870, 535], fill=WHITE)

# 4. UNIVERSITY Lower Coral Block
draw.rounded_rectangle([130, 540, 870, 680], radius=16, fill=CORAL_RED)

# Fonts: Attempt clean system serif/sans or fallback to default
try:
    font_vvit = ImageFont.truetype("timesbd.ttf", 190)
    font_univ = ImageFont.truetype("timesbd.ttf", 66)
    font_sub1 = ImageFont.truetype("arialbd.ttf", 29)
    font_sub2 = ImageFont.truetype("arialbd.ttf", 20)
    font_badge = ImageFont.truetype("segoeuib.ttf", 28)
except Exception:
    try:
        font_vvit = ImageFont.truetype("DejaVuSerif-Bold.ttf", 190)
        font_univ = ImageFont.truetype("DejaVuSerif-Bold.ttf", 66)
        font_sub1 = ImageFont.truetype("DejaVuSans-Bold.ttf", 29)
        font_sub2 = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        font_badge = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
    except Exception:
        font_vvit = font_univ = font_sub1 = font_sub2 = font_badge = ImageFont.load_default()

# Draw VVIT Text
draw.text((500, 390), "VVIT", fill=WHITE, font=font_vvit, anchor="mm")

# Draw UNIVERSITY Text
draw.text((500, 610), "UNIVERSITY", fill=WHITE, font=font_univ, anchor="mm")

# 5. Full University Name
draw.text((500, 735), "VASIREDDY VENKATADRI", fill=DARK_TEXT, font=font_sub1, anchor="mm")
draw.text((500, 780), "INTERNATIONAL TECHNOLOGICAL UNIVERSITY", fill=SUB_TEXT, font=font_sub2, anchor="mm")

# 6. Bottom Modern "PLACEMENTS AGENT" Pill Badge
draw.rounded_rectangle([250, 840, 750, 920], radius=40, fill=(37, 99, 235, 255))
draw.text((500, 880), "🚀 PLACEMENTS AGENT", fill=WHITE, font=font_badge, anchor="mm")

# Save file directly
output_path = os.path.join(os.path.dirname(__file__), "vvit_logo.png")
img.save(output_path, "PNG")
print(f"✅ Successfully created: {output_path}")