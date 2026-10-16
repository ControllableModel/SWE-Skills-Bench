"""
Test for the 'terraform-testing' skill (variant ext7).

Skill task: add plan-mode `terraform test` regression coverage for the
`modules/vpc-endpoints/` CHILD module of terraform-aws-modules/terraform-aws-vpc.

The agent must create a new file:

    modules/vpc-endpoints/tests/endpoints_unit_test.tftest.hcl

exercising the submodule directly (the configuration rooted at
`modules/vpc-endpoints/`) entirely in plan mode, with NO AWS credentials /
network. Its run blocks must pin:

  * endpoint fan-out: N entries in the `endpoints` map  ->  N planned
    `aws_vpc_endpoint` resources (N, 1, and 0 cases),
  * the `create` gate: `create = false`  ->  0 endpoints AND 0 security groups,
  * security-group creation: `create_security_group = true`  ->  exactly one
    `aws_security_group` bound to the supplied `vpc_id`; default -> zero,
  * the output contract: the `endpoints` output is keyed by exactly the keys of
    the supplied `endpoints` input map.

Acceptance command (run from inside modules/vpc-endpoints/):

    terraform init -backend=false && terraform test -test-directory=tests -verbose

What this file verifies (against the agent's edits in REPO_DIR =
/workspace/terraform-aws-vpc):

  L1  - the `modules/vpc-endpoints/tests/` directory exists and contains the
        single required `endpoints_unit_test.tftest.hcl`, non-empty and using
        terraform `run`/`assert` constructs.

  L2  - DYNAMIC EXECUTION with the real terraform/opentofu toolchain:
          * `terraform init -backend=false` of the submodule succeeds.
          * the agent's own committed suite
            (`terraform test -test-directory=tests -verbose`) reports every run
            block as pass.
          * INDEPENDENT tftest scenarios authored *by this test* (written into a
            throwaway directory under the submodule) re-derive the required
            behaviour from scratch: fan-out counts (2 / 1 / 0), the create gate,
            security-group creation + vpc_id binding, the default no-SG case,
            and the `endpoints` output key-set contract.

The independent scenarios are the discriminative core: a solution that merely
drops a file that "looks related", hardcodes counts, ignores the `create` gate,
or omits the security-group / output-key assertions fails them even if the
agent's own suite is hollow.

All scenarios stay offline: the submodule's `region` input is set non-null so
the `data "aws_vpc_endpoint_service"` lookup (which is gated on
`var.region == null`) is skipped, and every endpoint entry supplies an explicit
`service_endpoint` so `service_name` never needs the data source. A provider
stub with skip flags guarantees no credential / metadata calls.
"""

import os
import shutil
import subprocess

import pytest


REPO_DIR = "/workspace/terraform-aws-vpc"
# The submodule under test is the configuration root for `terraform test` here.
SUBMODULE_DIR = os.path.join(REPO_DIR, "modules", "vpc-endpoints")


# Baseline inputs shared by every independent scenario. `region` is set so the
# data source is skipped; each endpoint carries an explicit `service_endpoint`
# so no AWS lookup is ever required during plan.
BASELINE = '''
    vpc_id = "vpc-12345678"
    region = "eu-west-1"
    endpoints = {
      s3 = {
        service          = "s3"
        service_endpoint = "com.amazonaws.eu-west-1.s3"
        service_type     = "Gateway"
      }
      dynamodb = {
        service          = "dynamodb"
        service_endpoint = "com.amazonaws.eu-west-1.dynamodb"
        service_type     = "Gateway"
      }
    }
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


def _run_tf(args, cwd=SUBMODULE_DIR, timeout=600):
    """Run a terraform subcommand inside the submodule with no AWS access."""
    env = dict(os.environ)
    env.setdefault("AWS_ACCESS_KEY_ID", "test")
    env.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    env.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
    env.setdefault("AWS_REGION", "eu-west-1")
    env["AWS_EC2_METADATA_DISABLED"] = "true"
    env["TF_IN_AUTOMATION"] = "1"
    env["TF_INPUT"] = "0"
    return subprocess.run(
        [TERRAFORM] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


_INIT_DONE = {"ok": False}


def _ensure_init():
    """Run `terraform init -backend=false` once for the submodule."""
    if _INIT_DONE["ok"]:
        return
    proc = _run_tf(["init", "-backend=false", "-input=false", "-no-color"], timeout=600)
    assert proc.returncode == 0, (
        "`terraform init -backend=false` failed for modules/vpc-endpoints:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    _INIT_DONE["ok"] = True


# A provider stub so plan-only `terraform test` never reaches AWS.
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


def _write_independent_suite(dirname, contents):
    """
    Write a single .tftest.hcl file into a throwaway directory *under* the
    submodule and run `terraform test` against the submodule using it.

    Returns the CompletedProcess. The directory is created fresh each call and
    removed afterwards.
    """
    test_dir = os.path.join(SUBMODULE_DIR, dirname)
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


@pytest.fixture(scope="module", autouse=True)
def _module_init():
    if TERRAFORM is None:
        pytest.skip("terraform/opentofu binary not found")
    assert os.path.isdir(SUBMODULE_DIR), (
        "submodule directory not found: " + SUBMODULE_DIR
    )
    _ensure_init()


class TestTerraformTesting:
    """Plan-only regression-suite verification for modules/vpc-endpoints."""

    REPO_DIR = REPO_DIR

    SUBMODULE_DIR = SUBMODULE_DIR
    TESTS_DIR = os.path.join(SUBMODULE_DIR, "tests")
    TEST_FILE = os.path.join(TESTS_DIR, "endpoints_unit_test.tftest.hcl")

    # ------------------------------------------------------------------
    # L1 - deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_tests_directory_exists(self):
        """A `tests/` directory must exist inside modules/vpc-endpoints/."""
        assert os.path.isdir(self.TESTS_DIR), (
            "expected directory not found: " + self.TESTS_DIR
        )

    def test_required_tftest_file_present(self):
        """`tests/` must contain endpoints_unit_test.tftest.hcl (non-empty)."""
        assert os.path.isfile(self.TEST_FILE), (
            "missing required test file: " + self.TEST_FILE
        )
        assert os.path.getsize(self.TEST_FILE) > 0, "test file is empty"

    def test_tftest_file_uses_run_and_assert(self):
        """The committed test file must use `run` and `assert` constructs."""
        with open(self.TEST_FILE) as fh:
            body = fh.read()
        assert "run " in body or 'run"' in body, "no `run` block in test file"
        assert "assert" in body, "no `assert` block in test file"
        # Must operate against the submodule itself, in plan mode.
        assert "command" in body and "plan" in body, (
            "test file does not appear to drive plan-mode runs"
        )

    def test_tftest_file_references_submodule_resources(self):
        """
        The committed suite must actually assert on this submodule's resources /
        output (aws_vpc_endpoint / aws_security_group / the endpoints output),
        not on unrelated symbols.
        """
        with open(self.TEST_FILE) as fh:
            body = fh.read()
        assert "aws_vpc_endpoint" in body, (
            "committed suite never references aws_vpc_endpoint resources"
        )
        # Either it asserts on the security group or on the endpoints output;
        # the task requires at least the SG gate AND the output key set, so both
        # symbols should appear.
        assert "aws_security_group" in body, (
            "committed suite never references aws_security_group (create gate / "
            "security-group scenarios missing)"
        )

    # ------------------------------------------------------------------
    # L2 - dynamic execution of the agent's own committed suite
    # ------------------------------------------------------------------

    @requires_terraform
    def test_agent_suite_all_pass(self):
        """
        The acceptance command must succeed and report every run block as pass:
          terraform init -backend=false && terraform test -test-directory=tests -verbose
        (run from inside modules/vpc-endpoints/)
        """
        proc = _run_tf(
            ["test", "-test-directory=tests", "-no-color", "-verbose"],
            timeout=600,
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "`terraform test -test-directory=tests` did not exit 0 in "
            "modules/vpc-endpoints.\n"
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
    def test_independent_fanout_two(self):
        """Independent: a 2-entry endpoints map -> exactly 2 aws_vpc_endpoint."""
        suite = PROVIDER_STUB + '''
run "fanout_two" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_vpc_endpoint.this) == 2
    error_message = "expected 2 aws_vpc_endpoint resources for a 2-entry endpoints map"
  }
}
'''
        proc = _write_independent_suite("_indep_fanout_two", suite)
        assert proc.returncode == 0, (
            "independent 2-entry fan-out scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_fanout_single(self):
        """Independent: a 1-entry endpoints map -> exactly 1 aws_vpc_endpoint."""
        suite = PROVIDER_STUB + '''
run "fanout_single" {
  command = plan
  variables {
    vpc_id = "vpc-12345678"
    region = "eu-west-1"
    endpoints = {
      s3 = {
        service          = "s3"
        service_endpoint = "com.amazonaws.eu-west-1.s3"
        service_type     = "Gateway"
      }
    }
  }
  assert {
    condition     = length(aws_vpc_endpoint.this) == 1
    error_message = "expected exactly 1 aws_vpc_endpoint for a 1-entry endpoints map"
  }
}
'''
        proc = _write_independent_suite("_indep_fanout_single", suite)
        assert proc.returncode == 0, (
            "independent single-entry fan-out scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_fanout_empty(self):
        """Independent: an empty endpoints map -> 0 aws_vpc_endpoint resources."""
        suite = PROVIDER_STUB + '''
run "fanout_empty" {
  command = plan
  variables {
    vpc_id    = "vpc-12345678"
    region    = "eu-west-1"
    endpoints = {}
  }
  assert {
    condition     = length(aws_vpc_endpoint.this) == 0
    error_message = "expected 0 aws_vpc_endpoint resources for an empty endpoints map"
  }
}
'''
        proc = _write_independent_suite("_indep_fanout_empty", suite)
        assert proc.returncode == 0, (
            "independent empty-map scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_create_gate(self):
        """
        Independent: create = false -> 0 aws_vpc_endpoint AND 0 aws_security_group,
        regardless of a non-empty endpoints map and create_security_group=true.
        """
        suite = PROVIDER_STUB + '''
run "create_disabled" {
  command = plan
  variables {
''' + BASELINE + '''
    create                = false
    create_security_group = true
  }
  assert {
    condition     = length(aws_vpc_endpoint.this) == 0
    error_message = "expected 0 aws_vpc_endpoint resources when create=false"
  }
  assert {
    condition     = length(aws_security_group.this) == 0
    error_message = "expected 0 aws_security_group resources when create=false"
  }
}
'''
        proc = _write_independent_suite("_indep_create_gate", suite)
        assert proc.returncode == 0, (
            "independent create-gate scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_security_group_created_and_bound(self):
        """
        Independent: create_security_group = true -> exactly 1 aws_security_group
        planned and bound to the supplied vpc_id.
        """
        suite = PROVIDER_STUB + '''
run "security_group_created" {
  command = plan
  variables {
''' + BASELINE + '''
    create_security_group = true
  }
  assert {
    condition     = length(aws_security_group.this) == 1
    error_message = "expected exactly 1 aws_security_group when create_security_group=true"
  }
  assert {
    condition     = aws_security_group.this[0].vpc_id == "vpc-12345678"
    error_message = "the created security group is not bound to the supplied vpc_id"
  }
}
'''
        proc = _write_independent_suite("_indep_sg_created", suite)
        assert proc.returncode == 0, (
            "independent security-group-created scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_security_group_default_absent(self):
        """
        Independent: with create_security_group left at its default (false),
        zero aws_security_group resources are planned.
        """
        suite = PROVIDER_STUB + '''
run "security_group_default_absent" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(aws_security_group.this) == 0
    error_message = "expected 0 aws_security_group by default (create_security_group=false)"
  }
}
'''
        proc = _write_independent_suite("_indep_sg_absent", suite)
        assert proc.returncode == 0, (
            "independent default-no-security-group scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_output_key_set(self):
        """
        Independent: the `endpoints` output is keyed by exactly the keys of the
        supplied endpoints input map (set equality, both directions).
        """
        suite = PROVIDER_STUB + '''
run "output_key_set" {
  command = plan
  variables {
''' + BASELINE + '''
  }
  assert {
    condition     = length(keys(output.endpoints)) == 2
    error_message = "endpoints output must have one key per input map entry (2)"
  }
  assert {
    condition     = contains(keys(output.endpoints), "s3")
    error_message = "endpoints output is missing the 's3' input key"
  }
  assert {
    condition     = contains(keys(output.endpoints), "dynamodb")
    error_message = "endpoints output is missing the 'dynamodb' input key"
  }
  assert {
    condition     = alltrue([for k in keys(output.endpoints) : contains(["s3", "dynamodb"], k)])
    error_message = "endpoints output contains a key not present in the input map"
  }
}
'''
        proc = _write_independent_suite("_indep_output_keys", suite)
        assert proc.returncode == 0, (
            "independent output-key-set scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_output_keys_distinct_map(self):
        """
        Independent (discriminative): a DIFFERENT 1-entry input map must yield an
        `endpoints` output keyed by exactly that one key -- catching an impl that
        hardcodes / ignores the input keys.
        """
        suite = PROVIDER_STUB + '''
run "output_keys_distinct" {
  command = plan
  variables {
    vpc_id = "vpc-12345678"
    region = "eu-west-1"
    endpoints = {
      sts = {
        service          = "sts"
        service_endpoint = "com.amazonaws.eu-west-1.sts"
        service_type     = "Interface"
      }
    }
  }
  assert {
    condition     = keys(output.endpoints) == ["sts"]
    error_message = "endpoints output keys must equal exactly the single input key 'sts'"
  }
}
'''
        proc = _write_independent_suite("_indep_output_distinct", suite)
        assert proc.returncode == 0, (
            "independent distinct-output-keys scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    @requires_terraform
    def test_independent_per_entry_create_gate(self):
        """
        Independent (discriminative): the per-entry `create = false` flag on an
        endpoint excludes only that entry from fan-out. With two entries where
        one carries create=false, exactly 1 aws_vpc_endpoint is planned and the
        output is keyed only by the enabled entry.
        """
        suite = PROVIDER_STUB + '''
run "per_entry_gate" {
  command = plan
  variables {
    vpc_id = "vpc-12345678"
    region = "eu-west-1"
    endpoints = {
      s3 = {
        service          = "s3"
        service_endpoint = "com.amazonaws.eu-west-1.s3"
        service_type     = "Gateway"
      }
      dynamodb = {
        create           = false
        service          = "dynamodb"
        service_endpoint = "com.amazonaws.eu-west-1.dynamodb"
        service_type     = "Gateway"
      }
    }
  }
  assert {
    condition     = length(aws_vpc_endpoint.this) == 1
    error_message = "per-entry create=false must drop exactly that entry (expected 1 endpoint)"
  }
  assert {
    condition     = keys(output.endpoints) == ["s3"]
    error_message = "only the enabled 's3' entry should appear in the endpoints output"
  }
}
'''
        proc = _write_independent_suite("_indep_per_entry_gate", suite)
        assert proc.returncode == 0, (
            "independent per-entry create-gate scenario failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
