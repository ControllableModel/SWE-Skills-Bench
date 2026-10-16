"""
Test for the 'terraform-testing' skill (variant ext8).

Skill task: add a single plan-only `terraform test` regression file
(`tests/tag_propagation_unit_test.tftest.hcl`) to the
`terraform-aws-modules/terraform-aws-vpc` root module that pins down the
module's cross-cutting *tag* behavior:

  * global `tags` propagation onto the VPC, public subnets, private subnets,
    and the Internet Gateway;
  * per-tier precedence (a `public_subnet_tags` value overrides the global
    `tags` value for a shared key on public subnets);
  * tier isolation (a public-only tag key is present on public subnets but
    absent from private subnets);
  * Name-tag preservation (supplying global tags with NO `Name` key leaves the
    computed `Name` intact: VPC `Name == name`, public subnet `Name` follows
    `"<name>-<public suffix>-<az>"`).

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the top-level `tests/` directory exists and contains the required
        `tag_propagation_unit_test.tftest.hcl`, which is non-empty and uses
        terraform `run`/`assert` constructs in plan mode.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's own committed suite, driven by the doc's native command
            `terraform test -test-directory=tests -verbose`, reports every run
            block as pass.
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) re-derive the required tag
            behavior straight from THIS task doc: global-tag propagation across
            VPC / public / private / IGW, public-tier precedence over a shared
            key, tier isolation of a public-only key, and Name-tag preservation
            on both the VPC and a public subnet.

The independent scenarios are the discriminative core: a solution that merely
drops a file that "looks related", hardcodes a tag, or wires precedence the
wrong way (global winning over the tier map) fails them even if the agent's own
committed suite is hollow or absent.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the task doc).
# A *global* tag map with Owner / CostCenter and NO `Name` key.
BASELINE = '''
    name            = "tag-vpc"
    cidr            = "10.70.0.0/16"
    azs             = ["us-east-1a", "us-east-1b"]
    public_subnets  = ["10.70.1.0/24", "10.70.2.0/24"]
    private_subnets = ["10.70.11.0/24", "10.70.12.0/24"]
    tags            = { Owner = "platform", CostCenter = "1234" }
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
    and run `terraform test` against the root module using it. Returns the
    CompletedProcess; the directory is created fresh each call and removed after.
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
    """Plan-only tag-propagation/precedence regression verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    TAG_FILE = os.path.join(TESTS_DIR, "tag_propagation_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_tag_propagation_file_present(self):
        """`tests/` must contain the required tag_propagation_unit_test.tftest.hcl file."""
        assert os.path.isfile(self.TAG_FILE), (
            "required deliverable missing: " + self.TAG_FILE
        )

    def test_tag_file_uses_run_and_assert(self):
        """The tag test file must be non-empty and use terraform `run`/`assert` blocks."""
        assert os.path.isfile(self.TAG_FILE), "tag_propagation_unit_test.tftest.hcl missing"
        with open(self.TAG_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "tag propagation test file is empty"
        assert "run " in body or 'run"' in body, "no `run` block in tag test file"
        assert "assert" in body, "no `assert` block in tag test file"

    def test_tag_file_is_plan_mode(self):
        """The committed tag suite must run in plan mode (no apply against real AWS)."""
        with open(self.TAG_FILE) as fh:
            body = fh.read()
        assert "command = plan" in body or "command=plan" in body, (
            "tag suite must use `command = plan` (plan-only, no apply)"
        )
        assert "command = apply" not in body and "command=apply" not in body, (
            "tag suite must not apply real AWS resources"
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
        assert "fail" not in combined.lower() or "0 failed" in combined.lower(), (
            "agent's tag suite reported a failing run block:\n" + combined
        )
        assert "pass" in combined.lower(), (
            "agent's tag suite produced no passing run blocks:\n" + combined
        )

    # ------------------------------------------------------------------
    # L2 - INDEPENDENT scenarios authored by this test (discriminative)
    # ------------------------------------------------------------------

    @requires_terraform
    def test_independent_global_tags_on_vpc(self):
        """Independent: every global `tags` key/value appears on the planned aws_vpc."""
        suite = PROVIDER_STUB + '''
run "global_tags_on_vpc" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = aws_vpc.this[0].tags["Owner"] == "platform"
    error_message = "global tag Owner=platform did not propagate to the VPC"
  }
  assert {
    condition     = aws_vpc.this[0].tags["CostCenter"] == "1234"
    error_message = "global tag CostCenter=1234 did not propagate to the VPC"
  }
}
'''
        proc = _write_independent_suite("_indep_vpc_tags", suite)
        assert proc.returncode == 0, (
            "independent global-tags-on-VPC scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_global_tags_on_public_subnet(self):
        """Independent: every global `tags` key/value appears on a planned public subnet."""
        suite = PROVIDER_STUB + '''
run "global_tags_on_public" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = aws_subnet.public[0].tags["Owner"] == "platform"
    error_message = "global tag Owner=platform did not propagate to a public subnet"
  }
  assert {
    condition     = aws_subnet.public[1].tags["CostCenter"] == "1234"
    error_message = "global tag CostCenter=1234 did not propagate to a public subnet"
  }
}
'''
        proc = _write_independent_suite("_indep_public_global_tags", suite)
        assert proc.returncode == 0, (
            "independent global-tags-on-public-subnet scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_global_tags_on_private_subnet(self):
        """Independent: every global `tags` key/value appears on a planned private subnet."""
        suite = PROVIDER_STUB + '''
run "global_tags_on_private" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = aws_subnet.private[0].tags["Owner"] == "platform"
    error_message = "global tag Owner=platform did not propagate to a private subnet"
  }
  assert {
    condition     = aws_subnet.private[1].tags["CostCenter"] == "1234"
    error_message = "global tag CostCenter=1234 did not propagate to a private subnet"
  }
}
'''
        proc = _write_independent_suite("_indep_private_global_tags", suite)
        assert proc.returncode == 0, (
            "independent global-tags-on-private-subnet scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_global_tags_on_igw(self):
        """Independent: every global `tags` key/value appears on the planned Internet Gateway."""
        suite = PROVIDER_STUB + '''
run "global_tags_on_igw" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = aws_internet_gateway.this[0].tags["Owner"] == "platform"
    error_message = "global tag Owner=platform did not propagate to the Internet Gateway"
  }
  assert {
    condition     = aws_internet_gateway.this[0].tags["CostCenter"] == "1234"
    error_message = "global tag CostCenter=1234 did not propagate to the Internet Gateway"
  }
}
'''
        proc = _write_independent_suite("_indep_igw_tags", suite)
        assert proc.returncode == 0, (
            "independent global-tags-on-IGW scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_public_precedence_over_global(self):
        """
        Independent: when `public_subnet_tags` shares a key (Owner) with the
        global `tags` map but a different value, the planned public subnet
        carries the public-subnet-specific value, while the *private* subnet
        still carries the global value for that same key.
        """
        suite = PROVIDER_STUB + '''
run "public_precedence" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_tags = { Owner = "public-team" }
  }
  assert {
    condition     = aws_subnet.public[0].tags["Owner"] == "public-team"
    error_message = "public_subnet_tags value for Owner must override the global tags value on public subnets"
  }
  assert {
    condition     = aws_subnet.private[0].tags["Owner"] == "platform"
    error_message = "private subnet Owner must remain the global value (public override must not leak to private)"
  }
}
'''
        proc = _write_independent_suite("_indep_precedence", suite)
        assert proc.returncode == 0, (
            "independent public-precedence scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_tier_isolation(self):
        """
        Independent: a public-subnet-specific tag key (Tier) not present in the
        global map must appear on a planned public subnet and must be ABSENT
        from a planned private subnet.
        """
        suite = PROVIDER_STUB + '''
run "tier_isolation" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_tags = { Tier = "frontend" }
  }
  assert {
    condition     = aws_subnet.public[0].tags["Tier"] == "frontend"
    error_message = "public-only tag Tier=frontend must appear on the public subnet"
  }
  assert {
    condition     = !contains(keys(aws_subnet.private[0].tags), "Tier")
    error_message = "public-only tag key Tier must NOT appear on a private subnet (tier isolation)"
  }
}
'''
        proc = _write_independent_suite("_indep_isolation", suite)
        assert proc.returncode == 0, (
            "independent tier-isolation scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_name_tag_preserved_on_vpc(self):
        """
        Independent: with a global tag map that has NO `Name` key, the planned
        VPC `Name` tag stays equal to the module `name` input.
        """
        suite = PROVIDER_STUB + '''
run "vpc_name_preserved" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = aws_vpc.this[0].tags["Name"] == "tag-vpc"
    error_message = "VPC Name tag must equal the module name when global tags carry no Name key"
  }
}
'''
        proc = _write_independent_suite("_indep_vpc_name", suite)
        assert proc.returncode == 0, (
            "independent VPC-Name-preservation scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_name_tag_convention_on_public_subnet(self):
        """
        Independent: with no `Name` in global tags, a planned public subnet's
        Name tag follows "<name>-<public suffix>-<az>" derived from inputs
        (default public_subnet_suffix == "public").
        """
        suite = PROVIDER_STUB + '''
run "public_name_convention" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_suffix = "public"
  }
  assert {
    condition     = aws_subnet.public[0].tags["Name"] == "tag-vpc-public-us-east-1a"
    error_message = "public subnet[0] Name must follow <name>-<public suffix>-<az>"
  }
  assert {
    condition     = aws_subnet.public[1].tags["Name"] == "tag-vpc-public-us-east-1b"
    error_message = "public subnet[1] Name must follow the az at that index"
  }
}
'''
        proc = _write_independent_suite("_indep_public_name", suite)
        assert proc.returncode == 0, (
            "independent public-subnet-Name-convention scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_precedence_wrong_value_is_caught(self):
        """
        Independent NEGATIVE control: this asserts the OPPOSITE precedence wiring
        (global winning over the public tier map) and must FAIL, proving the
        precedence assertions above are discriminative rather than vacuous. A
        test harness that passed this would mean tags are not being merged with
        tier-specific maps taking precedence.
        """
        suite = PROVIDER_STUB + '''
run "wrong_precedence_should_fail" {
  command = plan
  variables {
''' + BASELINE + '''
    public_subnet_tags = { Owner = "public-team" }
  }
  assert {
    condition     = aws_subnet.public[0].tags["Owner"] == "platform"
    error_message = "intentionally-wrong precedence assertion"
  }
}
'''
        proc = _write_independent_suite("_indep_neg_precedence", suite)
        assert proc.returncode != 0, (
            "expected the wrong-precedence assertion to FAIL (public tier tags must "
            "win over global tags), but terraform test exited 0:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
