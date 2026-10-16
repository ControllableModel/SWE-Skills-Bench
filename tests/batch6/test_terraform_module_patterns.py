"""
Test for 'terraform-module-patterns' skill — Dynamic Network ACL VPC Example.

Verifies that the agent authored a runnable example under
``examples/dynamic-acl/`` that builds a VPC and configures its inbound network
ACL rules from a *structured, validated list of rule objects*. The example must
invoke the root VPC module (``source = "../../"``) exactly once, enable a
dedicated public network ACL, and feed it a rule list that is *derived* from
``var.inbound_rules`` via a ``for`` comprehension (not a hand-expanded literal).

Verification strategy
---------------------
This test inspects the generated ``.tf`` files as text using only the Python
standard library (it does NOT invoke any ``terraform`` binary, matching the
variant's native acceptance command ``pytest tests/ext6/...``). Validation goes
well beyond substring matching: HCL top-level blocks are parsed with a
brace-aware tokenizer so individual ``variable`` / ``locals`` / ``module`` /
``output`` / ``terraform`` blocks can be examined for their required arguments,
types, validation rules, comprehensions, naming, and formatting.

Discriminative intent: a stub that merely copies the existing
``examples/network-acls`` (a hand-written literal rule map, no typed/validated
``inbound_rules`` variable, no ``for`` comprehension, no rule-count output)
must FAIL the L2 cases below.
"""

import os
import re
import pytest


REQUIRED_FILES = ["versions.tf", "variables.tf", "locals.tf", "main.tf", "outputs.tf"]


# ----------------------------------------------------------------------------
# Lightweight HCL helpers (stdlib only) — shared with the ext1 harness style
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
    """Return the raw RHS text of a top-level argument `name = ...` within body."""
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
    """Validate the examples/dynamic-acl/ data-driven NACL Terraform example."""

    REPO_DIR = "/workspace/terraform-aws-vpc"

    # -- shared helpers ----------------------------------------------------

    @property
    def _example_dir(self):
        return os.path.join(self.REPO_DIR, "examples", "dynamic-acl")

    def _read(self, fname):
        p = os.path.join(self._example_dir, fname)
        assert os.path.isfile(p), f"missing required file: examples/dynamic-acl/{fname}"
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
        """Return body of the module block with source = "../../" (or None)."""
        for labels, body, fn in self._blocks_of_type("module"):
            src = _top_level_arg(body, "source")
            if src and '"../../"' in src:
                return body
        return None

    # ====================================================================
    # L1 — deliverable files exist and are minimally well-formed
    # ====================================================================

    def test_example_directory_exists(self):
        """examples/dynamic-acl/ must exist as a directory."""
        assert os.path.isdir(self._example_dir), \
            "examples/dynamic-acl/ directory not found"

    def test_exact_required_files_present(self):
        """The directory must contain exactly the five required .tf files."""
        tf_files = sorted(f for f in os.listdir(self._example_dir) if f.endswith(".tf"))
        assert tf_files == sorted(REQUIRED_FILES), (
            f"expected exactly {sorted(REQUIRED_FILES)} .tf files, found {tf_files}"
        )

    def test_files_nonempty_and_parseable(self):
        """Each required file is non-empty and parses at least one HCL block."""
        for fn in REQUIRED_FILES:
            text = self._read(fn)
            assert text.strip(), f"{fn} is empty"
            blocks = list(_iter_top_level_blocks(text))
            assert blocks, f"{fn} contains no parseable HCL block"

    def test_module_block_sources_root(self):
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

    def test_only_versions_file_declares_version_requirements(self):
        """No file other than versions.tf may carry the terraform version block."""
        for fn, text in self._all_tf().items():
            if fn == "versions.tf":
                continue
            for t, labels, body in _iter_top_level_blocks(text):
                assert t != "terraform", \
                    f"terraform version block must live only in versions.tf, found in {fn}"

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

    def test_inbound_rules_variable_is_list_of_object(self):
        """inbound_rules must be typed list(object(...)) with the rule attributes."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        assert "inbound_rules" in variables, "variable 'inbound_rules' not declared"
        body = variables["inbound_rules"]
        type_rhs = _top_level_arg(body, "type")
        assert type_rhs, "inbound_rules variable has no type"
        assert "list(" in type_rhs and "object(" in type_rhs, \
            f"inbound_rules type must be list(object(...)), got: {type_rhs!r}"
        # The object schema must carry the documented rule fields with sane types.
        assert re.search(r'(rule_number|rule_no)\s*=\s*number', type_rhs), \
            f"rule object must include a numeric rule number: {type_rhs!r}"
        assert re.search(r'(rule_action|action)\s*=\s*string', type_rhs), \
            f"rule object must include a string action: {type_rhs!r}"
        assert re.search(r'protocol\s*=\s*string', type_rhs), \
            f"rule object must include a string protocol: {type_rhs!r}"
        assert re.search(r'from_port\s*=\s*number', type_rhs), \
            f"rule object must include a numeric from_port: {type_rhs!r}"
        assert re.search(r'to_port\s*=\s*number', type_rhs), \
            f"rule object must include a numeric to_port: {type_rhs!r}"
        assert re.search(r'cidr_block\s*=\s*string', type_rhs), \
            f"rule object must include a string cidr_block: {type_rhs!r}"

    def test_inbound_rules_default_has_at_least_two_rules(self):
        """inbound_rules default must define a list of >= 2 rule objects."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables["inbound_rules"]
        default = _top_level_arg(body, "default")
        assert default, "inbound_rules variable must provide a default"
        assert default.lstrip().startswith("["), \
            f"inbound_rules default must be a list literal, got: {default[:40]!r}"
        # count object entries inside the default list (each begins with `{`)
        objects = re.findall(r'\{', default)
        assert len(objects) >= 2, \
            f"inbound_rules default must contain >= 2 rule objects, found {len(objects)}"
        # each default rule must carry an action key
        assert default.count("rule_action") + default.count("action =") >= 2 \
            or len(re.findall(r'(rule_action|action)\s*=', default)) >= 2, \
            "default rules must each declare an action"

    def test_inbound_rules_validation_restricts_action(self):
        """inbound_rules must have a validation block with a non-empty error_message."""
        variables = {l[0]: b for l, b, f in self._blocks_of_type("variable") if l}
        body = variables["inbound_rules"]
        vbody = _block_body(body, "validation")
        assert vbody is not None, "inbound_rules must contain a validation block"
        # non-empty error_message string literal
        em = re.search(r'error_message\s*=\s*"([^"]+)"', vbody)
        assert em and em.group(1).strip(), \
            "validation must set a non-empty error_message string literal"
        # condition must reference an allow-list of actions (allow/deny)
        cond = _top_level_arg(vbody, "condition")
        assert cond, "validation must declare a condition"
        assert re.search(r'(contains\s*\(|alltrue|anytrue|for\s)', cond), \
            f"validation condition should check actions against an allow-list: {cond!r}"
        assert ("allow" in vbody and "deny" in vbody) \
            or re.search(r'"(allow|deny)"', cond), \
            "validation must restrict action to the allowed set (e.g. allow/deny)"

    def test_locals_transform_inbound_rules_with_for_comprehension(self):
        """locals.tf must derive the module rule list from var.inbound_rules via for."""
        text = self._read("locals.tf")
        locals_blocks = [b for t, l, b in _iter_top_level_blocks(text) if t == "locals"]
        assert locals_blocks, "locals.tf must contain a locals{} block"
        body = "\n".join(locals_blocks)
        assert "var.inbound_rules" in body, \
            "locals.tf must reference var.inbound_rules"
        # a for comprehension producing the transformed rule list
        comp = re.search(
            r'[\[{]\s*for\s+\w+(?:\s*,\s*\w+)?\s+in\s+var\.inbound_rules',
            body,
        )
        assert comp, \
            "locals.tf must transform var.inbound_rules with a [for ...] / {for ...} comprehension"

    def test_locals_rule_list_is_not_hand_expanded_literal(self):
        """The transformed rule set must come from the comprehension, not a literal map.

        Guards against copying examples/network-acls (a fully pre-expanded
        nested literal). The comprehension must be the source of the rule list.
        """
        text = _strip_comments(self._read("locals.tf"))
        # The for-comprehension over var.inbound_rules must exist...
        assert re.search(r'for\s+\w+(?:\s*,\s*\w+)?\s+in\s+var\.inbound_rules', text), \
            "rule list must be generated from var.inbound_rules, not hand-written"
        # ...and there must NOT be a large hand-expanded literal list of >= 3
        # rule objects that bypasses var.inbound_rules. Count object literals
        # that carry rule_number but are NOT inside a for-expression context.
        literal_rule_blocks = re.findall(
            r'\{\s*rule_number\s*=\s*\d+', text)
        assert len(literal_rule_blocks) <= 1, (
            "rule objects appear to be hand-expanded literals "
            f"({len(literal_rule_blocks)} found); they must be derived from var.inbound_rules"
        )

    def test_locals_shared_tags_include_terraform_managed_marker(self):
        """locals.tf shared tags must include a Terraform-managed marker tag."""
        text = _strip_comments(self._read("locals.tf"))
        found = re.search(
            r'(["\']?(ManagedBy|managed_by|managed-by)["\']?)\s*=\s*["\']?[Tt]erraform["\']?',
            text,
        )
        alt = re.search(r'["\']?[Tt]erraform["\']?\s*=\s*["\']?(true|managed)["\']?', text)
        assert found or alt, \
            'locals.tf shared tags must mark resources Terraform-managed (e.g. ManagedBy = "Terraform")'

    def test_root_module_invoked_exactly_once_with_dedicated_public_acl(self):
        """source = "../../" appears once and enables a dedicated public NACL."""
        sources = [
            _top_level_arg(body, "source")
            for _, body, _ in self._blocks_of_type("module")
        ]
        root_count = sum(1 for s in sources if s and '"../../"' in s)
        assert root_count == 1, \
            f'module with source = "../../" must appear exactly once, found {root_count}'

        body = self._root_module_body()
        assert body is not None, 'no module with source = "../../"'
        ded = _top_level_arg(body, "public_dedicated_network_acl")
        assert ded and re.search(r'\btrue\b', ded), \
            "root module must set public_dedicated_network_acl = true"
        # the inbound ACL rules must be fed by the transformed local list
        inbound = _top_level_arg(body, "public_inbound_acl_rules")
        assert inbound, "root module must set public_inbound_acl_rules"
        assert "local." in inbound, \
            f"public_inbound_acl_rules must be fed by the transformed local rule list: {inbound!r}"

    def test_vpc_name_not_bare_repeated_literal(self):
        """VPC name must derive from a variable/local, not a bare repeated literal."""
        body = self._root_module_body()
        assert body is not None, 'no module with source = "../../"'
        name = _top_level_arg(body, "name")
        assert name, "root module must set a name"
        assert ("var." in name or "local." in name), \
            f"VPC name must derive from a variable or local, got bare literal: {name!r}"

    def test_outputs_each_have_description(self):
        """Every output block must include a non-empty description."""
        outputs = self._blocks_of_type("output")
        assert outputs, "no output blocks found"
        for labels, body, fn in outputs:
            name = labels[0] if labels else "<unnamed>"
            desc = _top_level_arg(body, "description")
            assert desc and desc.strip().strip('"'), \
                f"output {name} ({fn}) missing a non-empty description"

    def test_outputs_expose_vpc_id_nacl_id_and_rule_count(self):
        """Outputs must expose the VPC id, the public NACL id, and the rule count."""
        outputs = self._blocks_of_type("output")
        values = []
        for labels, body, fn in outputs:
            val = _top_level_arg(body, "value")
            values.append((labels[0] if labels else "", val or ""))

        # VPC id output
        vpc_id = [n for n, v in values if re.search(r'\bvpc_id\b', v)]
        assert vpc_id, "need an output exposing the module's vpc_id"

        # Public network ACL id output
        nacl_id = [
            n for n, v in values
            if re.search(r'(public_network_acl_id|network_acl.*id|nacl.*id)', v, re.I)
        ]
        assert nacl_id, "need an output exposing the public network ACL id"

        # Count of configured inbound rules — must be a computed length, not a
        # hardcoded integer literal.
        count_out = [
            (n, v) for n, v in values
            if re.search(r'(length\s*\(|count)', v, re.I)
            and re.search(r'(inbound|rule)', n + v, re.I)
        ]
        assert count_out, \
            "need an output exposing the count of configured inbound rules"
        for n, v in count_out:
            if re.search(r'length\s*\(', v):
                assert re.search(r'(var\.inbound_rules|local\.)', v), \
                    f"rule-count output must measure the real rule list, got: {v!r}"
                break
        else:
            # if no length() form, the value must still not be a bare integer literal
            for n, v in count_out:
                assert not re.fullmatch(r'\d+', v.strip()), \
                    f"rule-count output must be computed, not a literal: {n} = {v!r}"

    def test_identifier_naming_convention(self):
        """All top-level block labels must match lowercase-underscore."""
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
