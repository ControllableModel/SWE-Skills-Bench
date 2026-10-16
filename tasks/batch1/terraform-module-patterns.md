# Task: Author a Multi-Tier VPC Example Configuration

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships a set of runnable
example configurations under `examples/` (e.g. `examples/simple`, `examples/ipv6-only`)
that consume the root VPC module. This task adds a new example that provisions
*several independent VPCs in one apply* — one VPC per logical tier — using the
root module at `../../`.

## Files to Create/Modify

Create a new example directory `examples/multi-tier/` containing the following
configuration files. Each file has a single, specific responsibility — do not
collapse them into one file.

- `examples/multi-tier/versions.tf` (new) — Terraform and provider version requirements.
- `examples/multi-tier/variables.tf` (new) — all input variable declarations.
- `examples/multi-tier/locals.tf` (new) — derived/local values.
- `examples/multi-tier/main.tf` (new) — provider, data sources, and the VPC module invocation(s).
- `examples/multi-tier/outputs.tf` (new) — output value declarations.
- `tests/ext1/test_terraform_module_patterns.py` (new) — the deterministic test described below.

## Requirements

### Configurable input

The example must expose a single input variable named `tiers` that maps a tier
name to its configuration. Each entry carries at least a CIDR block (string) and
a desired number of availability zones (number). The variable must be typed as a
map of objects (not `any`, not a bare `map`), and it must carry a human-readable
description. Provide a sensible default containing at least three tiers (for
example `dev`, `staging`, and `prod`).

A second input variable named `region` must exist, typed as a string, with a
description, and constrained so that an invalid value is rejected at plan time
rather than silently accepted. Only AWS regions from an explicit allow-list may
be accepted; any other value must surface a clear, custom error message.

### One VPC per tier

The example must create one VPC per entry in `var.tiers` by invoking the root
module (`source = "../../"`) once per tier. The set of VPCs produced must scale
with the *contents* of `var.tiers`: adding, removing, or renaming a tier must add,
remove, or rename exactly that VPC, and must never destroy-and-recreate the other,
unrelated tiers' VPCs. Each VPC's name must incorporate its tier key so the VPCs
are individually addressable.

### Derived values

Per-tier availability-zone selection and any shared tag set must be computed in
`locals.tf` (not inline inside the module block and not in `variables.tf`). Common
tags applied to every tier must include at minimum a tag identifying that the
resources are managed by Terraform.

### Outputs

Expose, at minimum:

- An output exposing a map from tier name to that tier's resulting VPC id.
- An output exposing a map from tier name to that tier's VPC CIDR block.

Every output declared in the example must carry a description.

### Constraints

- Every declared input variable must specify both a `type` and a `description`.
- Version requirements (the `required_version` and the `aws` provider `version`)
  must be pinned with explicit constraints, consistent with the other examples in
  `examples/`. The provider `source` must be `hashicorp/aws`.
- All resource/module/variable/output/local identifiers must be lowercase words
  separated by underscores; no camelCase, no hyphens, no plural resource labels.
- The HCL must be canonically formatted: two-space indentation, no tabs.
- The example must not contain any hardcoded long-lived AWS credentials,
  access keys, or secret values.

### Expected Functionality

- Applying the example with the default `tiers` -> one VPC is planned per default tier.
- Removing one tier from `tiers` -> only that tier's VPC is removed from the plan; the others are untouched.
- Passing `region = "not-a-region"` -> validation fails with the custom error message.
- A consumer can read `outputs.tf` to obtain, per tier, the VPC id and CIDR block.

## Acceptance Criteria

A deterministic test at `tests/ext1/test_terraform_module_patterns.py` (Python
standard library only — it inspects the generated `.tf` files as text, it does
not invoke any `terraform` binary) verifies all of the following, and passes:

- The directory `examples/multi-tier/` exists and contains exactly the files
  `versions.tf`, `variables.tf`, `locals.tf`, `main.tf`, and `outputs.tf`.
- `versions.tf` declares `required_version` with an explicit constraint operator
  (`>=`, `~>`, `=`, or a range) and declares the `aws` provider with
  `source = "hashicorp/aws"` and a pinned `version` constraint. No other file
  declares the terraform/provider version requirements.
- Every `variable` block found across the example files contains both a `type`
  argument and a `description` argument.
- The `tiers` variable's `type` is a map-of-object type (it references both
  `map(` and `object(`), not `any`.
- The `region` variable contains a `validation` block whose `error_message` is a
  non-empty string literal.
- Multiple VPCs are produced from the data in `var.tiers` without enumerating a
  fixed integer count: the module invocation that references `source = "../../"`
  uses `for_each` and references `var.tiers`, and no `count = <integer>` /
  `count = var.<name>` appears on that block.
- Every `output` block found across the example files contains a `description`
  argument, and there exists an output whose `value` is a map keyed by tier
  producing VPC ids, and an output producing VPC CIDR blocks.
- Common tags computed in `locals.tf` include a tag indicating Terraform-managed
  resources.
- All top-level block labels (variable/output/local names, module name) match the
  lowercase-underscore convention (regex `^[a-z][a-z0-9_]*$`); none contain a
  hyphen, uppercase letter, or trailing plural-style label that duplicates the
  resource type.
- Indentation uses spaces only (no literal tab characters) in every `.tf` file.
- No file contains a hardcoded AWS access key pattern (`AKIA[0-9A-Z]{16}`) or an
  `aws_access_key`/`secret_key` assigned a non-empty string literal.

Run the test with:

```bash
pytest tests/ext1/test_terraform_module_patterns.py -v
```
