# Task: Add a band-limited spectral feature extractor to scipy.signal

## Background

The SciPy repository (`scipy/signal`) provides building blocks for digital
signal processing but has no single helper that, given a raw 1-D time series,
isolates a frequency band and reports quantitative features of that band. This
task adds such a helper as a new private module inside `scipy/signal`, together
with its test suite.

## Files to Create/Modify

- `scipy/signal/_bandpower.py` (new) — implementation of the feature extractor.
- `scipy/signal/meson.build` (modify) — add `_bandpower.py` to the
  `py3.install_sources([...])` list for `subdir: 'scipy/signal'` so the new
  module is installed/importable.
- `scipy/signal/tests/test_bandpower.py` (new) — deterministic unit tests.
- `scipy/signal/tests/meson.build` (modify) — add `test_bandpower.py` to the
  `py3.install_sources([...])` list for `subdir: 'scipy/signal/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.signal._bandpower import band_features`. No change to the public
`scipy/signal/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/signal/_bandpower.py`:

```
band_features(x, fs, band, *, order=4, nperseg=None)
```

with the following contract.

- `x` is a 1-D, real-valued, finite-length sequence (accept any array-like that
  `numpy.asarray` turns into a 1-D float array).
- `fs` is the sampling frequency in Hz (a positive float).
- `band` is a 2-tuple `(low, high)` of pass-band edge frequencies in Hz, with
  `0 < low < high < fs/2`.
- `order` is the order of the band-pass filter used for isolation.
- `nperseg` is the segment length used for spectral estimation; when `None`, a
  sensible default derived from the input length must be chosen so that short
  inputs still work.

The function returns a dictionary with exactly these keys:

- `"filtered"` — the input restricted to the requested band by **zero-phase**
  band-pass filtering. It must be a 1-D float array **the same length as `x`**,
  and applying the band isolation must introduce no net time shift (a sinusoid
  inside the band must come out aligned with the input, not delayed).
- `"band_power"` — a non-negative float: the total power of the original signal
  contained within `band`, obtained by integrating the power spectral density
  over the requested frequency interval.
- `"peak_frequencies"` — a 1-D float array of the frequencies (in Hz, ascending)
  of the prominent spectral peaks of the **original** signal `x`. "Prominent"
  means local maxima of the spectrum whose height is at least 5% of the global
  spectral maximum. Frequencies must be reported in Hz, not in normalized units.

### Behavioral constraints

- Out-of-band content must be strongly suppressed in `"filtered"`: a pure tone
  whose frequency lies well outside `band` must be attenuated by many orders of
  magnitude relative to its input amplitude.
- In-band content must be preserved: a pure tone whose frequency lies inside
  `band` must survive with its amplitude essentially unchanged.
- `"band_power"` must reflect the original signal's energy in the band and must
  be (approximately) additive across disjoint bands of a multi-tone signal: the
  power reported for a band containing one tone must match that tone's analytic
  power, and must be near zero for a band that contains none of the tones.
- The computation must not mutate the caller's input array.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `x` is not 1-D, or has fewer than 2 samples.
- `fs <= 0`.
- `band` is not a 2-tuple, or does not satisfy `0 < low < high < fs/2`.

### Expected Functionality

- Signal `sin(2π·50·t)+0.5·sin(2π·200·t)` sampled at `fs=1000` for 2 s, with
  `band=(40,60)` -> `"band_power"` ≈ 0.5 (the analytic power of a unit-amplitude
  sinusoid), and the 200 Hz energy is absent from `"filtered"`.
- The same signal with `band=(150,250)` -> `"band_power"` ≈ 0.125 (power of the
  0.5-amplitude tone), and `"filtered"` contains essentially only the 200 Hz
  component.
- The same signal with `band=(300,400)` -> `"band_power"` ≈ 0 (no tone there).
- `"peak_frequencies"` for that signal ≈ `[50.0, 200.0]` (within spectral
  resolution), independent of which band was requested.
- A single in-band sinusoid passed through is returned in-phase (cross-correlation
  is maximized at zero lag).

## Acceptance Criteria

- A new module `scipy/signal/_bandpower.py` exists and exposes `band_features`
  with the signature and return contract above.
- `scipy/signal/tests/test_bandpower.py` exists with at least 10 test cases that,
  using `numpy.testing.assert_allclose` with appropriate tolerances, verify:
  band power matches analytic tone power for in-band requests and is ~0 for
  empty bands; band power is additive across disjoint bands; out-of-band tones
  are attenuated by many orders of magnitude in `"filtered"`; in-band tones are
  preserved with no net delay (zero-lag alignment); recovered `"peak_frequencies"`
  match the source tone frequencies in Hz; `"filtered"` has the same length as
  the input; the input array is not mutated; and each invalid-input case raises
  `ValueError`.
- A naive or hardcoded implementation (e.g. returning the raw FFT magnitude, or
  ignoring the band, or applying a one-pass causal filter that shifts the signal)
  must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/signal/tests/test_bandpower.py -v
  ```
