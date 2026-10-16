"""
Test for 'terraform-module-patterns' skill — Secure VPC Flow-Log Example (ext7).

Verifies that the agent authored a runnable example under
``examples/secure-flow-log/`` that creates a VPC (via ``source = "../../"``) and
ships its VPC flow logs to a destination whose *type* and *retention* are driven
by validated inputs, with a **sensitive** KMS key id input that must never be
rendered in plan/state output.

This is a DISTINCT task from the ext1 ``examples/multi-tier/`` multi-VPC example:
different deliverable directory, different variables
(``flow_log_destination_type`` / ``log_retention_days`` / ``flow_log_kms_key_id``),
different validation rules, and a sensitivity requirement that ext1 does not have.

Per the variant's Acceptance Criteria, this test uses ONLY the Python standard
library and inspects the generated ``.tf`` files as text — it does NOT invoke the
``terraform`` binary. The native acceptance command is::

    pytest tests/ext7/test_terraform_module_patterns.py -v

Validation goes well beyond substring matching: HCL top-level blocks are parsed
with a brace-aware tokenizer so each ``variable`` / ``output`` / ``module`` /
``locals`` / ``terraform`` block is examined individually for its required
arguments, types, validation rules, sensitivity markers, naming, and formatting.
A naive stub (omitting a validation block, leaving the KMS input non-sensitive,
hardcoding the destination type, or dropping the root-module invocation) fails.
"""

import os
import re
import pytest


REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — shared brace/string-aware tokenizer.
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

    Returns the value up to end-of-line for scalars, or the full balanced block
    for nested object/list values. None if absent at depth 0.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # compute brace/bracket depth at this offset
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
    """Yield the inner text of each `validation { ... }` block in a variable body."""
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
    """Validate the examples/secure-flow-log/ encrypted-flow-log Terraform example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "secure-flow-log")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), \
            f"missing required file: examples/secure-flow-log/{fname}"
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

    def _variables_by_name(self):
        return {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/secure-flow-log/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/secure-flow-log/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain exactly the five required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and parses to >= 1 top-level block.

        (locals.tf needs a locals block; main.tf needs blocks; etc.)
        """
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

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

    def test_destination_type_validation_allowlist(self):
        """flow_log_destination_type must be a string with an allow-list validation.

        A naive stub that hardcodes the destination or omits the validation block
        (or leaves error_message empty) must fail here.
        """
        variables = self._variables_by_name()
        assert "flow_log_destination_type" in variables, \
            "variable 'flow_log_destination_type' not declared"
        body = variables["flow_log_destination_type"]

        type_rhs = _top_level_arg(body, "type")
        assert type_rhs and "string" in type_rhs, \
            f"flow_log_destination_type must be typed string, got {type_rhs!r}"

        vblocks = list(_validation_blocks(body))
        assert vblocks, "flow_log_destination_type must contain a validation block"
        joined = "\n".join(vblocks)

        em = re.search(r'error_message\s*=\s*"([^"]+)"', joined)
        assert em and em.group(1).strip(), \
            "flow_log_destination_type validation must set a non-empty error_message"

        cond = "\n".join(re.findall(r'condition\s*=\s*(.+)', joined))
        assert cond, "flow_log_destination_type validation must declare a condition"
        assert re.search(r'(contains\s*\(|\bin\b\s*\[|anytrue)', cond), \
            f"destination_type validation must check an allow-list: {cond!r}"
        # The allow-list itself must enumerate the permitted destinations.
        assert re.search(r'(cloud-watch-logs|cloudwatch)', joined, re.I) and \
            re.search(r'"s3"', joined), \
            "validation allow-list must enumerate cloud-watch-logs and s3"

    def test_log_retention_days_validation_allowlist(self):
        """log_retention_days must be a number constrained to AWS-permitted values.

        AWS only permits a fixed set (1,3,5,7,14,...). The validation must reject
        an arbitrary value; a stub with no validation block fails this test.
        """
        variables = self._variables_by_name()
        assert "log_retention_days" in variables, \
            "variable 'log_retention_days' not declared"
        body = variables["log_retention_days"]

        type_rhs = _top_level_arg(body, "type")
        assert type_rhs and "number" in type_rhs, \
            f"log_retention_days must be typed number, got {type_rhs!r}"

        vblocks = list(_validation_blocks(body))
        assert vblocks, "log_retention_days must contain a validation block"
        joined = "\n".join(vblocks)

        em = re.search(r'error_message\s*=\s*"([^"]+)"', joined)
        assert em and em.group(1).strip(), \
            "log_retention_days validation must set a non-empty error_message"

        cond = "\n".join(re.findall(r'condition\s*=\s*(.+)', joined))
        assert re.search(r'(contains\s*\(|\bin\b\s*\[|anytrue)', cond), \
            f"retention validation must check an allow-list: {cond!r}"
        # The permitted AWS retention set should be enumerated; spot-check a few
        # canonical values that are members of the allowed set.
        nums = set(re.findall(r'\b(\d+)\b', joined))
        canonical = {"1", "3", "5", "7", "14", "30", "60", "90"}
        assert len(nums & canonical) >= 4, (
            "retention validation must enumerate the AWS-permitted day values "
            f"(found numbers {sorted(nums)})"
        )

    def test_kms_key_variable_is_sensitive_with_description(self):
        """flow_log_kms_key_id must be a string marked sensitive = true.

        This is the discriminating requirement of the variant: a stub that
        declares the variable but forgets `sensitive = true` must fail.
        """
        variables = self._variables_by_name()
        assert "flow_log_kms_key_id" in variables, \
            "variable 'flow_log_kms_key_id' not declared"
        body = variables["flow_log_kms_key_id"]

        type_rhs = _top_level_arg(body, "type")
        assert type_rhs and "string" in type_rhs, \
            f"flow_log_kms_key_id must be typed string, got {type_rhs!r}"

        desc = _top_level_arg(body, "description")
        assert desc and desc.strip().strip('"'), \
            "flow_log_kms_key_id must carry a non-empty description"

        sens = _top_level_arg(body, "sensitive")
        assert sens is not None, "flow_log_kms_key_id must declare a sensitive argument"
        assert re.match(r'true\b', sens.strip()), \
            f"flow_log_kms_key_id must be sensitive = true, got {sens!r}"

    def test_root_module_invoked_once_with_flow_logs(self):
        """The root module (source = "../../") is invoked exactly once and enables flow logs.

        It must wire the chosen destination type, retention, and (when provided)
        the KMS key id derived from the sensitive variable — not a literal.
        """
        modules = self._blocks_of_type("module")
        roots = []
        for labels, body, fn in modules:
            src = _top_level_arg(body, "source")
            if src and re.fullmatch(r'"\.\./\.\./?"', src.strip()):
                roots.append(body)
        assert len(roots) == 1, \
            f'module with source = "../../" must appear exactly once, found {len(roots)}'
        body = roots[0]

        enable = _top_level_arg(body, "enable_flow_log")
        assert enable is not None, \
            "root module must set enable_flow_log to turn on VPC flow logs"
        assert re.search(r'\btrue\b|var\.|local\.', enable), \
            f"enable_flow_log must enable flow logs, got {enable!r}"

        dest = _top_level_arg(body, "flow_log_destination_type")
        assert dest is not None, "root module must pass flow_log_destination_type"
        assert ("var.flow_log_destination_type" in dest
                or "local." in dest), \
            f"destination type must come from the validated input, got {dest!r}"

        # retention wired from the validated number input
        retention = None
        for arg in ("flow_log_cloudwatch_log_group_retention_in_days",
                    "log_retention_days"):
            retention = _top_level_arg(body, arg)
            if retention:
                break
        assert retention is not None, \
            "root module must wire log retention into the flow-log configuration"
        assert "var.log_retention_days" in retention or "local." in retention, \
            f"retention must come from the validated input, got {retention!r}"

        # KMS key id wired from the sensitive variable (not a literal ARN/value)
        kms = None
        for arg in ("flow_log_cloudwatch_log_group_kms_key_id",
                    "flow_log_kms_key_id"):
            kms = _top_level_arg(body, arg)
            if kms:
                break
        assert kms is not None, \
            "root module must wire flow_log_kms_key_id into the flow-log configuration"
        assert "var.flow_log_kms_key_id" in kms or "local." in kms, \
            f"KMS key id must come from the sensitive input, got {kms!r}"

    def test_locals_compute_terraform_managed_tags(self):
        """locals.tf must compute a shared tag set with a Terraform-managed marker."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = _strip_comments("\n".join(locals_blocks))

        # An explicit Terraform-managed marker tag (key=value), not just a comment.
        found = re.search(
            r'(["\']?(ManagedBy|managed_by|managed-by)["\']?)\s*=\s*["\']?[Tt]erraform["\']?',
            body,
        )
        alt = re.search(
            r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', body
        )
        assert found or alt, \
            "locals.tf must assign a Terraform-managed marker tag (e.g. ManagedBy = \"Terraform\")"

    def test_outputs_each_have_description(self):
        """Every output block must include a non-empty description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_vpc_id_and_flow_log_id(self):
        """Outputs must expose the VPC id and a flow log id from the root module."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            val = _top_level_arg(body, "value") or ""
            values.append((labels[0] if labels else "", val))

        vpc_id = [
            (n, v) for n, v in values
            if re.search(r'module\.[A-Za-z0-9_]+\.vpc_id\b', v)
        ]
        assert vpc_id, \
            "need an output whose value is module.<vpc>.vpc_id"

        flow_id = [
            (n, v) for n, v in values
            if re.search(r'module\.[A-Za-z0-9_]+\.(vpc_flow_log_id|flow_log_id)\b', v)
        ]
        assert flow_id, \
            "need an output whose value is module.<vpc>.vpc_flow_log_id (the flow log id)"

    def test_kms_output_is_marked_sensitive(self):
        """Any output surfacing the KMS key id must itself be sensitive = true.

        A stub that surfaces var.flow_log_kms_key_id without sensitive=true leaks
        the secret in plan/state and must fail here.
        """
        outputs = self._blocks_of_type("output")
        leaking = []
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            val = _top_level_arg(body, "value") or ""
            references_kms = (
                "flow_log_kms_key_id" in val
                or re.search(r'kms_key', val) is not None
            )
            if not references_kms:
                continue
            sens = _top_level_arg(body, "sensitive")
            if not (sens and re.match(r'true\b', sens.strip())):
                leaking.append((fn, name, val))
        assert not leaking, (
            "outputs referencing the KMS key id must be marked sensitive = true; "
            f"offenders: {leaking}"
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
