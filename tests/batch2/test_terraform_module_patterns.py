"""
Test for 'terraform-module-patterns' skill — Per-Environment VPC Example with
Validated Sizing (variant ext2).

Verifies that the agent authored a runnable example under
``examples/env-sizing/`` that provisions a SINGLE VPC whose subnet sizing is
driven entirely by validated scalar input variables (``environment``,
``vpc_cidr``, ``subnet_newbits``, ``az_count``).  The same configuration can be
re-targeted to dev/staging/prod by changing only inputs:

  * ``environment`` is constrained to an explicit allow-list (custom error).
  * ``subnet_newbits`` is constrained to an inclusive numeric range (custom error).
  * public/private subnet CIDRs are DERIVED in ``locals.tf`` via ``cidrsubnet``
    from ``vpc_cidr`` + ``var.subnet_newbits`` — never hardcoded literal blocks.
  * the root module (``source = "../../"``) is invoked exactly once, with a
    ``name`` that incorporates the ``environment`` value.

This test inspects the generated ``.tf`` files as text using only the Python
standard library (it does NOT invoke any ``terraform`` binary, matching the
acceptance command ``pytest tests/ext2/test_terraform_module_patterns.py -v``).
Validation goes beyond substring matching: HCL top-level blocks are parsed with
a brace-aware tokenizer so individual ``variable`` / ``output`` / ``module`` /
``locals`` / ``terraform`` blocks can be examined for required arguments, types,
validation rules, naming conventions, derivation, and formatting.

Discriminative intent (a naive/stub implementation MUST fail):
  * hardcoding literal ``/24`` subnet lists instead of ``cidrsubnet(...)`` -> fail
  * omitting the ``environment``/``subnet_newbits`` ``validation`` blocks -> fail
  * using ``count`` / multiple module invocations -> fail
  * a ``name`` that ignores ``var.environment`` -> fail
  * declaring versions in more than one file -> fail
"""

import os
import re
import pytest


REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — proven by the ext1 harness.
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
        r'(?m)^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)'                 # block type
        r'((?:[ \t]+(?:"[^"]*"|[a-zA-Z_][a-zA-Z0-9_]*))*)'     # labels
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
    block for nested object/list values. None if absent.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # compute brace/bracket depth at this candidate position
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


def _validation_blocks(body):
    """Yield the inner text of every `validation { ... }` block inside body."""
    for m in re.finditer(r'(?m)^[ \t]*validation[ \t]*\{', body):
        open_idx = body.index("{", m.start())
        close_idx = _find_matching_brace(body, open_idx)
        if close_idx == -1:
            continue
        yield body[open_idx + 1:close_idx]


# ----------------------------------------------------------------------------
# Test class
# ----------------------------------------------------------------------------

class TestTerraformModulePatterns:
    """Validate the examples/env-sizing/ single-VPC validated-sizing example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "env-sizing")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), f"missing required file: examples/env-sizing/{fname}"
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

    def _variables(self):
        return {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}

    def _root_module_body(self):
        for labels, body, fn in self._blocks_of_type("module"):
            src = _top_level_arg(body, "source")
            if src and '"../../"' in src:
                return body
        return None

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/env-sizing/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/env-sizing/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain EXACTLY the five required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, "
            f"found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and parses at least one HCL block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable top-level HCL block"

    def test_module_block_sources_root(self):
        """main.tf must contain a module block sourcing the root module."""
        body = self._root_module_body()
        assert body is not None, 'no module block with source = "../../" found'

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
            f"required_version lacks an explicit constraint operator: {rv!r}"

        rp = _block_body(body, "required_providers")
        if rp is None:
            rp = _top_level_arg(body, "required_providers")
        assert rp, "required_providers block missing in versions.tf"
        assert re.search(r'source\s*=\s*"hashicorp/aws"', rp), \
            'aws provider source must be exactly "hashicorp/aws"'
        m = re.search(r'aws\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"', rp, re.S)
        assert m, "aws provider must declare a pinned version constraint"
        assert re.search(r'(>=|~>|<=|<|>|=)\s*\d', m.group(1)), \
            f"aws provider version is not a pinned constraint: {m.group(1)!r}"

    def test_only_versions_file_declares_version_requirements(self):
        """Only versions.tf may carry terraform/provider version requirements."""
        for fn, text in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                assert t != "terraform", \
                    f"terraform version block must live only in versions.tf, found in {fn}"
                assert "required_providers" not in body, \
                    f"required_providers must live only in versions.tf, found in {fn}"
                assert "required_version" not in body, \
                    f"required_version must live only in versions.tf, found in {fn}"

    def test_required_variables_declared_with_type_and_description(self):
        """The four sizing variables exist, each with a type AND description."""
        variables = self._variables()
        for needed in ("environment", "vpc_cidr", "subnet_newbits", "az_count"):
            assert needed in variables, f"variable '{needed}' not declared"
        # every variable (not just the four) must carry type + description
        for labels, body, fn in self._blocks_of_type("variable"):
            name = labels[0] if labels else "<unnamed>"
            assert _top_level_arg(body, "type"), \
                f"variable {name} ({fn}) missing a type argument"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"variable {name} ({fn}) missing a non-empty description"

    def test_variable_types_are_correct(self):
        """environment/vpc_cidr are string; subnet_newbits/az_count are number."""
        variables = self._variables()
        assert "string" in (_top_level_arg(variables["environment"], "type") or ""), \
            "environment must be typed string"
        assert "string" in (_top_level_arg(variables["vpc_cidr"], "type") or ""), \
            "vpc_cidr must be typed string"
        assert "number" in (_top_level_arg(variables["subnet_newbits"], "type") or ""), \
            "subnet_newbits must be typed number"
        assert "number" in (_top_level_arg(variables["az_count"], "type") or ""), \
            "az_count must be typed number"

    def test_environment_has_allowlist_validation(self):
        """environment must have a validation block checking an allow-list with
        a non-empty custom error_message (a naive var with no validation fails)."""
        variables = self._variables()
        body = variables["environment"]
        vbodies = list(_validation_blocks(body))
        assert vbodies, "environment variable must contain a validation block"
        joined = "\n".join(vbodies)
        cond = re.search(r'condition\s*=\s*(.+)', joined)
        assert cond, "environment validation must declare a condition"
        # allow-list semantics: contains([...], var.environment) or `in [...]`
        assert re.search(r'(contains\s*\(|\bin\s*\[|anytrue|alltrue|for\s)', cond.group(1)), \
            f"environment validation must check an allow-list: {cond.group(1)!r}"
        em = re.search(r'error_message\s*=\s*"([^"]+)"', joined)
        assert em and em.group(1).strip(), \
            "environment validation must set a non-empty error_message string literal"

    def test_subnet_newbits_has_numeric_range_validation(self):
        """subnet_newbits must validate an inclusive numeric range with a custom
        error_message; the condition must compare against numeric bounds."""
        variables = self._variables()
        body = variables["subnet_newbits"]
        vbodies = list(_validation_blocks(body))
        assert vbodies, "subnet_newbits variable must contain a validation block"
        joined = "\n".join(vbodies)
        cond = re.search(r'condition\s*=\s*(.+)', joined)
        assert cond, "subnet_newbits validation must declare a condition"
        condtext = cond.group(1)
        # a real numeric range references the variable and uses comparison ops
        assert "var.subnet_newbits" in condtext, \
            f"subnet_newbits validation must reference var.subnet_newbits: {condtext!r}"
        assert re.search(r'(>=|<=|>|<)\s*\d', condtext) or re.search(r'\d\s*(>=|<=|>|<)', condtext), \
            f"subnet_newbits validation must bound a numeric range: {condtext!r}"
        em = re.search(r'error_message\s*=\s*"([^"]+)"', joined)
        assert em and em.group(1).strip(), \
            "subnet_newbits validation must set a non-empty error_message string literal"

    def test_subnet_cidrs_derived_via_cidrsubnet(self):
        """locals.tf must derive subnet CIDRs with cidrsubnet referencing both
        vpc_cidr and var.subnet_newbits — NOT hardcoded literal blocks."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)
        assert "cidrsubnet(" in body, \
            "locals.tf must compute subnet CIDRs with the cidrsubnet() function"
        assert "var.subnet_newbits" in body, \
            "cidrsubnet derivation must reference var.subnet_newbits (newbits arg)"
        # the base must come from vpc_cidr (var or a local derived from it)
        assert re.search(r'cidrsubnet\([^)]*(var\.vpc_cidr|local\.\w*cidr\w*)', body, re.S), \
            "cidrsubnet must derive subnets from vpc_cidr (var.vpc_cidr or local)"

    def test_no_literal_subnet_cidrs_assigned_to_module(self):
        """The module's subnet lists must not be hardcoded /24-style literals.

        A stub that writes `private_subnets = ["10.0.1.0/24", ...]` must fail.
        """
        body = self._root_module_body()
        assert body is not None, 'no module with source = "../../"'
        for arg in ("private_subnets", "public_subnets"):
            rhs = _top_level_arg(body, arg)
            if rhs is None:
                continue
            # a literal CIDR list assigned directly is forbidden
            assert not re.search(r'"\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}"', rhs), \
                f"{arg} must be derived (local/cidrsubnet), not a literal CIDR list: {rhs!r}"
            # it should reference a local or cidrsubnet derivation
            assert ("local." in rhs) or ("cidrsubnet" in rhs), \
                f"{arg} must reference derived locals or cidrsubnet, got: {rhs!r}"
        # also: no literal subnet CIDR list should exist anywhere as a module arg
        # within locals it's fine to compute, but the supplied lists must derive.

    def test_module_invoked_exactly_once_without_count_or_foreach(self):
        """The root module must be invoked exactly once (single VPC), with no
        count/for_each (this variant is single-VPC, unlike the multi-tier ext1)."""
        roots = [
            (labels, body, fn)
            for labels, body, fn in self._blocks_of_type("module")
            if (_top_level_arg(body, "source") or "").find('"../../"') != -1
        ]
        assert len(roots) == 1, \
            f'root module (source="../../") must appear exactly once, found {len(roots)}'
        body = roots[0][1]
        assert _top_level_arg(body, "count") is None and \
            not re.search(r'(?m)^\s*count\s*=', body), \
            "single-VPC example must not use count on the module"
        assert _top_level_arg(body, "for_each") is None and \
            not re.search(r'(?m)^\s*for_each\s*=', body), \
            "single-VPC example must not use for_each on the module"

    def test_module_name_incorporates_environment(self):
        """The VPC name must incorporate var.environment (a hardcoded name fails)."""
        body = self._root_module_body()
        assert body is not None, 'no module with source = "../../"'
        name = _top_level_arg(body, "name")
        assert name, "root module must set a name"
        assert ("var.environment" in name) or ("local." in name and
                re.search(r'environment', "\n".join(
                    b for t, l, b in _iter_top_level_blocks(self._read("locals.tf"))
                    if t == "locals"))), \
            f"VPC name must incorporate the environment value, got: {name!r}"
        # interpolation, not a bare static literal
        assert ("${" in name) or name.strip().startswith(("local.", "var.", "format(")), \
            f"VPC name must be interpolated from the environment, got: {name!r}"

    def test_module_receives_derived_azs_and_tags(self):
        """The module invocation must pass locally-derived AZ list and tags."""
        body = self._root_module_body()
        assert body is not None, 'no module with source = "../../"'
        azs = _top_level_arg(body, "azs")
        assert azs and "local." in azs, \
            f"module azs must come from a derived local, got: {azs!r}"
        tags = _top_level_arg(body, "tags")
        assert tags and "local." in tags, \
            f"module tags must come from a derived local, got: {tags!r}"

    def test_locals_compute_azs_and_terraform_managed_tag(self):
        """locals.tf must compute the AZ selection and a Terraform-managed tag
        plus an environment-name tag (not hardcoded inline in the module)."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)
        # AZ list derived from data source + az_count
        assert "var.az_count" in body or re.search(r'slice\s*\(', body), \
            "locals.tf must derive the AZ selection (e.g. slice(..., var.az_count))"
        # Terraform-managed marker tag as a real key=value, not a comment
        clean = _strip_comments(body)
        managed = re.search(
            r'(["\']?(ManagedBy|managed_by|managed-by)["\']?)\s*=\s*["\']?[Tt]erraform["\']?',
            clean,
        ) or re.search(r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', clean)
        assert managed, \
            'locals.tf must assign a Terraform-managed tag (e.g. ManagedBy = "Terraform")'
        # environment-name tag references var.environment
        assert "var.environment" in clean, \
            "the shared tag set must carry the environment name (var.environment)"

    def test_outputs_each_have_description(self):
        """Every output block must include a non-empty description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_vpc_id_cidr_and_private_subnets(self):
        """Outputs must expose the VPC id, the VPC CIDR block, and the list of
        private subnet ids — each derived from the single module instance."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            values.append(_top_level_arg(body, "value") or "")
        blob = "\n".join(values)
        assert re.search(r'module\.\w+\.vpc_id\b', blob), \
            "an output must expose module.<vpc>.vpc_id"
        assert re.search(r'module\.\w+\.vpc_cidr_block\b', blob) or \
            re.search(r'module\.\w+\.(cidr_block|vpc_cidr)\b', blob), \
            "an output must expose the VPC CIDR block (module.<vpc>.vpc_cidr_block)"
        assert re.search(r'module\.\w+\.private_subnets\b', blob), \
            "an output must expose module.<vpc>.private_subnets (list of private subnet ids)"

    def test_identifier_naming_convention(self):
        """All user identifiers must match lowercase-underscore: ^[a-z][a-z0-9_]*$."""
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

    def test_no_tabs_and_two_space_indentation(self):
        """Indentation must use spaces only, in multiples of two (no tabs)."""
        for fn, text in self._all_tf().items():
            assert "\t" not in text, f"{fn} contains a literal tab character"
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
