import unittest

from modules import validator
from modules.exceptions import ValidationError


class EmailValidationTests(unittest.TestCase):
    def test_valid_email_is_lowercased_and_trimmed(self):
        self.assertEqual(validator.validate_email("  Priya.Nair@Outlook.com "), "priya.nair@outlook.com")

    def test_invalid_emails_are_rejected(self):
        for bad in ["", "priya", "priya@", "priya@gmail", "priya@@gmail.com", "priya..nair@gmail.com", "a b@gmail.com"]:
            with self.subTest(email=bad), self.assertRaises(ValidationError) as ctx:
                validator.validate_email(bad)
            self.assertEqual(ctx.exception.field, "email")


class NameAndPhoneTests(unittest.TestCase):
    def test_name_allows_common_punctuation(self):
        self.assertEqual(validator.validate_name("  Anne-Marie  D'Souza "), "Anne-Marie D'Souza")

    def test_name_rejects_digits_and_short_values(self):
        for bad in ["John123", "A", "", "--"]:
            with self.subTest(name=bad), self.assertRaises(ValidationError):
                validator.validate_name(bad)

    def test_phone_formats_are_normalised(self):
        self.assertEqual(validator.validate_phone("+91 98765 43210"), "+919876543210")
        self.assertEqual(validator.validate_phone("98765-43210"), "9876543210")
        self.assertEqual(validator.validate_phone(""), "")  # optional

    def test_phone_rejects_letters_and_short_numbers(self):
        for bad in ["12345", "98765abcde", "+91 98765"]:
            with self.subTest(phone=bad), self.assertRaises(ValidationError):
                validator.validate_phone(bad)


class ExperienceValidationTests(unittest.TestCase):
    def test_numeric_strings_are_accepted_and_rounded(self):
        self.assertEqual(validator.validate_experience("2.46"), 2.5)
        self.assertEqual(validator.validate_experience(0), 0.0)

    def test_invalid_experience_values(self):
        for bad in ["two", "", "-1", "51", "nan", True]:
            with self.subTest(value=bad), self.assertRaises(ValidationError):
                validator.validate_experience(bad)


class SkillsAndEducationTests(unittest.TestCase):
    def test_skills_are_split_trimmed_and_deduplicated(self):
        skills = validator.validate_skills("Python,  SQL , python, , sklearn, Scikit-learn")
        self.assertEqual(skills, ["Python", "SQL", "sklearn"])  # alias duplicate removed

    def test_skills_accept_lists(self):
        self.assertEqual(validator.validate_skills(["C++", "C#", "Node.js"]), ["C++", "C#", "Node.js"])

    def test_empty_skills_rejected(self):
        with self.assertRaises(ValidationError):
            validator.validate_skills(" , ,")

    def test_skill_key_applies_aliases(self):
        self.assertEqual(validator.skill_key("  SKLearn "), "scikit-learn")
        self.assertEqual(validator.skill_key("JS"), "javascript")

    def test_education_level_is_case_insensitive(self):
        self.assertEqual(validator.validate_education_level("bachelors"), "Bachelor's")
        with self.assertRaises(ValidationError):
            validator.validate_education_level("Graduate")

    def test_weights_must_total_100(self):
        self.assertEqual(validator.validate_weights({"skills": 60, "experience": 25, "education": 15}),
                         {"skills": 60, "projects": 0, "experience": 25, "education": 15})
        with self.assertRaises(ValidationError):
            validator.validate_weights({"skills": 60, "experience": 30, "education": 15})

    def test_invalid_weight_values(self):
        bad_sets = [
            {"skills": -10, "experience": 60, "education": 50},     # negative
            {"skills": "abc", "experience": 50, "education": 50},   # not a number
            {"skills": 100, "luck": 0},                             # unknown component
            {"skills": True, "experience": 99},                     # bool is not a weight
        ]
        for weights in bad_sets:
            with self.subTest(weights=weights), self.assertRaises(ValidationError):
                validator.validate_weights(weights)


class ProjectValidationTests(unittest.TestCase):
    def test_projects_parse_from_text(self):
        projects = validator.validate_projects("Sales dashboard: Power BI; SQL | Churn model: Python, Scikit-learn")
        self.assertEqual([p["project_name"] for p in projects], ["Sales dashboard", "Churn model"])
        self.assertEqual(projects[1]["technologies"], ["Python", "Scikit-learn"])

    def test_projects_are_optional(self):
        self.assertEqual(validator.validate_projects(None), [])
        self.assertEqual(validator.validate_projects(""), [])

    def test_invalid_projects_rejected(self):
        for bad in ["No colon here", "A: ", [{"title": "X", "skills": ["SQL"]}],
                    [{"title": "Same", "skills": "SQL"}, {"title": "same", "skills": "Excel"}]]:
            with self.subTest(projects=bad), self.assertRaises(ValidationError):
                validator.validate_projects(bad)


if __name__ == "__main__":
    unittest.main()
