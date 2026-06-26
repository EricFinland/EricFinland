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
# Grid is intentionally larger than the donut so the zoom/breathing pulse has
# room to grow without clipping the edges. The final SVG is cropped tight to
# the donut's actual extent, so the extra margin costs nothing in the output.
W, H = 96, 34
RAMP = ".,-~:;=!*#$@"          # 12 brightness levels, dim -> bright
K = 15.0                        # projection scale (distance scaling)
XFAC = 1.6                      # horizontal stretch so the torus reads as round
THETA_STEP = 0.07
PHI_STEP = 0.02

# --- animation ---
N_FRAMES = 180
DURATION_S = 9.0                # full loop length
A_TURNS = 3                     # net full turns on the A axis over one loop
B_TURNS = 2                     # net full turns on the B axis over one loop

# Pace envelope: a periodic "how fast is the clock right now" curve. The frame
# loop advances the animation phase by this pace each frame instead of a fixed
# step, so the whole donut eases into slow drift and back to full-speed tumble.
# Each term is (frequency, amplitude, phase); keep total amplitude < 1 so the
# pace never hits zero (the phase must keep moving forward). Because the curve
# is periodic, the slow/fast rhythm loops seamlessly too.
PACE = [(1, 0.62, 0.0), (2, 0.22, 2.1)]


def pace(t):
    """Return the relative clock speed at loop fraction t (always > 0)."""
    p = 1.0
    for f, amp, ph in PACE:
        p += amp * math.sin(2 * math.pi * f * t + ph)
    return p

# Wiggle terms layered on the steady turns to make the tumble feel random and
# jiggly. Each is (frequency, amplitude_radians, phase). Frequencies are whole
# numbers on purpose: integer-frequency sines (and their derivatives) return to
# the same value at t=0 and t=1, so orientation AND speed match exactly at the
# loop seam -- the motion looks chaotic but loops with no jump or stutter.
A_WIGGLE = [(1, 0.85, 0.0), (2, 0.55, 1.3), (3, 0.40, 3.0), (5, 0.30, 2.1)]
B_WIGGLE = [(1, 0.90, 0.7), (2, 0.60, 2.4), (4, 0.45, 0.5), (7, 0.22, 4.0)]


def spin_angles(t):
    """Return (A, B) tumble angles at loop fraction t in [0, 1)."""
    a = 2 * math.pi * A_TURNS * t
    for f, amp, ph in A_WIGGLE:
        a += amp * math.sin(2 * math.pi * f * t + ph)
    b = 2 * math.pi * B_TURNS * t
    for f, amp, ph in B_WIGGLE:
        b += amp * math.sin(2 * math.pi * f * t + ph)
    return a, b


# Breathing zoom: a gentle scale pulse on top of the spin. Whole-number
# frequencies keep it seamless at the loop seam (same as the wiggle). Keep the
# total amplitude modest so the zoomed-in donut still fits the padded grid.
ZOOM = [(2, 0.085, 0.0), (3, 0.045, 1.6)]


def zoom_at(t):
    """Return the projection-scale multiplier at loop fraction t."""
    z = 1.0
    for f, amp, ph in ZOOM:
        z += amp * math.sin(2 * math.pi * f * t + ph)
    return z


# --- layout (SVG units) ---
CHAR_W = 7.5
LINE_H = 13.7
FONT_SIZE = 13
BLOCK_X = 30                           # text origin x (final SVG is cropped)
BLOCK_Y0 = 40                          # first baseline (final SVG is cropped)
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


def render_frame(A, B, zoom=1.0):
    """Return a 2D list [row][col] of ramp indices, or -1 for empty cells."""
    grid = [[-1] * W for _ in range(H)]
    zbuf = [[0.0] * W for _ in range(H)]
    cA, sA = math.cos(A), math.sin(A)
    cB, sB = math.cos(B), math.sin(B)
    Kz = K * zoom                   # breathing zoom scales the projection

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
            xp = int(W / 2 + XFAC * Kz * ooz * x)
            yp = int(H / 2 - Kz * ooz * y)
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
    """Emit one <g> holding per-band <text> with column-aligned tspans.

    Visibility is driven by a SMIL <animate> on opacity (not CSS keyframes):
    GitHub serves README SVGs through an image proxy that runs SMIL but not
    CSS animation, so each frame toggles opacity 0->1 only during its slice.
    """
    a = frame_index / N_FRAMES
    b_end = (frame_index + 1) / N_FRAMES
    if frame_index == 0:
        values, keytimes = "1;1;0;0", f"0;{b_end:.5f};{b_end:.5f};1"
    elif frame_index == N_FRAMES - 1:
        values, keytimes = "0;0;1;1", f"0;{a:.5f};{a:.5f};1"
    else:
        values = "0;0;1;1;0;0"
        keytimes = f"0;{a:.5f};{a:.5f};{b_end:.5f};{b_end:.5f};1"
    anim = (
        f'<animate attributeName="opacity" dur="{DURATION_S}s" '
        f'repeatCount="indefinite" calcMode="linear" '
        f'values="{values}" keyTimes="{keytimes}"/>'
    )
    parts = [f'<g opacity="0">{anim}']
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
    # render every frame's grid first so we can crop the canvas tight to the
    # donut (no terminal frame, transparent background, floating shape)
    # Warp the clock: each frame advances the phase by the local pace, so slow
    # stretches spend many frames covering little motion and fast stretches fewer.
    paces = [pace(i / N_FRAMES) for i in range(N_FRAMES)]
    total = sum(paces)
    grids = []
    cum = 0.0
    for i in range(N_FRAMES):
        tau = cum / total           # warped loop phase in [0, 1)
        cum += paces[i]
        a, b = spin_angles(tau)
        grids.append(render_frame(a, b, zoom_at(tau)))

    min_c, max_c, min_r, max_r = W, -1, H, -1
    for g in grids:
        for r in range(H):
            row = g[r]
            for c in range(W):
                if row[c] >= 0:
                    if c < min_c:
                        min_c = c
                    if c > max_c:
                        max_c = c
                    if r < min_r:
                        min_r = r
                    if r > max_r:
                        max_r = r

    pad = 14
    vb_x = BLOCK_X + min_c * CHAR_W - pad
    vb_w = (max_c - min_c + 1) * CHAR_W + 2 * pad
    vb_y = BLOCK_Y0 + min_r * LINE_H - FONT_SIZE - pad
    vb_h = (max_r - min_r) * LINE_H + 2 * FONT_SIZE + 2 * pad

    frames = [frame_svg(grids[i], i) for i in range(N_FRAMES)]

    style = (
        "<style>"
        f"text{{font-family:{FONT};font-size:{FONT_SIZE}px;"
        "white-space:pre;dominant-baseline:middle}"
        "</style>"
    )
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'viewBox="{vb_x:.1f} {vb_y:.1f} {vb_w:.1f} {vb_h:.1f}" '
        f'role="img" xml:space="preserve">'
        f"<title>Eric Catalano - spinning ASCII donut</title>"
        f"<desc>A 3D torus rendered in ASCII characters, spinning.</desc>"
    )
    return header + style + "".join(frames) + "</svg>"


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
