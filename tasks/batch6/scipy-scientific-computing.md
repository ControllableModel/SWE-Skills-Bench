# Task: Add a damped-oscillator ODE simulator to scipy.integrate

## Background

The SciPy repository (`scipy/integrate`) provides initial-value ODE solvers, but
has no single helper that simulates a forced, damped harmonic oscillator over a
time span and reports both the trajectory and conserved/derived quantities. This
task adds such a helper as a new private module inside `scipy/integrate`, with
its own test suite.

## Files to Create/Modify

- `scipy/integrate/_oscillator.py` (new) — implementation of the simulator.
- `scipy/integrate/meson.build` (modify) — add `_oscillator.py` to a
  `py3.install_sources([...])` list whose `subdir` is `'scipy/integrate'`.
- `scipy/integrate/tests/test_oscillator.py` (new) — deterministic unit tests.
- `scipy/integrate/tests/meson.build` (modify) — add `test_oscillator.py` to the
  `py3.install_sources([...])` list whose `subdir` is `'scipy/integrate/tests'`.

(The test file imports the implementation directly, e.g.
`from scipy.integrate._oscillator import simulate_oscillator`. No change to the
public `scipy/integrate/__init__.py` API surface is required.)

## Requirements

### Public function

Implement a single function in `scipy/integrate/_oscillator.py`:

```
simulate_oscillator(omega, zeta, y0, t_span, *, n_eval=200, forcing=None)
```

with the following contract.

- The model is `x'' + 2*zeta*omega*x' + omega**2 * x = forcing(t)`, written as a
  first-order system in state `(x, v)`.
- `omega` is the natural angular frequency (`omega > 0`).
- `zeta` is the damping ratio (`zeta >= 0`).
- `y0` is the initial state `(x0, v0)`.
- `t_span` is a `(t0, t1)` pair with `t0 < t1`.
- `n_eval` is the number of equally spaced output times (including endpoints).
- `forcing` is either `None` (unforced) or a callable `f(t)` of the drive.

The function returns a dictionary with exactly these keys:

- `"t"` — a 1-D float array of length `n_eval`, ascending, spanning `t_span`.
- `"x"` — a 1-D float array of the position at those times.
- `"v"` — a 1-D float array of the velocity at those times.
- `"energy"` — a 1-D float array of the mechanical energy
  `0.5*v**2 + 0.5*omega**2 * x**2` at those times.

### Behavioral constraints

- For the unforced undamped case (`zeta=0`, `forcing=None`), `"x"` must match the
  analytic solution `x0*cos(omega t) + (v0/omega)*sin(omega t)` to tight
  tolerance, and `"energy"` must be conserved (constant across `"t"`).
- For an underdamped unforced case (`0 < zeta < 1`), the oscillation amplitude
  must decay and `"energy"` must be monotonically non-increasing.
- For an overdamped/critically-damped case started from rest displaced, `"x"`
  must approach `0` without sign change (no overshoot through zero).
- The function must not mutate the caller's `y0`.

### Input validation (edge cases)

Raise `ValueError` with an informative message when:

- `omega <= 0` or `zeta < 0`.
- `y0` is not a length-2 pair of finite numbers.
- `t_span` does not satisfy `t0 < t1`.
- `n_eval < 2`.

### Expected Functionality

- `omega=2, zeta=0, y0=(1,0)`, `forcing=None` -> `"x"` ≈ `cos(2 t)` and
  `"energy"` constant within tolerance.
- `omega=1, zeta=0.1, y0=(1,0)` -> envelope of `"x"` decays; `"energy"` is
  non-increasing along `"t"`.
- `omega=1, zeta=2, y0=(1,0)` (overdamped) -> `"x"` stays one-signed and tends
  toward 0.

## Acceptance Criteria

- A new module `scipy/integrate/_oscillator.py` exists and exposes
  `simulate_oscillator` with the signature and return contract above.
- `scipy/integrate/tests/test_oscillator.py` exists with at least 10 test cases
  that, using `numpy.testing.assert_allclose` / inequality assertions, verify:
  the undamped solution matches the analytic cosine/sine form and conserves
  energy; the underdamped energy is non-increasing and amplitude decays; the
  overdamped trajectory does not overshoot zero; `"t"` is correct length and
  span; a forcing callable changes the steady-state response; `y0` is not
  mutated; and each invalid-input case raises `ValueError`.
- A naive or hardcoded implementation (e.g. emitting a fixed cosine regardless of
  damping, or a one-step Euler scheme that leaks energy badly in the conservative
  case) must fail these tests.
- The following command passes from the repository root after building SciPy:

  ```
  python -m pytest scipy/integrate/tests/test_oscillator.py -v
  ```
