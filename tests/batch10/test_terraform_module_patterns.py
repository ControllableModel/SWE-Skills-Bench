"""
Test for 'terraform-module-patterns' skill — Reusable Tagging Helper Submodule (ext10).

Verifies that the agent authored a *standalone, resource-free* helper submodule
under ``modules/tagging/`` that takes structured inputs (environment, application,
mandatory_tags, extra_tags) and emits a normalized, governance-compliant merged
tag map via ``merge(...)`` in ``locals.tf``, exposing ``tags`` (full merged map)
and ``tag_keys`` (the sorted list of merged keys) as described outputs.

Verification strategy
----------------------
This test inspects the generated ``.tf`` files as text using only the Python
standard library (it does NOT invoke any ``terraform`` binary, matching the
variant's native acceptance command ``pytest tests/ext10/...``). Validation goes
well beyond substring matching: top-level HCL blocks are extracted with a
brace-aware tokenizer so that ``variable`` / ``locals`` / ``output`` / ``terraform``
blocks can be examined individually for their required arguments, types,
validation rules, merge semantics, naming conventions, and formatting.

Discriminative intent: a naive/stub implementation MUST fail. Specifically a
module that hand-writes a single literal tag map (no ``merge(``), that ignores
``var.extra_tags`` / ``var.mandatory_tags``, that omits the ``environment``
validation/error_message, that returns an unsorted ``tag_keys`` (no
``sort(``/``keys(``), that declares a provider/resource, or that drops output
descriptions — each of these is caught by a dedicated assertion below.
"""

import os
import re
import subprocess
import sys

import pytest


# The four files this submodule must contain — and ONLY these (no main.tf,
# because no resources are created).
REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — ported from the ext1 harness template.
# ----------------------------------------------------------------------------

def _strip_comments(text):
    """Remove // and # line comments and /* */ block comments (HCL syntax).

    Careful not to strip '#'/'//' occurring inside string literals.
    """
    out = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "#":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _find_matching_brace(text, open_idx):
    """Given index of an opening '{', return index of the matching '}'."""
    depth = 0
    i = open_idx
    n = len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _iter_top_level_blocks(text):
    """Yield (block_type, [labels], body_text) for each top-level HCL block."""
    clean = _strip_comments(text)
    header_re = re.compile(
        r'(?m)^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)'                # block type
        r'((?:[ \t]+(?:"[^"]*"|[a-zA-Z_][a-zA-Z0-9_]*))*)'    # labels
        r'[ \t]*\{'
    )
    for m in header_re.finditer(clean):
        btype = m.group(1)
        labels_raw = m.group(2).strip()
        labels = re.findall(r'"([^"]*)"|([a-zA-Z_][a-zA-Z0-9_]*)', labels_raw)
        labels = [a or b for (a, b) in labels]
        open_idx = clean.index("{", m.start())
        close_idx = _find_matching_brace(clean, open_idx)
        if close_idx == -1:
            continue
        body = clean[open_idx + 1:close_idx]
        yield btype, labels, body


def _bracket_balance(s):
    """Return net unbalanced opening brackets in s (string-literal aware)."""
    depth = 0
    i = 0
    in_str = False
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        i += 1
    return depth


def _find_balanced(text, open_idx):
    pairs = {"{": "}", "[": "]", "(": ")"}
    opener = text[open_idx]
    closer = pairs[opener]
    depth = 0
    i = open_idx
    n = len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def _top_level_arg(body, name):
    """Return the raw RHS text of a top-level argument `name = ...` within body."""
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # compute brace/bracket depth at start
        d = 0
        j = 0
        s = False
        while j < start:
            c = body[j]
            if s:
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    s = False
                j += 1
                continue
            if c == '"':
                s = True
            elif c in "{[(":
                d += 1
            elif c in "}])":
                d -= 1
            j += 1
        if d != 0:
            continue
        rhs_start = m.end()
        k = rhs_start
        while k < n and body[k] in " \t":
            k += 1
        if k < n and body[k] in "{[(":
            close = _find_balanced(body, k)
            return body[rhs_start:close + 1].strip()
        end = body.find("\n", rhs_start)
        if end == -1:
            end = n
        while _bracket_balance(body[rhs_start:end]) > 0 and end < n:
            nxt = body.find("\n", end + 1)
            end = n if nxt == -1 else nxt
        return body[rhs_start:end].strip()
    return None


def _block_body(body, name):
    """Return inner text of a nested block-style entry `name { ... }`."""
    m = re.search(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*\{', body)
    if not m:
        return None
    open_idx = body.index("{", m.start())
    close_idx = _find_matching_brace(body, open_idx)
    if close_idx == -1:
        return None
    return body[open_idx + 1:close_idx]


# ----------------------------------------------------------------------------
# Test class
# ----------------------------------------------------------------------------

class TestTerraformModulePatterns:
    """Validate the modules/tagging/ pure tag-normalization submodule."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _mod_dir(self):
        return os.path.join(self.REPO_DIR, "modules", "tagging")

    def _read(self, fname):
        p = os.path.join(self._mod_dir, fname)
        assert os.path.isfile(p), f"missing required file: modules/tagging/{fname}"
        with open(p, "r", encoding="utf-8") as fh:
            return fh.read()

    def _all_tf(self):
        """Return dict {filename: raw_text} for every .tf file in the module."""
        out = {}
        assert os.path.isdir(self._mod_dir), "modules/tagging/ directory not found"
        for fn in os.listdir(self._mod_dir):
            if fn.endswith(".tf"):
                with open(os.path.join(self._mod_dir, fn), "r", encoding="utf-8") as fh:
                    out[fn] = fh.read()
        return out

    def _blocks_of_type(self, btype):
        """Collect every (labels, body, filename) for the given block type."""
        res = []
        for fn, text in self._all_tf().items():
            for t, labels, body in _iter_top_level_blocks(text):
                if t == btype:
                    res.append((labels, body, fn))
        return res

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_module_directory_exists(self):
        """modules/tagging/ must exist as a directory."""
        assert os.path.isdir(self._mod_dir), \
            "modules/tagging/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain EXACTLY the four required .tf files.

        Notably no main.tf (no resources) — a stub that re-uses the standard
        4-file layout with main.tf would fail here.
        """
        tf_files = sorted(f for f in os.listdir(self._mod_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, found {tf_files}"
        )
        assert not os.path.isfile(os.path.join(self._mod_dir, "main.tf")), \
            "modules/tagging/ must NOT contain main.tf (no resources created)"

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and yields >=1 parseable HCL block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    # ====================================================================
    # L2 — deep semantic validation of the requirements
    # ====================================================================

    def test_no_provider_or_resource_anywhere(self):
        """Pure transformation module: no provider{} and no resource{} blocks.

        Catches a stub that copies a real resource-creating module.
        """
        for fn, text in self._all_tf().items():
            for t, labels, body in _iter_top_level_blocks(text):
                assert t != "provider", \
                    f"{fn} declares a provider block; tagging module must declare none"
                assert t != "resource", \
                    f"{fn} declares a resource block; tagging module creates no resources"
            # also guard against a bare `provider "..." {` header escaping the parser
            clean = _strip_comments(text)
            assert not re.search(r'(?m)^\s*resource\s+"', clean), \
                f"{fn} contains a resource block"
            assert not re.search(r'(?m)^\s*provider\s+"', clean), \
                f"{fn} contains a provider block"

    def test_versions_required_version_only_no_aws_provider(self):
        """versions.tf pins required_version (explicit operator) and declares NO aws provider."""
        text = self._read("versions.tf")
        tf_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "terraform"]
        assert tf_blocks, "no terraform{} block in versions.tf"
        body = tf_blocks[0]

        rv = _top_level_arg(body, "required_version")
        assert rv, "required_version not declared in terraform{} block"
        assert re.search(r'(>=|~>|<=|<|>|=)\s*\d', rv), \
            f"required_version lacks an explicit constraint operator: {rv!r}"

        # Must NOT declare a required_providers / aws provider requirement.
        rp = _block_body(body, "required_providers")
        assert rp is None, \
            "tagging module must NOT declare required_providers (it uses no provider)"
        for fn, t in self._all_tf().items():
            assert not re.search(r'(?m)^\s*required_providers\b', _strip_comments(t)), \
                f"{fn} declares required_providers; tagging module uses no provider"
            assert not re.search(r'source\s*=\s*"hashicorp/aws"', t), \
                f"{fn} references hashicorp/aws provider; tagging module needs none"

    def test_every_variable_has_type_and_description(self):
        """Each variable block must declare both a type and a non-empty description."""
        variables = self._blocks_of_type("variable")
        assert variables, "no variable blocks found"
        names = set()
        for labels, body, fn in variables:
            name = labels[0] if labels else "<unnamed>"
            names.add(name)
            assert _top_level_arg(body, "type"), \
                f"variable {name} ({fn}) missing a type argument"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"variable {name} ({fn}) missing a non-empty description"
        for required in ("environment", "application", "mandatory_tags", "extra_tags"):
            assert required in names, f"required variable '{required}' not declared"

    def test_environment_has_validation_with_error_message_and_allowlist(self):
        """environment is a string with a validation block enforcing an allow-list + custom error_message.

        A stub that accepts any environment (no validation block) MUST fail.
        """
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "environment" in variables, "variable 'environment' not declared"
        body = variables["environment"]

        type_rhs = _top_level_arg(body, "type")
        assert type_rhs and "string" in type_rhs, \
            f"environment must be typed string, got {type_rhs!r}"

        vmatch = re.search(r'validation\s*\{', body)
        assert vmatch, "environment variable must contain a validation block"
        vopen = body.index("{", vmatch.start())
        vbody = body[vmatch.end():_find_matching_brace(body, vopen)]

        em = re.search(r'error_message\s*=\s*"([^"]+)"', vbody)
        assert em and em.group(1).strip(), \
            "environment validation must set a non-empty error_message string literal"

        cond = re.search(r'condition\s*=\s*(.+)', vbody)
        assert cond, "environment validation must declare a condition"
        assert re.search(r'(contains\s*\(|in\s*\[|anytrue|for\s)', cond.group(1)), \
            f"environment validation must check against an allow-list: {cond.group(1)!r}"

    def test_tag_map_variables_are_map_string(self):
        """mandatory_tags and extra_tags must be typed map(string), defaulting to {}."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        for vname in ("mandatory_tags", "extra_tags"):
            assert vname in variables, f"variable '{vname}' not declared"
            body = variables[vname]
            type_rhs = _top_level_arg(body, "type")
            assert type_rhs, f"{vname} has no type"
            normalized = re.sub(r"\s+", "", type_rhs)
            assert "map(string)" in normalized, \
                f"{vname} type must be map(string), got {type_rhs!r}"
            default = _top_level_arg(body, "default")
            assert default is not None, f"{vname} must default to an empty map"
            assert re.sub(r"\s+", "", default) == "{}", \
                f"{vname} default must be an empty map {{}}, got {default!r}"

    def test_application_variable_is_string(self):
        """application owning-app variable must be a typed string with a description."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "application" in variables, "variable 'application' not declared"
        body = variables["application"]
        type_rhs = _top_level_arg(body, "type")
        assert type_rhs and "string" in type_rhs, \
            f"application must be typed string, got {type_rhs!r}"

    def test_locals_merges_all_tag_sources(self):
        """locals.tf builds the merged map via merge(), referencing baseline marker, env, app, mandatory_tags, extra_tags.

        A hand-written single literal map (no merge(, ignoring caller inputs) MUST fail.
        """
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)
        clean = _strip_comments(body)

        assert "merge(" in clean, \
            "locals.tf must combine tag sources using the merge() function"
        assert "var.mandatory_tags" in clean, \
            "merged tags must reference var.mandatory_tags"
        assert "var.extra_tags" in clean, \
            "merged tags must reference var.extra_tags"
        assert "var.environment" in clean, \
            "merged tags must reference var.environment"
        assert "var.application" in clean, \
            "merged tags must reference var.application"

        # Baseline Terraform-managed marker tag must be a real key=value assignment.
        marker = re.search(
            r'["\']?(ManagedBy|managed_by|managed-by)["\']?\s*=\s*["\']?[Tt]erraform["\']?',
            clean,
        )
        alt = re.search(r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', clean)
        assert marker or alt, \
            'locals.tf baseline must include a Terraform-managed marker tag ' \
            '(e.g. ManagedBy = "Terraform")'

    def test_locals_merge_orders_extra_tags_to_extend(self):
        """The merge() call must list multiple maps so later sources extend earlier ones.

        A single-argument merge (or a literal map) cannot satisfy the
        'later sources extend earlier ones' requirement.
        """
        clean = _strip_comments(self._read("locals.tf"))
        m = re.search(r'merge\s*\(', clean)
        assert m, "locals.tf must call merge(...)"
        open_paren = clean.index("(", m.start())
        close_paren = _find_balanced(clean, open_paren)
        args_text = clean[open_paren + 1:close_paren]
        # Split top-level comma-separated arguments (bracket-aware).
        depth = 0
        in_str = False
        commas = 0
        i = 0
        while i < len(args_text):
            c = args_text[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c in "{[(":
                depth += 1
            elif c in "}])":
                depth -= 1
            elif c == "," and depth == 0:
                commas += 1
            i += 1
        assert commas >= 1, \
            "merge() must combine at least two tag maps (baseline + caller inputs)"
        # extra_tags should be among the merge arguments (caller override capability)
        assert "var.extra_tags" in args_text, \
            "var.extra_tags must be an argument to merge() so callers can extend tags"

    def test_outputs_tags_and_tag_keys_present_with_descriptions(self):
        """outputs.tf declares 'tags' and 'tag_keys', each with a non-empty description."""
        outputs = {l[0]: b for l, b, f in self._blocks_of_type("output") if l}
        assert outputs, "no output blocks found"
        for required in ("tags", "tag_keys"):
            assert required in outputs, f"output '{required}' not declared"
        for name, body, fn in self._blocks_of_type("output"):
            label = name[0] if name else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {label} ({fn}) missing a non-empty description"

    def test_tags_output_references_merged_local(self):
        """The 'tags' output value must reference the merged local (local.*), not a literal."""
        outputs = {l[0]: b for l, b, f in self._blocks_of_type("output") if l}
        body = outputs["tags"]
        val = _top_level_arg(body, "value")
        assert val, "tags output must declare a value"
        assert "local." in val, \
            f"tags output must surface the merged local tag map, got {val!r}"
        assert "{" not in val.replace("local.", ""), \
            f"tags output must not inline a literal map, got {val!r}"

    def test_tag_keys_output_is_sorted_keys_of_merged_map(self):
        """tag_keys output value must use both keys( ) and sort( ) over the merged map.

        A naive implementation returning an unsorted/hardcoded list MUST fail.
        """
        outputs = {l[0]: b for l, b, f in self._blocks_of_type("output") if l}
        body = outputs["tag_keys"]
        val = _top_level_arg(body, "value")
        assert val, "tag_keys output must declare a value"
        assert "keys(" in val, \
            f"tag_keys value must use the keys() function, got {val!r}"
        assert "sort(" in val, \
            f"tag_keys value must use the sort() function, got {val!r}"
        assert "local." in val, \
            f"tag_keys must derive from the merged local map, got {val!r}"
        # sort( must wrap keys( — i.e. sort(keys(...))
        assert re.search(r'sort\s*\(\s*keys\s*\(', val), \
            f"tag_keys must be sort(keys(...)), got {val!r}"

    def test_identifier_naming_convention(self):
        """All user-chosen block labels must match lowercase-underscore: ^[a-z][a-z0-9_]*$."""
        ident_re = re.compile(r'^[a-z][a-z0-9_]*$')
        offenders = []
        for fn, text in self._all_tf().items():
            for t, labels, body in _iter_top_level_blocks(text):
                if t in ("variable", "output", "module", "data", "resource", "provider"):
                    check = labels[-1:] if t in ("data", "resource") else labels
                    for lab in check:
                        if not ident_re.match(lab):
                            offenders.append((fn, t, lab))
                if t == "locals":
                    for m in re.finditer(r'(?m)^\s{2}([A-Za-z_][\w-]*)\s*=', body):
                        if not ident_re.match(m.group(1)):
                            offenders.append((fn, "local", m.group(1)))
        assert not offenders, f"identifiers violate lowercase_underscore: {offenders}"

    def test_no_tabs_in_any_tf_file(self):
        """Indentation must use spaces only — no literal tab characters."""
        for fn, text in self._all_tf().items():
            assert "\t" not in text, f"{fn} contains a literal tab character"

    def test_two_space_indentation(self):
        """Nested HCL lines must indent in multiples of two spaces."""
        for fn, text in self._all_tf().items():
            for ln, line in enumerate(text.splitlines(), 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                lead = len(line) - len(line.lstrip(" "))
                assert lead % 2 == 0, \
                    f"{fn}:{ln} indentation is not a multiple of two spaces"

    def test_no_hardcoded_aws_credentials(self):
        """No AKIA access keys or non-empty access/secret key literal assignments."""
        akia = re.compile(r'AKIA[0-9A-Z]{16}')
        cred = re.compile(r'(aws_access_key|access_key|secret_key|aws_secret_access_key)'
                          r'\s*=\s*"([^"]+)"')
        for fn, text in self._all_tf().items():
            assert not akia.search(text), f"{fn} contains a hardcoded AKIA access key"
            for m in cred.finditer(text):
                val = m.group(2).strip()
                if val and not val.startswith("${") and not val.startswith("var."):
                    pytest.fail(f"{fn} assigns a literal credential: {m.group(1)} = \"{val}\"")

    def test_native_acceptance_command_collects_this_module(self):
        """Drive the variant's native acceptance command (pytest collection) for this file.

        Mirrors the doc's acceptance command
        ``pytest tests/ext10/test_terraform_module_patterns.py`` by collecting
        this very file and asserting the test class is discovered, proving the
        suite is runnable end-to-end under the repo's toolchain.
        """
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", os.path.abspath(__file__),
             "--collect-only", "-q"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, \
            f"pytest collection failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        assert "TestTerraformModulePatterns" in proc.stdout, \
            f"expected test class not collected:\n{proc.stdout}"
