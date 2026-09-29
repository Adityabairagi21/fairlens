import unittest

from modules.candidate import Candidate
from modules.job import JobRole
from modules.screening_engine import ScreeningEngine, classify_score
from modules.exceptions import ValidationError


def make_candidate(**overrides) -> Candidate:
    fields = dict(
        candidate_id="C001", name="Aarav Sharma", email="aarav@example.com",
        experience_years=2, education_level="Bachelor's", degree="B.Tech in Computer Science",
        skills="Python, SQL, pandas, Tableau",
    )
    fields.update(overrides)
    return Candidate(**fields)


def make_job(**overrides) -> JobRole:
    fields = dict(
        job_id="J001", title="Data Analyst", required_skills="Python, SQL, Pandas, Power BI",
        min_experience=2, min_education="Bachelor's",
    )
    fields.update(overrides)
    return JobRole(**fields)


class SkillMatchingTests(unittest.TestCase):
    def test_matched_missing_and_extra_skills(self):
        matched, missing, extra = ScreeningEngine.match_skills(make_candidate(), make_job())
        self.assertEqual(matched, ["Python", "SQL", "Pandas"])   # case-insensitive
        self.assertEqual(missing, ["Power BI"])
        self.assertEqual(extra, ["Tableau"])

    def test_aliases_count_as_a_match(self):
        candidate = make_candidate(skills="sklearn, JS")
        job = make_job(required_skills="Scikit-learn, JavaScript")
        matched, missing, _ = ScreeningEngine.match_skills(candidate, job)
        self.assertEqual(matched, ["Scikit-learn", "JavaScript"])
        self.assertEqual(missing, [])


class ScoreCalculationTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = ScreeningEngine()  # Traditional: 60 / 0 / 25 / 15

    def test_component_scores(self):
        self.assertEqual(ScreeningEngine.skill_score(3, 4), 75.0)
        self.assertEqual(ScreeningEngine.experience_score(1, 4), 25.0)
        self.assertEqual(ScreeningEngine.experience_score(10, 4), 100.0)   # capped
        self.assertEqual(ScreeningEngine.experience_score(0, 0), 100.0)    # no minimum
        self.assertEqual(ScreeningEngine.education_score(2, 2), 100.0)
        self.assertEqual(ScreeningEngine.education_score(1, 2), 50.0)
        self.assertEqual(ScreeningEngine.education_score(0, 3), 0.0)

    def test_final_score_is_weighted_sum(self):
        result = self.analyzer.analyze(make_candidate(), make_job())
        # skills 75% * 0.60 + experience 100% * 0.25 + education 100% * 0.15 = 85
        self.assertEqual(result.skill_score, 75.0)
        self.assertEqual(result.final_score, 85.0)
        self.assertEqual(result.status, "Strong match")

    def test_experience_shortfall_is_proportional(self):
        result = self.analyzer.analyze(make_candidate(experience_years=1), make_job(min_experience=4))
        self.assertEqual(result.experience_score, 25.0)
        self.assertIn("1 year of experience against a 4-year minimum", result.explanation)

    def test_custom_weights(self):
        analyzer = ScreeningEngine({"skills": 100, "experience": 0, "education": 0})
        self.assertEqual(analyzer.analyze(make_candidate(), make_job()).final_score, 75.0)

    def test_invalid_weights_rejected(self):
        with self.assertRaises(ValidationError):
            ScreeningEngine({"skills": 50, "experience": 20, "education": 20})   # 90%

    def test_rank_candidates_orders_best_first(self):
        strong = make_candidate(candidate_id="C1", email="a@example.com", skills="Python, SQL, Pandas, Power BI")
        weak = make_candidate(candidate_id="C2", email="b@example.com", skills="Excel")
        ranked = self.analyzer.rank_candidates([weak, strong], make_job())
        self.assertEqual([r.candidate_id for r in ranked], ["C1", "C2"])

    def test_classify_score_boundaries(self):
        self.assertEqual(classify_score(75), "Strong match")
        self.assertEqual(classify_score(74.9), "Possible match")
        self.assertEqual(classify_score(50), "Possible match")
        self.assertEqual(classify_score(10), "Weak match")


if __name__ == "__main__":
    unittest.main()
