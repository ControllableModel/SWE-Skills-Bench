# Task: Add Plan-Mode Coverage for Tag Propagation and Per-Tier Tag Precedence

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). Almost every resource computes its tags by merging a `Name` tag with the global `tags` map and then a tier-specific tag map (`public_subnet_tags`, `private_subnet_tags`, `vpc_tags`, `igw_tags`, etc.). The precedence and propagation of these merged tags across tiers is a cross-cutting behavior with no test coverage.

## Files to Create/Modify

- `tests/tag_propagation_unit_test.tftest.hcl` (new) — plan-mode regression coverage for global-tag propagation and tier-specific tag precedence across the VPC, public subnets, private subnets, and the Internet Gateway.

The file must live in a new top-level `tests/` directory and must exercise the **root module** at the repository root.

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Use a fixed baseline with a global tag map, for example:

```
name = "tag-vpc"
cidr = "10.70.0.0/16"
azs  = ["us-east-1a", "us-east-1b"]
public_subnets  = ["10.70.1.0/24", "10.70.2.0/24"]
private_subnets = ["10.70.11.0/24", "10.70.12.0/24"]
tags = { Owner = "platform", CostCenter = "1234" }
```

Individual scenarios may add or override inputs on top of this baseline.

### Global tag propagation

- **VPC**: every key/value in the global `tags` map appears on the planned `aws_vpc` resource's tag set.
- **Public subnets**: every key/value in the global `tags` map appears on a planned public subnet's tag set.
- **Private subnets**: every key/value in the global `tags` map appears on a planned private subnet's tag set.
- **Internet Gateway**: every key/value in the global `tags` map appears on the planned Internet Gateway's tag set.

### Per-tier precedence

- **Public-subnet-specific tags win**: when a public-subnet-specific tag map is supplied that shares a key with the global `tags` map but a different value, the planned public subnet carries the public-subnet-specific value for that key.
- **Tier isolation**: a public-subnet-specific tag key (one that does not appear in the global map) must appear on a planned public subnet but must **not** appear on a planned private subnet.

### Name tag preservation

- **Name not overwritten**: supplying a global tag map that does not contain a `Name` key must leave the computed `Name` tag intact on the planned VPC (equal to the module `name`) and on the planned public subnet (equal to its `"<name>-<public suffix>-<az>"` value derived from inputs).

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete tag keys/values across multiple resource types and the precedence outcomes — not merely that a single tag exists somewhere.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | global tags appear on VPC, public subnet, private subnet, IGW |
| public tag sharing a key with global, different value | public subnet uses the public-specific value |
| public-specific-only tag key | present on public subnet, absent on private subnet |
| baseline (no `Name` in tags) | VPC `Name` == `tag-vpc`; public subnet `Name` follows convention |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `tag_propagation_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on global-tag propagation across at least the VPC, public subnets, private subnets, and IGW, on per-tier precedence, on tier isolation, and on `Name`-tag preservation.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
