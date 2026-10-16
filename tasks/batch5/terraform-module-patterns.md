# Task: Author a Multi-Region VPC Example with Aliased Providers

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships consumer examples
under `examples/` that invoke the root VPC module at `../../`. This task adds a new
example that provisions **one VPC in a primary region and one in a secondary
region** within the same apply, using aliased AWS providers so each VPC is created
in the correct region.

## Files to Create/Modify

Create a new example directory `examples/multi-region/`; one file per concern.

- `examples/multi-region/versions.tf` (new) — version requirements (must declare the provider `configuration_aliases`).
- `examples/multi-region/providers.tf` (new) — primary and aliased provider configurations.
- `examples/multi-region/variables.tf` (new) — input variables.
- `examples/multi-region/locals.tf` (new) — derived values.
- `examples/multi-region/main.tf` (new) — the two region-specific VPC module invocations.
- `examples/multi-region/outputs.tf` (new) — outputs.
- `tests/ext5/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Aliased providers

`providers.tf` must declare a default `provider "aws"` for the primary region and a
second `provider "aws"` with an `alias` for the secondary region. Each provider's
region must come from an input variable, not a hardcoded literal.

### Configurable input

- A variable `primary_region` (string) and a variable `secondary_region` (string),
  each rejected unless it is a member of an explicit allow-list of AWS regions, each
  with a clear custom error message.
- A variable `primary_cidr` (string) and a variable `secondary_cidr` (string) for the
  two VPCs' base CIDR blocks.

### Module invocations

`main.tf` invokes the root module (`source = "../../"`) twice — once bound to the
default provider (primary region) and once bound to the aliased provider (secondary
region) via an explicit `providers = { aws = aws.<alias> }` mapping on the second
invocation. The two module instances must have distinct names that encode their region.

### Derived values

Per-region availability-zone selection and the shared tag set must be computed in
`locals.tf`. Shared tags must include a Terraform-managed marker tag.

### Outputs

Expose at least: a map (or two outputs) giving the primary and secondary VPC ids, and
the primary and secondary VPC CIDR blocks. Every output must carry a description.

### Constraints

- Every variable has a `type` and a `description`.
- Version requirements pinned with explicit operators in `versions.tf` only; provider
  `source = "hashicorp/aws"`.
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- The default-provider VPC is created in `primary_region`; the aliased-provider VPC in `secondary_region`.
- Passing an out-of-allow-list region for either variable -> validation fails with the custom message.
- The secondary module invocation is explicitly bound to the aliased provider.

## Acceptance Criteria

A deterministic test at `tests/ext5/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `examples/multi-region/` exists and contains exactly `versions.tf`, `providers.tf`,
  `variables.tf`, `locals.tf`, `main.tf`, `outputs.tf`.
- `providers.tf` contains two `provider "aws"` blocks, exactly one of which declares an
  `alias`, and each provider's `region` references a `var.` value (no literal region string).
- `versions.tf` pins `required_version` with an explicit operator and the `aws`
  provider with `source = "hashicorp/aws"` and a pinned `version`; no other file does.
- Every `variable` block has `type` and `description`.
- Both `primary_region` and `secondary_region` contain a `validation` block with a
  non-empty `error_message` string literal.
- The module block referencing `source = "../../"` appears exactly twice, and exactly
  one of those module blocks contains a `providers =` mapping that references `aws.`.
- Every `output` block has a `description`; outputs exposing both VPC ids and both VPC
  CIDR blocks exist.
- `locals.tf` shared tags include a Terraform-managed marker tag.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext5/test_terraform_module_patterns.py -v
```
