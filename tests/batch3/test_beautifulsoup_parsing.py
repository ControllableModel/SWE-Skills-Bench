"""
Test for the 'beautifulsoup-parsing' skill — HTML Form Field Extraction Module.

Variant task (ext3)
-------------------
The Agent must create a self-contained form-extraction utility at
``bs4/forms.py`` exposing four public functions —

  * ``form_action(html)``        -> dict envelope (action / method / enctype) or None
  * ``extract_fields(html)``     -> list[dict] of input/textarea/select controls
  * ``select_options(html, name)`` -> list[dict] of <option> for a named <select>
  * ``required_field_names(html)`` -> list[str] of named required controls

— plus an accompanying deterministic test file ``bs4/tests/test_forms.py``.
The module operates entirely in-process on HTML *strings*, builds its tree via
``bs4.BeautifulSoup`` using only the stdlib ``html.parser`` (no third-party
parser package), and performs no network / file access.

Verification strategy
----------------------
* L1 checks the two deliverable files exist, the module imports cleanly with the
  repo's own Python, and exposes the four public callables.
* L2 drives the Agent's *real* module independently of any test the Agent itself
  wrote: a tiny JSON-emitting driver is written into REPO_DIR and run with
  ``cwd=REPO_DIR`` so ``import bs4.forms`` resolves against the package.  The
  emitted plain-data structures are deep-validated against the requirement's
  contract — method lowercasing/defaulting, enctype None-default, boolean
  attribute detection by presence (``<input required>``), option value-fallback
  to visible text, selected flags, required-name filtering (skipping nameless
  required controls), the no-form case, and malformed-HTML tolerance.  A
  hardcoded / look-alike solution that does not really parse the HTML cannot
  satisfy these fixtures.
* One L2 case runs the native acceptance command
  (``python -m pytest bs4/tests/test_forms.py -v``).
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/BeautifulSoup4"


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _run_driver(body, timeout=120):
    """
    Write ``body`` (a Python snippet that defines a module-level ``RESULT``
    object) into a throwaway driver under REPO_DIR, execute it with the repo's
    Python so that ``import bs4.forms`` resolves, and return the parsed JSON
    that the driver prints to stdout.

    The driver imports the Agent's real module — there is no stubbing — so the
    returned data reflects genuine parsing behaviour.
    """
    driver_dir = os.path.join(REPO_DIR, "_skill_forms_driver_tmp")
    os.makedirs(driver_dir, exist_ok=True)
    driver_path = os.path.join(driver_dir, "drv.py")

    header = textwrap.dedent(
        """
        import json, sys, os
        sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
        from bs4.forms import (
            form_action,
            extract_fields,
            select_options,
            required_field_names,
        )
        """
    )
    full = header + "\n" + textwrap.dedent(body) + "\nprint(json.dumps(RESULT))\n"

    with open(driver_path, "w") as fh:
        fh.write(full)

    try:
        proc = subprocess.run(
            ["python", driver_path],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        try:
            os.remove(driver_path)
        except OSError:
            pass

    assert proc.returncode == 0, (
        "driver failed (returncode={})\n--- stdout ---\n{}\n--- stderr ---\n{}".format(
            proc.returncode, proc.stdout, proc.stderr
        )
    )
    out = proc.stdout.strip().splitlines()
    assert out, "driver produced no stdout; stderr=\n" + proc.stderr
    return json.loads(out[-1])


# A reasonably rich form exercising every contract dimension at once.
FORM_HTML = """
<html><body>
  <form action="/submit" method="POST" enctype="multipart/form-data">
    <input name="username" type="TEXT" required value="alice">
    <input name="agree" type="checkbox" required>
    <input name="nickname">
    <input type="submit" value="Go">
    <textarea name="bio">hello world</textarea>
    <select name="country">
      <option value="us">United States</option>
      <option value="ca" selected>Canada</option>
      <option>Other</option>
    </select>
  </form>
</body></html>
"""


# ----------------------------------------------------------------------------
# L1: deliverables exist and are importable
# ----------------------------------------------------------------------------

class TestBeautifulsoupParsing:
    """Validate the HTML form-field extraction module and its behaviour."""

    REPO_DIR = REPO_DIR

    def test_forms_module_file_exists(self):
        """bs4/forms.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "forms.py")), \
            "bs4/forms.py was not created"

    def test_forms_test_file_exists(self):
        """bs4/tests/test_forms.py must exist."""
        assert os.path.isfile(os.path.join(REPO_DIR, "bs4", "tests", "test_forms.py")), \
            "bs4/tests/test_forms.py was not created"

    def test_module_exposes_public_callables(self):
        """The module must import cleanly and expose the four public functions."""
        res = _run_driver(
            """
            RESULT = {
                "form_action": callable(form_action),
                "extract_fields": callable(extract_fields),
                "select_options": callable(select_options),
                "required_field_names": callable(required_field_names),
            }
            """
        )
        assert res == {
            "form_action": True,
            "extract_fields": True,
            "select_options": True,
            "required_field_names": True,
        }, "forms.py must define the four documented callables"

    # ------------------------------------------------------------------
    # L2: form_action behaviour
    # ------------------------------------------------------------------

    def test_form_action_envelope_full(self):
        """form_action lowercases method and reports action + enctype verbatim."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = form_action(HTML)
            """ % FORM_HTML
        )
        assert isinstance(res, dict), "form_action must return a dict for a form"
        assert set(res.keys()) == {"action", "method", "enctype"}, \
            "form_action dict must have exactly action/method/enctype, got %r" % sorted(res.keys())
        assert res["action"] == "/submit", "action mis-parsed: %r" % res["action"]
        assert res["method"] == "post", \
            "method must be lowercased ('POST'->'post'), got %r" % res["method"]
        assert res["enctype"] == "multipart/form-data", \
            "enctype must be reported verbatim, got %r" % res["enctype"]

    def test_form_action_defaults(self):
        """Absent method defaults to 'get'; absent action -> ''; absent enctype -> None."""
        html = "<form><input name='x'></form>"
        res = _run_driver(
            """
            HTML = %r
            RESULT = form_action(HTML)
            """ % html
        )
        assert res == {"action": "", "method": "get", "enctype": None}, \
            "bare <form> must default to action=''/method='get'/enctype=None, got %r" % res

    def test_form_action_no_form_returns_none(self):
        """A document with no form -> form_action returns None (JSON null)."""
        res = _run_driver(
            """
            RESULT = form_action("<html><body><p>no form here</p></body></html>")
            """
        )
        assert res is None, "document with no form must yield None, got %r" % res

    # ------------------------------------------------------------------
    # L2: extract_fields behaviour
    # ------------------------------------------------------------------

    def test_extract_fields_order_and_keys(self):
        """One dict per input/textarea/select in document order with exact keys."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = extract_fields(HTML)
            """ % FORM_HTML
        )
        assert isinstance(res, list), "extract_fields must return a list"
        # 4 inputs + 1 textarea + 1 select, in document order.
        tags = [f["tag"] for f in res]
        assert tags == ["input", "input", "input", "input", "textarea", "select"], \
            "controls must be in document order with correct tags, got %r" % tags
        for f in res:
            assert set(f.keys()) == {"tag", "name", "type", "required", "value"}, \
                "each field dict must have exactly the 5 documented keys, got %r" % sorted(f.keys())

    def test_extract_fields_input_type_default_and_lowercase(self):
        """<input> type defaults to 'text' when absent and is lowercased."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {f["name"]: f["type"] for f in extract_fields(HTML) if f["name"]}
            """ % FORM_HTML
        )
        # 'TEXT' attribute must be lowercased to 'text'.
        assert res["username"] == "text", \
            "explicit type='TEXT' must lowercase to 'text', got %r" % res.get("username")
        assert res["agree"] == "checkbox", "checkbox type mis-parsed: %r" % res.get("agree")
        # nickname has no type attribute at all -> default 'text'.
        assert res["nickname"] == "text", \
            "<input> without type must default to 'text', got %r" % res.get("nickname")

    def test_extract_fields_textarea_and_select_synthetic_type(self):
        """textarea/select get literal type; textarea value is always None."""
        res = _run_driver(
            """
            HTML = %r
            fields = extract_fields(HTML)
            RESULT = {f["tag"]: {"type": f["type"], "value": f["value"], "name": f["name"]}
                      for f in fields if f["tag"] in ("textarea", "select")}
            """ % FORM_HTML
        )
        assert res["textarea"]["type"] == "textarea", \
            "<textarea> type must be literal 'textarea', got %r" % res["textarea"]["type"]
        assert res["textarea"]["value"] is None, \
            "<textarea> value must be None, got %r" % res["textarea"]["value"]
        assert res["textarea"]["name"] == "bio", "textarea name mis-parsed"
        assert res["select"]["type"] == "select", \
            "<select> type must be literal 'select', got %r" % res["select"]["type"]

    def test_extract_fields_required_is_bool_by_presence(self):
        """required is a real bool, True by presence of the valueless attribute."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = {f["name"]: f["required"] for f in extract_fields(HTML) if f["name"]}
            """ % FORM_HTML
        )
        # username carries `required value="alice"`, agree carries valueless `required`.
        assert res["username"] is True, "required must be True for username, got %r" % res.get("username")
        assert res["agree"] is True, \
            "valueless `required` attribute must be detected as True, got %r" % res.get("agree")
        assert res["nickname"] is False, \
            "control without required must be False, got %r" % res.get("nickname")
        # Ensure it is a genuine bool, not a truthy string.
        for k in ("username", "agree", "nickname"):
            assert isinstance(res[k], bool), \
                "required must be a bool for %s, got %r" % (k, type(res[k]))

    def test_extract_fields_value_and_missing_name(self):
        """value reflects the value attribute or None; absent name -> None."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = [{"name": f["name"], "value": f["value"], "type": f["type"]}
                      for f in extract_fields(HTML)]
            """ % FORM_HTML
        )
        by_name = {f["name"]: f for f in res if f["name"]}
        assert by_name["username"]["value"] == "alice", \
            "value attribute must be reported, got %r" % by_name["username"]["value"]
        assert by_name["agree"]["value"] is None, \
            "control without value attribute must yield None, got %r" % by_name["agree"]["value"]
        assert by_name["nickname"]["value"] is None, \
            "control without value attribute must yield None, got %r" % by_name["nickname"]["value"]
        # The submit input has no name -> name None.
        submits = [f for f in res if f["type"] == "submit"]
        assert submits and submits[0]["name"] is None, \
            "nameless <input type=submit> must have name None, got %r" % submits

    def test_extract_fields_no_form_returns_empty(self):
        """A document with no form -> extract_fields returns []."""
        res = _run_driver(
            """
            RESULT = extract_fields("<html><body><p>nothing</p></body></html>")
            """
        )
        assert res == [], "no-form document must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: select_options behaviour
    # ------------------------------------------------------------------

    def test_select_options_value_fallback_and_selected(self):
        """Options in order; value falls back to text; selected flag by presence."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = select_options(HTML, "country")
            """ % FORM_HTML
        )
        assert isinstance(res, list) and len(res) == 3, \
            "expected exactly 3 options, got %r" % res
        for o in res:
            assert set(o.keys()) == {"value", "label", "selected"}, \
                "each option dict must have value/label/selected, got %r" % sorted(o.keys())
        assert res[0] == {"value": "us", "label": "United States", "selected": False}, \
            "first option mis-parsed: %r" % res[0]
        assert res[1] == {"value": "ca", "label": "Canada", "selected": True}, \
            "selected middle option mis-parsed: %r" % res[1]
        # Third option has NO value attribute -> value falls back to stripped text.
        assert res[2] == {"value": "Other", "label": "Other", "selected": False}, \
            "value-less option must fall back to visible text, got %r" % res[2]

    def test_select_options_selected_is_real_bool(self):
        """The selected flag must be a genuine bool, exactly one True here."""
        res = _run_driver(
            """
            HTML = %r
            opts = select_options(HTML, "country")
            RESULT = {"flags": [o["selected"] for o in opts],
                      "types": [str(type(o["selected"]).__name__) for o in opts]}
            """ % FORM_HTML
        )
        assert res["flags"] == [False, True, False], \
            "exactly the middle option must be selected, got %r" % res["flags"]
        assert res["types"] == ["bool", "bool", "bool"], \
            "selected must be a bool, got %r" % res["types"]

    def test_select_options_unknown_name_returns_empty(self):
        """No <select> with the requested name -> empty list."""
        res = _run_driver(
            """
            HTML = %r
            RESULT = select_options(HTML, "no_such_select")
            """ % FORM_HTML
        )
        assert res == [], "unknown select name must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: required_field_names behaviour
    # ------------------------------------------------------------------

    def test_required_field_names_filters_named_required(self):
        """Returns names of required controls in order, skipping nameless ones."""
        html = """
        <form>
          <input name="a" required>
          <input name="b">
          <input required>
          <textarea name="c" required></textarea>
          <select name="d"><option>x</option></select>
        </form>
        """
        res = _run_driver(
            """
            HTML = %r
            RESULT = required_field_names(HTML)
            """ % html
        )
        # 'a' and 'c' are required+named; the nameless required input is skipped;
        # 'b' and 'd' are not required.
        assert res == ["a", "c"], \
            "must return only named required controls in document order, got %r" % res

    def test_required_field_names_empty_when_none_required(self):
        """A form with no required controls -> empty list."""
        html = "<form><input name='x'><input name='y' value='z'></form>"
        res = _run_driver(
            """
            HTML = %r
            RESULT = required_field_names(HTML)
            """ % html
        )
        assert res == [], "form with no required controls must yield [], got %r" % res

    # ------------------------------------------------------------------
    # L2: robustness / malformed HTML
    # ------------------------------------------------------------------

    def test_malformed_html_still_parses(self):
        """Unclosed/misnested form markup must still recover its controls."""
        malformed = (
            '<form method="post" action="/x">'
            '<input name="user" required'
            '<select name="role"><option value="admin" selected>Admin'
            '<option>Guest'
        )
        res = _run_driver(
            """
            HTML = %r
            RESULT = {
                "action": form_action(HTML),
                "n_fields": len(extract_fields(HTML)),
                "required": required_field_names(HTML),
            }
            """ % malformed
        )
        assert res["action"]["method"] == "post", \
            "method must be recoverable from malformed markup, got %r" % res["action"]
        assert res["n_fields"] >= 1, \
            "malformed form must still surface at least one control, got %r" % res["n_fields"]

    # ------------------------------------------------------------------
    # L2: native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The Agent's own bs4/tests/test_forms.py must collect and pass green."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "bs4/tests/test_forms.py", "-v"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native acceptance command failed\n--- stdout ---\n{}\n--- stderr ---\n{}".format(
                proc.stdout, proc.stderr
            )
        )
        # Guard against a vacuous suite that collects zero tests.
        assert "no tests ran" not in proc.stdout.lower(), \
            "test_forms.py collected no tests:\n" + proc.stdout
        assert " passed" in proc.stdout, \
            "expected at least one passing test in native suite:\n" + proc.stdout
