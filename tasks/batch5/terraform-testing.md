# Task: Add Plan-Mode Coverage for the Intra Subnet Tier and Its Isolation Guarantees

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). The module supports an **intra** subnet tier (`intra_subnets`) that is deliberately isolated: intra subnets get their own route table(s) but **no** route to a NAT gateway or the Internet Gateway. This isolation property is central to the tier's purpose and is currently untested.

## Files to Create/Modify

- `tests/intra_subnets_unit_test.tftest.hcl` (new) — plan-mode regression coverage for intra subnet creation, route tables, isolation (no NAT/IGW route), naming, and the intra outputs.

The file must live in a new top-level `tests/` directory and must exercise the **root module** at the repository root.

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Use a fixed baseline, for example:

```
name           = "intra-vpc"
cidr           = "10.50.0.0/16"
azs            = ["us-west-2a", "us-west-2b", "us-west-2c"]
private_subnets = ["10.50.11.0/24", "10.50.12.0/24", "10.50.13.0/24"]
intra_subnets   = ["10.50.21.0/24", "10.50.22.0/24", "10.50.23.0/24"]
```

Individual scenarios may add or override inputs on top of this baseline.

### Intra subnet creation

- **Subnet count**: with the baseline, the number of planned intra subnets equals the length of `intra_subnets`.
- **No intra subnets**: when `intra_subnets` is an empty list, zero intra subnets and zero intra route tables are planned.
- **CIDR membership**: every planned intra subnet's `cidr_block` is one of the values supplied in `intra_subnets`, expressed as a single assertion over the whole intra-subnet collection.

### Isolation guarantees

- **Route table present**: with the baseline, at least one intra route table is planned and the number of intra route-table associations equals the number of intra subnets.
- **No NAT route**: even when NAT gateways are enabled in the same configuration, the intra tier must not receive a route through a NAT gateway. (No `aws_route` resource that targets a NAT gateway may belong to the intra route table.)
- **No public IGW route**: the intra route table receives no default route to the Internet Gateway.

### Naming and outputs

- **Subnet naming**: a planned intra subnet's `Name` tag follows the `"<name>-<intra suffix>-<az>"` convention for the AZ at that index, derived from the `name`, intra subnet suffix, and `azs` inputs.
- **Output contract**: the module's `intra_subnets` output has the same length as the `intra_subnets` input list, and the `intra_route_table_ids` output is non-empty when intra subnets exist.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete subnet/route-table/association counts, the isolation property, the name-tag convention, and the listed outputs.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | 3 intra subnets, >=1 intra route table, 3 intra associations |
| `intra_subnets = []` | 0 intra subnets, 0 intra route tables |
| NAT gateways enabled | intra tier still has no NAT-gateway route |
| baseline | intra tier has no `0.0.0.0/0` IGW route |
| baseline | `intra_subnets` output length == 3 |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `intra_subnets_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on concrete intra subnet/route-table/association counts, the no-NAT and no-IGW isolation guarantees, the intra subnet name-tag convention, and the intra outputs.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
