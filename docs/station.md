# Checking a labelled part before stamping

I use the station module to check whether a drawing or seal carrier is loaded
and whether its drawing number and revision match the intended operation. A
carrier is the piece that holds something in a repeatable position. This is a
separate command from the PDF and CAD tools. It does not approve drawings or
control a physical machine.

## Run the public example

With the README's Python environment active:

```sh
python -m stamper.station_demo --output-dir output/station
python -m stamper.station --image output/station/present.png --empty output/station/empty.png --recipe output/station/recipe.json
```

The first command generates an empty fixture image, a loaded image, a recipe
(the inspection settings), 44 challenge images and `sensitivity.json`, the full
report. The second inspects one frame and prints a JSON record. On the loaded
example it reports `"status": "PASS"`, `"plc_pass": 1` and no failure reasons.
The `codes` entries include the actual text and format read from the image.
Run an empty check with:

```sh
python -m stamper.station --image output/station/empty.png --empty output/station/empty.png --recipe output/station/recipe.json
```

This reports FAIL and `plc_pass: 0`, even though both labels still read correctly.
Exit codes are 0 for PASS, 1 for an inspection FAIL and 2 for an input or
processing error. The empty-check command intentionally exits 1. Malformed or
missing command arguments also exit 2, through the argument parser; those may
have no JSON record. An adapter must treat any missing/invalid result as failure.

All example content is generated. The part is a dark rounded carrier with a
hole. Its 1D label, bars in one direction, contains `DEMO-042` as Code 128. Its
2D label, a square grid called a QR code, contains `DEMO-042:REV-B`. The reader
also supports Data Matrix, another 2D format, through the recipe.

## Use my own fixed-camera images

1. Lock the camera position, focus and image resolution. Choose a repeatable
   fixture and a clear patch of its surface that remains visible when loaded.
2. Capture `empty.png` with the part removed. Keep static fixture markings in
   place. This file is the reference, not a frame from a previous passing cycle.
3. Generate the example recipe and edit its JSON. `frame_size` is `[width,
   height]`. Every `roi` is a region of interest, written as `[left, top, right,
   bottom]` in pixels from the top left. Right and bottom are excluded. Set
   `part_roi`, `background_roi` and a separate `roi` for each expected code.
   Regions must be inside the frame and must not overlap. Preserve blank
   margins around barcodes so the reader can find their edges.
4. Change each label's `name`, `format` (`Code128`, `QRCode` or `DataMatrix`)
   and exact expected `text`. At least one code is required. The example
   requires both drawing and revision; removing a label requirement is an
   explicit recipe change.
5. Capture known loaded and empty images under the real range of lighting.
   Adjust `difference_threshold`, `min_area`, `max_area`, `center_tolerance`,
   `min_background`, `max_background` and `max_glare` using those images.
   Keep separate held-out images to check the settings before use.
6. Run the single-frame command with the new paths. Check `presence`, decoded
   code text and every `reasons` entry before connecting an output adapter.

The default changed-area range is 30% to 65% of the part region. The centroid,
meaning the average location of changed pixels, must stay within 15% of the
region width/height from its centre. The brightness range is 30 to 250 on a
0-to-255 grayscale scale. At most 10% of the part region may be saturated white,
which is a possible glare reflection. These defaults describe the example
fixture; they are not universal camera settings.

## How the decision works

`stamper/station.py` converts both images to grayscale. It measures median
brightness in the clear background patch and divides each image by its own
measurement. This compensates for an overall change in lamp brightness without
requiring a new empty reference for every frame. It compares the normalized
part regions and counts pixels differing by at least 0.15 of the measured
background brightness. Saturated white pixels cannot count as part evidence.
The changed area and its centre must meet the recipe, and excessive glare fails.

ZXing-C++, the local barcode decoder, reads each label region independently.
It must find exactly the expected format and text. A readable wrong revision,
a missing label, or an extra different code in that region fails. Identical
copies of the same code count as one identity. A correct code elsewhere in the
frame cannot rescue a missing label in the assigned region.

The result combines part presence **and** every label check. A cropped frame,
bad recipe, corrupt file or decoder exception cannot return a passing decision.
There is no cached passing result and no network request. The decoder and
example writer use the pinned Python package `zxing-cpp==3.0.0`; see its
[upstream Python documentation](https://github.com/zxing-cpp/zxing-cpp/blob/v3.0.0/wrappers/python/README.md).

## Connecting the decision to a controller

A PLC is a programmable logic controller. Its digital input represents a high
or low electrical signal. `plc_pass` is the software value for an adapter:
1 means all checks passed for this frame; 0 means reject or fault. This repository
emits the decision only. It does not generate a 24 V signal or claim a hardware
commissioning test.

For a real adapter, set the output LOW before triggering a fresh capture. Raise
it only after a complete current-frame PASS record and successful exit code 0.
Drop it on FAIL, exceptions, malformed output, capture timeout, stale frame,
process loss or watchdog expiry. A watchdog is a timer that removes permission
when fresh results stop arriving. Do not hold the last HIGH across frames.
The adapter must pair the result with its own capture/cycle identifier and
maximum age; this file-based command cannot detect an old image supplied again.
Choose compatible isolated output hardware and validate the timing and wiring
at the station. This decision is not a safety interlock.

## Measured synthetic sensitivity

`python -m stamper.station_demo` returns nonzero if any expected decision is
wrong. CI runs it and saves all images and the full JSON report as an artifact.
The baseline measured on this version is **44/44 correct, zero false passes and
zero false rejects**:

| Challenge | Cases | Expected decisions | Measured correct |
| --- | ---: | --- | ---: |
| Brightness gain 0.25, 0.5, 1.0; contrast 0.35, 0.6, 1.0; glare radius 0 or 15 px; loaded and empty | 36 | 18 PASS, 18 FAIL | 36 |
| Near darkness, overexposure, glare radius 65 px, lost contrast | 4 | FAIL | 4 |
| Wrong drawing, wrong revision, missing 1D, missing 2D | 4 | FAIL | 4 |

Noise has a fixed seed and a standard deviation of one grayscale level. Lamp
gain and contrast change the whole frame, including the actual barcode pixels.
The small glare spot crosses the part. The severe spot hides too much of it.
This is a deterministic sensitivity exercise, not a field accuracy estimate.

The 85 station tests also check rotated Code 128 and QR labels, Data Matrix,
wrong formats, extra codes, strict region boundaries, partial/oversized/shifted
parts, invalid calibration and the command's PASS/FAIL/error behavior. Run:

```sh
python -m pytest tests/test_station.py -q
python -m pytest -q
```

The fixture must stay aligned. A different object with the same changed area
and centre could pass the presence test. Nonuniform shadows, moving backgrounds,
transparent parts, blur, perspective and print damage need real camera trials
and possibly a different inspection method. Code identity checks cannot prove
that a detachable label belongs to the physical part. No live camera, PLC,
voltage output, reject mechanism or production performance has been tested.
