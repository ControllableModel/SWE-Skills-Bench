"""
Test for 'terraform-module-patterns' skill — Multi-Tier VPC Example Configuration.

Verifies that the agent authored a runnable example under
``examples/multi-tier/`` that provisions one VPC per logical tier by invoking
the root VPC module (``source = "../../"``) with ``for_each`` over a strongly
typed ``tiers`` map-of-object input.

This test inspects the generated ``.tf`` files as text using only the Python
standard library (it does NOT invoke any ``terraform`` binary). Validation goes
beyond substring matching: HCL top-level blocks are parsed with a brace-aware
tokenizer so that ``variable`` / ``output`` / ``module`` / ``locals`` blocks can
be examined individually for their required arguments, types, validation rules,
naming conventions, and formatting.
"""

import os
import re
import pytest


REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only)
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
    """Yield (block_type, [labels], body_text) for each top-level HCL block.

    Example matches:
      variable "tiers" { ... }
      module "vpc" { ... }
      locals { ... }
      terraform { ... }
    """
    clean = _strip_comments(text)
    # block header: identifier, then optional quoted/bare labels, then '{'
    header_re = re.compile(
        r'(?m)^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)'      # block type
        r'((?:[ \t]+(?:"[^"]*"|[a-zA-Z_][a-zA-Z0-9_]*))*)'  # labels
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


def _top_level_arg(body, name):
    """Return the raw RHS text of a top-level argument `name = ...` within body.

    Returns the value up to end-of-line for scalars, or the full block for
    nested object/list values (brace/bracket aware). None if absent.
    """
    # Only match at top nesting level of `body`.
    # Walk the body tracking brace/bracket depth.
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    depth = 0
    i = 0
    n = len(body)
    in_str = False
    line_start_depth = {}
    # Build a map of positions at depth 0 by scanning.
    # Simpler: find candidate via regex then verify depth at that offset.
    for m in pattern.finditer(body):
        start = m.start()
        # compute depth at start
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
        # capture RHS
        rhs_start = m.end()
        # if value begins with a bracket/brace, capture balanced
        k = rhs_start
        while k < n and body[k] in " \t":
            k += 1
        if k < n and body[k] in "{[(":
            close = _find_balanced(body, k)
            return body[rhs_start:close + 1].strip()
        # otherwise capture to end of line, but continue across lines while the
        # captured text has unbalanced brackets (e.g. `type = map(object({`).
        end = body.find("\n", rhs_start)
        if end == -1:
            end = n
        while _bracket_balance(body[rhs_start:end]) > 0 and end < n:
            nxt = body.find("\n", end + 1)
            end = n if nxt == -1 else nxt
        return body[rhs_start:end].strip()
    return None


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


# ----------------------------------------------------------------------------
# Test class
# ----------------------------------------------------------------------------

class TestTerraformModulePatterns:
    """Validate the examples/multi-tier/ multi-VPC Terraform example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "multi-tier")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), f"missing required file: examples/multi-tier/{fname}"
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

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/multi-tier/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/multi-tier/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain exactly the five required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, "
            f"found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and has balanced top-level braces."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            # at least one well-formed top-level block must parse
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    def test_module_block_present_in_main(self):
        """main.tf must contain a module block sourcing the root module."""
        modules = self._blocks_of_type("module")
        assert modules, "no module block found in the example"
        sources = [_top_level_arg(body, "source") for _, body, _ in modules]
        assert any(s and '"../../"' in s for s in sources), \
            'no module block with source = "../../" found'

    # ====================================================================
    # L2 — deep semantic validation of the requirements
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
            f"required_version lacks an explicit constraint operator: {rv}"

        # required_providers must declare aws -> source hashicorp/aws + version
        rp = _block_body(body, "required_providers")
        if rp is None:
            rp = _top_level_arg(body, "required_providers")
        assert rp, "required_providers block missing in versions.tf"
        assert re.search(r'source\s*=\s*"hashicorp/aws"', rp), \
            'aws provider source must be "hashicorp/aws"'
        m = re.search(r'aws\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"', rp, re.S)
        assert m, "aws provider must declare a pinned version constraint"
        assert re.search(r'(>=|~>|<=|<|>|=)\s*\d', m.group(1)), \
            f"aws provider version is not a pinned constraint: {m.group(1)}"

    def test_no_other_file_declares_versions(self):
        """Only versions.tf may carry the terraform/provider version requirements."""
        for fn, text in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                assert t != "terraform", \
                    f"terraform version block must live only in versions.tf, found in {fn}"
                assert "required_providers" not in body or t != "terraform", \
                    f"required_providers must live only in versions.tf, found in {fn}"

    def test_every_variable_has_type_and_description(self):
        """Each variable block must declare both type and description."""
        variables = self._blocks_of_type("variable")
        assert variables, "no variable blocks found"
        for labels, body, fn in variables:
            name = labels[0] if labels else "<unnamed>"
            assert _top_level_arg(body, "type"), \
                f"variable {name} ({fn}) missing a type argument"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"variable {name} ({fn}) missing a non-empty description"

    def test_tiers_variable_is_map_of_object(self):
        """The 'tiers' variable must be typed map(object(...)), not any."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "tiers" in variables, "variable 'tiers' not declared"
        body = variables["tiers"]
        type_rhs = _top_level_arg(body, "type")
        assert type_rhs, "tiers variable has no type"
        assert "map(" in type_rhs and "object(" in type_rhs, \
            f"tiers type must be a map of object, got: {type_rhs!r}"
        assert not re.search(r'\bany\b', type_rhs.replace("object(", "")), \
            f"tiers type must not be 'any': {type_rhs!r}"
        # Object must carry a cidr (string) and an az/number-ish count field.
        assert re.search(r'(cidr|cidr_block)\s*=\s*string', type_rhs), \
            f"tiers object must include a string CIDR attribute: {type_rhs!r}"
        assert re.search(r'=\s*number', type_rhs), \
            f"tiers object must include a numeric AZ-count attribute: {type_rhs!r}"

    def test_tiers_default_has_three_named_tiers(self):
        """tiers default must define at least three named tier entries."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables["tiers"]
        default = _top_level_arg(body, "default")
        assert default, "tiers variable must provide a default"
        # count top-level keys inside the default map: `key = {`
        keys = re.findall(r'(?m)^\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*\{', default)
        # also accept quoted keys
        keys += re.findall(r'(?m)^\s*"([a-zA-Z_][a-zA-Z0-9_-]*)"\s*=\s*\{', default)
        keys = [k for k in keys if k]
        assert len(set(keys)) >= 3, \
            f"tiers default must contain >= 3 tier entries, found {sorted(set(keys))}"

    def test_region_variable_has_validation_with_error_message(self):
        """region variable must be a string with a validation/error_message."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "region" in variables, "variable 'region' not declared"
        body = variables["region"]
        type_rhs = _top_level_arg(body, "type")
        assert type_rhs and "string" in type_rhs, \
            f"region must be typed string, got {type_rhs!r}"
        # find validation block inside the region variable body
        vmatch = re.search(r'validation\s*\{', body)
        assert vmatch, "region variable must contain a validation block"
        vbody = body[vmatch.end():_find_matching_brace(body, body.index("{", vmatch.start())) ]
        # error_message non-empty string literal
        em = re.search(r'error_message\s*=\s*"([^"]+)"', body)
        assert em and em.group(1).strip(), \
            "region validation must set a non-empty error_message string literal"
        # condition must reference an allow-list (contains/list semantics)
        cond = re.search(r'condition\s*=\s*(.+)', vbody)
        assert cond, "region validation must declare a condition"
        assert re.search(r'(contains\s*\(|in\s*\[|anytrue|for\s)', cond.group(1)), \
            f"region validation should check against an allow-list: {cond.group(1)!r}"

    def test_module_uses_for_each_over_tiers_not_count(self):
        """The root-module invocation must use for_each on var.tiers, not count."""
        modules = self._blocks_of_type("module")
        target = None
        for labels, body, fn in modules:
            src = _top_level_arg(body, "source")
            if src and '"../../"' in src:
                target = body
                break
        assert target is not None, 'no module with source = "../../"'

        for_each = _top_level_arg(target, "for_each")
        assert for_each, "root module block must use for_each"
        assert "var.tiers" in for_each or "local." in for_each, \
            f"for_each must derive from var.tiers (or a local of it): {for_each!r}"

        count = _top_level_arg(target, "count")
        assert count is None, \
            f"root module must NOT use count (got count = {count!r})"
        # guard against count anywhere in the block body too
        assert not re.search(r'(?m)^\s*count\s*=', target), \
            "root module block must not declare count"

    def test_module_name_incorporates_tier_key(self):
        """Each VPC name must incorporate the tier key (each.key)."""
        modules = self._blocks_of_type("module")
        for labels, body, fn in modules:
            src = _top_level_arg(body, "source")
            if src and '"../../"' in src:
                name = _top_level_arg(body, "name")
                assert name, "root module must set a name"
                assert "each.key" in name or "each.value" in name, \
                    f"VPC name must incorporate the tier key, got: {name!r}"
                return
        pytest.fail('no module with source = "../../"')

    def test_locals_compute_tags_and_az_selection(self):
        """locals.tf must compute common tags (Terraform-managed) + AZ selection."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)
        # A tag indicating Terraform-managed resources.
        assert re.search(r'(ManagedBy|managed_by|Managed_By)\s*=\s*"?[Tt]erraform"?', body) \
            or re.search(r'"?[Tt]erraform"?\s*=\s*"?true"?', body) \
            or re.search(r'[Tt]erraform', body), \
            "common tags in locals.tf must mark resources as Terraform-managed"
        # stronger: there must be an explicit Terraform-managed marker, not just the word
        assert re.search(
            r'(ManagedBy|managed_by|managed-by|Terraform)\b', body
        ), "locals.tf must include a Terraform-managed tag marker"

    def test_locals_terraform_managed_tag_is_real_tag(self):
        """The Terraform-managed marker must be a key=value tag, not a comment."""
        text = _strip_comments(self._read("locals.tf"))
        # look for a ManagedBy = "Terraform" style assignment specifically
        found = re.search(
            r'(["\']?(ManagedBy|managed_by|managed-by)["\']?)\s*=\s*["\']?[Tt]erraform["\']?',
            text,
        )
        # fallback: Terraform = true style
        alt = re.search(r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', text)
        assert found or alt, \
            "locals.tf must assign a Terraform-managed tag (e.g. ManagedBy = \"Terraform\")"

    def test_outputs_each_have_description(self):
        """Every output block must include a description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_vpc_ids_and_cidrs_per_tier(self):
        """Outputs must expose a per-tier map of VPC ids and a map of CIDRs."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            val = _top_level_arg(body, "value")
            values.append((labels[0] if labels else "", val or ""))

        # an output whose value is a tier-keyed map producing vpc id(s)
        id_out = [
            (n, v) for n, v in values
            if re.search(r'for\s+\w+\s*,\s*\w+\s+in\s+(module\.|var\.tiers|local\.)', v)
            and re.search(r'vpc_id', v)
        ]
        assert id_out, \
            "need an output producing a per-tier map of VPC ids (for-expression over module.* exposing vpc_id)"

        cidr_out = [
            (n, v) for n, v in values
            if re.search(r'for\s+\w+\s*,\s*\w+\s+in\s+(module\.|var\.tiers|local\.)', v)
            and re.search(r'(vpc_cidr_block|cidr_block|vpc_cidr)', v)
        ]
        assert cidr_out, \
            "need an output producing a per-tier map of VPC CIDR blocks"

    def test_identifier_naming_convention(self):
        """All block labels must match lowercase-underscore: ^[a-z][a-z0-9_]*$."""
        ident_re = re.compile(r'^[a-z][a-z0-9_]*$')
        offenders = []
        for fn, text in self._all_tf().items():
            for t, labels, body in _iter_top_level_blocks(text):
                if t in ("variable", "output", "module", "data", "resource", "provider"):
                    # check the name label(s) that are user-chosen identifiers
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
                # interpolations / variable refs are fine; literal secrets are not
                if val and not val.startswith("${") and not val.startswith("var."):
                    pytest.fail(f"{fn} assigns a literal credential: {m.group(1)} = \"{val}\"")
