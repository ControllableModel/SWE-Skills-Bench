# Task: Add Plan-Mode Coverage for the Redshift and ElastiCache Subnet Tiers

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). Alongside public/private subnets the module supports **redshift** (`redshift_subnets`) and **elasticache** (`elasticache_subnets`) tiers, each of which can create its own subnets, a managed subnet group (`aws_redshift_subnet_group` / `aws_elasticache_subnet_group`), and a dedicated route table. These two tiers and their subnet groups are not covered by any test.

## Files to Create/Modify

- `tests/redshift_elasticache_unit_test.tftest.hcl` (new) — plan-mode regression coverage for the redshift and elasticache subnet tiers, their subnet groups, route tables, naming, and outputs.

The file must live in a new top-level `tests/` directory and must exercise the **root module** at the repository root.

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Use a fixed baseline, for example:

```
name               = "cache-vpc"
cidr               = "10.90.0.0/16"
azs                = ["us-east-1a", "us-east-1b"]
private_subnets     = ["10.90.11.0/24", "10.90.12.0/24"]
redshift_subnets    = ["10.90.21.0/24", "10.90.22.0/24"]
elasticache_subnets = ["10.90.31.0/24", "10.90.32.0/24"]
```

Individual scenarios may add or override inputs on top of this baseline.

### Redshift tier

- **Subnet count**: with the baseline, the number of planned redshift subnets equals the length of `redshift_subnets`.
- **Subnet group**: with the baseline, exactly one `aws_redshift_subnet_group` is planned and the cardinality of its member subnet ids equals the redshift subnet count.
- **Group disabled**: when redshift-subnet-group creation is turned off while redshift subnets remain, zero `aws_redshift_subnet_group` resources are planned but the redshift subnets are still planned.
- **Subnet naming**: a planned redshift subnet's `Name` tag follows the `"<name>-<redshift suffix>-<az>"` convention derived from the `name`, redshift suffix, and `azs` inputs.

### ElastiCache tier

- **Subnet count**: with the baseline, the number of planned elasticache subnets equals the length of `elasticache_subnets`.
- **Subnet group**: with the baseline, exactly one `aws_elasticache_subnet_group` is planned with member-subnet cardinality equal to the elasticache subnet count.
- **Group disabled**: when elasticache-subnet-group creation is turned off while elasticache subnets remain, zero `aws_elasticache_subnet_group` resources are planned but the subnets are still planned.

### Empty-tier and output coverage

- **No redshift subnets**: when `redshift_subnets` is empty, zero redshift subnets and zero redshift subnet groups are planned.
- **No elasticache subnets**: when `elasticache_subnets` is empty, zero elasticache subnets and zero elasticache subnet groups are planned.
- **Output contract**: the `redshift_subnets` and `elasticache_subnets` outputs each have the same length as their corresponding input lists for the baseline.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete subnet/subnet-group counts, the disabled-group behavior, the redshift subnet name-tag convention, and the listed outputs.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | 2 redshift subnets, 1 redshift subnet group |
| baseline | 2 elasticache subnets, 1 elasticache subnet group |
| redshift subnet group disabled | 0 redshift subnet groups, 2 redshift subnets still planned |
| elasticache subnet group disabled | 0 elasticache subnet groups, 2 elasticache subnets still planned |
| `redshift_subnets = []` | 0 redshift subnets, 0 redshift subnet groups |
| `elasticache_subnets = []` | 0 elasticache subnets, 0 elasticache subnet groups |
| baseline | `redshift_subnets` / `elasticache_subnets` outputs length == 2 each |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `redshift_elasticache_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on concrete redshift/elasticache subnet and subnet-group counts, the disabled-group behavior, the redshift subnet name-tag convention, and the redshift/elasticache outputs as described above.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
