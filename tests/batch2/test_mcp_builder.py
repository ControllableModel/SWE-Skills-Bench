"""
Test skill: mcp-builder
Verify that the Agent correctly builds an MCP server for markdown knowledge
base search with indexing, searching, and retrieval tools backed by SQLite.
"""

import os
import json
import subprocess
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"

    # === File Path Checks ===

    def test_markdown_sqlite_directory_exists(self):
        """Verify src/markdown-sqlite/ directory exists"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        assert os.path.isdir(path), f"src/markdown-sqlite/ directory not found at {path}"

    def test_package_json_exists(self):
        """Verify package.json exists in src/markdown-sqlite/"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        assert os.path.exists(path), f"package.json not found at {path}"

    def test_package_json_is_valid(self):
        """Verify package.json is valid JSON with required fields"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        with open(path) as f:
            pkg = json.load(f)
        assert "name" in pkg, "package.json missing 'name' field"
        assert "scripts" in pkg, "package.json missing 'scripts' section"

    def test_typescript_source_files_exist(self):
        """Verify TypeScript source files exist in src/markdown-sqlite/"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite/src")
        if not os.path.isdir(src_dir):
            # Might be in the root of markdown-sqlite
            src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")

        ts_files = []
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".tsx")):
                    ts_files.append(fname)

        assert len(ts_files) > 0, (
            f"No TypeScript source files found under {src_dir}"
        )

    # === Semantic Checks ===

    def test_package_json_has_build_script(self):
        """Verify package.json defines a build script"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        with open(path) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        assert "build" in scripts, (
            f"package.json should have a 'build' script. Scripts found: {list(scripts.keys())}"
        )

    def test_package_json_has_sqlite_dependency(self):
        """Verify package.json includes a SQLite dependency"""
        path = os.path.join(self.REPO_DIR, "src/markdown-sqlite/package.json")
        with open(path) as f:
            pkg = json.load(f)
        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        sqlite_deps = [d for d in all_deps if "sqlite" in d.lower() or "sql" in d.lower()]
        assert len(sqlite_deps) > 0, (
            f"package.json should include a SQLite dependency. "
            f"Dependencies: {list(all_deps.keys())}"
        )

    def test_source_defines_three_mcp_tools(self):
        """Verify source code defines at least 3 MCP tools (index, search, retrieve)"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        combined_content = ""
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".js")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        combined_content += f.read() + "\n"

        tool_keywords = {
            "index": ["index", "ingest", "import"],
            "search": ["search", "query", "find"],
            "retrieve": ["retrieve", "get", "fetch", "read"],
        }
        found_tools = []
        for tool_name, keywords in tool_keywords.items():
            if any(kw.lower() in combined_content.lower() for kw in keywords):
                found_tools.append(tool_name)

        assert len(found_tools) >= 3, (
            f"MCP server should define at least 3 tools (index, search, retrieve). "
            f"Found: {found_tools}"
        )

    def test_source_uses_mcp_sdk(self):
        """Verify source code uses MCP SDK for tool registration"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        combined_content = ""
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".js")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        combined_content += f.read() + "\n"

        mcp_indicators = [
            "@modelcontextprotocol",
            "mcp",
            "Tool",
            "Server",
            "McpServer",
        ]
        found = [ind for ind in mcp_indicators if ind in combined_content]
        assert len(found) >= 1, (
            "Source should use MCP SDK for tool registration. "
            f"None of {mcp_indicators} found."
        )

    def test_source_tracks_document_metadata(self):
        """Verify source code tracks document metadata (path, title, timestamp)"""
        src_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        combined_content = ""
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith((".ts", ".js")):
                    fpath = os.path.join(root, fname)
                    with open(fpath) as f:
                        combined_content += f.read() + "\n"

        metadata_fields = {
            "path": "path" in combined_content.lower(),
            "title": "title" in combined_content.lower(),
            "timestamp/time": (
                "timestamp" in combined_content.lower()
                or "indexed_at" in combined_content.lower()
                or "created_at" in combined_content.lower()
                or "time" in combined_content.lower()
            ),
        }
        found = [k for k, v in metadata_fields.items() if v]
        assert len(found) >= 3, (
            f"Source should track document metadata (path, title, timestamp). "
            f"Found: {found}"
        )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install succeeds in src/markdown-sqlite/"""
        project_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        result = subprocess.run(
            ["npm", "install"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0 or os.path.exists(
            os.path.join(project_dir, "node_modules")
        ), f"npm install failed: {result.stderr[:1000]}"

    def test_npm_build_succeeds(self):
        """Verify npm run build succeeds in src/markdown-sqlite/"""
        project_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        # Ensure deps installed
        subprocess.run(
            ["npm", "install"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"npm run build failed (exit code {result.returncode}).\n"
            f"stdout: {result.stdout[:1000]}\n"
            f"stderr: {result.stderr[:1000]}"
        )

    def test_build_produces_js_output(self):
        """Verify build produces JavaScript output files"""
        project_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        # Ensure build has been run
        subprocess.run(["npm", "install"], cwd=project_dir,
                       capture_output=True, text=True, timeout=300)
        subprocess.run(["npm", "run", "build"], cwd=project_dir,
                       capture_output=True, text=True, timeout=120)

        # Look for JS output in common locations
        js_found = False
        for search_dir in ["dist", "build", "lib", "."]:
            check_dir = os.path.join(project_dir, search_dir)
            if os.path.isdir(check_dir):
                for root, _dirs, files in os.walk(check_dir):
                    if any(f.endswith(".js") for f in files):
                        js_found = True
                        break
            if js_found:
                break

        assert js_found, (
            "Build should produce .js output files in dist/, build/, or lib/"
        )

    def test_typescript_files_have_no_syntax_errors(self):
        """Verify TypeScript files have no syntax errors via tsc --noEmit"""
        project_dir = os.path.join(self.REPO_DIR, "src/markdown-sqlite")
        subprocess.run(["npm", "install"], cwd=project_dir,
                       capture_output=True, text=True, timeout=300)

        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            output = result.stdout + result.stderr
            syntax_errors = [
                line for line in output.splitlines()
                if "error TS1" in line
            ]
            assert len(syntax_errors) == 0, (
                f"TypeScript syntax errors found:\n" +
                "\n".join(syntax_errors[:10])
            )
