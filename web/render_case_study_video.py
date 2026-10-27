from __future__ import annotations

import math
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1280
HEIGHT = 720
FPS = 24
SCENE_SECONDS = 5
SCENE_COUNT = 7
TOTAL_FRAMES = FPS * SCENE_SECONDS * SCENE_COUNT

BG = (14, 20, 20)
PANEL = (22, 31, 30)
PANEL_LIGHT = (28, 40, 38)
GRID = (32, 46, 42)
INK = (235, 241, 235)
MUTED = (150, 164, 157)
FAINT = (92, 109, 101)
MINT = (167, 230, 189)
MINT_DARK = (91, 166, 123)
AMBER = (240, 173, 105)
RED = (226, 126, 105)

FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts/truetype/lato"),
]

def find_font(bold: bool = False) -> str | None:
    names = (
        ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Lato-Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Lato-Regular.ttf"]
    )
    for directory in FONT_DIRS:
        for name in names:
            path = directory / name
            if path.exists():
                return str(path)
    return None

FONT_REGULAR = find_font(False)
FONT_BOLD = find_font(True)

def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    chosen = FONT_BOLD if bold else FONT_REGULAR
    if size <= 12:
        size = round(size * 1.3)
    elif size <= 18:
        size = round(size * 1.18)
    else:
        size = round(size * 1.05)
    if chosen:
        return ImageFont.truetype(chosen, size)
    return ImageFont.load_default(size=size)

def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)

def blend(color_a: tuple[int, int, int], color_b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    return tuple(round(a + (b - a) * amount) for a, b in zip(color_a, color_b))

def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int], outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def write(draw: ImageDraw.ImageDraw, xy: tuple[int, int], content: str, size: int = 18, color=INK, bold: bool = False, anchor: str | None = None) -> None:
    draw.text(xy, content, font=font(size, bold), fill=color, anchor=anchor)

def centered(draw: ImageDraw.ImageDraw, x: int, y: int, content: str, size: int = 18, color=INK, bold: bool = False) -> None:
    write(draw, (x, y), content, size, color, bold, "mm")

def centered_ribbon(draw: ImageDraw.ImageDraw, x: int, y: int, content: str, size: int, color, bold: bool = False) -> None:
    selected = FONT_BOLD if bold else FONT_REGULAR
    ribbon_font = ImageFont.truetype(selected, size) if selected else ImageFont.load_default(size=size)
    draw.text((x, y), content, font=ribbon_font, fill=color, anchor="mm")

def wrap(draw: ImageDraw.ImageDraw, text: str, width: int, size: int = 18, bold: bool = False) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    selected_font = font(size, bold)
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=selected_font)[2] <= width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def paragraph(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, width: int, size: int = 17, color=MUTED, line_height: int | None = None, bold: bool = False) -> int:
    selected_font = font(size, bold)
    text_box = draw.textbbox((0, 0), "Ag", font=selected_font)
    line_height = max(line_height or 0, text_box[3] - text_box[1] + 8)
    lines = wrap(draw, text, width, size, bold)
    for index, line in enumerate(lines):
        write(draw, (xy[0], xy[1] + index * line_height), line, size, color, bold)
    return xy[1] + len(lines) * line_height

def base_frame(scene_index: int, local_progress: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 82), fill=(17, 25, 24))
    draw.line((0, 81, WIDTH, 81), fill=(47, 63, 56), width=1)
    write(draw, (52, 23), "GATE LOGIC", 14, MINT, True)
    write(draw, (52, 46), "AVIATION AI / RESEARCH PROTOTYPE", 8, MUTED, True)
    stages = ["PROBLEM", "CONSTRAINTS", "AI METHOD", "OUTCOMES", "FUTURE WORK"]
    stage_xs = [610, 742, 905, 1040, 1167]
    active_stage = [0, 1, 1, 3, 3, 4, 4][scene_index]
    for index, (stage, x) in enumerate(zip(stages, stage_xs)):
        active = active_stage == index
        centered_ribbon(draw, x, 43, stage, 9, MINT if active else FAINT, active)
    progress = (scene_index + local_progress) / SCENE_COUNT
    draw.rectangle((0, 81, int(WIDTH * progress), 84), fill=AMBER)
    return image, draw

def draw_plane(draw: ImageDraw.ImageDraw, x: float, y: float, scale: float = 1.0, color=AMBER, angle: float = 0.0) -> None:
    # Top-down jet silhouette: pointed nose, swept wings, tailplane and engines.
    points = [
        (41, 0), (31, -3), (8, -4), (1, -28), (-4, -31), (-2, -5),
        (-25, -14), (-36, -12), (-19, 0), (-36, 12), (-25, 14),
        (-2, 5), (-4, 31), (1, 28), (8, 4), (31, 3),
    ]
    transformed = []
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    for px, py in points:
        px *= scale
        py *= scale
        transformed.append((x + px * cos_a - py * sin_a, y + px * sin_a + py * cos_a))
    draw.polygon(transformed, fill=color)
    def transform(px: float, py: float) -> tuple[float, float]:
        px *= scale
        py *= scale
        return x + px * cos_a - py * sin_a, y + px * sin_a + py * cos_a
    draw.line([transform(-28, 0), transform(31, 0)], fill=(229, 237, 224), width=max(1, round(2 * scale)))
    for engine_y in (-12, 12):
        engine_center = transform(3, engine_y)
        engine_radius = max(1.5, 3.2 * scale)
        draw.ellipse(
            (engine_center[0] - engine_radius, engine_center[1] - engine_radius,
             engine_center[0] + engine_radius, engine_center[1] + engine_radius),
            fill=(28, 39, 35),
        )
    cockpit = transform(34, 0)
    cockpit_radius = max(1.5, 2.4 * scale)
    draw.ellipse(
        (cockpit[0] - cockpit_radius, cockpit[1] - cockpit_radius,
         cockpit[0] + cockpit_radius, cockpit[1] + cockpit_radius),
        fill=(225, 238, 224),
    )

def draw_docking_scene(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0, progress: float = 0.0) -> None:
    def point(px: float, py: float) -> tuple[float, float]:
        return x + px * scale, y + py * scale

    def box(left: float, top: float, right: float, bottom: float) -> tuple[float, float, float, float]:
        return (*point(left, top), *point(right, bottom))

    # Original side-perspective terminal illustration with three jet bridges.
    draw.polygon([point(8, 24), point(624, 24), point(610, 190), point(18, 190)], fill=(24, 42, 38), outline=(95, 125, 108))
    draw.polygon([point(0, 22), point(632, 22), point(620, 38), point(12, 38)], fill=(56, 83, 69))
    draw.rectangle(box(20, 142, 612, 190), fill=(18, 30, 28))
    draw.line([point(18, 141), point(612, 141)], fill=(111, 143, 122), width=max(1, round(scale * 2)))
    for column in range(13):
        window_x = 34 + column * 44
        draw.polygon(
            [point(window_x, 53), point(window_x + 34, 53), point(window_x + 30, 124), point(window_x - 2, 124)],
            fill=(43, 73, 66),
            outline=(85, 123, 108),
        )
        draw.line([point(window_x + 16, 55), point(window_x + 14, 122)], fill=(68, 101, 88), width=max(1, round(scale)))
    draw.line([point(22, 169), point(610, 169)], fill=(42, 59, 52), width=max(1, round(scale)))
    draw.polygon([point(0, 194), point(630, 194), point(604, 350), point(25, 350)], fill=(21, 31, 29), outline=(58, 76, 66))
    for index, (plane_x, gate_label) in enumerate(((110, "GATE 06"), (315, "GATE 13"), (520, "GATE 24"))):
        stand_y = 229 + index * 2
        draw.line([point(plane_x - 63, 209), point(plane_x + 78, 209)], fill=(83, 104, 87), width=max(1, round(scale)))
        draw.line([point(plane_x - 48, 204), point(plane_x - 48, 332)], fill=(52, 69, 59), width=max(1, round(scale)))
        write(draw, (round(x + (plane_x - 48) * scale), round(y + 196 * scale)), gate_label, max(7, round(8 * scale)), MUTED, True)
        draw.ellipse(box(plane_x - 70, 273, plane_x + 84, 294), fill=(12, 20, 19))

        plane_color = ((214, 225, 214), (177, 198, 185), (224, 225, 211))[index]
        plane_center = point(plane_x + 22, 262)
        draw_plane(draw, plane_center[0], plane_center[1], 1.35 * scale, plane_color, 0.0)

        # Telescoping aerobridge reaches the aircraft's nose from the terminal.
        bridge_top = point(plane_x + 18, 171)
        bridge_elbow = point(plane_x + 24, 204)
        bridge_end = point(plane_x + 77, 259)
        draw.line([bridge_top, bridge_elbow, bridge_end], fill=(149, 174, 151), width=max(3, round(scale * 9)))
        draw.line([point(plane_x + 14, 171), point(plane_x + 22, 204)], fill=(205, 220, 202), width=max(1, round(scale * 2)))
        draw.line([point(plane_x + 28, 207), point(plane_x + 80, 260)], fill=(205, 220, 202), width=max(1, round(scale * 2)))
        draw.ellipse(box(plane_x + 72, 254, plane_x + 82, 264), fill=AMBER if index == 0 else MINT)

    moving = point(584, 318 - math.sin(progress * math.pi) * 12)
    draw_plane(draw, moving[0], moving[1], 0.31 * scale, AMBER, -0.08)
    write(draw, point(23, 326), "APRON  /  AIRCRAFT AT CONTACT STANDS", max(7, round(8 * scale)), FAINT, True)

def draw_passenger_icon(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0, color=MINT) -> None:
    for offset in range(3):
        cx = x + offset * 22 * scale
        radius = 4 * scale
        draw.ellipse((cx - radius, y, cx + radius, y + radius * 2), fill=color)
        draw.rounded_rectangle((cx - 5 * scale, y + 10 * scale, cx + 5 * scale, y + 25 * scale), radius=max(1, round(3 * scale)), fill=color)
        draw.line((cx, y + 23 * scale, cx - 5 * scale, y + 31 * scale), fill=color, width=max(1, round(2 * scale)))
        draw.line((cx, y + 23 * scale, cx + 5 * scale, y + 31 * scale), fill=color, width=max(1, round(2 * scale)))

def draw_engineering_icon(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0, color=AMBER) -> None:
    draw.ellipse((x, y, x + 36 * scale, y + 36 * scale), outline=color, width=max(1, round(2 * scale)))
    draw.ellipse((x + 13 * scale, y + 13 * scale, x + 23 * scale, y + 23 * scale), outline=color, width=max(1, round(2 * scale)))
    for angle in range(0, 360, 45):
        radians = math.radians(angle)
        x1 = x + (18 + 7 * math.cos(radians)) * scale
        y1 = y + (18 + 7 * math.sin(radians)) * scale
        x2 = x + (18 + 17 * math.cos(radians)) * scale
        y2 = y + (18 + 17 * math.sin(radians)) * scale
        draw.line((x1, y1, x2, y2), fill=color, width=max(1, round(2 * scale)))

def draw_airfield(draw: ImageDraw.ImageDraw, progress: float) -> None:
    ground = [(650, 596), (1195, 596), (1040, 244), (790, 244)]
    draw.polygon(ground, fill=(19, 34, 31), outline=(64, 91, 78))
    for index in range(9):
        y = 282 + index * 34
        left = 770 + index * 17
        right = 1062 - index * 5
        draw.line((left, y, right, y), fill=(43, 62, 54), width=1)
    draw.line((936, 252, 936, 586), fill=(96, 114, 94), width=2)
    draw.line((929, 416, 943, 416), fill=AMBER, width=3)
    for index in range(10):
        x = 806 + index * 24
        y = 284 + index * 5
        rounded(draw, (x, y, x + 17, y + 9), 2, MINT_DARK, outline=MINT, width=1)
    for index in range(30):
        row, col = divmod(index, 10)
        x = 790 + col * 27 + row * 11
        y = 418 + row * 35
        rounded(draw, (x, y, x + 17, y + 9), 2, (70, 91, 81), outline=(113, 134, 119), width=1)
    moving_x = 760 + progress * 325
    moving_y = 500 - math.sin(progress * math.pi) * 146
    draw_plane(draw, moving_x, moving_y, 0.68, AMBER, -0.15)
    write(draw, (780, 225), "10 CODE F GATES", 10, MINT, True)
    write(draw, (780, 388), "30 STANDARD GATES", 10, MUTED, True)

def draw_gate_matrix(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    width = round(540 * scale)
    height = round(300 * scale)
    rounded(draw, (x, y, x + width, y + height), 8, PANEL, outline=(54, 72, 64), width=1)
    write(draw, (x + round(22 * scale), y + round(19 * scale)), "40-GATE CAPACITY NETWORK", round(11 * scale), MUTED, True)
    tile_width = 48 * scale
    tile_height = 30 * scale
    gap_x = 10 * scale
    gap_y = 11 * scale
    start_x = x + 24 * scale
    start_y = y + 57 * scale
    for gate_number in range(40):
        row, column = divmod(gate_number, 8)
        tile_x = start_x + column * (tile_width + gap_x)
        tile_y = start_y + row * (tile_height + gap_y)
        is_code_f = gate_number < 10
        rounded(
            draw,
            (round(tile_x), round(tile_y), round(tile_x + tile_width), round(tile_y + tile_height)),
            max(2, round(4 * scale)),
            (41, 79, 61) if is_code_f else (34, 48, 43),
            outline=MINT_DARK if is_code_f else (59, 76, 67),
            width=1,
        )
        centered(draw, round(tile_x + tile_width / 2), round(tile_y + tile_height / 2), f"{gate_number + 1:02d}", round(9 * scale), MINT if is_code_f else MUTED, True)
    legend_y = y + height - 23 * scale
    rounded(draw, (x + 25 * scale, legend_y, x + 39 * scale, legend_y + 10 * scale), 2, MINT_DARK)
    write(draw, (x + 46 * scale, legend_y - 3 * scale), "CODE F", round(8 * scale), MINT, True)
    rounded(draw, (x + 125 * scale, legend_y, x + 139 * scale, legend_y + 10 * scale), 2, (59, 76, 67))
    write(draw, (x + 146 * scale, legend_y - 3 * scale), "STANDARD", round(8 * scale), MUTED, True)

def slide_intro(draw: ImageDraw.ImageDraw, p: float) -> None:
    offset = int((1 - ease(min(p * 2.3, 1))) * 70)
    write(draw, (76 + offset, 171), "AVIATION OPERATIONS  /  PROOF OF CONCEPT", 10, MINT, True)
    write(draw, (72 + offset, 237), "A PROOF OF", 55, INK, True)
    write(draw, (72 + offset, 301), "CONCEPT.", 60, MINT, True)
    write(draw, (75 + offset, 374), "MODERN AI FOR", 39, AMBER, True)
    write(draw, (75 + offset, 420), "AVIATION", 42, AMBER, True)
    paragraph(draw, (78, 489), "How modern AI can benefit the aviation ecosystem: a gate-planning case study from problem to measurable outcome.", 470, 15, MUTED, 23)
    draw_gate_matrix(draw, 650, 276, 0.98)
    write(draw, (78, 635), "SYNTHETIC SCHEDULE  ·  300 AIRCRAFT  ·  40 GATES", 10, FAINT, True)

def metric_card(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, number: str, label: str, detail: str, accent=MINT) -> None:
    rounded(draw, (x, y, x + width, y + 190), 8, PANEL, outline=(54, 72, 64), width=1)
    write(draw, (x + 21, y + 18), "SYSTEM SIGNAL", 9, FAINT, True)
    write(draw, (x + 21, y + 50), number, 54, accent, True)
    write(draw, (x + 21, y + 119), label, 11, INK, True)
    paragraph(draw, (x + 21, y + 146), detail, width - 42, 11, MUTED, 16)

def slide_problem(draw: ImageDraw.ImageDraw, p: float) -> None:
    write(draw, (70, 137), "01  /  THE OPERATING ENVELOPE", 11, MINT, True)
    write(draw, (70, 177), "CAPACITY IS FINITE.", 48, INK, True)
    write(draw, (70, 230), "DEMAND IS NOT.", 48, MINT, True)
    write(draw, (72, 307), "THE INITIAL ASSIGNMENT REVEALS THE BOTTLENECK", 10, MUTED, True)
    cards = [(300, "300", "AIRCRAFT", "One scheduled arrival and departure each"), (40, "40", "GATES", "10 Code F · 30 standard"), (137, "BLOCKED ARRIVALS", "45.7%", "Gate occupied when arrival needs service")]
    positions = [76, 467, 858]
    for index, (number, label, detail, _) in enumerate(cards):
        reveal = ease(max(0, min(1, (p * 1.45) - index * 0.22)))
        y = 368 + int((1 - reveal) * 32)
        metric_card(draw, positions[index], y, 346, str(number), label, detail, AMBER if index == 2 else MINT)
    draw.line((77, 601, 1200, 601), fill=(65, 81, 72), width=1)
    write(draw, (78, 623), "The bottleneck is temporal, not just spatial.", 21, INK, True)
    write(draw, (78, 654), "Minute-level gate occupancy includes midnight wraparound.", 12, MUTED)

def slide_constraints(draw: ImageDraw.ImageDraw, p: float) -> None:
    write(draw, (70, 124), "02  /  OPERATING PARADIGM", 10, MINT, True)
    write(draw, (70, 157), "OPERATING PARADIGM", 38, INK, True)
    write(draw, (70, 201), "OF AN AERODROME", 38, MINT, True)
    rules = [
        ("01", "COMPATIBILITY", "Aircraft gates are coded for specific types of aircraft."),
        ("02", "EXCLUSIVE OCCUPANCY", "Dynamic service windows reflect turnaround time."),
        ("03", "OPERATIONAL PEAKS", "Flight volumes into and out of an aerodrome vary throughout the day."),
        ("04", "CHANGE HAS A COST", "Reduce conflicts, retain original gates."),
    ]
    for index, (num, title, description) in enumerate(rules):
        y = 282 + index * 91
        reveal = ease(max(0, min(1, p * 1.6 - index * 0.18)))
        x = 70 + int((1 - reveal) * -28)
        rounded(draw, (x, y, x + 615, y + 76), 4, PANEL, outline=(51, 68, 61))
        write(draw, (x + 17, y + 18), num, 17, AMBER, True)
        write(draw, (x + 65, y + 11), title, 11, INK, True)
        paragraph(draw, (x + 65, y + 36), description, 525, 10, MUTED, 13)
    draw_gate_matrix(draw, 760, 307, 0.8)

def bar(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int, fraction: float, color=MINT) -> None:
    rounded(draw, (x, y, x + width, y + height), height // 2, (45, 59, 53))
    fill_width = int(width * max(0, min(1, fraction)))
    if fill_width:
        rounded(draw, (x, y, x + fill_width, y + height), height // 2, color)

def slide_baseline(draw: ImageDraw.ImageDraw, p: float) -> None:
    write(draw, (70, 136), "03  /  GOOGLE OR-TOOLS CP-SAT", 11, MINT, True)
    write(draw, (70, 177), "FEWER CONFLICTS.", 47, INK, True)
    write(draw, (70, 230), "NOT YET ZERO.", 47, AMBER, True)
    rounded(draw, (70, 315, 1210, 585), 7, PANEL, outline=(56, 73, 65))
    write(draw, (104, 344), "DEDICATED GATE GROUPS", 10, MUTED, True)
    write(draw, (104, 387), "172", 58, INK, True)
    write(draw, (105, 452), "INITIAL CONFLICTS", 9, MUTED, True)
    draw.line((338, 386, 338, 493), fill=(58, 76, 67), width=1)
    write(draw, (395, 409), "→", 39, FAINT, True)
    write(draw, (516, 387), "7", 58, MINT, True)
    write(draw, (518, 452), "AFTER CP-SAT", 9, MUTED, True)
    write(draw, (746, 392), "−96%", 25, MINT, True)
    bar(draw, 746, 446, 385, 8, 1 - 7 / 172, MINT)
    write(draw, (746, 466), "172 INITIAL", 9, FAINT, True)
    write(draw, (1050, 466), "0", 9, FAINT, True, "ra")
    write(draw, (104, 523), "135 / 300 AIRCRAFT REASSIGNED", 10, AMBER, True)
    rounded(draw, (70, 610, 1210, 672), 4, (45, 34, 27), outline=(117, 81, 52))
    centered(draw, 640, 641, "FEASIBLE  ·  NOT PROVEN OPTIMAL", 17, AMBER, True)

def slide_flexible(draw: ImageDraw.ImageDraw, p: float) -> None:
    write(draw, (70, 136), "04  /  FLEXIBLE GATE ACCESS", 11, MINT, True)
    write(draw, (70, 177), "SHARE THE CAPACITY.", 47, INK, True)
    write(draw, (70, 230), "CHANGE THE RESULT.", 47, MINT, True)
    rounded(draw, (70, 312, 1210, 585), 7, PANEL, outline=(56, 73, 65))
    write(draw, (104, 341), "NON CODE F AIRCRAFT MAY ALSO USE CODE F GATES", 10, MUTED, True)
    write(draw, (104, 395), "172", 58, INK, True)
    write(draw, (105, 461), "INITIAL CONFLICTS", 9, MUTED, True)
    draw.line((338, 386, 338, 500), fill=(58, 76, 67), width=1)
    write(draw, (395, 416), "→", 39, FAINT, True)
    write(draw, (515, 395), "6", 58, MINT, True)
    write(draw, (518, 461), "AFTER CP-SAT", 9, MUTED, True)
    write(draw, (744, 399), "−97%", 25, MINT, True)
    bar(draw, 744, 449, 386, 8, 1 - 6 / 172, MINT)
    write(draw, (104, 526), "130 / 300 AIRCRAFT REASSIGNED", 10, AMBER, True)
    write(draw, (746, 526), "18 NON CODE F AIRCRAFT USED CODE F GATES", 10, INK, True)
    rounded(draw, (70, 610, 1210, 672), 4, (45, 34, 27), outline=(117, 81, 52))
    centered(draw, 640, 641, "FEASIBLE  ·  NOT PROVEN OPTIMAL", 17, AMBER, True)

def slide_future(draw: ImageDraw.ImageDraw, p: float) -> None:
    write(draw, (70, 136), "05  /  WHAT'S NEXT", 11, MINT, True)
    write(draw, (70, 177), "THE NEXT EXPERIMENT", 47, INK, True)
    write(draw, (70, 230), "IS THE COMPARISON.", 47, MINT, True)
    cards = [
        ("A", "MODEL COMPARISONS", "CP-SAT vs metaheuristics", "Tabu / annealing", "Quality · runtime · stability", AMBER),
        ("B", "PASSENGER MOVEMENT", "OD and TT demand", "Connection flows", "Transfer-window impact", MINT),
        ("C", "ENGINEERING", "Turnaround considerations", "Taxi and buffers", "Disruption scenarios", (146, 183, 162)),
    ]
    for index, (letter, label, line1, line2, line3, accent) in enumerate(cards):
        reveal = ease(max(0, min(1, p * 1.45 - index * 0.2)))
        x = 73 + index * 390
        y = 323 + int((1 - reveal) * 26)
        rounded(draw, (x, y, x + 350, y + 243), 6, PANEL, outline=(54, 71, 63))
        write(draw, (x + 22, y + 19), letter, 18, accent, True)
        write(draw, (x + 22, y + 63), label, 11, MUTED, True)
        draw.line((x + 22, y + 91, x + 320, y + 91), fill=(54, 71, 63), width=1)
        for offset, line in enumerate((line1, line2, line3)):
            draw.ellipse((x + 25, y + 117 + offset * 31, x + 31, y + 123 + offset * 31), fill=accent)
            write(draw, (x + 42, y + 112 + offset * 31), line, 13, INK)
    write(draw, (75, 616), "COMPARE ON QUALITY  /  RUNTIME  /  ROBUSTNESS  /  VALIDATION", 11, AMBER, True)
    write(draw, (75, 653), "Next: compare decision quality, passenger impact, engineering realism and runtime.", 12, MUTED)

def slide_caveat(draw: ImageDraw.ImageDraw, p: float) -> None:
    write(draw, (70, 153), "DECISION SUPPORT,", 54, INK, True)
    write(draw, (70, 213), "NOT AUTOPILOT.", 54, MINT, True)
    write(draw, (74, 301), "A PROTOTYPE WITH CLEAR BOUNDARIES", 11, AMBER, True)
    draw_gate_matrix(draw, 810, 133, 0.62)
    rounded(draw, (72, 350, 1208, 566), 7, PANEL, outline=(117, 81, 52))
    paragraph(
        draw,
        (105, 385),
        "This case study uses synthetic schedules, passenger counts and capacity proxies. CP-SAT returned feasible assignments within a time limit; neither result proves global optimality. Validate fleet layouts, operating buffers, passenger connections and disruption rules before real-world use.",
        1050,
        18,
        INK,
        31,
    )
    draw.line((105, 514, 1170, 514), fill=(64, 77, 68), width=1)
    write(draw, (105, 535), "GATE LOGIC  ·  AVIATION AI CASE 001", 10, MUTED, True)
    write(draw, (1170, 535), "END OF STUDY  /  2026", 10, FAINT, True, "ra")
    write(draw, (75, 631), "PROBLEM  →  CONSTRAINTS  →  CP-SAT  →  OUTCOMES  →  FUTURE WORK", 12, MINT, True)

def mobile_title(draw: ImageDraw.ImageDraw, section: str, title: str, second_line: str | None = None) -> None:
    write(draw, (70, 116), section, 11, MINT, True)
    if second_line:
        write(draw, (70, 158), title, 40, INK, True)
        write(draw, (70, 228), second_line, 40, MINT, True)
    else:
        write(draw, (70, 178), title, 40, INK, True)

def mobile_intro(draw: ImageDraw.ImageDraw, progress: float) -> None:
    centered(draw, 640, 165, "AVIATION OPERATIONS  /  PROOF OF CONCEPT", 12, MINT, True)
    centered(draw, 640, 258, "MODERN AI FOR AVIATION", 43, INK, True)
    centered(draw, 640, 327, "A PROOF OF CONCEPT", 36, MINT, True)
    paragraph(
        draw,
        (165, 392),
        "From an airport scheduling problem to a measurable solver outcome.",
        950,
        18,
        MUTED,
    )
    rounded(draw, (105, 520, 1175, 665), 8, PANEL, outline=(54, 72, 64), width=2)
    for x, number, label in ((280, "300", "AIRCRAFT"), (640, "40", "GATES"), (1000, "24 H", "TIME CYCLE")):
        centered(draw, x, 570, number, 40, MINT, True)
        centered(draw, x, 625, label, 14, INK, True)
    draw.line((460, 540, 460, 643), fill=(54, 72, 64), width=2)
    draw.line((820, 540, 820, 643), fill=(54, 72, 64), width=2)

def mobile_problem(draw: ImageDraw.ImageDraw, progress: float) -> None:
    mobile_title(draw, "01  /  THE PROBLEM", "CAPACITY IS FINITE.", "DEMAND IS NOT.")
    cards = [
        ("300", "AIRCRAFT", "Arrival + departure per aircraft."),
        ("40", "GATES", "10 Code F · 30 standard."),
        ("137", "BLOCKED ARRIVALS", "Gate occupied on arrival."),
    ]
    positions = [70, 465, 860]
    for index, (number, label, detail) in enumerate(cards):
        x = positions[index]
        y = 346 + round((1 - ease(min(1, progress * 1.4 - index * 0.18))) * 12)
        rounded(draw, (x, y, x + 350, y + 286), 8, PANEL, outline=(54, 72, 64), width=2)
        centered(draw, x + 175, y + 72, number, 58, AMBER if index == 2 else MINT, True)
        centered(draw, x + 175, y + 146, label, 13, INK, True)
        paragraph(draw, (x + 24, y + 183), detail, 302, 11, MUTED)
    centered(draw, 640, 674, "THE BOTTLENECK IS TEMPORAL, NOT JUST SPATIAL.", 11, INK, True)

def mobile_constraints(draw: ImageDraw.ImageDraw, progress: float) -> None:
    mobile_title(draw, "02  /  OPERATING PARADIGM", "OPERATING PARADIGM", "OF AN AERODROME")
    rows = [
        ("01", "COMPATIBILITY", "Gates are coded for aircraft types."),
        ("02", "EXCLUSIVE OCCUPANCY", "Service windows vary with turnaround."),
        ("03", "OPERATIONAL PEAKS", "Flight volumes change throughout the day."),
        ("04", "CHANGE HAS A COST", "Reduce conflicts; retain original gates."),
    ]
    for index, (number, title, detail) in enumerate(rows):
        y = 300 + index * 92
        rounded(draw, (70, y, 1210, y + 84), 5, PANEL, outline=(51, 68, 61), width=2)
        write(draw, (95, y + 23), number, 14, AMBER, True)
        write(draw, (176, y + 5), title, 11, INK, True)
        write(draw, (176, y + 44), detail, 11, MUTED)

def mobile_outcome(draw: ImageDraw.ImageDraw, flexible: bool) -> None:
    section = "04  /  FLEXIBLE GATE ACCESS" if flexible else "03  /  GOOGLE OR-TOOLS CP-SAT"
    title = "SHARED GATES. FEWER CONFLICTS." if flexible else "FEWER CONFLICTS."
    second_line = "A BETTER FEASIBLE RESULT." if flexible else "NOT YET ZERO."
    mobile_title(draw, section, title, second_line)
    rounded(draw, (70, 306, 1210, 568), 8, PANEL, outline=(56, 73, 65), width=2)
    if flexible:
        centered(draw, 640, 337, "NON CODE F AIRCRAFT MAY ALSO USE CODE F GATES", 11, MUTED, True)
    else:
        centered(draw, 640, 337, "GOOGLE OR-TOOLS CP-SAT  /  DEDICATED GATE GROUPS", 11, MUTED, True)
    left_x = 360 if flexible else 365
    right_x = 870 if flexible else 865
    centered(draw, left_x, 423, "172", 70, INK, True)
    centered(draw, left_x, 490, "INITIAL CONFLICTS", 11, MUTED, True)
    centered(draw, 615, 430, "→", 36, FAINT, True)
    after = "6" if flexible else "7"
    centered(draw, right_x, 423, after, 70, MINT, True)
    centered(draw, right_x, 490, "AFTER CP-SAT", 11, MUTED, True)
    centered(draw, 640, 538, "−97%" if flexible else "−96%", 15, AMBER, True)
    if flexible:
        centered(draw, 640, 586, "130 OF 300 AIRCRAFT MOVED", 11, INK, True)
        centered(draw, 640, 632, "18 NON CODE F AIRCRAFT USED CODE F GATES", 11, MINT, True)
    else:
        centered(draw, 640, 610, "135 OF 300 AIRCRAFT REASSIGNED", 11, INK, True)
    rounded(draw, (200, 660, 1080, 712), 5, (45, 34, 27), outline=(117, 81, 52), width=2)
    centered(draw, 640, 686, "FEASIBLE  ·  NOT PROVEN OPTIMAL", 14, AMBER, True)

def mobile_future(draw: ImageDraw.ImageDraw, progress: float) -> None:
    mobile_title(draw, "05  /  FUTURE WORK", "THE NEXT EXPERIMENT", "IS THE COMPARISON.")
    cards = [
        ("MODEL COMPARISON", "Compare CP-SAT with tabu, annealing and genetic search."),
        ("PASSENGER FLOWS", "Simulate OD, TT and connection-window demand."),
        ("ENGINEERING", "Add turnaround, taxi, buffers and disruptions."),
    ]
    for index, (heading, detail) in enumerate(cards):
        x = 70 + index * 395
        rounded(draw, (x, 310, x + 360, 650), 7, PANEL, outline=(54, 71, 63), width=2)
        write(draw, (x + 22, 334), f"0{index + 1}", 10, AMBER if index == 0 else MINT, True)
        paragraph(draw, (x + 22, 380), heading, 316, 10, INK, bold=True)
        paragraph(draw, (x + 22, 455), detail, 316, 10, MUTED)
    centered(draw, 640, 683, "COMPARE QUALITY  ·  RUNTIME  ·  ROBUSTNESS", 10, AMBER, True)

def mobile_caveat(draw: ImageDraw.ImageDraw, progress: float) -> None:
    centered(draw, 640, 160, "DECISION SUPPORT", 44, INK, True)
    centered(draw, 640, 232, "NOT AUTOPILOT", 44, MINT, True)
    rounded(draw, (90, 316, 1190, 665), 8, PANEL, outline=(117, 81, 52), width=2)
    centered(draw, 640, 360, "PROTOTYPE CAVEAT", 13, AMBER, True)
    for y, line in zip(
        (420, 470, 520, 570, 620),
        (
            "Synthetic schedules and passenger counts.",
            "Capacity includes fleet-layout proxies.",
            "Feasible solutions; optimality is unproven.",
            "Validate fleet, buffers, connections, baggage,",
            "and disruption cases before any operational use.",
        ),
    ):
        centered(draw, 640, y, line, 11, INK)

def mobile_scene_drawers():
    return [
        mobile_intro,
        mobile_problem,
        mobile_constraints,
        lambda draw, progress: mobile_outcome(draw, False),
        lambda draw, progress: mobile_outcome(draw, True),
        mobile_future,
        mobile_caveat,
    ]

def render_frame(frame_index: int) -> Image.Image:
    scene_index = min(frame_index // (FPS * SCENE_SECONDS), SCENE_COUNT - 1)
    frame_in_scene = frame_index % (FPS * SCENE_SECONDS)
    p = frame_in_scene / (FPS * SCENE_SECONDS - 1)
    image, draw = base_frame(scene_index, p)
    scene_drawers = [
        slide_intro,
        slide_problem,
        slide_constraints,
        slide_baseline,
        slide_flexible,
        slide_future,
        slide_caveat,
    ]
    scene_drawers[scene_index](draw, p)

    # Crossfade from the preceding complete scene to avoid a black flash.
    fade_frames = 10
    if scene_index > 0 and frame_in_scene < fade_frames:
        previous, previous_draw = base_frame(scene_index - 1, 0.98)
        scene_drawers[scene_index - 1](previous_draw, 0.98)
        image = Image.blend(previous, image, ease((frame_in_scene + 1) / fade_frames))
    return image

def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("gate_logic_case_study.mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio_ffmpeg.write_frames(
        str(output),
        (WIDTH, HEIGHT),
        fps=FPS,
        codec="libx264",
        quality=8,
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        macro_block_size=1,
    )
    writer.send(None)
    for frame_index in range(TOTAL_FRAMES):
        writer.send(np.asarray(render_frame(frame_index), dtype=np.uint8).tobytes())
    writer.close()
    print(f"Rendered {output} ({TOTAL_FRAMES / FPS:.0f}s, {WIDTH}x{HEIGHT}, {FPS}fps).")

if __name__ == "__main__":
    main()
