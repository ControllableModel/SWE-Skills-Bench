"""
Test skill: springboot-tdd
Verify that the Agent correctly implements a Veterinary Specialty Management
REST API in the Spring PetClinic application with proper TDD practices.
"""

import os
import re
import subprocess
import json
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    # === File Path Checks ===

    def test_specialty_controller_exists(self):
        """Verify SpecialtyController.java exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyController.java"
        )
        assert os.path.isfile(fpath), f"SpecialtyController.java not found at {fpath}"

    def test_specialty_service_exists(self):
        """Verify SpecialtyService.java exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyService.java"
        )
        assert os.path.isfile(fpath), f"SpecialtyService.java not found at {fpath}"

    def test_specialty_repository_exists(self):
        """Verify SpecialtyRepository.java exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyRepository.java"
        )
        assert os.path.isfile(fpath), f"SpecialtyRepository.java not found at {fpath}"

    def test_specialty_dto_exists(self):
        """Verify SpecialtyDto.java exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyDto.java"
        )
        assert os.path.isfile(fpath), f"SpecialtyDto.java not found at {fpath}"

    def test_controller_tests_exist(self):
        """Verify SpecialtyControllerTests.java exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/specialty/SpecialtyControllerTests.java"
        )
        assert os.path.isfile(fpath), f"SpecialtyControllerTests.java not found at {fpath}"

    def test_service_tests_exist(self):
        """Verify SpecialtyServiceTests.java exists"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/specialty/SpecialtyServiceTests.java"
        )
        assert os.path.isfile(fpath), f"SpecialtyServiceTests.java not found at {fpath}"

    # === Semantic Checks ===

    def test_controller_has_crud_endpoints(self):
        """Verify SpecialtyController has GET, POST, PUT, DELETE endpoint annotations"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyController.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        assert re.search(r'@GetMapping', content), "Controller missing @GetMapping"
        assert re.search(r'@PostMapping', content), "Controller missing @PostMapping"
        assert re.search(r'@PutMapping', content), "Controller missing @PutMapping"
        assert re.search(r'@DeleteMapping', content), "Controller missing @DeleteMapping"

    def test_controller_uses_api_specialties_path(self):
        """Verify controller is mapped to /api/specialties path"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyController.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_path = bool(re.search(r'["\']/?api/specialties["\']', content))
        assert has_path, "Controller should be mapped to '/api/specialties'"

    def test_controller_returns_proper_status_codes(self):
        """Verify controller uses appropriate HTTP status codes (201, 204, 404, 409)"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyController.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_created = bool(re.search(r'(CREATED|201|HttpStatus\.CREATED)', content))
        has_no_content = bool(re.search(r'(NO_CONTENT|204|HttpStatus\.NO_CONTENT)', content))
        assert has_created, "Controller should return HTTP 201 for creation"
        assert has_no_content, "Controller should return HTTP 204 for deletion"

    def test_dto_has_name_field(self):
        """Verify SpecialtyDto has a name field"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyDto.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_name = bool(re.search(r'(String\s+name|name\s*;|getName|setName)', content))
        assert has_name, "SpecialtyDto should have a 'name' field"

    def test_dto_has_validation_annotations(self):
        """Verify SpecialtyDto has validation annotations for name field"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyDto.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_not_blank = bool(re.search(r'@NotBlank|@NotEmpty|@NotNull', content))
        has_size = bool(re.search(r'@Size|@Length', content))
        assert has_not_blank, "SpecialtyDto should have @NotBlank or @NotNull on name"
        assert has_size, "SpecialtyDto should have @Size annotation for name (2-80 chars)"

    def test_service_has_business_methods(self):
        """Verify SpecialtyService has CRUD business methods"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyService.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        methods = re.findall(r'(public|protected)\s+\w+\s+(\w+)\s*\(', content)
        method_names = [m[1] for m in methods]
        # Should have methods for find, create, update, delete
        has_find = any("find" in m.lower() or "get" in m.lower() or "all" in m.lower() for m in method_names)
        has_create = any("create" in m.lower() or "save" in m.lower() or "add" in m.lower() for m in method_names)
        has_delete = any("delete" in m.lower() or "remove" in m.lower() for m in method_names)
        assert has_find, f"Service should have a find/get method. Found: {method_names}"
        assert has_create, f"Service should have a create/save method. Found: {method_names}"
        assert has_delete, f"Service should have a delete/remove method. Found: {method_names}"

    def test_repository_extends_spring_data(self):
        """Verify SpecialtyRepository extends a Spring Data interface"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/main/java/org/springframework/samples/petclinic/specialty/SpecialtyRepository.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_extends = bool(re.search(
            r'extends\s+(JpaRepository|CrudRepository|PagingAndSortingRepository|Repository)',
            content
        ))
        assert has_extends, "SpecialtyRepository should extend a Spring Data repository interface"

    def test_controller_tests_use_mockmvc(self):
        """Verify controller tests use MockMvc for endpoint testing"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/specialty/SpecialtyControllerTests.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        assert "MockMvc" in content, "Controller tests should use MockMvc"
        assert "@Test" in content, "Controller tests should have @Test annotations"

    def test_controller_tests_cover_error_cases(self):
        """Verify controller tests include conflict and validation error scenarios"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/specialty/SpecialtyControllerTests.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_conflict = bool(re.search(r'(409|CONFLICT|conflict|duplicate)', content, re.IGNORECASE))
        has_bad_request = bool(re.search(r'(400|BAD_REQUEST|badRequest|validation)', content, re.IGNORECASE))
        has_not_found = bool(re.search(r'(404|NOT_FOUND|notFound)', content, re.IGNORECASE))
        assert has_conflict, "Controller tests should cover 409 Conflict scenario"
        assert has_bad_request, "Controller tests should cover 400 Bad Request scenario"
        assert has_not_found, "Controller tests should cover 404 Not Found scenario"

    # === Functional Checks ===

    def test_project_compiles(self):
        """Verify the project compiles successfully with mvnw"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        if not os.path.isfile(mvnw):
            pytest.skip("mvnw not found, cannot compile")
        result = subprocess.run(
            ["./mvnw", "compile", "-DskipTests", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )
        assert result.returncode == 0, f"Compilation failed: {result.stderr[-1000:]}"

    def test_all_tests_pass(self):
        """Verify all tests (new and existing) pass via mvnw test"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        if not os.path.isfile(mvnw):
            pytest.skip("mvnw not found, cannot run tests")
        result = subprocess.run(
            ["./mvnw", "test", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600
        )
        assert result.returncode == 0, (
            f"Tests failed. Last 1000 chars of stdout:\n{result.stdout[-1000:]}\n"
            f"stderr:\n{result.stderr[-1000:]}"
        )

    def test_service_tests_mock_repository(self):
        """Verify service tests use mocked repository (not integration tests)"""
        fpath = os.path.join(
            self.REPO_DIR,
            "src/test/java/org/springframework/samples/petclinic/specialty/SpecialtyServiceTests.java"
        )
        with open(fpath, "r") as f:
            content = f.read()
        has_mock = bool(re.search(r'(@Mock|@MockBean|Mockito|mock\()', content))
        assert has_mock, "Service tests should mock the repository using Mockito or @MockBean"
