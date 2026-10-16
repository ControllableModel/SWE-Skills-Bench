# Task: Add Plan-Mode Coverage for Internet/Egress Gateways and Public IP Mapping

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). The module gates the **Internet Gateway** (`aws_internet_gateway`) on having public subnets and `create_igw`, gates the **egress-only Internet Gateway** (`aws_egress_only_internet_gateway`) on IPv6 plus `create_egress_only_igw`, and controls whether public subnets auto-assign public IPs via `map_public_ip_on_launch`. These gateway-gating conditions and the public-IP toggle are untested.

## Files to Create/Modify

- `tests/gateways_unit_test.tftest.hcl` (new) — plan-mode regression coverage for Internet Gateway creation, egress-only IGW gating, public-IP-on-launch, and the gateway outputs.

The file must live in a new top-level `tests/` directory and must exercise the **root module** at the repository root.

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Use a fixed baseline, for example:

```
name           = "gw-vpc"
cidr           = "10.80.0.0/16"
azs            = ["eu-west-1a", "eu-west-1b"]
public_subnets  = ["10.80.1.0/24", "10.80.2.0/24"]
private_subnets = ["10.80.11.0/24", "10.80.12.0/24"]
```

Individual scenarios may add or override inputs on top of this baseline.

### Internet Gateway gating

- **Created with public subnets**: with the baseline, exactly one `aws_internet_gateway` is planned and its `Name` tag equals the module `name`.
- **Not created without public subnets**: when `public_subnets` is an empty list, zero `aws_internet_gateway` resources are planned.
- **Not created when disabled**: when Internet-Gateway creation is turned off (with public subnets still present), zero `aws_internet_gateway` resources are planned.

### Egress-only Internet Gateway gating

- **Not created by default**: with the baseline (IPv6 not enabled), zero `aws_egress_only_internet_gateway` resources are planned even if egress-only IGW creation is requested.
- **Created when IPv6 + requested**: when IPv6 is enabled and egress-only IGW creation is requested with at least one subnet present, exactly one `aws_egress_only_internet_gateway` is planned.

### Public IP on launch

- **Default off**: with the baseline, the planned public subnets do not auto-assign public IPs on launch.
- **Enabled**: when public-IP-on-launch is turned on, every planned public subnet has `map_public_ip_on_launch` set to true (expressed as a single assertion over the whole public-subnet collection).

### Output contract

- **IGW id output**: when an Internet Gateway is planned the module's `igw_id` output is defined; when no Internet Gateway is planned (no public subnets), the `igw_id` output is empty/null.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete gateway counts, the public-IP-on-launch flag across all public subnets, the IGW `Name` tag, and the `igw_id` output presence — not merely that a gateway exists.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | 1 internet gateway, `Name` tag == `gw-vpc` |
| `public_subnets = []` | 0 internet gateways; `igw_id` output empty |
| IGW creation disabled | 0 internet gateways |
| egress-only IGW requested, IPv6 off | 0 egress-only IGWs |
| IPv6 enabled + egress-only IGW requested | 1 egress-only IGW |
| public-IP-on-launch enabled | all public subnets `map_public_ip_on_launch == true` |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `gateways_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on concrete Internet-Gateway and egress-only-IGW counts under each gating condition, the public-IP-on-launch flag across all public subnets, and the `igw_id` output behavior.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
