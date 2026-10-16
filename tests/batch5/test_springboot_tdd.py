"""
Test skill: springboot-tdd
Verify that the Agent correctly adds a Medication resource with TDD
to the Spring PetClinic application.
"""

import os
import re
import subprocess
import pytest


class TestSpringbootTdd:
    REPO_DIR = "/workspace/spring-petclinic"

    MEDICATION_ENTITY = "src/main/java/org/springframework/samples/petclinic/medication/Medication.java"
    MEDICATION_REPO = "src/main/java/org/springframework/samples/petclinic/medication/MedicationRepository.java"
    MEDICATION_CONTROLLER = "src/main/java/org/springframework/samples/petclinic/medication/MedicationController.java"
    CONTROLLER_TEST = "src/test/java/org/springframework/samples/petclinic/medication/MedicationControllerTests.java"
    REPO_TEST = "src/test/java/org/springframework/samples/petclinic/medication/MedicationRepositoryTests.java"
    DATA_SQL = "src/main/resources/db/h2/data.sql"
    LIST_TEMPLATE = "src/main/resources/templates/medications/medicationList.html"
    FORM_TEMPLATE = "src/main/resources/templates/medications/createOrUpdateMedicationForm.html"

    def _read_file(self, rel_path):
        filepath = os.path.join(self.REPO_DIR, rel_path)
        with open(filepath) as f:
            return f.read()

    # === File Path Checks ===

    def test_medication_entity_exists(self):
        """Verify Medication.java entity file exists"""
        filepath = os.path.join(self.REPO_DIR, self.MEDICATION_ENTITY)
        assert os.path.exists(filepath), f"Medication.java not found at {filepath}"

    def test_medication_repository_exists(self):
        """Verify MedicationRepository.java exists"""
        filepath = os.path.join(self.REPO_DIR, self.MEDICATION_REPO)
        assert os.path.exists(filepath), f"MedicationRepository.java not found at {filepath}"

    def test_medication_controller_exists(self):
        """Verify MedicationController.java exists"""
        filepath = os.path.join(self.REPO_DIR, self.MEDICATION_CONTROLLER)
        assert os.path.exists(filepath), f"MedicationController.java not found at {filepath}"

    def test_controller_test_exists(self):
        """Verify MedicationControllerTests.java exists (TDD: tests written first)"""
        filepath = os.path.join(self.REPO_DIR, self.CONTROLLER_TEST)
        assert os.path.exists(filepath), f"Controller test file not found at {filepath}"

    def test_repository_test_exists(self):
        """Verify MedicationRepositoryTests.java exists"""
        filepath = os.path.join(self.REPO_DIR, self.REPO_TEST)
        assert os.path.exists(filepath), f"Repository test file not found at {filepath}"

    # === Semantic Checks ===

    def test_medication_entity_has_jpa_annotations(self):
        """Verify Medication.java has @Entity and required JPA annotations"""
        content = self._read_file(self.MEDICATION_ENTITY)
        assert "@Entity" in content, "Medication.java missing @Entity annotation"
        assert "@ManyToOne" in content, \
            "Medication.java missing @ManyToOne for Pet relationship"

    def test_medication_entity_has_required_fields(self):
        """Verify Medication entity has all required fields"""
        content = self._read_file(self.MEDICATION_ENTITY)
        required_fields = ["name", "dosage", "frequency", "startDate", "endDate"]
        for field in required_fields:
            pattern = rf'(private|protected)\s+\w+\s+{field}\b'
            assert re.search(pattern, content), \
                f"Medication.java missing field: {field}"

    def test_medication_entity_has_validation_constraints(self):
        """Verify Medication entity has validation annotations"""
        content = self._read_file(self.MEDICATION_ENTITY)
        has_not_blank = "@NotBlank" in content or "@NotEmpty" in content
        has_not_null = "@NotNull" in content
        assert has_not_blank, \
            "Medication.java missing @NotBlank/@NotEmpty for required string fields"
        assert has_not_null, \
            "Medication.java missing @NotNull for startDate"

    def test_medication_repository_has_custom_queries(self):
        """Verify MedicationRepository has findByPetId and findActiveMedications"""
        content = self._read_file(self.MEDICATION_REPO)
        assert "findByPetId" in content, \
            "MedicationRepository missing findByPetId method"
        has_active = "findActiveMedication" in content or "findActive" in content
        assert has_active, \
            "MedicationRepository missing findActiveMedications query"

    def test_medication_repository_has_query_annotation(self):
        """Verify findActiveMedications uses @Query with correct JPQL/HQL"""
        content = self._read_file(self.MEDICATION_REPO)
        assert "@Query" in content, \
            "MedicationRepository missing @Query annotation for custom query"
        # Verify the query filters by endDate and petId
        has_end_date_filter = bool(re.search(
            r'endDate\s+(IS NULL|is null|>=|>)', content
        ))
        assert has_end_date_filter, \
            "@Query for active medications should filter on endDate IS NULL or >= currentDate"

    def test_controller_maps_medication_endpoints(self):
        """Verify MedicationController has correct request mappings"""
        content = self._read_file(self.MEDICATION_CONTROLLER)
        assert "medications" in content, \
            "Controller missing 'medications' in URL mapping"
        has_get = bool(re.search(r'@GetMapping|@RequestMapping.*GET', content))
        has_post = bool(re.search(r'@PostMapping|@RequestMapping.*POST', content))
        assert has_get, "Controller missing GET mapping for medication list/form"
        assert has_post, "Controller missing POST mapping for medication creation"

    def test_data_sql_has_medication_inserts(self):
        """Verify data.sql has sample medication data inserted"""
        content = self._read_file(self.DATA_SQL)
        content_lower = content.lower()
        assert "medication" in content_lower, \
            "data.sql missing medication INSERT statements"
        inserts = re.findall(
            r'INSERT\s+INTO\s+medication', content, re.IGNORECASE
        )
        assert len(inserts) >= 3, \
            f"Expected at least 3 medication inserts in data.sql, found {len(inserts)}"

    def test_templates_exist(self):
        """Verify Thymeleaf templates for medication list and form exist"""
        list_path = os.path.join(self.REPO_DIR, self.LIST_TEMPLATE)
        form_path = os.path.join(self.REPO_DIR, self.FORM_TEMPLATE)
        assert os.path.exists(list_path), \
            f"Medication list template not found at {list_path}"
        assert os.path.exists(form_path), \
            f"Medication form template not found at {form_path}"

    # === Functional Checks ===

    def test_maven_compile_succeeds(self):
        """Verify the project compiles successfully with Maven"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        cmd = ["./mvnw", "compile", "-DskipTests", "-q"]
        if not os.path.exists(mvnw):
            cmd = ["mvn", "compile", "-DskipTests", "-q"]
        result = subprocess.run(
            cmd,
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, \
            f"Maven compile failed: {result.stderr[-500:]}"

    def test_maven_tests_pass(self):
        """Verify all tests pass including new medication tests"""
        mvnw = os.path.join(self.REPO_DIR, "mvnw")
        cmd = ["./mvnw", "test", "-q"]
        if not os.path.exists(mvnw):
            cmd = ["mvn", "test", "-q"]
        result = subprocess.run(
            cmd,
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, \
            f"Maven tests failed: {result.stdout[-500:]}\n{result.stderr[-500:]}"

    def test_controller_test_covers_validation(self):
        """Verify controller test file covers validation error scenarios"""
        content = self._read_file(self.CONTROLLER_TEST)
        assert "@Test" in content, "Controller test file missing @Test annotations"
        test_methods = re.findall(r'(public|void)\s+test\w+', content, re.IGNORECASE)
        assert len(test_methods) >= 3, \
            f"Expected at least 3 test methods in controller tests, found {len(test_methods)}"
        # Check for validation error testing
        has_validation_test = bool(re.search(
            r'(validation|error|invalid|blank|BadRequest)', content, re.IGNORECASE
        ))
        assert has_validation_test, \
            "Controller tests missing validation error scenarios"
