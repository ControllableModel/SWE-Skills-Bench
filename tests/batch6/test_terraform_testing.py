"""
Test for the 'terraform-testing' skill (variant batch: ext6).

Skill / variant task: add a plan-only `terraform test` regression file
(`tests/vpc_core_unit_test.tftest.hcl`) to the
`terraform-aws-modules/terraform-aws-vpc` root module that covers the *core
VPC-level attributes* and the *secondary-CIDR-block association* sizing logic:

  * VPC creation + identity: exactly one `aws_vpc` is planned, its `cidr_block`
    equals the supplied `cidr`, and its `Name` tag equals the supplied `name`.
  * Tag merge precedence: a global `tags` map and a VPC-specific `vpc_tags` map
    both land on the planned VPC; on a key collision the `vpc_tags` value wins
    (the module merges `{Name=...}, var.tags, var.vpc_tags`).
  * Configurable attributes: DNS support / DNS hostnames respect explicit
    overrides; `instance_tenancy` is `"default"` by default and `"dedicated"`
    when set.
  * Secondary CIDR associations: zero `aws_vpc_ipv4_cidr_block_association`
    resources by default, and exactly `length(secondary_cidr_blocks)` of them
    (with matching CIDR values) when a list is supplied.

This variant deliverable differs from ext1 (which targeted NAT/EIP counting and
subnets across two files). Here the single deliverable is
`tests/vpc_core_unit_test.tftest.hcl`.

Verification strategy (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the top-level `tests/` directory exists and contains the required
        `vpc_core_unit_test.tftest.hcl`, non-empty and using terraform
        `run`/`assert` constructs.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's own committed suite (the doc's native acceptance
            command, `terraform test -test-directory=tests -verbose`) reports
            every run block as pass.
          * INDEPENDENT tftest scenarios authored *by this test* (written into
            a throwaway directory under REPO_DIR) pin the concrete plan-time
            behaviour: VPC count + cidr_block, Name tag, tag-merge precedence,
            instance_tenancy default vs `dedicated`, DNS-attribute overrides,
            zero secondary associations by default, and N associations with
            matching CIDRs when a list is supplied.

The independent scenarios are the discriminative core: a file that merely
"looks related", hardcodes outcomes, or never wires the secondary-CIDR sizing
logic still fails them, because they execute against the real root-module plan.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by the independent scenarios (mirrors the task doc).
BASELINE = '''
    name = "core-vpc"
    cidr = "10.60.0.0/16"
    azs  = ["us-east-2a", "us-east-2b"]
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
    env.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    env.setdefault("AWS_REGION", "us-east-2")
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

    Returns the CompletedProcess. The directory is created fresh each call and
    removed afterwards.
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
  region                      = "us-east-2"
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
    """Plan-only core-VPC regression suite verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    CORE_FILE = os.path.join(TESTS_DIR, "vpc_core_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_core_test_file_present(self):
        """`tests/vpc_core_unit_test.tftest.hcl` must exist (the variant deliverable)."""
        assert os.path.isfile(self.CORE_FILE), (
            "expected deliverable not found: " + self.CORE_FILE
        )

    def test_core_file_uses_run_and_assert(self):
        """The deliverable must be non-empty and use terraform `run`/`assert` blocks."""
        assert os.path.isfile(self.CORE_FILE), "vpc_core_unit_test.tftest.hcl missing"
        with open(self.CORE_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "core test file is empty"
        assert "run " in body or 'run"' in body, "no `run` block in core test file"
        assert "assert" in body, "no `assert` block in core test file"

    def test_core_file_is_plan_mode(self):
        """
        The deliverable must run entirely in plan mode (`command = plan`) so it
        never creates/refreshes/destroys real AWS resources.
        """
        with open(self.CORE_FILE) as fh:
            body = fh.read()
        assert "command = plan" in body or "command=plan" in body.replace(" ", ""), (
            "core test file must use `command = plan` (plan-only, no apply)"
        )
        # A plan-only suite must never apply.
        assert "command = apply" not in body and "command=apply" not in body.replace(" ", ""), (
            "core test file must not use `command = apply` (must be plan-only)"
        )

    # ------------------------------------------------------------------
    # L2 - dynamic execution of the agent's own committed suite
    # ------------------------------------------------------------------

    @requires_terraform
    def test_agent_suite_all_pass(self):
        """
        The doc's native acceptance command must succeed and report every run
        block as pass:
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
    def test_independent_vpc_count_and_cidr(self):
        """Independent: baseline plans exactly 1 aws_vpc whose cidr_block == supplied cidr."""
        suite = PROVIDER_STUB + '''
run "vpc_count_and_cidr" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_vpc.this) == 1
    error_message = "expected exactly one aws_vpc to be planned for the baseline"
  }
  assert {
    condition     = aws_vpc.this[0].cidr_block == "10.60.0.0/16"
    error_message = "planned VPC cidr_block does not equal the supplied cidr"
  }
}
'''
        proc = _write_independent_suite("_indep_vpc_count", suite)
        assert proc.returncode == 0, (
            "independent vpc-count/cidr scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_vpc_name_tag(self):
        """Independent: the planned VPC's Name tag equals the supplied name."""
        suite = PROVIDER_STUB + '''
run "vpc_name_tag" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = aws_vpc.this[0].tags["Name"] == "core-vpc"
    error_message = "planned VPC Name tag does not equal the supplied name"
  }
}
'''
        proc = _write_independent_suite("_indep_vpc_name", suite)
        assert proc.returncode == 0, (
            "independent vpc-name-tag scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_tag_merge_precedence(self):
        """
        Independent: a global `tags` map and a VPC-specific `vpc_tags` map both
        land on the planned VPC; on a colliding key, the vpc_tags value wins
        (module merges {Name=name}, var.tags, var.vpc_tags).
        """
        suite = PROVIDER_STUB + '''
run "tag_merge_precedence" {
  command = plan
  variables {
''' + BASELINE + '''
    tags     = { Environment = "global", Owner = "team-a" }
    vpc_tags = { Environment = "vpc-specific", Tier = "network" }
  }
  assert {
    condition     = aws_vpc.this[0].tags["Owner"] == "team-a"
    error_message = "global tag Owner did not propagate to the planned VPC"
  }
  assert {
    condition     = aws_vpc.this[0].tags["Tier"] == "network"
    error_message = "vpc-specific tag Tier did not propagate to the planned VPC"
  }
  assert {
    condition     = aws_vpc.this[0].tags["Environment"] == "vpc-specific"
    error_message = "vpc_tags value must win over tags on a colliding key (Environment)"
  }
  assert {
    condition     = aws_vpc.this[0].tags["Name"] == "core-vpc"
    error_message = "Name tag must remain the supplied name after the merge"
  }
}
'''
        proc = _write_independent_suite("_indep_tag_merge", suite)
        assert proc.returncode == 0, (
            "independent tag-merge-precedence scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_instance_tenancy_default(self):
        """Independent: with the baseline, the planned VPC instance_tenancy == 'default'."""
        suite = PROVIDER_STUB + '''
run "tenancy_default" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = aws_vpc.this[0].instance_tenancy == "default"
    error_message = "baseline instance_tenancy should be the default value 'default'"
  }
}
'''
        proc = _write_independent_suite("_indep_tenancy_default", suite)
        assert proc.returncode == 0, (
            "independent tenancy-default scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_instance_tenancy_dedicated(self):
        """Independent: instance_tenancy='dedicated' is reflected on the planned VPC."""
        suite = PROVIDER_STUB + '''
run "tenancy_dedicated" {
  command = plan
  variables {
''' + BASELINE + '''
    instance_tenancy = "dedicated"
  }
  assert {
    condition     = aws_vpc.this[0].instance_tenancy == "dedicated"
    error_message = "planned VPC instance_tenancy should equal 'dedicated' when set"
  }
}
'''
        proc = _write_independent_suite("_indep_tenancy_dedicated", suite)
        assert proc.returncode == 0, (
            "independent tenancy-dedicated scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_dns_overrides(self):
        """
        Independent: explicit DNS overrides are reflected exactly on the planned
        VPC: enable_dns_hostnames=true and enable_dns_support=false.
        """
        suite = PROVIDER_STUB + '''
run "dns_overrides" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dns_hostnames = true
    enable_dns_support   = false
  }
  assert {
    condition     = aws_vpc.this[0].enable_dns_hostnames == true
    error_message = "planned VPC enable_dns_hostnames should be true when overridden"
  }
  assert {
    condition     = aws_vpc.this[0].enable_dns_support == false
    error_message = "planned VPC enable_dns_support should be false when overridden"
  }
}
'''
        proc = _write_independent_suite("_indep_dns_overrides", suite)
        assert proc.returncode == 0, (
            "independent dns-overrides scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_no_secondary_cidr_by_default(self):
        """Independent: baseline plans zero aws_vpc_ipv4_cidr_block_association resources."""
        suite = PROVIDER_STUB + '''
run "no_secondary_cidr" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_vpc_ipv4_cidr_block_association.this) == 0
    error_message = "expected zero secondary-CIDR associations for the baseline"
  }
}
'''
        proc = _write_independent_suite("_indep_no_secondary", suite)
        assert proc.returncode == 0, (
            "independent no-secondary-cidr scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_secondary_cidr_count_and_values(self):
        """
        Independent: when 2 secondary CIDR blocks are supplied, exactly 2
        associations are planned and each association's cidr_block is one of the
        supplied values (and the two supplied values are both present).
        """
        suite = PROVIDER_STUB + '''
run "secondary_cidr_count" {
  command = plan
  variables {
''' + BASELINE + '''
    secondary_cidr_blocks = ["10.61.0.0/16", "10.62.0.0/16"]
  }
  assert {
    condition     = length(aws_vpc_ipv4_cidr_block_association.this) == 2
    error_message = "expected 2 secondary-CIDR associations to match the input list length"
  }
  assert {
    condition = alltrue([
      for a in aws_vpc_ipv4_cidr_block_association.this :
      contains(["10.61.0.0/16", "10.62.0.0/16"], a.cidr_block)
    ])
    error_message = "a planned secondary-CIDR association has a cidr_block not in the supplied list"
  }
  assert {
    condition = (
      contains([for a in aws_vpc_ipv4_cidr_block_association.this : a.cidr_block], "10.61.0.0/16") &&
      contains([for a in aws_vpc_ipv4_cidr_block_association.this : a.cidr_block], "10.62.0.0/16")
    )
    error_message = "both supplied secondary CIDRs must appear among the planned associations"
  }
}
'''
        proc = _write_independent_suite("_indep_secondary_count", suite)
        assert proc.returncode == 0, (
            "independent secondary-cidr-count/values scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_secondary_cidr_three(self):
        """
        Independent (discriminative against a hardcoded count): supplying THREE
        secondary CIDR blocks plans exactly three associations — a stub that
        always returns 0/2 fails here.
        """
        suite = PROVIDER_STUB + '''
run "secondary_cidr_three" {
  command = plan
  variables {
''' + BASELINE + '''
    secondary_cidr_blocks = ["10.61.0.0/16", "10.62.0.0/16", "10.63.0.0/16"]
  }
  assert {
    condition     = length(aws_vpc_ipv4_cidr_block_association.this) == 3
    error_message = "expected 3 secondary-CIDR associations for a 3-element input list"
  }
}
'''
        proc = _write_independent_suite("_indep_secondary_three", suite)
        assert proc.returncode == 0, (
            "independent secondary-cidr-three scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
