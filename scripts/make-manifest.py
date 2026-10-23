#!/usr/bin/env python3
"""Build manifest/<scan>/images.csv, checksums.sha256, missions.csv and summary.json from an
image directory.

Usage:  scripts/make-manifest.py <images_dir> <scan> --missions <list> [--repo <root>]

Columns: filename, battery, mission, mission_type, bytes, sha256, width, height, datetime,
         lat, lon, alt_m, rel_alt_m, gimbal_pitch, gimbal_yaw, gps_valid

  battery       numbered from 1 in capture order. A new battery starts when two consecutive
                frames are more than 120 s apart (a swap took about 3.5 minutes; within a
                battery, missions are 40-60 s apart).
  mission       the waypoint mission, numbered from 1 in capture order. A new mission starts
                when two consecutive frames are more than 15 s apart (a mission shoots every
                3-12 s).
  mission_type  from --missions: a text file, "<mission number> <type>" per line, '#' lines are
                comments. It must name exactly the missions the time gaps find.
  rel_alt_m     height above the takeoff point (DJI RelativeAltitude), not above the ground.
  gps_valid     false for null-island (0,0) fixes and for missing coordinates.

missions.csv has one row per mission: type, battery, photos, first and last frame and time,
height above takeoff, gimbal pitch range, and the orbit center and radius or the grid's line
heading, line spacing and photo spacing, in meters on a local plane around the mission.

Checksum paths are '<scan>/images/<name>', the same paths the files have on Hugging Face, so
scripts/verify.sh can check a download without rewriting anything.
"""
import argparse, csv, hashlib, json, math, os, statistics, subprocess, sys
from datetime import datetime

ap = argparse.ArgumentParser()
ap.add_argument("images_dir")
ap.add_argument("scan")
ap.add_argument("--missions", required=True)
ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = ap.parse_args()

img_dir = os.path.abspath(a.images_dir)
out = os.path.join(a.repo, "manifest", a.scan)
os.makedirs(out, exist_ok=True)

files = sorted(f for f in os.listdir(img_dir) if f.lower().endswith(".jpg"))
if not files:
    sys.exit(f"no .jpg found in {img_dir}")
print(f"{len(files)} images in {img_dir}")

types = {}
for line in open(a.missions):
    line = line.strip()
    if line and not line.startswith("#"):
        n, t = line.split(None, 1)
        types[int(n)] = t

print("reading EXIF ...")
proc = subprocess.run(
    ["exiftool", "-q", "-q", "-m", "-n", "-json",
     "-FileName", "-ImageWidth", "-ImageHeight", "-DateTimeOriginal",
     "-GPSLatitude", "-GPSLongitude", "-GPSAltitude", "-GPSLatitudeRef", "-GPSLongitudeRef",
     "-RelativeAltitude", "-GimbalPitchDegree", "-GimbalYawDegree", img_dir],
    capture_output=True, text=True)
meta = {r.get("FileName", ""): r for r in json.loads(proc.stdout or "[]")}


def signed(val, ref, negative_ref):
    """exiftool -n returns an UNSIGNED magnitude; the hemisphere lives in a separate Ref tag.
    Without this, every western longitude comes out positive."""
    if val in (None, ""):
        return ""
    v = abs(float(val))
    if str(ref).strip().upper().startswith(negative_ref):
        v = -v
    return v


# Capture order is time order. DJI frame numbers wrap (0999 -> 0001), so sort on the timestamp,
# then the full filename, never on the frame number.
order = sorted(files, key=lambda n: (meta[n]["DateTimeOriginal"], n))
rows, last_t, battery, mission = {}, None, 0, 0
for name in order:
    m = meta[name]
    t = datetime.strptime(m["DateTimeOriginal"], "%Y:%m:%d %H:%M:%S")
    gap = None if last_t is None else (t - last_t).total_seconds()
    if gap is None or gap > 120:
        battery += 1
    if gap is None or gap > 15:
        mission += 1
    last_t = t
    lat = signed(m.get("GPSLatitude"), m.get("GPSLatitudeRef"), "S")
    lon = signed(m.get("GPSLongitude"), m.get("GPSLongitudeRef"), "W")
    valid = lat != "" and lon != "" and float(lat) != 0.0 and float(lon) != 0.0
    rows[name] = {
        "filename": name, "battery": battery, "mission": mission, "mission_type": "",
        "bytes": 0, "sha256": "",
        "width": m.get("ImageWidth", ""), "height": m.get("ImageHeight", ""),
        "datetime": m.get("DateTimeOriginal", ""), "lat": lat, "lon": lon,
        "alt_m": m.get("GPSAltitude", ""), "rel_alt_m": m.get("RelativeAltitude", ""),
        "gimbal_pitch": m.get("GimbalPitchDegree", ""), "gimbal_yaw": m.get("GimbalYawDegree", ""),
        "gps_valid": "true" if valid else "false",
    }
if sorted(types) != list(range(1, mission + 1)):
    sys.exit(f"the time gaps find {mission} missions; --missions names {sorted(types)}")
for r in rows.values():
    r["mission_type"] = types[r["mission"]]

sums = []
for i, name in enumerate(files, 1):
    path = os.path.join(img_dir, name)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    rows[name]["bytes"] = os.path.getsize(path)
    rows[name]["sha256"] = h.hexdigest()
    sums.append(f"{h.hexdigest()}  {a.scan}/images/{name}")
    if i % 250 == 0 or i == len(files):
        print(f"  hashed {i}/{len(files)}")

cols = list(next(iter(rows.values())).keys())
with open(os.path.join(out, "images.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(rows[n] for n in files)
with open(os.path.join(out, "checksums.sha256"), "w") as fh:
    fh.write("\n".join(sums) + "\n")


# ── one row per mission ─────────────────────────────────────────────────────────────────────
def local_xy(rs):
    lat0 = statistics.fmean(float(r["lat"]) for r in rs)
    lon0 = statistics.fmean(float(r["lon"]) for r in rs)
    k = 6378137.0 * math.pi / 180
    return [((float(r["lon"]) - lon0) * k * math.cos(math.radians(lat0)), (float(r["lat"]) - lat0) * k) for r in rs]


missions = []
for n in range(1, mission + 1):
    rs = [rows[name] for name in order if rows[name]["mission"] == n]
    xy = local_xy(rs)
    pitch = [float(r["gimbal_pitch"]) for r in rs]
    alt = [float(r["rel_alt_m"]) for r in rs]
    row = {"mission": n, "type": types[n], "battery": rs[0]["battery"], "photos": len(rs),
           "first": rs[0]["filename"], "last": rs[-1]["filename"],
           "start": rs[0]["datetime"].split(" ")[1], "end": rs[-1]["datetime"].split(" ")[1],
           "rel_alt_m": round(statistics.median(alt), 1),
           "gimbal_pitch": f"{min(pitch):g}..{max(pitch):g}" if min(pitch) != max(pitch) else f"{pitch[0]:g}",
           "center_lat": "", "center_lon": "", "radius_m": "", "deg_per_photo": "", "direction": "",
           "line_heading_deg": "", "lines": "", "line_spacing_m": "", "photo_spacing_m": ""}
    if types[n].startswith("orbit"):
        row["center_lat"] = round(statistics.fmean(float(r["lat"]) for r in rs), 6)
        row["center_lon"] = round(statistics.fmean(float(r["lon"]) for r in rs), 6)
        row["radius_m"] = round(statistics.median(math.hypot(x, y) for x, y in xy), 1)
        ang = [math.atan2(y, x) for x, y in xy]
        swept = sum((b - c + math.pi) % (2 * math.pi) - math.pi for c, b in zip(ang, ang[1:]))
        row["deg_per_photo"] = round(abs(math.degrees(swept)) / (len(rs) - 1), 1)
        row["direction"] = "clockwise" if swept < 0 else "counterclockwise"
    else:
        # flight lines = runs of photos whose step heading stays within 30 degrees
        hd = lambda p, q: math.degrees(math.atan2(q[0] - p[0], q[1] - p[1])) % 360
        lines = [[xy[0], xy[1]]]
        for p, q in zip(xy[1:], xy[2:]):
            if abs((hd(p, q) - hd(lines[-1][-2], lines[-1][-1]) + 180) % 360 - 180) > 30:
                lines.append([p])
            lines[-1].append(q)
        long_lines = [l for l in lines if len(l) >= 10]
        h0 = round(hd(long_lines[0][0], long_lines[0][-1]) % 180)
        nx, ny = math.cos(math.radians(h0)), -math.sin(math.radians(h0))
        offs = sorted(statistics.fmean(x * nx + y * ny for x, y in l) for l in long_lines)
        steps = [math.hypot(q[0] - p[0], q[1] - p[1]) for l in long_lines for p, q in zip(l, l[1:])]
        row["line_heading_deg"] = f"{h0}/{h0 + 180}"
        row["lines"] = len(long_lines)
        row["line_spacing_m"] = round(statistics.median(b - c for c, b in zip(offs, offs[1:])), 1)
        row["photo_spacing_m"] = round(statistics.median(steps), 1)
    missions.append(row)
with open(os.path.join(out, "missions.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(missions[0].keys()))
    w.writeheader()
    w.writerows(missions)

total = sum(r["bytes"] for r in rows.values())
batteries = {}
for name in order:
    r = rows[name]
    b = batteries.setdefault(str(r["battery"]), {"images": 0, "missions": [], "first": r["datetime"]})
    b["images"] += 1
    b["last"] = r["datetime"]
    if r["mission"] not in b["missions"]:
        b["missions"].append(r["mission"])
summary = {
    "images": len(rows), "bytes": total, "gb": round(total / 1e9, 2),
    "gps_invalid": sum(1 for r in rows.values() if r["gps_valid"] == "false"),
    "camera_originals": len(rows),
    "missions": {str(m["mission"]): {"type": m["type"], "photos": m["photos"]} for m in missions},
    "batteries": batteries,
}
with open(os.path.join(out, "summary.json"), "w") as fh:
    json.dump(summary, fh, indent=2)
    fh.write("\n")
print(json.dumps(summary, indent=2))
