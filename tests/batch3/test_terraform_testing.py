"""
Test for the 'terraform-testing' skill (variant batch: ext3).

Skill task: add plan-mode (`terraform test`) regression coverage to the
`terraform-aws-modules/terraform-aws-vpc` root module for its PUBLIC routing
logic -- specifically the number of public route tables (single shared table by
default vs. one table per public subnet when
`create_multiple_public_route_tables=true`), the number of public route-table
associations, the Internet-Gateway default route (`aws_route.public_internet_gateway`
to `0.0.0.0/0`, gated on `create_igw`), the empty-`public_subnets` edge case,
and the public route-table `Name` tag conventions (shared-table vs per-subnet).

Required deliverable:
  tests/public_routing_unit_test.tftest.hcl  (new top-level tests/ dir)

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the top-level `tests/` directory exists and contains the required
        `public_routing_unit_test.tftest.hcl`, non-empty and using terraform
        `run`/`assert` constructs and the plan command.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's own committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass (the doc's native acceptance command).
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) pin down the concrete behaviour
            required by the task: single-table sizing + association count,
            per-subnet table sizing, empty-`public_subnets` (0/0/0), the IGW
            route destination `0.0.0.0/0`, the IGW route disappearing when
            `create_igw=false` (while route tables remain), and the shared vs
            per-subnet `Name`-tag conventions derived from inputs.

The independent scenarios are the discriminative core: a solution that merely
drops files that "look related", that hard-codes counts, that ignores
`create_multiple_public_route_tables` / `create_igw`, or that gets the
name-tag convention wrong fails them even if the agent's own suite is hollow.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the task doc).
BASELINE = '''
    name            = "route-vpc"
    cidr            = "10.30.0.0/16"
    azs             = ["eu-central-1a", "eu-central-1b", "eu-central-1c"]
    public_subnets  = ["10.30.1.0/24", "10.30.2.0/24", "10.30.3.0/24"]
    private_subnets = ["10.30.11.0/24", "10.30.12.0/24", "10.30.13.0/24"]
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
    env.setdefault("AWS_DEFAULT_REGION", "eu-central-1")
    env.setdefault("AWS_REGION", "eu-central-1")
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
  region                      = "eu-central-1"
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
    """Plan-only public-routing regression suite verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    ROUTING_FILE = os.path.join(TESTS_DIR, "public_routing_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_routing_file_present(self):
        """`tests/` must contain the required public_routing_unit_test.tftest.hcl."""
        assert os.path.isfile(self.ROUTING_FILE), (
            "expected deliverable missing: tests/public_routing_unit_test.tftest.hcl"
        )

    def test_routing_file_uses_run_assert_plan(self):
        """The routing test file must be non-empty and use `run`/`assert`/plan."""
        assert os.path.isfile(self.ROUTING_FILE), (
            "public_routing_unit_test.tftest.hcl missing"
        )
        with open(self.ROUTING_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "routing test file is empty"
        assert "run " in body or "run\"" in body, "no `run` block in routing test file"
        assert "assert" in body, "no `assert` block in routing test file"
        assert "plan" in body, (
            "routing test file must run in plan mode (no `command = plan` found)"
        )

    def test_routing_file_references_public_route_table(self):
        """
        The file must actually exercise the public-routing resources by name
        (a file that only touches NAT/subnets is not the deliverable).
        """
        with open(self.ROUTING_FILE) as fh:
            body = fh.read()
        assert "aws_route_table.public" in body, (
            "routing test must reference aws_route_table.public"
        )
        assert "aws_route.public_internet_gateway" in body, (
            "routing test must reference aws_route.public_internet_gateway"
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
    def test_independent_single_shared_table(self):
        """
        Independent: with the baseline (default mode), exactly 1 public route
        table is planned and the number of public route-table associations
        equals the number of public subnets (3).
        """
        suite = PROVIDER_STUB + '''
run "single_shared_table" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_route_table.public) == 1
    error_message = "expected exactly 1 shared public route table in default mode"
  }
  assert {
    condition     = length(aws_route_table_association.public) == 3
    error_message = "expected public associations to equal the 3 public subnets"
  }
}
'''
        proc = _write_independent_suite("_indep_single_table", suite)
        assert proc.returncode == 0, (
            "independent single-shared-table scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_table_per_subnet(self):
        """
        Independent: with create_multiple_public_route_tables=true, the number
        of public route tables equals the number of public subnets (3) and the
        number of public associations still equals the public subnet count (3).
        """
        suite = PROVIDER_STUB + '''
run "table_per_subnet" {
  command = plan
  variables {
''' + BASELINE + '''
    create_multiple_public_route_tables = true
  }
  assert {
    condition     = length(aws_route_table.public) == 3
    error_message = "expected 1 public route table per subnet (3) in multi-table mode"
  }
  assert {
    condition     = length(aws_route_table_association.public) == 3
    error_message = "expected 3 public associations in multi-table mode"
  }
}
'''
        proc = _write_independent_suite("_indep_per_subnet", suite)
        assert proc.returncode == 0, (
            "independent table-per-subnet scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_no_public_subnets(self):
        """
        Independent: with public_subnets = [], zero public route tables, zero
        public associations, and zero public IGW routes are planned.
        """
        suite = PROVIDER_STUB + '''
run "no_public_subnets" {
  command = plan
  variables {
    name            = "route-vpc"
    cidr            = "10.30.0.0/16"
    azs             = ["eu-central-1a", "eu-central-1b", "eu-central-1c"]
    public_subnets  = []
    private_subnets = ["10.30.11.0/24", "10.30.12.0/24", "10.30.13.0/24"]
  }
  assert {
    condition     = length(aws_route_table.public) == 0
    error_message = "expected 0 public route tables when public_subnets is empty"
  }
  assert {
    condition     = length(aws_route_table_association.public) == 0
    error_message = "expected 0 public associations when public_subnets is empty"
  }
  assert {
    condition     = length(aws_route.public_internet_gateway) == 0
    error_message = "expected 0 public IGW routes when public_subnets is empty"
  }
}
'''
        proc = _write_independent_suite("_indep_no_public", suite)
        assert proc.returncode == 0, (
            "independent no-public-subnets scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_igw_route_default(self):
        """
        Independent: with the baseline (create_igw on by default), exactly one
        public IGW route is planned (single-table mode) and its destination is
        0.0.0.0/0.
        """
        suite = PROVIDER_STUB + '''
run "igw_route_default" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_route.public_internet_gateway) == 1
    error_message = "expected 1 public IGW route in default single-table mode"
  }
  assert {
    condition     = aws_route.public_internet_gateway[0].destination_cidr_block == "0.0.0.0/0"
    error_message = "public IGW route destination must be 0.0.0.0/0"
  }
}
'''
        proc = _write_independent_suite("_indep_igw_default", suite)
        assert proc.returncode == 0, (
            "independent IGW-route-default scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_igw_disabled(self):
        """
        Independent: with create_igw=false, zero public IGW routes are planned,
        but a public route table is still planned (1 in default mode).
        """
        suite = PROVIDER_STUB + '''
run "igw_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create_igw = false
  }
  assert {
    condition     = length(aws_route.public_internet_gateway) == 0
    error_message = "expected 0 public IGW routes when create_igw=false"
  }
  assert {
    condition     = length(aws_route_table.public) == 1
    error_message = "public route table must still be planned when create_igw=false"
  }
}
'''
        proc = _write_independent_suite("_indep_igw_disabled", suite)
        assert proc.returncode == 0, (
            "independent IGW-disabled scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_shared_table_name(self):
        """
        Independent: in single-table mode the shared public route table's Name
        tag equals "<name>-<public suffix>", derived from the name and
        public_subnet_suffix inputs.
        """
        suite = PROVIDER_STUB + '''
run "shared_table_name" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_suffix = "public"
  }
  assert {
    condition     = aws_route_table.public[0].tags["Name"] == "route-vpc-public"
    error_message = "shared public route table Name tag must be <name>-<public suffix>"
  }
}
'''
        proc = _write_independent_suite("_indep_shared_name", suite)
        assert proc.returncode == 0, (
            "independent shared-table-name scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_per_subnet_table_name(self):
        """
        Independent: in multi-table mode a public route table's Name tag follows
        "<name>-<public suffix>-<az>" for the AZ at that index, derived from
        name, suffix, and azs.
        """
        suite = PROVIDER_STUB + '''
run "per_subnet_table_name" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_suffix                = "public"
    create_multiple_public_route_tables = true
  }
  assert {
    condition     = aws_route_table.public[0].tags["Name"] == "route-vpc-public-eu-central-1a"
    error_message = "per-subnet public route table[0] Name must be <name>-<suffix>-<az0>"
  }
  assert {
    condition     = aws_route_table.public[2].tags["Name"] == "route-vpc-public-eu-central-1c"
    error_message = "per-subnet public route table[2] Name must match az at that index"
  }
}
'''
        proc = _write_independent_suite("_indep_per_subnet_name", suite)
        assert proc.returncode == 0, (
            "independent per-subnet-table-name scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_custom_suffix_name(self):
        """
        Independent (anti-hardcode): with a non-default public_subnet_suffix the
        shared table Name must track the supplied suffix, not a hard-coded
        "public" literal.
        """
        suite = PROVIDER_STUB + '''
run "custom_suffix_name" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_suffix = "edge"
  }
  assert {
    condition     = aws_route_table.public[0].tags["Name"] == "route-vpc-edge"
    error_message = "shared route table Name must derive from supplied suffix (edge)"
  }
}
'''
        proc = _write_independent_suite("_indep_custom_suffix", suite)
        assert proc.returncode == 0, (
            "independent custom-suffix-name scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_multi_table_igw_route_count(self):
        """
        Independent: in multi-table mode (create_multiple_public_route_tables=
        true, IGW on) the number of public IGW routes equals the number of
        public route tables (3), each destined for 0.0.0.0/0.
        """
        suite = PROVIDER_STUB + '''
run "multi_table_igw_routes" {
  command = plan
  variables {
''' + BASELINE + '''
    create_multiple_public_route_tables = true
  }
  assert {
    condition     = length(aws_route.public_internet_gateway) == 3
    error_message = "expected 3 public IGW routes (one per public route table) in multi-table mode"
  }
  assert {
    condition     = alltrue([for r in aws_route.public_internet_gateway : r.destination_cidr_block == "0.0.0.0/0"])
    error_message = "every public IGW route must be destined for 0.0.0.0/0"
  }
}
'''
        proc = _write_independent_suite("_indep_multi_igw", suite)
        assert proc.returncode == 0, (
            "independent multi-table IGW-route-count scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
