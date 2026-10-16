# Task: Add Plan-Mode Coverage for Public Route Tables and Internet Gateway Routing

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). The module decides how many **public route tables** to create (one shared table by default, or one per public subnet when multiple-table mode is requested), wires each public subnet to a route table, and adds a default IPv4 route to the Internet Gateway. This conditional routing logic currently has no automated test coverage.

## Files to Create/Modify

- `tests/public_routing_unit_test.tftest.hcl` (new) — plan-mode regression coverage for public route-table sizing, route-table associations, and the IGW default route.

The file must live in a new top-level `tests/` directory and must exercise the **root module** at the repository root.

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Use a fixed baseline, for example:

```
name           = "route-vpc"
cidr           = "10.30.0.0/16"
azs            = ["eu-central-1a", "eu-central-1b", "eu-central-1c"]
public_subnets  = ["10.30.1.0/24", "10.30.2.0/24", "10.30.3.0/24"]
private_subnets = ["10.30.11.0/24", "10.30.12.0/24", "10.30.13.0/24"]
```

Individual scenarios may add or override inputs on top of this baseline.

### Public route-table sizing

- **Single shared table (default)**: with the baseline, exactly one public route table is planned, and the number of public route-table associations equals the number of public subnets.
- **One table per subnet**: when multiple public route tables are requested, the number of public route tables equals the number of public subnets, and the number of public route-table associations still equals the number of public subnets.
- **No public subnets**: when `public_subnets` is an empty list, zero public route tables, zero public route-table associations, and zero public Internet-Gateway routes are planned.

### Internet Gateway routing

- **IGW route present by default**: with the baseline (IGW creation on), the public Internet-Gateway route is planned with destination `0.0.0.0/0`.
- **No IGW route when IGW disabled**: when Internet-Gateway creation is turned off, zero public Internet-Gateway routes are planned even though public subnets and a public route table still are.

### Route-table naming

- **Shared-table name**: in single-table mode the public route table's `Name` tag equals `"<name>-<public suffix>"`, derived from the `name` and public-subnet-suffix inputs.
- **Per-subnet table name**: in multiple-table mode a public route table's `Name` tag follows `"<name>-<public suffix>-<az>"` for the AZ at that index, derived from `name`, the suffix input, and `azs`.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete route-table counts, association counts, the route destination, and the name-tag conventions — naming assertions must be derived from inputs, not hard-coded.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | 1 public route table, 3 public associations, 1 IGW route to `0.0.0.0/0` |
| multiple public route tables enabled | 3 public route tables, 3 public associations |
| IGW creation disabled | 0 public IGW routes; public route table(s) still planned |
| `public_subnets = []` | 0 public route tables, 0 associations, 0 IGW routes |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `public_routing_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on concrete route-table and association counts, the IGW route destination, and the route-table name-tag conventions (single-table vs per-subnet) derived from inputs.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
