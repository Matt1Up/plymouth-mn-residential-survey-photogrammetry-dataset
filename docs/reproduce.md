# Reproducing the reconstruction

The images are ordinary geotagged JPEGs, so any structure-from-motion tool reads them. Below is
what to expect from *this* capture before you spend hours on it.

The scan ships solved poses for the original photos in [`../poses/survey/`](../poses/survey/),
so you can skip alignment and go straight to meshing or splatting. Re-align only if you want to
compare.

---

## What to expect

| | |
|---|---|
| images | 1,421 |
| solved | **1,414 / 1,421**, one component |
| solver | RealityScan 2.2 |

**Everything joins.** The two nadir grids, the large orbit and all ten small orbits solve in
one component.

**Tree canopy is the weak spot.** Six of the seven images that did not align look straight down
on dense trees (grid frames `…0224`–`…0227` and `…0271`–`…0272`); the seventh is an orbit frame
with a tree close in front of the camera (`…0617`). They are listed in
[`../poses/survey/unaligned.txt`](../poses/survey/unaligned.txt).

**DJI frame numbers repeat.** The aircraft's counter wraps after 0999, so 424 frame numbers
appear twice in this set. Match photos by their full filename (which carries the capture time),
never by the four-digit number alone.

---

## COLMAP / GLOMAP

```bash
colmap feature_extractor \
  --database_path db.db --image_path images/ \
  --ImageReader.camera_model OPENCV

colmap exhaustive_matcher --database_path db.db   # or spatial_matcher: every photo is geotagged

# either COLMAP's mapper, or GLOMAP for a much faster global solve
colmap mapper --database_path db.db --image_path images/ --output_path sparse/
```

Every frame is 4096 × 3072 from the same lens at the same settings, so
`--ImageReader.single_camera 1` looks natural. Test it before relying on it: in the published
solve RealityScan gave each photo its own focal length and distortion, and holding all photos
to one shared camera fits those poses clearly worse — on the epipolar check, a median of 0.2–0.5 px
with the published cameras against up to 15.6 px with one shared camera.

---

## Scale

There is no scale reference in this capture. The published poses are in meters only because
the solve was fitted to the photos' GPS positions — see *Coordinate frame* in the
[README](../README.md) and [`../poses/survey/frame.txt`](../poses/survey/frame.txt). A fresh
solve of your own comes out at arbitrary scale, or at GPS scale if your tool uses the EXIF
positions.

---

## Gaussian splatting

`poses/survey/colmap/` is a drop-in sparse reconstruction — `cameras.txt`, `images.txt` and
`points3D.txt` (the last hosted with the images). The cameras are `FULL_OPENCV`, one per photo,
for the original photos. A pipeline that reads OpenCV distortion trains on them directly; one
that accepts only pinhole cameras needs undistorted copies first:

```bash
colmap image_undistorter --image_path images/ --input_path colmap/ --output_path undistorted/
```

Downsample to ~1600 px wide before training — nothing trains at 4096 px, and the originals are
here so you can choose. The `mission` and `mission_type` columns of
`manifest/survey/images.csv` let you train on part of the capture (only the grids, only the
orbits) and compare.
