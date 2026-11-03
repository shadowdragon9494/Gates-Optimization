"""Render a cursor-guided MP4 walkthrough of the gate-planning webpage."""

# --- Imports and video composition settings ---
from __future__ import annotations

import math
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT, FPS = 1600, 900, 24
DURATION_SECONDS = 24
TOTAL_FRAMES = FPS * DURATION_SECONDS
OUTPUT = Path(__file__).with_name("gate_planner_demo.mp4")

BG = (16, 26, 25)
PANEL = (23, 35, 33)
SURFACE = (16, 27, 24)
LINE = (48, 67, 62)
TEXT = (227, 235, 229)
MUTED = (158, 175, 167)
MINT = (167, 230, 189)
AMBER = (233, 189, 136)
RED = (233, 147, 131)
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT_REGULAR_PATH = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD_PATH = FONT_DIR / "DejaVuSans-Bold.ttf"


# --- Font, easing, and rounded-panel drawing helpers ---
def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    path = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    outline: tuple[int, int, int] | None = None,
    radius: int = 9,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    size: int = 14,
    color: tuple[int, int, int] = TEXT,
    bold: bool = False,
) -> None:
    draw.text(xy, value, font=font(size, bold), fill=color)


def centered(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    size: int = 14,
    color: tuple[int, int, int] = TEXT,
    bold: bool = False,
) -> None:
    draw.text(xy, value, font=font(size, bold), fill=color, anchor="mm")


# --- Draw the browser frame and current planner webpage layout ---
def draw_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 36), fill=(27, 37, 35))
    for x in (18, 38, 58):
        draw.ellipse((x - 5, 13, x + 5, 23), fill=(100, 115, 108))
    rounded(draw, (105, 7, 1470, 30), (19, 28, 27), radius=11)
    text(draw, (125, 12), "localhost:8080", 11, MUTED)
    text(draw, (1510, 10), "⋯", 20, MUTED)

    draw.rectangle((0, 37, WIDTH, 94), fill=(16, 26, 25))
    draw.line((0, 93, WIDTH, 93), fill=LINE)
    text(draw, (61, 48), "G", 29, TEXT, True)
    text(draw, (88, 48), "/", 29, MINT, True)
    text(draw, (112, 50), "GATE LOGIC", 16, TEXT, True)
    text(draw, (112, 70), "PLANNING WORKSPACE", 9, MUTED)
    text(draw, (1324, 59), "SYNTHETIC DATA · RESEARCH PROTOTYPE", 10, MINT, True)

    text(draw, (62, 111), "AIRPORT OPERATIONS / SCENARIO LAB", 11, MINT, True)
    text(draw, (62, 130), "A clearer plan.  One conversation away.", 25, TEXT)
    text(draw, (62, 164), "Explore gate assignments, then watch the solver’s plan unfold.", 13, MUTED)

    rounded(draw, (60, 194, 460, 855), PANEL, LINE)
    rounded(draw, (482, 194, 1540, 855), PANEL, LINE)
    return image, draw


# --- Draw the assistant panel, messages, and request box ---
def draw_chat(draw: ImageDraw.ImageDraw, progress: float) -> None:
    text(draw, (85, 214), "Planning assistant", 17)
    rounded(draw, (343, 207, 438, 237), SURFACE, LINE, radius=6)
    centered(draw, (390, 222), "New conversation", 10, MUTED)
    draw.line((84, 250, 436, 250), fill=LINE)

    rounded(draw, (84, 272, 436, 390), (35, 51, 45), radius=8)
    text(draw, (101, 287), "Ask me to optimise a schedule or compare", 12)
    text(draw, (101, 307), "gate policies. I’ll show original conflicts", 12)
    text(draw, (101, 327), "before CP-SAT reassignment.", 12)
    if progress > 0.53:
        rounded(draw, (104, 347, 416, 380), (46, 57, 49), radius=7)
        text(draw, (116, 356), "Optimise the default schedule", 11, AMBER)

    rounded(draw, (84, 407, 251, 438), SURFACE, LINE, radius=6)
    centered(draw, (168, 422), "Optimise baseline ↗", 10, MUTED)
    rounded(draw, (260, 407, 436, 438), SURFACE, LINE, radius=6)
    centered(draw, (348, 422), "Compare policies ↗", 10, MUTED)
    rounded(draw, (84, 454, 436, 564), SURFACE, LINE, radius=7)
    text(draw, (101, 471), "What would you like to explore?", 12, MUTED)
    draw.line((100, 498, 420, 498), fill=LINE)
    text(draw, (101, 515), "Optimise the default schedule…", 12, MUTED)
    rounded(draw, (84, 576, 436, 619), MINT, radius=7)
    text(draw, (102, 588), "Send request", 13, (16, 37, 26), True)
    text(draw, (409, 586), "↗", 17, (16, 37, 26), True)
    text(draw, (84, 645), "OpenAI configured · CP-SAT runs on the server", 10, MUTED)
    text(draw, (84, 817), "Plain-English requests can tune the scenario.", 10, MUTED)


# --- Draw solver inputs, status, result metrics, and playback controls ---
def field(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: str,
    width: int = 130,
    highlighted: bool = False,
) -> None:
    text(draw, (x, y), label, 11, MINT if highlighted else MUTED)
    rounded(
        draw,
        (x, y + 20, x + width, y + 53),
        SURFACE,
        MINT if highlighted else LINE,
        radius=6,
        width=2 if highlighted else 1,
    )
    text(draw, (x + 10, y + 29), value, 12, TEXT)


def draw_controls(
    draw: ImageDraw.ImageDraw,
    time_seconds: float,
    callout: str,
    click_phase: float,
    result: dict,
    current_time: int,
    playing: bool,
) -> None:
    result_ready = time_seconds >= 12.4
    text(draw, (510, 214), "Airfield playback", 17)
    rounded(draw, (1393, 207, 1512, 236), SURFACE, LINE, radius=7)
    centered(
        draw,
        (1452, 221),
        result["status"] if result_ready else "READY",
        10,
        MINT,
        True,
    )
    draw.line((506, 250, 1516, 250), fill=LINE)

    field(draw, 510, 267, "Schedule", "Default", 126)
    field(draw, 650, 267, "Aircraft", "300", 92)
    field(draw, 755, 267, "Gates", "40", 92)
    field(draw, 860, 267, "Locked (%)", "5", 108, callout == "locked")
    field(draw, 980, 267, "Connections", "0", 120)
    field(draw, 1110, 267, "Solver limit (seconds)", "10", 135)
    field(draw, 1255, 267, "Handling rate", "Default: 2 hours", 155, callout == "handling")
    rounded(
        draw,
        (1420, 305, 1516, 347),
        MINT if click_phase > 0.35 else SURFACE,
        MINT,
        radius=7,
        width=2,
    )
    centered(draw, (1468, 326), "Run solver preview", 10, (16, 37, 26) if click_phase > 0.35 else TEXT, True)

    if time_seconds >= 8.6:
        rounded(draw, (510, 358, 1516, 396), (19, 31, 28), LINE, radius=6)
        running = not result_ready
        text(
            draw,
            (528, 369),
            "Running CP-SAT solver…" if running else (result.get("message") or "CP-SAT returned a gate assignment."),
            11,
            MINT,
        )
        text(draw, (1268, 369), "Working…" if running else "Complete", 10, MUTED)
        draw.rounded_rectangle((1333, 374, 1489, 382), radius=4, fill=(45, 64, 56))
        if running:
            segment_x = 1333 + int(((time_seconds - 8.6) % 1.2) / 1.2 * 116)
            draw.rounded_rectangle((segment_x, 374, segment_x + 40, 382), radius=4, fill=MINT)
        else:
            draw.rounded_rectangle((1333, 374, 1489, 382), radius=4, fill=MINT)

    rounded(draw, (510, 408, 1516, 446), SURFACE, LINE, radius=6)
    text(draw, (528, 421), "Result", 11, MUTED)
    text(draw, (601, 421), f"default / 300 aircraft / 40 gates / Separate / {result['status'] if result_ready else 'RUNNING'}", 11, TEXT)
    text(draw, (1402, 421), "Download JSON ↓", 10, MUTED)

    original_conflicts = result["original_conflicts"]
    optimized_conflicts = result.get("optimized_conflicts") or original_conflicts
    moved = result.get("aircraft_moved") or 0
    connections = result.get("connections_fulfilled") or 0
    values = (
        str(original_conflicts),
        str(moved if result_ready else 0),
        str(max(0, original_conflicts - optimized_conflicts) if result_ready else 0),
        str(connections if result_ready else 0),
    )
    labels = ("Conflicts before CP-SAT", "Aircraft moved", "Conflicts removed", "Connections fulfilled")
    metric_width = 241
    for index, (value, label) in enumerate(zip(values, labels)):
        x = 510 + index * 253
        rounded(draw, (x, 457, x + metric_width, 518), SURFACE, LINE, radius=7)
        text(draw, (x + 13, 463), value, 23, MINT)
        text(draw, (x + 76, 473), label, 10, MUTED)

    rounded(draw, (510, 529, 566, 562), SURFACE, LINE, radius=6)
    centered(draw, (538, 546), "Ⅱ Pause" if playing else "▶ Play", 11, TEXT, True)
    rounded(draw, (578, 539, 987, 552), (44, 64, 56), radius=6)
    draw.rounded_rectangle(
        (578, 539, 578 + int(409 * current_time / 1440), 552),
        radius=6,
        fill=MINT,
    )
    text(draw, (1000, 536), f"{current_time // 60:02d}:{current_time % 60:02d}", 13, TEXT, True)
    text(draw, (1083, 538), "View", 10, MUTED)
    rounded(draw, (1124, 529, 1282, 562), SURFACE, MINT if callout == "view" else LINE, radius=6)
    text(draw, (1136, 539), "After CP-SAT  ▾", 10, TEXT)
    quality = {
        "OPTIMAL": "Proven optimal weighted objective",
        "FEASIBLE": "Feasible · optimality not proven",
        "HEURISTIC": "Greedy fallback · not a CP-SAT solution",
        "SKIPPED": "CP-SAT skipped",
    }.get(result["status"], result["status"])
    text(draw, (1312, 539), f"● {quality}", 9, MUTED)
    text(draw, (510, 575), "A380-compatible", 9, MUTED)
    draw.ellipse((626, 579, 634, 587), fill=MINT)
    text(draw, (649, 575), "Occupied", 9, MUTED)
    draw.ellipse((701, 579, 709, 587), fill=AMBER)
    text(draw, (724, 575), "Conflict", 9, MUTED)
    draw.ellipse((773, 579, 781, 587), fill=RED)


# --- Draw the 40 animated gates and aircraft currently occupying them ---
def gate_occupants(flights: list[dict], minute: int) -> list[list[str]]:
    occupants = [[] for _ in range(40)]
    for flight in flights:
        arrival = int(flight["arrival_minute"])
        duration = min(int(flight["duration_minutes"]), 1440)
        if (minute - arrival + 1440) % 1440 < duration:
            gate_number = int(flight["optimized_gate"].split()[1])
            if 1 <= gate_number <= 40:
                occupants[gate_number - 1].append(flight["aircraft_id"])
    return occupants


def draw_gate_grid(
    draw: ImageDraw.ImageDraw,
    flights: list[dict],
    minute: int,
    previous_occupants: list[list[str]],
    pulse: float,
) -> list[list[str]]:
    occupants = gate_occupants(flights, minute)
    left, top = 510, 601
    cell_width, cell_height = 119, 43
    gap_x, gap_y = 7, 6
    for index in range(40):
        row, column = divmod(index, 8)
        x = left + column * (cell_width + gap_x)
        y = top + row * (cell_height + gap_y)
        current = occupants[index]
        if len(current) > 1:
            fill, border = (73, 47, 41), RED
        elif current:
            fill, border = (59, 57, 41), AMBER
        else:
            fill, border = ((24, 42, 36), (57, 93, 71)) if index < 10 else ((29, 41, 38), LINE)
        rounded(draw, (x, y, x + cell_width, y + cell_height), fill, border, radius=6)
        if current and current != previous_occupants[index]:
            radius = int(5 + 6 * pulse)
            center_x, center_y = x + cell_width - 12, y + 11
            draw.ellipse(
                (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                outline=AMBER,
                width=2,
            )
        text(draw, (x + 9, y + 5), f"{index + 1:02d}", 10, MINT if index < 10 else MUTED, True)
        if current:
            centered(draw, (x + 60, y + 23), f"✈  {len(current)} AIRCRAFT", 10, AMBER, True)
        else:
            centered(draw, (x + 70, y + 23), "EMPTY", 8, MUTED)
    return occupants


# --- Draw a moving mouse pointer, click ripple, and tutorial caption ---
def pointer_position(time_seconds: float) -> tuple[float, float]:
    targets = [
        (1.0, (95, 169)),
        (3.4, (914, 280)),
        (5.6, (1328, 282)),
        (8.0, (1468, 326)),
        (11.4, (1455, 327)),
        (14.2, (1200, 546)),
        (16.1, (537, 546)),
        (17.2, (537, 546)),
        (22.8, (1465, 792)),
    ]
    for (start_time, start), (end_time, end) in zip(targets, targets[1:]):
        if start_time <= time_seconds <= end_time:
            phase = ease((time_seconds - start_time) / (end_time - start_time))
            return (start[0] + (end[0] - start[0]) * phase,
                    start[1] + (end[1] - start[1]) * phase)
    return targets[0][1] if time_seconds < targets[0][0] else targets[-1][1]


def draw_pointer(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    time_seconds: float,
) -> None:
    click_times = (8.2, 14.35, 16.25)
    clicking = min(abs(time_seconds - click) for click in click_times) < 0.23
    if clicking:
        ripple = min(abs(time_seconds - click) for click in click_times) / 0.23
        radius = int(10 + (1 - ripple) * 11)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=MINT, width=2)
    points = [(x, y), (x + 1, y + 26), (x + 7, y + 19), (x + 13, y + 31), (x + 19, y + 28), (x + 12, y + 16), (x + 22, y + 16)]
    draw.polygon(points, fill=(250, 252, 248))
    draw.line(points + [points[0]], fill=(12, 20, 18), width=2, joint="curve")


def caption_for_time(time_seconds: float) -> str:
    if time_seconds < 3.2:
        return "Set a scenario in seconds"
    if time_seconds < 5.3:
        return "Choose how many aircraft stay gate-locked"
    if time_seconds < 7.7:
        return "Tune handling time for passenger volume"
    if time_seconds < 10.2:
        return "Run the gate-assignment solver"
    if time_seconds < 13.5:
        return "CP-SAT is finding a better assignment…"
    if time_seconds < 15.8:
        return "Review the before-and-after plan"
    if time_seconds < 17.4:
        return "Click Play to start airfield playback"
    return "Watch aircraft occupancy change across 40 gates"


# --- Compose each video frame with state changes and animated playback ---
def render_frame(frame_index: int, flights: list[dict]) -> Image.Image:
    time_seconds = frame_index / FPS
    image, draw = draw_page()
    draw_chat(draw, time_seconds / DURATION_SECONDS)

    if time_seconds < 5.4:
        callout = "locked"
    elif time_seconds < 7.8:
        callout = "handling"
    elif time_seconds < 14:
        callout = "run"
    elif time_seconds < 16:
        callout = "view"
    else:
        callout = "play"
    click_phase = max(0.0, min(1.0, (time_seconds - 8.0) / 0.6))
    minute = int((360 + max(0, time_seconds - 17.1) * 38) % 1440)
    if time_seconds < 17.1:
        minute = 360
    result = getattr(render_frame, "result", {})
    playing = time_seconds >= 16.3
    draw_controls(
        draw,
        time_seconds,
        callout,
        click_phase,
        result,
        minute,
        playing,
    )
    previous = getattr(render_frame, "previous_occupants", [[] for _ in range(40)])
    occupants = draw_gate_grid(
        draw,
        flights,
        minute,
        previous,
        (time_seconds * 2.4) % 1,
    )
    render_frame.previous_occupants = occupants

    caption = caption_for_time(time_seconds)
    rounded(draw, (484, 858, 1539, 891), (13, 22, 20), LINE, radius=7)
    centered(draw, (1010, 875), caption, 13, MINT, True)
    x, y = pointer_position(time_seconds)
    draw_pointer(draw, x, y, time_seconds)
    return image


# --- Run the data-backed rendering and encode the MP4 ---
def main() -> None:
    sys.path.insert(0, str(ROOT))
    from gate_solver import optimize_gates

    output = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    result = optimize_gates(time_limit_seconds=3)
    render_frame.result = result
    flights = result.get("assignments") or []
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
    render_frame.previous_occupants = [[] for _ in range(40)]
    for frame_index in range(TOTAL_FRAMES):
        frame = render_frame(frame_index, flights)
        writer.send(np.asarray(frame, dtype=np.uint8).tobytes())
    writer.close()
    print(
        f"Rendered {output} ({DURATION_SECONDS}s, {WIDTH}x{HEIGHT}, "
        f"{FPS}fps; solver status {result['status']})."
    )


if __name__ == "__main__":
    main()
