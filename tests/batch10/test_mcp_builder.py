"""
Test skill: mcp-builder
Verify that the Agent correctly builds a Markdown-to-SQLite MCP server
in the modelcontextprotocol/servers monorepo.
"""

import os
import json
import subprocess
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"
    PKG_DIR = "/workspace/servers/src/markdown-sqlite"

    # === File Path Checks ===

    def test_package_json_exists(self):
        """Verify src/markdown-sqlite/package.json was created"""
        path = os.path.join(self.PKG_DIR, "package.json")
        assert os.path.exists(path), f"package.json not found at {path}"

    def test_tsconfig_exists(self):
        """Verify src/markdown-sqlite/tsconfig.json was created"""
        path = os.path.join(self.PKG_DIR, "tsconfig.json")
        assert os.path.exists(path), f"tsconfig.json not found at {path}"

    def test_index_ts_exists(self):
        """Verify src/markdown-sqlite/src/index.ts entry point was created"""
        path = os.path.join(self.PKG_DIR, "src/index.ts")
        assert os.path.exists(path), f"index.ts not found at {path}"

    def test_db_ts_exists(self):
        """Verify src/markdown-sqlite/src/db.ts was created"""
        path = os.path.join(self.PKG_DIR, "src/db.ts")
        assert os.path.exists(path), f"db.ts not found at {path}"

    def test_tools_ts_exists(self):
        """Verify src/markdown-sqlite/src/tools.ts was created"""
        path = os.path.join(self.PKG_DIR, "src/tools.ts")
        assert os.path.exists(path), f"tools.ts not found at {path}"

    def test_readme_exists(self):
        """Verify src/markdown-sqlite/README.md was created"""
        path = os.path.join(self.PKG_DIR, "README.md")
        assert os.path.exists(path), f"README.md not found at {path}"

    # === Semantic Checks ===

    def test_package_json_has_build_script(self):
        """Verify package.json has a build script invoking tsc"""
        path = os.path.join(self.PKG_DIR, "package.json")
        with open(path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        assert "build" in scripts, "package.json missing 'build' script"
        assert "tsc" in scripts["build"], (
            f"build script should invoke tsc, got: {scripts['build']}"
        )

    def test_package_json_has_mcp_sdk_dependency(self):
        """Verify package.json declares @modelcontextprotocol/sdk dependency"""
        path = os.path.join(self.PKG_DIR, "package.json")
        with open(path) as f:
            pkg = json.load(f)
        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}
        assert "@modelcontextprotocol/sdk" in all_deps, (
            "package.json should depend on @modelcontextprotocol/sdk"
        )

    def test_package_json_has_sqlite_dependency(self):
        """Verify package.json declares better-sqlite3 dependency"""
        path = os.path.join(self.PKG_DIR, "package.json")
        with open(path) as f:
            pkg = json.load(f)
        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}
        assert "better-sqlite3" in all_deps, (
            "package.json should depend on better-sqlite3"
        )

    def test_package_json_has_zod_dependency(self):
        """Verify package.json declares zod dependency"""
        path = os.path.join(self.PKG_DIR, "package.json")
        with open(path) as f:
            pkg = json.load(f)
        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}
        assert "zod" in all_deps, "package.json should depend on zod"

    def test_tsconfig_strict_mode(self):
        """Verify tsconfig.json has strict mode enabled"""
        path = os.path.join(self.PKG_DIR, "tsconfig.json")
        with open(path) as f:
            content = f.read()
        # Handle jsonc (comments)
        import re
        clean = re.sub(r'//.*', '', content)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        config = json.loads(clean)
        compiler_opts = config.get("compilerOptions", {})
        assert compiler_opts.get("strict") is True, (
            "tsconfig.json should have strict: true"
        )

    def test_index_ts_registers_tools(self):
        """Verify index.ts registers MCP tools"""
        path = os.path.join(self.PKG_DIR, "src/index.ts")
        with open(path) as f:
            content = f.read()
        tool_names = ["ingest_markdown", "search_documents", "list_documents", "get_document"]
        found = sum(1 for name in tool_names if name in content)
        # At least the tools should be referenced (might be in tools.ts and imported)
        if found < 2:
            # Check tools.ts
            tools_path = os.path.join(self.PKG_DIR, "src/tools.ts")
            with open(tools_path) as f:
                tools_content = f.read()
            found = sum(1 for name in tool_names if name in tools_content)
        assert found >= 4, (
            f"Expected all 4 tools registered. Found {found}/4 tool names in source files."
        )

    def test_db_creates_documents_table(self):
        """Verify db.ts creates the documents table with required columns"""
        path = os.path.join(self.PKG_DIR, "src/db.ts")
        with open(path) as f:
            content = f.read()
        assert "documents" in content, "db.ts should reference 'documents' table"
        for col in ["path", "title", "content", "frontmatter", "last_modified"]:
            assert col in content, f"db.ts missing column '{col}' in documents table"

    def test_tools_use_zod_validation(self):
        """Verify tools use Zod schemas for input validation"""
        path = os.path.join(self.PKG_DIR, "src/tools.ts")
        with open(path) as f:
            content = f.read()
        assert "zod" in content.lower() or "z." in content, (
            "tools.ts should use Zod for input validation"
        )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install succeeds in the markdown-sqlite package"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.PKG_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"npm install failed: {result.stderr[-1000:]}"
        )

    def test_npm_run_build_succeeds(self):
        """Verify npm run build compiles TypeScript without errors"""
        # Ensure deps are installed first
        subprocess.run(
            ["npm", "install"],
            cwd=self.PKG_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.PKG_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"npm run build failed: {result.stderr[-1000:]}\n{result.stdout[-1000:]}"
        )

    def test_dist_contains_compiled_output(self):
        """Verify dist/ directory contains compiled JavaScript after build"""
        # Build first
        subprocess.run(["npm", "install"], cwd=self.PKG_DIR, capture_output=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.PKG_DIR, capture_output=True, timeout=120)

        dist_dir = os.path.join(self.PKG_DIR, "dist")
        assert os.path.isdir(dist_dir), f"dist/ directory not found after build at {dist_dir}"
        js_files = [f for f in os.listdir(dist_dir) if f.endswith('.js')]
        assert len(js_files) > 0, "dist/ should contain .js files after build"
        assert "index.js" in js_files, "dist/ should contain index.js"

    def test_compiled_entry_point_is_loadable(self):
        """Verify the compiled entry point can be loaded by Node.js without immediate crash"""
        subprocess.run(["npm", "install"], cwd=self.PKG_DIR, capture_output=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.PKG_DIR, capture_output=True, timeout=120)

        # Check syntax by requiring the module (it will try to start stdio transport, so timeout quickly)
        result = subprocess.run(
            ["node", "-e", "try { require('./dist/index.js') } catch(e) { if(!e.message.includes('stdin')) throw e; }"],
            cwd=self.PKG_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # It may exit non-zero because stdin isn't connected, but shouldn't have syntax errors
        if result.returncode != 0:
            assert "SyntaxError" not in result.stderr, (
                f"Compiled entry point has syntax errors: {result.stderr[:500]}"
            )
