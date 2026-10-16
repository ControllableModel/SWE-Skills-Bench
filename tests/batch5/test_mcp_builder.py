"""
Test skill: mcp-builder
Verify that the Agent correctly builds an MCP Server for Markdown-to-SQLite
operations in the modelcontextprotocol/servers repository.
"""

import os
import re
import json
import subprocess
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"
    PKG_DIR = "src/markdown-sqlite"

    def _pkg_path(self, rel_path=""):
        return os.path.join(self.REPO_DIR, self.PKG_DIR, rel_path)

    def _read_file(self, rel_path):
        filepath = self._pkg_path(rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_package_json_exists(self):
        """Verify package.json exists in src/markdown-sqlite"""
        assert os.path.exists(self._pkg_path("package.json")), \
            "package.json not found in src/markdown-sqlite"

    def test_tsconfig_exists(self):
        """Verify tsconfig.json exists in src/markdown-sqlite"""
        assert os.path.exists(self._pkg_path("tsconfig.json")), \
            "tsconfig.json not found in src/markdown-sqlite"

    def test_index_entry_point_exists(self):
        """Verify src/index.ts entry point exists"""
        assert os.path.exists(self._pkg_path("src/index.ts")), \
            "Entry point src/index.ts not found"

    def test_tool_files_exist(self):
        """Verify all three tool files exist"""
        tools = ["ingest", "query", "list-tables"]
        alt_names = {
            "ingest": ["ingest.ts", "ingest_markdown.ts", "ingestMarkdown.ts"],
            "query": ["query.ts", "query_db.ts", "queryDb.ts"],
            "list-tables": ["list-tables.ts", "list_tables.ts", "listTables.ts"],
        }
        for tool in tools:
            found = False
            for name in alt_names[tool]:
                if os.path.exists(self._pkg_path(f"src/tools/{name}")):
                    found = True
                    break
            if not found:
                # Check src/ directly
                for name in alt_names[tool]:
                    if os.path.exists(self._pkg_path(f"src/{name}")):
                        found = True
                        break
            assert found, f"Tool file for '{tool}' not found in src/tools/ or src/"

    def test_db_helper_exists(self):
        """Verify database helper file exists"""
        candidates = [
            self._pkg_path("src/db.ts"),
            self._pkg_path("src/database.ts"),
            self._pkg_path("src/sqlite.ts"),
        ]
        assert any(os.path.exists(p) for p in candidates), \
            "Database helper file (db.ts/database.ts/sqlite.ts) not found"

    # === Semantic Checks ===

    def test_package_json_has_required_dependencies(self):
        """Verify package.json includes MCP SDK and SQLite dependencies"""
        content = json.loads(self._read_file("package.json"))
        all_deps = {}
        for key in ["dependencies", "devDependencies"]:
            all_deps.update(content.get(key, {}))

        has_mcp = any("modelcontextprotocol" in dep or "mcp" in dep.lower()
                       for dep in all_deps)
        has_sqlite = any("sqlite" in dep.lower() for dep in all_deps)
        assert has_mcp, "package.json missing MCP SDK dependency"
        assert has_sqlite, "package.json missing SQLite dependency"

    def test_package_json_has_build_script(self):
        """Verify package.json has a build script"""
        content = json.loads(self._read_file("package.json"))
        scripts = content.get("scripts", {})
        assert "build" in scripts, "package.json missing 'build' script"

    def test_index_registers_three_tools(self):
        """Verify index.ts registers exactly three tools"""
        content = self._read_file("src/index.ts")
        # Tools should be registered via server.tool() or similar
        tool_registrations = re.findall(
            r'(tool|addTool|registerTool|setRequestHandler)\s*\(', content
        )
        # Also check for tool name strings
        tool_names = re.findall(
            r'["\']?(ingest_markdown|query_db|list_tables)["\']?', content
        )
        total_indicators = len(set(tool_names))
        if total_indicators < 3:
            # Check imports from tool files
            tool_imports = re.findall(r'from\s+["\'].*?tools/', content)
            total_indicators = max(total_indicators, len(tool_imports))
        assert total_indicators >= 3, \
            f"Expected 3 tool registrations, found indicators: {total_indicators}"

    def test_documents_table_schema_defined(self):
        """Verify documents table schema is defined with required columns"""
        # Look across all source files for the schema definition
        all_content = ""
        for root, dirs, files in os.walk(self._pkg_path("src")):
            for f in files:
                if f.endswith(".ts"):
                    with open(os.path.join(root, f)) as fp:
                        all_content += fp.read()

        required_cols = ["element_type", "content", "position"]
        for col in required_cols:
            assert col in all_content, \
                f"Documents table schema missing column: {col}"

    def test_query_tool_rejects_write_operations(self):
        """Verify query tool has logic to reject INSERT/UPDATE/DELETE/DROP"""
        all_content = ""
        for root, dirs, files in os.walk(self._pkg_path("src")):
            for f in files:
                if f.endswith(".ts"):
                    with open(os.path.join(root, f)) as fp:
                        all_content += fp.read()

        write_rejection = bool(re.search(
            r'(INSERT|UPDATE|DELETE|DROP|write|read.only|readonly)',
            all_content,
            re.IGNORECASE,
        ))
        assert write_rejection, \
            "query_db tool missing write operation rejection logic"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes in the package directory"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self._pkg_path(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, \
            f"npm install failed: {result.stderr[:500]}"

    def test_npm_build_succeeds(self):
        """Verify npm run build compiles TypeScript without errors"""
        subprocess.run(
            ["npm", "install"], cwd=self._pkg_path(),
            capture_output=True, text=True, timeout=300,
        )
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self._pkg_path(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, \
            f"npm run build failed: {result.stderr[:500]}\n{result.stdout[:500]}"

    def test_typescript_compiles_without_errors(self):
        """Verify TypeScript strict compilation passes"""
        subprocess.run(
            ["npm", "install"], cwd=self._pkg_path(),
            capture_output=True, text=True, timeout=300,
        )
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=self._pkg_path(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, \
            f"TypeScript compilation errors: {result.stdout[:500]}"
