import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from modules import analytics
from modules.data_manager import DataManager, filter_candidates, search_candidates, sort_candidates
from modules.exceptions import DataFileError, DuplicateCandidateError, DuplicateJobError, ValidationError
from modules.file_handler import load_json
from modules.screening_engine import ScreeningEngine

CANDIDATE = dict(
    name="Priya Nair", email="priya.nair@example.com", phone="9812345670", experience_years="3",
    education_level="Master's", degree="M.Sc in Data Science", skills="Python, SQL, Pandas",
)


class DataManagerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.manager = DataManager(self.data_dir)
        self.job = self.manager.create_job(
            title="Data Analyst", required_skills="Python, SQL, Excel", min_experience=1, min_education="Bachelor's"
        )

    def tearDown(self):
        self._tmp.cleanup()


class PersistenceTests(DataManagerTestCase):
    def test_missing_files_are_created_on_first_run(self):
        self.assertTrue((self.data_dir / "candidates.json").exists())
        self.assertEqual(self.manager.load_errors, {})

    def test_candidates_survive_a_reload(self):
        created = self.manager.create_candidate(**CANDIDATE, target_job_id=self.job.job_id)
        reloaded = DataManager(self.data_dir)
        self.assertEqual(reloaded.get_candidate(created.candidate_id).email, "priya.nair@example.com")
        self.assertEqual(created.candidate_id, "C001")

    def test_malformed_json_is_reported_not_raised(self):
        (self.data_dir / "candidates.json").write_text("[{ broken", encoding="utf-8")
        manager = DataManager(self.data_dir)
        self.assertIn("candidates", manager.load_errors)
        self.assertIn("may be corrupted", manager.load_errors["candidates"])
        self.assertEqual(len(manager.jobs), 1)  # other files still load

    def test_reset_file_keeps_a_backup(self):
        path = self.data_dir / "candidates.json"
        path.write_text("not json", encoding="utf-8")
        manager = DataManager(self.data_dir)
        backup = manager.reset_file("candidates")
        self.assertEqual(backup.read_text(encoding="utf-8"), "not json")
        self.assertEqual(manager.load_errors, {})

    def test_invalid_records_are_skipped_with_a_reason(self):
        records = [{**CANDIDATE, "candidate_id": "C001"}, {"candidate_id": "C002", "name": "No Email"}]
        (self.data_dir / "candidates.json").write_text(json.dumps(records), encoding="utf-8")
        manager = DataManager(self.data_dir)
        self.assertEqual(list(manager.candidates), ["C001"])
        self.assertEqual(len(manager.skipped_records), 1)

    def test_load_json_without_default_raises_for_missing_file(self):
        with self.assertRaises(DataFileError):
            load_json(self.data_dir / "does_not_exist.json")


class DuplicateHandlingTests(DataManagerTestCase):
    def test_duplicate_email_is_rejected(self):
        self.manager.create_candidate(**CANDIDATE)
        with self.assertRaises(DuplicateCandidateError):
            self.manager.create_candidate(**{**CANDIDATE, "name": "Priya N"})

    def test_duplicate_id_is_rejected(self):
        self.manager.create_candidate(**CANDIDATE, candidate_id="C010")
        with self.assertRaises(DuplicateCandidateError):
            self.manager.create_candidate(**{**CANDIDATE, "email": "other@example.com"}, candidate_id="c010")

    def test_duplicate_job_title_is_rejected(self):
        with self.assertRaises(DuplicateJobError):
            self.manager.create_job(title="data analyst", required_skills="SQL", min_experience=0,
                                    min_education="Diploma")

    def test_failed_update_leaves_record_unchanged(self):
        created = self.manager.create_candidate(**CANDIDATE)
        with self.assertRaises(ValidationError):
            self.manager.update_candidate(created.candidate_id, email="not-an-email")
        self.assertEqual(self.manager.get_candidate(created.candidate_id).email, "priya.nair@example.com")

    def test_deleting_a_job_unassigns_candidates(self):
        created = self.manager.create_candidate(**CANDIDATE, target_job_id=self.job.job_id)
        affected = self.manager.delete_job(self.job.job_id)
        self.assertEqual(affected, 1)
        self.assertIsNone(self.manager.get_candidate(created.candidate_id).target_job_id)


class CsvImportTests(DataManagerTestCase):
    def test_valid_rows_import_and_invalid_rows_are_reported(self):
        csv_path = self.data_dir / "import.csv"
        csv_path.write_text(
            "name,email,phone,experience_years,education_level,degree,skills,target_role\n"
            "Rahul Das,rahul.das@example.com,9876500000,2,Bachelor's,BCA,Python;SQL,Data Analyst\n"
            "Bad Email,bad@,9876500001,2,Bachelor's,BCA,Python,Data Analyst\n"
            "Meera Joshi,meera@example.com,9876500002,two,Bachelor's,BCA,Python,Data Analyst\n"
            "Ravi Kumar,ravi@example.com,9876500003,1,Bachelor's,BCA,Python,Astronaut\n",
            encoding="utf-8",
        )
        summary = self.manager.import_candidates_csv(csv_path)
        self.assertEqual(len(summary.added), 1)
        self.assertEqual([row for row, _ in summary.skipped], [3, 4, 5])
        imported = self.manager.get_candidate(summary.added[0])
        self.assertEqual(imported.skills, ("Python", "SQL"))
        self.assertEqual(imported.target_job_id, self.job.job_id)

    def test_csv_missing_columns_raises(self):
        csv_path = self.data_dir / "bad.csv"
        csv_path.write_text("name,email\nA B,a@example.com\n", encoding="utf-8")
        with self.assertRaises(DataFileError):
            self.manager.import_candidates_csv(csv_path)


class SearchFilterSortTests(DataManagerTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.manager.create_candidate(**CANDIDATE, target_job_id=self.job.job_id)
        self.b = self.manager.create_candidate(
            name="Karan Patel", email="karan@example.com", experience_years=1, education_level="Diploma",
            degree="Diploma in Computer Engineering", skills="Excel, SQL",
        )

    def test_search_matches_skills_and_names(self):
        people = self.manager.candidates.values()
        self.assertEqual(search_candidates(people, "pandas"), [self.a])
        self.assertEqual(search_candidates(people, "karan sql"), [self.b])
        self.assertEqual(len(search_candidates(people, "")), 2)

    def test_filter_by_skill_experience_and_role(self):
        people = self.manager.candidates.values()
        self.assertEqual(filter_candidates(people, must_have_skills=["sql", "excel"]), [self.b])
        self.assertEqual(filter_candidates(people, min_experience=2), [self.a])
        self.assertEqual(filter_candidates(people, job_id=self.job.job_id), [self.a])

    def test_sort_by_name_and_score(self):
        people = list(self.manager.candidates.values())
        self.assertEqual(sort_candidates(people, by="Name", descending=False), [self.b, self.a])
        scores = {self.a.candidate_id: 40.0, self.b.candidate_id: 90.0}
        self.assertEqual(sort_candidates(people, by="Match score", scores=scores), [self.b, self.a])


class AnalyticsTests(DataManagerTestCase):
    def test_score_statistics_match_numpy(self):
        stats = analytics.score_statistics([50, 70, 90, float("nan")])
        self.assertEqual(stats["count"], 3)
        self.assertAlmostEqual(stats["mean"], 70.0)
        self.assertAlmostEqual(stats["std"], float(np.std([50, 70, 90])))
        self.assertIsNone(analytics.score_statistics([]))

    def test_distribution_counts_every_score(self):
        dist = analytics.score_distribution([10, 45, 85, 100])
        self.assertEqual(dist["candidates"].sum(), 4)  # 100 falls in the last, closed bin

    def test_candidate_frame_and_group_by(self):
        self.manager.create_candidate(**CANDIDATE | {"email": "x@example.com"}, target_job_id=self.job.job_id)
        frame = analytics.build_candidate_frame(
            self.manager, analytics.screen_all(self.manager, ScreeningEngine())
        )
        self.assertEqual(len(frame), 1)
        by_role = analytics.average_score_by_role(frame)
        self.assertEqual(by_role.iloc[0]["target_role"], "Data Analyst")


if __name__ == "__main__":
    unittest.main()
