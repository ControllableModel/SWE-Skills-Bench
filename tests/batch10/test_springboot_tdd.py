"""
Test skill: springboot-tdd
Verify that the Agent correctly adds a visit scheduling feature to Spring PetClinic
with full test coverage (unit, web-layer, and integration tests).
"""

import os
import re
import subprocess
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    # === File Path Checks ===

    def test_visit_scheduling_service_exists(self):
        """Verify VisitSchedulingService.java was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitSchedulingService.java",
        )
        assert os.path.exists(path), f"VisitSchedulingService.java not found at {path}"

    def test_visit_status_enum_exists(self):
        """Verify VisitStatus.java enum was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitStatus.java",
        )
        assert os.path.exists(path), f"VisitStatus.java not found at {path}"

    def test_visit_schedule_request_dto_exists(self):
        """Verify VisitScheduleRequest.java DTO was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitScheduleRequest.java",
        )
        assert os.path.exists(path), f"VisitScheduleRequest.java not found at {path}"

    def test_visit_scheduling_controller_exists(self):
        """Verify VisitSchedulingController.java was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitSchedulingController.java",
        )
        assert os.path.exists(path), f"VisitSchedulingController.java not found at {path}"

    def test_unit_test_file_exists(self):
        """Verify VisitSchedulingServiceTest.java was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/visit/VisitSchedulingServiceTest.java",
        )
        assert os.path.exists(path), f"VisitSchedulingServiceTest.java not found at {path}"

    def test_web_layer_test_file_exists(self):
        """Verify VisitSchedulingControllerTest.java was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/visit/VisitSchedulingControllerTest.java",
        )
        assert os.path.exists(path), f"VisitSchedulingControllerTest.java not found at {path}"

    def test_integration_test_file_exists(self):
        """Verify VisitSchedulingIntegrationTest.java was created"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/visit/VisitSchedulingIntegrationTest.java",
        )
        assert os.path.exists(path), f"VisitSchedulingIntegrationTest.java not found at {path}"

    # === Semantic Checks ===

    def test_visit_status_enum_has_required_values(self):
        """Verify VisitStatus enum defines SCHEDULED, COMPLETED, CANCELLED"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitStatus.java",
        )
        with open(path) as f:
            content = f.read()
        assert "SCHEDULED" in content, "VisitStatus missing SCHEDULED value"
        assert "COMPLETED" in content, "VisitStatus missing COMPLETED value"
        assert "CANCELLED" in content, "VisitStatus missing CANCELLED value"
        assert "enum" in content, "VisitStatus should be an enum"

    def test_visit_schedule_request_has_validation_annotations(self):
        """Verify VisitScheduleRequest DTO has Jakarta/javax validation annotations"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitScheduleRequest.java",
        )
        with open(path) as f:
            content = f.read()
        assert "NotNull" in content, "VisitScheduleRequest missing @NotNull annotation"
        assert "petId" in content, "VisitScheduleRequest missing petId field"
        assert "scheduledDate" in content or "scheduled_date" in content, (
            "VisitScheduleRequest missing scheduledDate field"
        )
        # Should have @Future or @FutureOrPresent
        has_future = "Future" in content
        assert has_future, "VisitScheduleRequest should have @Future annotation on scheduledDate"

    def test_scheduling_service_has_required_methods(self):
        """Verify VisitSchedulingService has scheduleVisit, cancelVisit, completeVisit methods"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitSchedulingService.java",
        )
        with open(path) as f:
            content = f.read()
        assert "scheduleVisit" in content, "VisitSchedulingService missing scheduleVisit method"
        assert "cancelVisit" in content, "VisitSchedulingService missing cancelVisit method"
        assert "completeVisit" in content, "VisitSchedulingService missing completeVisit method"

    def test_scheduling_controller_has_rest_endpoints(self):
        """Verify VisitSchedulingController exposes required REST endpoints"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitSchedulingController.java",
        )
        with open(path) as f:
            content = f.read()
        assert "PostMapping" in content or "RequestMapping" in content, (
            "Controller missing POST endpoint annotation"
        )
        assert "schedule" in content.lower(), "Controller should have a schedule endpoint"
        assert "cancel" in content.lower(), "Controller should have a cancel endpoint"
        assert "complete" in content.lower(), "Controller should have a complete endpoint"

    def test_visit_entity_has_status_field(self):
        """Verify Visit.java entity has status and scheduledDate fields"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/Visit.java",
        )
        assert os.path.exists(path), f"Visit.java not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "status" in content, "Visit entity missing 'status' field"
        assert "scheduledDate" in content or "scheduled_date" in content, (
            "Visit entity missing 'scheduledDate' field"
        )

    def test_schema_sql_has_new_columns(self):
        """Verify H2 schema.sql includes status and scheduled_date columns"""
        path = os.path.join(self.REPO_DIR, "src/main/resources/db/h2/schema.sql")
        if not os.path.exists(path):
            pytest.skip("H2 schema.sql not found")
        with open(path) as f:
            content = f.read().lower()
        assert "status" in content, "schema.sql missing 'status' column for visits"
        assert "scheduled_date" in content or "scheduleddate" in content, (
            "schema.sql missing 'scheduled_date' column for visits"
        )

    def test_unit_test_uses_mockito(self):
        """Verify unit tests use Mockito for mocking dependencies"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/visit/VisitSchedulingServiceTest.java",
        )
        with open(path) as f:
            content = f.read()
        assert "Mockito" in content or "mock" in content.lower(), (
            "Unit test should use Mockito for mocking dependencies"
        )

    def test_controller_test_uses_webmvctest(self):
        """Verify controller tests use @WebMvcTest annotation"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/visit/VisitSchedulingControllerTest.java",
        )
        with open(path) as f:
            content = f.read()
        assert "WebMvcTest" in content, "Controller test should use @WebMvcTest annotation"
        assert "MockMvc" in content, "Controller test should use MockMvc"

    def test_integration_test_uses_springboottest(self):
        """Verify integration tests use @SpringBootTest"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/visit/VisitSchedulingIntegrationTest.java",
        )
        with open(path) as f:
            content = f.read()
        assert "SpringBootTest" in content, "Integration test should use @SpringBootTest"

    # === Functional Checks ===

    def test_maven_compile_succeeds(self):
        """Verify mvnw compile succeeds without errors"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        if not os.path.exists(mvnw):
            pytest.skip("mvnw not found")
        # Ensure mvnw is executable
        subprocess.run(["chmod", "+x", mvnw], cwd=self.REPO_DIR, capture_output=True)
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"Maven compile failed (exit {result.returncode}).\n"
            f"stderr: {result.stderr[-1500:]}"
        )

    def test_maven_tests_pass(self):
        """Verify all Maven tests pass (including new scheduling tests)"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        if not os.path.exists(mvnw):
            pytest.skip("mvnw not found")
        subprocess.run(["chmod", "+x", mvnw], cwd=self.REPO_DIR, capture_output=True)
        result = subprocess.run(
            ["./mvnw", "test", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"Maven tests failed (exit {result.returncode}).\n"
            f"stderr: {result.stderr[-2000:]}"
        )

    def test_scheduling_service_handles_illegal_state_transitions(self):
        """Verify service code has IllegalStateException handling for invalid transitions"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitSchedulingService.java",
        )
        with open(path) as f:
            content = f.read()
        assert "IllegalStateException" in content, (
            "VisitSchedulingService should throw IllegalStateException for invalid state transitions"
        )

    def test_scheduling_service_handles_duplicate_detection(self):
        """Verify service checks for duplicate scheduled visits on same date"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/visit/VisitSchedulingService.java",
        )
        with open(path) as f:
            content = f.read()
        assert "IllegalArgumentException" in content, (
            "VisitSchedulingService should throw IllegalArgumentException for duplicates"
        )
        # Should check for existing scheduled visits
        duplicate_check = (
            "already scheduled" in content.lower()
            or "findByPetId" in content
            or "existsBy" in content
        )
        assert duplicate_check, (
            "VisitSchedulingService should check for existing scheduled visits for duplicate detection"
        )
