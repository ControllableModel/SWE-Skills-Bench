"""
Test skill: springboot-tdd
Verify that the Agent correctly implements a pet weight tracking feature
for Spring PetClinic using test-driven development, including JPA entity,
repository, REST controller, schema changes, and TDD tests.
"""

import os
import re
import subprocess
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    # === File Path Checks ===

    def test_weight_record_entity_exists(self):
        """Verify WeightRecord.java entity file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightRecord.java",
        )
        assert os.path.exists(path), f"WeightRecord.java not found at {path}"

    def test_weight_repository_exists(self):
        """Verify WeightRepository.java exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightRepository.java",
        )
        assert os.path.exists(path), f"WeightRepository.java not found at {path}"

    def test_weight_controller_exists(self):
        """Verify WeightController.java exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightController.java",
        )
        assert os.path.exists(path), f"WeightController.java not found at {path}"

    def test_weight_controller_tests_exist(self):
        """Verify WeightControllerTests.java test file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/weight/WeightControllerTests.java",
        )
        assert os.path.exists(path), f"WeightControllerTests.java not found at {path}"

    # === Semantic Checks ===

    def test_weight_record_has_jpa_annotations(self):
        """Verify WeightRecord.java uses JPA annotations (@Entity, @Id, etc.)"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightRecord.java",
        )
        with open(path) as f:
            content = f.read()

        assert "@Entity" in content, "WeightRecord should be annotated with @Entity"
        assert "@Id" in content, "WeightRecord should have an @Id annotated field"

        # Verify required fields
        field_keywords = ["weight", "unit", "date"]
        found = [kw for kw in field_keywords if kw.lower() in content.lower()]
        assert len(found) >= 3, (
            f"WeightRecord should have weight, unit, and date fields. "
            f"Found references to: {found}"
        )

    def test_weight_record_has_pet_relationship(self):
        """Verify WeightRecord.java maps a relationship to Pet entity"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightRecord.java",
        )
        with open(path) as f:
            content = f.read()

        relationship_annotations = [
            "@ManyToOne", "@JoinColumn", "Pet", "pet",
        ]
        found = [ann for ann in relationship_annotations if ann in content]
        assert len(found) >= 2, (
            f"WeightRecord should map a relationship to Pet. Found: {found}. "
            f"Expected at least 2 of: {relationship_annotations}"
        )

    def test_weight_repository_extends_spring_data(self):
        """Verify WeightRepository.java extends a Spring Data repository interface"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightRepository.java",
        )
        with open(path) as f:
            content = f.read()

        repo_indicators = [
            "Repository", "CrudRepository", "JpaRepository",
            "extends", "@Repository",
        ]
        found = [ind for ind in repo_indicators if ind in content]
        assert len(found) >= 2, (
            f"WeightRepository should extend a Spring Data repository interface. "
            f"Found: {found}. Expected at least 2 of: {repo_indicators}"
        )

    def test_weight_controller_has_rest_annotations(self):
        """Verify WeightController.java has REST controller annotations"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightController.java",
        )
        with open(path) as f:
            content = f.read()

        rest_annotations = [
            "@RestController", "@Controller",
            "@RequestMapping", "@GetMapping", "@PostMapping",
        ]
        found = [ann for ann in rest_annotations if ann in content]
        assert len(found) >= 2, (
            f"WeightController should have REST annotations. Found: {found}. "
            f"Expected at least 2 of: {rest_annotations}"
        )

    def test_weight_controller_has_validation(self):
        """Verify WeightController.java validates input (reject zero/negative weights)"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/weight/WeightController.java",
        )
        with open(path) as f:
            content = f.read()

        validation_indicators = [
            "@Valid", "@Validated", "@NotNull", "@Positive",
            "@Min", "@DecimalMin", "BindingResult",
            "validation", "Validator", "validate",
            "weight <= 0", "weight < 0", "weight == 0",
        ]
        found = [ind for ind in validation_indicators if ind in content]
        assert len(found) >= 1, (
            "WeightController should validate weight values (reject zero/negative). "
            f"Found: {found}. Expected at least 1 of: {validation_indicators}"
        )

    def test_schema_sql_has_weight_table(self):
        """Verify schema.sql contains the weight records table definition"""
        schema_path = os.path.join(
            self.REPO_DIR, "src/main/resources/db/hsqldb/schema.sql"
        )
        if not os.path.exists(schema_path):
            # Try other common schema locations
            for alt in [
                "src/main/resources/db/h2/schema.sql",
                "src/main/resources/schema.sql",
                "src/main/resources/db/mysql/schema.sql",
            ]:
                alt_path = os.path.join(self.REPO_DIR, alt)
                if os.path.exists(alt_path):
                    schema_path = alt_path
                    break
            else:
                pytest.fail("No schema.sql file found")

        with open(schema_path) as f:
            content = f.read().lower()

        assert "weight" in content, (
            "schema.sql should contain a weight records table definition"
        )
        assert "create table" in content, (
            "schema.sql should contain CREATE TABLE statement for weights"
        )

    def test_tdd_tests_cover_required_scenarios(self):
        """Verify WeightControllerTests.java covers required TDD scenarios"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/weight/WeightControllerTests.java",
        )
        with open(path) as f:
            content = f.read()

        # Should have @Test annotations
        test_count = content.count("@Test")
        assert test_count >= 3, (
            f"WeightControllerTests should have at least 3 @Test methods, found {test_count}"
        )

        # Should cover various scenarios
        scenario_keywords = ["save", "record", "add", "history", "list", "get",
                             "invalid", "valid", "not found", "notfound"]
        found = [kw for kw in scenario_keywords if kw.lower() in content.lower()]
        assert len(found) >= 3, (
            f"Tests should cover saving, retrieval, and validation scenarios. "
            f"Found: {found}"
        )

    # === Functional Checks ===

    def test_project_compiles(self):
        """Verify the project compiles successfully with the new code"""
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"Maven compile failed (exit code {result.returncode}).\n"
            f"stderr: {result.stderr[:2000]}"
        )

    def test_project_tests_pass(self):
        """Verify Maven tests pass including the new weight tests"""
        result = subprocess.run(
            ["./mvnw", "test", "-pl", ".", "-Dtest=WeightControllerTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            # Try running all tests
            result2 = subprocess.run(
                ["./mvnw", "test", "-q"],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=600,
            )
            assert result2.returncode == 0, (
                f"Maven tests failed.\nstdout: {result2.stdout[:2000]}\n"
                f"stderr: {result2.stderr[:2000]}"
            )

    def test_weight_java_files_have_valid_syntax(self):
        """Verify all new Java files compile individually without errors"""
        java_files = [
            "src/main/java/org/springframework/samples/petclinic/weight/WeightRecord.java",
            "src/main/java/org/springframework/samples/petclinic/weight/WeightRepository.java",
            "src/main/java/org/springframework/samples/petclinic/weight/WeightController.java",
        ]
        for rel_path in java_files:
            full_path = os.path.join(self.REPO_DIR, rel_path)
            if os.path.exists(full_path):
                with open(full_path) as f:
                    content = f.read()
                # Basic Java syntax checks
                assert "package " in content, (
                    f"{rel_path} should have a package declaration"
                )
                assert "class " in content or "interface " in content, (
                    f"{rel_path} should define a class or interface"
                )
                # Check balanced braces
                assert content.count("{") == content.count("}"), (
                    f"{rel_path} has unbalanced braces"
                )
