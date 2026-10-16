"""
Test skill: mcp-builder
Verify that the MCP server for Markdown-to-SQLite conversion has been correctly
built, including package structure, TypeScript compilation, tool definitions,
database schema, and input validation.
"""

import os
import re
import json
import subprocess
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"
    PROJECT_DIR = "/workspace/servers/src/markdown-sqlite"

    # === File Path Checks ===

    def test_package_json_exists(self):
        """Verify package.json exists in the markdown-sqlite project"""
        filepath = os.path.join(self.PROJECT_DIR, "package.json")
        assert os.path.exists(filepath), f"package.json not found at {filepath}"

    def test_tsconfig_exists(self):
        """Verify tsconfig.json exists"""
        filepath = os.path.join(self.PROJECT_DIR, "tsconfig.json")
        assert os.path.exists(filepath), f"tsconfig.json not found at {filepath}"

    def test_index_ts_exists(self):
        """Verify src/index.ts entry point exists"""
        filepath = os.path.join(self.PROJECT_DIR, "src/index.ts")
        assert os.path.exists(filepath), f"src/index.ts not found at {filepath}"

    def test_db_module_exists(self):
        """Verify src/db.ts database module exists"""
        filepath = os.path.join(self.PROJECT_DIR, "src/db.ts")
        assert os.path.exists(filepath), f"src/db.ts not found at {filepath}"

    def test_tool_files_exist(self):
        """Verify all three tool implementation files exist"""
        tool_files = [
            "src/tools/ingest.ts",
            "src/tools/query.ts",
            "src/tools/list.ts",
        ]
        for rel in tool_files:
            filepath = os.path.join(self.PROJECT_DIR, rel)
            assert os.path.exists(filepath), f"Tool file not found at {filepath}"

    # === Semantic Checks ===

    def test_package_json_has_required_fields(self):
        """Verify package.json has bin entry, build script, and required dependencies"""
        filepath = os.path.join(self.PROJECT_DIR, "package.json")
        with open(filepath) as f:
            pkg = json.load(f)
        assert "bin" in pkg, "package.json should have a 'bin' field for the entry point"
        assert "scripts" in pkg, "package.json should have 'scripts'"
        assert "build" in pkg.get("scripts", {}), "package.json should have a 'build' script"
        # Check dependencies
        all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        has_sqlite = any("sqlite" in dep.lower() for dep in all_deps)
        assert has_sqlite, "package.json should depend on a SQLite library (e.g., better-sqlite3)"
        has_zod = "zod" in all_deps
        assert has_zod, "package.json should depend on 'zod' for input validation"

    def test_tsconfig_is_valid_json(self):
        """Verify tsconfig.json is valid JSON and has basic TypeScript config"""
        filepath = os.path.join(self.PROJECT_DIR, "tsconfig.json")
        with open(filepath) as f:
            content = f.read()
        # Remove comments for JSON parsing (TypeScript configs allow comments)
        import re
        cleaned = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
        config = json.loads(cleaned)
        assert "compilerOptions" in config or "extends" in config, \
            "tsconfig.json should have compilerOptions or extends"

    def test_index_ts_registers_three_tools(self):
        """Verify index.ts registers ingest_markdown, query_content, and list_documents tools"""
        filepath = os.path.join(self.PROJECT_DIR, "src/index.ts")
        with open(filepath) as f:
            content = f.read()
        expected_tools = ["ingest_markdown", "query_content", "list_documents"]
        for tool in expected_tools:
            assert tool in content, \
                f"index.ts should register tool '{tool}'"

    def test_db_module_defines_schema(self):
        """Verify db.ts creates documents and sections tables with proper schema"""
        filepath = os.path.join(self.PROJECT_DIR, "src/db.ts")
        with open(filepath) as f:
            content = f.read()
        assert "documents" in content, "db.ts should define 'documents' table"
        assert "sections" in content, "db.ts should define 'sections' table"
        # Verify key columns
        assert "document_id" in content or "documentId" in content, \
            "sections table should have a foreign key to documents"
        assert "heading" in content, "sections table should have 'heading' column"
        assert "body" in content, "sections table should have 'body' column"

    def test_ingest_tool_handles_file_size_limit(self):
        """Verify ingest tool implements 1MB file size limit check"""
        filepath = os.path.join(self.PROJECT_DIR, "src/tools/ingest.ts")
        with open(filepath) as f:
            content = f.read()
        # Should check file size (1MB = 1048576 bytes or reference to 1MB)
        has_size_check = ("1048576" in content or "1024 * 1024" in content or
                          "1_048_576" in content or "1mb" in content.lower() or
                          "1 mb" in content.lower() or "size" in content.lower())
        assert has_size_check, \
            "Ingest tool should enforce a 1MB file size limit"

    def test_query_tool_uses_case_insensitive_search(self):
        """Verify query tool implements case-insensitive search with LIKE"""
        filepath = os.path.join(self.PROJECT_DIR, "src/tools/query.ts")
        with open(filepath) as f:
            content = f.read()
        has_like = ("LIKE" in content or "like" in content)
        assert has_like, "query_content tool should use SQL LIKE for case-insensitive search"
        has_limit = ("limit" in content.lower())
        assert has_limit, "query_content tool should support a limit parameter"

    def test_ingest_tool_annotated_non_readonly(self):
        """Verify ingest_markdown is annotated as non-read-only and non-idempotent"""
        filepath = os.path.join(self.PROJECT_DIR, "src/tools/ingest.ts")
        with open(filepath) as f:
            content = f.read()
        has_annotation = ("readOnly" in content or "read_only" in content or
                          "idempotent" in content or "annotations" in content)
        assert has_annotation, \
            "ingest_markdown should have tool annotations (readOnly: false)"

    def test_tools_use_zod_validation(self):
        """Verify tool inputs are validated with Zod schemas"""
        tool_files = [
            "src/tools/ingest.ts",
            "src/tools/query.ts",
            "src/tools/list.ts",
        ]
        for rel in tool_files:
            filepath = os.path.join(self.PROJECT_DIR, rel)
            with open(filepath) as f:
                content = f.read()
            has_zod = ("z." in content or "zod" in content.lower() or "Zod" in content)
            assert has_zod, \
                f"{rel} should use Zod for input validation"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install succeeds for the markdown-sqlite project"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.PROJECT_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"npm install failed: {result.stderr[:1000]}"

    def test_npm_build_succeeds(self):
        """Verify npm run build compiles TypeScript without errors"""
        subprocess.run(["npm", "install"], cwd=self.PROJECT_DIR,
                       capture_output=True, text=True, timeout=120)
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.PROJECT_DIR,
            capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, \
            f"npm run build failed:\n{result.stdout[-1000:]}\n{result.stderr[-1000:]}"

    def test_build_produces_dist_output(self):
        """Verify that build produces compiled JavaScript output files"""
        subprocess.run(["npm", "install"], cwd=self.PROJECT_DIR,
                       capture_output=True, text=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.PROJECT_DIR,
                       capture_output=True, text=True, timeout=120)
        # Check for dist or build output directory
        dist_path = os.path.join(self.PROJECT_DIR, "dist")
        build_path = os.path.join(self.PROJECT_DIR, "build")
        has_output = os.path.isdir(dist_path) or os.path.isdir(build_path)
        assert has_output, \
            "Build should produce a dist/ or build/ directory with compiled output"

    def test_compiled_entry_point_exists(self):
        """Verify the compiled entry point file exists after build"""
        subprocess.run(["npm", "install"], cwd=self.PROJECT_DIR,
                       capture_output=True, text=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.PROJECT_DIR,
                       capture_output=True, text=True, timeout=120)
        # Read package.json to find bin entry
        pkg_path = os.path.join(self.PROJECT_DIR, "package.json")
        with open(pkg_path) as f:
            pkg = json.load(f)
        bin_entry = pkg.get("bin", {})
        if isinstance(bin_entry, str):
            entry_path = os.path.join(self.PROJECT_DIR, bin_entry)
        elif isinstance(bin_entry, dict):
            entry_path = os.path.join(self.PROJECT_DIR, list(bin_entry.values())[0])
        else:
            pytest.skip("No bin entry found in package.json")
            return
        assert os.path.exists(entry_path), \
            f"Compiled entry point not found at {entry_path}"
