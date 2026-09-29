"""The Candidate model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modules import validator
from modules.exceptions import ValidationError

# Fields that must be present when a candidate is loaded from JSON/CSV.
REQUIRED_FIELDS: tuple[str, ...] = (
    "candidate_id", "name", "email", "experience_years", "education_level", "degree", "skills",
)


class Candidate:
    """A job applicant and the evidence on their resume.

    All inputs are validated in the constructor, so a ``Candidate`` object
    is always in a valid state. Skills are kept private and exposed as a
    tuple so other code cannot modify the list behind the object's back.

    Evidence is kept in separate places on purpose:
    - skills the candidate *lists*,
    - projects: name, technologies used, a description and outcomes,
    - a free-text experience summary (work history in the candidate's words).
    The screening engine reads the structured parts; the competence audit
    also reads the text.
    """

    def __init__(
        self,
        candidate_id: str,
        name: str,
        email: str,
        experience_years: float | str,
        education_level: str,
        degree: str,
        skills: list[str] | str,
        phone: str = "",
        target_job_id: str | None = None,
        created_at: str | None = None,
        projects: list[dict[str, Any]] | str | None = None,
        notes: str = "",
        experience_summary: str = "",
        review: dict[str, str] | None = None,
    ):
        self.candidate_id = validator.validate_record_id(candidate_id, field="candidate_id")
        self.name = validator.validate_name(name)
        self.email = validator.validate_email(email)
        self.phone = validator.validate_phone(phone)
        self.experience_years = validator.validate_experience(experience_years)
        self.education_level = validator.validate_education_level(education_level)
        self.degree = validator.validate_degree(degree)
        self._skills: list[str] = validator.validate_skills(skills)
        self._projects: list[dict[str, Any]] = validator.validate_projects(projects)
        self.experience_summary = validator.validate_notes(experience_summary)
        self.notes = validator.validate_notes(notes)          # the reviewer's own notes
        self.review = validator.validate_review(review)       # the reviewer's own assessment
        self.target_job_id = target_job_id or None
        self.created_at = created_at or datetime.now().isoformat(timespec="seconds")

    @property
    def skills(self) -> tuple[str, ...]:
        return tuple(self._skills)

    @property
    def skill_keys(self) -> set[str]:
        """Normalised skills, used for set-based matching."""
        return {validator.skill_key(skill) for skill in self._skills}

    @property
    def projects(self) -> tuple[dict[str, Any], ...]:
        """Copies, so callers cannot edit a project in place."""
        return tuple({**p, "technologies": list(p["technologies"])} for p in self._projects)

    @property
    def project_skill_keys(self) -> set[str]:
        """Technologies used in at least one described project."""
        return {validator.skill_key(s) for p in self._projects for s in p["technologies"]}

    @property
    def evidence_skill_keys(self) -> set[str]:
        """Every skill the structured record gives evidence of: listed or a project technology."""
        return self.skill_keys | self.project_skill_keys

    @property
    def education_rank(self) -> int:
        return validator.EDUCATION_LEVELS.index(self.education_level)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "experience_years": self.experience_years,
            "education_level": self.education_level,
            "degree": self.degree,
            "skills": list(self._skills),
            "experience_summary": self.experience_summary,
            "projects": [dict(p) for p in self.projects],
            "target_job_id": self.target_job_id,
            "review": dict(self.review),
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        missing = [field for field in REQUIRED_FIELDS if field not in data]
        if missing:
            raise ValidationError(missing[0], f"Candidate record is missing: {', '.join(missing)}.")
        return cls(
            candidate_id=data["candidate_id"],
            name=data["name"],
            email=data["email"],
            phone=data.get("phone", ""),
            experience_years=data["experience_years"],
            education_level=data["education_level"],
            degree=data["degree"],
            skills=data["skills"],
            target_job_id=data.get("target_job_id"),
            created_at=data.get("created_at"),
            projects=data.get("projects"),
            notes=data.get("notes", ""),
            experience_summary=data.get("experience_summary", ""),
            review=data.get("review"),
        )

    def __repr__(self) -> str:
        return f"Candidate({self.candidate_id!r}, {self.name!r})"
