# Task: Add Plan-Mode Coverage for the DHCP Options Set and Its VPC Association

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). When DHCP options are enabled the module creates an `aws_vpc_dhcp_options` resource (with domain name, name servers, NTP servers, NetBIOS settings, and merged tags) plus an `aws_vpc_dhcp_options_association` binding it to the VPC. This conditional resource and its tag-merging behavior are untested.

## Files to Create/Modify

- `tests/dhcp_options_unit_test.tftest.hcl` (new) — plan-mode regression coverage for DHCP options creation, the VPC association, the option values, and tag merging.

The file must live in a new top-level `tests/` directory and must exercise the **root module** at the repository root.

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Use a fixed baseline, for example:

```
name           = "dhcp-vpc"
cidr           = "10.40.0.0/16"
azs            = ["ap-southeast-2a", "ap-southeast-2b"]
private_subnets = ["10.40.11.0/24", "10.40.12.0/24"]
```

Individual scenarios may add or override inputs on top of this baseline.

### DHCP options creation gating

- **Disabled by default**: with the baseline (DHCP options not enabled), zero `aws_vpc_dhcp_options` and zero `aws_vpc_dhcp_options_association` resources are planned.
- **Enabled**: when DHCP options are turned on, exactly one `aws_vpc_dhcp_options` and exactly one `aws_vpc_dhcp_options_association` are planned.

### Option values

- **Domain name and servers**: when DHCP options are enabled with a supplied domain name, domain name servers, and NTP servers, the planned DHCP options resource carries exactly those supplied values (the domain name equals the supplied string, and the name-server and NTP-server lists equal the supplied lists).
- **NetBIOS node type**: when a NetBIOS node type is supplied, the planned DHCP options resource carries that value.

### Tag merging

- **Name and merged tags**: when DHCP options are enabled, the planned DHCP options resource's `Name` tag equals the module `name`, and any supplied global tags plus DHCP-specific tags both appear on the planned resource's tag set with their supplied values. When the same tag key is supplied both globally and as a DHCP-specific tag, the DHCP-specific value is the one present on the planned resource.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete resource counts, the specific option values supplied, and the merged-tag outcomes — not merely check that a resource exists.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | 0 DHCP options, 0 DHCP associations |
| DHCP options enabled | 1 DHCP options, 1 DHCP association |
| DHCP enabled + domain name `example.internal` | options `domain_name` == `"example.internal"` |
| DHCP enabled + supplied name servers / NTP servers | option lists equal the supplied lists |
| DHCP enabled + global tag + DHCP-specific tag w/ same key | DHCP-specific value wins on the planned resource |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `dhcp_options_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on concrete DHCP resource counts, the supplied option values, and the tag-merge precedence as described above.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
