# Task: Author a Reusable Tagging Helper Submodule

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository keeps reusable building
blocks under `modules/` (today: `modules/flow-log`, `modules/vpc-endpoints`), each
a self-contained module with its own `versions.tf`, `variables.tf`, `main.tf`, and
`outputs.tf`. This task adds a new **standalone helper submodule** under `modules/`
that takes structured inputs and emits a normalized, governance-compliant tag map
for downstream modules to consume — no AWS resources are created.

## Files to Create/Modify

Create a new submodule directory `modules/tagging/`; one file per concern.

- `modules/tagging/versions.tf` (new) — Terraform version requirement only (no provider needed; this module declares no providers).
- `modules/tagging/variables.tf` (new) — input variable declarations.
- `modules/tagging/locals.tf` (new) — the tag-merging/normalization logic.
- `modules/tagging/outputs.tf` (new) — output value declarations.
- `tests/ext10/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Configurable input

- A variable `environment` (string) rejected unless it is one of an explicit allow-list,
  with a clear custom error message.
- A variable `application` (string) for the owning application name, with a description.
- A variable `mandatory_tags` typed as a `map(string)` for tags that must always be
  present, defaulting to an empty map.
- A variable `extra_tags` typed as a `map(string)` for optional caller-supplied tags,
  defaulting to an empty map.

### Normalization logic

`locals.tf` must produce a single merged tag map that combines: a baseline
Terraform-managed marker tag, the environment, the application, the `mandatory_tags`,
and the `extra_tags`. The merge must use map-merging (so later sources can extend earlier
ones) rather than a single hand-written literal. The merged result must be exposed for
downstream consumption.

### Outputs

Expose at least: `tags` (the full merged tag map) and `tag_keys` (the sorted list of keys
present in the merged map). Every output must carry a description.

### Constraints

- This submodule declares **no** `provider` blocks and creates **no** resources — it is a
  pure data/transformation module.
- `versions.tf` declares `required_version` with an explicit constraint operator; because
  no provider is used, it need not (and must not) declare an `aws` provider requirement.
- Every variable has a `type` and a `description`.
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- A caller passing `extra_tags` -> those keys appear in the `tags` output.
- `mandatory_tags` keys always appear in the `tags` output.
- An `environment` outside the allow-list -> validation fails with the custom message.
- `tag_keys` is the sorted key list of the merged map.

## Acceptance Criteria

A deterministic test at `tests/ext10/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `modules/tagging/` exists and contains exactly `versions.tf`, `variables.tf`,
  `locals.tf`, `outputs.tf` (no `main.tf`, since no resources are created).
- `versions.tf` declares `required_version` with an explicit constraint operator and
  contains no `provider "aws"`/`required_providers` `aws` block.
- No file in `modules/tagging/` contains a `provider "` block or a `resource "` block.
- Every `variable` block has `type` and `description`.
- The `environment` variable contains a `validation` block with a non-empty
  `error_message` string literal.
- Both `mandatory_tags` and `extra_tags` variable types are `map(string)`.
- `locals.tf` builds the merged tag map using the `merge(` function and references both
  `var.mandatory_tags` and `var.extra_tags`; the baseline tag map includes a
  Terraform-managed marker tag.
- `outputs.tf` declares an output named `tags` and an output named `tag_keys`; the
  `tag_keys` output's `value` references the `keys(` function and the `sort(` function;
  every output has a `description`.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext10/test_terraform_module_patterns.py -v
```
