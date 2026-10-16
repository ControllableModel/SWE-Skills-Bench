"""
Test for the 'terraform-testing' skill (variant ext9).

Skill task: add a plan-only `terraform test` regression file
`tests/gateways_unit_test.tftest.hcl` to the
`terraform-aws-modules/terraform-aws-vpc` root module that covers:

  * Internet Gateway gating
      - created with public subnets (exactly 1 igw, Name tag == module name),
      - not created when public_subnets is empty,
      - not created when create_igw is disabled.
  * Egress-only Internet Gateway gating
      - not created by default (IPv6 off) even when requested,
      - created when IPv6 is enabled and requested (exactly 1).
  * Public-IP-on-launch
      - default off across all public subnets,
      - enabled -> every public subnet has map_public_ip_on_launch == true.
  * Output contract
      - igw_id output defined when an IGW is planned,
      - igw_id output empty/null when no IGW is planned (no public subnets).

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the `tests/` directory exists and contains the required
        `gateways_unit_test.tftest.hcl` deliverable, non-empty and using
        terraform `run`/`assert` constructs, and runs entirely in plan mode.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass and the deliverable file is exercised in plan mode.
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) pin down the concrete behaviour
            the task requires: IGW created / not-created counts under each gate,
            the IGW Name tag, egress-only IGW gating on IPv6, the
            map_public_ip_on_launch flag across the whole public-subnet
            collection in both states, and the igw_id output presence/absence.

The independent scenarios are the discriminative core: a solution that merely
drops a file that "looks related", hardcodes a gateway count, ignores the
create_igw / public_subnets gates, or never asserts on the public-IP flag fails
them even if the agent's own suite is hollow.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the task doc).
BASELINE = '''
    name            = "gw-vpc"
    cidr            = "10.80.0.0/16"
    azs             = ["eu-west-1a", "eu-west-1b"]
    public_subnets  = ["10.80.1.0/24", "10.80.2.0/24"]
    private_subnets = ["10.80.11.0/24", "10.80.12.0/24"]
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
    """Plan-only gateway/public-IP regression suite verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    GW_FILE = os.path.join(TESTS_DIR, "gateways_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_gateways_file_present(self):
        """`tests/` must contain the required gateways_unit_test.tftest.hcl deliverable."""
        assert os.path.isfile(self.GW_FILE), (
            "required deliverable missing: tests/gateways_unit_test.tftest.hcl"
        )

    def test_gateways_file_uses_run_and_assert(self):
        """The gateways test file must be non-empty and use `run`/`assert` blocks."""
        assert os.path.isfile(self.GW_FILE), "gateways_unit_test.tftest.hcl missing"
        with open(self.GW_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "gateways test file is empty"
        assert "run " in body or "run\"" in body, "no `run` block in gateways test file"
        assert "assert" in body, "no `assert` block in gateways test file"

    def test_gateways_file_is_plan_only(self):
        """
        The deliverable must run entirely in plan mode: every `command` directive
        must be `plan` (no `apply`, which would attempt real AWS resources).
        """
        with open(self.GW_FILE) as fh:
            body = fh.read()
        # Any explicit command directive must be plan.
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("command") and "=" in stripped:
                value = stripped.split("=", 1)[1].strip()
                assert value.startswith("plan"), (
                    "gateways test must run in plan mode only; found: " + stripped
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
    def test_independent_igw_created_with_public_subnets(self):
        """
        Independent: with the baseline (public subnets present, create_igw default
        true) exactly one aws_internet_gateway is planned and its Name tag equals
        the module name.
        """
        suite = PROVIDER_STUB + '''
run "igw_created" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_internet_gateway.this) == 1
    error_message = "expected exactly 1 internet gateway with public subnets present"
  }
  assert {
    condition     = aws_internet_gateway.this[0].tags["Name"] == "gw-vpc"
    error_message = "internet gateway Name tag must equal the module name (gw-vpc)"
  }
}
'''
        proc = _write_independent_suite("_indep_igw_created", suite)
        assert proc.returncode == 0, (
            "independent igw-created scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_igw_not_created_without_public_subnets(self):
        """
        Independent: with an empty public_subnets list, zero aws_internet_gateway
        resources are planned (the IGW is gated on having public subnets).
        """
        suite = PROVIDER_STUB + '''
run "igw_no_public_subnets" {
  command = plan
  variables {
    name            = "gw-vpc"
    cidr            = "10.80.0.0/16"
    azs             = ["eu-west-1a", "eu-west-1b"]
    public_subnets  = []
    private_subnets = ["10.80.11.0/24", "10.80.12.0/24"]
  }
  assert {
    condition     = length(aws_internet_gateway.this) == 0
    error_message = "expected 0 internet gateways when public_subnets is empty"
  }
}
'''
        proc = _write_independent_suite("_indep_igw_no_public", suite)
        assert proc.returncode == 0, (
            "independent igw-without-public-subnets scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_igw_not_created_when_disabled(self):
        """
        Independent: with public subnets present but create_igw=false, zero
        aws_internet_gateway resources are planned.
        """
        suite = PROVIDER_STUB + '''
run "igw_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create_igw = false
  }
  assert {
    condition     = length(aws_internet_gateway.this) == 0
    error_message = "expected 0 internet gateways when create_igw=false"
  }
}
'''
        proc = _write_independent_suite("_indep_igw_disabled", suite)
        assert proc.returncode == 0, (
            "independent igw-disabled scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_egress_only_igw_not_created_without_ipv6(self):
        """
        Independent: with the baseline (IPv6 off) and egress-only IGW creation
        requested, zero aws_egress_only_internet_gateway resources are planned
        because the egress-only IGW is gated on enable_ipv6.
        """
        suite = PROVIDER_STUB + '''
run "egress_only_no_ipv6" {
  command = plan
  variables {
''' + BASELINE + '''
    create_egress_only_igw = true
    enable_ipv6            = false
  }
  assert {
    condition     = length(aws_egress_only_internet_gateway.this) == 0
    error_message = "expected 0 egress-only IGWs when IPv6 is disabled"
  }
}
'''
        proc = _write_independent_suite("_indep_eigw_no_ipv6", suite)
        assert proc.returncode == 0, (
            "independent egress-only-without-ipv6 scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_egress_only_igw_created_with_ipv6(self):
        """
        Independent: with IPv6 enabled, egress-only IGW creation requested, and at
        least one subnet present, exactly one aws_egress_only_internet_gateway is
        planned.
        """
        suite = PROVIDER_STUB + '''
run "egress_only_ipv6" {
  command = plan
  variables {
''' + BASELINE + '''
    create_egress_only_igw = true
    enable_ipv6            = true
  }
  assert {
    condition     = length(aws_egress_only_internet_gateway.this) == 1
    error_message = "expected exactly 1 egress-only IGW with IPv6 enabled and creation requested"
  }
}
'''
        proc = _write_independent_suite("_indep_eigw_ipv6", suite)
        assert proc.returncode == 0, (
            "independent egress-only-with-ipv6 scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_public_ip_default_off(self):
        """
        Independent: with the baseline, every planned public subnet has
        map_public_ip_on_launch == false (the default is off), expressed as a
        single assertion over the whole public-subnet collection.
        """
        suite = PROVIDER_STUB + '''
run "public_ip_default_off" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = alltrue([for s in aws_subnet.public : s.map_public_ip_on_launch == false])
    error_message = "expected map_public_ip_on_launch to default to false on all public subnets"
  }
}
'''
        proc = _write_independent_suite("_indep_pubip_off", suite)
        assert proc.returncode == 0, (
            "independent public-ip-default-off scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_public_ip_enabled(self):
        """
        Independent: with map_public_ip_on_launch=true, every planned public subnet
        has map_public_ip_on_launch == true, expressed as a single assertion over
        the whole public-subnet collection.
        """
        suite = PROVIDER_STUB + '''
run "public_ip_enabled" {
  command = plan
  variables {
''' + BASELINE + '''
    map_public_ip_on_launch = true
  }
  assert {
    condition     = alltrue([for s in aws_subnet.public : s.map_public_ip_on_launch == true])
    error_message = "expected map_public_ip_on_launch==true on every public subnet when enabled"
  }
}
'''
        proc = _write_independent_suite("_indep_pubip_on", suite)
        assert proc.returncode == 0, (
            "independent public-ip-enabled scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_igw_id_output_defined(self):
        """
        Independent: when an Internet Gateway is planned (baseline), the module's
        igw_id output is defined (not null/empty).
        """
        suite = PROVIDER_STUB + '''
run "igw_id_defined" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = output.igw_id != null
    error_message = "igw_id output must be defined when an internet gateway is planned"
  }
}
'''
        proc = _write_independent_suite("_indep_igwid_defined", suite)
        assert proc.returncode == 0, (
            "independent igw_id-defined scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_igw_id_output_empty_without_igw(self):
        """
        Independent: when no Internet Gateway is planned (empty public_subnets),
        the module's igw_id output is empty/null.
        """
        suite = PROVIDER_STUB + '''
run "igw_id_empty" {
  command = plan
  variables {
    name            = "gw-vpc"
    cidr            = "10.80.0.0/16"
    azs             = ["eu-west-1a", "eu-west-1b"]
    public_subnets  = []
    private_subnets = ["10.80.11.0/24", "10.80.12.0/24"]
  }
  assert {
    condition     = output.igw_id == null
    error_message = "igw_id output must be null/empty when no internet gateway is planned"
  }
}
'''
        proc = _write_independent_suite("_indep_igwid_empty", suite)
        assert proc.returncode == 0, (
            "independent igw_id-empty scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_naive_hardcode_rejected(self):
        """
        Independent DISCRIMINATOR: a stub that ignores the create_igw gate would
        keep planning an IGW. We assert the *contrast* in one suite: with the gate
        on (baseline) there is exactly 1 IGW, and with create_igw=false there are
        0. A naive module that always emits a fixed IGW count fails one of the two
        run blocks, so the whole `terraform test` exits non-zero here.
        """
        suite = PROVIDER_STUB + '''
run "gate_on" {
  command = plan
  variables {
''' + BASELINE + '''
    create_igw = true
  }
  assert {
    condition     = length(aws_internet_gateway.this) == 1
    error_message = "gate-on: expected exactly 1 internet gateway"
  }
}

run "gate_off" {
  command = plan
  variables {
''' + BASELINE + '''
    create_igw = false
  }
  assert {
    condition     = length(aws_internet_gateway.this) == 0
    error_message = "gate-off: expected 0 internet gateways when create_igw=false"
  }
}
'''
        proc = _write_independent_suite("_indep_gate_contrast", suite)
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "independent gate-contrast scenario failed (the IGW gate is not honored):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "pass" in combined.lower(), (
            "gate-contrast scenario produced no passing run block:\n" + combined
        )
