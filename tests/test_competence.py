"""Tests for the competence audit: taxonomy, evidence statuses, coverages, two-pass
screening, semantic-gap rule, reports, human review and the optional similarity layer."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from modules import reports
from modules.audit import AuditEngine
from modules.candidate import Candidate
from modules.competence import CompetenceAuditEngine
from modules.data_manager import DataManager
from modules.exceptions import DataFileError, ValidationError
from modules.job import JobRole
from modules.screening_engine import ScreeningConfig
from modules.semantic_matcher import SemanticMatcher
from modules.taxonomy import SkillTaxonomy

TAXONOMY = SkillTaxonomy({
    "python": {"label": "Python", "terms": ["python", "python programming"]},
    "machine_learning": {"label": "Machine Learning", "terms": ["machine learning", "ml", "predictive modeling"],
                         "related": ["scikit-learn"]},
    "scikit_learn": {"label": "Scikit-learn", "terms": ["scikit-learn", "sklearn"]},
    "sql": {"label": "SQL", "terms": ["sql"], "related": ["postgresql", "mysql"]},
    "postgresql": {"label": "PostgreSQL", "terms": ["postgresql", "postgres"]},
    "docker": {"label": "Docker", "terms": ["docker", "docker compose"]},
    "rest_apis": {"label": "REST APIs", "terms": ["rest apis", "restful apis"]},
})
TRADITIONAL = ScreeningConfig.create("T", "Traditional", {"skills": 60, "experience": 25, "education": 15})


def job(**overrides) -> JobRole:
    fields = dict(job_id="J1", title="ML Engineer", required_skills="Python, Machine Learning, SQL, Docker",
                  min_experience=0, min_education="Bachelor's")
    fields.update(overrides)
    return JobRole(**fields)


def candidate(**overrides) -> Candidate:
    fields = dict(candidate_id="C1", name="Meera Joshi", email="meera@example.com", experience_years=2,
                  education_level="Bachelor's", degree="B.Tech", skills="Python, ML, PostgreSQL")
    fields.update(overrides)
    return Candidate(**fields)


class TaxonomyTests(unittest.TestCase):
    def test_synonym_related_and_direction(self):
        self.assertEqual(TAXONOMY.compare("Machine Learning", "ML"), "synonym")
        self.assertEqual(TAXONOMY.compare("SQL", "PostgreSQL"), "related")
        self.assertIsNone(TAXONOMY.compare("PostgreSQL", "SQL"))        # related is one-directional
        self.assertEqual(TAXONOMY.compare("Python", " python "), "exact")

    def test_app_spelling_aliases_are_merged(self):
        self.assertEqual(TAXONOMY.compare("Scikit-learn", "scikit learn"), "synonym")   # from validator aliases

    def test_text_search_uses_word_boundaries_and_skips_short_terms(self):
        self.assertIsNotNone(TAXONOMY.find_in_text("Docker", "Deployed with Docker Compose."))
        self.assertIsNone(TAXONOMY.find_in_text("SQL", "Tuned PostgreSQLx builds"))       # not a whole word
        self.assertIsNone(TAXONOMY.find_in_text("Machine Learning", "used ML daily"))     # 'ml' too short for text

    def test_invalid_taxonomy_is_reported(self):
        for bad in [{"x": {"label": "X"}},                                            # no terms
                    {"a": {"label": "A", "terms": ["same"]}, "b": {"label": "B", "terms": ["same"]}},
                    {"c": "not an object"}]:
            with self.subTest(entries=bad), self.assertRaises(DataFileError):
                SkillTaxonomy(bad)

    def test_malformed_taxonomy_file_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "skills_taxonomy.json").write_text("{ broken", encoding="utf-8")
            manager = DataManager(Path(tmp))
            self.assertIn("taxonomy", manager.load_errors)
            self.assertFalse(manager.taxonomy_loaded)
            with self.assertRaises(DataFileError):
                manager.reset_file("taxonomy")          # hand-edited reference data is never overwritten


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = CompetenceAuditEngine(TAXONOMY, TRADITIONAL)

    def test_exact_vs_normalized_match(self):
        """The example from the brief: Python/ML/PostgreSQL against Python/ML/SQL/Docker."""
        result = self.engine.assess(candidate(), job())
        self.assertEqual(result.vocabulary_match, 25.0)       # 1 of 4: Python
        self.assertEqual(result.normalized_match, 75.0)       # 3 of 4: + ML (synonym), SQL (related)
        self.assertEqual([s.skill for s in result.missed_by_exact], ["Machine Learning", "SQL", "Docker"])
        self.assertEqual([s.skill for s in result.unsupported], ["Docker"])

    def test_statuses(self):
        c = candidate(projects=[{"project_name": "Churn model", "technologies": "Python; Scikit-learn",
                                 "description": "A machine learning model for churn.", "outcomes": ""}])
        status = {s.skill: s.status for s in self.engine.assess(c, job()).skills}
        self.assertEqual(status, {"Python": "EXPLICIT", "Machine Learning": "SUPPORTED",
                                  "SQL": "RELATED", "Docker": "MISSING"})

    def test_project_text_and_experience_summary_count_as_evidence(self):
        c = candidate(skills="Python", experience_summary="Two years deploying services with Docker.",
                      projects=[{"project_name": "API", "technologies": "Python",
                                 "description": "Queried Postgres tables", "outcomes": "Used predictive modeling"}])
        result = self.engine.assess(c, job())
        by_skill = {s.skill: s for s in result.skills}
        self.assertEqual(by_skill["Docker"].status, "SUPPORTED")
        self.assertEqual(by_skill["Docker"].sources[0].place, "Experience summary")
        self.assertEqual(by_skill["SQL"].sources[0].field, "description")
        self.assertEqual(result.evidence_coverage, 100.0)
        self.assertIn("PROJECT_EVIDENCE", {o.code for o in result.observations})

    def test_coverage_order_always_holds(self):
        result = self.engine.assess(candidate(), job())
        self.assertLessEqual(result.vocabulary_match, result.normalized_match)
        self.assertLessEqual(result.normalized_match, result.evidence_coverage)


class GapAndPassTests(unittest.TestCase):
    def setUp(self):
        self.engine = CompetenceAuditEngine(TAXONOMY, TRADITIONAL)

    def test_semantic_gap_rule_and_signal(self):
        c = candidate(skills="python programming, ML, Postgres",
                      projects=[{"project_name": "Deploy", "technologies": "Docker"}])
        result = self.engine.assess(c, job())
        self.assertEqual((result.vocabulary_match, result.evidence_coverage), (0.0, 100.0))
        self.assertTrue(result.semantic_gap)
        self.assertEqual(result.signal, "Review recommended")

    def test_consistent_and_limited_signals(self):
        exact = candidate(skills="Python, Machine Learning, SQL, Docker")
        self.assertEqual(self.engine.assess(exact, job()).signal, "Consistent")
        thin = candidate(skills="Excel")
        self.assertEqual(self.engine.assess(thin, job()).signal, "Limited evidence")

    def test_two_pass_scores_use_the_baseline_weights(self):
        result = self.engine.assess(candidate(), job())
        # exact pass: skills 25% x 60 + experience 25 + education 15 = 55
        self.assertEqual(result.exact_pass_score, 55.0)
        # evidence pass: skills 75% x 60 + 25 + 15 = 85
        self.assertEqual(result.evidence_pass_score, 85.0)
        self.assertEqual(result.pass_difference, 30.0)

    def test_neutral_language(self):
        c = candidate(skills="ML", projects=[{"project_name": "X1", "technologies": "Docker"}])
        text = " ".join(o.title + o.text for o in self.engine.assess(c, job()).observations).lower()
        for word in ("reject", "hire", "unfair", "discriminat", "qualified"):
            self.assertNotIn(word, text)
        self.assertNotRegex(text, r"\bats\b")      # FairLens does not know what any ATS did

    def test_frame_and_numpy_statistics(self):
        results = [self.engine.assess(candidate(), job()),
                   self.engine.assess(candidate(candidate_id="C2", email="b@example.com",
                                                skills="Python, Machine Learning, SQL, Docker"), job())]
        frame = CompetenceAuditEngine.frame(results)
        stats = CompetenceAuditEngine.statistics(frame)
        self.assertEqual(list(frame["vocabulary_match"]), [25.0, 100.0])
        # gaps (evidence - vocabulary): 75 - 25 = 50 and 100 - 100 = 0
        self.assertAlmostEqual(stats["mean_gap"], float(np.mean([50, 0])))
        self.assertEqual(stats["semantic_gaps"], int(frame["semantic_gap"].sum()))


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "skills_taxonomy.json").write_text(json.dumps({"skills": {
            "machine_learning": {"label": "Machine Learning", "terms": ["machine learning", "ml"]},
            "sql": {"label": "SQL", "terms": ["sql"], "related": ["postgresql"]},
        }}), encoding="utf-8")
        self.manager = DataManager(root)
        role = self.manager.create_job(title="ML Engineer", required_skills="Python, Machine Learning, SQL, Docker",
                                       min_experience=0, min_education="Bachelor's")
        self.manager.add_candidate(candidate(target_job_id=role.job_id))

    def tearDown(self):
        self._tmp.cleanup()

    def test_audit_includes_competence_columns_and_observations(self):
        m = self.manager
        report = AuditEngine(m.baseline, m.alternative, list(m.configs.values())).run(m)
        row = report.table.iloc[0]
        self.assertEqual((row["vocabulary_match"], row["normalized_match"]), (25.0, 75.0))
        self.assertIn("semantic_gaps", report.summary)
        self.assertIn("evidence_coverage", report.to_csv_frame().columns)
        self.assertIn("WORDING_MISMATCH", {o.code for o in report.observations["C1"]})

    def test_deep_audit_report_is_generated_from_data(self):
        m = self.manager
        result = CompetenceAuditEngine(m.taxonomy, m.baseline).assess(m.candidates["C1"], next(iter(m.jobs.values())))
        text = reports.competence_report(m.candidates["C1"], result, spread=12.5)
        self.assertIn("Exact match          25.0%", text)
        self.assertIn("Normalized match     75.0%", text)
        self.assertIn("Missing skills       Docker", text)
        self.assertIn("12.5 points", text)

    def test_human_review_is_recorded_and_validated(self):
        self.manager.record_review("C1", "Possible fit", "Checked the project repository.")
        reloaded = DataManager(Path(self._tmp.name))
        self.assertEqual(reloaded.get_candidate("C1").review["assessment"], "Possible fit")
        self.assertEqual(reloaded.get_candidate("C1").notes, "Checked the project repository.")
        with self.assertRaises(ValidationError):
            self.manager.record_review("C1", "Hire", "")

    def test_legacy_project_keys_still_load(self):
        c = candidate(projects=[{"title": "Old", "skills": ["SQL"], "summary": "From v2 data"}])
        self.assertEqual(c.projects[0]["project_name"], "Old")
        self.assertEqual(c.projects[0]["description"], "From v2 data")


class SemanticMatcherTests(unittest.TestCase):
    def test_similarity_hints_are_separate_from_scores(self):
        c = candidate(skills="Python, Postgre SQL")
        role = job(required_skills="Python, PostgreSQL")
        plain = CompetenceAuditEngine(TAXONOMY, TRADITIONAL).assess(c, role)
        hinted = CompetenceAuditEngine(TAXONOMY, TRADITIONAL, semantic=SemanticMatcher()).assess(c, role)
        self.assertEqual(plain.evidence_coverage, hinted.evidence_coverage)    # hints never change figures
        self.assertEqual(hinted.hints[0][:2], ("PostgreSQL", "Postgre SQL"))

    def test_cosine_similarity_matrix(self):
        matrix = SemanticMatcher().similarity(["docker"], ["docker", "excel"])
        self.assertAlmostEqual(matrix[0, 0], 1.0)
        self.assertLess(matrix[0, 1], 0.2)


if __name__ == "__main__":
    unittest.main()
