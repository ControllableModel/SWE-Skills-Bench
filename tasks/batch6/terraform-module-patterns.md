# Task: Author a VPC Example with Dynamic Network ACL Rules

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships consumer examples
under `examples/` (including `examples/network-acls`) that invoke the root VPC
module at `../../`. This task adds a new example that builds a VPC and configures
its inbound network ACL rules from a **structured, validated list of rule objects**,
so the rule set can be edited as data without touching resource logic.

## Files to Create/Modify

Create a new example directory `examples/dynamic-acl/`; one file per concern.

- `examples/dynamic-acl/versions.tf` (new) — version requirements.
- `examples/dynamic-acl/variables.tf` (new) — input variables.
- `examples/dynamic-acl/locals.tf` (new) — transformation of rule inputs into the module's expected shape.
- `examples/dynamic-acl/main.tf` (new) — provider, data source, VPC module invocation.
- `examples/dynamic-acl/outputs.tf` (new) — outputs.
- `tests/ext6/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Configurable input

- A variable `inbound_rules` typed as a **list of objects**, each object carrying at
  least: a rule number (number), an action (string), a protocol (string), a from-port
  (number), a to-port (number), and a CIDR block (string). The variable must carry a
  description and a sensible default of at least two rules.
- The `inbound_rules` variable must include a `validation` block ensuring every rule's
  `action` is one of an allowed set (for example `allow` / `deny`), with a clear custom
  error message.

### Derived values

`locals.tf` must transform `var.inbound_rules` into the shape the module expects
(a comprehension over the list, not a hand-written literal of pre-expanded rules), and
must compute the shared tag set including a Terraform-managed marker tag.

### Module invocation

`main.tf` invokes the root module once (`source = "../../"`) and enables a dedicated
public network ACL fed by the transformed rule list. The VPC name must be derived from
a variable or local, not a bare literal repeated across files.

### Outputs

Expose at least the VPC id, the public network ACL id, and the count of configured
inbound rules. Every output must carry a description.

### Constraints

- Every variable has a `type` and a `description`.
- Version requirements pinned with explicit operators in `versions.tf` only; provider
  `source = "hashicorp/aws"`.
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- The default `inbound_rules` -> a public NACL with one rule per list entry is planned.
- A rule whose `action` is outside the allowed set -> validation fails with the custom message.
- Adding a rule object to `inbound_rules` -> the planned rule set grows by exactly one.

## Acceptance Criteria

A deterministic test at `tests/ext6/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `examples/dynamic-acl/` exists and contains exactly `versions.tf`, `variables.tf`,
  `locals.tf`, `main.tf`, `outputs.tf`.
- `versions.tf` pins `required_version` with an explicit operator and the `aws`
  provider with `source = "hashicorp/aws"` and a pinned `version`; no other file does.
- Every `variable` block has `type` and `description`.
- The `inbound_rules` variable type references both `list(` and `object(`, and the
  variable contains a `validation` block with a non-empty `error_message` string literal.
- `locals.tf` transforms `var.inbound_rules` using a `for` comprehension (a `[for ` or
  `{for ` expression referencing `var.inbound_rules`); the rule list is not a fully
  hand-expanded literal.
- The module block referencing `source = "../../"` appears exactly once.
- Every `output` block has a `description`; outputs exposing the VPC id, a public NACL
  id, and the inbound-rule count all exist.
- `locals.tf` shared tags include a Terraform-managed marker tag.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext6/test_terraform_module_patterns.py -v
```
