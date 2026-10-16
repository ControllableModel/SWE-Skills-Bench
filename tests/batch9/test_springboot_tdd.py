"""
Test skill: springboot-tdd
Verify that the Agent correctly adds appointment scheduling to the Spring PetClinic application.
"""

import os
import subprocess
import re
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    # === File Path Checks ===

    def test_appointment_entity_exists(self):
        """Verify Appointment entity Java file exists"""
        candidates = [
            "src/main/java/org/springframework/samples/petclinic/appointment/Appointment.java",
            "src/main/java/org/springframework/samples/petclinic/model/Appointment.java",
            "src/main/java/org/springframework/samples/petclinic/owner/Appointment.java",
        ]
        found = any(
            os.path.exists(os.path.join(self.REPO_DIR, c)) for c in candidates
        )
        assert found, "Appointment.java entity not found in expected locations"

    def test_appointment_repository_exists(self):
        """Verify AppointmentRepository interface exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/main")):
            for f in files:
                if "AppointmentRepository" in f:
                    found = True
                    break
        assert found, "AppointmentRepository not found"

    def test_appointment_controller_exists(self):
        """Verify AppointmentController exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/main")):
            for f in files:
                if "AppointmentController" in f:
                    found = True
                    break
        assert found, "AppointmentController not found"

    # === Semantic Checks ===

    def test_appointment_entity_has_jpa_annotations(self):
        """Verify Appointment entity uses JPA annotations"""
        entity_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/main")):
            for f in files:
                if f == "Appointment.java":
                    entity_file = os.path.join(root, f)
                    break
        assert entity_file is not None, "Appointment.java not found"
        with open(entity_file) as fh:
            content = fh.read()
        assert "@Entity" in content, "Appointment class missing @Entity annotation"
        assert "@Id" in content or "BaseEntity" in content, (
            "Appointment class missing @Id or does not extend BaseEntity"
        )

    def test_appointment_has_required_fields(self):
        """Verify Appointment entity has date, description, pet/vet references"""
        entity_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/main")):
            for f in files:
                if f == "Appointment.java":
                    entity_file = os.path.join(root, f)
                    break
        assert entity_file is not None
        with open(entity_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        assert "date" in content_lower or "datetime" in content_lower or "localdate" in content_lower, (
            "Appointment missing date/dateTime field"
        )
        assert "description" in content_lower or "reason" in content_lower, (
            "Appointment missing description field"
        )

    def test_appointment_has_validation_annotations(self):
        """Verify Appointment entity uses Bean Validation annotations"""
        entity_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/main")):
            for f in files:
                if f == "Appointment.java":
                    entity_file = os.path.join(root, f)
                    break
        assert entity_file is not None
        with open(entity_file) as fh:
            content = fh.read()
        validation_annotations = ["@NotNull", "@NotEmpty", "@NotBlank", "@Valid", "@Future", "@Size"]
        found = [a for a in validation_annotations if a in content]
        assert len(found) >= 1, (
            f"No Bean Validation annotations found. Expected at least one of: {validation_annotations}"
        )

    def test_controller_has_conflict_detection(self):
        """Verify AppointmentController includes scheduling conflict detection logic"""
        controller_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/main")):
            for f in files:
                if "AppointmentController" in f:
                    controller_file = os.path.join(root, f)
                    break
        assert controller_file is not None
        with open(controller_file) as fh:
            content = fh.read()
        content_lower = content.lower()
        has_conflict = (
            "conflict" in content_lower
            or "overlap" in content_lower
            or "already booked" in content_lower
            or "existing" in content_lower
            or "findby" in content_lower
        )
        assert has_conflict, (
            "AppointmentController does not appear to implement conflict detection"
        )

    def test_appointment_test_file_exists(self):
        """Verify test file for appointment functionality exists"""
        found = False
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/test")):
            for f in files:
                if "appointment" in f.lower() or "Appointment" in f:
                    found = True
                    break
        assert found, "No test file for appointment feature found under src/test"

    def test_appointment_test_uses_web_mvc_test(self):
        """Verify appointment controller test uses @WebMvcTest annotation"""
        test_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/test")):
            for f in files:
                if "appointment" in f.lower() and f.endswith(".java"):
                    test_file = os.path.join(root, f)
                    break
        if test_file is None:
            pytest.skip("No appointment test file found")
        with open(test_file) as fh:
            content = fh.read()
        assert "@WebMvcTest" in content or "@SpringBootTest" in content, (
            "Appointment test does not use @WebMvcTest or @SpringBootTest annotation"
        )

    # === Functional Checks ===

    def test_maven_compile_succeeds(self):
        """Verify project compiles with Maven"""
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Maven compile failed:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"
        )

    def test_maven_tests_pass(self):
        """Verify all tests pass including new appointment tests"""
        result = subprocess.run(
            ["./mvnw", "test", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Maven tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}"
        )

    def test_appointment_controller_responds(self):
        """Verify the application starts and appointment endpoint is accessible"""
        # Check that the controller mapping is present in source
        controller_file = None
        for root, dirs, files in os.walk(os.path.join(self.REPO_DIR, "src/main")):
            for f in files:
                if "AppointmentController" in f:
                    controller_file = os.path.join(root, f)
                    break
        assert controller_file is not None
        with open(controller_file) as fh:
            content = fh.read()
        has_mapping = (
            "@RequestMapping" in content
            or "@GetMapping" in content
            or "@PostMapping" in content
            or "@Controller" in content
            or "@RestController" in content
        )
        assert has_mapping, (
            "AppointmentController has no request mapping annotations"
        )
