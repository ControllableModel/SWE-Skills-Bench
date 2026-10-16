# Task: Build a Format-Aware Web Save Helper

## Background

Pillow's `Image.save` requires the caller to know the right per-format keyword arguments and to handle format incompatibilities by hand. This task adds a new module `src/PIL/WebSave.py` providing a single entry point that picks correct save parameters from the destination file extension and resolves the common transparency-vs-JPEG mismatch.

## Files to Create/Modify

- `src/PIL/WebSave.py` (new) — the save helper described below.
- `Tests/test_websave.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library. Do not invoke external binaries or add third-party dependencies.

## Requirements

### `save(image, path, *, quality=None, optimize=True)`

Persist `image` to `path`, deriving save behaviour from the file extension (case-insensitive). Any missing parent directories of `path` must be created. The function returns the absolute or given `path` string it wrote to.

### Per-format behaviour

- `.png` → saved losslessly; when `optimize` is true the PNG optimisation flag must be enabled.
- `.webp` → saved as a lossy WebP. The `quality` value (see default below) must be passed through to the encoder.
- `.jpg` / `.jpeg` → saved as JPEG. Because JPEG has no alpha channel, an image whose mode carries transparency (`RGBA`, `LA`, or a `P` image with transparency) must be flattened onto an **opaque white** canvas using the source alpha as the paste mask before saving; a fully transparent source pixel therefore reopens as `(255, 255, 255)`. The `quality` value must be passed through.
- Any other extension raises `ValueError` whose message contains the offending extension.

### Quality handling

- For the lossy formats (`webp`, `jpg`/`jpeg`), when `quality` is `None` a built-in default in the range 80–90 inclusive is applied.
- An explicitly passed `quality` always overrides the default and is forwarded to the encoder.
- For `.png`, `quality` is ignored (PNG is lossless) and passing it must not raise.

### Edge cases

- The input image must never be mutated (mode, size, and pixel data unchanged after the call).
- A path with no directory component (bare filename in the current directory) must still save successfully without raising on directory creation.

## Acceptance Criteria

All checks run with in-memory images; no network or fixtures required.

1. Saving the same `RGB` image to `.png`, `.jpg`, and `.webp` paths each produces a file that reopens with the expected Pillow format identifier.
2. Saving an `RGBA` image with at least one fully transparent pixel to a `.jpg` path reopens that pixel as `(255, 255, 255)`.
3. Saving to a path whose parent directory does not yet exist creates the directory and writes the file.
4. An unsupported extension (e.g. `.gif`) raises `ValueError`.
5. Passing an explicit `quality` is honoured (a low quality produces a strictly smaller JPEG file than a high quality for the same source image), and omitting it uses the default without error.
6. The source image object is unchanged after every save.

The added test file must pass:

```
python -m pytest Tests/test_websave.py -q
```
