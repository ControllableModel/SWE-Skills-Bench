# Task: Add Plan-Mode Coverage for the Database Subnet Tier and Its Subnet Group

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). The module can carve out a dedicated **database subnet tier** (`database_subnets`), optionally bundle those subnets into an `aws_db_subnet_group`, give them their own route table, and name everything from the `name` / `database_subnet_suffix` inputs. None of this behavior is currently protected by any automated test.

## Files to Create/Modify

- `tests/database_subnets_unit_test.tftest.hcl` (new) — plan-mode regression coverage for the database subnet tier, its DB subnet group, route tables, and the related module outputs.

The file must live in a new top-level `tests/` directory and must exercise the **root module** (the configuration defined by `main.tf` / `variables.tf` / `outputs.tf` at the repository root).

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or make any network call. Use a fixed baseline so results are deterministic, for example:

```
name            = "db-tier-vpc"
cidr            = "10.20.0.0/16"
azs             = ["us-east-1a", "us-east-1b"]
public_subnets   = ["10.20.1.0/24", "10.20.2.0/24"]
private_subnets  = ["10.20.11.0/24", "10.20.12.0/24"]
database_subnets = ["10.20.21.0/24", "10.20.22.0/24"]
```

Individual scenarios may add or override inputs on top of this baseline.

### Database subnet creation

- **Subnet count**: with the baseline, the number of planned database subnets equals the length of the `database_subnets` list.
- **No database subnets**: when `database_subnets` is set to an empty list, zero database subnets and zero database route tables are planned.
- **CIDR correctness**: every planned database subnet's `cidr_block` is one of the values supplied in `database_subnets` (expressed as a single assertion over the whole database-subnet collection).

### Database subnet group

- **Group created by default**: with the baseline, exactly one `aws_db_subnet_group` is planned, and its set of member subnet ids has the same cardinality as the database subnet list.
- **Group name lowercasing**: when `name` contains uppercase characters and no explicit group name is supplied, the planned subnet group's `name` is the fully lower-cased form of `name`. When an explicit database subnet group name is supplied that contains uppercase characters, the planned group `name` is the lower-cased form of that explicit value.
- **Group disabled**: when subnet-group creation is turned off while database subnets remain, zero `aws_db_subnet_group` resources are planned but the database subnets themselves are still planned.

### Naming and route table

- **Subnet naming**: a planned database subnet's `Name` tag follows the `"<name>-<database suffix>-<az>"` convention for the AZ at that index, derived from the `name`, the database subnet suffix input, and `azs` (it must not be hard-coded to a literal that ignores those inputs).
- **Dedicated route table**: with the baseline, the database tier's dedicated route table is planned; when dedicated database route-table creation is turned off, zero database route tables are planned.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or any wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message identifying which expectation broke.
- A naive test that only checks "an output is non-empty" is insufficient — assertions must pin concrete counts, the lower-cased group name, the name-tag convention, and CIDR membership.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | 2 database subnets, 1 db subnet group |
| `database_subnets = []` | 0 database subnets, 0 database route tables |
| `name = "DB-Tier-VPC"` (no group name) | db subnet group name == `"db-tier-vpc"` |
| explicit group name `"My-DB-Group"` | db subnet group name == `"my-db-group"` |
| database subnet group creation disabled | 0 db subnet groups, 2 database subnets still planned |
| dedicated database route table disabled | 0 database route tables |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `database_subnets_unit_test.tftest.hcl`.
- The file runs entirely in plan mode (no real resources created, refreshed, or destroyed) and completes with no AWS credentials configured.
- Every scenario passes and asserts on concrete planned counts, the lower-cased subnet-group name, the database subnet name-tag convention, and database subnet CIDR membership as described above.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
