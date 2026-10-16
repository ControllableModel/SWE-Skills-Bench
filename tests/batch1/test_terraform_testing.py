"""
Test for the 'terraform-testing' skill.

Skill task: add an automated, plan-only regression suite (`terraform test`) to
the `terraform-aws-modules/terraform-aws-vpc` root module covering NAT-gateway /
EIP counting modes, subnet counts / naming / tagging / CIDR containment, the
module's key outputs, and a negative input-validation scenario for a malformed
`cidr`.

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the `tests/` directory exists and contains exactly the two required
        `.tftest.hcl` files, each non-empty and using terraform `run`/`assert`
        constructs.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's own committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass.
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) pin down the concrete behaviour
            required by the task: NAT/EIP counts in disabled / default / single /
            per-AZ / reuse-IP modes, subnet counts, the Name-tag convention,
            common-tag propagation, private-subnet CIDR containment, the module
            outputs, and that a malformed `cidr` is *rejected* by module input
            validation (the negative scenario passes only because validation
            fires).

The independent scenarios are the discriminative core: a solution that merely
drops files that "look related", or that forgets to add the `cidr` validation,
fails them even if the agent's own suite is hollow.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the task doc).
BASELINE = '''
    name            = "regression-vpc"
    cidr            = "10.0.0.0/16"
    azs             = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
    public_subnets  = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
    private_subnets = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
'''


# ---------------------------------------------------------------------------
# Toolchain resolution
# ---------------------------------------------------------------------------

def _find_terraform():
    """Return the terraform/opentofu executable to use, or None."""
    for cand in ("terraform", "tofu", "opentofu"):
        path = shutil.which(cand)
        if path:
            return path
    # common install locations
    for path in (
        "/usr/local/bin/terraform",
        "/usr/bin/terraform",
        "/usr/local/bin/tofu",
        "/usr/bin/tofu",
    ):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


TERRAFORM = _find_terraform()
requires_terraform = pytest.mark.skipif(
    TERRAFORM is None,
    reason="terraform/opentofu binary not found in container",
)


def _run_tf(args, timeout=600):
    """Run a terraform subcommand inside REPO_DIR with no AWS access."""
    env = dict(os.environ)
    # Guarantee no real AWS access / credentials are required.
    env.setdefault("AWS_ACCESS_KEY_ID", "test")
    env.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    env.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
    env.setdefault("AWS_REGION", "eu-west-1")
    env["AWS_EC2_METADATA_DISABLED"] = "true"
    env["TF_IN_AUTOMATION"] = "1"
    env["TF_INPUT"] = "0"
    return subprocess.run(
        [TERRAFORM] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


_INIT_DONE = {"ok": False}


def _ensure_init():
    """Run `terraform init -backend=false` once for the module."""
    if _INIT_DONE["ok"]:
        return
    proc = _run_tf(["init", "-backend=false", "-input=false", "-no-color"], timeout=600)
    assert proc.returncode == 0, (
        "`terraform init -backend=false` failed:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    _INIT_DONE["ok"] = True


def _write_independent_suite(dirname, contents):
    """
    Write a single .tftest.hcl file into a throwaway directory *under* REPO_DIR
    and run `terraform test` against the root module using it.

    Returns the CompletedProcess. The directory is created fresh each call.
    """
    test_dir = os.path.join(REPO_DIR, dirname)
    if os.path.isdir(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    fpath = os.path.join(test_dir, "independent.tftest.hcl")
    with open(fpath, "w") as fh:
        fh.write(contents)
    try:
        proc = _run_tf(
            ["test", "-test-directory=" + dirname, "-no-color", "-verbose"],
            timeout=600,
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    return proc


# A provider stub so plan-only `terraform test` never reaches AWS. Each
# independent suite embeds it via a `provider "aws"` block with skip flags.
PROVIDER_STUB = '''
provider "aws" {
  region                      = "eu-west-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}
'''


@pytest.fixture(scope="module", autouse=True)
def _module_init():
    if TERRAFORM is None:
        pytest.skip("terraform/opentofu binary not found")
    _ensure_init()


class TestTerraformTesting:
    """Plan-only regression suite verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    NAT_FILE = os.path.join(TESTS_DIR, "nat_gateway_unit_test.tftest.hcl")
    SUBNET_FILE = os.path.join(TESTS_DIR, "subnets_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_exactly_two_tftest_files(self):
        """`tests/` must contain exactly the two required .tftest.hcl files."""
        assert os.path.isdir(self.TESTS_DIR), "tests/ directory missing"
        tftests = sorted(
            f for f in os.listdir(self.TESTS_DIR) if f.endswith(".tftest.hcl")
        )
        assert tftests == [
            "nat_gateway_unit_test.tftest.hcl",
            "subnets_unit_test.tftest.hcl",
        ], (
            "tests/ must contain exactly nat_gateway_unit_test.tftest.hcl and "
            "subnets_unit_test.tftest.hcl, found: " + repr(tftests)
        )

    def test_nat_file_uses_run_and_assert(self):
        """NAT test file must be non-empty and use `run`/`assert` blocks."""
        assert os.path.isfile(self.NAT_FILE), "nat_gateway_unit_test.tftest.hcl missing"
        with open(self.NAT_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "NAT test file is empty"
        assert "run " in body or "run\"" in body, "no `run` block in NAT test file"
        assert "assert" in body, "no `assert` block in NAT test file"

    def test_subnet_file_uses_run_and_assert(self):
        """Subnet test file must be non-empty and use `run`/`assert` blocks."""
        assert os.path.isfile(self.SUBNET_FILE), "subnets_unit_test.tftest.hcl missing"
        with open(self.SUBNET_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "subnet test file is empty"
        assert "run " in body or "run\"" in body, "no `run` block in subnet test file"
        assert "assert" in body, "no `assert` block in subnet test file"

    # ------------------------------------------------------------------
    # L2 - dynamic execution of the agent's own committed suite
    # ------------------------------------------------------------------

    @requires_terraform
    def test_agent_suite_all_pass(self):
        """
        The acceptance command must succeed and report every run block as pass:
          terraform init -backend=false && terraform test -test-directory=tests -verbose
        """
        proc = _run_tf(
            ["test", "-test-directory=tests", "-no-color", "-verbose"],
            timeout=600,
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "`terraform test -test-directory=tests` did not exit 0.\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        # No run block may be reported as failing.
        assert "fail" not in combined.lower() or "0 failed" in combined.lower(), (
            "agent's suite reported a failing run block:\n" + combined
        )
        # Sanity: the suite must actually have executed run blocks (not empty).
        assert "pass" in combined.lower(), (
            "agent's suite produced no passing run blocks:\n" + combined
        )

    # ------------------------------------------------------------------
    # L2 - INDEPENDENT scenarios authored by this test (discriminative)
    # ------------------------------------------------------------------

    @requires_terraform
    def test_independent_nat_disabled(self):
        """Independent: NAT disabled -> 0 NAT gateways, 0 module EIPs."""
        suite = PROVIDER_STUB + '''
run "nat_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_nat_gateway = false
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 0
    error_message = "expected 0 NAT gateways when enable_nat_gateway=false"
  }
  assert {
    condition     = length(aws_eip.nat) == 0
    error_message = "expected 0 module EIPs when enable_nat_gateway=false"
  }
}
'''
        proc = _write_independent_suite("_indep_nat_disabled", suite)
        assert proc.returncode == 0, (
            "independent nat-disabled scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_nat_default_multi(self):
        """Independent: NAT on, no flags -> 3 NAT gateways and 3 module EIPs."""
        suite = PROVIDER_STUB + '''
run "nat_default_multi" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_nat_gateway = true
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 3
    error_message = "expected 3 NAT gateways for default multi-NAT over 3 subnets"
  }
  assert {
    condition     = length(aws_eip.nat) == 3
    error_message = "expected 3 module EIPs for default multi-NAT"
  }
}
'''
        proc = _write_independent_suite("_indep_nat_multi", suite)
        assert proc.returncode == 0, (
            "independent default-multi-NAT scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_single_nat(self):
        """Independent: single_nat_gateway -> exactly 1 NAT gateway and 1 EIP."""
        suite = PROVIDER_STUB + '''
run "single_nat" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_nat_gateway = true
    single_nat_gateway = true
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 1
    error_message = "expected exactly 1 NAT gateway with single_nat_gateway=true"
  }
  assert {
    condition     = length(aws_eip.nat) == 1
    error_message = "expected exactly 1 module EIP with single_nat_gateway=true"
  }
}
'''
        proc = _write_independent_suite("_indep_single_nat", suite)
        assert proc.returncode == 0, (
            "independent single-NAT scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_one_nat_per_az(self):
        """Independent: one_nat_gateway_per_az -> NAT gateways == #AZs == 3, EIPs == 3."""
        suite = PROVIDER_STUB + '''
run "one_nat_per_az" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_nat_gateway     = true
    one_nat_gateway_per_az = true
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 3
    error_message = "expected one NAT gateway per AZ (3) with one_nat_gateway_per_az=true"
  }
  assert {
    condition     = length(aws_eip.nat) == 3
    error_message = "expected 3 module EIPs with one_nat_gateway_per_az=true"
  }
}
'''
        proc = _write_independent_suite("_indep_nat_per_az", suite)
        assert proc.returncode == 0, (
            "independent one-NAT-per-AZ scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_reuse_nat_ips(self):
        """Independent: reuse_nat_ips with external IPs -> 3 NAT gateways, 0 module EIPs."""
        suite = PROVIDER_STUB + '''
run "reuse_nat_ips" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_nat_gateway = true
    reuse_nat_ips      = true
    external_nat_ip_ids = ["eipalloc-aaaa1111", "eipalloc-bbbb2222", "eipalloc-cccc3333"]
  }
  assert {
    condition     = length(aws_nat_gateway.this) == 3
    error_message = "expected 3 NAT gateways when reusing external EIPs"
  }
  assert {
    condition     = length(aws_eip.nat) == 0
    error_message = "expected 0 module-managed EIPs when reuse_nat_ips=true"
  }
}
'''
        proc = _write_independent_suite("_indep_reuse_nat", suite)
        assert proc.returncode == 0, (
            "independent reuse-NAT-IPs scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_subnet_counts(self):
        """Independent: planned public/private subnet counts each equal the input list length (3)."""
        suite = PROVIDER_STUB + '''
run "subnet_counts" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_subnet.public) == 3
    error_message = "expected 3 public subnets to match the public_subnets input length"
  }
  assert {
    condition     = length(aws_subnet.private) == 3
    error_message = "expected 3 private subnets to match the private_subnets input length"
  }
}
'''
        proc = _write_independent_suite("_indep_subnet_counts", suite)
        assert proc.returncode == 0, (
            "independent subnet-counts scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_subnet_naming(self):
        """
        Independent: a public subnet's Name tag follows
        "<name>-<public suffix>-<az>" and private follows the analogous private
        convention, derived from the actual name/suffix/azs inputs.
        """
        suite = PROVIDER_STUB + '''
run "subnet_naming" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_suffix  = "public"
    private_subnet_suffix = "private"
  }
  assert {
    condition     = aws_subnet.public[0].tags["Name"] == "regression-vpc-public-eu-west-1a"
    error_message = "public subnet[0] Name tag does not follow <name>-<public suffix>-<az>"
  }
  assert {
    condition     = aws_subnet.public[2].tags["Name"] == "regression-vpc-public-eu-west-1c"
    error_message = "public subnet[2] Name tag does not match az at that index"
  }
  assert {
    condition     = aws_subnet.private[1].tags["Name"] == "regression-vpc-private-eu-west-1b"
    error_message = "private subnet[1] Name tag does not follow <name>-<private suffix>-<az>"
  }
}
'''
        proc = _write_independent_suite("_indep_subnet_naming", suite)
        assert proc.returncode == 0, (
            "independent subnet-naming scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_common_tags_propagate(self):
        """Independent: each supplied common tag key/value appears on a planned public subnet."""
        suite = PROVIDER_STUB + '''
run "common_tags" {
  command = plan
  variables {
''' + BASELINE + '''
    tags = { Environment = "test", Team = "platform" }
  }
  assert {
    condition     = aws_subnet.public[0].tags["Environment"] == "test"
    error_message = "common tag Environment=test did not propagate to public subnet"
  }
  assert {
    condition     = aws_subnet.public[0].tags["Team"] == "platform"
    error_message = "common tag Team=platform did not propagate to public subnet"
  }
}
'''
        proc = _write_independent_suite("_indep_common_tags", suite)
        assert proc.returncode == 0, (
            "independent common-tags scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_private_cidr_containment(self):
        """Independent: every planned private subnet CIDR begins with the VPC network prefix (10.0.)."""
        suite = PROVIDER_STUB + '''
run "private_cidr_containment" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = alltrue([for s in aws_subnet.private : startswith(s.cidr_block, "10.0.")])
    error_message = "a private subnet CIDR falls outside the VPC 10.0.0.0/16 prefix"
  }
}
'''
        proc = _write_independent_suite("_indep_private_cidr", suite)
        assert proc.returncode == 0, (
            "independent private-CIDR-containment scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_output_contract(self):
        """
        Independent: vpc_cidr_block == cidr, public/private subnet output lengths
        equal the input list lengths, and azs output equals the azs input.
        """
        suite = PROVIDER_STUB + '''
run "output_contract" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = output.vpc_cidr_block == "10.0.0.0/16"
    error_message = "vpc_cidr_block output does not equal supplied cidr"
  }
  assert {
    condition     = length(output.public_subnets) == 3
    error_message = "public_subnets output length != 3"
  }
  assert {
    condition     = length(output.private_subnets) == 3
    error_message = "private_subnets output length != 3"
  }
  assert {
    condition     = output.azs == ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
    error_message = "azs output does not equal supplied azs list"
  }
}
'''
        proc = _write_independent_suite("_indep_outputs", suite)
        assert proc.returncode == 0, (
            "independent output-contract scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_malformed_cidr_rejected(self):
        """
        Independent NEGATIVE: a malformed `cidr` must be rejected by the module's
        own input validation. We use `expect_failures` on var.cidr; the scenario
        PASSES only because validation fires. If the agent never added a cidr
        validation block, the plan would succeed and this run block fails (so the
        whole `terraform test` exits non-zero and this assertion catches it).
        """
        suite = PROVIDER_STUB + '''
run "malformed_cidr_rejected" {
  command = plan
  variables {
    name            = "regression-vpc"
    cidr            = "not-a-cidr"
    azs             = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]
    public_subnets  = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
    private_subnets = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
  }
  expect_failures = [
    var.cidr,
  ]
}
'''
        proc = _write_independent_suite("_indep_neg_cidr", suite)
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "negative scenario did not pass: a malformed `cidr` was NOT rejected "
            "by module input validation (the module must add a validation block "
            "on var.cidr).\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "pass" in combined.lower(), (
            "negative cidr scenario produced no passing run block:\n" + combined
        )
