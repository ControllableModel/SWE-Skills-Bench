# Task: Author a Conditional-Endpoints VPC Example

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships consumer
configurations under `examples/` that invoke the root VPC module at `../../`, and
it also ships a `modules/vpc-endpoints` submodule. This task adds a new example
that creates a VPC and **optionally** attaches a set of gateway/interface VPC
endpoints whose creation is toggled by a feature flag, demonstrating both
conditional creation and keyed iteration.

## Files to Create/Modify

Create a new example directory `examples/optional-endpoints/`; one file per concern.

- `examples/optional-endpoints/versions.tf` (new) — version requirements.
- `examples/optional-endpoints/variables.tf` (new) — input variables.
- `examples/optional-endpoints/locals.tf` (new) — derived values.
- `examples/optional-endpoints/main.tf` (new) — provider, data source, VPC module, endpoints submodule call.
- `examples/optional-endpoints/outputs.tf` (new) — outputs.
- `tests/ext3/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Configurable input

- A boolean variable `enable_endpoints` that gates whether the endpoints submodule
  is instantiated at all.
- A variable `endpoints` typed as a **map of objects** (each object carrying at least
  a service name string and a boolean for whether the endpoint is private-dns enabled),
  with a description and a sensible default of at least two entries (for example `s3`
  and `dynamodb`).

### Conditional creation

The VPC endpoints submodule (`source = "../../modules/vpc-endpoints"`) must only be
instantiated when `enable_endpoints` is true — i.e. its creation must be gated by a
conditional that yields zero instances when the flag is false. The individual
endpoints themselves must be produced by iterating over the **contents** of
`var.endpoints` (keyed iteration), not by a fixed integer count: adding/removing an
endpoint entry must add/remove exactly that endpoint.

### Derived values

The map passed to the endpoints submodule and the shared tag set must be computed in
`locals.tf`. Shared tags must include a Terraform-managed marker tag.

### Outputs

Expose at least: the VPC id; and a value exposing the configured endpoint service
names (which must be empty/absent-safe when endpoints are disabled). Every output
must carry a description.

### Constraints

- Every variable has a `type` and a `description`.
- Version requirements pinned with explicit operators in `versions.tf` only;
  provider `source = "hashicorp/aws"`.
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- `enable_endpoints = false` -> the endpoints submodule produces zero instances; the VPC is still created.
- `enable_endpoints = true` with the default `endpoints` -> one endpoint per map entry is planned.
- Adding an entry to `endpoints` -> exactly one additional endpoint is planned; existing ones are untouched.

## Acceptance Criteria

A deterministic test at `tests/ext3/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `examples/optional-endpoints/` exists with exactly `versions.tf`, `variables.tf`,
  `locals.tf`, `main.tf`, `outputs.tf`.
- `versions.tf` pins `required_version` with an explicit operator and the `aws`
  provider with `source = "hashicorp/aws"` and a pinned `version`; no other file does.
- Every `variable` block has `type` and `description`.
- The `endpoints` variable type references both `map(` and `object(` (not `any`).
- The module block whose source ends in `modules/vpc-endpoints` is gated by a
  conditional driven by `var.enable_endpoints` (a `count = var.enable_endpoints ? 1 : 0`
  meta-argument, or an equivalent `for_each` whose collection is emptied when the flag
  is false — the block must reference `var.enable_endpoints`).
- The set of endpoints is produced from `var.endpoints` via `for_each` (the relevant
  block references `for_each` and `var.endpoints`); no `count = <integer>` enumerates the endpoints.
- Every `output` block has a `description`; an output exposing the VPC id and an output
  exposing endpoint service names both exist.
- `locals.tf` shared tags include a Terraform-managed marker tag.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext3/test_terraform_module_patterns.py -v
```
