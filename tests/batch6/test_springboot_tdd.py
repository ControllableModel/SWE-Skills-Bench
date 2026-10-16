"""
Test skill: springboot-tdd
Verify that the Agent correctly implements a Vet Appointment Booking feature
in Spring Petclinic using TDD with proper entity, repository, service, and controller.
"""

import os
import re
import subprocess
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"
    APPOINTMENT_PKG = "src/main/java/org/springframework/samples/petclinic/appointment"
    TEST_PKG = "src/test/java/org/springframework/samples/petclinic/appointment"

    # === File Path Checks ===

    def test_appointment_entity_exists(self):
        """Verify that Appointment.java entity file exists"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "Appointment.java")
        assert os.path.exists(path), f"Appointment.java not found at {path}"

    def test_appointment_repository_exists(self):
        """Verify that AppointmentRepository.java file exists"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "AppointmentRepository.java")
        assert os.path.exists(path), f"AppointmentRepository.java not found at {path}"

    def test_appointment_service_exists(self):
        """Verify that AppointmentService.java file exists"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "AppointmentService.java")
        assert os.path.exists(path), f"AppointmentService.java not found at {path}"

    def test_appointment_controller_exists(self):
        """Verify that AppointmentController.java file exists"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "AppointmentController.java")
        assert os.path.exists(path), f"AppointmentController.java not found at {path}"

    def test_create_appointment_request_dto_exists(self):
        """Verify that CreateAppointmentRequest.java DTO file exists"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "CreateAppointmentRequest.java")
        assert os.path.exists(path), f"CreateAppointmentRequest.java not found at {path}"

    # === Semantic Checks ===

    def test_appointment_entity_has_required_fields(self):
        """Verify that Appointment entity has all required fields with correct annotations"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "Appointment.java")
        with open(path, "r") as f:
            content = f.read()

        # Check required fields
        required_fields = [
            "appointmentDate", "startTime", "endTime", "reason", "status"
        ]
        for field in required_fields:
            assert field in content, (
                f"Appointment entity missing required field: {field}"
            )

        # Check JPA annotations
        assert "@Entity" in content, "Appointment class missing @Entity annotation"
        assert "@Table" in content or "@Entity" in content, "Missing table mapping"

        # Check relationships
        assert "@ManyToOne" in content, (
            "Appointment should have @ManyToOne relationships for pet and vet"
        )
        assert "Pet" in content, "Appointment should reference Pet entity"
        assert "Vet" in content, "Appointment should reference Vet entity"

    def test_appointment_entity_has_status_enum(self):
        """Verify that Appointment status uses an enum with SCHEDULED, COMPLETED, CANCELLED"""
        pkg_dir = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG)
        # Status enum might be in Appointment.java or a separate file
        enum_found = False
        for filename in os.listdir(pkg_dir):
            if filename.endswith(".java"):
                filepath = os.path.join(pkg_dir, filename)
                with open(filepath, "r") as f:
                    content = f.read()
                if "SCHEDULED" in content and "COMPLETED" in content and "CANCELLED" in content:
                    enum_found = True
                    break

        assert enum_found, (
            "AppointmentStatus enum with SCHEDULED, COMPLETED, CANCELLED not found"
        )

    def test_repository_has_custom_query_methods(self):
        """Verify that AppointmentRepository has required custom query methods"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "AppointmentRepository.java")
        with open(path, "r") as f:
            content = f.read()

        # Check for required query methods
        assert "findByVet" in content, (
            "Repository missing findByVetAndAppointmentDate method"
        )
        assert "findByPetOwner" in content or "ownerId" in content.lower(), (
            "Repository missing findByPetOwnerId method"
        )

    def test_service_has_scheduling_conflict_detection(self):
        """Verify that AppointmentService implements scheduling conflict detection"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "AppointmentService.java")
        with open(path, "r") as f:
            content = f.read()

        # Check for conflict detection logic
        has_conflict_check = any(kw in content for kw in [
            "conflict", "Conflict", "overlap", "Overlap",
            "already has an appointment",
        ])
        assert has_conflict_check, (
            "AppointmentService should implement scheduling conflict detection"
        )

    def test_service_validates_business_hours(self):
        """Verify that AppointmentService enforces business hours (08:00-18:00)"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "AppointmentService.java")
        with open(path, "r") as f:
            content = f.read()

        has_business_hours = any(kw in content for kw in [
            "08:00", "18:00", "8, 0", "18, 0",
            "business hours", "BUSINESS_HOURS",
            "LocalTime.of(8", "LocalTime.of(18",
        ])
        assert has_business_hours, (
            "AppointmentService should validate business hours (08:00-18:00)"
        )

    def test_controller_has_required_endpoints(self):
        """Verify that AppointmentController defines all required REST endpoints"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "AppointmentController.java")
        with open(path, "r") as f:
            content = f.read()

        # Check for REST controller annotation
        assert "@RestController" in content, (
            "AppointmentController should be annotated with @RestController"
        )

        # Check for endpoint mappings
        assert "@PostMapping" in content or "POST" in content, (
            "Controller missing POST endpoint for creating appointments"
        )
        assert "@GetMapping" in content or "GET" in content, (
            "Controller missing GET endpoint for retrieving appointments"
        )
        assert "@PatchMapping" in content or "cancel" in content.lower(), (
            "Controller missing PATCH endpoint for cancellation"
        )

    def test_create_appointment_request_has_validation(self):
        """Verify that CreateAppointmentRequest DTO has validation annotations"""
        path = os.path.join(self.REPO_DIR, self.APPOINTMENT_PKG, "CreateAppointmentRequest.java")
        with open(path, "r") as f:
            content = f.read()

        # Check for required fields
        required_fields = ["petId", "vetId", "appointmentDate", "startTime",
                          "endTime", "reason"]
        for field in required_fields:
            assert field in content, (
                f"CreateAppointmentRequest missing required field: {field}"
            )

        # Check for validation annotations
        has_validation = any(ann in content for ann in [
            "@NotNull", "@NotBlank", "@FutureOrPresent", "@Valid",
            "jakarta.validation", "javax.validation",
        ])
        assert has_validation, (
            "CreateAppointmentRequest should have validation annotations"
        )

    # === Functional Checks (Service Tests & Build) ===

    def test_schema_sql_updated_with_appointments_table(self):
        """Verify that H2 schema.sql has been updated with the appointments table"""
        path = os.path.join(self.REPO_DIR, "src/main/resources/db/h2/schema.sql")
        with open(path, "r") as f:
            content = f.read().lower()

        assert "appointments" in content, (
            "schema.sql missing appointments table definition"
        )
        # Verify table has correct columns
        assert "appointment_date" in content or "appointmentdate" in content, (
            "appointments table missing appointment_date column"
        )
        assert "start_time" in content or "starttime" in content, (
            "appointments table missing start_time column"
        )
        assert "status" in content, "appointments table missing status column"

    def test_data_sql_has_sample_appointments(self):
        """Verify that data.sql includes sample appointment data"""
        path = os.path.join(self.REPO_DIR, "src/main/resources/db/h2/data.sql")
        with open(path, "r") as f:
            content = f.read().lower()

        assert "appointments" in content, (
            "data.sql missing sample appointment INSERT statements"
        )

    def test_service_test_file_exists_and_uses_mockito(self):
        """Verify that service unit test uses Mockito for mocking"""
        path = os.path.join(self.REPO_DIR, self.TEST_PKG, "AppointmentServiceTest.java")
        assert os.path.exists(path), f"AppointmentServiceTest.java not found at {path}"

        with open(path, "r") as f:
            content = f.read()

        assert "Mockito" in content or "@Mock" in content or "mock" in content.lower(), (
            "Service test should use Mockito for mocking repository"
        )
        # Check for conflict detection test
        assert "conflict" in content.lower() or "overlap" in content.lower(), (
            "Service test should test scheduling conflict detection"
        )

    def test_controller_test_file_exists_and_uses_mockmvc(self):
        """Verify that controller test uses MockMvc for web layer testing"""
        path = os.path.join(self.REPO_DIR, self.TEST_PKG, "AppointmentControllerTest.java")
        assert os.path.exists(path), f"AppointmentControllerTest.java not found at {path}"

        with open(path, "r") as f:
            content = f.read()

        assert "MockMvc" in content, (
            "Controller test should use MockMvc for web layer testing"
        )
        # Check for status code assertions
        assert "201" in content or "Created" in content or "isCreated" in content, (
            "Controller test should verify 201 Created status"
        )
        assert "409" in content or "Conflict" in content or "isConflict" in content, (
            "Controller test should verify 409 Conflict status"
        )

    def test_repository_test_file_exists_and_uses_datajpatest(self):
        """Verify that repository test uses @DataJpaTest annotation"""
        path = os.path.join(self.REPO_DIR, self.TEST_PKG, "AppointmentRepositoryTest.java")
        assert os.path.exists(path), f"AppointmentRepositoryTest.java not found at {path}"

        with open(path, "r") as f:
            content = f.read()

        assert "@DataJpaTest" in content, (
            "Repository test should use @DataJpaTest annotation"
        )

    def test_project_compiles_successfully(self):
        """Verify that the project compiles with ./mvnw compile -DskipTests"""
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"Maven compile failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        )

    def test_service_cancellation_logic_in_tests(self):
        """Verify that service tests include cancellation logic tests"""
        path = os.path.join(self.REPO_DIR, self.TEST_PKG, "AppointmentServiceTest.java")
        with open(path, "r") as f:
            content = f.read()

        assert "cancel" in content.lower(), (
            "Service test should include cancellation logic tests"
        )
        assert "CANCELLED" in content or "cancelled" in content.lower(), (
            "Service test should verify appointment status changes to CANCELLED"
        )
