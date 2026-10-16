# Task: Author a Per-Environment VPC Example with Validated Sizing

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships runnable consumer
configurations under `examples/` (e.g. `examples/simple`, `examples/complete`)
that invoke the root VPC module at `../../`. This task adds a new example that
provisions a **single VPC whose subnet sizing is driven entirely by validated
input variables**, so the same configuration can be applied to dev/staging/prod
by changing only the inputs.

## Files to Create/Modify

Create a new example directory `examples/env-sizing/` with one file per concern;
do not collapse them.

- `examples/env-sizing/versions.tf` (new) — Terraform and provider version requirements.
- `examples/env-sizing/variables.tf` (new) — all input variable declarations.
- `examples/env-sizing/locals.tf` (new) — derived values (computed subnet CIDRs, tags).
- `examples/env-sizing/main.tf` (new) — provider, data source, and the VPC module invocation.
- `examples/env-sizing/outputs.tf` (new) — output value declarations.
- `tests/ext2/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Configurable input

- A variable `environment` (string) that is rejected at plan time unless it is one
  of an explicit allow-list of environment names; an invalid value must surface a
  clear, custom error message.
- A variable `vpc_cidr` (string) carrying the base CIDR block for the VPC.
- A variable `subnet_newbits` (number) controlling how many additional bits are
  added when carving subnets out of `vpc_cidr`; it must be rejected unless it falls
  within a sensible inclusive numeric range, with a custom error message.
- A variable `az_count` (number) for how many availability zones to span.

### Derived values

The actual public and private subnet CIDR lists, the selected availability-zone
list, and the shared tag set must all be computed in `locals.tf` — not inline in
the module block and not in `variables.tf`. The subnet CIDRs must be derived from
`vpc_cidr` and `subnet_newbits` (not hardcoded literal blocks). The shared tag set
must include at minimum a tag identifying the resources as Terraform-managed and a
tag carrying the environment name.

### Module invocation

`main.tf` invokes the root module (`source = "../../"`) exactly once, passing the
locally-derived subnet lists, AZ list, and tags. The VPC `name` must incorporate
the `environment` value.

### Outputs

Expose at least the resulting VPC id, the VPC CIDR block, and the list of private
subnet ids. Every output must carry a description.

### Constraints

- Every declared variable must specify both a `type` and a `description`.
- `required_version` and the `aws` provider `version` must be pinned with explicit
  constraint operators; the provider `source` must be `hashicorp/aws`. No other file
  may declare these version requirements.
- All identifiers must be lowercase words separated by underscores (no camelCase, no
  hyphens, no plural resource labels).
- HCL must be canonically formatted with two-space indentation and no tab characters.
- No hardcoded AWS access keys or secret values.

### Expected Functionality

- Applying with a valid `environment` and in-range `subnet_newbits` -> one VPC is planned.
- Passing `environment = "qa-bogus"` (not in the allow-list) -> validation fails with the custom message.
- Passing an out-of-range `subnet_newbits` -> validation fails with the custom message.
- Subnet CIDRs change when `vpc_cidr` or `subnet_newbits` change (they are derived, not literal).

## Acceptance Criteria

A deterministic test at `tests/ext2/test_terraform_module_patterns.py` (Python
standard library only; it inspects the generated `.tf` files as text and does not
invoke any `terraform` binary) verifies and passes:

- `examples/env-sizing/` exists and contains exactly `versions.tf`, `variables.tf`,
  `locals.tf`, `main.tf`, `outputs.tf`.
- `versions.tf` declares `required_version` with an explicit constraint operator and
  the `aws` provider with `source = "hashicorp/aws"` plus a pinned `version`. No
  other example file declares version requirements.
- Every `variable` block has both `type` and `description`.
- Both `environment` and `subnet_newbits` variables contain a `validation` block with
  a non-empty `error_message` string literal.
- The subnet CIDR computation in `locals.tf` references the `cidrsubnet` function and
  references `var.subnet_newbits`; no literal `/24`-style subnet CIDR strings are
  assigned as the module's subnet lists.
- The module block referencing `source = "../../"` appears exactly once.
- Every `output` block has a `description`; outputs exposing the VPC id, the VPC CIDR
  block, and a list of private subnet ids all exist.
- The shared tags in `locals.tf` include a Terraform-managed marker tag.
- All top-level block labels match the regex `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tab characters).
- No file contains an `AKIA[0-9A-Z]{16}` pattern or an `aws_access_key`/`secret_key`
  assigned a non-empty string literal.

Run the test with:

```bash
pytest tests/ext2/test_terraform_module_patterns.py -v
```
