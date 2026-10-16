"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext6).

Task: Add a `QuerySnippet.search(org, term)` classmethod to redash's ORM model
(`redash/models/__init__.py`) that returns the org's `QuerySnippet` rows whose
`trigger` OR `description` contains `term` as a CASE-INSENSITIVE substring,
scoped to the given org, with each matching row appearing at most once.

Verification strategy
---------------------
L1 checks confirm the deliverable files exist, the classmethod is defined on the
`QuerySnippet` class with the exact required signature `(cls, org, term)` and the
`@classmethod` decorator (verified via AST, not substring grep), and the modified
module imports cleanly.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting any test
the agent may have written, we drop our OWN focused pytest driver modules into
the repo's `tests/models/` directory (so they pick up the real DB-backed
`tests.BaseTestCase` + `self.factory`), seed `QuerySnippet` rows directly via the
ORM factory, call `QuerySnippet.search(org, term)`, and assert on the concrete
returned rows. Each driver runs under the repo's native `pytest`; we assert on
returncode + behavior.

A naive solution (returning all snippets, a hardcoded list, case-sensitive
matching, matching only on `trigger`, leaking other-org snippets, or emitting a
matching row twice when both fields match) fails these tests.

Native acceptance command (from the task's Acceptance Criteria):
    pytest tests/models/test_query_snippets.py
"""

import ast
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/redash"
MODELS_FILE = os.path.join(REPO_DIR, "redash", "models", "__init__.py")
MODELS_TESTS_DIR = os.path.join(REPO_DIR, "tests", "models")
AGENT_TEST_FILE = os.path.join(MODELS_TESTS_DIR, "test_query_snippets.py")

# Files we inject into the repo so we can clean them up afterwards.
_INJECTED = []


def _write_driver(name, body):
    """Write a pytest driver module into tests/models/ and remember it."""
    path = os.path.join(MODELS_TESTS_DIR, name)
    with open(path, "w") as fh:
        fh.write(body)
    _INJECTED.append(path)
    return path


def _run_pytest(target, timeout=600, extra=None):
    """Run the repo's native pytest against `target` (path relative to REPO_DIR)."""
    cmd = ["python", "-m", "pytest", target, "-v", "--tb=short", "-p", "no:cacheprovider"]
    if extra:
        cmd.extend(extra)
    env = dict(os.environ)
    # Ensure the repo itself is importable regardless of how we were invoked.
    env["PYTHONPATH"] = REPO_DIR
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


@pytest.fixture(scope="module", autouse=True)
def _cleanup_injected():
    """Remove any driver modules we injected once the module's tests finish."""
    yield
    for path in _INJECTED:
        try:
            os.remove(path)
        except OSError:
            pass
    pycache = os.path.join(MODELS_TESTS_DIR, "__pycache__")
    if os.path.isdir(pycache):
        for f in os.listdir(pycache):
            if "snip_search_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios.
#
# NOTE: QuerySnippet.trigger has a UNIQUE constraint at the DB level, so every
# snippet we create MUST be given a globally distinct `trigger`. We expose a
# `snip()` helper that requires an explicit trigger and lets description vary.
_PREAMBLE = '''\
from redash.models import QuerySnippet, db
from tests import BaseTestCase


class _SnipSearchBase(BaseTestCase):
    def snip(self, trigger, description="", org=None, user=None):
        org = org if org is not None else self.factory.org
        user = user if user is not None else self.factory.user
        s = self.factory.create_query_snippet(
            trigger=trigger, description=description, org=org, user=user
        )
        db.session.flush()
        return s

    def triggers(self, org, term):
        return sorted(s.trigger for s in QuerySnippet.search(org, term))

    def ids(self, org, term):
        return [s.id for s in QuerySnippet.search(org, term)]
'''


class TestSqlalchemyOrmPatterns:
    REPO_DIR = "/workspace/redash"

    # ------------------------------------------------------------------ L1

    def test_models_file_exists(self):
        """L1: the model module to be modified exists."""
        assert os.path.isfile(MODELS_FILE), f"missing {MODELS_FILE}"

    def test_agent_test_file_present(self):
        """L1: the new deliverable test module exists for the native run."""
        assert os.path.isdir(MODELS_TESTS_DIR), f"missing {MODELS_TESTS_DIR}"
        assert os.path.isfile(AGENT_TEST_FILE), (
            "tests/models/test_query_snippets.py must be created by the agent"
        )

    def test_search_classmethod_signature(self):
        """L1: `search` is defined on the QuerySnippet class as a @classmethod
        taking exactly (cls, org, term) -- verified via AST, not substring grep."""
        with open(MODELS_FILE) as fh:
            tree = ast.parse(fh.read())

        snippet_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "QuerySnippet":
                snippet_cls = node
                break
        assert snippet_cls is not None, "class QuerySnippet not found in models"

        method = None
        for item in snippet_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "search":
                method = item
                break
        assert method is not None, "QuerySnippet.search method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, "search must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "org", "term"], (
            f"search signature must be (cls, org, term); got {argnames}"
        )

    def test_models_module_imports(self):
        """L1: the modified models module imports cleanly (no syntax/import error)."""
        proc = subprocess.run(
            ["python", "-c", "import redash.models"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": REPO_DIR},
        )
        assert proc.returncode == 0, (
            "importing redash.models failed:\n" + proc.stdout + proc.stderr
        )

    # ------------------------------------------------------------------ L2

    def test_substring_match_on_trigger_and_description(self):
        """L2: a substring `term` matches on trigger OR description.

        trigger 'sum_sales' and a *different* snippet whose description contains
        'SUMmary' both match 'sum'. A solution that only searches `trigger`
        (or only `description`) fails here."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchBoth(_SnipSearchBase):
                def test_trigger_or_description(self):
                    org = self.factory.org
                    self.snip("sum_sales", description="totals report")
                    self.snip("monthly_report", description="A SUMmary of things")
                    self.snip("unrelated", description="nothing here")
                    assert self.triggers(org, "sum") == ["monthly_report", "sum_sales"], \\
                        self.triggers(org, "sum")
        ''')
        _write_driver("test_snip_search_driver_both.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_both.py")
        assert proc.returncode == 0, (
            "trigger-or-description substring match failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_case_insensitive_match(self):
        """L2: matching is case-insensitive; 'SUM' and 'sum' return the same set.

        A case-sensitive `LIKE`/Python `in` solution fails the uppercase query."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchCase(_SnipSearchBase):
                def test_upper_equals_lower(self):
                    org = self.factory.org
                    self.snip("sum_sales", description="totals")
                    self.snip("rep_x", description="A SUMmary")
                    lower = self.triggers(org, "sum")
                    upper = self.triggers(org, "SUM")
                    mixed = self.triggers(org, "SuM")
                    assert lower == ["rep_x", "sum_sales"], lower
                    assert upper == lower, (upper, lower)
                    assert mixed == lower, (mixed, lower)
        ''')
        _write_driver("test_snip_search_driver_case.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_case.py")
        assert proc.returncode == 0, (
            "case-insensitive match failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_org_scoping(self):
        """L2: only snippets of the given org appear; a matching snippet in a
        different org must never leak in.

        Discriminates a solution that ignores the `org` argument."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchOrg(_SnipSearchBase):
                def test_other_org_excluded(self):
                    org = self.factory.org
                    other = self.factory.create_org(name="Other", slug="other-org")
                    self.snip("sum_here", description="x", org=org)
                    # Same matching term but a different org -> must be excluded.
                    self.snip("sum_there", description="y", org=other)
                    assert self.triggers(org, "sum") == ["sum_here"], \\
                        self.triggers(org, "sum")
                    # And searching the OTHER org returns only its own snippet.
                    assert self.triggers(other, "sum") == ["sum_there"], \\
                        self.triggers(other, "sum")
        ''')
        _write_driver("test_snip_search_driver_org.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_org.py")
        assert proc.returncode == 0, (
            "org scoping failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_match_both_fields_appears_once(self):
        """L2: a snippet whose trigger AND description both match the term must
        appear exactly once (no duplicate row from an OR-join)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchOnce(_SnipSearchBase):
                def test_no_duplicate(self):
                    org = self.factory.org
                    s = self.snip("sum_both", description="this is a summary")
                    ids = self.ids(org, "sum")
                    assert ids == [s.id], ids
                    assert len(ids) == 1, ids
                    # And in a mixed set, the dual-match row still counted once.
                    self.snip("other_sum", description="plain")
                    triggers = self.triggers(org, "sum")
                    assert triggers == ["other_sum", "sum_both"], triggers
        ''')
        _write_driver("test_snip_search_driver_once.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_once.py")
        assert proc.returncode == 0, (
            "dedup-on-both-fields failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_non_matching_term_empty(self):
        """L2: a term that matches nothing yields an empty list (not all rows).

        Discriminates a stub that returns `cls.all(org)` regardless of term."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchEmpty(_SnipSearchBase):
                def test_no_match(self):
                    org = self.factory.org
                    self.snip("alpha", description="first")
                    self.snip("beta", description="second")
                    assert list(QuerySnippet.search(org, "zzz_nomatch")) == [], \\
                        list(QuerySnippet.search(org, "zzz_nomatch"))
        ''')
        _write_driver("test_snip_search_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_empty.py")
        assert proc.returncode == 0, (
            "non-matching term should be empty:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_term_matches_all_in_org(self):
        """L2: an empty term matches every snippet in the org (empty string is a
        substring of any string), and ONLY those in the given org."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchEmptyTerm(_SnipSearchBase):
                def test_empty_term(self):
                    org = self.factory.org
                    other = self.factory.create_org(name="Other2", slug="other2-org")
                    self.snip("a_one", description="d1", org=org)
                    self.snip("a_two", description="d2", org=org)
                    self.snip("b_one", description="d3", org=other)
                    assert self.triggers(org, "") == ["a_one", "a_two"], \\
                        self.triggers(org, "")
                    assert self.triggers(other, "") == ["b_one"], \\
                        self.triggers(other, "")
        ''')
        _write_driver("test_snip_search_driver_emptyterm.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_emptyterm.py")
        assert proc.returncode == 0, (
            "empty-term-matches-all-in-org failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_partial_substring_not_just_equality(self):
        """L2: the match is a SUBSTRING match, not whole-field equality.

        'ale' must match trigger 'sum_sales' (substring inside 'sales')."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchPartial(_SnipSearchBase):
                def test_partial(self):
                    org = self.factory.org
                    self.snip("sum_sales", description="numbers")
                    self.snip("inventory", description="stock levels")
                    assert self.triggers(org, "ale") == ["sum_sales"], \\
                        self.triggers(org, "ale")
                    # substring inside description too.
                    assert self.triggers(org, "lev") == ["inventory"], \\
                        self.triggers(org, "lev")
        ''')
        _write_driver("test_snip_search_driver_partial.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_partial.py")
        assert proc.returncode == 0, (
            "partial substring match failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_query_snippet_objects(self):
        """L2: results are real QuerySnippet ORM instances (have trigger/
        description/org_id), and list(...) is the supported wrapper."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchShape(_SnipSearchBase):
                def test_shape(self):
                    org = self.factory.org
                    self.snip("sum_sales", description="totals")
                    res = list(QuerySnippet.search(org, "sum"))
                    assert len(res) == 1, res
                    row = res[0]
                    assert isinstance(row, QuerySnippet), type(row)
                    assert row.trigger == "sum_sales", row.trigger
                    assert row.org_id == org.id, (row.org_id, org.id)
        ''')
        _write_driver("test_snip_search_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_shape.py")
        assert proc.returncode == 0, (
            "result shape / type check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: search is read-only and repeatable -- repeated calls give the same
        result and never change the underlying snippet row count."""
        driver = _PREAMBLE + textwrap.dedent('''
            class SnipSearchReadOnly(_SnipSearchBase):
                def test_read_only(self):
                    org = self.factory.org
                    self.snip("sum_sales", description="totals")
                    self.snip("rep_x", description="A SUMmary")
                    self.snip("other", description="nope")
                    before = QuerySnippet.query.count()
                    r1 = self.triggers(org, "sum")
                    r2 = self.triggers(org, "sum")
                    r3 = self.triggers(org, "sum")
                    assert r1 == r2 == r3 == ["rep_x", "sum_sales"], (r1, r2, r3)
                    assert QuerySnippet.query.count() == before, "row count changed"
        ''')
        _write_driver("test_snip_search_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_snip_search_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_native_command(self):
        """L2: the agent's own tests/models/test_query_snippets.py must pass under
        the native command from the task's Acceptance Criteria
        (`pytest tests/models/test_query_snippets.py`).

        We require at least one test to have been collected & passed (no
        rubber-stamp empty collection)."""
        proc = _run_pytest("tests/models/test_query_snippets.py", timeout=600)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's test_query_snippets.py did not pass:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "no test was collected in test_query_snippets.py:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing test in test_query_snippets.py:\n" + out[-2000:]
        )
