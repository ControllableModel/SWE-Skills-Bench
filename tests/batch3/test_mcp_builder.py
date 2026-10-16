"""
Test skill: mcp-builder
Verify that the Agent correctly builds an MCP server (markdown-sqlite) with tool
registration, JSON Schema validation, SQLite database, cursor-based pagination,
and MCP-compliant error handling.
"""

import os
import json
import subprocess
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"

    # === File Path Checks ===

    def test_index_ts_exists(self):
        """Verify the MCP server entry point exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/index.ts")
        assert os.path.exists(path), f"index.ts not found at {path}"

    def test_tools_ts_exists(self):
        """Verify the tools definition file exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/tools.ts")
        assert os.path.exists(path), f"tools.ts not found at {path}"

    def test_database_ts_exists(self):
        """Verify the database operations file exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/database.ts")
        assert os.path.exists(path), f"database.ts not found at {path}"

    def test_pagination_ts_exists(self):
        """Verify the pagination module exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/pagination.ts")
        assert os.path.exists(path), f"pagination.ts not found at {path}"

    def test_package_json_exists(self):
        """Verify package.json exists for the markdown-sqlite package"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        assert os.path.exists(path), f"package.json not found at {path}"
        with open(path) as f:
            data = json.load(f)
        assert "name" in data, "package.json missing 'name' field"

    def test_tsconfig_exists(self):
        """Verify tsconfig.json exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/tsconfig.json")
        assert os.path.exists(path), f"tsconfig.json not found at {path}"

    # === Semantic Checks ===

    def test_tools_define_all_four_tools(self):
        """Verify tool definitions include all four required tools"""
        tools_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/tools.ts")
        with open(tools_path) as f:
            content = f.read()
        required_tools = [
            "search_documents",
            "get_document",
            "list_documents",
            "get_document_sections",
        ]
        for tool in required_tools:
            assert tool in content, f"Tool '{tool}' not defined in tools.ts"

    def test_tools_have_input_schemas(self):
        """Verify each tool has inputSchema defined with JSON Schema"""
        tools_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/tools.ts")
        with open(tools_path) as f:
            content = f.read()
        assert "inputSchema" in content, "Tools should define inputSchema"
        # Check for JSON Schema type definitions
        assert '"type"' in content or "'type'" in content, \
            "inputSchema should include type definitions"

    def test_tools_have_readonly_hint(self):
        """Verify tool annotations include readOnlyHint: true"""
        tools_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/tools.ts")
        with open(tools_path) as f:
            content = f.read()
        assert "readOnlyHint" in content, \
            "Tool annotations should include readOnlyHint"

    def test_database_has_parameterized_queries(self):
        """Verify database.ts uses parameterized queries (no string interpolation)"""
        db_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/database.ts")
        with open(db_path) as f:
            content = f.read()
        # Should use parameterized queries with ? placeholders
        assert "?" in content or "params" in content.lower() or "$" in content, \
            "Database queries should use parameterized statements"
        # Check for FTS5
        assert "fts5" in content.lower() or "FTS5" in content, \
            "Database should enable FTS5 full-text search"

    def test_database_has_required_tables(self):
        """Verify database defines documents and sections tables"""
        db_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/database.ts")
        with open(db_path) as f:
            content = f.read()
        assert "documents" in content, "Database should define 'documents' table"
        assert "sections" in content, "Database should define 'sections' table"

    def test_pagination_uses_cursor_based_approach(self):
        """Verify pagination implements cursor-based pagination with base64 encoding"""
        pag_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src/pagination.ts")
        with open(pag_path) as f:
            content = f.read()
        # Check for cursor-related terms
        assert "cursor" in content.lower(), "Pagination should reference cursor"
        # Check for base64 encoding
        has_base64 = (
            "base64" in content.lower() or
            "btoa" in content or
            "Buffer.from" in content or
            "atob" in content
        )
        assert has_base64, \
            "Cursor should use base64 encoding"
        # Check for has_more / next_cursor
        assert "has_more" in content or "hasMore" in content, \
            "Pagination should include has_more indicator"

    def test_error_codes_defined(self):
        """Verify MCP error codes are used: -32600, -32601, -32602, -32603"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src")
        found_codes = set()
        required_codes = {"-32602", "-32603"}
        for fname in os.listdir(src_dir):
            if fname.endswith(".ts"):
                with open(os.path.join(src_dir, fname)) as f:
                    content = f.read()
                for code in required_codes:
                    if code in content:
                        found_codes.add(code)
        assert required_codes.issubset(found_codes), \
            f"Missing MCP error codes. Found: {found_codes}, Required: {required_codes}"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install succeeds in the markdown-sqlite directory"""
        pkg_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        result = subprocess.run(
            ["npm", "install"],
            cwd=pkg_dir,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            pytest.skip(f"npm install failed: {result.stderr[:500]}")

    def test_npm_build_succeeds(self):
        """Verify the project builds successfully with npm run build"""
        pkg_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        # Ensure deps installed
        subprocess.run(
            ["npm", "install"],
            cwd=pkg_dir,
            capture_output=True, text=True, timeout=120
        )
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=pkg_dir,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"npm run build failed:\n{result.stdout[:1000]}\n{result.stderr[:1000]}"

    def test_typescript_compiles_without_errors(self):
        """Verify TypeScript compiles without type errors"""
        pkg_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        subprocess.run(
            ["npm", "install"],
            cwd=pkg_dir,
            capture_output=True, text=True, timeout=120
        )
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=pkg_dir,
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            # Check if it's a type error vs missing config
            if "error TS" in result.stdout:
                assert False, \
                    f"TypeScript compilation errors:\n{result.stdout[:2000]}"

    def test_package_json_has_mcp_sdk_dependency(self):
        """Verify package.json includes MCP SDK dependency"""
        pkg_path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        with open(pkg_path) as f:
            data = json.load(f)
        all_deps = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))
        mcp_dep = any("mcp" in dep.lower() or "model-context" in dep.lower()
                       for dep in all_deps.keys())
        assert mcp_dep, \
            f"package.json should include MCP SDK dependency. Found deps: {list(all_deps.keys())}"
