#!/usr/bin/env python3
"""Generate an animated ASCII spinning-donut banner as a self-contained SVG.

Pure standard library. Computes the classic donut.c torus, renders each frame
as luminance-shaded ASCII (cyan to white), and emits a single SVG whose frames
cycle via CSS keyframes + per-frame animation-delay. Works as a GitHub README
banner when referenced with <img src="assets/donut.svg">, because GitHub serves
the SVG as an image and the browser runs the CSS animation.

Run:  python scripts/gen_donut.py  ->  writes assets/donut.svg
"""

import math
import os

# --- ASCII grid ---
W, H = 72, 24
RAMP = ".,-~:;=!*#$@"          # 12 brightness levels, dim -> bright
K = 15.0                        # projection scale (distance scaling)
XFAC = 1.6                      # horizontal stretch so the torus reads as round
THETA_STEP = 0.07
PHI_STEP = 0.02

# --- animation ---
N_FRAMES = 120
DURATION_S = 6.0                # full loop length
A_TURNS = 2                     # full rotations on the A axis over the loop
B_TURNS = 1                     # full rotations on the B axis over the loop
DA = 2 * math.pi * A_TURNS / N_FRAMES
DB = 2 * math.pi * B_TURNS / N_FRAMES

# --- layout (SVG units) ---
VB_W, VB_H = 640, 430
CHAR_W = 7.5
LINE_H = 13.7
FONT_SIZE = 13
BLOCK_X = (VB_W - W * CHAR_W) / 2     # centered horizontally
BLOCK_Y0 = 92                          # first baseline
FONT = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"

# --- luminance bands: (max ramp index inclusive, color) dim -> bright ---
BANDS = [
    (3, "#0ea5e9"),   # deep cyan (shadowed)
    (7, "#38bdf8"),   # mid cyan
    (11, "#e0f2fe"),  # near white (lit edge)
]


def band_of(ramp_idx):
    for b, (hi, _color) in enumerate(BANDS):
        if ramp_idx <= hi:
            return b
    return len(BANDS) - 1


def render_frame(A, B):
    """Return a 2D list [row][col] of ramp indices, or -1 for empty cells."""
    grid = [[-1] * W for _ in range(H)]
    zbuf = [[0.0] * W for _ in range(H)]
    cA, sA = math.cos(A), math.sin(A)
    cB, sB = math.cos(B), math.sin(B)

    theta = 0.0
    while theta < 2 * math.pi:
        ct, st = math.cos(theta), math.sin(theta)
        phi = 0.0
        while phi < 2 * math.pi:
            cp, sp = math.cos(phi), math.sin(phi)
            ox = 2 + ct
            oy = st
            x = ox * (cB * cp + sA * sB * sp) - oy * cA * sB
            y = ox * (sB * cp - sA * cB * sp) + oy * cA * cB
            z = 5 + cA * ox * sp + oy * sA
            ooz = 1.0 / z
            xp = int(W / 2 + XFAC * K * ooz * x)
            yp = int(H / 2 - K * ooz * y)
            lum = (cp * ct * sB - cA * ct * sp - sA * st
                   + cB * (cA * st - ct * sA * sp))
            if 0 <= yp < H and 0 <= xp < W and lum > 0:
                if ooz > zbuf[yp][xp]:
                    zbuf[yp][xp] = ooz
                    idx = int(lum * 8)
                    if idx > 11:
                        idx = 11
                    grid[yp][xp] = idx
            phi += PHI_STEP
        theta += THETA_STEP
    return grid


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def frame_svg(grid, frame_index):
    """Emit one <g> holding per-band <text> with column-aligned tspans."""
    delay = -(frame_index * (DURATION_S / N_FRAMES))
    parts = [f'<g class="f" style="animation-delay:{delay:.3f}s">']
    for b, (_hi, color) in enumerate(BANDS):
        tspans = []
        for row in range(H):
            cells = grid[row]
            # build this band's characters for the row
            chars = []
            for col in range(W):
                ri = cells[col]
                chars.append(RAMP[ri] if (ri >= 0 and band_of(ri) == b) else " ")
            # trim to first/last non-space (keep interior spaces)
            first = next((i for i, c in enumerate(chars) if c != " "), None)
            if first is None:
                continue
            last = max(i for i, c in enumerate(chars) if c != " ")
            content = "".join(chars[first:last + 1])
            x = BLOCK_X + first * CHAR_W
            y = BLOCK_Y0 + row * LINE_H
            tlen = len(content) * CHAR_W
            tspans.append(
                f'<tspan x="{x:.1f}" y="{y:.1f}" textLength="{tlen:.1f}" '
                f'lengthAdjust="spacingAndGlyphs">{esc(content)}</tspan>'
            )
        if tspans:
            parts.append(f'<text fill="{color}">{"".join(tspans)}</text>')
    parts.append("</g>")
    return "".join(parts)


def build_svg():
    frames = []
    A, B = 0.0, 0.0
    for i in range(N_FRAMES):
        frames.append(frame_svg(render_frame(A, B), i))
        A += DA
        B += DB

    style = (
        "<style>"
        f"text{{font-family:{FONT};font-size:{FONT_SIZE}px;"
        "white-space:pre;dominant-baseline:middle}}"
        ".f{opacity:0;animation:cyc " + f"{DURATION_S}s" + " linear infinite}"
        "@keyframes cyc{0%,0.83%{opacity:1}0.84%,100%{opacity:0}}"
        "</style>"
    )
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'viewBox="0 0 {VB_W} {VB_H}" role="img" xml:space="preserve">'
        f"<title>Eric Catalano - spinning ASCII donut</title>"
        f"<desc>A 3D torus rendered in ASCII characters, spinning in a "
        f"terminal window.</desc>"
    )
    chrome = (
        f'<rect x="0.5" y="0.5" width="{VB_W - 1}" height="{VB_H - 1}" rx="16" '
        f'fill="#0b1020" stroke="#1e293b" stroke-width="1"/>'
        '<circle cx="28" cy="28" r="6" fill="#ff5f56"/>'
        '<circle cx="48" cy="28" r="6" fill="#ffbd2e"/>'
        '<circle cx="68" cy="28" r="6" fill="#27c93f"/>'
        f'<text x="90" y="32" fill="#64748b" font-size="13">'
        f'~/eric.catalano $ ./render</text>'
        f'<line x1="0" y1="52" x2="{VB_W}" y2="52" stroke="#1e293b" '
        f'stroke-width="1"/>'
    )
    return header + style + chrome + "".join(frames) + "</svg>"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "..", "assets")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.normpath(os.path.join(out_dir, "donut.svg"))
    svg = build_svg()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out_path} ({len(svg) / 1024:.0f} KB, {N_FRAMES} frames)")


if __name__ == "__main__":
    main()
