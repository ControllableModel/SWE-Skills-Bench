"""
Test for the 'scipy-scientific-computing' skill.

Verifies the agent added a band-limited spectral feature extractor to
``scipy/signal`` as a new private module ``scipy/signal/_bandpower.py`` exposing
``band_features(x, fs, band, *, order=4, nperseg=None)``.

The tests do not trust the agent's own test file or string-match the source.
Instead they exercise the real ``band_features`` function inside the built
SciPy (running each scenario in a fresh ``python`` subprocess with
cwd=REPO_DIR, exactly the environment the acceptance command uses) and
deep-validate the numeric / structural contract:

  * band power matches the analytic power of an in-band tone and is ~0 for an
    empty band, and is additive across disjoint bands;
  * out-of-band tones are attenuated by many orders of magnitude in
    ``"filtered"`` while in-band tones survive;
  * ``"filtered"`` is zero-phase (cross-correlation peaks at zero lag) and the
    same length as the input;
  * ``"peak_frequencies"`` recover the source tone frequencies in Hz;
  * the caller's input array is not mutated;
  * every invalid-input case raises ``ValueError``.

A naive implementation (raw FFT magnitude, ignoring the band, or a one-pass
causal filter that shifts the signal) fails these tests.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/scipy"

# Common preamble used by every driver subprocess. It loads ``band_features``
# preferring the official package import path required by the task, and falling
# back to loading the source file directly (its own ``from scipy.signal ...``
# imports still resolve through the installed SciPy) so that the behavioural
# tests can run even if the editable rebuild has not re-registered the module
# under the package namespace yet.
_LOADER = r"""
import json, sys, importlib.util, os
import numpy as np

def _load_band_features():
    try:
        from scipy.signal._bandpower import band_features as bf
        return bf
    except Exception:
        pass
    src = os.path.join(REPO_DIR, "scipy", "signal", "_bandpower.py")
    spec = importlib.util.spec_from_file_location("_bandpower_under_test", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.band_features

REPO_DIR = %r
band_features = _load_band_features()
""" % REPO_DIR


def _run_driver(body, timeout=300):
    """Run ``_LOADER + body`` as a python subprocess in REPO_DIR.

    ``body`` is expected to ``print(json.dumps(...))`` its result on the final
    line. Returns the parsed JSON object. Raises AssertionError with captured
    output on failure.
    """
    script = _LOADER + "\n" + textwrap.dedent(body)
    proc = subprocess.run(
        ["python", "-c", script],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, (
        "driver subprocess failed (rc=%d)\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
        % (proc.returncode, proc.stdout, proc.stderr)
    )
    # Result is the last non-empty stdout line (JSON).
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "driver produced no stdout\nSTDERR:\n%s" % proc.stderr
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "could not parse driver JSON output: %s\nLAST LINE: %r\nFULL STDOUT:\n%s"
            % (exc, lines[-1], proc.stdout)
        )


class TestScipyScientificComputing:
    """Validate the band_features spectral feature extractor."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """scipy/signal/_bandpower.py must exist."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "signal", "_bandpower.py")
        assert os.path.isfile(fpath), "_bandpower.py not found at %s" % fpath

    def test_test_file_exists(self):
        """scipy/signal/tests/test_bandpower.py must exist."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "signal", "tests", "test_bandpower.py"
        )
        assert os.path.isfile(fpath), "test_bandpower.py not found at %s" % fpath

    def test_meson_registers_module(self):
        """scipy/signal/meson.build must list _bandpower.py for installation."""
        fpath = os.path.join(self.REPO_DIR, "scipy", "signal", "meson.build")
        assert os.path.isfile(fpath), "signal meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "_bandpower.py" in content, (
            "_bandpower.py was not added to scipy/signal/meson.build install_sources"
        )

    def test_meson_registers_test(self):
        """scipy/signal/tests/meson.build must list test_bandpower.py."""
        fpath = os.path.join(
            self.REPO_DIR, "scipy", "signal", "tests", "meson.build"
        )
        assert os.path.isfile(fpath), "tests meson.build missing"
        with open(fpath) as f:
            content = f.read()
        assert "test_bandpower.py" in content, (
            "test_bandpower.py was not added to tests/meson.build install_sources"
        )

    def test_function_importable_and_callable(self):
        """band_features must be importable and return a dict with the three keys."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2 * np.pi * 50 * t)
            out = band_features(x, fs, (40.0, 60.0))
            assert isinstance(out, dict), "return value must be a dict"
            print(json.dumps(sorted(out.keys())))
            """
        )
        assert res == ["band_power", "filtered", "peak_frequencies"], (
            "band_features must return exactly keys "
            "{'filtered','band_power','peak_frequencies'}, got %r" % res
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution / deep behavioural validation
    # ------------------------------------------------------------------

    def test_band_power_matches_analytic_in_band(self):
        """band=(40,60) on sin(50)+0.5 sin(200) -> band_power ~= 0.5."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*200*t)
            out = band_features(x, fs, (40.0, 60.0))
            bp = float(out["band_power"])
            print(json.dumps({"bp": bp}))
            """
        )
        bp = res["bp"]
        assert bp >= 0.0, "band_power must be non-negative, got %r" % bp
        # Analytic power of a unit-amplitude sinusoid is 0.5.
        assert abs(bp - 0.5) < 0.05, (
            "band_power for the 50 Hz tone should be ~0.5, got %r" % bp
        )

    def test_band_power_second_band(self):
        """band=(150,250) -> band_power ~= 0.125 (the 0.5-amplitude tone)."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*200*t)
            out = band_features(x, fs, (150.0, 250.0))
            print(json.dumps({"bp": float(out["band_power"])}))
            """
        )
        bp = res["bp"]
        # Power of a 0.5-amplitude sinusoid is 0.5 * 0.5^2 = 0.125.
        assert abs(bp - 0.125) < 0.02, (
            "band_power for the 200 Hz tone should be ~0.125, got %r" % bp
        )

    def test_band_power_empty_band_is_near_zero(self):
        """band=(300,400) contains no tone -> band_power ~= 0."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*200*t)
            out = band_features(x, fs, (300.0, 400.0))
            print(json.dumps({"bp": float(out["band_power"])}))
            """
        )
        bp = res["bp"]
        assert bp < 1e-2, (
            "band_power for an empty band should be ~0, got %r "
            "(a naive impl that returns total/raw power fails here)" % bp
        )

    def test_band_power_additive_across_disjoint_bands(self):
        """Sum of disjoint-band powers ~= total signal power (0.5 + 0.125)."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*200*t)
            b_low  = float(band_features(x, fs, (40.0, 60.0))["band_power"])
            b_high = float(band_features(x, fs, (150.0, 250.0))["band_power"])
            b_empty= float(band_features(x, fs, (300.0, 400.0))["band_power"])
            print(json.dumps({"low": b_low, "high": b_high, "empty": b_empty}))
            """
        )
        total = res["low"] + res["high"] + res["empty"]
        # Analytic total in-band power = 0.5 + 0.125 = 0.625.
        assert abs(total - 0.625) < 0.06, (
            "disjoint-band powers should sum to ~0.625, got %r (low=%r high=%r empty=%r)"
            % (total, res["low"], res["high"], res["empty"])
        )
        # And they must be individually distinct (not all the same total power).
        assert res["low"] > res["high"] > res["empty"], (
            "band powers must be band-specific, got %r" % res
        )

    def test_out_of_band_tone_strongly_attenuated(self):
        """A pure 200 Hz tone, band=(40,60): filtered amplitude << input."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*200*t)        # tone well OUTSIDE the band
            out = band_features(x, fs, (40.0, 60.0))
            filt = np.asarray(out["filtered"], dtype=float)
            # ignore filter edge transients
            n = filt.size
            core = filt[n//5 : -n//5]
            ratio = float(np.max(np.abs(core)) / np.max(np.abs(x)))
            print(json.dumps({"ratio": ratio}))
            """
        )
        ratio = res["ratio"]
        # "Many orders of magnitude" — require >= ~2 orders of suppression.
        assert ratio < 1e-2, (
            "out-of-band 200 Hz tone must be strongly attenuated; "
            "residual amplitude ratio was %r (an impl that ignores the band fails)"
            % ratio
        )

    def test_in_band_tone_preserved(self):
        """A pure 50 Hz tone, band=(40,60): filtered amplitude ~= input."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t)         # tone INSIDE the band
            out = band_features(x, fs, (40.0, 60.0))
            filt = np.asarray(out["filtered"], dtype=float)
            n = filt.size
            core_f = filt[n//5 : -n//5]
            core_x = x[n//5 : -n//5]
            amp_in = float(np.max(np.abs(core_x)))
            amp_out = float(np.max(np.abs(core_f)))
            print(json.dumps({"amp_in": amp_in, "amp_out": amp_out}))
            """
        )
        ratio = res["amp_out"] / res["amp_in"]
        assert 0.9 < ratio < 1.1, (
            "in-band 50 Hz tone must be preserved (amp ratio ~1.0), got %r" % ratio
        )

    def test_zero_phase_no_net_delay(self):
        """Filtered in-band tone is zero-phase: cross-correlation peaks at lag 0."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t)
            out = band_features(x, fs, (40.0, 60.0))
            filt = np.asarray(out["filtered"], dtype=float)
            n = filt.size
            a = x[n//5 : -n//5]
            b = filt[n//5 : -n//5]
            a = a - a.mean(); b = b - b.mean()
            corr = np.correlate(b, a, mode="full")
            lags = np.arange(-len(a)+1, len(a))
            best_lag = int(lags[int(np.argmax(corr))])
            print(json.dumps({"best_lag": best_lag}))
            """
        )
        # Zero-phase (filtfilt) -> best alignment within +/-1 sample of lag 0.
        # A one-pass causal Butterworth would shift by several samples here.
        assert abs(res["best_lag"]) <= 1, (
            "filtered output must be in-phase with input (zero-lag); "
            "cross-correlation peaked at lag %r samples (a causal one-pass "
            "filter that shifts the signal fails this)" % res["best_lag"]
        )

    def test_peak_frequencies_recover_tones(self):
        """peak_frequencies for sin(50)+0.5 sin(200) ~= [50, 200] Hz, ascending."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*200*t)
            out = band_features(x, fs, (40.0, 60.0))
            peaks = [float(v) for v in np.asarray(out["peak_frequencies"], dtype=float)]
            print(json.dumps({"peaks": peaks}))
            """
        )
        peaks = res["peaks"]
        # ascending
        assert peaks == sorted(peaks), "peak_frequencies must be ascending, got %r" % peaks
        # exactly the two source tones, in Hz (not normalized units in [0,0.5]).
        assert len(peaks) == 2, (
            "expected 2 prominent peaks (50, 200 Hz), got %r "
            "(an impl reporting normalized freqs or raw FFT bins fails)" % peaks
        )
        assert abs(peaks[0] - 50.0) <= 2.0, "first peak should be ~50 Hz, got %r" % peaks[0]
        assert abs(peaks[1] - 200.0) <= 2.0, "second peak should be ~200 Hz, got %r" % peaks[1]

    def test_peak_frequencies_independent_of_band(self):
        """peak_frequencies of the ORIGINAL signal do not depend on requested band."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 2.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*200*t)
            p1 = [float(v) for v in np.asarray(band_features(x, fs, (40.0, 60.0))["peak_frequencies"], float)]
            p2 = [float(v) for v in np.asarray(band_features(x, fs, (300.0, 400.0))["peak_frequencies"], float)]
            print(json.dumps({"p1": p1, "p2": p2}))
            """
        )
        p1, p2 = res["p1"], res["p2"]
        assert len(p1) == len(p2) == 2, (
            "peak_frequencies must describe the original signal regardless of band; got %r / %r"
            % (p1, p2)
        )
        for a, b in zip(sorted(p1), sorted(p2)):
            assert abs(a - b) <= 2.0, (
                "peak_frequencies must be band-independent; %r vs %r" % (p1, p2)
            )

    def test_filtered_same_length_as_input(self):
        """'filtered' is 1-D float and exactly the same length as the input."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 500.0
            t = np.arange(0, 1.0, 1.0 / fs)   # 500 samples
            x = np.sin(2*np.pi*30*t)
            out = band_features(x, fs, (20.0, 40.0))
            filt = np.asarray(out["filtered"])
            print(json.dumps({"n_in": int(x.size), "n_out": int(filt.size), "ndim": int(filt.ndim)}))
            """
        )
        assert res["ndim"] == 1, "'filtered' must be 1-D, got ndim=%r" % res["ndim"]
        assert res["n_out"] == res["n_in"], (
            "'filtered' length (%r) must equal input length (%r)"
            % (res["n_out"], res["n_in"])
        )

    def test_input_not_mutated(self):
        """band_features must not mutate the caller's input array."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 1.0, 1.0 / fs)
            x = np.sin(2*np.pi*50*t) + 0.5*np.sin(2*np.pi*200*t)
            before = x.copy()
            _ = band_features(x, fs, (40.0, 60.0))
            unchanged = bool(np.array_equal(x, before))
            print(json.dumps({"unchanged": unchanged}))
            """
        )
        assert res["unchanged"] is True, "band_features must not mutate its input array"

    def test_short_input_uses_default_nperseg(self):
        """nperseg=None must pick a default that works for short inputs."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 200.0
            t = np.arange(0, 0.25, 1.0 / fs)   # only 50 samples
            x = np.sin(2*np.pi*30*t)
            out = band_features(x, fs, (20.0, 40.0))   # nperseg defaulted
            ok = (np.asarray(out["filtered"]).size == x.size
                  and float(out["band_power"]) >= 0.0)
            print(json.dumps({"ok": bool(ok), "bp": float(out["band_power"])}))
            """
        )
        assert res["ok"] is True, (
            "band_features must handle short inputs via a sensible default nperseg"
        )

    def test_invalid_inputs_raise_value_error(self):
        """Each invalid-input case must raise ValueError."""
        res = _run_driver(
            r"""
            import numpy as np
            fs = 1000.0
            t = np.arange(0, 1.0, 1.0 / fs)
            good = np.sin(2*np.pi*50*t)

            def raises_value_error(fn):
                try:
                    fn()
                except ValueError:
                    return True
                except Exception:
                    return False
                return False

            results = {}
            # x not 1-D
            results["x_2d"] = raises_value_error(
                lambda: band_features(np.ones((4, 4)), fs, (40.0, 60.0)))
            # x too few samples
            results["x_short"] = raises_value_error(
                lambda: band_features(np.array([1.0]), fs, (40.0, 60.0)))
            # fs <= 0
            results["fs_zero"] = raises_value_error(
                lambda: band_features(good, 0.0, (40.0, 60.0)))
            results["fs_neg"] = raises_value_error(
                lambda: band_features(good, -100.0, (40.0, 60.0)))
            # band not a 2-tuple
            results["band_len"] = raises_value_error(
                lambda: band_features(good, fs, (10.0, 20.0, 30.0)))
            # low >= high
            results["band_order"] = raises_value_error(
                lambda: band_features(good, fs, (60.0, 40.0)))
            # low <= 0
            results["band_low0"] = raises_value_error(
                lambda: band_features(good, fs, (0.0, 60.0)))
            # high >= fs/2 (Nyquist)
            results["band_nyq"] = raises_value_error(
                lambda: band_features(good, fs, (40.0, 600.0)))
            print(json.dumps(results))
            """
        )
        for case, ok in res.items():
            assert ok is True, "invalid-input case %r did not raise ValueError" % case

    def test_acceptance_pytest_command(self):
        """The agent's own test file passes via the acceptance command."""
        proc = subprocess.run(
            ["python", "-m", "pytest",
             "scipy/signal/tests/test_bandpower.py", "-v", "--tb=short"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command failed\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
            % (proc.stdout[-4000:], proc.stderr[-2000:])
        )
