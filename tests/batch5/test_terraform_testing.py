"""
Test for the 'terraform-testing' skill  (variant: ext5).

Skill task (ext5): add plan-only `terraform test` regression coverage for the
**intra** subnet tier of the `terraform-aws-modules/terraform-aws-vpc` root
module. The intra tier is deliberately ISOLATED: intra subnets get their own
route table(s) but NO route to a NAT gateway and NO default route to the
Internet Gateway. The agent must create exactly one new file:

    tests/intra_subnets_unit_test.tftest.hcl

covering intra subnet creation (count, empty-list, CIDR membership), the
isolation guarantees (route table present, association count, no NAT route, no
IGW route), the intra subnet Name-tag convention, and the intra outputs.

Native acceptance command (driven by the L2 tests below):

    terraform init -backend=false && terraform test -test-directory=tests -verbose

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the `tests/` directory exists and contains the required
        `intra_subnets_unit_test.tftest.hcl`, non-empty, using terraform
        `run`/`assert`/`plan` constructs, and referencing the intra tier.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's own committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass.
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) re-derive, from the task doc, the
            concrete behaviour required: intra subnet count == len(intra_subnets);
            empty intra_subnets -> 0 subnets / 0 route tables; every intra CIDR is
            one of the supplied values; >=1 intra route table with one association
            per intra subnet; ISOLATION — even with NAT gateways enabled the intra
            route table receives no NAT route and no IGW route; the intra Name-tag
            convention "<name>-<intra suffix>-<az>"; and the intra outputs.

Discriminative core: the isolation scenarios verify that the intra tier owns no
`aws_route.*` that targets a NAT gateway or the IGW (the module ships no
`aws_route "intra*"` resource at all), and that enabling NAT does not perturb the
single intra route table. A solution that merely drops a file that "looks
related", that uses the wrong resource addresses, or that conflates the intra
tier with private/public routing fails these independent scenarios even if the
agent's own suite is hollow.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the ext5 task doc).
BASELINE = '''
    name            = "intra-vpc"
    cidr            = "10.50.0.0/16"
    azs             = ["us-west-2a", "us-west-2b", "us-west-2c"]
    private_subnets = ["10.50.11.0/24", "10.50.12.0/24", "10.50.13.0/24"]
    intra_subnets   = ["10.50.21.0/24", "10.50.22.0/24", "10.50.23.0/24"]
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
    """Run a terraform subcommand inside REPO_DIR with no real AWS access."""
    env = dict(os.environ)
    env.setdefault("AWS_ACCESS_KEY_ID", "test")
    env.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    env.setdefault("AWS_DEFAULT_REGION", "us-west-2")
    env.setdefault("AWS_REGION", "us-west-2")
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
  region                      = "us-west-2"
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
    """Plan-only intra-subnet-tier regression suite verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    INTRA_FILE = os.path.join(TESTS_DIR, "intra_subnets_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_intra_test_file_present(self):
        """`tests/` must contain the required intra_subnets_unit_test.tftest.hcl file."""
        assert os.path.isfile(self.INTRA_FILE), (
            "expected file not found: " + self.INTRA_FILE
        )

    def test_intra_file_uses_plan_run_and_assert(self):
        """The intra test file must be non-empty, plan-mode, and use run/assert blocks targeting the intra tier."""
        assert os.path.isfile(self.INTRA_FILE), "intra_subnets_unit_test.tftest.hcl missing"
        with open(self.INTRA_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "intra test file is empty"
        assert "run " in body or 'run"' in body, "no `run` block in intra test file"
        assert "assert" in body, "no `assert` block in intra test file"
        # Plan-only requirement from the doc.
        assert "command = plan" in body or "command=plan" in body, (
            "intra test file must run scenarios in plan mode (command = plan)"
        )
        # Must actually exercise the intra tier, not just any subnet.
        assert "intra" in body, "intra test file does not reference the intra tier"

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
    def test_independent_intra_subnet_count(self):
        """Independent: planned intra subnet count equals len(intra_subnets) == 3."""
        suite = PROVIDER_STUB + '''
run "intra_subnet_count" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_subnet.intra) == 3
    error_message = "expected 3 intra subnets to match the intra_subnets input length"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_count", suite)
        assert proc.returncode == 0, (
            "independent intra-subnet-count scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_empty_intra_no_subnets_no_route_tables(self):
        """Independent: intra_subnets=[] -> 0 intra subnets AND 0 intra route tables."""
        suite = PROVIDER_STUB + '''
run "intra_empty" {
  command = plan
  variables {
    name            = "intra-vpc"
    cidr            = "10.50.0.0/16"
    azs             = ["us-west-2a", "us-west-2b", "us-west-2c"]
    private_subnets = ["10.50.11.0/24", "10.50.12.0/24", "10.50.13.0/24"]
    intra_subnets   = []
  }
  assert {
    condition     = length(aws_subnet.intra) == 0
    error_message = "expected 0 intra subnets when intra_subnets is an empty list"
  }
  assert {
    condition     = length(aws_route_table.intra) == 0
    error_message = "expected 0 intra route tables when intra_subnets is an empty list"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_empty", suite)
        assert proc.returncode == 0, (
            "independent empty-intra scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_intra_cidr_membership(self):
        """Independent: every planned intra subnet cidr_block is one of the supplied intra_subnets values."""
        suite = PROVIDER_STUB + '''
run "intra_cidr_membership" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition = alltrue([
      for s in aws_subnet.intra :
      contains(["10.50.21.0/24", "10.50.22.0/24", "10.50.23.0/24"], s.cidr_block)
    ])
    error_message = "an intra subnet cidr_block is not one of the supplied intra_subnets values"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_cidr", suite)
        assert proc.returncode == 0, (
            "independent intra-CIDR-membership scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_intra_route_table_and_associations(self):
        """Independent: >=1 intra route table planned and intra associations == intra subnet count (3)."""
        suite = PROVIDER_STUB + '''
run "intra_route_tables" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_route_table.intra) >= 1
    error_message = "expected at least one intra route table with the baseline intra_subnets"
  }
  assert {
    condition     = length(aws_route_table_association.intra) == 3
    error_message = "expected one intra route-table association per intra subnet (3)"
  }
  assert {
    condition     = length(aws_route_table_association.intra) == length(aws_subnet.intra)
    error_message = "intra associations count must equal intra subnet count"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_rt", suite)
        assert proc.returncode == 0, (
            "independent intra-route-table/association scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_intra_isolation_with_nat_enabled(self):
        """
        Independent ISOLATION: even with NAT gateways enabled in the SAME config,
        the intra tier must remain isolated -- it still owns a single intra route
        table and one association per intra subnet, and enabling NAT does not add
        intra route tables. The module ships no `aws_route` resource that targets
        a NAT gateway from the intra tier, so the intra route table count is
        unaffected by NAT being on.
        """
        suite = PROVIDER_STUB + '''
run "intra_isolation_nat" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_nat_gateway = true
    single_nat_gateway = true
  }
  assert {
    condition     = length(aws_route_table.intra) == 1
    error_message = "enabling NAT must not change the single intra route table (intra tier is isolated, no NAT route)"
  }
  assert {
    condition     = length(aws_route_table_association.intra) == 3
    error_message = "intra associations must remain one per intra subnet even with NAT enabled"
  }
  assert {
    condition     = length(aws_subnet.intra) == 3
    error_message = "intra subnet count must be unaffected by NAT being enabled"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_isolation_nat", suite)
        assert proc.returncode == 0, (
            "independent intra-isolation-with-NAT scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_intra_no_igw_default_route(self):
        """
        Independent ISOLATION: the intra route table receives no default
        (0.0.0.0/0) route to the Internet Gateway even when the public tier and
        IGW exist. We verify this structurally: the planned public IGW route
        targets the PUBLIC route table, never an intra route table id, and the
        intra route table itself is still a single isolated table.
        """
        suite = PROVIDER_STUB + '''
run "intra_no_igw_route" {
  command = plan
  variables {
    name            = "intra-vpc"
    cidr            = "10.50.0.0/16"
    azs             = ["us-west-2a", "us-west-2b", "us-west-2c"]
    public_subnets  = ["10.50.1.0/24", "10.50.2.0/24", "10.50.3.0/24"]
    private_subnets = ["10.50.11.0/24", "10.50.12.0/24", "10.50.13.0/24"]
    intra_subnets   = ["10.50.21.0/24", "10.50.22.0/24", "10.50.23.0/24"]
  }
  assert {
    condition     = length(aws_route_table.intra) == 1
    error_message = "intra tier must own exactly one isolated route table"
  }
  assert {
    condition = alltrue([
      for r in aws_route.public_internet_gateway :
      !contains(aws_route_table.intra[*].id, r.route_table_id)
    ])
    error_message = "an IGW default route is attached to an intra route table (intra must have no IGW route)"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_no_igw", suite)
        assert proc.returncode == 0, (
            "independent intra-no-IGW-route scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_intra_subnet_naming(self):
        """
        Independent: an intra subnet's Name tag follows
        "<name>-<intra suffix>-<az>" for the AZ at that index, derived from the
        name, intra_subnet_suffix, and azs inputs.
        """
        suite = PROVIDER_STUB + '''
run "intra_naming" {
  command = plan
  variables {
''' + BASELINE + '''
    intra_subnet_suffix = "intra"
  }
  assert {
    condition     = aws_subnet.intra[0].tags["Name"] == "intra-vpc-intra-us-west-2a"
    error_message = "intra subnet[0] Name tag does not follow <name>-<intra suffix>-<az>"
  }
  assert {
    condition     = aws_subnet.intra[2].tags["Name"] == "intra-vpc-intra-us-west-2c"
    error_message = "intra subnet[2] Name tag does not match the az at that index"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_naming", suite)
        assert proc.returncode == 0, (
            "independent intra-naming scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_intra_naming_custom_suffix(self):
        """
        Independent: a non-default intra_subnet_suffix is honoured in the Name
        tag -- "<name>-<custom suffix>-<az>". Guards against a solution that
        hardcodes the suffix instead of deriving it from the input.
        """
        suite = PROVIDER_STUB + '''
run "intra_naming_custom" {
  command = plan
  variables {
''' + BASELINE + '''
    intra_subnet_suffix = "isolated"
  }
  assert {
    condition     = aws_subnet.intra[1].tags["Name"] == "intra-vpc-isolated-us-west-2b"
    error_message = "intra subnet[1] Name tag must honour the custom intra_subnet_suffix"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_naming_custom", suite)
        assert proc.returncode == 0, (
            "independent intra-custom-suffix-naming scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_intra_output_contract(self):
        """
        Independent: the intra_subnets output has the same length as the
        intra_subnets input (3) and intra_route_table_ids is non-empty when
        intra subnets exist.
        """
        suite = PROVIDER_STUB + '''
run "intra_outputs" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(output.intra_subnets) == 3
    error_message = "intra_subnets output length must equal the intra_subnets input length (3)"
  }
  assert {
    condition     = length(output.intra_route_table_ids) >= 1
    error_message = "intra_route_table_ids output must be non-empty when intra subnets exist"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_outputs", suite)
        assert proc.returncode == 0, (
            "independent intra-output-contract scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_empty_intra_outputs_empty(self):
        """
        Independent (boundary): with intra_subnets=[], the intra_subnets output is
        empty and the intra_route_table_ids output is empty -- the tier collapses
        to nothing. A stub that always reports a fixed non-empty output fails.
        """
        suite = PROVIDER_STUB + '''
run "intra_outputs_empty" {
  command = plan
  variables {
    name            = "intra-vpc"
    cidr            = "10.50.0.0/16"
    azs             = ["us-west-2a", "us-west-2b", "us-west-2c"]
    private_subnets = ["10.50.11.0/24", "10.50.12.0/24", "10.50.13.0/24"]
    intra_subnets   = []
  }
  assert {
    condition     = length(output.intra_subnets) == 0
    error_message = "intra_subnets output must be empty when intra_subnets is []"
  }
  assert {
    condition     = length(output.intra_route_table_ids) == 0
    error_message = "intra_route_table_ids output must be empty when there are no intra subnets"
  }
}
'''
        proc = _write_independent_suite("_indep_intra_outputs_empty", suite)
        assert proc.returncode == 0, (
            "independent empty-intra-outputs scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
