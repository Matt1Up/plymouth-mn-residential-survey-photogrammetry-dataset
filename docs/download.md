# Downloading

Images, the ZIP and the tie points are hosted on Hugging Face, not GitHub — this repo holds
documentation, manifests, checksums and the small pose files.

**→ https://huggingface.co/datasets/Matt1up/plymouth-mn-residential-survey-photogrammetry**

```
survey/images/      1,421 images                    16.23 GB
zip/                the same 1,421, one file        16.23 GB
survey/poses/       poses and tie points             0.17 GB
```

## Two ways to take the images

**One ZIP.** Simplest if your connection is good. Stored, not compressed: the JPEGs inside are
the original files, byte for byte, in sorted (capture) order under one folder,
`plymouth-mn-residential-survey-images/`.

```bash
curl -LO https://huggingface.co/datasets/Matt1up/plymouth-mn-residential-survey-photogrammetry/resolve/main/zip/plymouth-mn-residential-survey-images.zip
sha256sum plymouth-mn-residential-survey-images.zip      # must print the line below
unzip plymouth-mn-residential-survey-images.zip
```

```
20143d2f80d3444a5b1e2758b7d2110721651d2a32bb996bc7197c3715458c40  plymouth-mn-residential-survey-images.zip
16,229,373,816 bytes
```

If it stops part-way, `curl -C - -LO <same URL>` resumes. To check every image after
unzipping:

```bash
./scripts/verify.sh --unzipped plymouth-mn-residential-survey-images
```

**File by file.** Better on a flaky connection: each file is resumable and checksummed on its
own, and you can take part of the set.

```bash
pip install -U huggingface_hub

./scripts/download.sh --images   # 16.23 GB
./scripts/download.sh --zip      # 16.23 GB
./scripts/download.sh --poses    # poses and tie points, 0.17 GB
./scripts/download.sh --all      # everything, 32.64 GB — the images twice, loose and zipped
./scripts/verify.sh
```

Raw CLI, without the wrapper. Run it again if it stops — finished files are skipped.

```bash
hf download Matt1up/plymouth-mn-residential-survey-photogrammetry --repo-type dataset --local-dir ./data --include 'survey/images/*'
```

To take one part of the capture only, pick the filenames from `manifest/survey/images.csv` by
its `mission_type` column (`grid-ew`, `grid-ns`, `orbit-large`, `orbit`) and download those.

## What's where

```
survey/images/               source JPEGs, original aircraft filenames, EXIF intact
survey/poses/colmap/         cameras.txt, images.txt, points3D.txt (the 3,893,468 tie points)
survey/poses/xmp/            RealityScan XMP sidecars, one per posed image, named after it
survey/poses/frame.txt       the coordinate frame: GPS-fitted, in meters, and the transform
survey/poses/unaligned.txt   the 7 images that did not align
zip/                         all images in one stored ZIP
preview/                     renders of the reconstructed model and the mission maps
```

Everything in `survey/poses/` except `points3D.txt` is also committed to this repo under
`poses/survey/`, so you can read the camera parameters without downloading anything.
`points3D.txt` is on Hugging Face only: at 0.17 GB it is over GitHub's 100 MB file limit.

## Verifying

```bash
./scripts/verify.sh
```

Checks SHA-256 for every file you actually have and ignores the rest, so partial downloads
verify cleanly. The lists are `manifest/survey/checksums.sha256` (per image),
`manifest/survey/poses.sha256` and `manifest/zip.sha256`.

`manifest/survey/images.csv` carries filename, battery, mission, mission type, size, SHA-256,
dimensions, capture time, GPS, height above takeoff, gimbal pitch and gimbal yaw for every
image. `manifest/survey/missions.csv` has one row per mission: its photos, times, height,
camera angle, and the orbit radius or the grid's line heading and spacing.
