"""
Test for 'terraform-module-patterns' skill — Conditional-Endpoints VPC Example.

Variant: ext3. Verifies that the agent authored a new example under
``examples/optional-endpoints/`` that provisions a VPC and *optionally* attaches
a set of VPC endpoints (sourced from ``../../modules/vpc-endpoints``) whose
creation is gated by a boolean ``enable_endpoints`` feature flag, while the
individual endpoints are produced by *keyed iteration* (``for_each``) over a
strongly typed ``endpoints`` map-of-object input — never by a fixed integer
``count``.

Verification strategy
---------------------
This test inspects the generated ``.tf`` files as text using only the Python
standard library (it does NOT invoke any ``terraform`` binary, matching the
variant's acceptance contract). Validation goes far beyond substring matching:
HCL top-level blocks are parsed with a brace-aware tokenizer so that
``variable`` / ``output`` / ``module`` / ``locals`` / ``terraform`` blocks can be
examined individually for their required arguments, types, conditional-creation
meta-arguments, iteration style, naming conventions, and formatting.

Discriminative intent: a naive/stub example — one that hardcodes the endpoints
submodule unconditionally, ignores ``enable_endpoints``, enumerates endpoints
with a fixed integer ``count``, types ``endpoints`` as ``any``, or omits the
Terraform-managed marker tag — MUST fail at least one L2 case below.
"""

import os
import re
import pytest


REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — brace/bracket/string aware.
# ----------------------------------------------------------------------------

def _strip_comments(text):
    """Remove // and # line comments and /* */ block comments (HCL syntax)."""
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
        r'(?m)^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)'                  # block type
        r'((?:[ \t]+(?:"[^"]*"|[a-zA-Z_][a-zA-Z0-9_]*))*)'      # labels
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

    Handles scalar (to end-of-line, continuing across unbalanced brackets) and
    block/list/object values (brace/bracket balanced). None if absent.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # compute brace/bracket depth at this position; only accept depth 0
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
    """Return the inner text of a nested block-style entry `name { ... }`."""
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
    """Validate the examples/optional-endpoints/ conditional-endpoints example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "optional-endpoints")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), \
            f"missing required file: examples/optional-endpoints/{fname}"
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

    def _endpoints_module(self):
        """Return (labels, body, fn) for the module sourcing modules/vpc-endpoints."""
        for labels, body, fn in self._blocks_of_type("module"):
            src = _top_level_arg(body, "source")
            if src and re.search(r'modules/vpc-endpoints"\s*$', src.strip()):
                return labels, body, fn
            if src and "modules/vpc-endpoints" in src:
                return labels, body, fn
        return None

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/optional-endpoints/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/optional-endpoints/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain exactly the five required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and yields at least one HCL block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    def test_main_invokes_root_vpc_and_endpoints_submodule(self):
        """main.tf must call the root VPC module and the vpc-endpoints submodule."""
        modules = self._blocks_of_type("module")
        assert modules, "no module block found in the example"
        sources = [_top_level_arg(b, "source") or "" for _, b, _ in modules]
        assert any('"../../"' in s for s in sources), \
            'no module block sourcing the root VPC module (source = "../../")'
        assert any("modules/vpc-endpoints" in s for s in sources), \
            'no module block sourcing "../../modules/vpc-endpoints"'

    # ====================================================================
    # L2 — deep semantic validation of the variant requirements
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

    def test_versions_declared_only_in_versions_tf(self):
        """Only versions.tf may carry the terraform/provider version requirements."""
        for fn, text in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                if t == "terraform":
                    assert _top_level_arg(body, "required_version") is None, \
                        f"required_version must live only in versions.tf, found in {fn}"
                    assert "required_providers" not in body, \
                        f"required_providers must live only in versions.tf, found in {fn}"

    def test_every_variable_has_type_and_description(self):
        """Each variable block must declare both a type and a description."""
        variables = self._blocks_of_type("variable")
        assert variables, "no variable blocks found"
        for labels, body, fn in variables:
            name = labels[0] if labels else "<unnamed>"
            assert _top_level_arg(body, "type"), \
                f"variable {name} ({fn}) missing a type argument"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"variable {name} ({fn}) missing a non-empty description"

    def test_enable_endpoints_is_bool_variable(self):
        """A boolean 'enable_endpoints' feature flag must be declared."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "enable_endpoints" in variables, \
            "variable 'enable_endpoints' not declared"
        type_rhs = _top_level_arg(variables["enable_endpoints"], "type")
        assert type_rhs and re.search(r'\bbool\b', type_rhs), \
            f"enable_endpoints must be typed bool, got: {type_rhs!r}"

    def test_endpoints_variable_is_map_of_object(self):
        """The 'endpoints' variable must be typed map(object(...)), not any."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "endpoints" in variables, "variable 'endpoints' not declared"
        body = variables["endpoints"]
        type_rhs = _top_level_arg(body, "type")
        assert type_rhs, "endpoints variable has no type"
        assert "map(" in type_rhs and "object(" in type_rhs, \
            f"endpoints type must be a map of object, got: {type_rhs!r}"
        # the object schema, not the map() wrapper, must not be 'any'
        assert not re.search(r'\bany\b', type_rhs.replace("object(", "")), \
            f"endpoints type must not collapse to 'any': {type_rhs!r}"
        # object must carry a string service name and a bool private-dns attribute
        assert re.search(r'=\s*string', type_rhs), \
            f"endpoints object must include a string service-name attribute: {type_rhs!r}"
        assert re.search(r'=\s*bool', type_rhs), \
            f"endpoints object must include a bool private-dns attribute: {type_rhs!r}"

    def test_endpoints_default_has_at_least_two_entries(self):
        """endpoints default must define at least two named entries (e.g. s3, dynamodb)."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables["endpoints"]
        default = _top_level_arg(body, "default")
        assert default, "endpoints variable must provide a default"
        keys = re.findall(r'(?m)^\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*=\s*\{', default)
        keys += re.findall(r'(?m)^\s*"([a-zA-Z_][a-zA-Z0-9_-]*)"\s*=\s*\{', default)
        keys = sorted(set(k for k in keys if k))
        assert len(keys) >= 2, \
            f"endpoints default must contain >= 2 entries, found {keys}"

    def test_endpoints_submodule_creation_gated_by_flag(self):
        """The vpc-endpoints module must be gated by var.enable_endpoints.

        A naive implementation that instantiates the submodule unconditionally
        (no count/for_each referencing enable_endpoints) must fail here.
        """
        found = self._endpoints_module()
        assert found, 'no module sourcing "../../modules/vpc-endpoints"'
        _labels, body, _fn = found

        count = _top_level_arg(body, "count")
        for_each = _top_level_arg(body, "for_each")
        gating = (count or "") + " " + (for_each or "")
        assert count or for_each, \
            "endpoints submodule must use a count/for_each meta-argument to gate creation"
        assert "var.enable_endpoints" in gating or "enable_endpoints" in gating, \
            ("endpoints submodule creation must reference var.enable_endpoints; "
             f"got count={count!r} for_each={for_each!r}")
        if count is not None:
            # must be the conditional form, not a fixed integer
            assert re.search(r'\?', count) and "enable_endpoints" in count, \
                f"count must be a conditional on enable_endpoints, got: {count!r}"
            assert not re.fullmatch(r'\d+', count.strip()), \
                f"count must not be a hardcoded integer: {count!r}"

    def test_endpoints_produced_by_keyed_iteration_not_count(self):
        """Individual endpoints must come from for_each over var.endpoints, not a fixed count.

        Either the submodule passes a map keyed from var.endpoints (so the
        submodule's own for_each enumerates them), or it for_each's over
        var.endpoints directly. A fixed integer count enumerating endpoints fails.
        """
        found = self._endpoints_module()
        assert found, 'no module sourcing "../../modules/vpc-endpoints"'
        _labels, body, _fn = found

        # The endpoints map argument passed to the submodule must derive from
        # var.endpoints (possibly via a local).
        ep_arg = _top_level_arg(body, "endpoints")
        all_tf_text = "\n".join(self._all_tf().values())
        derives_from_endpoints = False
        if ep_arg and ("var.endpoints" in ep_arg or "local." in ep_arg):
            derives_from_endpoints = True
        # for_each directly over var.endpoints is also valid keyed iteration
        for_each = _top_level_arg(body, "for_each") or ""
        if "var.endpoints" in for_each:
            derives_from_endpoints = True
        # or a local map computed from var.endpoints that's referenced here
        if not derives_from_endpoints:
            for lbody in [b for t, l, b in _iter_top_level_blocks(all_tf_text) if t == "locals"]:
                if "var.endpoints" in lbody:
                    derives_from_endpoints = True
                    break
        assert derives_from_endpoints, \
            ("endpoints must be derived from var.endpoints (keyed), "
             f"got endpoints={ep_arg!r} for_each={for_each!r}")

        # No fixed integer count may enumerate the endpoints anywhere.
        for m in re.finditer(r'(?m)^\s*count\s*=\s*(\d+)\s*$', body):
            pytest.fail(f"endpoints submodule uses a hardcoded integer count = {m.group(1)}")

    def test_locals_builds_endpoints_map_and_managed_tag(self):
        """locals.tf must compute the endpoints map and a Terraform-managed tag set."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)
        # derived endpoints map must reference var.endpoints
        assert "var.endpoints" in body, \
            "locals.tf must derive a value from var.endpoints"
        # explicit Terraform-managed marker tag (key = value), not just a comment.
        clean = _strip_comments(body)
        managed = re.search(
            r'(["\']?(ManagedBy|managed_by|managed-by)["\']?)\s*=\s*["\']?[Tt]erraform["\']?',
            clean,
        )
        alt = re.search(r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', clean)
        assert managed or alt, \
            'locals.tf shared tags must include a Terraform-managed marker (e.g. ManagedBy = "Terraform")'

    def test_outputs_each_have_description(self):
        """Every output block must include a non-empty description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_vpc_id_and_endpoint_service_names(self):
        """Outputs must expose the VPC id and the configured endpoint service names."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            val = _top_level_arg(body, "value") or ""
            values.append((labels[0] if labels else "", val))

        vpc_id_out = [
            (n, v) for n, v in values
            if re.search(r'module\.[a-z0-9_]+\.vpc_id', v) or re.search(r'\bvpc_id\b', v)
        ]
        assert vpc_id_out, \
            "need an output exposing the VPC id (e.g. module.vpc.vpc_id)"

        # endpoint service names output: must derive from var.endpoints / the
        # endpoints submodule, and be empty/absent-safe when endpoints disabled.
        svc_out = [
            (n, v) for n, v in values
            if ("var.endpoints" in v or "endpoints" in v.lower())
            and ("service" in v.lower() or "keys(" in v or "for " in v)
        ]
        assert svc_out, (
            "need an output exposing configured endpoint service names derived "
            f"from var.endpoints; outputs were: {[n for n, _ in values]}"
        )
        # disabled-safety: the service-names output must guard for the empty case
        # (a conditional, try(), coalesce, can(), or a for-expression that yields
        # an empty collection when there are no endpoints).
        joined = " ".join(v for _, v in svc_out)
        assert re.search(r'(\?|try\(|coalesce\(|can\(|for\s|enable_endpoints|\[\])', joined), \
            ("endpoint service-names output must be empty/absent-safe when endpoints "
             f"are disabled; got: {joined!r}")

    def test_identifier_naming_convention(self):
        """All top-level block labels must match lowercase-underscore: ^[a-z][a-z0-9_]*$."""
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
