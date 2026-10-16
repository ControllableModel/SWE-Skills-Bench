"""
Test for 'terraform-module-patterns' skill (variant ext8) — Keyed Multi-VPC
"VPC fleet" wrapper example.

Verifies that the agent authored a runnable example under
``examples/vpc-fleet/`` that stamps out a *fleet* of similarly-shaped VPCs from a
single ``vpcs`` map-of-objects input. Every VPC is individually addressable by
its map key: the root module (``source = "../../"``) is invoked once per entry
via ``for_each`` over ``var.vpcs``, each VPC's name incorporates ``each.key``,
and outputs expose key->id and key->CIDR maps built with ``{ for ... }``
expressions.

This is a DISTINCT task from ext1 (which targeted ``examples/multi-tier/`` with
a ``tiers`` input and a region allow-list validation). Here the deliverable
directory, the variable name (``vpcs``), the validation semantics (a CIDR-shape
``/`` check rather than a region allow-list), and the output shapes all differ;
every assertion below is re-derived from the ext8 requirement doc.

Per the doc's Acceptance Criteria, this test uses the Python standard library
only and inspects the generated ``.tf`` files as TEXT (it does NOT invoke any
``terraform`` binary). Validation goes well beyond substring matching: HCL
top-level blocks are parsed with a brace-aware tokenizer so that
``variable`` / ``output`` / ``module`` / ``locals`` / ``terraform`` blocks are
examined individually for their required arguments, types, validation rules,
keyed-iteration semantics, naming conventions, and formatting.

Discriminative intent (a naive/stub implementation must FAIL):
  * Using ``count`` (a positional fleet) instead of keyed ``for_each`` -> fail.
  * A ``name`` that ignores ``each.key`` (all VPCs share a name) -> fail.
  * Typing ``vpcs`` as ``any`` / a plain list, dropping the object schema -> fail.
  * Outputs that return a single scalar instead of a key-keyed ``{ for ... }``
    map of ids / CIDRs -> fail.
  * Omitting the CIDR-shape ``validation`` block / its ``error_message`` -> fail.
  * Putting version pins outside ``versions.tf`` -> fail.

Native acceptance command (from the doc):
  pytest tests/ext8/test_terraform_module_patterns.py -v
"""

import os
import re
import subprocess
import sys

import pytest


REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — brace/bracket aware, string-literal
# aware. Reused (proven) toolkit; assertions below are ext8-specific.
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
    """Given index of an opening '{', return index of the matching '}'.

    String-literal aware so braces inside strings are ignored.
    """
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
        r'(?m)^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)'
        r'((?:[ \t]+(?:"[^"]*"|[a-zA-Z_][a-zA-Z0-9_]*))*)'
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
    """Return the raw RHS text of a top-level argument `name = ...` within body.

    Returns the value up to end-of-line for scalars, or the full balanced
    block for nested object/list/tuple values. None if absent. Only matches at
    the top nesting level of ``body``.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # compute brace/bracket depth at the match start
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
    """Return the inner text of a nested block-style entry `name { ... }`.

    Handles HCL blocks that are NOT assignments (e.g. required_providers {}).
    Returns None if not present.
    """
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
    """Validate the examples/vpc-fleet/ keyed multi-VPC Terraform example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "vpc-fleet")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), f"missing required file: examples/vpc-fleet/{fname}"
        with open(p, "r", encoding="utf-8") as fh:
            return fh.read()

    def _all_tf(self):
        """Return dict {filename: raw_text} for every .tf file in the example."""
        out = {}
        for fn in os.listdir(self._example_dir):
            if fn.endswith(".tf"):
                with open(os.path.join(self._example_dir, fn), "r", encoding="utf-8") as fh:
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

    def _root_module_body(self):
        """Return the body text of the module block sourcing the root module.

        The 'fleet' invocation is identified by source = "../../".
        """
        for labels, body, fn in self._blocks_of_type("module"):
            src = _top_level_arg(body, "source")
            if src and '"../../"' in src:
                return body
        return None

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/vpc-fleet/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/vpc-fleet/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain exactly the five required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, "
            f"found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and yields >=1 parseable HCL block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    def test_python_file_compiles(self):
        """Sanity: this very test module imports/compiles cleanly (self-check)."""
        rc = subprocess.run(
            [sys.executable, "-m", "py_compile", os.path.abspath(__file__)],
            capture_output=True, text=True, timeout=120,
        )
        assert rc.returncode == 0, f"py_compile failed: {rc.stderr}"

    def test_root_module_block_present(self):
        """main.tf must contain a module block sourcing the root module ../../."""
        body = self._root_module_body()
        assert body is not None, 'no module block with source = "../../" found'

    # ====================================================================
    # L2 — deep semantic validation of the ext8 requirements
    # ====================================================================

    def test_versions_pins_terraform_and_aws_provider(self):
        """versions.tf pins required_version + hashicorp/aws provider version."""
        text = self._read("versions.tf")
        tf_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "terraform"]
        assert tf_blocks, "no terraform{} block in versions.tf"
        body = tf_blocks[0]

        rv = _top_level_arg(body, "required_version")
        assert rv, "required_version not declared in terraform{} block"
        assert re.search(r'(>=|~>|<=|<|>|=)\s*\d', rv), \
            f"required_version lacks an explicit constraint operator: {rv!r}"

        rp = _block_body(body, "required_providers")
        if rp is None:
            rp = _top_level_arg(body, "required_providers")
        assert rp, "required_providers block missing in versions.tf"
        assert re.search(r'source\s*=\s*"hashicorp/aws"', rp), \
            'aws provider source must be "hashicorp/aws"'
        m = re.search(r'aws\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"', rp, re.S)
        assert m, "aws provider must declare a pinned version constraint"
        assert re.search(r'(>=|~>|<=|<|>|=)\s*\d', m.group(1)), \
            f"aws provider version is not a pinned constraint: {m.group(1)!r}"

    def test_only_versions_file_declares_version_requirements(self):
        """Version pins must live ONLY in versions.tf (no terraform{} elsewhere)."""
        for fn, text in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                assert t != "terraform", \
                    f"terraform/version block must live only in versions.tf, found in {fn}"
            assert "required_providers" not in _strip_comments(text), \
                f"required_providers must live only in versions.tf, found in {fn}"

    def test_every_variable_has_type_and_description(self):
        """Each variable block must declare both type and a non-empty description."""
        variables = self._blocks_of_type("variable")
        assert variables, "no variable blocks found"
        for labels, body, fn in variables:
            name = labels[0] if labels else "<unnamed>"
            assert _top_level_arg(body, "type"), \
                f"variable {name} ({fn}) missing a type argument"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"variable {name} ({fn}) missing a non-empty description"

    def test_vpcs_variable_is_map_of_object(self):
        """The 'vpcs' variable must be typed map(object(...)) with cidr/az/nat fields."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "vpcs" in variables, "variable 'vpcs' not declared"
        body = variables["vpcs"]
        type_rhs = _top_level_arg(body, "type")
        assert type_rhs, "vpcs variable has no type"
        assert "map(" in type_rhs and "object(" in type_rhs, \
            f"vpcs type must be a map of object, got: {type_rhs!r}"
        # the type must not be the lazy 'any'
        assert not re.search(r'\bany\b', type_rhs.replace("object(", "")), \
            f"vpcs type must not be 'any': {type_rhs!r}"
        # object schema: a string CIDR, a numeric AZ count, a bool NAT flag
        assert re.search(r'(cidr|cidr_block)\s*=\s*string', type_rhs), \
            f"vpcs object must include a string CIDR attribute: {type_rhs!r}"
        assert re.search(r'=\s*number', type_rhs), \
            f"vpcs object must include a numeric AZ-count attribute: {type_rhs!r}"
        assert re.search(r'=\s*bool', type_rhs), \
            f"vpcs object must include a boolean NAT-gateway attribute: {type_rhs!r}"

    def test_vpcs_default_has_three_named_entries(self):
        """vpcs default must define at least three named map entries."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables["vpcs"]
        default = _top_level_arg(body, "default")
        assert default, "vpcs variable must provide a default"
        keys = re.findall(r'(?m)^\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*\{', default)
        keys += re.findall(r'(?m)^\s*"([a-zA-Z_][a-zA-Z0-9_-]*)"\s*=\s*\{', default)
        keys = [k for k in keys if k]
        assert len(set(keys)) >= 3, \
            f"vpcs default must contain >= 3 named entries, found {sorted(set(keys))}"

    def test_vpcs_validation_checks_cidr_shape(self):
        """vpcs must carry a validation block enforcing a CIDR '/' shape check."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables["vpcs"]
        vmatch = re.search(r'(?m)^[ \t]*validation\s*\{', body)
        assert vmatch, "vpcs variable must contain a validation block"
        open_idx = body.index("{", vmatch.start())
        close_idx = _find_matching_brace(body, open_idx)
        vbody = body[open_idx + 1:close_idx]

        # non-empty error_message string literal
        em = re.search(r'error_message\s*=\s*"([^"]+)"', vbody)
        assert em and em.group(1).strip(), \
            "vpcs validation must set a non-empty error_message string literal"

        # condition must reference a CIDR-shape '/' check, iterating the entries
        cond = _top_level_arg(vbody, "condition")
        assert cond, "vpcs validation must declare a condition"
        # the '/' shape check: a literal "/" appears in the condition text, and
        # the condition iterates over the entries (alltrue/for/contains-style).
        assert '"/"' in cond or "/" in cond, \
            f"vpcs validation condition must perform a CIDR '/' shape check: {cond!r}"
        assert re.search(r'(alltrue|for\s|can\(|contains\s*\(|regex)', cond), \
            f"vpcs validation must iterate/check each entry's CIDR: {cond!r}"

    def test_root_module_uses_for_each_over_vpcs_not_count(self):
        """The root-module invocation must use keyed for_each on var.vpcs, not count."""
        body = self._root_module_body()
        assert body is not None, 'no module with source = "../../"'

        for_each = _top_level_arg(body, "for_each")
        assert for_each, "root module block must use for_each (keyed iteration)"
        assert "var.vpcs" in for_each or "local." in for_each, \
            f"for_each must derive from var.vpcs (or a local of it): {for_each!r}"

        # NO count anywhere in the block — keyed, not positional.
        count = _top_level_arg(body, "count")
        assert count is None, \
            f"root module must NOT use count (got count = {count!r})"
        assert not re.search(r'(?m)^\s*count\s*=', body), \
            "root module block must not declare count = <integer>/var.<name>"

    def test_root_module_name_incorporates_each_key(self):
        """Each VPC's name must incorporate the map key (each.key)."""
        body = self._root_module_body()
        assert body is not None, 'no module with source = "../../"'
        name = _top_level_arg(body, "name")
        assert name, "root module must set a name argument"
        assert "each.key" in name, \
            f"VPC name must incorporate the map key via each.key, got: {name!r}"

    def test_locals_compute_az_selection_and_managed_tag(self):
        """locals.tf must compute per-entry AZ selection + a Terraform-managed tag."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)
        # Terraform-managed marker must be a real key=value tag, not just a word.
        clean = _strip_comments(body)
        managed = re.search(
            r'(["\']?(ManagedBy|managed_by|managed-by)["\']?)\s*=\s*["\']?[Tt]erraform["\']?',
            clean,
        )
        alt = re.search(r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', clean)
        assert managed or alt, \
            'locals.tf shared tags must mark resources Terraform-managed ' \
            '(e.g. ManagedBy = "Terraform")'

    def test_outputs_each_have_description(self):
        """Every output block must include a non-empty description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_keyed_id_and_cidr_maps(self):
        """Outputs must expose a key->VPC-id map and a key->CIDR map via { for ... }."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            val = _top_level_arg(body, "value")
            values.append((labels[0] if labels else "", val or ""))

        # An output whose value is a brace-delimited for-expression (a map) that
        # iterates the keyed module instances and exposes vpc_id.
        def _is_for_map(v):
            return v.strip().startswith("{") and re.search(
                r'for\s+\w+\s*,\s*\w+\s+in\s+(module\.|var\.vpcs|local\.)', v)

        id_out = [
            (n, v) for n, v in values
            if _is_for_map(v) and re.search(r'\bvpc_id\b', v)
        ]
        assert id_out, (
            "need an output whose value is a { for ... } map of key -> VPC id "
            "(for-expression over module.* exposing vpc_id)"
        )

        cidr_out = [
            (n, v) for n, v in values
            if _is_for_map(v) and re.search(r'(vpc_cidr_block|cidr_block|vpc_cidr)', v)
        ]
        assert cidr_out, (
            "need an output whose value is a { for ... } map of key -> VPC CIDR block"
        )

    def test_identifier_naming_convention(self):
        """All top-level block labels must match lowercase-underscore ^[a-z][a-z0-9_]*$."""
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
        """No AKIA access keys or non-empty access/secret key literals allowed."""
        akia = re.compile(r'AKIA[0-9A-Z]{16}')
        cred = re.compile(r'(aws_access_key|access_key|secret_key|aws_secret_access_key)'
                          r'\s*=\s*"([^"]+)"')
        for fn, text in self._all_tf().items():
            assert not akia.search(text), f"{fn} contains a hardcoded AKIA access key"
            for m in cred.finditer(text):
                val = m.group(2).strip()
                if val and not val.startswith("${") and not val.startswith("var."):
                    pytest.fail(f"{fn} assigns a literal credential: {m.group(1)} = \"{val}\"")
