"""
Test for 'terraform-module-patterns' skill — Multi-Region VPC Example with Aliased Providers.

Verifies that the agent authored a runnable example under ``examples/multi-region/``
that provisions one VPC in a *primary* region and one in a *secondary* region in a
single apply, using aliased AWS providers. The root VPC module (``source = "../../"``)
is invoked twice: once bound to the default provider (primary region) and once bound to
an aliased provider (secondary region) via an explicit ``providers = { aws = aws.<alias> }``
mapping on the second invocation.

This test inspects the generated ``.tf`` files as text using only the Python standard
library (it does NOT invoke any ``terraform`` binary). Validation goes far beyond
substring matching: HCL top-level blocks are parsed with a brace-aware tokenizer so that
``variable`` / ``output`` / ``module`` / ``provider`` / ``terraform`` / ``locals`` blocks
can be examined individually for their required arguments, aliases, provider mappings,
validation rules, naming conventions, and formatting.

Discriminative intent — a naive/stub implementation MUST fail:
  * Hardcoding a literal region (instead of ``var.primary_region`` / ``var.secondary_region``)
    in either provider block fails ``test_providers_region_from_variable``.
  * Declaring no ``alias`` on the second provider, or invoking the module without an
    explicit ``providers = { aws = aws.<alias> }`` mapping, fails
    ``test_two_aliased_provider_blocks`` / ``test_secondary_module_bound_to_aliased_provider``.
  * Invoking the root module only once (or sharing one provider) fails
    ``test_root_module_invoked_exactly_twice``.
  * Omitting the region allow-list validation / custom ``error_message`` fails
    ``test_region_variables_have_allowlist_validation``.
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
# Lightweight HCL helpers (stdlib only) — shared with the ext1 harness style.
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
    """Return raw RHS text of a top-level argument `name = ...` within body.

    Returns the value up to end-of-line for scalars, or the full balanced
    object/list value for nested values. None if absent.
    """
    pattern = re.compile(r'(?m)^[ \t]*' + re.escape(name) + r'[ \t]*=[ \t]*')
    n = len(body)
    for m in pattern.finditer(body):
        start = m.start()
        # compute brace/bracket depth at the match start; only accept depth 0
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
    """Validate the examples/multi-region/ aliased-provider Terraform example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "multi-region")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), f"missing required file: examples/multi-region/{fname}"
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

    def _root_modules(self):
        """Return list of (labels, body, fn) for module blocks sourcing ../../."""
        out = []
        for labels, body, fn in self._blocks_of_type("module"):
            src = _top_level_arg(body, "source")
            if src and re.search(r'"\.\./\.\./?"', src):
                out.append((labels, body, fn))
        return out

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/multi-region/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/multi-region/ directory not found"

    def test_exact_required_files_present(self):
        """Directory must contain exactly the six required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and has >=1 well-formed top-level block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    def test_root_module_block_present_in_main(self):
        """main.tf must contain module block(s) sourcing the root module ../../."""
        roots = self._root_modules()
        assert roots, 'no module block with source = "../../" found'
        for _, _, fn in roots:
            assert fn == "main.tf", \
                f'root-module invocation must live in main.tf, found in {fn}'

    # ====================================================================
    # L2 — deep semantic validation of the multi-region requirements
    # ====================================================================

    def test_versions_pins_terraform_and_aws_provider(self):
        """versions.tf pins required_version + hashicorp/aws provider with version.

        Must also declare configuration_aliases for the aws provider so the
        aliased secondary provider is valid for the root module example.
        """
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
        m = re.search(r'aws\s*=\s*\{(.*?)\}', rp, re.S)
        assert m, "aws provider must be declared as a map with source/version"
        aws_map = m.group(1)
        vm = re.search(r'version\s*=\s*"([^"]+)"', aws_map)
        assert vm, "aws provider must declare a pinned version constraint"
        assert re.search(r'(>=|~>|<=|<|>|=)\s*\d', vm.group(1)), \
            f"aws provider version is not a pinned constraint: {vm.group(1)!r}"
        # configuration_aliases is what makes an aliased provider valid here.
        assert "configuration_aliases" in aws_map, \
            "versions.tf aws provider must declare configuration_aliases for the aliased provider"

    def test_no_other_file_declares_versions(self):
        """Only versions.tf may carry the terraform version/required_providers block."""
        for fn, text in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                if t == "terraform":
                    assert "required_version" not in body and "required_providers" not in body, \
                        f"version requirements must live only in versions.tf, found in {fn}"

    def test_two_aliased_provider_blocks(self):
        """providers.tf must contain two provider \"aws\" blocks; exactly one aliased."""
        text = self._read("providers.tf")
        provs = [(l, b) for t, l, b in _iter_top_level_blocks(text)
                 if t == "provider" and l and l[0] == "aws"]
        assert len(provs) == 2, \
            f'providers.tf must declare exactly two provider "aws" blocks, found {len(provs)}'
        aliased = [b for l, b in provs if _top_level_arg(b, "alias") is not None]
        assert len(aliased) == 1, \
            f"exactly one provider block must declare an alias, found {len(aliased)}"
        # the aliased provider's alias must be a non-empty string literal
        alias_val = _top_level_arg(aliased[0], "alias")
        assert alias_val and alias_val.strip().strip('"'), \
            "aliased provider must set a non-empty alias name"

    def test_providers_region_from_variable(self):
        """Each provider's region must reference a var.* value, never a literal.

        A naive impl that hardcodes e.g. region = "us-east-1" must fail here.
        """
        text = self._read("providers.tf")
        provs = [(l, b) for t, l, b in _iter_top_level_blocks(text)
                 if t == "provider" and l and l[0] == "aws"]
        assert len(provs) == 2, "expected two aws provider blocks"
        seen_refs = set()
        for labels, body in provs:
            region = _top_level_arg(body, "region")
            assert region, "every aws provider block must set a region"
            assert region.strip().startswith("var.") or "var." in region, \
                f"provider region must come from a var.* input, got literal: {region!r}"
            # ensure it is NOT a bare quoted literal like "us-east-1"
            assert not re.fullmatch(r'"[a-z]{2}-[a-z]+-\d"', region.strip()), \
                f"provider region must not be a hardcoded region literal: {region!r}"
            seen_refs.add(re.search(r'var\.[a-z0-9_]+', region).group(0))
        # the two providers must reference two *distinct* region variables
        assert "var.primary_region" in seen_refs and "var.secondary_region" in seen_refs, \
            f"providers must use var.primary_region and var.secondary_region, saw {seen_refs}"

    def test_required_region_and_cidr_variables_declared(self):
        """The four expected input variables must be declared with proper types."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        for vname in ("primary_region", "secondary_region", "primary_cidr", "secondary_cidr"):
            assert vname in variables, f"variable '{vname}' not declared"
            t = _top_level_arg(variables[vname], "type")
            assert t and "string" in t, f"variable {vname} must be typed string, got {t!r}"

    def test_every_variable_has_type_and_description(self):
        """Each variable block must declare both a type and a non-empty description."""
        variables = self._blocks_of_type("variable")
        assert variables, "no variable blocks found"
        for labels, body, fn in variables:
            name = labels[0] if labels else "<unnamed>"
            assert _top_level_arg(body, "type"), \
                f"variable {name} ({fn}) missing a type argument"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"variable {name} ({fn}) missing a non-empty description"

    def test_region_variables_have_allowlist_validation(self):
        """Both region variables must validate membership in a region allow-list.

        Each validation block must carry a condition that checks an allow-list
        (contains()/in [...]/for-expr) plus a non-empty custom error_message.
        A stub that omits validation must fail.
        """
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        for vname in ("primary_region", "secondary_region"):
            assert vname in variables, f"variable '{vname}' not declared"
            body = variables[vname]
            vmatch = re.search(r'(?m)^[ \t]*validation[ \t]*\{', body)
            assert vmatch, f"{vname} must contain a validation block"
            vopen = body.index("{", vmatch.start())
            vbody = body[vopen + 1:_find_matching_brace(body, vopen)]
            cond = _top_level_arg(vbody, "condition")
            assert cond, f"{vname} validation must declare a condition"
            assert re.search(r'(contains\s*\(|\bin\s*\[|anytrue|for\s)', cond), \
                f"{vname} validation must check an allow-list, got: {cond!r}"
            em = re.search(r'error_message\s*=\s*"([^"]+)"', vbody)
            assert em and em.group(1).strip(), \
                f"{vname} validation must set a non-empty error_message string literal"

    def test_root_module_invoked_exactly_twice(self):
        """The root module (source = ../../) must be invoked exactly twice.

        One invocation per region. A single-invocation stub must fail.
        """
        roots = self._root_modules()
        assert len(roots) == 2, \
            f'module with source = "../../" must appear exactly twice, found {len(roots)}'
        # the two module instance labels must be distinct and encode region.
        names = [l[0] for l, b, f in roots if l]
        assert len(set(names)) == 2, f"the two module invocations must have distinct names, got {names}"
        joined = " ".join(names).lower()
        assert ("primary" in joined or "secondary" in joined) or \
               re.search(r'(primary|secondary|region)', joined), \
            f"module instance names should encode their region, got {names}"

    def test_secondary_module_bound_to_aliased_provider(self):
        """Exactly one root-module invocation must map aws -> an aliased provider.

        A stub that omits the providers={ aws = aws.<alias> } mapping must fail.
        """
        roots = self._root_modules()
        assert len(roots) == 2, "need exactly two root-module invocations"
        mapped = []
        for labels, body, fn in roots:
            providers = _top_level_arg(body, "providers")
            if providers and re.search(r'aws\s*=\s*aws\.[a-z0-9_]+', providers):
                mapped.append((labels[0] if labels else "<unnamed>", providers))
        assert len(mapped) == 1, (
            "exactly one root-module invocation must carry a providers = { aws = aws.<alias> } "
            f"mapping referencing an aliased provider, found {len(mapped)}"
        )
        # the alias used in the mapping must match the alias declared in providers.tf
        ptext = self._read("providers.tf")
        declared_aliases = set()
        for t, l, b in _iter_top_level_blocks(ptext):
            if t == "provider" and l and l[0] == "aws":
                av = _top_level_arg(b, "alias")
                if av:
                    declared_aliases.add(av.strip().strip('"'))
        used = re.search(r'aws\s*=\s*aws\.([a-z0-9_]+)', mapped[0][1]).group(1)
        assert used in declared_aliases, \
            f"providers mapping references aws.{used} but no such alias declared {declared_aliases}"

    def test_default_module_not_provider_mapped(self):
        """The primary (default-provider) invocation must NOT carry a providers map.

        Exactly one of the two invocations is aliased; the other uses the default.
        """
        roots = self._root_modules()
        unmapped = []
        for labels, body, fn in roots:
            providers = _top_level_arg(body, "providers")
            if not (providers and re.search(r'aws\s*=\s*aws\.[a-z0-9_]+', providers)):
                unmapped.append(labels[0] if labels else "<unnamed>")
        assert len(unmapped) == 1, \
            f"exactly one invocation must use the default provider (no aliased map), found {len(unmapped)}"

    def test_module_cidrs_wired_from_variables(self):
        """Each root-module invocation must wire its CIDR from the matching var.

        Ensures the two VPCs use primary_cidr / secondary_cidr respectively,
        not a single shared/hardcoded CIDR.
        """
        roots = self._root_modules()
        cidr_refs = set()
        for labels, body, fn in roots:
            cidr = _top_level_arg(body, "cidr")
            assert cidr, f"module {labels} must set a cidr argument"
            m = re.search(r'var\.[a-z0-9_]+', cidr)
            assert m, f"module cidr must reference a var.* input, got {cidr!r}"
            cidr_refs.add(m.group(0))
        assert {"var.primary_cidr", "var.secondary_cidr"} <= cidr_refs, \
            f"the two VPCs must use var.primary_cidr and var.secondary_cidr, saw {cidr_refs}"

    def test_locals_shared_tags_with_terraform_marker(self):
        """locals.tf must compute shared tags including a Terraform-managed marker."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = _strip_comments("\n".join(locals_blocks))
        found = re.search(
            r'(["\']?(ManagedBy|managed_by|managed-by)["\']?)\s*=\s*["\']?[Tt]erraform["\']?',
            body,
        )
        alt = re.search(r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', body)
        assert found or alt, \
            'locals.tf shared tags must assign a Terraform-managed marker (e.g. ManagedBy = "Terraform")'

    def test_outputs_each_have_description(self):
        """Every output block must include a non-empty description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_both_vpc_ids_and_cidrs(self):
        """Outputs must expose primary+secondary VPC ids and CIDR blocks.

        Values must reference the actual module instances' attributes, not literals.
        """
        outputs = self._blocks_of_type("output")
        # gather all output value RHS text
        vals = []
        for labels, body, fn in outputs:
            v = _top_level_arg(body, "value")
            vals.append(v or "")
        joined = "\n".join(vals)

        # VPC ids: must reference module.<name>.vpc_id for both instances
        id_refs = set(re.findall(r'module\.([a-z0-9_]+)\.vpc_id\b', joined))
        assert len(id_refs) >= 2, (
            "outputs must expose both primary and secondary VPC ids "
            f"(module.<name>.vpc_id for two distinct instances), saw {id_refs}"
        )

        # CIDR blocks: must reference vpc_cidr_block / cidr_block for both instances
        cidr_refs = set(re.findall(
            r'module\.([a-z0-9_]+)\.(?:vpc_cidr_block|cidr_block|vpc_cidr)\b', joined))
        assert len(cidr_refs) >= 2, (
            "outputs must expose both primary and secondary VPC CIDR blocks, "
            f"saw {cidr_refs}"
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
