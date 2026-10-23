#!/usr/bin/env python3
"""Convert RealityScan XMP sidecars for the ORIGINAL images to COLMAP sparse text format.

Usage: scripts/xmp-to-colmap.py <xmp_dir> <images_dir> <tiepoints.ply> <out_dir>

Writes cameras.txt, images.txt, points3D.txt.

The XMPs must be the ones RealityScan writes for the original (distorted) images, one per photo
and named after it (DJI_..._D.xmp next to DJI_..._D.JPG) — exported headless with
    -set calexExportUndistorted=false -set calexExportImages=false -exportXMPForSelectedComponent
An XMP written for undistorted copies (zero distortion, 00000.xmp ... numbered) describes a
different, cropped image, and this script refuses it.

Conversion, one camera per image (RealityScan solved each photo's calibration on its own):
  model       FULL_OPENCV — RealityScan's brown3 radial model k1 k2 k3 maps onto it with k4..k6 = 0;
              tangential t1 t2 map to OpenCV p2 p1 (the order RealityScan's own OpenCV export uses)
  focal       FocalLength35mm * max(W, H) / 36
  principal   W/2 + PrincipalPointU * max(W, H),  H/2 + PrincipalPointV * max(W, H)
              (pixel edges at 0 and W, which is COLMAP's convention too)
  pose        COLMAP R = xcr:Rotation, t = -R * xcr:Position
points3D.txt carries position and color only; the export has no 2D tracks.
"""
import glob, math, os, re, sys
import numpy as np
from PIL import Image

xmp_dir, img_dir, ply_path, out_dir = sys.argv[1:5]
os.makedirs(out_dir, exist_ok=True)


def tag(t, k):
    m = re.search(rf"<xcr:{k}>([^<]+)</xcr:{k}>", t) or re.search(rf'xcr:{k}="([^"]+)"', t)
    return m.group(1) if m else None


on_disk = {os.path.splitext(f)[0]: f for f in os.listdir(img_dir) if f.lower().endswith(".jpg")}
cams, skipped = [], []
for p in sorted(glob.glob(os.path.join(xmp_dir, "*.xmp"))):
    stem = os.path.basename(p)[:-4]
    t = open(p).read()
    if stem not in on_disk:
        sys.exit(f"{os.path.basename(p)} has no image of the same name — not a per-image sidecar export")
    if tag(t, "Rotation") is None:
        skipped.append(stem); continue
    k = [float(v) for v in tag(t, "DistortionCoeficients").split()]
    model = tag(t, "DistortionModel")
    if model not in ("brown3", "brown3t2") or (len(k) > 3 and k[3] != 0):
        sys.exit(f"{stem}: distortion model {model} {k} has no exact FULL_OPENCV equivalent")
    if model == "brown3" and not any(k):
        sys.exit(f"{stem}: zero distortion — this looks like an export for undistorted images")
    name = on_disk[stem]
    with Image.open(os.path.join(img_dir, name)) as im:
        W, H = im.size
    L = max(W, H)
    f = float(tag(t, "FocalLength35mm")) * L / 36.0
    cx = W / 2.0 + float(tag(t, "PrincipalPointU")) * L
    cy = H / 2.0 + float(tag(t, "PrincipalPointV")) * L
    t1, t2 = (k[4], k[5]) if len(k) >= 6 else (0.0, 0.0)
    R = np.array([float(v) for v in tag(t, "Rotation").split()]).reshape(3, 3)
    C = np.array([float(v) for v in tag(t, "Position").split()])
    cams.append(dict(name=name, W=W, H=H, f=f, cx=cx, cy=cy, k1=k[0], k2=k[1], k3=k[2], p1=t2, p2=t1, R=R, C=C))
print(f"{len(cams)} cameras" + (f", {len(skipped)} XMPs without a pose skipped" if skipped else ""))


def quat(R):
    tr = np.trace(R)
    if tr > 0:
        S = math.sqrt(tr + 1.0) * 2; w = 0.25 * S
        x = (R[2, 1] - R[1, 2]) / S; y = (R[0, 2] - R[2, 0]) / S; z = (R[1, 0] - R[0, 1]) / S
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        S = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / S; x = 0.25 * S; y = (R[0, 1] + R[1, 0]) / S; z = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / S; x = (R[0, 1] + R[1, 0]) / S; y = 0.25 * S; z = (R[1, 2] + R[2, 1]) / S
    else:
        S = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / S; x = (R[0, 2] + R[2, 0]) / S; y = (R[1, 2] + R[2, 1]) / S; z = 0.25 * S
    return w, x, y, z


with open(os.path.join(out_dir, "cameras.txt"), "w") as fc, open(os.path.join(out_dir, "images.txt"), "w") as fi:
    fc.write("# Camera list with one line of data per camera:\n#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
    fc.write("# FULL_OPENCV params: fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6\n")
    fi.write("# Image list with two lines of data per image:\n#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
    for i, c in enumerate(cams, 1):
        fc.write(f"{i} FULL_OPENCV {c['W']} {c['H']} {c['f']:.6f} {c['f']:.6f} {c['cx']:.6f} {c['cy']:.6f} "
                 f"{c['k1']:.12g} {c['k2']:.12g} {c['p1']:.12g} {c['p2']:.12g} {c['k3']:.12g} 0 0 0\n")
        t = -c["R"] @ c["C"]
        qw, qx, qy, qz = quat(c["R"])
        fi.write(f"{i} {qw:.12f} {qx:.12f} {qy:.12f} {qz:.12f} {t[0]:.9f} {t[1]:.9f} {t[2]:.9f} {i} {c['name']}\n\n")

n = 0
with open(ply_path, "rb") as fh, open(os.path.join(out_dir, "points3D.txt"), "w") as fp:
    props, N = [], 0
    while True:
        line = fh.readline().decode("ascii", "replace").strip()
        if line.startswith("element vertex"): N = int(line.split()[-1])
        if line.startswith("property"): props.append(line.split()[-1])
        if line == "end_header": break
    ix = [props.index(k) for k in ("x", "y", "z", "red", "green", "blue")]
    fp.write("# 3D point list with one line of data per point:\n#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n")
    for _ in range(N):
        v = fh.readline().split()
        n += 1
        fp.write(f"{n} {v[ix[0]].decode()} {v[ix[1]].decode()} {v[ix[2]].decode()} {v[ix[3]].decode()} {v[ix[4]].decode()} {v[ix[5]].decode()} 0\n")
print(f"wrote {out_dir}/cameras.txt images.txt points3D.txt — {len(cams)} cameras, {n:,} points")
