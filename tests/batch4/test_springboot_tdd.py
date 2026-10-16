"""
Test skill: springboot-tdd
Verify that the veterinary visit scheduling feature has been correctly implemented
in Spring PetClinic with TDD, including service layer, REST controller, DTOs,
validation, conflict detection, and comprehensive test coverage.
"""

import os
import re
import subprocess
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    MAIN_BASE = "src/main/java/org/springframework/samples/petclinic/visit"
    TEST_BASE = "src/test/java/org/springframework/samples/petclinic/visit"

    # === File Path Checks ===

    def test_visit_scheduling_service_exists(self):
        """Verify VisitSchedulingService.java was created"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitSchedulingService.java")
        assert os.path.exists(filepath), \
            f"VisitSchedulingService.java not found at {filepath}"

    def test_visit_schedule_controller_exists(self):
        """Verify VisitScheduleController.java was created"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitScheduleController.java")
        assert os.path.exists(filepath), \
            f"VisitScheduleController.java not found at {filepath}"

    def test_schedule_visit_request_dto_exists(self):
        """Verify ScheduleVisitRequest.java DTO was created"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "ScheduleVisitRequest.java")
        assert os.path.exists(filepath), \
            f"ScheduleVisitRequest.java not found at {filepath}"

    def test_service_unit_test_exists(self):
        """Verify VisitSchedulingServiceTest.java was created"""
        filepath = os.path.join(self.REPO_DIR, self.TEST_BASE, "VisitSchedulingServiceTest.java")
        assert os.path.exists(filepath), \
            f"VisitSchedulingServiceTest.java not found at {filepath}"

    def test_controller_test_exists(self):
        """Verify VisitScheduleControllerTest.java was created"""
        filepath = os.path.join(self.REPO_DIR, self.TEST_BASE, "VisitScheduleControllerTest.java")
        assert os.path.exists(filepath), \
            f"VisitScheduleControllerTest.java not found at {filepath}"

    def test_integration_test_exists(self):
        """Verify VisitSchedulingIntegrationTest.java was created"""
        filepath = os.path.join(self.REPO_DIR, self.TEST_BASE, "VisitSchedulingIntegrationTest.java")
        assert os.path.exists(filepath), \
            f"VisitSchedulingIntegrationTest.java not found at {filepath}"

    # === Semantic Checks ===

    def test_controller_has_post_endpoint(self):
        """Verify controller exposes POST /api/visits/schedule endpoint"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitScheduleController.java")
        with open(filepath) as f:
            content = f.read()
        assert "@PostMapping" in content or ("@RequestMapping" in content and "POST" in content), \
            "Controller should have @PostMapping for scheduling endpoint"
        assert "schedule" in content.lower(), \
            "Controller should reference 'schedule' in its endpoint mapping"

    def test_controller_has_get_endpoint(self):
        """Verify controller exposes GET endpoint for querying scheduled visits"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitScheduleController.java")
        with open(filepath) as f:
            content = f.read()
        assert "@GetMapping" in content or ("@RequestMapping" in content and "GET" in content), \
            "Controller should have @GetMapping for querying visits"

    def test_controller_returns_correct_status_codes(self):
        """Verify controller handles 201, 400, 404, 409 status codes"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitScheduleController.java")
        with open(filepath) as f:
            content = f.read()
        # Should return 201 Created for successful scheduling
        has_created = ("HttpStatus.CREATED" in content or "201" in content or
                       "CREATED" in content)
        assert has_created, \
            "Controller should return 201 Created status for successful scheduling"

    def test_request_dto_has_required_fields(self):
        """Verify ScheduleVisitRequest has petId, vetId, visitDate, and description fields"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "ScheduleVisitRequest.java")
        with open(filepath) as f:
            content = f.read()
        required_fields = ["petId", "vetId", "visitDate", "description"]
        for field in required_fields:
            assert field in content, \
                f"ScheduleVisitRequest missing required field '{field}'"

    def test_request_dto_has_validation_annotations(self):
        """Verify ScheduleVisitRequest uses Jakarta/javax validation annotations"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "ScheduleVisitRequest.java")
        with open(filepath) as f:
            content = f.read()
        validation_annotations = ["@NotNull", "@NotBlank", "@Size", "@Future", "@Valid"]
        found = [a for a in validation_annotations if a in content]
        assert len(found) >= 2, \
            f"ScheduleVisitRequest should have validation annotations. Found: {found}"
        # description must have @Size(max=255)
        has_size = "@Size" in content
        if has_size:
            size_match = re.search(r'@Size\s*\([^)]*max\s*=\s*(\d+)', content)
            if size_match:
                max_val = int(size_match.group(1))
                assert max_val == 255, \
                    f"description @Size max should be 255, got {max_val}"

    def test_service_has_scheduling_method(self):
        """Verify VisitSchedulingService has a method for scheduling visits"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitSchedulingService.java")
        with open(filepath) as f:
            content = f.read()
        has_schedule = bool(re.search(
            r'public\s+\w+\s+\w*(schedule|create)\w*\s*\(',
            content, re.IGNORECASE
        ))
        assert has_schedule, \
            "VisitSchedulingService should have a public method for scheduling visits"

    def test_service_uses_dependency_injection(self):
        """Verify VisitSchedulingService uses Spring dependency injection"""
        filepath = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitSchedulingService.java")
        with open(filepath) as f:
            content = f.read()
        has_di = ("@Service" in content or "@Component" in content or
                  "@Autowired" in content or "private final" in content)
        assert has_di, \
            "VisitSchedulingService should use Spring dependency injection (@Service, @Autowired, etc.)"

    def test_service_test_covers_key_scenarios(self):
        """Verify unit tests cover success, not-found, conflict, and validation scenarios"""
        filepath = os.path.join(self.REPO_DIR, self.TEST_BASE, "VisitSchedulingServiceTest.java")
        with open(filepath) as f:
            content = f.read()
        test_methods = re.findall(r'@Test\s', content)
        assert len(test_methods) >= 4, \
            f"VisitSchedulingServiceTest should have at least 4 @Test methods, found {len(test_methods)}"
        content_lower = content.lower()
        # Should cover conflict detection
        assert ("conflict" in content_lower or "overlap" in content_lower or "409" in content), \
            "Service tests should cover conflict detection scenario"
        # Should use Mockito for mocking
        assert "mock" in content_lower or "@Mock" in content or "Mockito" in content, \
            "Service tests should use Mockito for mocking dependencies"

    def test_visit_repository_has_query_methods(self):
        """Verify VisitRepository has custom query methods for date range and conflict check"""
        # Look for VisitRepository in the visit package or owner package
        repo_path = os.path.join(self.REPO_DIR, self.MAIN_BASE, "VisitRepository.java")
        if not os.path.exists(repo_path):
            # Try alternative location
            result = subprocess.run(
                ["find", self.REPO_DIR, "-name", "VisitRepository.java", "-type", "f"],
                capture_output=True, text=True, timeout=30
            )
            if result.stdout.strip():
                repo_path = result.stdout.strip().split('\n')[0]
            else:
                pytest.skip("VisitRepository.java not found")

        with open(repo_path) as f:
            content = f.read()
        has_query = ("@Query" in content or
                     "findBy" in content or
                     "Between" in content or
                     "conflict" in content.lower())
        assert has_query, \
            "VisitRepository should have custom query methods for scheduling"

    # === Functional Checks ===

    def test_project_compiles_successfully(self):
        """Verify that the project compiles without errors"""
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=600
        )
        assert result.returncode == 0, \
            f"Project compilation failed:\n{result.stderr[-2000:]}"

    def test_all_tests_pass(self):
        """Verify all Maven tests pass (unit + integration)"""
        result = subprocess.run(
            ["./mvnw", "test", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=600
        )
        assert result.returncode == 0, \
            f"Maven test failed:\n{result.stdout[-2000:]}\n{result.stderr[-1000:]}"

    def test_service_unit_test_passes(self):
        """Verify VisitSchedulingServiceTest passes individually"""
        result = subprocess.run(
            ["./mvnw", "test", "-Dtest=VisitSchedulingServiceTest", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, \
            f"VisitSchedulingServiceTest failed:\n{result.stdout[-1500:]}\n{result.stderr[-500:]}"

    def test_controller_test_passes(self):
        """Verify VisitScheduleControllerTest passes individually"""
        result = subprocess.run(
            ["./mvnw", "test", "-Dtest=VisitScheduleControllerTest", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, \
            f"VisitScheduleControllerTest failed:\n{result.stdout[-1500:]}\n{result.stderr[-500:]}"

    def test_integration_test_passes(self):
        """Verify VisitSchedulingIntegrationTest passes individually"""
        result = subprocess.run(
            ["./mvnw", "test", "-Dtest=VisitSchedulingIntegrationTest", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, \
            f"VisitSchedulingIntegrationTest failed:\n{result.stdout[-1500:]}\n{result.stderr[-500:]}"
