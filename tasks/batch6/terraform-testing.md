# Task: Add Plan-Mode Coverage for Core VPC Attributes and Secondary CIDR Associations

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). The top-level `aws_vpc` resource exposes several configurable attributes — `instance_tenancy`, `enable_dns_support`, `enable_dns_hostnames`, network-address-usage metrics — and the module can attach additional CIDR ranges via `aws_vpc_ipv4_cidr_block_association` driven by `secondary_cidr_blocks`. These VPC-level settings and the secondary-CIDR sizing logic are untested.

## Files to Create/Modify

- `tests/vpc_core_unit_test.tftest.hcl` (new) — plan-mode regression coverage for the core VPC attributes, the VPC `Name`/tag merge, and secondary-CIDR-block associations.

The file must live in a new top-level `tests/` directory and must exercise the **root module** at the repository root.

## Requirements

All scenarios must be evaluated against the generated plan only. No scenario may create, refresh, or destroy real AWS resources, require credentials, or perform network calls. Use a fixed baseline, for example:

```
name = "core-vpc"
cidr = "10.60.0.0/16"
azs  = ["us-east-2a", "us-east-2b"]
```

Individual scenarios may add or override inputs on top of this baseline.

### VPC creation and identity

- **VPC count**: with the baseline, exactly one `aws_vpc` resource is planned, and its `cidr_block` equals the supplied `cidr`.
- **VPC name tag**: the planned VPC's `Name` tag equals the supplied `name`.
- **Tag merge**: when both a global tag map and a VPC-specific tag map are supplied, each supplied key appears on the planned VPC's tag set; when the same key is supplied in both, the VPC-specific value is the one present.

### Configurable attributes

- **DNS defaults**: with the baseline the planned VPC has DNS support enabled and DNS hostnames disabled (the module's documented defaults).
- **DNS overrides**: when DNS hostnames are explicitly enabled and DNS support explicitly disabled, the planned VPC reflects exactly those values.
- **Instance tenancy**: with the baseline the planned VPC's `instance_tenancy` is the default value; when tenancy is set to `dedicated`, the planned VPC's `instance_tenancy` equals `"dedicated"`.

### Secondary CIDR associations

- **None by default**: with the baseline, zero `aws_vpc_ipv4_cidr_block_association` resources are planned.
- **Count matches input**: when a list of secondary CIDR blocks is supplied, the number of planned secondary-CIDR associations equals the length of that list, and each planned association's CIDR is one of the supplied values.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or wall-clock/random behavior.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message.
- Assertions must pin concrete attribute values, the tag-merge precedence, and the secondary-CIDR association count/values — not merely that the VPC exists.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| baseline | 1 VPC, `cidr_block` == `10.60.0.0/16`, `Name` tag == `core-vpc` |
| baseline | DNS support enabled, DNS hostnames disabled |
| `enable_dns_hostnames = true`, `enable_dns_support = false` | VPC reflects those values |
| `instance_tenancy = "dedicated"` | VPC `instance_tenancy` == `"dedicated"` |
| baseline | 0 secondary-CIDR associations |
| 2 secondary CIDR blocks supplied | 2 secondary-CIDR associations, CIDRs match input |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing the file `vpc_core_unit_test.tftest.hcl`.
- The file runs entirely in plan mode and completes with no AWS credentials configured.
- Every scenario passes and asserts on the concrete VPC attribute values, the VPC tag-merge precedence, and the secondary-CIDR association count and CIDR values as described above.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
