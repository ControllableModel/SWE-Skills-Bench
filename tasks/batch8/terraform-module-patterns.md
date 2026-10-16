# Task: Author a Keyed Multi-VPC-Peering Wrapper Example

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships a `wrappers/`
directory whose pattern instantiates the root module once per entry of an
`items` map via `for_each`, and consumer examples under `examples/` that invoke
the root module at `../../`. This task adds a new example that uses the same
**map-driven, keyed** pattern to stamp out a fleet of similarly-shaped VPCs from a
single data structure, where every VPC is individually addressable by its key.

## Files to Create/Modify

Create a new example directory `examples/vpc-fleet/`; one file per concern.

- `examples/vpc-fleet/versions.tf` (new) — version requirements.
- `examples/vpc-fleet/variables.tf` (new) — input variables.
- `examples/vpc-fleet/locals.tf` (new) — derived values.
- `examples/vpc-fleet/main.tf` (new) — the keyed module invocation.
- `examples/vpc-fleet/outputs.tf` (new) — outputs.
- `tests/ext8/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Configurable input

- A variable `vpcs` typed as a **map of objects**, each object carrying at least a CIDR
  block (string), a desired AZ count (number), and a boolean for whether a NAT gateway
  is enabled. The variable must carry a description and a default of at least three
  named entries.
- The `vpcs` variable must include a `validation` block ensuring every entry's CIDR
  block is non-empty and contains a `/` (a basic CIDR shape check), with a clear custom
  error message.

### Keyed instantiation

`main.tf` must instantiate the root module (`source = "../../"`) once per entry of
`var.vpcs` using keyed iteration, so that adding/removing/renaming a key
adds/removes/renames exactly that VPC and never disturbs the others. Each VPC's name
must incorporate its map key.

### Derived values

Per-entry AZ selection and the shared tag set must be computed in `locals.tf`. Shared
tags must include a Terraform-managed marker tag.

### Outputs

Expose at least: a map from key to VPC id, and a map from key to VPC CIDR block. Every
output must carry a description.

### Constraints

- Every variable has a `type` and a `description`.
- Version requirements pinned with explicit operators in `versions.tf` only; provider
  `source = "hashicorp/aws"`.
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- The default `vpcs` -> one VPC per map entry is planned.
- Renaming a key -> only that VPC is renamed; the others are untouched.
- An entry whose CIDR lacks a `/` -> validation fails with the custom message.

## Acceptance Criteria

A deterministic test at `tests/ext8/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `examples/vpc-fleet/` exists and contains exactly `versions.tf`, `variables.tf`,
  `locals.tf`, `main.tf`, `outputs.tf`.
- `versions.tf` pins `required_version` with an explicit operator and the `aws`
  provider with `source = "hashicorp/aws"` and a pinned `version`; no other file does.
- Every `variable` block has `type` and `description`.
- The `vpcs` variable type references both `map(` and `object(` (not `any`) and contains
  a `validation` block with a non-empty `error_message` string literal.
- The module block referencing `source = "../../"` uses `for_each` and references
  `var.vpcs`; no `count = <integer>` or `count = var.<name>` appears on that block.
- The module's `name` argument references the iteration key (`each.key`).
- Every `output` block has a `description`; an output mapping key->VPC id and an output
  mapping key->VPC CIDR block both exist (each `value` is a `{ for ... }` map expression).
- `locals.tf` shared tags include a Terraform-managed marker tag.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext8/test_terraform_module_patterns.py -v
```
