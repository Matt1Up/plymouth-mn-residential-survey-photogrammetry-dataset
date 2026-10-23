#!/usr/bin/env python3
"""Draw the mission maps in preview/: where every photo was taken, over the scan itself.

usage: python3 scripts/make-mission-maps.py <images.csv> <missions.csv> <points3D.txt> <frame.txt> <out_dir>

  missions-grids.png   the two crosshatched nadir grids
  missions-orbits.png  the large orbit and the ten small ones
  missions-3d.png      all thirteen missions in 3D, above the tie points

Camera positions are each photo's own GPS fix (EXIF), at its height above the takeoff point.
The base map is the dataset's own tie points (poses/colmap/points3D.txt) seen from straight
above: no satellite or map imagery is used. Both are in the frame described in frame.txt
(x east, y north, meters), so north is up and the scale bar is in meters.
Needs numpy, matplotlib and Pillow.
"""
import csv, math, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch

images_csv, missions_csv, points_txt, frame_txt, out_dir = sys.argv[1:6]
os.makedirs(out_dir, exist_ok=True)

# ── colors: three validated categorical slots (dark surface) + neutral ink ──────────────────
PAGE, INK, INK2, MUTED = "#0d0d0d", "#f0efec", "#c3c2b7", "#898781"
COLOR = {"grid-ew": "#3987e5", "grid-ns": "#d95926", "orbit": "#199e70", "orbit-large": INK}
NAME = {"grid-ew": "Grid, east–west lines", "grid-ns": "Grid, north–south lines",
        "orbit": "Small orbits", "orbit-large": "Large orbit"}
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK, "axes.edgecolor": PAGE})

# ── frame origin ────────────────────────────────────────────────────────────────────────────
lat0 = lon0 = None
for line in open(frame_txt):
    if "latitude" in line and "longitude" in line:
        p = line.replace(",", " ").split()
        lat0, lon0 = float(p[p.index("latitude") + 1]), float(p[p.index("longitude") + 1])
K = 6378137.0 * math.pi / 180


def xy(lat, lon):
    return (lon - lon0) * K * math.cos(math.radians(lat0)), (lat - lat0) * K


photos = []
for r in csv.DictReader(open(images_csv)):
    x, y = xy(float(r["lat"]), float(r["lon"]))
    photos.append(dict(name=r["filename"], t=r["datetime"], m=int(r["mission"]), type=r["mission_type"],
                       x=x, y=y, z=float(r["rel_alt_m"]), pitch=float(r["gimbal_pitch"])))
photos.sort(key=lambda p: (p["t"], p["name"]))
missions = list(csv.DictReader(open(missions_csv)))
by_m = {int(m["mission"]): [p for p in photos if p["m"] == int(m["mission"])] for m in missions}

# ── base map from the tie points ────────────────────────────────────────────────────────────
EXT = (-252, 246, -238, 238)            # x0 x1 y0 y1, meters
RES = 0.3
pts = []
with open(points_txt) as f:
    for line in f:
        if line[0] != "#":
            v = line.split()
            pts.append((float(v[1]), float(v[2]), float(v[3]), int(v[4]), int(v[5]), int(v[6])))
P = np.array(pts, dtype=np.float64)
x0, x1, y0, y1 = EXT
keep = (P[:, 0] > x0) & (P[:, 0] < x1) & (P[:, 1] > y0) & (P[:, 1] < y1) & (P[:, 2] > -10) & (P[:, 2] < 45)
Q = P[keep][np.argsort(P[keep][:, 2])]          # low first, so roofs and canopy draw on top
H, W = int((y1 - y0) / RES), int((x1 - x0) / RES)
base = np.zeros((H, W, 3), np.float32)
ii = ((y1 - Q[:, 1]) / RES).astype(int); jj = ((Q[:, 0] - x0) / RES).astype(int)
for di in (0, 1):                               # splat each point 2 x 2 px to close the gaps
    for dj in (0, 1):
        a, b = np.clip(ii + di, 0, H - 1), np.clip(jj + dj, 0, W - 1)
        base[a, b] = Q[:, 3:6] / 255.0
gray = base.mean(2, keepdims=True)
base_dim = (0.55 * base + 0.45 * gray) * 0.62   # desaturate and darken so the flight paths lead


def frame_axes(fig, rect):
    ax = fig.add_axes(rect)
    ax.imshow(base_dim, extent=EXT, origin="upper", interpolation="bilinear")
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.axis("off")
    # scale bar + north arrow
    sx, sy = x0 + 14, y0 + 14
    ax.plot([sx, sx + 100], [sy, sy], color=INK, lw=2.5, solid_capstyle="butt")
    for t in (0, 50, 100):
        ax.plot([sx + t, sx + t], [sy, sy + 4], color=INK, lw=1.5)
    ax.text(sx + 50, sy + 7, "100 m", ha="center", va="bottom", fontsize=14, color=INK)
    ax.annotate("", xy=(x1 - 22, y1 - 14), xytext=(x1 - 22, y1 - 44),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=2, mutation_scale=18))
    ax.text(x1 - 22, y1 - 52, "N", ha="center", va="top", fontsize=16, color=INK, weight="bold")
    return ax


# Sized for a README, where the image is shown about 900 px wide: no text below ~11 px there.
def side_panel(fig, title, subtitle, legend, foot):
    ax = fig.add_axes([0.625, 0.04, 0.36, 0.92]); ax.axis("off")
    ax.text(0, 1, title, fontsize=27, weight="bold", va="top", color=INK, transform=ax.transAxes, linespacing=1.15)
    ax.text(0, 0.86, subtitle, fontsize=15, va="top", color=INK2, transform=ax.transAxes, linespacing=1.5)
    y = 0.69
    for handle, label, stats in legend:
        if "markers" in handle:
            for (mx, mk) in handle["markers"]:
                ax.plot([mx], [y], transform=ax.transAxes, marker=mk, markersize=13, color=MUTED,
                        markeredgecolor=INK, markeredgewidth=2, linestyle="none", clip_on=False)
        else:
            ax.add_line(Line2D([0.0, 0.08], [y, y], transform=ax.transAxes, **handle))
        ax.text(0.12, y, label, fontsize=17, weight="bold", va="center", color=INK, transform=ax.transAxes)
        for k, s in enumerate(stats):
            ax.text(0.12, y - 0.055 - 0.045 * k, s, fontsize=14.5, va="center", color=INK2, transform=ax.transAxes)
        y -= 0.10 + 0.045 * len(stats)
    ax.text(0, 0.0, foot, fontsize=12.5, va="bottom", color=MUTED, transform=ax.transAxes, linespacing=1.5)


def arrow_along(ax, ps, k, color, size=16):
    a, b = ps[k], ps[min(k + 2, len(ps) - 1)]
    ax.add_patch(FancyArrowPatch((a["x"], a["y"]), (b["x"], b["y"]), arrowstyle="-|>",
                                 mutation_scale=size, color=color, lw=0, zorder=6))


FOOT = ("Positions: each photo's GPS fix. Base map: the dataset's\n"
        "own 3.9 million tie points from straight above.")
DPI = 160
FIG = (16, 9)
mrow = {int(m["mission"]): m for m in missions}

# ── 1 · grids ───────────────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=FIG, dpi=DPI, facecolor=PAGE)
ax = frame_axes(fig, [0.005, 0.02, 0.60, 0.96])
for n, z in ((12, 3), (13, 4)):
    ps = by_m[n]; c = COLOR[ps[0]["type"]]
    ax.plot([p["x"] for p in ps], [p["y"] for p in ps], color=c, lw=2.0, alpha=0.95, zorder=z)
    ax.scatter([p["x"] for p in ps], [p["y"] for p in ps], s=13, color=c, edgecolors=PAGE, linewidths=0.6, zorder=z + 0.5)
    ax.scatter([ps[0]["x"]], [ps[0]["y"]], s=150, marker="o", color=c, edgecolors=INK, linewidths=2, zorder=8)
    ax.scatter([ps[-1]["x"]], [ps[-1]["y"]], s=150, marker="s", color=c, edgecolors=INK, linewidths=2, zorder=8)
    for k in range(5, len(ps) - 3, 26):
        arrow_along(ax, ps, k, INK, 14)
legend = []
for n in (12, 13):
    m = mrow[n]
    legend.append((dict(color=COLOR[m["type"]], lw=5), f"{n} · {NAME[m['type']]}",
                   [f"{m['photos']} photos · {m['start'][:5]}–{m['end'][:5]} · battery {m['battery']}",
                    f"{m['lines']} lines, {round(float(m['line_spacing_m']))} m apart · photo every {m['photo_spacing_m']} m"]))
legend.append((dict(markers=[(0.015, "o"), (0.065, "s")]), "Start  ·  end",
               ["white arrows: direction of flight"]))
side_panel(fig, "Two nadir grids,\ncrosshatched",
           "60 m above takeoff, camera straight down.\nThe second grid turned 90°: 708 photos.",
           legend, FOOT)
fig.savefig(os.path.join(out_dir, "missions-grids.png"), facecolor=PAGE, dpi=DPI)
plt.close(fig)

# ── 2 · orbits ──────────────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=FIG, dpi=DPI, facecolor=PAGE)
ax = frame_axes(fig, [0.005, 0.02, 0.60, 0.96])
ps = by_m[1]
ax.plot([p["x"] for p in ps] + [ps[0]["x"]], [p["y"] for p in ps] + [ps[0]["y"]], color=INK, lw=2.2, ls=(0, (6, 4)), zorder=3)
ax.scatter([p["x"] for p in ps], [p["y"] for p in ps], s=16, color=INK, edgecolors=PAGE, linewidths=0.6, zorder=4)
for k in range(10, len(ps) - 3, 30):
    arrow_along(ax, ps, k, INK, 18)
ax.text(ps[len(ps) // 8]["x"] + 8, ps[len(ps) // 8]["y"] + 8, "1", fontsize=15, weight="bold", color=PAGE,
        ha="center", va="center", zorder=9, bbox=dict(boxstyle="circle,pad=0.35", fc=INK, ec=PAGE, lw=1.5))
c = COLOR["orbit"]
for n in range(2, 12):
    ps = by_m[n]
    ax.plot([p["x"] for p in ps] + [ps[0]["x"]], [p["y"] for p in ps] + [ps[0]["y"]], color=c, lw=1.8, alpha=0.9, zorder=5)
    ax.scatter([p["x"] for p in ps], [p["y"] for p in ps], s=10, color=c, edgecolors=PAGE, linewidths=0.5, zorder=5.5)
    arrow_along(ax, ps, len(ps) // 2, c, 20)
    cx, cy = float(np.mean([p["x"] for p in ps])), float(np.mean([p["y"] for p in ps]))
    ax.text(cx, cy, str(n), fontsize=15, weight="bold", color=INK, ha="center", va="center", zorder=9,
            bbox=dict(boxstyle="circle,pad=0.35", fc=c, ec=PAGE, lw=1.5))
m1 = mrow[1]
small = [mrow[n] for n in range(2, 12)]
legend = [
    (dict(color=INK, lw=3, ls=(0, (3, 2))), "1 · Large orbit",
     [f"{m1['photos']} photos · radius {round(float(m1['radius_m']))} m",
      f"{round(float(m1['rel_alt_m']))} m above takeoff · −45° · every {m1['deg_per_photo']}°"]),
    (dict(color=c, lw=5), "2–11 · Small orbits",
     [f"{sum(int(m['photos']) for m in small)} photos · radius {round(float(small[0]['radius_m']))} m · 58–60 each",
      f"{round(float(small[0]['rel_alt_m']))} m above takeoff · −40° · every 6°"]),
]
side_panel(fig, "One large orbit,\nten small ones",
           "All eleven clockwise, camera tilted to the\ncenter: every part seen from all sides.",
           legend, FOOT)
fig.savefig(os.path.join(out_dir, "missions-orbits.png"), facecolor=PAGE, dpi=DPI)
plt.close(fig)

# ── 3 · all thirteen in 3D ──────────────────────────────────────────────────────────────────
rng = np.random.default_rng(0)
sub = Q[rng.choice(len(Q), size=min(450_000, len(Q)), replace=False)]
fig = plt.figure(figsize=FIG, dpi=DPI, facecolor=PAGE)
ax = fig.add_axes([0.0, -0.12, 0.66, 1.24], projection="3d", facecolor=PAGE)
ax.scatter(sub[:, 0], sub[:, 1], sub[:, 2], c=np.clip(sub[:, 3:6] / 255.0 * 1.1, 0, 1), s=1.1, linewidths=0, depthshade=False)
for n in range(1, 14):
    ps = by_m[n]; t = ps[0]["type"]; col = COLOR[t]
    X = [p["x"] for p in ps]; Y = [p["y"] for p in ps]; Z = [p["z"] for p in ps]
    if t.startswith("orbit"):
        X, Y, Z = X + X[:1], Y + Y[:1], Z + Z[:1]
    ax.plot(X, Y, Z, color=col, lw=1.6 if t == "orbit" else 1.8, ls=(0, (6, 4)) if t == "orbit-large" else "-")
    ax.scatter([p["x"] for p in ps], [p["y"] for p in ps], [p["z"] for p in ps], color=col, s=7, depthshade=False)
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_zlim(-5, 75)
ax.set_box_aspect((x1 - x0, y1 - y0, 80 * 1.6), zoom=1.22)
ax.view_init(elev=27, azim=-58)
ax.set_axis_off()
legend = [
    (dict(color=INK, lw=3, ls=(0, (3, 2))), "Large orbit · 60 m", ["mission 1 · 123 photos · −45°"]),
    (dict(color=COLOR["orbit"], lw=5), "Small orbits · 40 m", ["missions 2–11 · 590 photos · −40°"]),
    (dict(color=COLOR["grid-ew"], lw=5), "Grid, east–west · 60 m", ["mission 12 · 354 photos · −90°"]),
    (dict(color=COLOR["grid-ns"], lw=5), "Grid, north–south · 60 m", ["mission 13 · 354 photos · −90°"]),
]
side_panel(fig, "Thirteen missions,\nfour batteries",
           "1,421 photos in 90 minutes, all on waypoints.\nHeight above takeoff, drawn ×1.6.",
           legend,
           "Positions: each photo's GPS fix. Ground: 450,000\nof the dataset's 3.9 million tie points.")
fig.savefig(os.path.join(out_dir, "missions-3d.png"), facecolor=PAGE, dpi=DPI)
plt.close(fig)
print("wrote", ", ".join(f for f in sorted(os.listdir(out_dir)) if f.startswith("missions-")))
