"""
Test skill: mcp-builder
Verify that the Agent correctly builds an MCP server for Markdown-to-SQLite
conversion and querying in the modelcontextprotocol/servers repository.
"""

import os
import subprocess
import json
import re
import pytest


class TestMcpBuilder:
    REPO_DIR = "/workspace/servers"
    MCP_DIR = "/workspace/servers/src/markdown-sqlite"

    # === File Path Checks ===

    def test_index_ts_exists(self):
        """Verify that the MCP server entry point exists"""
        filepath = os.path.join(self.MCP_DIR, "src/index.ts")
        assert os.path.exists(filepath), f"index.ts not found at {filepath}"

    def test_parser_ts_exists(self):
        """Verify that the Markdown parser module exists"""
        filepath = os.path.join(self.MCP_DIR, "src/parser.ts")
        assert os.path.exists(filepath), f"parser.ts not found at {filepath}"

    def test_database_ts_exists(self):
        """Verify that the database module exists"""
        filepath = os.path.join(self.MCP_DIR, "src/database.ts")
        assert os.path.exists(filepath), f"database.ts not found at {filepath}"

    def test_tools_ts_exists(self):
        """Verify that the tools module exists"""
        filepath = os.path.join(self.MCP_DIR, "src/tools.ts")
        assert os.path.exists(filepath), f"tools.ts not found at {filepath}"

    def test_package_json_exists_and_valid(self):
        """Verify that package.json exists and is valid JSON with required fields"""
        filepath = os.path.join(self.MCP_DIR, "package.json")
        assert os.path.exists(filepath), f"package.json not found at {filepath}"
        with open(filepath) as f:
            data = json.load(f)
        assert "name" in data, "package.json missing 'name'"
        assert "scripts" in data, "package.json missing 'scripts'"
        assert "build" in data.get("scripts", {}), (
            "package.json missing 'build' script"
        )

    def test_tsconfig_exists(self):
        """Verify that tsconfig.json exists"""
        filepath = os.path.join(self.MCP_DIR, "tsconfig.json")
        assert os.path.exists(filepath), f"tsconfig.json not found at {filepath}"

    # === Semantic Checks ===

    def test_parser_implements_section_extraction(self):
        """Verify that parser.ts implements heading/section parsing logic"""
        filepath = os.path.join(self.MCP_DIR, "src/parser.ts")
        with open(filepath) as f:
            content = f.read()

        required_concepts = {
            "heading": "heading" in content.lower(),
            "level": "level" in content.lower(),
            "content": "content" in content.lower(),
            "word_count or wordCount": "word_count" in content.lower() or "wordcount" in content.lower(),
            "path": "path" in content.lower(),
        }
        missing = [c for c, found in required_concepts.items() if not found]
        assert len(missing) == 0, (
            f"parser.ts missing required concepts: {missing}. "
            "Parser must extract heading, level, path, content, and word_count."
        )

    def test_database_has_required_tables(self):
        """Verify that database.ts defines documents, sections, and FTS tables"""
        filepath = os.path.join(self.MCP_DIR, "src/database.ts")
        with open(filepath) as f:
            content = f.read()

        required_tables = {
            "documents": "documents" in content,
            "sections": "sections" in content,
            "FTS5/sections_fts": "fts" in content.lower() or "sections_fts" in content,
        }
        missing = [t for t, found in required_tables.items() if not found]
        assert len(missing) == 0, (
            f"database.ts missing table definitions: {missing}"
        )

    def test_tools_defines_all_mcp_tools(self):
        """Verify that tools.ts defines all 4 required MCP tools"""
        filepath = os.path.join(self.MCP_DIR, "src/tools.ts")
        with open(filepath) as f:
            content = f.read()

        required_tools = ["ingest_document", "query_sections", "search_content", "list_documents"]
        for tool in required_tools:
            assert tool in content, (
                f"tools.ts missing MCP tool '{tool}'. "
                "All 4 tools must be defined."
            )

    def test_tools_use_zod_validation(self):
        """Verify that tools use Zod schemas for input validation"""
        filepath = os.path.join(self.MCP_DIR, "src/tools.ts")
        with open(filepath) as f:
            content = f.read()

        # Also check index.ts in case schemas are defined there
        index_path = os.path.join(self.MCP_DIR, "src/index.ts")
        if os.path.exists(index_path):
            with open(index_path) as f:
                content += f.read()

        has_zod = "zod" in content.lower() or "z.object" in content or "z.string" in content
        assert has_zod, (
            "No Zod schema validation found in tools.ts or index.ts. "
            "All MCP tools must include Zod input schemas."
        )

    def test_database_supports_reingestion(self):
        """Verify that database.ts supports re-ingesting documents (replace on same name)"""
        filepath = os.path.join(self.MCP_DIR, "src/database.ts")
        with open(filepath) as f:
            content = f.read()

        has_replace_logic = (
            "DELETE" in content or "delete" in content.lower()
            or "REPLACE" in content or "replace" in content.lower()
            or "upsert" in content.lower()
            or "ON CONFLICT" in content
        )
        assert has_replace_logic, (
            "database.ts does not appear to support re-ingestion. "
            "Re-ingesting a document with the same name should replace the previous version."
        )

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify that npm install succeeds in the MCP server directory"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.MCP_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, (
            f"npm install failed: {result.stderr[:2000]}"
        )

    def test_npm_build_succeeds(self):
        """Verify that npm run build compiles TypeScript successfully"""
        subprocess.run(["npm", "install"], cwd=self.MCP_DIR, capture_output=True, timeout=120)

        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=self.MCP_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        assert result.returncode == 0, (
            f"npm run build failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}"
        )

    def test_dist_directory_created(self):
        """Verify that build output is in the dist/ directory"""
        subprocess.run(["npm", "install"], cwd=self.MCP_DIR, capture_output=True, timeout=120)
        subprocess.run(["npm", "run", "build"], cwd=self.MCP_DIR, capture_output=True, timeout=120)

        dist_dir = os.path.join(self.MCP_DIR, "dist")
        assert os.path.exists(dist_dir), (
            f"dist/ directory not found at {dist_dir}. "
            "TypeScript build should output to dist/."
        )
        # Check that compiled JS files exist
        js_files = [f for f in os.listdir(dist_dir) if f.endswith(".js")]
        assert len(js_files) > 0, (
            "dist/ directory contains no .js files. Build may not have produced output."
        )

    def test_tsconfig_has_strict_mode(self):
        """Verify that tsconfig.json enables strict mode"""
        filepath = os.path.join(self.MCP_DIR, "tsconfig.json")
        with open(filepath) as f:
            data = json.load(f)

        compiler_options = data.get("compilerOptions", {})
        assert compiler_options.get("strict") is True, (
            "tsconfig.json should have strict mode enabled. "
            f"Found compilerOptions: {compiler_options}"
        )

    def test_parser_handles_root_section(self):
        """Verify parser handles content before first heading as _root section"""
        filepath = os.path.join(self.MCP_DIR, "src/parser.ts")
        with open(filepath) as f:
            content = f.read()

        assert "_root" in content, (
            "parser.ts does not reference '_root' section. "
            "Content before the first heading must be assigned to a virtual _root section."
        )
