"""Tests for the FairLens layer: project evidence, configurations, sensitivity,
scenario simulation and the screening audit."""

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from modules import analytics
from modules.audit import AuditEngine
from modules.candidate import Candidate
from modules.data_manager import DataManager
from modules.exceptions import ValidationError
from modules.job import JobRole
from modules.screening_engine import DEFAULT_CONFIGS, ScreeningConfig, ScreeningEngine
from modules.sensitivity import HIGH_SENSITIVITY_POINTS, SensitivityAnalyzer

TRADITIONAL = ScreeningConfig.create("T", "Traditional", {"skills": 60, "experience": 25, "education": 15})
SKILLS_FIRST = ScreeningConfig.create("S", "Skills-first", {"skills": 70, "projects": 20, "experience": 10})
EXPERIENCE = ScreeningConfig.create("E", "Experience-weighted", {"skills": 50, "experience": 35, "education": 15})


def make_job(**overrides) -> JobRole:
    fields = dict(job_id="J001", title="Data Analyst", required_skills="Python, SQL, Pandas, Power BI",
                  min_experience=2, min_education="Bachelor's")
    fields.update(overrides)
    return JobRole(**fields)


def fresher(**overrides) -> Candidate:
    """Every required skill, backed by projects, but no experience."""
    fields = dict(
        candidate_id="C001", name="Ananya Iyer", email="ananya@example.com", experience_years=0,
        education_level="Bachelor's", degree="B.Sc Statistics", skills="Python, SQL, Pandas, Power BI",
        projects=[{"title": "Sales dashboard", "skills": ["Power BI", "SQL"]},
                  {"title": "Readmission study", "skills": ["Python", "Pandas"]}],
    )
    fields.update(overrides)
    return Candidate(**fields)


def veteran(**overrides) -> Candidate:
    """Long experience, half the required skills, no projects."""
    fields = dict(candidate_id="C002", name="Rajesh Kumar", email="rajesh@example.com", experience_years=8,
                  education_level="Bachelor's", degree="B.Com", skills="SQL, Excel, Power BI")
    fields.update(overrides)
    return Candidate(**fields)


class ProjectEvidenceTests(unittest.TestCase):
    def test_project_skills_count_as_evidence(self):
        result = ScreeningEngine(SKILLS_FIRST).analyze(fresher(), make_job())
        self.assertEqual(result.project_score, 100.0)
        self.assertEqual(set(result.evidenced_skills), {"Python", "SQL", "Pandas", "Power BI"})

    def test_skill_used_only_in_a_project_still_matches(self):
        candidate = fresher(skills="Python", projects=[{"title": "Dashboard", "skills": "SQL; Power BI"}])
        matched, missing, _ = ScreeningEngine.match_skills(candidate, make_job())
        self.assertEqual(matched, ["Python", "SQL", "Power BI"])     # set union of listed + project skills
        self.assertEqual(missing, ["Pandas"])

    def test_candidate_round_trips_projects(self):
        again = Candidate.from_dict(fresher().to_dict())
        self.assertEqual(again.projects, fresher().projects)

    def test_old_records_without_projects_still_load(self):
        record = veteran().to_dict()
        del record["projects"]
        self.assertEqual(Candidate.from_dict(record).projects, ())


class ConfigurationScoringTests(unittest.TestCase):
    def test_breakdown_points_add_up_to_final_score(self):
        result = ScreeningEngine(TRADITIONAL).analyze(fresher(), make_job())
        # skills 100% x 60 + experience 0% x 25 + education 100% x 15 = 75
        self.assertEqual(result.contributions, {"skills": 60, "projects": 0, "experience": 0, "education": 15})
        self.assertEqual(result.final_score, 75.0)
        self.assertEqual(result.largest_shortfall, ("experience", 25.0))
        self.assertEqual([c for c, _ in result.drivers], ["skills", "education", "experience"])

    def test_same_candidate_differs_across_configurations(self):
        traditional = ScreeningEngine(TRADITIONAL).analyze(fresher(), make_job()).final_score
        skills_first = ScreeningEngine(SKILLS_FIRST).analyze(fresher(), make_job()).final_score
        self.assertEqual((traditional, skills_first), (75.0, 90.0))

    def test_configuration_is_immutable_and_validated(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            TRADITIONAL.name = "Changed"
        self.assertIsInstance(TRADITIONAL.weights, tuple)
        with self.assertRaises(ValidationError):
            ScreeningConfig.create("X", "Broken", {"skills": 70, "experience": 20})     # 90%
        with self.assertRaises(ValidationError):
            ScreeningConfig.create("X", "", {"skills": 100})

    def test_presets_are_valid(self):
        for config in DEFAULT_CONFIGS:
            with self.subTest(config=config.name):
                self.assertEqual(sum(config.weights), 100)
                self.assertEqual(ScreeningConfig.from_dict(config.to_dict()), config)


class SensitivityTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = SensitivityAnalyzer([TRADITIONAL, SKILLS_FIRST, EXPERIENCE])
        self.job = make_job()

    def test_score_range_is_max_minus_min(self):
        frame = self.analyzer.sensitivity_frame([(fresher(), self.job), (veteran(), self.job)])
        row = frame.set_index("candidate_id").loc["C001"]
        # Traditional 75, Skills-first 90, Experience-weighted 65
        self.assertEqual((row["T"], row["S"], row["E"]), (75.0, 90.0, 65.0))
        self.assertEqual(row["score_range"], 25.0)
        self.assertAlmostEqual(row["score_std"], round(float(np.std([75, 90, 65])), 1))
        self.assertEqual((row["lowest_config"], row["highest_config"]), ("Experience-weighted", "Skills-first"))
        self.assertTrue(row["high_sensitivity"])
        self.assertGreaterEqual(row["score_range"], HIGH_SENSITIVITY_POINTS)

    def test_needs_two_configurations(self):
        with self.assertRaises(ValueError):
            SensitivityAnalyzer([TRADITIONAL])


class WhatIfTests(unittest.TestCase):
    def setUp(self):
        self.engine = ScreeningEngine(TRADITIONAL)
        self.analyzer = SensitivityAnalyzer([TRADITIONAL, SKILLS_FIRST])
        self.job = make_job()

    def test_extra_experience_uses_the_real_engine(self):
        one, two, three = self.analyzer.experience_scenarios(self.engine, fresher(), self.job)
        # experience component: 1/2 -> 50%, 2/2 -> 100% (capped after that)
        self.assertEqual((one.score, two.score, three.score), (87.5, 100.0, 100.0))
        self.assertEqual(one.change, 12.5)

    def test_adding_a_missing_skill(self):
        candidate = veteran()   # SQL + Power BI of 4 required
        scenarios = self.analyzer.skill_scenarios(self.engine, candidate, self.job)
        self.assertEqual({s.label for s in scenarios}, {"Add Python", "Add Pandas"})
        self.assertTrue(all(s.change == 15.0 for s in scenarios))   # one of four skills x 60%

    def test_simulation_never_changes_the_stored_candidate(self):
        candidate = fresher()
        self.analyzer.simulate(self.engine, candidate, self.job, "More", experience_years=5)
        self.assertEqual(candidate.experience_years, 0)

    def test_invalid_simulated_values_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.analyzer.simulate(self.engine, fresher(), self.job, "Bad", experience_years=-1)

    def test_experience_curve_is_monotonic(self):
        curve = SensitivityAnalyzer.experience_curve(self.engine, fresher(), self.job, max_years=4)
        self.assertEqual(curve["experience_years"].iloc[0], 0)
        self.assertTrue(curve["score"].is_monotonic_increasing)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.manager = DataManager(Path(self._tmp.name))
        job = self.manager.create_job(title="Data Analyst", required_skills="Python, SQL, Pandas, Power BI",
                                      min_experience=2, min_education="Bachelor's")
        for candidate in (fresher(target_job_id=job.job_id), veteran(target_job_id=job.job_id),
                          fresher(candidate_id="C003", name="Kiran Das", email="kiran@example.com",
                                  experience_years=3, projects=None, target_job_id=job.job_id)):
            self.manager.add_candidate(candidate)
        self.job_id = job.job_id
        self.audit = AuditEngine(TRADITIONAL, SKILLS_FIRST, [TRADITIONAL, SKILLS_FIRST, EXPERIENCE])

    def tearDown(self):
        self._tmp.cleanup()

    def test_audit_summary_is_calculated_from_the_data(self):
        report = self.audit.run(self.manager, self.job_id)
        summary = report.summary
        self.assertEqual(summary["candidates"], 3)
        self.assertAlmostEqual(summary["average_score"], float(np.mean(report.table["baseline_score"])))
        self.assertEqual(summary["high_sensitivity"], int(report.table["high_sensitivity"].sum()))

    def test_blind_spot_rules_fire_for_the_fresher(self):
        report = self.audit.run(self.manager, self.job_id)
        codes = {o.code for o in report.observations["C001"]}
        self.assertIn("HIGH_EVIDENCE_LOW_BASELINE", codes)   # 100% coverage, 75% baseline
        self.assertIn("SINGLE_CRITERION", codes)             # experience = all 25 lost points
        self.assertIn("UNCREDITED_PROJECTS", codes)
        self.assertTrue(report.table.set_index("candidate_id").loc["C001", "blind_spot"])

    def test_listed_skills_without_projects_is_noted(self):
        report = self.audit.run(self.manager, self.job_id)
        self.assertIn("UNBACKED_SKILLS", {o.code for o in report.observations["C003"]})

    def test_ranking_changes_between_configurations(self):
        table = self.audit.run(self.manager, self.job_id).table.set_index("candidate_id")
        # Traditional: Kiran 100, Ananya 75, Rajesh 55 | Skills-first: Ananya 90, Kiran 80, Rajesh 42.5
        self.assertEqual((table.loc["C001", "baseline_rank"], table.loc["C001", "alternative_rank"]), (2, 1))
        self.assertEqual(table.loc["C001", "rank_change"], 1)
        self.assertEqual(table.loc["C003", "rank_change"], -1)

    def test_observations_use_neutral_language(self):
        report = self.audit.run(self.manager, self.job_id)
        text = " ".join(o.text + o.title for found in report.observations.values() for o in found).lower()
        for word in ("reject", "hire", "unfair", "discriminat", "qualified"):
            self.assertNotIn(word, text)

    def test_history_and_csv_export(self):
        report = self.audit.run(self.manager, self.job_id)
        self.manager.record_audit(report.to_history_record())
        reloaded = DataManager(Path(self._tmp.name))
        self.assertEqual(reloaded.history[-1]["candidates"], 3)
        self.assertEqual(reloaded.history[-1]["baseline"], "Traditional")
        csv_frame = report.to_csv_frame()
        self.assertIn("score_Skills-first", csv_frame.columns)
        self.assertIn("observations", csv_frame.columns)

    def test_empty_pool_gives_an_empty_report(self):
        empty = DataManager(Path(self._tmp.name) / "empty")
        self.assertTrue(self.audit.run(empty).empty)


class ConfigStorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_presets_are_written_on_first_run(self):
        manager = DataManager(self.data_dir)
        self.assertEqual(len(manager.configs), len(DEFAULT_CONFIGS))
        self.assertNotEqual(manager.baseline_id, manager.alternative_id)

    def test_custom_configuration_survives_reload(self):
        created = DataManager(self.data_dir).create_config("Projects-heavy", {"skills": 50, "projects": 50})
        reloaded = DataManager(self.data_dir)
        self.assertEqual(reloaded.get_config(created.config_id).weight_map["projects"], 50)

    def test_config_rules(self):
        manager = DataManager(self.data_dir)
        with self.assertRaises(ValidationError):
            manager.create_config("traditional", {"skills": 100})            # duplicate name
        with self.assertRaises(ValidationError):
            manager.delete_config(manager.baseline_id)                       # in use
        with self.assertRaises(ValidationError):
            manager.set_comparison(manager.baseline_id, manager.baseline_id)  # must differ

    def test_malformed_config_file_is_reported(self):
        (self.data_dir / "screening_configs.json").write_text("{ nope", encoding="utf-8")
        manager = DataManager(self.data_dir)
        self.assertIn("configs", manager.load_errors)
        self.assertEqual(len(manager.configs), len(DEFAULT_CONFIGS))     # presets still usable

    def test_invalid_config_records_are_skipped(self):
        raw = {"baseline": "A", "alternative": "B", "configs": [
            {"config_id": "A", "name": "Alpha", "weights": {"skills": 100}},
            {"config_id": "B", "name": "Beta", "weights": {"skills": 40}},          # 40%
            {"config_id": "C", "name": "Gamma", "weights": {"experience": 100}},
        ]}
        (self.data_dir / "screening_configs.json").write_text(json.dumps(raw), encoding="utf-8")
        manager = DataManager(self.data_dir)
        self.assertEqual(list(manager.configs), ["A", "C"])
        self.assertEqual(manager.alternative_id, "C")   # the invalid alternative falls back
        self.assertEqual(len(manager.skipped_records), 1)


class AnalyticsPipelineTests(unittest.TestCase):
    def test_rank_within_groups_and_review_mask(self):
        import pandas as pd
        frame = pd.DataFrame({
            "target_role": ["A", "A", "A", "B"],
            "match_score": [70, 90, 70, 50],
            "skill_score": [100, 90, 60, 50],
        })
        self.assertEqual(analytics.rank_within_groups(frame, "match_score").tolist(), [2, 1, 2, 1])
        self.assertEqual(analytics.high_evidence_low_score(frame).tolist(), [True, False, False, False])

    def test_sensitivity_statistics(self):
        stats = analytics.sensitivity_statistics([10, 20, 30, float("nan")])
        self.assertEqual(stats["mean_range"], 20.0)
        self.assertEqual(stats["max_range"], 30.0)
        self.assertIsNone(analytics.sensitivity_statistics([]))


if __name__ == "__main__":
    unittest.main()
