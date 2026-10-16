# Task: Author a Secondary-CIDR VPC Example with Computed Subnet Plan

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships consumer examples
under `examples/` (including `examples/secondary-cidr-blocks`) that invoke the root
VPC module at `../../`. This task adds a new example that attaches one or more
**secondary CIDR blocks** to a VPC and lays out subnets across both the primary and
secondary ranges using a computed subnet plan rather than hand-written blocks.

## Files to Create/Modify

Create a new example directory `examples/secondary-cidr-plan/`; one file per concern.

- `examples/secondary-cidr-plan/versions.tf` (new) — version requirements.
- `examples/secondary-cidr-plan/variables.tf` (new) — input variables.
- `examples/secondary-cidr-plan/locals.tf` (new) — computed subnet plan.
- `examples/secondary-cidr-plan/main.tf` (new) — provider, data source, VPC module invocation.
- `examples/secondary-cidr-plan/outputs.tf` (new) — outputs.
- `tests/ext9/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Configurable input

- A variable `primary_cidr` (string) for the VPC's primary CIDR block.
- A variable `secondary_cidrs` typed as `list(string)` for additional CIDR blocks,
  defaulting to at least one block.
- A variable `az_count` (number) rejected unless it is within an inclusive sensible
  range (for example 1..4), with a clear custom error message.
- A variable `subnet_newbits` (number) controlling subnet sizing.

### Derived values

`locals.tf` must compute the private and public subnet CIDR lists by carving them from
the primary CIDR, and compute the secondary-range subnet CIDR list by carving from the
secondary CIDRs — all using subnet arithmetic functions and comprehensions, not literal
blocks. The selected AZ list and shared tag set (with a Terraform-managed marker tag)
must also live in `locals.tf`.

### Module invocation

`main.tf` invokes the root module once (`source = "../../"`), passing the primary CIDR,
the secondary CIDR list, the computed subnet lists, and the AZ list. The VPC name must be
derived from a variable or local.

### Outputs

Expose at least: the VPC id, the list of secondary CIDR association ids (or the
secondary CIDR list), and the computed private subnet CIDR list. Every output must carry
a description.

### Constraints

- Every variable has a `type` and a `description`.
- Version requirements pinned with explicit operators in `versions.tf` only; provider
  `source = "hashicorp/aws"`.
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- The default inputs -> a VPC with the secondary CIDR(s) associated and subnets carved across both ranges.
- An out-of-range `az_count` -> validation fails with the custom message.
- Subnet CIDRs change when `primary_cidr`, `secondary_cidrs`, or `subnet_newbits` change (they are computed).

## Acceptance Criteria

A deterministic test at `tests/ext9/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `examples/secondary-cidr-plan/` exists and contains exactly `versions.tf`,
  `variables.tf`, `locals.tf`, `main.tf`, `outputs.tf`.
- `versions.tf` pins `required_version` with an explicit operator and the `aws`
  provider with `source = "hashicorp/aws"` and a pinned `version`; no other file does.
- Every `variable` block has `type` and `description`.
- The `secondary_cidrs` variable type is `list(string)`.
- The `az_count` variable contains a `validation` block with a non-empty `error_message`
  string literal.
- `locals.tf` computes subnet CIDR lists using the `cidrsubnet` function inside a `for`
  comprehension and references `var.subnet_newbits`; no literal `/24`-style CIDR strings
  are assigned as the module's subnet lists.
- The module block referencing `source = "../../"` appears exactly once and passes a
  secondary-CIDR argument referencing `var.secondary_cidrs`.
- Every `output` block has a `description`; outputs exposing the VPC id, the secondary
  CIDRs (or their association ids), and the computed private subnet CIDR list all exist.
- `locals.tf` shared tags include a Terraform-managed marker tag.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext9/test_terraform_module_patterns.py -v
```
