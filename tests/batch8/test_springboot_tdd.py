"""
Test skill: springboot-tdd
Verify that the Agent correctly adds an Appointment resource to Spring PetClinic
using test-driven development, including entity, repository, controller, and validator.
"""

import os
import subprocess
import re
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    # === File Path Checks ===

    def test_appointment_entity_exists(self):
        """Verify that Appointment.java entity file exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/Appointment.java"
        )
        assert os.path.exists(filepath), f"Appointment.java not found at {filepath}"

    def test_appointment_repository_exists(self):
        """Verify that AppointmentRepository.java exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/AppointmentRepository.java"
        )
        assert os.path.exists(filepath), f"AppointmentRepository.java not found at {filepath}"

    def test_appointment_controller_exists(self):
        """Verify that AppointmentController.java exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/AppointmentController.java"
        )
        assert os.path.exists(filepath), f"AppointmentController.java not found at {filepath}"

    def test_appointment_validator_exists(self):
        """Verify that AppointmentValidator.java exists"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/AppointmentValidator.java"
        )
        assert os.path.exists(filepath), f"AppointmentValidator.java not found at {filepath}"

    def test_h2_schema_updated(self):
        """Verify that H2 schema.sql contains appointments table DDL"""
        filepath = os.path.join(self.REPO_DIR, "src/main/resources/db/h2/schema.sql")
        assert os.path.exists(filepath), f"H2 schema.sql not found at {filepath}"
        with open(filepath) as f:
            content = f.read().lower()
        assert "appointments" in content, (
            "H2 schema.sql does not contain 'appointments' table definition"
        )

    # === Semantic Checks ===

    def test_appointment_entity_has_jpa_annotations(self):
        """Verify that Appointment.java has required JPA and validation annotations"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/Appointment.java"
        )
        with open(filepath) as f:
            content = f.read()

        # Check for key annotations
        required_patterns = {
            "@Entity": "@Entity" in content,
            "@ManyToOne for pet": "ManyToOne" in content,
            "@NotNull": "NotNull" in content,
            "LocalDateTime field": "LocalDateTime" in content,
            "status enum": "SCHEDULED" in content or "AppointmentStatus" in content,
        }
        missing = [p for p, found in required_patterns.items() if not found]
        assert len(missing) == 0, (
            f"Appointment.java missing required annotations/fields: {missing}"
        )

    def test_appointment_entity_has_required_fields(self):
        """Verify that Appointment entity has all required fields"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/Appointment.java"
        )
        with open(filepath) as f:
            content = f.read()

        required_fields = ["pet", "vet", "appointmentDateTime", "description", "status"]
        for field in required_fields:
            # Check for field declaration (case insensitive for field name)
            pattern = rf'(?:private|protected|public)\s+\w+\s+{field}\b'
            match = re.search(pattern, content, re.IGNORECASE)
            assert match is not None, (
                f"Appointment.java missing required field '{field}'"
            )

    def test_appointment_repository_has_custom_queries(self):
        """Verify that AppointmentRepository has custom query methods for conflict detection"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/AppointmentRepository.java"
        )
        with open(filepath) as f:
            content = f.read()

        # Check for conflict detection query
        has_conflict_query = (
            "findByVetId" in content
            and ("Between" in content or "DateTime" in content)
        )
        assert has_conflict_query, (
            "AppointmentRepository missing conflict detection query method. "
            "Expected findByVetIdAndAppointmentDateTimeBetween or similar."
        )

        has_pet_query = "findByPetId" in content
        assert has_pet_query, (
            "AppointmentRepository missing findByPetId query method"
        )

    def test_appointment_controller_has_rest_endpoints(self):
        """Verify that AppointmentController defines required REST endpoints"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/appointment/AppointmentController.java"
        )
        with open(filepath) as f:
            content = f.read()

        required_annotations = {
            "@RestController or @Controller": "RestController" in content or "Controller" in content,
            "POST mapping": "PostMapping" in content or "RequestMapping" in content,
            "GET mapping": "GetMapping" in content or "RequestMapping" in content,
            "PUT or PATCH mapping": "PutMapping" in content or "PatchMapping" in content,
        }
        missing = [a for a, found in required_annotations.items() if not found]
        assert len(missing) == 0, (
            f"AppointmentController missing required REST annotations: {missing}"
        )

    def test_h2_schema_has_foreign_keys(self):
        """Verify that appointments table has foreign keys to pets and vets"""
        filepath = os.path.join(self.REPO_DIR, "src/main/resources/db/h2/schema.sql")
        with open(filepath) as f:
            content = f.read().lower()

        # Check for foreign key references
        has_pet_fk = "pet" in content and ("foreign key" in content or "references" in content or "pet_id" in content)
        has_vet_fk = "vet" in content and ("foreign key" in content or "references" in content or "vet_id" in content)

        assert has_pet_fk, "appointments table missing foreign key to pets table"
        assert has_vet_fk, "appointments table missing foreign key to vets table"

    # === Functional Checks ===

    def test_project_compiles(self):
        """Verify that the project compiles successfully with Maven"""
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600
        )
        assert result.returncode == 0, (
            f"Maven compile failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout[:3000]}\n"
            f"stderr: {result.stderr[:3000]}"
        )

    def test_controller_tests_exist_and_have_minimum_methods(self):
        """Verify AppointmentControllerTests has at least 8 test methods"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/appointment/AppointmentControllerTests.java"
        )
        assert os.path.exists(filepath), f"Controller test file not found at {filepath}"
        with open(filepath) as f:
            content = f.read()

        test_methods = re.findall(r'@Test\s', content)
        assert len(test_methods) >= 8, (
            f"Expected at least 8 @Test methods in AppointmentControllerTests, found {len(test_methods)}"
        )

    def test_repository_tests_exist_and_have_minimum_methods(self):
        """Verify AppointmentRepositoryTests has at least 4 test methods"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/appointment/AppointmentRepositoryTests.java"
        )
        assert os.path.exists(filepath), f"Repository test file not found at {filepath}"
        with open(filepath) as f:
            content = f.read()

        test_methods = re.findall(r'@Test\s', content)
        assert len(test_methods) >= 4, (
            f"Expected at least 4 @Test methods in AppointmentRepositoryTests, found {len(test_methods)}"
        )

    def test_validator_tests_exist_and_have_minimum_methods(self):
        """Verify AppointmentValidatorTests has at least 4 test methods"""
        filepath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/appointment/AppointmentValidatorTests.java"
        )
        assert os.path.exists(filepath), f"Validator test file not found at {filepath}"
        with open(filepath) as f:
            content = f.read()

        test_methods = re.findall(r'@Test\s', content)
        assert len(test_methods) >= 4, (
            f"Expected at least 4 @Test methods in AppointmentValidatorTests, found {len(test_methods)}"
        )

    def test_maven_tests_pass(self):
        """Verify that all tests pass when run with Maven"""
        result = subprocess.run(
            ["./mvnw", "test", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600
        )
        assert result.returncode == 0, (
            f"Maven test failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout[:3000]}\n"
            f"stderr: {result.stderr[:3000]}"
        )
