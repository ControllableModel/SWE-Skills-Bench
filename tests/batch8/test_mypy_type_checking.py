"""Tests for skill: mypy-type-checking (task: Add a Cache-Fingerprint Builder).

The agent must create a self-contained, standard-library-only module
``src/black/cache_fingerprint.py`` inside the ``black`` repository exposing
``CacheRecord``, ``fingerprint`` and ``FingerprintError`` (a subclass of
``ValueError``), plus a deterministic unit-test file
``tests/test_cache_fingerprint.py``.

This suite verifies the deliverable from two angles:

* L1 -- the deliverable files exist and are minimally well-formed, and the
  required public surface imports with the right shapes.
* L2 -- the runtime behaviour of the fingerprint builder is exercised
  independently by driving the module through a fresh Python subprocess (so a
  naive solution that hashes a raw ``repr()`` -- and is therefore
  order-sensitive -- or that skips ``from_dict`` validation fails), the
  project's configured (strict) ``mypy`` static-analysis gate is run over the
  new module, and the agent-authored pytest file is executed with the native
  toolchain.

The module is intentionally imported directly from its file location (and also
via the canonical ``black.cache_fingerprint`` package path) so that the heavy,
optional third-party dependencies of the top-level ``black`` package never gate
these behavioural checks.

The native L2 acceptance commands driven here are::

    python -m pytest tests/test_cache_fingerprint.py -q
    python -m mypy src/black/cache_fingerprint.py
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "cache_fingerprint.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_cache_fingerprint.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the fingerprint module directly.

        The module file is loaded by path via importlib so that we do NOT pull
        in the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``CacheRecord``/``fingerprint``/``FingerprintError`` are injected into
        the snippet's globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_cache_fingerprint_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            CacheRecord = mod.CacheRecord
            fingerprint = mod.fingerprint
            FingerprintError = mod.FingerprintError
            """
        ).format(module_path=self.MODULE_PATH)
        script = preamble + textwrap.dedent(body)
        result = subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result

    def _run_ok(self, body, timeout=120):
        result = self._run_driver(body, timeout=timeout)
        assert result.returncode == 0, (
            "driver exited non-zero\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        return result

    # A canonical helper the driver can use to build a CacheRecord regardless of
    # whether the agent implemented CacheRecord as a dataclass, a TypedDict or a
    # small class. ``from_dict`` is part of the required public surface.
    _MAKE = textwrap.dedent(
        """
        def make(content="x", line_length=88, target_versions=None, flags=None):
            data = {
                "content": content,
                "line_length": line_length,
                "target_versions": list(target_versions if target_versions is not None else []),
                "flags": dict(flags if flags is not None else {}),
            }
            return CacheRecord.from_dict(data)
        """
    )

    # ------------------------------------------------------------------ #
    # L1 -- deliverables exist and are well-formed
    # ------------------------------------------------------------------ #
    def test_module_file_exists(self):
        """L1: the new fingerprint module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected fingerprint module at {self.MODULE_PATH}"
        )
        assert os.path.getsize(self.MODULE_PATH) > 0

    def test_unit_test_file_exists(self):
        """L1: the deterministic unit-test file is created at the required path."""
        assert os.path.isfile(self.TEST_PATH), (
            f"expected unit-test file at {self.TEST_PATH}"
        )
        assert os.path.getsize(self.TEST_PATH) > 0

    def test_public_surface_importable(self):
        """L1->L2: the three required public names import with the right shapes.

        Also asserts FingerprintError is a subclass of ValueError, that
        CacheRecord exposes a ``from_dict`` classmethod, and that ``fingerprint``
        is callable -- the exact public contract from the requirement doc.
        """
        result = self._run_ok(
            """
            assert isinstance(CacheRecord, type)
            assert callable(fingerprint)
            assert isinstance(FingerprintError, type)
            assert issubclass(FingerprintError, ValueError)
            assert hasattr(CacheRecord, "from_dict")
            assert callable(CacheRecord.from_dict)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.cache_fingerprint import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.cache_fingerprint import "
            "CacheRecord, fingerprint, FingerprintError\n"
            "assert issubclass(FingerprintError, ValueError)\n"
            "print('IMPORT_OK')\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = self.SRC_DIR
        result = subprocess.run(
            ["python", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        assert result.returncode == 0, (
            "canonical import path failed\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "IMPORT_OK" in result.stdout

    # ------------------------------------------------------------------ #
    # L2 -- fingerprint runtime behaviour
    # ------------------------------------------------------------------ #
    def test_fingerprint_hex_format(self):
        """L2: fingerprint returns a 64-char lowercase hex SHA-256 digest.

        Maps to: ``^[0-9a-f]{64}$``. A stub returning a short/empty/uppercase
        value fails here.
        """
        self._run_ok(
            self._MAKE
            + """
            import re
            fp = fingerprint(make(content="hello", line_length=88,
                                  target_versions=["py311"], flags={"fast": True}))
            assert isinstance(fp, str), type(fp)
            assert re.fullmatch(r"[0-9a-f]{64}", fp), fp
            print("OK")
            """
        )

    def test_fingerprint_determinism(self):
        """L2: identical logical records yield identical fingerprints across calls.

        Two independently-built records with the same logical content must agree,
        and repeated calls on the same record must agree.
        """
        self._run_ok(
            self._MAKE
            + """
            r1 = make(content="src", line_length=88,
                      target_versions=["py38", "py311"], flags={"fast": True, "pyi": False})
            r2 = make(content="src", line_length=88,
                      target_versions=["py38", "py311"], flags={"fast": True, "pyi": False})
            a = fingerprint(r1)
            assert fingerprint(r1) == a, "non-deterministic within same record"
            assert fingerprint(r2) == a, "non-deterministic across equal records"
            print("OK")
            """
        )

    def test_fingerprint_target_versions_order_independent(self):
        """L2: reordering target_versions does NOT change the fingerprint.

        This is the key discriminator against a naive ``repr()``/order-sensitive
        hash. ``["py311","py38"]`` and ``["py38","py311"]`` must agree; duplicates
        must collapse to the same value as the deduplicated set.
        """
        self._run_ok(
            self._MAKE
            + """
            base = dict(content="c", line_length=88, flags={"fast": True})
            a = fingerprint(make(target_versions=["py311", "py38"], **base))
            b = fingerprint(make(target_versions=["py38", "py311"], **base))
            assert a == b, ("order of target_versions must not matter", a, b)

            # duplicates collapse -> same as the unique set
            dup = fingerprint(make(target_versions=["py38", "py311", "py38"], **base))
            assert dup == a, ("duplicate target_versions must collapse", dup, a)
            print("OK")
            """
        )

    def test_fingerprint_flags_order_independent(self):
        """L2: iteration order of the flags mapping does NOT change the fingerprint.

        Building the same logical flag set via differently-ordered dict literals
        must produce one fingerprint.
        """
        self._run_ok(
            self._MAKE
            + """
            base = dict(content="c", line_length=88, target_versions=["py311"])
            import collections
            f1 = {"a": True, "b": False, "c": True}
            f2 = collections.OrderedDict([("c", True), ("b", False), ("a", True)])
            a = fingerprint(make(flags=f1, **base))
            b = fingerprint(make(flags=dict(f2), **base))
            assert a == b, ("flags iteration order must not matter", a, b)
            print("OK")
            """
        )

    def test_fingerprint_sensitive_to_content(self):
        """L2: changing ``content`` changes the fingerprint."""
        self._run_ok(
            self._MAKE
            + """
            base = dict(line_length=88, target_versions=["py311"], flags={"fast": True})
            a = fingerprint(make(content="alpha", **base))
            b = fingerprint(make(content="beta", **base))
            assert a != b, "content change must alter fingerprint"
            print("OK")
            """
        )

    def test_fingerprint_sensitive_to_line_length(self):
        """L2: changing ``line_length`` from 88 to 100 changes the fingerprint."""
        self._run_ok(
            self._MAKE
            + """
            base = dict(content="c", target_versions=["py311"], flags={"fast": True})
            a = fingerprint(make(line_length=88, **base))
            b = fingerprint(make(line_length=100, **base))
            assert a != b, "line_length change must alter fingerprint"
            print("OK")
            """
        )

    def test_fingerprint_sensitive_to_target_version_set(self):
        """L2: changing the SET of target_versions changes the fingerprint.

        Distinct from the order test: adding/removing a real element must move
        the digest, even though pure reordering must not.
        """
        self._run_ok(
            self._MAKE
            + """
            base = dict(content="c", line_length=88, flags={"fast": True})
            a = fingerprint(make(target_versions=["py38", "py311"], **base))
            b = fingerprint(make(target_versions=["py38"], **base))
            c = fingerprint(make(target_versions=["py38", "py311", "py312"], **base))
            assert a != b, "removing a version must alter fingerprint"
            assert a != c, "adding a version must alter fingerprint"
            print("OK")
            """
        )

    def test_fingerprint_sensitive_to_flag_value(self):
        """L2: flipping a single flag from False to True changes the fingerprint."""
        self._run_ok(
            self._MAKE
            + """
            base = dict(content="c", line_length=88, target_versions=["py311"])
            a = fingerprint(make(flags={"skip_magic": False, "fast": True}, **base))
            b = fingerprint(make(flags={"skip_magic": True, "fast": True}, **base))
            assert a != b, "flipping a flag must alter fingerprint"
            print("OK")
            """
        )

    def test_empty_inputs_are_valid_and_stable(self):
        """L2: empty content and empty target_versions are valid and deterministic.

        A record with empty ``content`` and ``target_versions`` and no flags must
        produce a well-formed, repeatable hex fingerprint.
        """
        self._run_ok(
            self._MAKE
            + """
            import re
            r = make(content="", line_length=1, target_versions=[], flags={})
            fp = fingerprint(r)
            assert re.fullmatch(r"[0-9a-f]{64}", fp), fp
            assert fingerprint(make(content="", line_length=1, target_versions=[], flags={})) == fp
            print("OK")
            """
        )

    def test_from_dict_validation_errors(self):
        """L2: from_dict raises FingerprintError on malformed records.

        Covers the documented failure inputs -- the key discriminator against a
        validation-skipping implementation:

        * ``line_length=0`` (must be > 0)
        * ``line_length="88"`` (non-int)
        * a non-str element in ``target_versions``
        * a non-bool flag value (``{"skip_magic": "yes"}``)
        * a missing required field
        """
        self._run_ok(
            """
            good = {
                "content": "x",
                "line_length": 88,
                "target_versions": ["py311"],
                "flags": {"fast": True},
            }
            # sanity: the good record constructs without error
            CacheRecord.from_dict(dict(good))

            def expect_error(mutate, label):
                bad = dict(good)
                mutate(bad)
                try:
                    CacheRecord.from_dict(bad)
                except FingerprintError:
                    return
                except Exception as exc:
                    raise AssertionError(
                        f"{label}: expected FingerprintError, got {type(exc).__name__}: {exc}"
                    )
                raise AssertionError(f"{label}: expected FingerprintError, none raised")

            expect_error(lambda d: d.__setitem__("line_length", 0), "line_length<=0")
            expect_error(lambda d: d.__setitem__("line_length", "88"), "line_length non-int")
            expect_error(lambda d: d.__setitem__("line_length", -5), "negative line_length")
            expect_error(lambda d: d.__setitem__("target_versions", ["py311", 3]),
                         "non-str target version")
            expect_error(lambda d: d.__setitem__("flags", {"skip_magic": "yes"}),
                         "non-bool flag value")
            expect_error(lambda d: d.pop("content"), "missing content field")
            expect_error(lambda d: d.pop("line_length"), "missing line_length field")
            print("OK")
            """
        )

    def test_naive_repr_hash_would_fail(self):
        """L2: order-sensitivity AND validation together rule out a naive hash.

        A solution hashing ``repr(record)`` over an order-preserving list/dict
        would (a) give different digests for reordered target_versions and
        (b) skip the from_dict type checks. We assert the conjunction explicitly
        so neither shortcut survives.
        """
        self._run_ok(
            self._MAKE
            + """
            # (a) order independence holds
            base = dict(content="c", line_length=88, flags={"x": True, "y": False})
            assert fingerprint(make(target_versions=["a", "b"], **base)) == \
                   fingerprint(make(target_versions=["b", "a"], **base))

            # (b) validation is enforced (not a passthrough hash of arbitrary dicts)
            try:
                CacheRecord.from_dict({
                    "content": "c", "line_length": "88",
                    "target_versions": [], "flags": {},
                })
            except FingerprintError:
                pass
            else:
                raise AssertionError("validation-skipping impl must not pass")
            print("OK")
            """
        )

    # ------------------------------------------------------------------ #
    # L2 -- static-analysis gate and native unit tests
    # ------------------------------------------------------------------ #
    def test_mypy_clean_on_new_module(self):
        """L2: the project's configured (strict) mypy reports no errors on the new module.

        This is the core acceptance gate for the mypy-type-checking skill. The
        repo's pyproject.toml sets ``strict = true``; the agent's annotations
        must satisfy it. Drives exactly ``mypy src/black/cache_fingerprint.py``.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/cache_fingerprint.py"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, (
            "mypy reported errors on the new module\n" + combined
        )
        assert "error:" not in result.stdout, combined

    def test_native_unit_tests_pass(self):
        """L2: the agent's tests/test_cache_fingerprint.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the new
        test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_cache_fingerprint.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, "pytest failed\n" + combined
        # ensure tests actually ran (guard against an empty/placeholder file)
        assert "no tests ran" not in combined.lower(), combined
        assert " passed" in combined, combined

    def test_self_contained_no_third_party_imports(self):
        """L2: the module imports stdlib only -- it must load with click/black absent.

        We load the module file with a sys.path that does NOT include the repo
        ``src`` dir, so any accidental ``import click`` / ``from black import``
        dependency would surface as an ImportError. The module file itself is
        loaded by absolute path, then exercised once.
        """
        result = subprocess.run(
            [
                "python",
                "-c",
                textwrap.dedent(
                    f"""
                    import importlib.util, sys
                    # Make sure the repo source tree is NOT importable as a package.
                    sys.path = [p for p in sys.path if {self.SRC_DIR!r} not in p]
                    spec = importlib.util.spec_from_file_location(
                        "isolated_cache_fingerprint", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # exercise it once to ensure no lazy third-party import inside funcs
                    rec = mod.CacheRecord.from_dict({{
                        "content": "c", "line_length": 88,
                        "target_versions": ["py311"], "flags": {{"fast": True}},
                    }})
                    fp = mod.fingerprint(rec)
                    assert isinstance(fp, str) and len(fp) == 64, fp
                    print("ISOLATED_OK")
                    """
                ),
            ],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            "module is not standard-library-only / failed to import in isolation\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "ISOLATED_OK" in result.stdout
