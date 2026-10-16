# Task: Implement a Batch Directory Processor

## Background

Preparing a folder of raw assets for the web means applying the same operation (convert, resize, or thumbnail) to every supported image in a directory and writing the results to an output directory. This task adds `src/PIL/BatchOps.py`, a deterministic batch processor.

## Files to Create/Modify

- `src/PIL/BatchOps.py` (new) — the batch processor described below.
- `Tests/test_batchops.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library. It must operate on real files written to a temporary directory in the test (use `tmp_path`); no network.

## Requirements

### `process_dir(src_dir, dst_dir, *, action, **params)`

Process every supported image file directly inside `src_dir`, writing one output per input into `dst_dir` (created if missing). Return a list of the output file paths, sorted by input filename for deterministic ordering.

### Input selection

- Only files whose extension is one of `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp` (case-insensitive) are processed; all other files are ignored.
- Subdirectories are **not** recursed into.
- If `src_dir` does not exist, raise `FileNotFoundError`. If it exists but contains no supported images, return an empty list (and still create `dst_dir`).

### Actions

- `action="convert"` with `format=` (one of `"png"`, `"jpeg"`, `"webp"`): re-encode each image to that format. The output filename keeps the original stem and gets the new extension. JPEG output must flatten alpha onto opaque white.
- `action="resize"` with `width=` (positive int): resize each image to that width, height scaled to preserve aspect ratio (rounded, floor 1). Output keeps the original filename and format.
- `action="thumbnail"` with `size=` (positive int): fit each image inside a `size`×`size` box (longer side equals `size`, no upscaling). Output keeps the original filename and format.
- An unknown `action`, or a known action missing its required parameter, raises `ValueError`.

### Determinism

- The returned path list is sorted; processing two images with the same content and action produces identical outputs.

### Expected Functionality

- A `src_dir` containing `a.png` (400×200) and `b.png` (200×400), processed with `action="resize", width=100`, yields two files at widths `100` (heights `50` and `200` respectively).
- The same inputs with `action="convert", format="webp"` yield `a.webp` and `b.webp`.
- A `.txt` file in `src_dir` is ignored.

## Acceptance Criteria

All checks write real files under `tmp_path`.

1. `process_dir` processes only supported image extensions and ignores other files and subdirectories.
2. `action="convert"` writes the correct new extensions and JPEG output flattens alpha onto white.
3. `action="resize"` and `action="thumbnail"` produce the expected output dimensions for known inputs.
4. A missing `src_dir` raises `FileNotFoundError`; an empty-but-existing `src_dir` returns `[]` and creates `dst_dir`.
5. An unknown action or a missing required parameter raises `ValueError`, and the returned path list is sorted.

The added test file must pass:

```
python -m pytest Tests/test_batchops.py -q
```
