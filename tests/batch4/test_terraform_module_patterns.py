"""
Test for 'terraform-module-patterns' skill — Tag-Governance VPC Example (ext4).

Verifies that the agent authored a new consumer example under
``examples/tag-governance/`` that enforces organization-wide tag governance for
a single VPC. Mandatory tags are applied through a combination of:

  * a provider-level ``default_tags`` block declared **only** in ``providers.tf``
    (carrying a Terraform-managed marker),
  * validated input variables (``cost_center`` with a ``validation`` block,
    ``owner_email``, and a ``map(string)`` ``extra_tags``),
  * a ``locals.tf`` that ``merge(...)``-es mandatory tags with ``var.extra_tags``,
  * outputs exposing the VPC id and the effective merged tag map.

This test inspects the generated ``.tf`` files as text using ONLY the Python
standard library (it never invokes any ``terraform`` binary — that is the native
acceptance command for this variant: ``pytest tests/ext4/...``). Validation goes
well beyond substring matching: HCL top-level blocks are parsed with a
brace-aware tokenizer so that individual ``provider`` / ``variable`` / ``locals``
/ ``output`` blocks can be examined for their required arguments, types,
validation rules, the actual ``merge()`` data-flow, naming conventions, and
formatting. A naive stub (a single hardcoded tag literal that ignores
``extra_tags``, a provider block placed in ``main.tf``, a ``cost_center`` without
validation, etc.) is designed to FAIL.
"""

import os
import re
import pytest


REQUIRED_FILES = [
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "locals.tf",
    "main.tf",
    "outputs.tf",
]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — shared, proven harness from ext1.
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

    Returns the value up to end-of-line for scalars, or the full block for
    nested object/list values (brace/bracket aware). None if absent.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # compute brace/bracket depth at the match start; only accept depth 0.
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

    Handles HCL blocks that are NOT assignments (e.g. default_tags {}).
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
    """Validate the examples/tag-governance/ tag-governance Terraform example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "tag-governance")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), \
            f"missing required file: examples/tag-governance/{fname}"
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

    def _blocks_of_type(self, btype, only_file=None):
        """Collect every (labels, body, filename) for the given block type."""
        res = []
        for fn, text in self._all_tf().items():
            if only_file is not None and fn != only_file:
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                if t == btype:
                    res.append((labels, body, fn))
        return res

    def _variables(self):
        return {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/tag-governance/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/tag-governance/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain exactly the six required .tf files."""
        tf_files = sorted(
            f for f in os.listdir(self._example_dir) if f.endswith(".tf")
        )
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, "
            f"found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and contains a parseable HCL block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    def test_main_invokes_root_vpc_module(self):
        """main.tf must contain a module block sourcing the root module (../../)."""
        modules = self._blocks_of_type("module", only_file="main.tf")
        assert modules, "no module block found in main.tf"
        sources = [_top_level_arg(b, "source") for _, b, _ in modules]
        assert any(s and '"../../"' in s for s in sources), \
            'main.tf must invoke the root VPC module with source = "../../"'

    # ====================================================================
    # L2 — deep semantic validation of the requirements
    # ====================================================================

    def test_provider_block_lives_only_in_providers_tf(self):
        """A `provider "aws"` block must appear ONLY in providers.tf."""
        aws_provider_files = []
        for fn, text in self._all_tf().items():
            for t, labels, body in _iter_top_level_blocks(text):
                if t == "provider" and labels and labels[0] == "aws":
                    aws_provider_files.append(fn)
        assert "providers.tf" in aws_provider_files, \
            'a provider "aws" block must be declared in providers.tf'
        offenders = [f for f in aws_provider_files if f != "providers.tf"]
        assert not offenders, (
            'provider "aws" block must live ONLY in providers.tf; '
            f'also found in {offenders}'
        )
        # Hard requirement from the doc: NOT in main.tf.
        assert "main.tf" not in aws_provider_files, \
            'provider "aws" block must not appear in main.tf'

    def test_provider_declares_default_tags_with_terraform_marker(self):
        """providers.tf provider block must carry a default_tags block whose tag
        set includes a Terraform-managed marker (e.g. ManagedBy = "Terraform")."""
        providers = self._blocks_of_type("provider", only_file="providers.tf")
        aws = [b for l, b, f in providers if l and l[0] == "aws"]
        assert aws, 'no provider "aws" block in providers.tf'
        body = aws[0]
        dt = _block_body(body, "default_tags")
        assert dt is not None, \
            'provider "aws" must declare a default_tags { ... } block'
        # The tags themselves may be nested under `tags = { ... }`.
        tag_region = _top_level_arg(dt, "tags")
        scan = tag_region if tag_region else dt
        managed = re.search(
            r'["\']?(ManagedBy|managed_by|managed-by)["\']?\s*=\s*'
            r'["\']?[Tt]erraform["\']?',
            scan,
        )
        alt = re.search(
            r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?',
            scan,
        )
        assert managed or alt, (
            "default_tags must include a Terraform-managed marker, e.g. "
            'ManagedBy = "Terraform"'
        )

    def test_versions_pins_terraform_and_aws_provider(self):
        """versions.tf pins required_version + hashicorp/aws provider version."""
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

    def test_no_other_file_declares_versions(self):
        """Only versions.tf may carry the terraform/provider version block."""
        for fn, text in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                assert t != "terraform", (
                    "terraform version block must live only in versions.tf, "
                    f"found in {fn}"
                )

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

    def test_cost_center_has_validation_with_error_message(self):
        """cost_center (string) must enforce a format via a validation block
        with a non-empty custom error_message."""
        variables = self._variables()
        assert "cost_center" in variables, "variable 'cost_center' not declared"
        body = variables["cost_center"]

        type_rhs = _top_level_arg(body, "type")
        assert type_rhs and "string" in type_rhs, \
            f"cost_center must be typed string, got {type_rhs!r}"

        vmatch = re.search(r'validation\s*\{', body)
        assert vmatch, "cost_center variable must contain a validation block"
        vopen = body.index("{", vmatch.start())
        vclose = _find_matching_brace(body, vopen)
        assert vclose != -1, "cost_center validation block is unbalanced"
        vbody = body[vopen + 1:vclose]

        cond = re.search(r'condition\s*=\s*(.+)', vbody)
        assert cond, "cost_center validation must declare a condition"
        # The condition must actually constrain the value's format (regex /
        # length / character-class check), not be a tautology.
        assert re.search(
            r'(can\s*\(|regex\s*\(|regexall\s*\(|length\s*\(|'
            r'cidrhost|format)',
            cond.group(1),
        ), (
            "cost_center validation condition must check a required format "
            f"(regex / length), got: {cond.group(1)!r}"
        )

        em = re.search(r'error_message\s*=\s*"([^"]+)"', vbody)
        assert em and em.group(1).strip(), (
            "cost_center validation must set a non-empty error_message "
            "string literal"
        )

    def test_owner_email_and_extra_tags_typing(self):
        """owner_email is a described string; extra_tags is map(string)
        defaulting to an empty map."""
        variables = self._variables()
        assert "owner_email" in variables, "variable 'owner_email' not declared"
        oe = variables["owner_email"]
        assert _top_level_arg(oe, "type") and \
            "string" in _top_level_arg(oe, "type"), \
            "owner_email must be typed string"
        assert _top_level_arg(oe, "description"), \
            "owner_email must carry a description"

        assert "extra_tags" in variables, "variable 'extra_tags' not declared"
        et = variables["extra_tags"]
        et_type = _top_level_arg(et, "type")
        assert et_type and re.search(r'map\(\s*string\s*\)', et_type), \
            f"extra_tags type must be map(string), got {et_type!r}"
        default = _top_level_arg(et, "default")
        assert default is not None, "extra_tags must default to an empty map"
        assert re.match(r'\{\s*\}$', default.strip()), \
            f"extra_tags default must be an empty map {{}}, got {default!r}"

    def test_locals_merge_combines_extra_tags(self):
        """locals.tf must build the module tag map with merge(...) and feed
        var.extra_tags into it (not a single hardcoded literal block)."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text)
                         if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)

        # Find the assignment that uses merge(). Identify which local name it is.
        merge_assigns = re.findall(
            r'(?m)^\s*([a-z][a-z0-9_]*)\s*=\s*merge\s*\(', body
        )
        assert merge_assigns, \
            "locals.tf must compute the tag set using the merge() function"

        # Locate the full RHS of the first merge() local and ensure
        # var.extra_tags is one of the merged operands.
        merged_name = merge_assigns[0]
        rhs = _top_level_arg(body, merged_name)
        assert rhs and rhs.lstrip().startswith("merge"), \
            f"local {merged_name} should be a merge(...) expression: {rhs!r}"
        assert "var.extra_tags" in rhs, (
            "the merged tag map must include var.extra_tags so ad-hoc tags "
            f"flow into the effective set; got: {rhs!r}"
        )
        # Mandatory tags (cost center + owner) must be referenced as well.
        assert "var.cost_center" in rhs or re.search(
            r'(CostCenter|cost_center)', rhs), \
            "merged tag map must incorporate the cost center"
        assert "var.owner_email" in rhs or re.search(
            r'(Owner|owner)', rhs), \
            "merged tag map must incorporate the owner"

    def test_extra_tags_actually_flows_to_module_or_default(self):
        """The merged local (carrying var.extra_tags) must be consumed downstream
        — passed to the module's tags and/or surfaced as the effective output —
        so a stub that computes but never uses it fails."""
        text_locals = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text_locals)
                         if t == "locals"]
        body = "\n".join(locals_blocks)
        merge_assigns = re.findall(
            r'(?m)^\s*([a-z][a-z0-9_]*)\s*=\s*merge\s*\(', body
        )
        assert merge_assigns, "no merged tag local found in locals.tf"
        merged_local = merge_assigns[0]
        ref = f"local.{merged_local}"

        all_text = "\n".join(self._all_tf().values())
        # The merged local must be referenced somewhere other than its own
        # definition (module tags, default_tags, or an output).
        usages = len(re.findall(re.escape(ref), all_text))
        assert usages >= 1, (
            f"merged tag local {ref} is computed but never consumed downstream"
        )

    def test_outputs_each_have_description(self):
        """Every output block must include a non-empty description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_vpc_id_and_effective_tag_map(self):
        """Outputs must expose the VPC id AND the effective merged tag map."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            val = _top_level_arg(body, "value")
            values.append((labels[0] if labels else "", val or ""))

        # An output whose value reads the VPC id off the module.
        id_out = [
            (n, v) for n, v in values
            if re.search(r'module\.[\w.\[\]"]*vpc_id', v)
            or re.search(r'\bvpc_id\b', v)
        ]
        assert id_out, \
            "need an output exposing the VPC id (module.<x>.vpc_id)"

        # An output exposing the effective merged tag map. Accept either a
        # reference to the merged local or to var.extra_tags inside a tag-named
        # output, but require it to be tag-shaped (not just any value).
        text_locals = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text_locals)
                         if t == "locals"]
        merge_assigns = re.findall(
            r'(?m)^\s*([a-z][a-z0-9_]*)\s*=\s*merge\s*\(',
            "\n".join(locals_blocks),
        )
        merged_local = merge_assigns[0] if merge_assigns else None

        tag_out = []
        for n, v in values:
            name_is_tag = re.search(r'tag', n, re.I)
            val_is_merged = (
                (merged_local and f"local.{merged_local}" in v)
                or "var.extra_tags" in v
                or re.search(r'local\.[\w]*tag', v, re.I)
            )
            if name_is_tag and val_is_merged:
                tag_out.append((n, v))
        assert tag_out, (
            "need an output exposing the effective merged tag map "
            "(a tag-named output whose value is the merged tag local)"
        )

    def test_identifier_naming_convention(self):
        """All user-chosen block labels match lowercase-underscore."""
        ident_re = re.compile(r'^[a-z][a-z0-9_]*$')
        offenders = []
        for fn, text in self._all_tf().items():
            for t, labels, body in _iter_top_level_blocks(text):
                if t in ("variable", "output", "module", "data", "resource",
                         "provider", "local"):
                    check = labels[-1:] if t in ("data", "resource") else labels
                    for lab in check:
                        # provider "aws" / data source type names are fixed
                        # AWS identifiers; allow them through (already lowercase).
                        if not ident_re.match(lab):
                            offenders.append((fn, t, lab))
                if t == "locals":
                    for m in re.finditer(r'(?m)^\s{2}([A-Za-z_][\w-]*)\s*=', body):
                        if not ident_re.match(m.group(1)):
                            offenders.append((fn, "local", m.group(1)))
        assert not offenders, \
            f"identifiers violate lowercase_underscore: {offenders}"

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
                        f'{fn} assigns a literal credential: '
                        f'{m.group(1)} = "{val}"'
                    )
