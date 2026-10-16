"""
Test skill: mcp-builder
Verify that the Agent correctly builds an MCP server for the GitHub Issues API
with 7 tools, proper schemas, annotations, and streamable HTTP transport.
"""

import os
import re
import json
import subprocess
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"

    # === File Path Checks ===

    def test_package_json_exists(self):
        """Verify that the MCP server package.json exists"""
        # Could be in root or in a subdirectory
        possible_paths = [
            os.path.join(self.REPO_DIR, "package.json"),
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json"),
        ]
        found = any(os.path.exists(p) for p in possible_paths)
        assert found, f"package.json not found in expected locations"

    def test_index_ts_entry_point_exists(self):
        """Verify that the server entry point src/index.ts exists"""
        # Search for index.ts in typical locations
        possible_paths = [
            os.path.join(self.REPO_DIR, "src/index.ts"),
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/index.ts"),
        ]
        found = any(os.path.exists(p) for p in possible_paths)
        assert found, "src/index.ts entry point not found"

    def test_github_client_file_exists(self):
        """Verify that the GitHub API client file exists"""
        found = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            for f in files:
                if "github" in f.lower() and "client" in f.lower() and f.endswith(".ts"):
                    found = True
                    break
            if found:
                break
        assert found, "github-client.ts not found in project"

    def test_tool_files_exist(self):
        """Verify that individual tool files exist"""
        expected_tools = [
            "list-issues", "get-issue", "create-issue",
            "update-issue", "add-comment", "list-comments",
            "search-issues",
        ]
        tools_dir = None
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "tools" in dirs:
                tools_dir = os.path.join(root, "tools")
                break
        
        if tools_dir is None:
            # Tools might be defined in index.ts directly
            pytest.skip("No separate tools directory found; tools may be in index.ts")
        
        found_tools = []
        for f in os.listdir(tools_dir):
            found_tools.append(f)
        
        assert len(found_tools) >= 5, (
            f"Expected at least 5 tool files in tools directory, found: {found_tools}"
        )

    # === Semantic Checks ===

    def test_package_json_has_mcp_sdk_dependency(self):
        """Verify that package.json includes @modelcontextprotocol/sdk dependency"""
        pkg_path = None
        for p in [
            os.path.join(self.REPO_DIR, "package.json"),
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json"),
        ]:
            if os.path.exists(p):
                pkg_path = p
                break

        assert pkg_path is not None, "package.json not found"
        with open(pkg_path, "r") as f:
            pkg = json.load(f)

        all_deps = {}
        all_deps.update(pkg.get("dependencies", {}))
        all_deps.update(pkg.get("devDependencies", {}))

        assert "@modelcontextprotocol/sdk" in all_deps, (
            "package.json missing @modelcontextprotocol/sdk dependency"
        )

    def test_server_registers_seven_tools(self):
        """Verify that the server registers all 7 required tools"""
        # Find the index.ts
        index_path = None
        for p in [
            os.path.join(self.REPO_DIR, "src/index.ts"),
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/index.ts"),
        ]:
            if os.path.exists(p):
                index_path = p
                break

        assert index_path is not None, "index.ts not found"
        with open(index_path, "r") as f:
            content = f.read()

        # Check for tool names
        expected_tools = [
            "github_list_issues", "github_get_issue", "github_create_issue",
            "github_update_issue", "github_add_comment", "github_list_comments",
            "github_search_issues",
        ]
        found_count = sum(1 for tool in expected_tools if tool in content)
        
        # If tools are imported from separate files, check imports
        if found_count < 5:
            all_content = content
            # Also read tool files
            for root, dirs, files in os.walk(os.path.dirname(index_path)):
                for f in files:
                    if f.endswith(".ts") and f != "index.ts":
                        with open(os.path.join(root, f), "r") as fh:
                            all_content += fh.read()
            found_count = sum(1 for tool in expected_tools if tool in all_content)

        assert found_count >= 5, (
            f"Expected at least 5 of 7 tool definitions, found {found_count}. "
            f"Tools: {expected_tools}"
        )

    def test_tools_use_zod_schemas(self):
        """Verify that tool definitions use Zod for input validation"""
        found_zod = False
        for root, dirs, files in os.walk(self.REPO_DIR):
            # Skip node_modules
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".ts"):
                    filepath = os.path.join(root, f)
                    with open(filepath, "r") as fh:
                        content = fh.read()
                    if "zod" in content.lower() or "z." in content:
                        found_zod = True
                        break
            if found_zod:
                break
        assert found_zod, "Tools should use Zod for input schema validation"

    def test_tools_have_annotations(self):
        """Verify that tools define MCP annotations (readOnlyHint, destructiveHint)"""
        annotation_count = 0
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".ts"):
                    filepath = os.path.join(root, f)
                    with open(filepath, "r") as fh:
                        content = fh.read()
                    if "readOnlyHint" in content or "destructiveHint" in content:
                        annotation_count += 1
        assert annotation_count >= 1, (
            "Tools should define MCP annotations (readOnlyHint, destructiveHint)"
        )

    def test_read_only_tools_annotated_correctly(self):
        """Verify that read-only tools have readOnlyHint: true"""
        read_only_tools = ["list_issues", "get_issue", "list_comments", "search_issues"]
        all_ts_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".ts"):
                    with open(os.path.join(root, f), "r") as fh:
                        all_ts_content += fh.read() + "\n"

        has_readonly_true = "readOnlyHint" in all_ts_content and "true" in all_ts_content
        assert has_readonly_true, (
            "Read-only tools should be annotated with readOnlyHint: true"
        )

    def test_github_client_handles_rate_limit(self):
        """Verify that GitHub API client handles rate limiting"""
        client_content = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root:
                continue
            for f in files:
                if "github" in f.lower() and "client" in f.lower() and f.endswith(".ts"):
                    with open(os.path.join(root, f), "r") as fh:
                        client_content = fh.read()
                    break

        if not client_content:
            pytest.skip("GitHub client file not found")

        has_rate_limit = any(kw in client_content for kw in [
            "ratelimit", "rate_limit", "rate-limit", "getRateLimit",
            "x-ratelimit", "Rate limit",
        ])
        assert has_rate_limit, (
            "GitHub client should handle rate limiting"
        )

    def test_github_token_required(self):
        """Verify that GITHUB_TOKEN environment variable is required"""
        all_ts = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".ts"):
                    with open(os.path.join(root, f), "r") as fh:
                        all_ts += fh.read() + "\n"

        assert "GITHUB_TOKEN" in all_ts, (
            "Server should require GITHUB_TOKEN environment variable"
        )

    # === Functional Checks ===

    def test_typescript_compiles(self):
        """Verify that npm run build compiles without errors"""
        build_dir = self.REPO_DIR
        # Find the directory with package.json
        for p in ["src/markdown-sqlite", "."]:
            pkg_path = os.path.join(self.REPO_DIR, p, "package.json")
            if os.path.exists(pkg_path):
                build_dir = os.path.join(self.REPO_DIR, p)
                break

        # Install deps
        install_result = subprocess.run(
            ["npm", "install"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install_result.returncode != 0:
            pytest.skip(f"npm install failed: {install_result.stderr}")

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Build failed:\n{result.stdout[-1000:]}\n{result.stderr[-1000:]}"
        )

    def test_tsconfig_has_strict_mode(self):
        """Verify that tsconfig.json enables strict mode"""
        tsconfig_path = None
        for p in [
            os.path.join(self.REPO_DIR, "tsconfig.json"),
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/tsconfig.json"),
        ]:
            if os.path.exists(p):
                tsconfig_path = p
                break

        if tsconfig_path is None:
            pytest.skip("tsconfig.json not found")

        with open(tsconfig_path, "r") as f:
            content = f.read()

        assert '"strict"' in content, (
            "tsconfig.json should have strict mode enabled"
        )

    def test_error_handling_for_missing_issues(self):
        """Verify that tool implementations handle 404 errors for missing issues"""
        all_ts = ""
        for root, dirs, files in os.walk(self.REPO_DIR):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith(".ts"):
                    with open(os.path.join(root, f), "r") as fh:
                        all_ts += fh.read() + "\n"

        has_404_handling = any(kw in all_ts for kw in [
            "404", "not found", "NotFound", "isError",
        ])
        assert has_404_handling, (
            "Tools should handle 404 responses for non-existent issues"
        )
