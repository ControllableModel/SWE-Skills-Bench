"""
Test skill: springboot-tdd
Verify that the Agent correctly implements a Pet Vaccination Tracking feature
using TDD for Spring PetClinic.
"""

import os
import subprocess
import json
import re
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    # === File Path Checks ===

    def test_vaccination_entity_exists(self):
        """Verify that the Vaccination entity Java file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/Vaccination.java"
        )
        assert os.path.exists(path), f"Vaccination.java not found at {path}"

    def test_vaccination_repository_exists(self):
        """Verify that the VaccinationRepository interface file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/VaccinationRepository.java"
        )
        assert os.path.exists(path), f"VaccinationRepository.java not found at {path}"

    def test_vaccination_service_exists(self):
        """Verify that the VaccinationService file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/VaccinationService.java"
        )
        assert os.path.exists(path), f"VaccinationService.java not found at {path}"

    def test_vaccination_controller_exists(self):
        """Verify that the VaccinationController file exists"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/VaccinationController.java"
        )
        assert os.path.exists(path), f"VaccinationController.java not found at {path}"

    # === Semantic Checks ===

    def test_vaccination_entity_has_jpa_annotations(self):
        """Verify Vaccination entity uses JPA annotations (Entity, Id, ManyToOne)"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/Vaccination.java"
        )
        with open(path) as f:
            content = f.read()
        assert "@Entity" in content, "Vaccination.java missing @Entity annotation"
        assert "@Id" in content, "Vaccination.java missing @Id annotation"
        assert "@ManyToOne" in content or "ManyToOne" in content, \
            "Vaccination.java missing @ManyToOne relationship to Pet"

    def test_vaccination_entity_has_required_fields(self):
        """Verify Vaccination entity has all required fields"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/Vaccination.java"
        )
        with open(path) as f:
            content = f.read()
        required_fields = [
            "vaccineName", "vaccineType", "dateAdministered",
            "expirationDate", "batchNumber", "veterinarian"
        ]
        for field in required_fields:
            assert field in content, \
                f"Vaccination.java missing required field: {field}"

    def test_vaccination_entity_has_bean_validation(self):
        """Verify Vaccination entity uses bean validation annotations"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/Vaccination.java"
        )
        with open(path) as f:
            content = f.read()
        # Should have validation annotations
        validation_annotations = ["@NotNull", "@NotBlank", "@NotEmpty", "@Size", "@Pattern"]
        found = sum(1 for ann in validation_annotations if ann in content)
        assert found >= 2, \
            f"Vaccination.java should have bean validation annotations, found {found}"

    def test_vaccination_entity_has_batch_number_pattern(self):
        """Verify batchNumber field has pattern validation [A-Z]{2}[0-9]{6}"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/Vaccination.java"
        )
        with open(path) as f:
            content = f.read()
        assert "@Pattern" in content, "Missing @Pattern annotation for batchNumber"
        assert "[A-Z]" in content and "[0-9]" in content, \
            "batchNumber pattern should validate format [A-Z]{2}[0-9]{6}"

    def test_controller_has_rest_endpoints(self):
        """Verify VaccinationController defines required REST endpoints"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/VaccinationController.java"
        )
        with open(path) as f:
            content = f.read()
        assert "@RestController" in content or "@Controller" in content, \
            "Controller missing @RestController annotation"
        # Check for endpoint mappings
        assert "@GetMapping" in content or "@RequestMapping" in content, \
            "Controller missing GET endpoint mappings"
        assert "@PostMapping" in content, "Controller missing POST endpoint mapping"
        # Check for pet-based URL paths
        assert "petId" in content or "pet" in content.lower(), \
            "Controller should have pet-scoped endpoints"

    def test_controller_has_status_and_report_endpoints(self):
        """Verify controller has status and report endpoint methods"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/VaccinationController.java"
        )
        with open(path) as f:
            content = f.read()
        assert "status" in content.lower(), \
            "Controller missing status endpoint"
        assert "report" in content.lower(), \
            "Controller missing report endpoint"

    def test_service_has_business_logic_methods(self):
        """Verify VaccinationService has key business methods"""
        path = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/vaccination/VaccinationService.java"
        )
        with open(path) as f:
            content = f.read()
        # Check for main methods
        method_patterns = ["addVaccination", "getVaccinationStatus", "generateReport"]
        found_methods = [m for m in method_patterns if m in content]
        assert len(found_methods) >= 2, \
            f"Service should have business methods like addVaccination, getVaccinationStatus, generateReport. Found: {found_methods}"

    # === Functional Checks ===

    def test_project_compiles(self):
        """Verify the project compiles successfully with mvnw"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        if not os.path.exists(mvnw):
            pytest.skip("mvnw not found")
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=600
        )
        assert result.returncode == 0, \
            f"Project compilation failed:\n{result.stdout[:1000]}\n{result.stderr[:1000]}"

    def test_controller_tests_exist_and_use_mockmvc(self):
        """Verify controller tests exist and use MockMvc"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/vaccination/VaccinationControllerTests.java"
        )
        assert os.path.exists(path), f"Controller test file not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "MockMvc" in content, "Controller tests should use MockMvc"
        assert "@WebMvcTest" in content or "@SpringBootTest" in content, \
            "Controller tests should have @WebMvcTest or @SpringBootTest"

    def test_service_tests_exist_and_use_mocks(self):
        """Verify service tests exist and use mock repository"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/vaccination/VaccinationServiceTests.java"
        )
        assert os.path.exists(path), f"Service test file not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "@Mock" in content or "Mockito" in content, \
            "Service tests should use @Mock or Mockito"
        assert "assert" in content.lower() or "Assert" in content, \
            "Service tests should contain assertions"

    def test_repository_tests_exist(self):
        """Verify repository integration tests exist"""
        path = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/vaccination/VaccinationRepositoryTests.java"
        )
        assert os.path.exists(path), f"Repository test file not found at {path}"
        with open(path) as f:
            content = f.read()
        assert "@DataJpaTest" in content or "@SpringBootTest" in content, \
            "Repository tests should use @DataJpaTest"

    def test_unit_tests_pass(self):
        """Verify that the vaccination unit tests pass"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        if not os.path.exists(mvnw):
            pytest.skip("mvnw not found")
        result = subprocess.run(
            ["./mvnw", "test", "-pl", ".",
             "-Dtest=VaccinationControllerTests,VaccinationServiceTests,VaccinationRepositoryTests",
             "-DfailIfNoTests=false", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=600
        )
        # Allow partial success - some tests might need specific DB config
        if result.returncode != 0:
            # Check if tests actually ran
            if "BUILD FAILURE" in result.stdout and "No tests were executed" in result.stdout:
                pytest.skip("No tests were executed (possible configuration issue)")
            # Check for compilation errors specifically
            assert "COMPILATION ERROR" not in result.stdout, \
                f"Test compilation failed:\n{result.stdout[:2000]}"
        assert result.returncode == 0, \
            f"Vaccination tests failed:\n{result.stdout[:2000]}\n{result.stderr[:500]}"
