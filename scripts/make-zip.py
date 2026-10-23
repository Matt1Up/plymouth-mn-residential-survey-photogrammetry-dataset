#!/usr/bin/env python3
"""Build the one-file download: every image in a single stored (uncompressed) ZIP64 archive.

Usage:  scripts/make-zip.py <images_dir> <out.zip> <top_folder> [--manifest manifest/<scan>/images.csv]

  · STORED, not deflated. JPEG is already compressed: deflate saved 0.77 % on 20 evenly spaced
    images from this set, for CPU on both ends. The bytes inside are the original files, copied,
    never re-encoded.
  · Every image from the manifest, in sorted filename order (which is capture order), under one
    top folder, so unzipping makes one directory.
  · ZIP64, because the archive is far larger than 4 GiB.
  · Each entry is stamped with its capture time (DateTimeOriginal, from the manifest; a ZIP keeps
    time in 2-second steps, so an odd second reads one second early) and mode
    0644, so building it again from the same images gives the same bytes.
  · Refuses to finish if the image set does not match the manifest, or if any file's SHA-256
    differs from the manifest while it is being copied.
"""
import argparse, csv, hashlib, os, sys, zipfile

ap = argparse.ArgumentParser()
ap.add_argument("images_dir")
ap.add_argument("out")
ap.add_argument("top")
ap.add_argument("--manifest", required=True)
a = ap.parse_args()

rows = sorted(csv.DictReader(open(a.manifest)), key=lambda r: r["filename"])
on_disk = sorted(f for f in os.listdir(a.images_dir) if f.lower().endswith(".jpg"))
if [r["filename"] for r in rows] != on_disk:
    sys.exit("the images directory and the manifest do not list the same files")

tmp = a.out + ".partial"
total = 0
with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
    for i, r in enumerate(rows, 1):
        path = os.path.join(a.images_dir, r["filename"])
        d, t = r["datetime"].split(" ")
        info = zipfile.ZipInfo(f"{a.top}/{r['filename']}",
                               date_time=tuple(int(x) for x in d.split(":") + t.split(":")))
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3                      # Unix, so the mode below is honoured
        info.external_attr = 0o100644 << 16
        info.file_size = os.path.getsize(path)
        h = hashlib.sha256()
        with open(path, "rb") as src, zf.open(info, "w") as dst:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                h.update(chunk)
                dst.write(chunk)
        if h.hexdigest() != r["sha256"]:
            sys.exit(f"{r['filename']}: SHA-256 differs from the manifest — refusing to build")
        total += info.file_size
        if i % 250 == 0 or i == len(rows):
            print(f"  {i}/{len(rows)}  {total/1e9:.2f} GB")
os.replace(tmp, a.out)

h = hashlib.sha256()
with open(a.out, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 24), b""):
        h.update(chunk)
size = os.path.getsize(a.out)
print(f"\n{a.out}\n  {len(rows)} images, {size:,} bytes ({size/1e9:.2f} GB)\n  sha256 {h.hexdigest()}")
