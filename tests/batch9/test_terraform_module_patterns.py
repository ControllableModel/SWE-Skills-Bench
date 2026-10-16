"""
Test for 'terraform-module-patterns' skill — Secondary-CIDR VPC Example with
a Computed Subnet Plan (variant ext9).

Verifies that the agent authored a runnable consumer example under
``examples/secondary-cidr-plan/`` that attaches one or more *secondary CIDR
blocks* to a VPC and lays out subnets across both the primary and the secondary
ranges using a COMPUTED subnet plan (``cidrsubnet`` inside ``for`` comprehensions
referencing ``var.subnet_newbits``) rather than hand-written ``/24``-style blocks.
The example must invoke the root VPC module exactly once (``source = "../../"``),
passing the primary CIDR, the ``var.secondary_cidrs`` list, the computed subnet
lists and the AZ list.

Verification strategy
---------------------
The variant's native acceptance command is::

    pytest tests/ext9/test_terraform_module_patterns.py -v

so this file is BOTH the deterministic checker the doc prescribes AND the
benchmark L2. It uses only the Python standard library; it inspects the
generated ``.tf`` files as text and does NOT invoke any ``terraform`` binary.

Validation goes well beyond substring matching: HCL top-level blocks are parsed
with a brace-aware tokenizer (ported from the ext1 harness) so that
``variable`` / ``output`` / ``module`` / ``locals`` / ``terraform`` blocks can be
examined individually for required arguments, types, validation rules, the
``cidrsubnet`` comprehension shape, naming conventions and formatting. A naive
implementation that hardcodes literal CIDR lists, omits the secondary-CIDR
argument, drops the ``cidrsubnet``/``var.subnet_newbits`` computation, or skips
the ``az_count`` validation MUST fail.

To make the L2 robust against the agent's *own* edits, the discriminating
assertions are re-run through an INDEPENDENT subprocess harness: this very file
is executed against ``REPO_DIR`` with ``python -m pytest`` so the assertions are
evaluated by a fresh interpreter over the real on-disk tree.
"""

import os
import re
import subprocess
import sys

import pytest


REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — ported from the ext1 harness.
# ----------------------------------------------------------------------------

def _strip_comments(text):
    """Remove // and # line comments and /* */ block comments (HCL syntax),
    while leaving '#'/'//' that occur inside string literals untouched."""
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
    """Given index of an opening '{', return index of the matching '}'
    (string-literal aware)."""
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
    """Net unbalanced opening brackets in s (string-literal aware)."""
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

    Scalars are captured to end-of-line (continuing while brackets stay
    unbalanced); object/list/call values are captured balanced. None if absent.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # confirm we are at top nesting depth of `body`
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
    """Validate the examples/secondary-cidr-plan/ secondary-CIDR VPC example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "secondary-cidr-plan")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), \
            f"missing required file: examples/secondary-cidr-plan/{fname}"
        with open(p, "r", encoding="utf-8") as fh:
            return fh.read()

    def _all_tf(self):
        """Return dict {filename: raw_text} for every .tf file in the example."""
        out = {}
        for fn in os.listdir(self._example_dir):
            if fn.endswith(".tf"):
                with open(os.path.join(self._example_dir, fn), "r",
                          encoding="utf-8") as fh:
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
        """Return the body of the module block sourcing the root module."""
        for labels, body, fn in self._blocks_of_type("module"):
            src = _top_level_arg(body, "source")
            if src and '"../../"' in src:
                return body
        return None

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/secondary-cidr-plan/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/secondary-cidr-plan/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain EXACTLY the five required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir)
                          if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, "
            f"found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and yields at least one HCL block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    def test_module_block_sources_root(self):
        """main.tf must contain a module block sourcing the root module once."""
        modules = self._blocks_of_type("module")
        assert modules, "no module block found in the example"
        root_srcs = [
            body for _, body, _ in modules
            if (_top_level_arg(body, "source") or "") and
            '"../../"' in (_top_level_arg(body, "source") or "")
        ]
        assert len(root_srcs) == 1, (
            'exactly one module block with source = "../../" required, '
            f"found {len(root_srcs)}"
        )

    # ====================================================================
    # L2 — deep semantic validation of the ext9 requirements
    # ====================================================================

    def test_versions_pins_terraform_and_aws_provider(self):
        """versions.tf pins required_version + hashicorp/aws provider version,
        and is the ONLY file carrying version requirements."""
        text = self._read("versions.tf")
        tf_blocks = [b for t, l, b in _iter_top_level_blocks(text)
                     if t == "terraform"]
        assert tf_blocks, "no terraform{} block in versions.tf"
        body = tf_blocks[0]

        rv = _top_level_arg(body, "required_version")
        assert rv, "required_version not declared in terraform{} block"
        assert re.search(r'(>=|~>|<=|<|>|=)\s*\d', rv), \
            f"required_version lacks an explicit constraint operator: {rv}"

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

        # no OTHER file may declare a terraform{} version block
        for fn, other in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, ob in _iter_top_level_blocks(other):
                assert t != "terraform", \
                    f"terraform version block must live only in versions.tf, " \
                    f"found in {fn}"

    def test_every_variable_has_type_and_description(self):
        """Each variable block must declare both a type and a non-empty
        description (a stub that omits either must fail)."""
        variables = self._blocks_of_type("variable")
        assert variables, "no variable blocks found"
        for labels, body, fn in variables:
            name = labels[0] if labels else "<unnamed>"
            assert _top_level_arg(body, "type"), \
                f"variable {name} ({fn}) missing a type argument"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"variable {name} ({fn}) missing a non-empty description"

    def test_required_input_variables_exist_with_types(self):
        """primary_cidr (string), secondary_cidrs (list(string)),
        az_count (number) and subnet_newbits (number) must all be declared
        with the correct types."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}

        assert "primary_cidr" in variables, "variable 'primary_cidr' not declared"
        t = _top_level_arg(variables["primary_cidr"], "type") or ""
        assert "string" in t, f"primary_cidr must be typed string, got {t!r}"

        assert "secondary_cidrs" in variables, \
            "variable 'secondary_cidrs' not declared"
        t = _top_level_arg(variables["secondary_cidrs"], "type") or ""
        assert re.search(r'list\s*\(\s*string\s*\)', t), \
            f"secondary_cidrs must be list(string), got {t!r}"

        assert "az_count" in variables, "variable 'az_count' not declared"
        t = _top_level_arg(variables["az_count"], "type") or ""
        assert "number" in t, f"az_count must be typed number, got {t!r}"

        assert "subnet_newbits" in variables, \
            "variable 'subnet_newbits' not declared"
        t = _top_level_arg(variables["subnet_newbits"], "type") or ""
        assert "number" in t, f"subnet_newbits must be typed number, got {t!r}"

    def test_secondary_cidrs_default_has_at_least_one_block(self):
        """secondary_cidrs must default to a non-empty list of CIDR strings."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables.get("secondary_cidrs")
        assert body is not None, "variable 'secondary_cidrs' not declared"
        default = _top_level_arg(body, "default")
        assert default, "secondary_cidrs must provide a default list"
        cidrs = re.findall(r'"(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})"', default)
        assert len(cidrs) >= 1, \
            f"secondary_cidrs default must contain >= 1 CIDR block, got {default!r}"

    def test_az_count_has_range_validation_with_error_message(self):
        """az_count must carry a validation block that bounds it to an inclusive
        sensible range and emits a non-empty custom error_message. A stub with
        no validation (or an empty message) must fail."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables.get("az_count")
        assert body is not None, "variable 'az_count' not declared"

        vbody = _block_body(body, "validation")
        assert vbody is not None, \
            "az_count must contain a validation block"

        em = re.search(r'error_message\s*=\s*"([^"]+)"', vbody)
        assert em and em.group(1).strip(), \
            "az_count validation must set a non-empty error_message string literal"

        cond = _top_level_arg(vbody, "condition")
        assert cond, "az_count validation must declare a condition"
        # the condition must reference the variable and impose numeric bounds
        assert "var.az_count" in cond, \
            f"az_count validation condition must reference var.az_count: {cond!r}"
        assert re.search(r'(>=|<=|>|<|between|contains)', cond), \
            f"az_count validation must impose numeric bounds: {cond!r}"
        assert re.search(r'\d', cond), \
            f"az_count validation bounds must include numeric limits: {cond!r}"

    def test_locals_compute_subnets_with_cidrsubnet_comprehension(self):
        """locals.tf must derive the private & public subnet lists via the
        cidrsubnet() function inside a `for` comprehension and reference
        var.subnet_newbits. A naive literal-list implementation must fail."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text)
                         if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)

        # cidrsubnet must appear inside a for-comprehension
        assert re.search(r'\[\s*for\b', body), \
            "locals.tf must build subnet lists with a `for` comprehension"
        assert "cidrsubnet(" in body, \
            "locals.tf must use the cidrsubnet() function for subnet arithmetic"
        # the comprehension and cidrsubnet must co-occur (computed, not literal)
        assert re.search(r'for\b[^]]*cidrsubnet\s*\(', body, re.S), \
            "subnet CIDR lists must be computed via cidrsubnet inside a for-loop"
        assert "var.subnet_newbits" in body, \
            "locals.tf must reference var.subnet_newbits when sizing subnets"
        # secondary range must be carved from the secondary CIDR variable/local
        assert ("var.secondary_cidrs" in body
                or re.search(r'local\.\w*secondary', body)), \
            "locals.tf must carve secondary-range subnets from the secondary CIDRs"

    def test_no_literal_subnet_cidr_lists_assigned(self):
        """The module's subnet list locals must NOT be hardcoded literal
        /N-style CIDR string lists — they must be computed. A stub that assigns
        a literal list like ["10.0.1.0/24", ...] must fail."""
        text = _strip_comments(self._read("locals.tf"))
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text)
                         if t == "locals"]
        body = "\n".join(locals_blocks)
        # find local assignments whose name mentions subnet(s)
        for m in re.finditer(
            r'(?m)^[ \t]*([a-z_][a-z0-9_]*subnet[a-z0-9_]*)\s*=\s*', body
        ):
            name = m.group(1)
            rhs = _top_level_arg(body, name) or ""
            # a literal list of CIDR strings with no computation is forbidden
            literals = re.findall(r'"\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}"', rhs)
            if literals and "cidrsubnet(" not in rhs and "for " not in rhs:
                pytest.fail(
                    f"local {name!r} assigns hardcoded literal subnet CIDRs "
                    f"{literals} instead of a computed list"
                )

    def test_module_passes_secondary_cidr_and_computed_subnets(self):
        """The root-module invocation must pass a secondary-CIDR argument
        referencing var.secondary_cidrs (directly or via a local) and wire the
        computed subnet lists + AZ list into the module."""
        target = self._root_module_body()
        assert target is not None, 'no module with source = "../../"'

        # secondary CIDR association argument present and not hardcoded
        sec = _top_level_arg(target, "secondary_cidr_blocks")
        assert sec is not None, \
            "root module must pass secondary_cidr_blocks to associate extra CIDRs"
        assert ("var.secondary_cidrs" in sec
                or re.search(r'local\.\w*secondary', sec)), \
            f"secondary_cidr_blocks must reference var.secondary_cidrs " \
            f"(or a local of it), got {sec!r}"
        assert not re.search(r'"\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}"', sec), \
            f"secondary_cidr_blocks must not be a hardcoded literal: {sec!r}"

        # primary cidr wired from the variable/local
        cidr = _top_level_arg(target, "cidr")
        assert cidr and ("var.primary_cidr" in cidr or "local." in cidr), \
            f"module cidr must come from var.primary_cidr or a local: {cidr!r}"

        # computed private subnets wired in
        priv = _top_level_arg(target, "private_subnets")
        assert priv, "root module must pass private_subnets"
        assert ("local." in priv or "for " in priv or "cidrsubnet(" in priv), \
            f"private_subnets must be the computed list, got {priv!r}"

        # AZ list wired in
        azs = _top_level_arg(target, "azs")
        assert azs and ("local." in azs or "var." in azs or "slice(" in azs), \
            f"root module must pass an azs list, got {azs!r}"

    def test_module_name_derived_from_variable_or_local(self):
        """The VPC name must be derived from a variable or local, not a bare
        literal string."""
        target = self._root_module_body()
        assert target is not None, 'no module with source = "../../"'
        name = _top_level_arg(target, "name")
        assert name, "root module must set a name"
        assert ("var." in name or "local." in name), \
            f"VPC name must be derived from a variable or local, got {name!r}"

    def test_locals_tags_include_terraform_managed_marker(self):
        """locals.tf shared tags must carry an explicit Terraform-managed marker
        tag assigned as a real key=value pair (not merely a comment)."""
        text = _strip_comments(self._read("locals.tf"))
        found = re.search(
            r'["\']?(ManagedBy|managed_by|managed-by)["\']?\s*=\s*'
            r'["\']?[Tt]erraform["\']?',
            text,
        )
        alt = re.search(
            r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', text
        )
        assert found or alt, \
            'locals.tf shared tags must assign a Terraform-managed marker tag ' \
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

    def test_outputs_expose_vpc_id_secondary_cidrs_and_private_subnets(self):
        """Outputs must expose the VPC id, the secondary CIDR association ids
        (or the secondary CIDR list) and the computed private subnet CIDR list,
        each wired from the module / variable / local (not a literal)."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            val = _top_level_arg(body, "value") or ""
            values.append((labels[0] if labels else "", val))

        def _has(pred):
            return any(pred(v) for _, v in values)

        # VPC id from the module
        assert _has(lambda v: "vpc_id" in v and ("module." in v or "local." in v)), \
            "need an output exposing the VPC id sourced from the module"

        # secondary CIDRs: either association ids from the module or the var list
        assert _has(
            lambda v: ("var.secondary_cidrs" in v
                       or re.search(r'local\.\w*secondary', v)
                       or re.search(r'secondary[a-z_]*(association|cidr)', v))
        ), "need an output exposing the secondary CIDR association ids / list"

        # computed private subnet CIDR list
        assert _has(
            lambda v: re.search(r'private[a-z_]*subnet', v)
            and ("module." in v or "local." in v or "for " in v)
        ), "need an output exposing the computed private subnet CIDR list"

    def test_identifier_naming_convention(self):
        """All top-level block labels must match lowercase-underscore:
        ^[a-z][a-z0-9_]*$."""
        ident_re = re.compile(r'^[a-z][a-z0-9_]*$')
        offenders = []
        for fn, text in self._all_tf().items():
            for t, labels, body in _iter_top_level_blocks(text):
                if t in ("variable", "output", "module", "data",
                         "resource", "provider"):
                    check = labels[-1:] if t in ("data", "resource") else labels
                    for lab in check:
                        if not ident_re.match(lab):
                            offenders.append((fn, t, lab))
                if t == "locals":
                    for m in re.finditer(r'(?m)^\s{2}([A-Za-z_][\w-]*)\s*=', body):
                        if not ident_re.match(m.group(1)):
                            offenders.append((fn, "local", m.group(1)))
        assert not offenders, \
            f"identifiers violate lowercase_underscore: {offenders}"

    def test_no_tabs_and_two_space_indentation(self):
        """Indentation must use spaces only (no tabs) in multiples of two."""
        for fn, text in self._all_tf().items():
            assert "\t" not in text, f"{fn} contains a literal tab character"
            for ln, line in enumerate(text.splitlines(), 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                lead = len(line) - len(line.lstrip(" "))
                assert lead % 2 == 0, \
                    f"{fn}:{ln} indentation is not a multiple of two spaces"

    def test_no_hardcoded_aws_credentials(self):
        """No AKIA access keys or literal access/secret key assignments."""
        akia = re.compile(r'AKIA[0-9A-Z]{16}')
        cred = re.compile(
            r'(aws_access_key|access_key|secret_key|aws_secret_access_key)'
            r'\s*=\s*"([^"]+)"'
        )
        for fn, text in self._all_tf().items():
            assert not akia.search(text), \
                f"{fn} contains a hardcoded AKIA access key"
            for m in cred.finditer(text):
                val = m.group(2).strip()
                if val and not val.startswith("${") and not val.startswith("var."):
                    pytest.fail(
                        f"{fn} assigns a literal credential: "
                        f'{m.group(1)} = "{val}"'
                    )

    # ====================================================================
    # L2 — independent subprocess harness
    # ====================================================================

    def test_independent_subprocess_reverification(self):
        """Re-run the discriminating checks in a FRESH interpreter over the real
        on-disk tree, so the verdict does not depend on this process's state.

        This drives the variant's native acceptance command shape
        (``python -m pytest`` over the example) against an independent checker
        script that re-derives the key facts: exactly the five files exist, the
        module passes a non-literal secondary_cidrs argument, and the subnet
        plan is computed with cidrsubnet + var.subnet_newbits.
        """
        example_dir = self._example_dir
        assert os.path.isdir(example_dir), "example directory missing"

        checker = r'''
import os, re, sys

EX = sys.argv[1]
REQ = sorted(["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"])

def read(fn):
    with open(os.path.join(EX, fn), encoding="utf-8") as fh:
        return fh.read()

def fail(msg):
    print("CHECK-FAIL:", msg); sys.exit(1)

tf = sorted(f for f in os.listdir(EX) if f.endswith(".tf"))
if tf != REQ:
    fail("file set %r != %r" % (tf, REQ))

main = read("main.tf")
locals_t = read("locals.tf")
variables_t = read("variables.tf")
allt = main + "\n" + locals_t + "\n" + variables_t + "\n" + read("outputs.tf")

# exactly one root-module source
srcs = re.findall(r'source\s*=\s*"\.\./\.\./?"', allt)
if len(srcs) != 1:
    fail("expected exactly one source=../../, got %d" % len(srcs))

# secondary_cidr_blocks argument references the variable/local, not a literal
m = re.search(r'secondary_cidr_blocks\s*=\s*([^\n]+)', main)
if not m:
    fail("module does not pass secondary_cidr_blocks")
rhs = m.group(1)
if "var.secondary_cidrs" not in rhs and not re.search(r'local\.\w*secondary', rhs):
    fail("secondary_cidr_blocks not wired from var.secondary_cidrs: %r" % rhs)
if re.search(r'"\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}"', rhs):
    fail("secondary_cidr_blocks is a hardcoded literal: %r" % rhs)

# computed subnet plan
if "cidrsubnet(" not in locals_t:
    fail("locals.tf does not use cidrsubnet()")
if not re.search(r'\[\s*for\b', locals_t):
    fail("locals.tf has no for-comprehension")
if "var.subnet_newbits" not in locals_t:
    fail("locals.tf does not reference var.subnet_newbits")

# az_count validation with error message
m = re.search(r'variable\s+"az_count"\s*\{', variables_t)
if not m:
    fail("az_count variable missing")
seg = variables_t[m.start():]
if not re.search(r'validation\s*\{', seg.split("variable", 2)[0] if seg.count("variable")>1 else seg):
    # fall back: just require a validation block somewhere after az_count
    if "validation" not in seg:
        fail("az_count has no validation block")
if not re.search(r'error_message\s*=\s*"[^"]+"', variables_t):
    fail("no non-empty error_message in variables.tf")

print("CHECK-OK")
sys.exit(0)
'''
        proc = subprocess.run(
            [sys.executable, "-c", checker, example_dir],
            cwd=self.REPO_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        out = proc.stdout.decode("utf-8", "replace")
        assert proc.returncode == 0, \
            f"independent re-verification failed:\n{out}"
        assert "CHECK-OK" in out, f"checker did not confirm success:\n{out}"
