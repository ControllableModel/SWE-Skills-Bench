"""
Test skill: fix
Verify that the Agent correctly fixes React component bugs (state mutation,
zero-score rendering, timer memory leak), adds TypeScript types, and configures
ESLint in the Upgradle project.
"""

import os
import re
import json
import subprocess
import pytest


class TestFix:
    REPO_DIR = "/workspace/upgradle"

    # === File Path Checks ===

    def test_gameboard_component_exists(self):
        """Verify GameBoard.tsx component file exists"""
        filepath = os.path.join(self.REPO_DIR, "src/components/GameBoard.tsx")
        assert os.path.exists(filepath), f"GameBoard.tsx not found at {filepath}"

    def test_scoredisplay_component_exists(self):
        """Verify ScoreDisplay.tsx component file exists"""
        filepath = os.path.join(self.REPO_DIR, "src/components/ScoreDisplay.tsx")
        assert os.path.exists(filepath), f"ScoreDisplay.tsx not found at {filepath}"

    def test_timer_component_exists(self):
        """Verify Timer.tsx component file exists"""
        filepath = os.path.join(self.REPO_DIR, "src/components/Timer.tsx")
        assert os.path.exists(filepath), f"Timer.tsx not found at {filepath}"

    def test_game_types_file_exists(self):
        """Verify TypeScript types file created at src/types/game.ts"""
        filepath = os.path.join(self.REPO_DIR, "src/types/game.ts")
        assert os.path.exists(filepath), f"game.ts types file not found at {filepath}"

    def test_eslint_config_exists(self):
        """Verify ESLint configuration file exists"""
        candidates = [
            ".eslintrc.json", ".eslintrc.js", ".eslintrc.yaml",
            ".eslintrc.yml", ".eslintrc",
        ]
        found = any(
            os.path.exists(os.path.join(self.REPO_DIR, c)) for c in candidates
        )
        assert found, "ESLint configuration file not found"

    # === Semantic Checks ===

    def test_gameboard_no_direct_state_mutation(self):
        """Verify GameBoard.tsx does not directly mutate state arrays"""
        filepath = os.path.join(self.REPO_DIR, "src/components/GameBoard.tsx")
        with open(filepath) as f:
            content = f.read()
        # Pattern: state.push(x); setState(state) indicates direct mutation
        bad_patterns = [
            r'\b\w+\.push\s*\([^)]*\)\s*;\s*set[A-Z]\w*\s*\(\s*\w+\s*\)',
            r'\b\w+\.splice\s*\([^)]*\)\s*;\s*set[A-Z]\w*\s*\(\s*\w+\s*\)',
        ]
        for pat in bad_patterns:
            match = re.search(pat, content)
            assert match is None, \
                f"Direct state mutation found in GameBoard.tsx: {match.group()}"

    def test_scoredisplay_handles_zero_correctly(self):
        """Verify ScoreDisplay.tsx does not treat score 0 as falsy"""
        filepath = os.path.join(self.REPO_DIR, "src/components/ScoreDisplay.tsx")
        with open(filepath) as f:
            content = f.read()
        # Bad pattern: {score && <...>} treats 0 as falsy
        bad = re.search(r'\{\s*score\s+&&\s+<', content)
        assert bad is None, \
            "ScoreDisplay.tsx still uses '{score && <...>}' which renders nothing for score 0"

    def test_timer_has_interval_cleanup(self):
        """Verify Timer.tsx clears the interval in useEffect cleanup"""
        filepath = os.path.join(self.REPO_DIR, "src/components/Timer.tsx")
        with open(filepath) as f:
            content = f.read()
        assert "clearInterval" in content, \
            "Timer.tsx missing clearInterval - potential memory leak"
        # Verify clearInterval is in a return/cleanup context
        has_cleanup = bool(re.search(
            r'return\s*(\(\)\s*=>|function)\s*\{?\s*.*?clearInterval',
            content,
            re.DOTALL,
        ))
        assert has_cleanup, \
            "Timer.tsx has clearInterval but not in a useEffect cleanup return"

    def test_typescript_interfaces_defined(self):
        """Verify all required TypeScript interfaces are defined in game.ts"""
        filepath = os.path.join(self.REPO_DIR, "src/types/game.ts")
        with open(filepath) as f:
            content = f.read()
        for iface in ["GameState", "Player", "Round", "ScoreEntry"]:
            assert re.search(rf'(interface|type)\s+{iface}\b', content), \
                f"Interface/type '{iface}' not found in game.ts"

    def test_gamestate_has_required_fields(self):
        """Verify GameState interface has all required fields"""
        filepath = os.path.join(self.REPO_DIR, "src/types/game.ts")
        with open(filepath) as f:
            content = f.read()
        match = re.search(
            r'(interface|type)\s+GameState\s*[={]\s*\{?([^}]+)\}',
            content,
            re.DOTALL,
        )
        assert match is not None, "Could not parse GameState interface"
        body = match.group(2)
        for field in ["rounds", "currentRound", "players", "isActive", "startedAt"]:
            assert field in body, f"GameState missing field: {field}"

    def test_eslint_config_has_react_hooks_rules(self):
        """Verify ESLint config includes react-hooks plugin or rules"""
        config_content = None
        for name in [".eslintrc.json", ".eslintrc.js", ".eslintrc.yaml",
                     ".eslintrc.yml", ".eslintrc"]:
            path = os.path.join(self.REPO_DIR, name)
            if os.path.exists(path):
                with open(path) as f:
                    config_content = f.read()
                break
        assert config_content is not None, "ESLint config not found"
        assert "react-hooks" in config_content, \
            "ESLint config missing react-hooks rules"

    # === Functional Checks ===

    def test_npm_install_succeeds(self):
        """Verify npm install completes without errors"""
        result = subprocess.run(
            ["npm", "install"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, \
            f"npm install failed: {result.stderr[:500]}"

    def test_project_builds_successfully(self):
        """Verify the React project builds without TypeScript or compilation errors"""
        subprocess.run(
            ["npm", "install"], cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=300,
        )
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # Fallback: try npm run build
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
        assert result.returncode == 0, \
            f"Build failed: {result.stderr[:500]}"

    def test_eslint_runs_without_errors(self):
        """Verify ESLint runs on source code without fatal errors"""
        subprocess.run(
            ["npm", "install"], cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=300,
        )
        result = subprocess.run(
            ["npx", "eslint", "src/", "--max-warnings", "50"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # returncode 0 = no issues, 1 = warnings only, 2 = fatal
        assert result.returncode != 2, \
            f"ESLint has fatal errors: {result.stdout[:500]}"

    def test_test_file_exists_and_covers_bugs(self):
        """Verify test files exist and reference the bug-fixed components"""
        test_files = []
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src")):
            for f in files:
                if f.endswith(('.test.tsx', '.test.ts', '.spec.tsx', '.spec.ts')):
                    test_files.append(os.path.join(root, f))

        assert len(test_files) > 0, "No test files found under src/"

        all_content = ""
        for tf in test_files:
            with open(tf) as f:
                all_content += f.read()

        assert "GameBoard" in all_content or "gameBoard" in all_content, \
            "Tests do not cover GameBoard component"
