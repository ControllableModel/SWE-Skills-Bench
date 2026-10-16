# Task: Add Plan-Mode Coverage for the vpc-endpoints Submodule

## Background

This repository ships a child module at `modules/vpc-endpoints/` (`main.tf`, `variables.tf`, `outputs.tf`) that provisions `aws_vpc_endpoint` resources from an `endpoints` map, optionally creates a security group (`aws_security_group`) plus rules, and exposes an `endpoints` output keyed by the same map keys. None of this submodule's creation gating, fan-out, or output behavior is currently covered by tests.

## Files to Create/Modify

- `modules/vpc-endpoints/tests/endpoints_unit_test.tftest.hcl` (new) — plan-mode regression coverage for endpoint fan-out, the `create` gate, security-group creation, and the `endpoints` output.

The file must live in a new `tests/` directory **inside** `modules/vpc-endpoints/` and must exercise that submodule directly (the configuration under `modules/vpc-endpoints/`).

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Supply only the submodule's own inputs (`vpc_id`, `endpoints`, etc.) with fixed deterministic values, for example a `vpc_id` of `"vpc-12345678"` and an `endpoints` map with two entries (e.g. `s3` and `dynamodb`) each carrying a `service` and any required attributes.

Individual scenarios may add or override inputs as needed.

### Endpoint fan-out

- **One endpoint per map entry**: when an `endpoints` map with N entries is supplied, the number of planned `aws_vpc_endpoint` resources equals N.
- **Single entry**: when the map has exactly one entry, exactly one `aws_vpc_endpoint` is planned.
- **Empty map**: when the `endpoints` map is empty, zero `aws_vpc_endpoint` resources are planned.

### Create gate

- **Disabled**: when the submodule's `create` flag is turned off, zero `aws_vpc_endpoint` resources and zero security groups are planned regardless of the `endpoints` map contents.

### Security group

- **Created when requested**: when security-group creation is enabled, exactly one `aws_security_group` is planned and is associated with the supplied `vpc_id`.
- **Not created by default**: when security-group creation is not requested, zero `aws_security_group` resources are planned.

### Output contract

- **Endpoints output keys**: the submodule's `endpoints` output is keyed by the same keys present in the supplied `endpoints` input map (the set of output keys equals the set of input map keys).

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete resource counts, the create-gate behavior, and the output key set — not merely that an endpoint exists.

### Expected Functionality

| Scenario inputs | Expected planned outcome |
| --- | --- |
| 2-entry `endpoints` map | 2 `aws_vpc_endpoint` resources planned |
| 1-entry `endpoints` map | 1 `aws_vpc_endpoint` resource planned |
| empty `endpoints` map | 0 endpoints planned |
| `create = false` | 0 endpoints, 0 security groups |
| security-group creation enabled | 1 security group bound to the supplied `vpc_id` |
| 2-entry map | `endpoints` output keys == input map keys |

## Acceptance Criteria

- A new directory `modules/vpc-endpoints/tests/` exists containing the file `endpoints_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on concrete endpoint counts, the `create` gate, security-group creation, and the `endpoints` output key set as described above.
- The following command, run from inside `modules/vpc-endpoints/`, exits successfully (zero) and reports every run block as `pass`:

```bash
cd modules/vpc-endpoints && terraform init -backend=false && terraform test -test-directory=tests -verbose
```
