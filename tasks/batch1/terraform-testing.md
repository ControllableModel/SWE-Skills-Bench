# Task: Add an Automated Regression Suite for the VPC Module's NAT Gateway and Subnet Behavior

## Background

This repository is the `terraform-aws-modules/terraform-aws-vpc` root module (`main.tf`, `variables.tf`, `outputs.tf`). It exposes many input variables (e.g. `cidr`, `azs`, `public_subnets`, `private_subnets`, `enable_nat_gateway`, `single_nat_gateway`, `one_nat_gateway_per_az`) that interact in non-obvious ways to decide how many NAT gateways, EIPs, subnets, and route tables get created. The module currently ships with **no automated tests**, so any change to that conditional logic could silently break consumers.

## Files to Create/Modify

- `tests/nat_gateway_unit_test.tftest.hcl` (new) — regression coverage for NAT gateway / EIP counting across the single, per-AZ, and per-subnet modes.
- `tests/subnets_unit_test.tftest.hcl` (new) — regression coverage for subnet creation counts, naming, tagging, and the module's key outputs.

Both new files must live in a new top-level `tests/` directory and must exercise the root module (the configuration defined by `main.tf` / `variables.tf` / `outputs.tf` at the repository root).

## Requirements

The two new files form a fast, self-contained regression suite that exercises the root module's planning logic **without provisioning any real AWS infrastructure and without requiring AWS credentials or network access**. Every scenario must be evaluated against the generated plan only; no scenario may create, refresh, or destroy real resources.

All scenarios must run against a small, fixed VPC definition so results are deterministic. Use a single illustrative input set as the shared baseline, for example:

```
name           = "regression-vpc"
cidr           = "10.0.0.0/16"
azs            = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
public_subnets  = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
private_subnets = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
```

Individual scenarios may add or override inputs on top of this baseline as needed.

### NAT gateway counting (`tests/nat_gateway_unit_test.tftest.hcl`)

Cover, as distinct named scenarios, how the module sizes the NAT gateway tier given the baseline above (3 AZs, 3 public + 3 private subnets):

- **NAT disabled**: when NAT gateways are turned off, neither NAT gateways nor their dedicated Elastic IPs are planned.
- **Default multi-NAT**: when NAT is enabled with no consolidation flags set, the number of NAT gateways equals the largest subnet tier (3 for the baseline), and one dedicated Elastic IP is planned per NAT gateway.
- **Single shared NAT**: when NAT is enabled and the module is asked to consolidate to one shared gateway, exactly one NAT gateway and exactly one Elastic IP are planned, regardless of how many AZs or subnets exist.
- **One NAT per AZ**: when NAT is enabled and the module is asked to place one gateway in each availability zone, the number of NAT gateways and Elastic IPs each equals the number of AZs supplied.
- **Reused EIPs**: when NAT is enabled but the consumer supplies their own externally-managed NAT IP addresses, the module plans NAT gateways but plans **zero** module-managed Elastic IPs.

Each NAT-tier scenario must assert on the actual planned resource counts (NAT gateways and EIPs), not merely on output presence.

### Subnet, tagging, and output coverage (`tests/subnets_unit_test.tftest.hcl`)

Cover, as distinct named scenarios:

- **Subnet counts**: the number of planned public subnets and private subnets each matches the length of the corresponding input list for the baseline.
- **Subnet naming**: a public subnet's `Name` tag follows the module's `"<name>-<public suffix>-<az>"` convention for the AZ at that index, and a private subnet's `Name` tag follows the analogous private convention. The assertions must be derived from the supplied `name`, suffix, and `azs` inputs — they must hold for the baseline inputs and must not be hard-coded to a value that ignores them.
- **Common tags propagate**: when an arbitrary common tag map is supplied (e.g. `{ Environment = "test", Team = "platform" }`), each supplied key/value appears on a planned public subnet's tag set.
- **CIDR correctness**: every planned private subnet's CIDR block falls inside the VPC CIDR supplied in the baseline (i.e. each begins with the VPC network prefix), expressed as a single assertion over the whole private-subnet collection.
- **Output contract**: the module's `vpc_cidr_block` output equals the supplied `cidr`, the `public_subnets` and `private_subnets` outputs each have the expected length, and the `azs` output equals the supplied `azs` list.

### Negative coverage

At least one scenario must demonstrate that the module's own input validation rejects a malformed network input — for example, supplying a `cidr` that is not a syntactically valid IPv4 CIDR block must cause that scenario's plan to fail validation rather than silently succeed. This scenario must be expressed so that the failing validation makes the scenario **pass**, and a future change that removed the validation would make it **fail**.

### Constraints

- Tests must not depend on real AWS API calls, credentials, account state, region availability, or any wall-clock/random behavior; running them must be safe in an offline CI runner.
- Each scenario must carry a clear, scenario-specific name and a descriptive failure message that identifies which expectation broke.
- The suite must remain green against the module as it exists at this commit; a naive test that only checks "an output is non-empty" is insufficient — assertions must pin down the concrete counts, names, tags, and CIDRs described above.

### Expected Functionality

| Scenario inputs (on top of baseline) | Expected planned outcome |
| --- | --- |
| `enable_nat_gateway = false` | 0 NAT gateways, 0 module EIPs |
| `enable_nat_gateway = true` (no flags) | 3 NAT gateways, 3 module EIPs |
| `enable_nat_gateway = true`, `single_nat_gateway = true` | 1 NAT gateway, 1 module EIP |
| `enable_nat_gateway = true`, `one_nat_gateway_per_az = true` | 3 NAT gateways, 3 module EIPs |
| `enable_nat_gateway = true`, `reuse_nat_ips = true` with supplied external IP ids | 3 NAT gateways, 0 module EIPs |
| baseline | 3 public subnets, 3 private subnets planned; `vpc_cidr_block` output == `10.0.0.0/16` |
| malformed `cidr` | scenario's plan fails module input validation |

## Acceptance Criteria

- A new directory `tests/` exists at the repository root containing exactly the two files `nat_gateway_unit_test.tftest.hcl` and `subnets_unit_test.tftest.hcl`.
- Both files run entirely in plan mode (no real resources are created, refreshed, or destroyed) and complete with no AWS credentials configured.
- Every scenario passes, including the negative validation scenario, which passes *because* the malformed input is rejected.
- The NAT scenarios assert on concrete planned counts for both NAT gateways and module-managed Elastic IPs, matching the table above; the subnet scenarios assert on concrete subnet counts, the name-tag convention, common-tag propagation, private-subnet CIDR containment, and the listed module outputs.
- The following command, run from the repository root, exits successfully (zero) and reports every run block as `pass`:

```bash
terraform init -backend=false && terraform test -test-directory=tests -verbose
```
