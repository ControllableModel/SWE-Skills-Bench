"""
Test skill: analytics-events
Verify that the Agent adds 4 collection sharing analytics events to Metabase:
created, revoked, link_copied, settings_viewed.
"""

import os
import subprocess
import re
import pytest


class TestAnalyticsEvents:
    REPO_DIR = "/workspace/metabase"

    # === File Path Checks ===

    def test_frontend_src_exists(self):
        """Verify Metabase frontend source directory exists"""
        path = os.path.join(self.REPO_DIR, "frontend/src")
        assert os.path.isdir(path), f"frontend/src not found at {path}"

    # === Semantic Checks ===

    def test_sharing_analytics_events_defined(self):
        """Verify all 4 sharing analytics event names are defined in source"""
        events = ["created", "revoked", "link_copied", "settings_viewed"]
        all_content = ""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "frontend/src")):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith((".ts", ".tsx", ".js")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "sharing" in content.lower() or "collection" in content.lower():
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        found_events = [e for e in events if e in all_content.lower()]
        assert len(found_events) >= 3, (
            f"Only found {len(found_events)} of 4 expected events: {found_events}. Missing: {set(events) - set(found_events)}"
        )

    def test_tracking_functions_exist(self):
        """Verify tracking functions are defined for sharing events"""
        all_content = ""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "frontend/src")):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith((".ts", ".tsx")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "track" in content.lower() and "shar" in content.lower():
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        has_tracking = (
            "trackEvent" in all_content
            or "track(" in all_content
            or "trackShar" in all_content
            or "useTracking" in all_content
            or "analytics" in all_content.lower()
        )
        assert has_tracking, "No tracking functions found for sharing events"

    def test_collection_sharing_modal_exists(self):
        """Verify CollectionSharingModal component exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "frontend/src")):
            if "node_modules" in root:
                continue
            for f in files:
                if "sharing" in f.lower() and "modal" in f.lower():
                    found = True
                    break
                if f.endswith((".ts", ".tsx")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "CollectionSharingModal" in content:
                            found = True
                            break
                    except (UnicodeDecodeError, PermissionError):
                        continue
            if found:
                break
        assert found, "CollectionSharingModal component not found"

    def test_events_have_typescript_types(self):
        """Verify analytics events have TypeScript type definitions"""
        all_content = ""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "frontend/src")):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith((".ts", ".tsx")):
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        if "shar" in content.lower() and ("type " in content or "interface " in content or "enum " in content):
                            all_content += content + "\n"
                    except (UnicodeDecodeError, PermissionError):
                        continue
        has_types = (
            "type" in all_content
            or "interface" in all_content
            or "enum" in all_content
        )
        assert has_types or len(all_content) > 0, (
            "No TypeScript types found for sharing analytics events"
        )

    # === Functional Checks ===

    def test_typescript_compiles(self):
        """Verify TypeScript compilation succeeds for frontend"""
        fe_dir = os.path.join(self.REPO_DIR, "frontend")
        if not os.path.exists(os.path.join(fe_dir, "package.json")):
            fe_dir = self.REPO_DIR
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--skipLibCheck"],
            cwd=fe_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # TypeScript compilation may have pre-existing errors; check our files aren't causing new ones
        if result.returncode != 0:
            sharing_errors = [
                line for line in result.stdout.splitlines()
                if "sharing" in line.lower() or "analytics" in line.lower()
            ]
            assert len(sharing_errors) == 0, (
                f"TypeScript errors in sharing/analytics files: {sharing_errors[:5]}"
            )

    def test_eslint_on_sharing_files(self):
        """Verify ESLint passes on sharing-related files"""
        sharing_files = []
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "frontend/src")):
            if "node_modules" in root:
                continue
            for f in files:
                if "sharing" in f.lower() and f.endswith((".ts", ".tsx")):
                    sharing_files.append(os.path.join(root, f))
        if not sharing_files:
            pytest.skip("No sharing files found to lint")
        result = subprocess.run(
            ["npx", "eslint"] + sharing_files[:5],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"ESLint errors: {result.stdout[:500]}"

    def test_sharing_modal_integrates_tracking(self):
        """Verify CollectionSharingModal calls tracking functions"""
        modal_content = ""
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "frontend/src")):
            if "node_modules" in root:
                continue
            for f in files:
                if "sharing" in f.lower() and "modal" in f.lower() and f.endswith((".ts", ".tsx")):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        modal_content += fh.read() + "\n"
        if not modal_content:
            pytest.skip("Sharing modal file not found")
        has_tracking_call = (
            "track" in modal_content.lower()
            and ("event" in modal_content.lower() or "analytics" in modal_content.lower())
        )
        assert has_tracking_call, (
            "CollectionSharingModal does not appear to call tracking functions"
        )
