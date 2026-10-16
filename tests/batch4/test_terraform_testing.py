"""
Test for the 'terraform-testing' skill (variant ext4).

Skill task: add a plan-only `terraform test` regression suite to the
`terraform-aws-modules/terraform-aws-vpc` root module that covers the
**DHCP options set** (`aws_vpc_dhcp_options`) and its **VPC association**
(`aws_vpc_dhcp_options_association`):

  * gating  - disabled by default (0 DHCP options + 0 associations);
              enabled -> exactly 1 of each.
  * option values - the supplied `domain_name`, `domain_name_servers`,
              `ntp_servers`, and `netbios_node_type` flow through to the
              planned resource verbatim.
  * tag merging - the `Name` tag equals the module `name`, supplied global
              tags and DHCP-specific tags both appear, and when a key is
              supplied both globally and as a DHCP-specific tag the
              DHCP-specific value wins.

The single required deliverable is `tests/dhcp_options_unit_test.tftest.hcl`.

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the `tests/` directory exists at the repo root and contains the
        `dhcp_options_unit_test.tftest.hcl` deliverable, which is non-empty and
        uses terraform `run`/`assert` constructs targeting the DHCP resources.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` succeeds.
          * the agent's own committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass.
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under REPO_DIR) pin down the concrete behaviour
            required by the task against the *actual root module*: DHCP gating
            counts, the supplied option values, and the tag-merge precedence.

The independent scenarios are the discriminative core: a solution that merely
drops a file that "looks related", that hardcodes counts, that ignores the
supplied option values, or that gets tag-merge precedence wrong, fails them even
if the agent's own committed suite is hollow.

Native acceptance command driven (from the repo root):
    terraform init -backend=false && terraform test -test-directory=tests -verbose
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"

# Baseline inputs shared by every independent scenario (mirrors the task doc).
BASELINE = '''
    name            = "dhcp-vpc"
    cidr            = "10.40.0.0/16"
    azs             = ["ap-southeast-2a", "ap-southeast-2b"]
    private_subnets = ["10.40.11.0/24", "10.40.12.0/24"]
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
    env.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")
    env.setdefault("AWS_REGION", "ap-southeast-2")
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


def _write_independent_suite(dirname, contents, timeout=600):
    """
    Write a single .tftest.hcl file into a throwaway directory *under* REPO_DIR
    and run `terraform test` against the root module using it.

    Returns the CompletedProcess. The directory is created fresh each call and
    removed afterwards so it never pollutes the agent's own `tests/` directory.
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
            timeout=timeout,
        )
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    return proc


# A provider stub so plan-only `terraform test` never reaches AWS. Each
# independent suite embeds it via a `provider "aws"` block with skip flags.
PROVIDER_STUB = '''
provider "aws" {
  region                      = "ap-southeast-2"
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
    """Plan-only DHCP-options regression suite verification for terraform-aws-vpc."""

    REPO_DIR = REPO_DIR

    TESTS_DIR = os.path.join(REPO_DIR, "tests")
    DHCP_FILE = os.path.join(TESTS_DIR, "dhcp_options_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A top-level `tests/` directory must exist at the repo root."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_dhcp_deliverable_present(self):
        """`tests/` must contain the required dhcp_options_unit_test.tftest.hcl file."""
        assert os.path.isfile(self.DHCP_FILE), (
            "required deliverable missing: " + self.DHCP_FILE
        )

    def test_dhcp_file_uses_run_and_assert(self):
        """DHCP test file must be non-empty and use `run`/`assert` blocks."""
        assert os.path.isfile(self.DHCP_FILE), "dhcp_options_unit_test.tftest.hcl missing"
        with open(self.DHCP_FILE) as fh:
            body = fh.read()
        assert len(body.strip()) > 0, "DHCP test file is empty"
        assert "run " in body or "run\"" in body, "no `run` block in DHCP test file"
        assert "assert" in body, "no `assert` block in DHCP test file"
        assert "command = plan" in body.replace("  ", " ") or "command=plan" in body, (
            "DHCP test file must exercise plan mode (`command = plan`)"
        )

    def test_dhcp_file_targets_dhcp_resources(self):
        """
        The file must actually reference the DHCP options resource and its
        association by their module addresses (not merely look 'related').
        """
        with open(self.DHCP_FILE) as fh:
            body = fh.read()
        assert "aws_vpc_dhcp_options.this" in body, (
            "DHCP test file does not reference aws_vpc_dhcp_options.this"
        )
        assert "aws_vpc_dhcp_options_association.this" in body, (
            "DHCP test file does not reference aws_vpc_dhcp_options_association.this"
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
    def test_independent_dhcp_disabled_by_default(self):
        """
        Independent: with the baseline (DHCP options NOT enabled), zero
        aws_vpc_dhcp_options and zero aws_vpc_dhcp_options_association resources
        are planned.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_disabled_default" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_vpc_dhcp_options.this) == 0
    error_message = "expected 0 DHCP options sets when enable_dhcp_options is not set"
  }
  assert {
    condition     = length(aws_vpc_dhcp_options_association.this) == 0
    error_message = "expected 0 DHCP options associations when DHCP options are disabled"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_disabled", suite)
        assert proc.returncode == 0, (
            "independent dhcp-disabled-by-default scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_dhcp_enabled_counts(self):
        """
        Independent: enabling DHCP options yields exactly one
        aws_vpc_dhcp_options and exactly one aws_vpc_dhcp_options_association.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_enabled_counts" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options = true
  }
  assert {
    condition     = length(aws_vpc_dhcp_options.this) == 1
    error_message = "expected exactly 1 DHCP options set when enable_dhcp_options=true"
  }
  assert {
    condition     = length(aws_vpc_dhcp_options_association.this) == 1
    error_message = "expected exactly 1 DHCP options association when DHCP options are enabled"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_enabled", suite)
        assert proc.returncode == 0, (
            "independent dhcp-enabled-counts scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_domain_name_value(self):
        """
        Independent: the supplied DHCP `domain_name` flows through verbatim to
        the planned aws_vpc_dhcp_options resource.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_domain_name" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options      = true
    dhcp_options_domain_name = "example.internal"
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].domain_name == "example.internal"
    error_message = "planned DHCP options domain_name does not equal the supplied value"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_domain", suite)
        assert proc.returncode == 0, (
            "independent dhcp-domain-name scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_name_and_ntp_servers(self):
        """
        Independent: the supplied name-server and NTP-server lists equal the
        supplied lists exactly on the planned DHCP options resource.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_servers" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options              = true
    dhcp_options_domain_name_servers = ["10.40.0.2", "10.40.0.3"]
    dhcp_options_ntp_servers         = ["169.254.169.123"]
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].domain_name_servers == ["10.40.0.2", "10.40.0.3"]
    error_message = "planned DHCP domain_name_servers list does not equal the supplied list"
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].ntp_servers == ["169.254.169.123"]
    error_message = "planned DHCP ntp_servers list does not equal the supplied list"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_servers", suite)
        assert proc.returncode == 0, (
            "independent dhcp-servers scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_netbios_node_type(self):
        """
        Independent: a supplied NetBIOS node type appears verbatim on the
        planned DHCP options resource.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_netbios" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options            = true
    dhcp_options_netbios_node_type = "2"
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].netbios_node_type == "2"
    error_message = "planned DHCP netbios_node_type does not equal the supplied value"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_netbios", suite)
        assert proc.returncode == 0, (
            "independent dhcp-netbios scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_name_tag_equals_module_name(self):
        """
        Independent: the planned DHCP options resource's `Name` tag equals the
        module `name` input.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_name_tag" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options = true
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].tags["Name"] == "dhcp-vpc"
    error_message = "planned DHCP options Name tag does not equal the module name"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_name_tag", suite)
        assert proc.returncode == 0, (
            "independent dhcp-name-tag scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_global_and_specific_tags_present(self):
        """
        Independent: both supplied global tags and DHCP-specific tags (distinct
        keys) appear on the planned DHCP options resource's tag set with their
        supplied values.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_merged_tags" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options = true
    tags                = { Environment = "test" }
    dhcp_options_tags   = { Purpose = "dns" }
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].tags["Environment"] == "test"
    error_message = "global tag Environment=test did not propagate to the DHCP options resource"
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].tags["Purpose"] == "dns"
    error_message = "DHCP-specific tag Purpose=dns did not appear on the DHCP options resource"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_merged_tags", suite)
        assert proc.returncode == 0, (
            "independent dhcp-merged-tags scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_dhcp_specific_tag_precedence(self):
        """
        Independent: when the SAME tag key is supplied both globally and as a
        DHCP-specific tag, the DHCP-specific value is the one present on the
        planned resource (dhcp_options_tags wins over tags in the merge).
        """
        suite = PROVIDER_STUB + '''
run "dhcp_tag_precedence" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options = true
    tags                = { Owner = "global-owner" }
    dhcp_options_tags   = { Owner = "dhcp-owner" }
  }
  assert {
    condition     = aws_vpc_dhcp_options.this[0].tags["Owner"] == "dhcp-owner"
    error_message = "DHCP-specific tag value must win over the global tag for the same key"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_precedence", suite)
        assert proc.returncode == 0, (
            "independent dhcp-tag-precedence scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_association_binds_options(self):
        """
        Independent: the planned association references the planned DHCP options
        set (the association's dhcp_options_id is wired to the created options
        resource, confirming the binding rather than an orphan resource).
        """
        suite = PROVIDER_STUB + '''
run "dhcp_assoc_binds" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options = true
  }
  assert {
    condition     = length(aws_vpc_dhcp_options_association.this) == 1
    error_message = "expected exactly 1 DHCP options association when enabled"
  }
  assert {
    condition     = length(aws_vpc_dhcp_options.this) == length(aws_vpc_dhcp_options_association.this)
    error_message = "DHCP options and association counts must match (1:1 binding)"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_assoc", suite)
        assert proc.returncode == 0, (
            "independent dhcp-association-binding scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_disabled_with_options_still_zero(self):
        """
        Independent NEGATIVE / gating: supplying DHCP option values WITHOUT
        enabling DHCP options must still plan zero DHCP resources. This catches
        an implementation that keys creation off the presence of option values
        rather than the enable_dhcp_options flag.
        """
        suite = PROVIDER_STUB + '''
run "dhcp_values_without_enable" {
  command = plan
  variables {
''' + BASELINE + '''
    enable_dhcp_options      = false
    dhcp_options_domain_name = "example.internal"
    dhcp_options_tags        = { Purpose = "dns" }
  }
  assert {
    condition     = length(aws_vpc_dhcp_options.this) == 0
    error_message = "DHCP options must remain disabled (0) when enable_dhcp_options=false even if option values are supplied"
  }
  assert {
    condition     = length(aws_vpc_dhcp_options_association.this) == 0
    error_message = "DHCP association must remain disabled (0) when enable_dhcp_options=false"
  }
}
'''
        proc = _write_independent_suite("_indep_dhcp_gating_neg", suite)
        assert proc.returncode == 0, (
            "independent dhcp-gating-negative scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
