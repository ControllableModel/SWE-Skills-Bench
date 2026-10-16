"""Tests for the ``pandas-dataframe-patterns`` skill task (variant ext10).

The ext10 task asks the agent to create ``scripts/sessionize.py`` inside the
pandas repository: a clickstream *sessionization* utility exposing three public
functions that group raw web events into per-user sessions and summarize them:

    * ``assign_sessions(events, timeout_minutes)`` — label each event with a
      per-user ``session_id`` that restarts at 0 for each user and increments
      whenever the inter-event gap strictly exceeds ``timeout_minutes``.
    * ``session_summary(events_with_sessions)`` — one flat row per
      ``(user_id, session_id)`` with ``event_count``, ``duration_minutes`` and
      ``start``.
    * ``entry_pages(events_with_sessions)`` — for each landing page, how many
      sessions began on it, sorted by count desc then page asc.

These tests verify the *behaviour* of the agent's module dynamically. Each L2
case drives the real functions through a subprocess (so the installed pandas is
used, not the unbuilt repo source tree) and deep-validates session boundaries,
per-user numbering restart, gap/strict-timeout semantics, summary arithmetic,
ordering, flat contiguous indexing, and the "do not mutate the input" contracts.

A naive solution that merely creates files, hardcodes session ids, ignores the
``timeout_minutes`` argument, numbers sessions globally instead of per user,
uses ``>=`` instead of strict ``>`` for the gap, returns a grouped/MultiIndex
frame instead of a flat reset-index frame, or mutates its input WILL fail.
"""

import json
import os
import subprocess
import tempfile
import textwrap


class TestPandasDataframePatterns:
    REPO_DIR = "/workspace/pandas"

    MODULE_REL = os.path.join("scripts", "sessionize.py")
    TEST_REL = os.path.join("scripts", "tests", "test_sessionize.py")

    # ---- helpers ---------------------------------------------------------

    def _module_path(self):
        return os.path.join(self.REPO_DIR, self.MODULE_REL)

    def _run_driver(self, body, timeout=120):
        """Run a python snippet that imports the agent's sessionize module.

        The driver runs from a clean temporary cwd (NOT the repo root) so that
        ``import pandas`` resolves to the installed/built pandas instead of the
        repository's source tree. The agent's ``scripts`` directory is put on
        sys.path so ``import sessionize`` finds the deliverable. The snippet is
        expected to ``print`` a single JSON line as its final output.
        """
        scripts_dir = os.path.join(self.REPO_DIR, "scripts")
        assert os.path.isfile(self._module_path()), (
            "scripts/sessionize.py does not exist; agent did not create the "
            "deliverable module."
        )
        header = textwrap.dedent(
            f"""
            import sys, json
            sys.path.insert(0, {scripts_dir!r})
            import pandas as pd
            import numpy as np
            import sessionize as sz
            """
        )
        # Dedent each \f-separated chunk independently so a flush-left literal
        # may be concatenated with an indented body without losing indentation.
        body_src = "\n".join(textwrap.dedent(part) for part in body.split("\f"))
        src = header + body_src
        with tempfile.TemporaryDirectory() as workdir:
            script_path = os.path.join(workdir, "driver_snippet.py")
            with open(script_path, "w") as fh:
                fh.write(src)
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            proc = subprocess.run(
                ["python", script_path],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        return proc

    def _run_json(self, body, timeout=120):
        proc = self._run_driver(body, timeout=timeout)
        assert proc.returncode == 0, (
            "driver exited non-zero.\nSTDOUT:\n"
            + proc.stdout
            + "\nSTDERR:\n"
            + proc.stderr
        )
        last = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert last, "driver produced no stdout.\nSTDERR:\n" + proc.stderr
        try:
            return json.loads(last[-1])
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise AssertionError(
                f"final stdout line was not JSON: {last[-1]!r}\nSTDERR:\n{proc.stderr}"
            ) from exc

    # A reusable sample dataset literal. user 1 has gaps of 10 then 40 minutes
    # (timeout 30 -> sessions 0,0,1); user 2 is a single event.
    SAMPLE = textwrap.dedent(
        """
        events = pd.DataFrame({
            'user_id':   [1, 1, 1, 2],
            'timestamp': ['2023-01-01 10:00:00',
                          '2023-01-01 10:10:00',
                          '2023-01-01 10:50:00',
                          '2023-01-01 09:00:00'],
            'page':      ['home', 'cart', 'home', 'home'],
        })
        """
    )

    # ---- L1: deliverables exist & minimally well-formed ------------------

    def test_module_file_exists(self):
        """L1: scripts/sessionize.py must exist."""
        assert os.path.isfile(self._module_path()), (
            f"missing deliverable: {self._module_path()}"
        )

    def test_test_file_exists(self):
        """L1: scripts/tests/test_sessionize.py must exist."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, self.TEST_REL)), (
            "missing deliverable test file scripts/tests/test_sessionize.py"
        )

    def test_public_functions_present(self):
        """L1: the three required public functions are importable callables."""
        out = self._run_json(
            """
            names = ['assign_sessions', 'session_summary', 'entry_pages']
            res = {n: callable(getattr(sz, n, None)) for n in names}
            print(json.dumps(res))
            """
        )
        for name, ok in out.items():
            assert ok, f"sessionize.{name} is missing or not callable"

    # ---- L2: assign_sessions --------------------------------------------

    def test_assign_sessions_spec_example(self):
        """L2: gaps 10 then 40 min with timeout 30 -> sessions 0, 0, 1 for user 1."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            res = sz.assign_sessions(events, 30)
            # rows for user 1 in chronological order
            u1 = res[res['user_id'] == 1].sort_values('timestamp')
            sids = [int(x) for x in u1['session_id'].tolist()]
            pages = list(u1['page'])
            # user 2 single event
            u2 = res[res['user_id'] == 2]
            u2_sids = [int(x) for x in u2['session_id'].tolist()]
            print(json.dumps({
                'u1_sids': sids,
                'u1_pages': pages,
                'u2_sids': u2_sids,
                'n': int(len(res)),
                'has_col': 'session_id' in res.columns,
            }))
            """
        )
        assert out["has_col"], "result must add a session_id column"
        assert out["n"] == 4, "assign_sessions must keep every event row"
        assert out["u1_sids"] == [0, 0, 1], (
            "10-min gap stays in session 0; 40-min gap (> 30) opens session 1"
        )
        assert out["u1_pages"] == ["home", "cart", "home"]
        assert out["u2_sids"] == [0], "first event of each user is session 0"

    def test_assign_sessions_numbering_restarts_per_user(self):
        """L2: session_id restarts at 0 for every user (not a global counter)."""
        out = self._run_json(
            """
            events = pd.DataFrame({
                'user_id':   [1, 1, 2, 2],
                'timestamp': ['2023-01-01 10:00:00', '2023-01-01 12:00:00',
                              '2023-01-01 08:00:00', '2023-01-01 08:05:00'],
                'page':      ['a', 'b', 'c', 'd'],
            })
            res = sz.assign_sessions(events, 30)
            by_user = {}
            for uid in (1, 2):
                sub = res[res['user_id'] == uid].sort_values('timestamp')
                by_user[uid] = [int(x) for x in sub['session_id'].tolist()]
            print(json.dumps({
                'u1': by_user[1],
                'u2': by_user[2],
            }))
            """
        )
        # user 1: 2-hour gap (>30) -> 0,1 ; user 2: 5-min gap -> 0,0
        assert out["u1"] == [0, 1], "user 1 sessions wrong"
        assert out["u2"] == [0, 0], (
            "user 2 must restart numbering at 0 (5-min gap stays in session 0)"
        )

    def test_assign_sessions_strict_timeout_boundary(self):
        """L2: gap exactly == timeout stays in the same session (strict '>')."""
        out = self._run_json(
            """
            # exact 30-minute gap must NOT start a new session
            events = pd.DataFrame({
                'user_id':   [1, 1],
                'timestamp': ['2023-01-01 10:00:00', '2023-01-01 10:30:00'],
                'page':      ['a', 'b'],
            })
            exact = sz.assign_sessions(events, 30)
            exact_sids = [int(x) for x in
                          exact.sort_values('timestamp')['session_id'].tolist()]
            # a hair over 30 minutes -> new session
            events2 = pd.DataFrame({
                'user_id':   [1, 1],
                'timestamp': ['2023-01-01 10:00:00', '2023-01-01 10:30:01'],
                'page':      ['a', 'b'],
            })
            over = sz.assign_sessions(events2, 30)
            over_sids = [int(x) for x in
                         over.sort_values('timestamp')['session_id'].tolist()]
            print(json.dumps({'exact': exact_sids, 'over': over_sids}))
            """
        )
        assert out["exact"] == [0, 0], (
            "a gap equal to timeout_minutes must NOT open a new session (strict >)"
        )
        assert out["over"] == [0, 1], (
            "a gap strictly greater than timeout_minutes must open a new session"
        )

    def test_assign_sessions_respects_timeout_argument(self):
        """L2: the timeout_minutes argument actually drives boundaries.

        Same data with a large timeout collapses into one session; with a small
        timeout it splits. A stub that ignores the argument fails this.
        """
        out = self._run_json(
            """
            events = pd.DataFrame({
                'user_id':   [1, 1, 1],
                'timestamp': ['2023-01-01 10:00:00', '2023-01-01 10:20:00',
                              '2023-01-01 10:45:00'],
                'page':      ['a', 'b', 'c'],
            })
            small = sz.assign_sessions(events, 15)
            big = sz.assign_sessions(events, 600)
            small_sids = [int(x) for x in
                          small.sort_values('timestamp')['session_id'].tolist()]
            big_sids = [int(x) for x in
                        big.sort_values('timestamp')['session_id'].tolist()]
            print(json.dumps({
                'small': small_sids,
                'small_n': len(set(small_sids)),
                'big': big_sids,
                'big_n': len(set(big_sids)),
            }))
            """
        )
        # gaps are 20 and 25 minutes; both exceed 15 -> three sessions
        assert out["small"] == [0, 1, 2], "timeout=15 must split each 20/25-min gap"
        # timeout 600 -> everything in one session
        assert out["big"] == [0, 0, 0], "timeout=600 must keep all events in one session"
        assert out["big_n"] == 1 and out["small_n"] == 3

    def test_assign_sessions_output_sorted_and_reindexed(self):
        """L2: output sorted by user_id then timestamp, index reset to 0..n-1."""
        out = self._run_json(
            """
            # deliberately shuffled input order
            events = pd.DataFrame({
                'user_id':   [2, 1, 2, 1],
                'timestamp': ['2023-01-01 09:05:00', '2023-01-01 10:10:00',
                              '2023-01-01 09:00:00', '2023-01-01 10:00:00'],
                'page':      ['w', 'x', 'y', 'z'],
            })
            res = sz.assign_sessions(events, 30)
            users = [int(u) for u in res['user_id'].tolist()]
            ts = [pd.Timestamp(t).strftime('%Y-%m-%d %H:%M:%S')
                  for t in pd.to_datetime(res['timestamp']).tolist()]
            print(json.dumps({
                'index': list(res.index),
                'users': users,
                'ts': ts,
            }))
            """
        )
        assert out["index"] == [0, 1, 2, 3], "index must be reset to 0..n-1"
        assert out["users"] == [1, 1, 2, 2], "rows must be sorted by user_id"
        # within each user, ascending timestamp
        assert out["ts"][0] < out["ts"][1], "user 1 rows must be ascending in time"
        assert out["ts"][2] < out["ts"][3], "user 2 rows must be ascending in time"

    def test_assign_sessions_does_not_mutate_input(self):
        """L2: the caller's events frame must be unchanged after the call."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            before_cols = list(events.columns)
            before_hash = pd.util.hash_pandas_object(events, index=True).sum()
            _ = sz.assign_sessions(events, 30)
            after_cols = list(events.columns)
            after_hash = pd.util.hash_pandas_object(events, index=True).sum()
            print(json.dumps({
                'cols_same': before_cols == after_cols,
                'hash_same': bool(before_hash == after_hash),
                'has_session_id': 'session_id' in events.columns,
            }))
            """
        )
        assert out["cols_same"], "assign_sessions must not change input columns"
        assert out["hash_same"], "assign_sessions must not alter input values"
        assert not out["has_session_id"], (
            "assign_sessions must not add session_id to the caller's frame"
        )

    # ---- L2: session_summary --------------------------------------------

    def test_session_summary_counts_and_duration(self):
        """L2: per-session event_count, duration_minutes and start are correct."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            assigned = sz.assign_sessions(events, 30)
            summ = sz.session_summary(assigned)
            cols = list(summ.columns)
            idx = list(summ.index)
            rows = []
            for _, r in summ.iterrows():
                rows.append({
                    'user_id': int(r['user_id']),
                    'session_id': int(r['session_id']),
                    'event_count': int(r['event_count']),
                    'duration_minutes': float(r['duration_minutes']),
                    'start': pd.Timestamp(r['start']).strftime('%Y-%m-%d %H:%M:%S'),
                })
            print(json.dumps({'cols': cols, 'index': idx, 'rows': rows}))
            """
        )
        for c in ("user_id", "session_id", "event_count", "duration_minutes", "start"):
            assert c in out["cols"], f"summary missing column {c}"
        assert out["index"] == [0, 1, 2], "summary index must be reset to 0..n-1"
        rows = out["rows"]
        keys = [(r["user_id"], r["session_id"]) for r in rows]
        assert keys == [(1, 0), (1, 1), (2, 0)], (
            f"summary not sorted by user then session / wrong groups: {keys}"
        )
        # user 1 session 0: events at 10:00 and 10:10 -> 2 events, 10 minutes
        s10 = rows[0]
        assert s10["event_count"] == 2
        assert s10["duration_minutes"] == 10.0
        assert s10["start"] == "2023-01-01 10:00:00"
        # user 1 session 1: single event at 10:50 -> duration 0.0
        s11 = rows[1]
        assert s11["event_count"] == 1
        assert s11["duration_minutes"] == 0.0
        assert s11["start"] == "2023-01-01 10:50:00"
        # user 2 session 0: single event -> duration 0.0
        s20 = rows[2]
        assert s20["event_count"] == 1
        assert s20["duration_minutes"] == 0.0

    def test_session_summary_single_event_duration_zero(self):
        """L2: every single-event session reports duration_minutes == 0.0 exactly."""
        out = self._run_json(
            """
            events = pd.DataFrame({
                'user_id':   [5, 6, 7],
                'timestamp': ['2023-02-01 00:00:00', '2023-02-01 01:00:00',
                              '2023-02-01 02:00:00'],
                'page':      ['a', 'b', 'c'],
            })
            assigned = sz.assign_sessions(events, 30)
            summ = sz.session_summary(assigned)
            durs = [float(x) for x in summ['duration_minutes'].tolist()]
            counts = [int(x) for x in summ['event_count'].tolist()]
            print(json.dumps({'durs': durs, 'counts': counts, 'n': int(len(summ))}))
            """
        )
        assert out["n"] == 3, "three distinct single-event users -> three sessions"
        assert out["durs"] == [0.0, 0.0, 0.0]
        assert out["counts"] == [1, 1, 1]

    def test_session_summary_does_not_mutate_input(self):
        """L2: session_summary must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            assigned = sz.assign_sessions(events, 30)
            before = pd.util.hash_pandas_object(assigned, index=True).sum()
            before_cols = list(assigned.columns)
            _ = sz.session_summary(assigned)
            after = pd.util.hash_pandas_object(assigned, index=True).sum()
            after_cols = list(assigned.columns)
            print(json.dumps({
                'hash_same': bool(before == after),
                'cols_same': before_cols == after_cols,
            }))
            """
        )
        assert out["hash_same"], "session_summary must not mutate its input"
        assert out["cols_same"], "session_summary must not change input columns"

    # ---- L2: entry_pages ------------------------------------------------

    def test_entry_pages_counts_landing_pages(self):
        """L2: counts of sessions whose first page is each landing page, sorted."""
        out = self._run_json(
            """
            # user 1: two sessions both landing on 'home'
            # user 2: one session landing on 'search'
            # user 3: one session landing on 'home'
            events = pd.DataFrame({
                'user_id':   [1, 1, 1, 2, 3],
                'timestamp': ['2023-01-01 10:00:00',   # home  (u1 s0 entry)
                              '2023-01-01 11:00:00',   # cart  (u1 s1 entry, >30 gap)
                              '2023-01-01 11:05:00',   # detail
                              '2023-01-01 09:00:00',   # search(u2 s0 entry)
                              '2023-01-01 08:00:00'],  # home  (u3 s0 entry)
                'page':      ['home', 'cart', 'detail', 'search', 'home'],
            })
            assigned = sz.assign_sessions(events, 30)
            ep = sz.entry_pages(assigned)
            cols = list(ep.columns)
            idx = list(ep.index)
            rows = [{'page': r['page'], 'sessions': int(r['sessions'])}
                    for _, r in ep.iterrows()]
            print(json.dumps({'cols': cols, 'index': idx, 'rows': rows}))
            """
        )
        assert "page" in out["cols"] and "sessions" in out["cols"], (
            "entry_pages must expose 'page' and 'sessions' columns"
        )
        assert out["index"] == list(range(len(out["rows"]))), (
            "entry_pages index must be reset to 0..n-1"
        )
        rows = out["rows"]
        counts = {r["page"]: r["sessions"] for r in rows}
        # home: u1 s0 entry + u3 s0 entry = 2 ; cart: u1 s1 entry = 1 ; search: 1
        assert counts.get("home") == 2, "home is the entry of two sessions"
        assert counts.get("cart") == 1, "cart is the entry of u1's second session"
        assert counts.get("search") == 1
        assert "detail" not in counts, (
            "detail is never a session's first page; must not appear"
        )
        # sorted by sessions desc then page asc
        ordered = [(r["page"], r["sessions"]) for r in rows]
        assert ordered[0] == ("home", 2), "highest-count landing page must come first"
        # ties (cart=1, search=1) broken by page ascending
        assert ordered[1] == ("cart", 1)
        assert ordered[2] == ("search", 1)

    def test_entry_pages_uses_first_page_not_any_page(self):
        """L2: only the earliest page of a session counts as the landing page."""
        out = self._run_json(
            """
            # one user, one session: pages home -> promo -> home
            # 'promo' and the later 'home' visit must NOT count as entries.
            events = pd.DataFrame({
                'user_id':   [1, 1, 1],
                'timestamp': ['2023-01-01 10:00:00', '2023-01-01 10:05:00',
                              '2023-01-01 10:10:00'],
                'page':      ['landing', 'promo', 'landing'],
            })
            assigned = sz.assign_sessions(events, 30)
            ep = sz.entry_pages(assigned)
            rows = {r['page']: int(r['sessions']) for _, r in ep.iterrows()}
            print(json.dumps({'rows': rows, 'n': int(len(ep))}))
            """
        )
        assert out["n"] == 1, "only one distinct landing page across one session"
        assert out["rows"].get("landing") == 1, "the session landed once on 'landing'"
        assert "promo" not in out["rows"], (
            "a mid-session page must never be counted as a landing page"
        )

    def test_entry_pages_does_not_mutate_input(self):
        """L2: entry_pages must not mutate its input frame."""
        out = self._run_json(
            self.SAMPLE
            + "\f"
            + """
            assigned = sz.assign_sessions(events, 30)
            before = pd.util.hash_pandas_object(assigned, index=True).sum()
            before_cols = list(assigned.columns)
            _ = sz.entry_pages(assigned)
            after = pd.util.hash_pandas_object(assigned, index=True).sum()
            after_cols = list(assigned.columns)
            print(json.dumps({
                'hash_same': bool(before == after),
                'cols_same': before_cols == after_cols,
            }))
            """
        )
        assert out["hash_same"], "entry_pages must not mutate its input"
        assert out["cols_same"], "entry_pages must not change input columns"

    # ---- L2: end-to-end native command ----------------------------------

    def test_agent_native_pytest_passes(self):
        """L2: the spec's native command on the agent's own test suite passes."""
        test_file = os.path.join(self.REPO_DIR, self.TEST_REL)
        assert os.path.isfile(test_file), "agent test file missing"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["python", "-m", "pytest", "scripts/tests/test_sessionize.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native command `python -m pytest scripts/tests/test_sessionize.py -q` "
            "failed.\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
        )
        # guard against a vacuous (zero-collected) pass
        assert "no tests ran" not in proc.stdout.lower(), (
            "agent test suite collected no tests"
        )
