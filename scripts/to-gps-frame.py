#!/usr/bin/env python3
"""Move a RealityScan solve (original-image XMPs + tie point PLY) into a local metric frame
fitted to the photos' own GPS, by one similarity transform (scale, rotation, shift).

usage: python3 -I to-gps-frame.py <xmp_in> <images_dir> <tiepoints.ply> <out_dir> <lat0> <lon0>

The frame:  x east, y north, in meters, origin at (lat0, lon0) on a local tangent plane;
            z up, in meters above the takeoff point (DJI's RelativeAltitude reference).
The fit:    least-squares similarity (Umeyama) from every solved camera center to its photo's
            GPS position. Nothing inside the solve changes: relative poses, intrinsics and
            distortion are untouched, only the whole model is scaled, rotated and shifted.
Writes <out_dir>/xmp/*.xmp (Position and Rotation rewritten, everything else byte-identical),
<out_dir>/tiepoints.ply, and <out_dir>/frame.txt (the transform and the fit residuals).
"""
import glob, math, os, re, subprocess, sys
import numpy as np

xmp_in, img_dir, ply_in, out_dir, lat0, lon0 = sys.argv[1:7]
lat0, lon0 = float(lat0), float(lon0)
os.makedirs(os.path.join(out_dir, "xmp"), exist_ok=True)
R_EARTH = 6378137.0


def enu(lat, lon, alt):
    return [math.radians(lon - lon0) * R_EARTH * math.cos(math.radians(lat0)),
            math.radians(lat - lat0) * R_EARTH, alt]


exif = {}
out = subprocess.run(["exiftool", "-fast", "-T", "-n", "-FileName", "-GPSLatitude", "-GPSLongitude",
                      "-RelativeAltitude", img_dir], capture_output=True, text=True, check=True).stdout
for line in out.splitlines():
    n, la, lo, ra = line.split("\t")
    exif[n] = enu(float(la), float(lo), float(ra))

xmps = sorted(glob.glob(os.path.join(xmp_in, "*.xmp")))
names, C, G = [], [], []
def find(t, k):
    """RealityScan writes a value either as an attribute (xcr:K="...") or as an element
    (<xcr:K>...</xcr:K>) — the same export uses both. Returns (whole match, value) or None."""
    m = re.search(rf"<xcr:{k}>([^<]+)</xcr:{k}>", t) or re.search(rf'xcr:{k}="([^"]+)"', t)
    return (m.group(0), m.group(1)) if m else None


def put(whole, k, vals):
    v = " ".join(repr(float(x)) for x in vals)
    return f"<xcr:{k}>{v}</xcr:{k}>" if whole.startswith("<") else f'xcr:{k}="{v}"'


def read(p):
    with open(p, newline="") as f:      # keep RealityScan's CRLF line endings
        return f.read()


for p in xmps:
    t = read(p)
    m = find(t, "Position")
    if not m:
        continue
    n = os.path.basename(p)[:-4] + ".JPG"
    names.append(n); C.append([float(v) for v in m[1].split()]); G.append(exif[n])
C, G = np.array(C), np.array(G)

mc, mg = C.mean(0), G.mean(0)
U, S, Vt = np.linalg.svd((G - mg).T @ (C - mc) / len(C))
D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
A = U @ D @ Vt
s = np.trace(np.diag(S) @ D) / (C - mc).var(0).sum()
b = mg - s * A @ mc
res = np.linalg.norm((s * (A @ C.T)).T + b - G, axis=1)
horiz = np.linalg.norm(((s * (A @ C.T)).T + b - G)[:, :2], axis=1)
vert = np.abs(((s * (A @ C.T)).T + b - G)[:, 2])

for p in xmps:
    t = read(p)
    m = find(t, "Position")
    if m:
        Cn = s * A @ np.array([float(v) for v in m[1].split()]) + b
        t = t.replace(m[0], put(m[0], "Position", Cn), 1)
        r = find(t, "Rotation")
        Rn = np.array([float(v) for v in r[1].split()]).reshape(3, 3) @ A.T
        t = t.replace(r[0], put(r[0], "Rotation", Rn.ravel()), 1)
    with open(os.path.join(out_dir, "xmp", os.path.basename(p)), "w", newline="") as f:
        f.write(t)

n = 0
with open(ply_in, "rb") as fi, open(os.path.join(out_dir, "tiepoints.ply"), "wb") as fo:
    while True:
        line = fi.readline(); fo.write(line)
        if line.strip() == b"end_header":
            break
    for line in fi:
        v = line.split()
        X = s * A @ np.array([float(v[0]), float(v[1]), float(v[2])]) + b
        fo.write(b"%.4f %.4f %.4f %s %s %s\n" % (X[0], X[1], X[2], v[3], v[4], v[5])); n += 1

with open(os.path.join(out_dir, "frame.txt"), "w") as f:
    f.write(f"""# Coordinate frame of the published poses and tie points.
#
# x east, y north, in meters, on a local tangent plane with its origin at
#   latitude {lat0:.6f}, longitude {lon0:.6f} (WGS84).
# z up, in meters above the drone's takeoff point (DJI RelativeAltitude), not above sea level.
#
# The frame comes from GPS, not from a measured scale reference. RealityScan solved the photos
# in its own arbitrary units; the whole solve was then fitted to the photos' GPS positions with
# one similarity transform (scale, rotation, shift). The relative geometry of the solve is unchanged.
#
# Fit over {len(C)} solved cameras, solved camera center vs its photo's GPS position:
#   3D residual   median {np.median(res):.2f} m, 95th percentile {np.percentile(res, 95):.2f} m, max {res.max():.2f} m
#   horizontal    median {np.median(horiz):.2f} m
#   vertical      median {np.median(vert):.2f} m
#
# The transform, RealityScan frame -> this frame:  X' = s * A * X + b
s {s!r}
A {' '.join(repr(float(v)) for v in A.ravel())}
b {' '.join(repr(float(v)) for v in b)}
""")
print(f"{len(C)} cameras, {n:,} points; s={s:.6f}; residual median {np.median(res):.2f} m, "
      f"p95 {np.percentile(res, 95):.2f} m, max {res.max():.2f} m (horizontal median {np.median(horiz):.2f}, "
      f"vertical median {np.median(vert):.2f})")
