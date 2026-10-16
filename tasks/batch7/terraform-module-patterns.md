# Task: Author a VPC Example with Flow Logs to an Encrypted Destination

## Background

The `terraform-aws-modules/terraform-aws-vpc` repository ships consumer examples
under `examples/` (including `examples/flow-log`) and a `modules/flow-log`
submodule. This task adds a new example that creates a VPC and ships its VPC flow
logs to a destination, where the destination type and a sensitive retention/access
parameter are driven by validated, properly-marked inputs.

## Files to Create/Modify

Create a new example directory `examples/secure-flow-log/`; one file per concern.

- `examples/secure-flow-log/versions.tf` (new) — version requirements.
- `examples/secure-flow-log/variables.tf` (new) — input variables.
- `examples/secure-flow-log/locals.tf` (new) — derived values.
- `examples/secure-flow-log/main.tf` (new) — provider, data source, VPC module invocation with flow logs enabled.
- `examples/secure-flow-log/outputs.tf` (new) — outputs.
- `tests/ext7/test_terraform_module_patterns.py` (new) — the deterministic test below.

## Requirements

### Configurable input

- A variable `flow_log_destination_type` (string) rejected unless it is one of an
  explicit allow-list (for example `cloud-watch-logs` / `s3`), with a clear custom
  error message.
- A variable `log_retention_days` (number) rejected unless it is one of the values AWS
  permits for log retention, with a clear custom error message.
- A variable `flow_log_kms_key_id` (string) that is a **sensitive** input (it must be
  marked so it is not echoed in plan/state output) with a description; it may default to
  an empty string.

### Derived values

`locals.tf` must compute the shared tag set (including a Terraform-managed marker tag)
and any derived flow-log configuration values. The VPC name must be derived from a
variable or local.

### Module invocation

`main.tf` invokes the root module once (`source = "../../"`), enabling VPC flow logs
with the chosen destination type and retention, and wiring the KMS key id when provided.

### Outputs

Expose at least the VPC id and the flow log id. Any output that surfaces the KMS key id
must itself be marked sensitive. Every output must carry a description.

### Constraints

- Every variable has a `type` and a `description`.
- The KMS key input variable must be marked `sensitive = true`.
- Version requirements pinned with explicit operators in `versions.tf` only; provider
  `source = "hashicorp/aws"`.
- Lowercase-underscore identifiers; two-space indentation; no tabs.
- No hardcoded AWS credentials/secrets.

### Expected Functionality

- A valid destination type and retention -> a VPC with flow logs enabled is planned.
- An invalid `flow_log_destination_type` or `log_retention_days` -> validation fails with the custom message.
- The KMS key id is never rendered in plan output (it is a sensitive value).

## Acceptance Criteria

A deterministic test at `tests/ext7/test_terraform_module_patterns.py` (Python
standard library only; inspects `.tf` files as text, no `terraform` binary) verifies
and passes:

- `examples/secure-flow-log/` exists and contains exactly `versions.tf`, `variables.tf`,
  `locals.tf`, `main.tf`, `outputs.tf`.
- `versions.tf` pins `required_version` with an explicit operator and the `aws`
  provider with `source = "hashicorp/aws"` and a pinned `version`; no other file does.
- Every `variable` block has `type` and `description`.
- Both `flow_log_destination_type` and `log_retention_days` contain a `validation`
  block with a non-empty `error_message` string literal.
- The `flow_log_kms_key_id` variable block contains `sensitive = true`.
- Any `output` block whose `value` references `flow_log_kms_key_id` (or the KMS key)
  is itself marked `sensitive = true`.
- The module block referencing `source = "../../"` appears exactly once.
- Every `output` block has a `description`; outputs exposing the VPC id and a flow log id exist.
- `locals.tf` shared tags include a Terraform-managed marker tag.
- All top-level block labels match `^[a-z][a-z0-9_]*$`.
- Every `.tf` file uses spaces only for indentation (no tabs).
- No `AKIA[0-9A-Z]{16}` pattern and no `aws_access_key`/`secret_key` literal assignment.

Run the test with:

```bash
pytest tests/ext7/test_terraform_module_patterns.py -v
```
