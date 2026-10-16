# Task: Author a Tag-Governance VPC Example with Provider Default Tags

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships consumer examples
under `examples/` that invoke the root VPC module at `../../`. This task adds a new
example focused on **organization-wide tag governance**: a single VPC where mandatory
tags are enforced through a combination of provider-level default tags and validated
inputs, so every resource inherits a consistent, audited tag set.

## Files to Create/Modify

Create a new example directory `examples/tag-governance/`; one file per concern.

- `examples/tag-governance/versions.tf` (new) — version requirements.
- `examples/tag-governance/providers.tf` (new) — provider configuration with default tags.
- `examples/tag-governance/variables.tf` (new) — input variables.
- `examples/tag-governance/locals.tf` (new) — derived/merged tag set.
- `examples/tag-governance/main.tf` (new) — data source and VPC module invocation.
- `examples/tag-governance/outputs.tf` (new) — outputs.
- `tests/ext4/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Provider default tags

The provider configuration must live in its own `providers.tf` and must declare a
`default_tags` block so that a baseline set of tags (at minimum a Terraform-managed
marker) is applied to all resources automatically.

### Configurable input

- A variable `cost_center` (string) that is rejected unless it matches a required
  format (for example a fixed-length numeric code) — enforced with a `validation`
  block and a clear custom error message.
- A variable `owner_email` (string) for the resource owner, with a description.
- A variable `extra_tags` typed as a `map(string)` for ad-hoc tags, defaulting to an
  empty map.

### Derived values

`locals.tf` must compute the merged module-level tag set by combining the mandatory
tags (cost center, owner) with `var.extra_tags`. This merge must use a merge of maps
rather than a single hardcoded literal block, so that `extra_tags` entries appear in
the final set.

### Outputs

Expose at least the VPC id and the **effective merged tag map** that was passed to the
module. Every output must carry a description.

### Constraints

- Every variable has a `type` and a `description`.
- Version requirements pinned with explicit operators in `versions.tf` only; provider
  `source = "hashicorp/aws"`.
- The provider block lives only in `providers.tf` (not in `main.tf`).
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- A malformed `cost_center` -> validation fails with the custom message.
- Entries in `extra_tags` appear in the effective merged tag map output.
- The provider's `default_tags` carries a Terraform-managed marker.

## Acceptance Criteria

A deterministic test at `tests/ext4/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `examples/tag-governance/` exists and contains exactly `versions.tf`, `providers.tf`,
  `variables.tf`, `locals.tf`, `main.tf`, `outputs.tf`.
- A `provider "aws"` block appears in `providers.tf` and contains a `default_tags`
  block; no `provider "aws"` block appears in `main.tf`.
- `versions.tf` pins `required_version` with an explicit operator and the `aws`
  provider with `source = "hashicorp/aws"` and a pinned `version`; no other file does.
- Every `variable` block has `type` and `description`.
- The `cost_center` variable contains a `validation` block with a non-empty
  `error_message` string literal.
- The `extra_tags` variable type is `map(string)`.
- `locals.tf` builds the module tag map using the `merge(` function and references
  `var.extra_tags`.
- Every `output` block has a `description`; an output exposing the VPC id and an output
  exposing the merged effective tag map both exist.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext4/test_terraform_module_patterns.py -v
```
