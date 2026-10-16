"""Tests for skill: mypy-type-checking (task: Add a Bracket-Balance Scanner).

The agent must create a self-contained, standard-library-only module
``src/black/bracket_scan.py`` inside the ``black`` repository exposing exactly
``max_depth``, ``is_balanced`` and ``BracketError`` (a subclass of
``ValueError``), plus a deterministic unit-test file
``tests/test_bracket_scan.py``.

This suite verifies the deliverable from two angles:

* L1 -- the deliverable files exist and are minimally well-formed, and the
  required public surface imports with the correct shapes.
* L2 -- the runtime behaviour of the scanner is exercised independently by
  driving the module through a fresh Python subprocess with our OWN
  verification harness (so a naive solution that merely counts opens vs. closes,
  ignores LIFO pair matching, or ignores string literals fails), the project's
  configured ``mypy`` static-analysis gate is run over the new module, and the
  agent-authored pytest file is executed with the native toolchain.

The module is intentionally imported directly from its file location (and also
via the canonical ``black.bracket_scan`` package path) so that the heavy,
optional third-party dependencies of the top-level ``black`` package never gate
these behavioural checks.

Native acceptance command driven by L2:
    python -m pytest tests/test_bracket_scan.py -q
and the static gate:
    python -m mypy src/black/bracket_scan.py
"""

import os
import subprocess
import textwrap


class TestMypyTypeChecking:
    REPO_DIR = "/workspace/black"

    MODULE_PATH = os.path.join(REPO_DIR, "src", "black", "bracket_scan.py")
    TEST_PATH = os.path.join(REPO_DIR, "tests", "test_bracket_scan.py")
    SRC_DIR = os.path.join(REPO_DIR, "src")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Run a Python snippet that imports the scanner module directly.

        The module file is loaded by path via importlib so that we do NOT pull
        in the (heavy, optional-dependency-laden) top-level ``black`` package.
        ``max_depth``/``is_balanced``/``BracketError`` are injected into the
        snippet's globals.
        """
        preamble = textwrap.dedent(
            """
            import importlib.util, sys, os
            _mod_path = {module_path!r}
            spec = importlib.util.spec_from_file_location("_bracket_scan_probe", _mod_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            max_depth = mod.max_depth
            is_balanced = mod.is_balanced
            BracketError = mod.BracketError
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

    # ------------------------------------------------------------------ #
    # L1 -- deliverables exist and are well-formed
    # ------------------------------------------------------------------ #
    def test_module_file_exists(self):
        """L1: the new scanner module file is created at the required path."""
        assert os.path.isfile(self.MODULE_PATH), (
            f"expected scanner module at {self.MODULE_PATH}"
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

        Also asserts BracketError is a subclass of ValueError, as required.
        """
        result = self._run_ok(
            """
            assert callable(max_depth)
            assert callable(is_balanced)
            assert isinstance(BracketError, type)
            assert issubclass(BracketError, ValueError)
            print("OK")
            """
        )
        assert "OK" in result.stdout

    def test_canonical_package_import_path(self):
        """L1->L2: ``from black.bracket_scan import ...`` succeeds via the src path.

        The module is required to be importable through the ``black`` package
        namespace WITHOUT importing the (heavy) top-level ``black`` package
        machinery; it is stdlib-only, so a direct submodule import must work.
        """
        script = (
            "from black.bracket_scan import max_depth, is_balanced, BracketError\n"
            "assert issubclass(BracketError, ValueError)\n"
            "assert is_balanced('f(x)') is True\n"
            "assert max_depth('f(x)') == 1\n"
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
    # L2 -- runtime behaviour driven by our own harness
    # ------------------------------------------------------------------ #
    def test_is_balanced_truth_table(self):
        """L2: is_balanced returns the documented bool for the spec's examples.

        Drives every row of the doc's Expected Functionality table plus the
        edge cases. ``is_balanced`` must never raise -- it returns False for
        mismatched/unterminated input.
        """
        self._run_ok(
            """
            balanced = [
                "f(x)",
                "a[b[c]]",
                "{[()]}",
                "()()",
                "plain text",
                '"(" + ")"',
                'a = "([{"',
                'a = "x\\\\"(y)"',
                "",
            ]
            for t in balanced:
                r = is_balanced(t)
                assert r is True, ("expected balanced", t, r)

            unbalanced = [
                "f(x]",          # mismatched pair
                "(",             # unclosed
                ")(",            # stray close before open
                "([)]",          # interleaved / wrong LIFO order
                "a]b",           # stray close
                "{",             # unclosed brace
                'a = "([{',      # unterminated string literal
            ]
            for t in unbalanced:
                r = is_balanced(t)
                assert r is False, ("expected NOT balanced", t, r)
            print("OK")
            """
        )

    def test_max_depth_values(self):
        """L2: max_depth returns the exact nesting depth for balanced inputs.

        A naive opens-minus-closes counter that does not track the running
        maximum, or that mishandles sequential sibling groups, fails here.
        """
        self._run_ok(
            """
            cases = {
                "f(x)": 1,
                "a[b[c]]": 2,
                "{[()]}": 3,
                "()()": 1,
                "plain text": 0,
                '"(" + ")"': 0,
                'a = "([{"': 0,
                'a = "x\\\\"(y)"': 0,
                "": 0,
                "(())": 2,
                "()(())": 2,        # max over siblings, not a running sum
                "(()())": 2,
                "f(g(h(x)))": 3,
            }
            for text, want in cases.items():
                got = max_depth(text)
                assert got == want, (text, "want", want, "got", got)
                assert type(got) is int, (text, type(got))
                assert got >= 0
            print("OK")
            """
        )

    def test_max_depth_raises_on_imbalance(self):
        """L2: max_depth raises BracketError on every imbalanced/unterminated input.

        Covers the doc's three required raising inputs (``f(x]``, ``(``, ``)(``)
        plus interleaving, stray close, and an unterminated string literal.
        """
        self._run_ok(
            """
            raising = [
                "f(x]",
                "(",
                ")(",
                "([)]",
                "a]b",
                "{[(",
                'a = "([{',     # unterminated string literal
            ]
            for text in raising:
                try:
                    max_depth(text)
                except BracketError:
                    pass
                else:
                    raise AssertionError(f"max_depth({text!r}) must raise BracketError")
            print("OK")
            """
        )

    def test_string_literals_ignored(self):
        """L2: bracket chars inside string literals are ignored (single & double quoted).

        A naive scanner that does not skip string contents would see the inner
        brackets and report a wrong depth or a false imbalance.
        """
        self._run_ok(
            """
            # brackets entirely inside strings contribute nothing
            assert is_balanced('s = "(((("') is True
            assert max_depth('s = "(((("') == 0
            assert is_balanced("s = '][)('") is True
            assert max_depth("s = '][)('") == 0

            # a real bracket OUTSIDE the string still counts
            assert is_balanced('("(")') is True
            assert max_depth('("(")') == 1

            # mismatched brackets inside a string do NOT unbalance the text
            assert is_balanced('x = ")(" ') is True
            assert max_depth('x = ")(" ') == 0

            # a double-quoted string nested-looking inside parens: real parens count
            assert is_balanced('f("a)b")') is True
            assert max_depth('f("a)b")') == 1
            print("OK")
            """
        )

    def test_escaped_quote_inside_string(self):
        """L2: a backslash-escaped quote does not terminate the string literal.

        ``a = "x\\"(y)"`` is one continuous string, so the ``(`` and ``)`` are
        inside it and the text is balanced at depth 0. A scanner that treats the
        escaped quote as a real string terminator would wrongly count them.
        """
        self._run_ok(
            r"""
            text = 'a = "x\\"(y)"'
            assert is_balanced(text) is True, text
            assert max_depth(text) == 0, (text, max_depth(text))

            # escaped quote inside single-quoted string, likewise
            text2 = "a = 'p\\'[q]'"
            assert is_balanced(text2) is True, text2
            assert max_depth(text2) == 0, (text2, max_depth(text2))

            # but a real bracket after the closed string is counted
            text3 = 'a = "z\\"" (w)'
            assert is_balanced(text3) is True, text3
            assert max_depth(text3) == 1, (text3, max_depth(text3))
            print("OK")
            """
        )

    def test_lifo_matching_not_just_counting(self):
        """L2: closing brackets must match the most recent open (proper LIFO).

        This is the central discriminator: ``([)]`` and ``{(})`` have equal
        open/close counts per type but are NOT correctly nested. A count-only
        implementation would call them balanced -- it must not.
        """
        self._run_ok(
            """
            for bad in ("([)]", "{(})", "[(])", "(}", "{)", "[}"):
                assert is_balanced(bad) is False, ("must be unbalanced", bad)
                try:
                    max_depth(bad)
                except BracketError:
                    pass
                else:
                    raise AssertionError(f"max_depth({bad!r}) must raise")

            # equal counts overall but wrong order across types
            assert is_balanced("([)]") is False
            # correctly nested mixes are fine
            assert is_balanced("([{}])") is True
            assert max_depth("([{}])") == 3
            print("OK")
            """
        )

    def test_return_types_are_exact(self):
        """L2: is_balanced returns real bools and max_depth returns ints.

        Guards against an implementation that returns truthy/falsey non-bool
        values (e.g. 0/1 or None) from is_balanced, or a non-int depth.
        """
        self._run_ok(
            """
            for t in ("f(x)", "(", "([)]", "plain"):
                r = is_balanced(t)
                assert type(r) is bool, (t, type(r))

            for t in ("f(x)", "{[()]}", "plain text", ""):
                d = max_depth(t)
                assert type(d) is int, (t, type(d))
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
        must satisfy it. Runs exactly the doc's static command.
        """
        result = subprocess.run(
            ["python", "-m", "mypy", "src/black/bracket_scan.py"],
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
        """L2: the agent's tests/test_bracket_scan.py passes under pytest.

        Runs exactly the command from the Acceptance Criteria, scoped to the
        new test file, and asserts a non-empty passing collection.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_bracket_scan.py", "-q"],
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

    def test_native_tests_have_enough_cases(self):
        """L2: the agent's test file contains >= 12 independent collected cases.

        The Acceptance Criteria require at least 12 independent test cases
        (parametrized cases count individually). We collect with pytest and
        count the actually-collected node ids rather than trusting source text.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_bracket_scan.py",
             "--collect-only", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 0, "collection failed\n" + combined
        node_lines = [
            ln for ln in result.stdout.splitlines()
            if "::" in ln and "test_bracket_scan.py" in ln
        ]
        assert len(node_lines) >= 12, (
            f"expected >= 12 collected test cases, got {len(node_lines)}\n"
            + combined
        )

    def test_self_contained_no_third_party_imports(self):
        """L2: the module imports stdlib only -- it must load with black/click absent.

        We load the module file with a sys.path that does NOT include the repo
        ``src`` dir, so any accidental ``from black import`` / third-party
        dependency would surface as an ImportError. The module file itself is
        loaded by absolute path.
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
                        "isolated_bracket_scan", {self.MODULE_PATH!r}
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # exercise it once to ensure no lazy third-party import inside funcs
                    assert mod.is_balanced("f(x)") is True
                    assert mod.max_depth("a[b[c]]") == 2
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
