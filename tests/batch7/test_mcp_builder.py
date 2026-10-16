"""
Test skill: mcp-builder
Verify that the Agent correctly builds an MCP server for SQLite-backed
Markdown note management with CRUD tools and full-text search.
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
        """Verify package.json exists in src/markdown-sqlite/"""
        fpath = os.path.join(self.PROJECT_DIR, "package.json")
        assert os.path.isfile(fpath), f"package.json not found at {fpath}"

    def test_tsconfig_exists(self):
        """Verify tsconfig.json exists in src/markdown-sqlite/"""
        fpath = os.path.join(self.PROJECT_DIR, "tsconfig.json")
        assert os.path.isfile(fpath), f"tsconfig.json not found at {fpath}"

    def test_index_ts_exists(self):
        """Verify src/index.ts entry point exists"""
        fpath = os.path.join(self.PROJECT_DIR, "src/index.ts")
        assert os.path.isfile(fpath), f"src/index.ts not found at {fpath}"

    def test_database_ts_exists(self):
        """Verify src/database.ts database layer exists"""
        fpath = os.path.join(self.PROJECT_DIR, "src/database.ts")
        assert os.path.isfile(fpath), f"src/database.ts not found at {fpath}"

    def test_types_ts_exists(self):
        """Verify src/types.ts type definitions exist"""
        fpath = os.path.join(self.PROJECT_DIR, "src/types.ts")
        assert os.path.isfile(fpath), f"src/types.ts not found at {fpath}"

    def test_readme_exists(self):
        """Verify README.md documentation exists"""
        fpath = os.path.join(self.PROJECT_DIR, "README.md")
        assert os.path.isfile(fpath), f"README.md not found at {fpath}"

    # === Semantic Checks ===

    def test_package_json_has_required_dependencies(self):
        """Verify package.json includes MCP SDK and better-sqlite3 dependencies"""
        fpath = os.path.join(self.PROJECT_DIR, "package.json")
        with open(fpath, "r") as f:
            pkg = json.load(f)
        all_deps = {}
        all_deps.update(pkg.get("dependencies", {}))
        all_deps.update(pkg.get("devDependencies", {}))
        has_mcp_sdk = any("modelcontextprotocol" in k for k in all_deps)
        has_sqlite = any("sqlite" in k.lower() for k in all_deps)
        assert has_mcp_sdk, f"package.json missing @modelcontextprotocol/sdk dependency. Deps: {list(all_deps.keys())}"
        assert has_sqlite, f"package.json missing sqlite3 dependency. Deps: {list(all_deps.keys())}"

    def test_package_json_has_build_script(self):
        """Verify package.json has a build script"""
        fpath = os.path.join(self.PROJECT_DIR, "package.json")
        with open(fpath, "r") as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        assert "build" in scripts, f"package.json missing 'build' script. Scripts: {list(scripts.keys())}"

    def test_index_ts_defines_five_tools(self):
        """Verify index.ts defines all five required tools"""
        fpath = os.path.join(self.PROJECT_DIR, "src/index.ts")
        with open(fpath, "r") as f:
            content = f.read()
        required_tools = ["create_note", "get_note", "search_notes", "update_note", "delete_note"]
        for tool in required_tools:
            assert tool in content, f"index.ts missing tool definition: '{tool}'"

    def test_database_ts_has_fts5_support(self):
        """Verify database.ts creates an FTS5 virtual table for search"""
        fpath = os.path.join(self.PROJECT_DIR, "src/database.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_fts5 = bool(re.search(r'(FTS5|fts5|VIRTUAL\s+TABLE|virtual\s+table)', content, re.IGNORECASE))
        assert has_fts5, "database.ts should create an FTS5 virtual table for search"

    def test_database_ts_has_notes_schema(self):
        """Verify database.ts defines notes table with required columns"""
        fpath = os.path.join(self.PROJECT_DIR, "src/database.ts")
        with open(fpath, "r") as f:
            content = f.read()
        required_columns = ["id", "title", "content", "created_at", "updated_at"]
        for col in required_columns:
            assert col in content, f"database.ts missing column definition: '{col}'"

    def test_types_ts_defines_note_type(self):
        """Verify types.ts defines a Note type with required fields"""
        fpath = os.path.join(self.PROJECT_DIR, "src/types.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_note_type = bool(re.search(r'(interface|type)\s+Note\b', content))
        assert has_note_type, "types.ts should define a Note interface or type"
        for field in ["id", "title", "content"]:
            assert field in content, f"types.ts Note type missing field: '{field}'"

    def test_index_ts_uses_stdio_transport(self):
        """Verify server uses stdio transport for MCP communication"""
        fpath = os.path.join(self.PROJECT_DIR, "src/index.ts")
        with open(fpath, "r") as f:
            content = f.read()
        has_stdio = bool(re.search(r'(stdio|StdioServerTransport|StdioTransport)', content))
        assert has_stdio, "Server should use stdio transport for MCP communication"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes in the project directory"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, f"npm install failed: {result.stderr[-1000:]}"

    def test_npm_build_succeeds(self):
        """Verify npm run build compiles TypeScript successfully"""
        subprocess.run(["npm", "install"], cwd=self.PROJECT_DIR, capture_output=True, timeout=120)
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, f"Build failed: {result.stderr[-1000:]}"

    def test_build_output_exists(self):
        """Verify build produces output files (dist/ or build/)"""
        subprocess.run(["npm", "install"], cwd=self.PROJECT_DIR, capture_output=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.PROJECT_DIR, capture_output=True, timeout=120)

        dist_dir = os.path.join(self.PROJECT_DIR, "dist")
        build_dir = os.path.join(self.PROJECT_DIR, "build")
        has_output = os.path.isdir(dist_dir) or os.path.isdir(build_dir)
        assert has_output, "Build should produce dist/ or build/ directory"

        output_dir = dist_dir if os.path.isdir(dist_dir) else build_dir
        files = os.listdir(output_dir)
        js_files = [f for f in files if f.endswith(".js")]
        assert len(js_files) > 0, f"Build output directory should contain .js files, found: {files}"

    def test_tsconfig_targets_es2022(self):
        """Verify tsconfig targets ES2022 with strict mode"""
        fpath = os.path.join(self.PROJECT_DIR, "tsconfig.json")
        with open(fpath, "r") as f:
            # Handle potential comments in tsconfig
            content = f.read()
            # Strip single-line comments
            content = re.sub(r'//.*', '', content)
            tsconfig = json.loads(content)
        compiler = tsconfig.get("compilerOptions", {})
        target = compiler.get("target", "").upper()
        assert "ES2022" in target or "ESNEXT" in target, (
            f"tsconfig should target ES2022 or higher, got '{target}'"
        )
        strict = compiler.get("strict", False)
        assert strict is True, "tsconfig should have strict mode enabled"
