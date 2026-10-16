"""
Test for the 'terraform-testing' skill (variant ext10).

Skill task: add plan-mode regression coverage for the *redshift* and
*elasticache* subnet tiers of the `terraform-aws-modules/terraform-aws-vpc`
root module. The agent must create a single new file
`tests/redshift_elasticache_unit_test.tftest.hcl` that exercises, in plan mode
only (no AWS credentials / no real resources):

  * redshift subnet count == len(redshift_subnets) and exactly 1
    `aws_redshift_subnet_group` whose member-subnet cardinality equals the
    redshift subnet count;
  * elasticache subnet count == len(elasticache_subnets) and exactly 1
    `aws_elasticache_subnet_group` whose member-subnet cardinality equals the
    elasticache subnet count;
  * group-disabled behaviour: turning off `create_redshift_subnet_group` /
    `create_elasticache_subnet_group` yields zero subnet groups while the
    subnets themselves remain planned;
  * empty-tier behaviour: empty `redshift_subnets` / `elasticache_subnets`
    yields zero subnets *and* zero subnet groups;
  * redshift subnet Name-tag convention "<name>-<redshift suffix>-<az>";
  * the `redshift_subnets` / `elasticache_subnets` outputs have the same length
    as their input lists.

Native acceptance command (run from the repo root):

    terraform init -backend=false && terraform test -test-directory=tests -verbose

Verification strategy (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the top-level `tests/` directory exists and contains the required
        `redshift_elasticache_unit_test.tftest.hcl` file, non-empty and using
        terraform `run`/`assert` constructs.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds;
          * the agent's own committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass;
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) pin down the concrete behaviour
            required by the task: redshift/elasticache subnet counts, the single
            subnet group with matching member cardinality, the disabled-group
            behaviour, the empty-tier behaviour, the redshift Name-tag
            convention, and the two output lengths.

The independent scenarios are the discriminative core: a solution that merely
drops a file that "looks related", hardcodes counts, or forgets the
disabled-group / empty-tier behaviour fails them even if the agent's own suite
is hollow.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the task doc).
BASELINE = '''
    name                = "cache-vpc"
    cidr                = "10.90.0.0/16"
    azs                 = ["us-east-1a", "us-east-1b"]
    private_subnets     = ["10.90.11.0/24", "10.90.12.0/24"]
    redshift_subnets    = ["10.90.21.0/24", "10.90.22.0/24"]
    elasticache_subnets = ["10.90.31.0/24", "10.90.32.0/24"]
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
    env.setdefault("AWS_ACCESS_KEY_ID", "test")
    env.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    env.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    env.setdefault("AWS_REGION", "us-east-1")
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
    and run `terraform test` against the root module using it. The directory is
    created fresh each call and removed afterwards.
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
  region                      = "us-east-1"
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
    """Plan-only redshift/elasticache regression-suite verification."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    SUITE_FILE = os.path.join(TESTS_DIR, "redshift_elasticache_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_suite_file_present(self):
        """`tests/` must contain the required redshift/elasticache tftest file."""
        assert os.path.isdir(self.TESTS_DIR), "tests/ directory missing"
        present = sorted(
            f for f in os.listdir(self.TESTS_DIR) if f.endswith(".tftest.hcl")
        )
        assert "redshift_elasticache_unit_test.tftest.hcl" in present, (
            "tests/ must contain redshift_elasticache_unit_test.tftest.hcl, "
            "found: " + repr(present)
        )
        assert os.path.isfile(self.SUITE_FILE), (
            "redshift_elasticache_unit_test.tftest.hcl missing"
        )

    def test_suite_file_uses_run_and_assert(self):
        """The suite file must be non-empty and use `run`/`assert` blocks."""
        assert os.path.isfile(self.SUITE_FILE), "suite file missing"
        with open(self.SUITE_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "redshift/elasticache test file is empty"
        assert "run " in body or 'run"' in body, "no `run` block in suite file"
        assert "assert" in body, "no `assert` block in suite file"

    def test_suite_runs_in_plan_mode(self):
        """
        Every run block in the agent's suite must be plan-mode only (the task
        forbids applying real resources). At least one `command = plan` must be
        present and no `command = apply` may appear.
        """
        with open(self.SUITE_FILE) as fh:
            body = fh.read()
        # Normalise whitespace for a robust check of `command = plan/apply`.
        compact = " ".join(body.split())
        assert "command = plan" in compact, (
            "suite must drive plan mode (`command = plan`) for plan-only testing"
        )
        assert "command = apply" not in compact, (
            "suite must NOT use `command = apply` (plan-only requirement)"
        )

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
        assert "fail" not in combined.lower() or "0 failed" in combined.lower(), (
            "agent's suite reported a failing run block:\n" + combined
        )
        assert "pass" in combined.lower(), (
            "agent's suite produced no passing run blocks:\n" + combined
        )

    # ------------------------------------------------------------------
    # L2 - INDEPENDENT scenarios authored by this test (discriminative)
    # ------------------------------------------------------------------

    @requires_terraform
    def test_independent_redshift_subnet_count(self):
        """
        Independent: with the baseline, planned redshift subnets ==
        len(redshift_subnets) == 2.
        """
        suite = PROVIDER_STUB + '''
run "redshift_subnet_count" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_subnet.redshift) == 2
    error_message = "expected 2 redshift subnets to match the redshift_subnets input length"
  }
}
'''
        proc = _write_independent_suite("_indep_rs_count", suite)
        assert proc.returncode == 0, (
            "independent redshift-subnet-count scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_redshift_subnet_group(self):
        """
        Independent: with the baseline, exactly 1 aws_redshift_subnet_group is
        planned and its member subnet-id cardinality equals the redshift subnet
        count (2).
        """
        suite = PROVIDER_STUB + '''
run "redshift_subnet_group" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_redshift_subnet_group.redshift) == 1
    error_message = "expected exactly 1 redshift subnet group for the baseline"
  }
  assert {
    condition     = length(aws_redshift_subnet_group.redshift[0].subnet_ids) == 2
    error_message = "redshift subnet group member cardinality must equal redshift subnet count (2)"
  }
}
'''
        proc = _write_independent_suite("_indep_rs_group", suite)
        assert proc.returncode == 0, (
            "independent redshift-subnet-group scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_redshift_group_disabled(self):
        """
        Independent: create_redshift_subnet_group=false -> 0 redshift subnet
        groups, but the 2 redshift subnets are still planned.
        """
        suite = PROVIDER_STUB + '''
run "redshift_group_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create_redshift_subnet_group = false
  }
  assert {
    condition     = length(aws_redshift_subnet_group.redshift) == 0
    error_message = "expected 0 redshift subnet groups when create_redshift_subnet_group=false"
  }
  assert {
    condition     = length(aws_subnet.redshift) == 2
    error_message = "redshift subnets must still be planned when only the group is disabled"
  }
}
'''
        proc = _write_independent_suite("_indep_rs_group_off", suite)
        assert proc.returncode == 0, (
            "independent redshift-group-disabled scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_redshift_subnet_naming(self):
        """
        Independent: a planned redshift subnet's Name tag follows
        "<name>-<redshift suffix>-<az>", derived from name/suffix/azs inputs.
        """
        suite = PROVIDER_STUB + '''
run "redshift_subnet_naming" {
  command = plan
  variables {
''' + BASELINE + '''
    redshift_subnet_suffix = "redshift"
  }
  assert {
    condition     = aws_subnet.redshift[0].tags["Name"] == "cache-vpc-redshift-us-east-1a"
    error_message = "redshift subnet[0] Name tag does not follow <name>-<redshift suffix>-<az>"
  }
  assert {
    condition     = aws_subnet.redshift[1].tags["Name"] == "cache-vpc-redshift-us-east-1b"
    error_message = "redshift subnet[1] Name tag does not match az at that index"
  }
}
'''
        proc = _write_independent_suite("_indep_rs_naming", suite)
        assert proc.returncode == 0, (
            "independent redshift-subnet-naming scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_elasticache_subnet_count(self):
        """
        Independent: with the baseline, planned elasticache subnets ==
        len(elasticache_subnets) == 2.
        """
        suite = PROVIDER_STUB + '''
run "elasticache_subnet_count" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_subnet.elasticache) == 2
    error_message = "expected 2 elasticache subnets to match the elasticache_subnets input length"
  }
}
'''
        proc = _write_independent_suite("_indep_ec_count", suite)
        assert proc.returncode == 0, (
            "independent elasticache-subnet-count scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_elasticache_subnet_group(self):
        """
        Independent: with the baseline, exactly 1 aws_elasticache_subnet_group is
        planned and its member subnet-id cardinality equals the elasticache
        subnet count (2).
        """
        suite = PROVIDER_STUB + '''
run "elasticache_subnet_group" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_elasticache_subnet_group.elasticache) == 1
    error_message = "expected exactly 1 elasticache subnet group for the baseline"
  }
  assert {
    condition     = length(aws_elasticache_subnet_group.elasticache[0].subnet_ids) == 2
    error_message = "elasticache subnet group member cardinality must equal elasticache subnet count (2)"
  }
}
'''
        proc = _write_independent_suite("_indep_ec_group", suite)
        assert proc.returncode == 0, (
            "independent elasticache-subnet-group scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_elasticache_group_disabled(self):
        """
        Independent: create_elasticache_subnet_group=false -> 0 elasticache
        subnet groups, but the 2 elasticache subnets are still planned.
        """
        suite = PROVIDER_STUB + '''
run "elasticache_group_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create_elasticache_subnet_group = false
  }
  assert {
    condition     = length(aws_elasticache_subnet_group.elasticache) == 0
    error_message = "expected 0 elasticache subnet groups when create_elasticache_subnet_group=false"
  }
  assert {
    condition     = length(aws_subnet.elasticache) == 2
    error_message = "elasticache subnets must still be planned when only the group is disabled"
  }
}
'''
        proc = _write_independent_suite("_indep_ec_group_off", suite)
        assert proc.returncode == 0, (
            "independent elasticache-group-disabled scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_empty_redshift_tier(self):
        """
        Independent: redshift_subnets = [] -> 0 redshift subnets AND 0 redshift
        subnet groups (no orphan group when there are no subnets).
        """
        suite = PROVIDER_STUB + '''
run "empty_redshift" {
  command = plan
  variables {
    name                = "cache-vpc"
    cidr                = "10.90.0.0/16"
    azs                 = ["us-east-1a", "us-east-1b"]
    private_subnets     = ["10.90.11.0/24", "10.90.12.0/24"]
    redshift_subnets    = []
    elasticache_subnets = ["10.90.31.0/24", "10.90.32.0/24"]
  }
  assert {
    condition     = length(aws_subnet.redshift) == 0
    error_message = "expected 0 redshift subnets when redshift_subnets is empty"
  }
  assert {
    condition     = length(aws_redshift_subnet_group.redshift) == 0
    error_message = "expected 0 redshift subnet groups when redshift_subnets is empty"
  }
}
'''
        proc = _write_independent_suite("_indep_rs_empty", suite)
        assert proc.returncode == 0, (
            "independent empty-redshift-tier scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_empty_elasticache_tier(self):
        """
        Independent: elasticache_subnets = [] -> 0 elasticache subnets AND 0
        elasticache subnet groups.
        """
        suite = PROVIDER_STUB + '''
run "empty_elasticache" {
  command = plan
  variables {
    name                = "cache-vpc"
    cidr                = "10.90.0.0/16"
    azs                 = ["us-east-1a", "us-east-1b"]
    private_subnets     = ["10.90.11.0/24", "10.90.12.0/24"]
    redshift_subnets    = ["10.90.21.0/24", "10.90.22.0/24"]
    elasticache_subnets = []
  }
  assert {
    condition     = length(aws_subnet.elasticache) == 0
    error_message = "expected 0 elasticache subnets when elasticache_subnets is empty"
  }
  assert {
    condition     = length(aws_elasticache_subnet_group.elasticache) == 0
    error_message = "expected 0 elasticache subnet groups when elasticache_subnets is empty"
  }
}
'''
        proc = _write_independent_suite("_indep_ec_empty", suite)
        assert proc.returncode == 0, (
            "independent empty-elasticache-tier scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_output_contract(self):
        """
        Independent: the redshift_subnets and elasticache_subnets outputs each
        have the same length as their corresponding input lists (2 each) for the
        baseline.
        """
        suite = PROVIDER_STUB + '''
run "output_contract" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(output.redshift_subnets) == 2
    error_message = "redshift_subnets output length != len(redshift_subnets) input (2)"
  }
  assert {
    condition     = length(output.elasticache_subnets) == 2
    error_message = "elasticache_subnets output length != len(elasticache_subnets) input (2)"
  }
}
'''
        proc = _write_independent_suite("_indep_outputs", suite)
        assert proc.returncode == 0, (
            "independent output-contract scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
