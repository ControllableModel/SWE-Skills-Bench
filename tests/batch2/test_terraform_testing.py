"""
Test for the 'terraform-testing' skill (variant ext2).

Skill task: add plan-only `terraform test` regression coverage for the
`terraform-aws-modules/terraform-aws-vpc` root module's **database subnet
tier** -- the `aws_subnet.database` collection, its `aws_db_subnet_group`
(default-on, lower-cased name, disable-able), the dedicated
`aws_route_table.database`, the `<name>-<database suffix>-<az>` subnet naming
convention, and database-subnet CIDR membership. The single deliverable is:

    tests/database_subnets_unit_test.tftest.hcl

Native acceptance command (from the task doc's Acceptance Criteria), run from
the repository root:

    terraform init -backend=false && terraform test -test-directory=tests -verbose

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - a top-level `tests/` directory exists and contains
        `database_subnets_unit_test.tftest.hcl`, non-empty and using terraform
        `run`/`assert` constructs that actually reference the database tier
        (database subnets / db subnet group).

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's own committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass.
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) pin down the concrete behaviour
            required by THIS task: database subnet count == list length, empty
            list -> 0 db subnets + 0 db route tables, exactly one db subnet
            group whose member-id cardinality matches the db subnet list, the
            lower-cased group name from `name` and from an explicit uppercase
            group name, group-creation disabled -> 0 groups but db subnets
            survive, the `<name>-<db suffix>-<az>` Name-tag convention, db
            subnet CIDR membership, and the dedicated db route-table toggle.

The independent scenarios are the discriminative core: a solution that merely
drops a file that "looks related", hard-codes a Name tag, forgets to lower-case
the group name, or never wires the database tier into plan-mode assertions
fails them even if the agent's own suite is hollow.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the task doc).
BASELINE = '''
    name             = "db-tier-vpc"
    cidr             = "10.20.0.0/16"
    azs              = ["us-east-1a", "us-east-1b"]
    public_subnets   = ["10.20.1.0/24", "10.20.2.0/24"]
    private_subnets  = ["10.20.11.0/24", "10.20.12.0/24"]
    database_subnets = ["10.20.21.0/24", "10.20.22.0/24"]
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
    """Plan-only database-subnet-tier regression verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    DB_FILE = os.path.join(TESTS_DIR, "database_subnets_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_database_tftest_file_present(self):
        """`tests/` must contain the required database_subnets_unit_test.tftest.hcl."""
        assert os.path.isfile(self.DB_FILE), (
            "expected deliverable not found: " + self.DB_FILE
        )

    def test_db_file_uses_run_and_assert(self):
        """The db test file must be non-empty and use `run`/`assert` blocks."""
        assert os.path.isfile(self.DB_FILE), "database_subnets_unit_test.tftest.hcl missing"
        with open(self.DB_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "database test file is empty"
        assert "run " in body or 'run"' in body, "no `run` block in database test file"
        assert "assert" in body, "no `assert` block in database test file"

    def test_db_file_references_database_tier(self):
        """
        The deliverable must actually exercise the database tier (not a copy of
        an unrelated subnet test): it must reference the database subnet and/or
        db-subnet-group resources, and `command = plan` (plan mode only).
        """
        with open(self.DB_FILE) as fh:
            body = fh.read()
        assert "plan" in body, "database test file does not run in plan mode (`command = plan`)"
        assert "database" in body, (
            "database test file does not reference the database subnet tier "
            "(aws_subnet.database / aws_db_subnet_group / database_subnets)"
        )

    # ------------------------------------------------------------------
    # L2 - dynamic execution of the agent's own committed suite
    # ------------------------------------------------------------------

    @requires_terraform
    def test_agent_suite_all_pass(self):
        """
        The native acceptance command must succeed and report every run block as
        pass:
          terraform init -backend=false && terraform test -test-directory=tests -verbose
        """
        proc = _run_tf(
            ["test", "-test-directory=tests", "-no-color", "-verbose"],
            timeout=900,
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
    def test_independent_db_subnet_count(self):
        """Independent: planned db subnets == len(database_subnets) == 2."""
        suite = PROVIDER_STUB + '''
run "db_subnet_count" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_subnet.database) == 2
    error_message = "expected 2 database subnets to match the database_subnets input length"
  }
}
'''
        proc = _write_independent_suite("_indep_db_count", suite)
        assert proc.returncode == 0, (
            "independent db-subnet-count scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_empty_db_subnets(self):
        """
        Independent: database_subnets = [] -> 0 database subnets AND 0 database
        route tables planned (even with the dedicated route table toggled on).
        """
        suite = PROVIDER_STUB + '''
run "no_db_subnets" {
  command = plan
  variables {
    name             = "db-tier-vpc"
    cidr             = "10.20.0.0/16"
    azs              = ["us-east-1a", "us-east-1b"]
    public_subnets   = ["10.20.1.0/24", "10.20.2.0/24"]
    private_subnets  = ["10.20.11.0/24", "10.20.12.0/24"]
    database_subnets = []
    create_database_subnet_route_table = true
  }
  assert {
    condition     = length(aws_subnet.database) == 0
    error_message = "expected 0 database subnets when database_subnets is empty"
  }
  assert {
    condition     = length(aws_route_table.database) == 0
    error_message = "expected 0 database route tables when database_subnets is empty"
  }
}
'''
        proc = _write_independent_suite("_indep_db_empty", suite)
        assert proc.returncode == 0, (
            "independent empty-db-subnets scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_db_cidr_membership(self):
        """
        Independent: every planned database subnet's cidr_block is one of the
        supplied database_subnets values (single assertion over the collection).
        """
        suite = PROVIDER_STUB + '''
run "db_cidr_membership" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = alltrue([for s in aws_subnet.database : contains(["10.20.21.0/24", "10.20.22.0/24"], s.cidr_block)])
    error_message = "a database subnet cidr_block is not one of the supplied database_subnets values"
  }
}
'''
        proc = _write_independent_suite("_indep_db_cidr", suite)
        assert proc.returncode == 0, (
            "independent db-cidr-membership scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_db_subnet_group_default(self):
        """
        Independent: with the baseline exactly one aws_db_subnet_group is planned
        and its member-subnet-id set has the same cardinality as the database
        subnet list (2).
        """
        suite = PROVIDER_STUB + '''
run "db_group_default" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_db_subnet_group.database) == 1
    error_message = "expected exactly 1 aws_db_subnet_group by default"
  }
  assert {
    condition     = length(aws_db_subnet_group.database[0].subnet_ids) == 2
    error_message = "db subnet group member-id cardinality must equal the database subnet count (2)"
  }
}
'''
        proc = _write_independent_suite("_indep_db_group", suite)
        assert proc.returncode == 0, (
            "independent db-subnet-group-default scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_db_group_name_from_name_lowercased(self):
        """
        Independent: when `name` is uppercase and no explicit group name is given,
        the planned db subnet group name is the fully lower-cased `name`.
        """
        suite = PROVIDER_STUB + '''
run "db_group_name_lowercased" {
  command = plan
  variables {
    name             = "DB-Tier-VPC"
    cidr             = "10.20.0.0/16"
    azs              = ["us-east-1a", "us-east-1b"]
    public_subnets   = ["10.20.1.0/24", "10.20.2.0/24"]
    private_subnets  = ["10.20.11.0/24", "10.20.12.0/24"]
    database_subnets = ["10.20.21.0/24", "10.20.22.0/24"]
  }
  assert {
    condition     = aws_db_subnet_group.database[0].name == "db-tier-vpc"
    error_message = "db subnet group name must be the lower-cased form of var.name"
  }
}
'''
        proc = _write_independent_suite("_indep_db_group_name", suite)
        assert proc.returncode == 0, (
            "independent db-group-name-lowercasing scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_db_explicit_group_name_lowercased(self):
        """
        Independent: an explicit uppercase database_subnet_group_name is planned
        as its lower-cased form (taking precedence over `name`).
        """
        suite = PROVIDER_STUB + '''
run "db_explicit_group_name" {
  command = plan
  variables {
''' + BASELINE + '''
    database_subnet_group_name = "My-DB-Group"
  }
  assert {
    condition     = aws_db_subnet_group.database[0].name == "my-db-group"
    error_message = "explicit database_subnet_group_name must be planned lower-cased"
  }
}
'''
        proc = _write_independent_suite("_indep_db_explicit_name", suite)
        assert proc.returncode == 0, (
            "independent explicit-group-name scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_db_group_disabled(self):
        """
        Independent: with create_database_subnet_group=false and database subnets
        still present -> 0 db subnet groups, but 2 database subnets still planned.
        """
        suite = PROVIDER_STUB + '''
run "db_group_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create_database_subnet_group = false
  }
  assert {
    condition     = length(aws_db_subnet_group.database) == 0
    error_message = "expected 0 db subnet groups when create_database_subnet_group=false"
  }
  assert {
    condition     = length(aws_subnet.database) == 2
    error_message = "database subnets must still be planned when only the group is disabled"
  }
}
'''
        proc = _write_independent_suite("_indep_db_group_off", suite)
        assert proc.returncode == 0, (
            "independent db-group-disabled scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_db_subnet_naming(self):
        """
        Independent: a database subnet's Name tag follows
        "<name>-<database suffix>-<az>" derived from name/db-suffix/azs (must not
        be hard-coded). Uses an explicit non-default suffix to defeat hardcoding.
        """
        suite = PROVIDER_STUB + '''
run "db_subnet_naming" {
  command = plan
  variables {
''' + BASELINE + '''
    database_subnet_suffix = "database"
  }
  assert {
    condition     = aws_subnet.database[0].tags["Name"] == "db-tier-vpc-database-us-east-1a"
    error_message = "db subnet[0] Name tag does not follow <name>-<db suffix>-<az> for az index 0"
  }
  assert {
    condition     = aws_subnet.database[1].tags["Name"] == "db-tier-vpc-database-us-east-1b"
    error_message = "db subnet[1] Name tag does not follow <name>-<db suffix>-<az> for az index 1"
  }
}
'''
        proc = _write_independent_suite("_indep_db_naming", suite)
        assert proc.returncode == 0, (
            "independent db-subnet-naming scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_db_route_table_toggle(self):
        """
        Independent: dedicated db route table planned when
        create_database_subnet_route_table=true (one per AZ -> 2), and 0 when the
        toggle is off (the module default) while db subnets remain.
        """
        suite_on = PROVIDER_STUB + '''
run "db_rt_enabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create_database_subnet_route_table = true
  }
  assert {
    condition     = length(aws_route_table.database) == 2
    error_message = "expected one dedicated db route table per AZ (2) when the toggle is on"
  }
}

run "db_rt_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create_database_subnet_route_table = false
  }
  assert {
    condition     = length(aws_route_table.database) == 0
    error_message = "expected 0 dedicated db route tables when create_database_subnet_route_table=false"
  }
  assert {
    condition     = length(aws_subnet.database) == 2
    error_message = "database subnets must still be planned when only the dedicated route table is off"
  }
}
'''
        proc = _write_independent_suite("_indep_db_rt", suite_on)
        assert proc.returncode == 0, (
            "independent db-route-table-toggle scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
