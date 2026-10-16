"""
Test skill: linkerd-patterns
Verify that the Agent creates ServiceProfile, TrafficSplit, AuthorizationPolicy generators,
and canary controller for Linkerd (Go).
"""

import os
import re
import subprocess
import pytest


class TestLinkerdPatterns:
    REPO_DIR = "/workspace/linkerd2"

    # === File Path Checks ===

    def test_linkerd_generator_files_exist(self):
        """Verify Linkerd policy generator files exist"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("profile" in f.lower() or "traffic" in f.lower() or "canary" in f.lower() or "authori" in f.lower()):
                    found = True
                    break
            if found:
                break
        assert found, "Linkerd generator files not found"

    # === Semantic Checks ===

    def test_service_profile_generator_defined(self):
        """Verify ServiceProfile generator is implemented"""
        content = self._find_content()
        has_sp = "ServiceProfile" in content
        assert has_sp, "ServiceProfile generator not found"

    def test_traffic_split_generator_defined(self):
        """Verify TrafficSplit generator is implemented"""
        content = self._find_content()
        has_ts = "TrafficSplit" in content or "trafficsplit" in content.lower()
        assert has_ts, "TrafficSplit generator not found"

    def test_authorization_policy_generator_defined(self):
        """Verify AuthorizationPolicy generator is implemented"""
        content = self._find_content()
        has_auth = "AuthorizationPolicy" in content or "authorization" in content.lower()
        assert has_auth, "AuthorizationPolicy generator not found"

    def test_canary_controller_defined(self):
        """Verify canary controller is implemented"""
        content = self._find_content()
        content_lower = content.lower()
        has_canary = "canary" in content_lower
        assert has_canary, "Canary controller not found"

    def test_linkerd_api_types_used(self):
        """Verify Linkerd API types are used"""
        content = self._find_content()
        has_api = (
            "linkerd" in content.lower()
            or "serviceprofile" in content.lower()
            or "smi" in content.lower()
        )
        assert has_api, "Linkerd API types not used"

    # === Functional Checks ===

    def test_go_files_have_package(self):
        """Verify Go files have proper package declarations"""
        go_files = self._find_go_files()
        assert len(go_files) > 0, "No Linkerd generator Go files found"
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            assert "package " in content[:200], f"{gf} missing package declaration"

    def test_go_files_balanced_braces(self):
        """Verify Go files have balanced braces"""
        go_files = self._find_go_files()
        for gf in go_files:
            with open(gf) as fh:
                content = fh.read()
            cleaned = re.sub(r'"[^"]*"', '', content)
            cleaned = re.sub(r'//[^\n]*', '', cleaned)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            opens = cleaned.count('{')
            closes = cleaned.count('}')
            assert opens == closes, f"Unbalanced braces in {gf}: {opens} vs {closes}"

    def test_go_build(self):
        """Verify project builds"""
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            related_errors = [
                line for line in result.stderr.splitlines()
                if any(kw in line.lower() for kw in ["profile", "traffic", "canary", "authori"])
            ]
            assert len(related_errors) == 0, f"Build errors: {related_errors[:5]}"

    def test_canary_has_weight_management(self):
        """Verify canary controller manages traffic weights"""
        content = self._find_content()
        content_lower = content.lower()
        has_weight = "weight" in content_lower or "percentage" in content_lower or "ratio" in content_lower
        assert has_weight, "Canary controller missing weight management"

    def _find_content(self):
        all_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go"):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if any(kw in content for kw in ["ServiceProfile", "TrafficSplit", "AuthorizationPolicy", "canary", "Canary"]):
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        return all_content

    def _find_go_files(self):
        go_files = []
        for root, dirs, files in os.walk(self.REPO_DIR):
            if ".git" in root or "vendor" in root:
                continue
            for f in files:
                if f.endswith(".go") and ("profile" in f.lower() or "traffic" in f.lower() or "canary" in f.lower() or "authori" in f.lower()):
                    go_files.append(os.path.join(root, f))
        return go_files
