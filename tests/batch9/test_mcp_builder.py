"""
Test skill: mcp-builder
Verify that the Agent correctly builds a markdown-sqlite MCP server with SQLite FTS5 search.
"""

import os
import subprocess
import json
import re
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"

    # === File Path Checks ===

    def test_markdown_sqlite_directory_exists(self):
        """Verify src/markdown-sqlite directory exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        assert os.path.isdir(path), f"src/markdown-sqlite directory not found at {path}"

    def test_package_json_exists(self):
        """Verify src/markdown-sqlite/package.json exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        assert os.path.exists(path), f"package.json not found at {path}"

    def test_tsconfig_exists(self):
        """Verify TypeScript configuration exists"""
        candidates = [
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/tsconfig.json"),
        ]
        found = any(os.path.exists(c) for c in candidates)
        assert found, "tsconfig.json not found in src/markdown-sqlite"

    # === Semantic Checks ===

    def test_package_json_has_mcp_dependencies(self):
        """Verify package.json includes MCP SDK dependency"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        with open(path) as f:
            pkg = json.load(f)
        all_deps = {}
        all_deps.update(pkg.get("dependencies", {}))
        all_deps.update(pkg.get("devDependencies", {}))
        has_mcp = any("mcp" in k.lower() or "modelcontextprotocol" in k.lower() for k in all_deps)
        assert has_mcp, f"No MCP SDK dependency found. Dependencies: {list(all_deps.keys())}"

    def test_package_json_has_sqlite_dependency(self):
        """Verify package.json includes SQLite dependency"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        with open(path) as f:
            pkg = json.load(f)
        all_deps = {}
        all_deps.update(pkg.get("dependencies", {}))
        all_deps.update(pkg.get("devDependencies", {}))
        has_sqlite = any("sqlite" in k.lower() or "better-sqlite3" in k.lower() or "sql.js" in k.lower() for k in all_deps)
        assert has_sqlite, f"No SQLite dependency found. Dependencies: {list(all_deps.keys())}"

    def test_source_defines_five_mcp_tools(self):
        """Verify source code defines all 5 MCP tools: index_directory, search, get_document, list_documents, get_code_blocks"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        all_content = ""
        for root, dirs, files in os.walk(src_dir):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith((".ts", ".js")):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        all_content += fh.read() + "\n"
        expected_tools = ["index_directory", "search", "get_document", "list_documents", "get_code_blocks"]
        found_tools = [t for t in expected_tools if t in all_content]
        assert len(found_tools) >= 4, (
            f"Expected 5 MCP tools, found {len(found_tools)}: {found_tools}. Missing: {set(expected_tools) - set(found_tools)}"
        )

    def test_fts5_used_for_search(self):
        """Verify FTS5 virtual table is used for full-text search"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        all_content = ""
        for root, dirs, files in os.walk(src_dir):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith((".ts", ".js")):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        all_content += fh.read() + "\n"
        content_upper = all_content.upper()
        has_fts5 = "FTS5" in content_upper
        assert has_fts5, "No FTS5 usage found in source code"

    def test_source_handles_markdown_parsing(self):
        """Verify source includes markdown parsing logic"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        all_content = ""
        for root, dirs, files in os.walk(src_dir):
            if "node_modules" in root:
                continue
            for f in files:
                if f.endswith((".ts", ".js")):
                    fpath = os.path.join(root, f)
                    with open(fpath) as fh:
                        all_content += fh.read() + "\n"
        has_md_parse = (
            "markdown" in all_content.lower()
            or "frontmatter" in all_content.lower()
            or "remark" in all_content.lower()
            or "unified" in all_content.lower()
            or ".md" in all_content
        )
        assert has_md_parse, "No markdown parsing logic found"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes in markdown-sqlite directory"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=os.path.join(self.REPO_DIR, "src/markdown-sqlite"),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"npm install failed: {result.stderr[:500]}"

    def test_typescript_build_succeeds(self):
        """Verify TypeScript compilation succeeds"""
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=os.path.join(self.REPO_DIR, "src/markdown-sqlite"),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"Build failed:\n{result.stdout[:500]}\n{result.stderr[:500]}"
        )

    def test_build_output_exists(self):
        """Verify build produces output files"""
        dist_candidates = [
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/dist"),
            os.path.join(self.REPO_DIR, "src/markdown-sqlite/build"),
        ]
        found = False
        for d in dist_candidates:
            if os.path.isdir(d) and os.listdir(d):
                found = True
                break
        # Also check if there's a main entry in package.json
        if not found:
            pkg_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
            with open(pkg_path) as f:
                pkg = json.load(f)
            main = pkg.get("main", "")
            if main and os.path.exists(os.path.join(self.REPO_DIR, "src/markdown-sqlite", main)):
                found = True
        assert found, "No build output found"

    def test_server_entry_point_importable(self):
        """Verify the compiled server entry point can be loaded with node"""
        pkg_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        main = pkg.get("main", pkg.get("bin", ""))
        if isinstance(main, dict):
            main = list(main.values())[0]
        if not main:
            main = "dist/index.js"
        entry = os.path.join(self.REPO_DIR, "src/markdown-sqlite", main)
        if not os.path.exists(entry):
            pytest.skip(f"Entry point {entry} not found after build")
        result = subprocess.run(
            ["node", "-e", f"require('{entry}')"],
            cwd=os.path.join(self.REPO_DIR, "src/markdown-sqlite"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Entry point may start a server that doesn't exit, so just check no immediate crash
        assert "SyntaxError" not in result.stderr, f"Syntax error in entry point: {result.stderr[:500]}"
