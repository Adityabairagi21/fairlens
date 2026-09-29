"""The JobRole model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modules import validator
from modules.exceptions import ValidationError

REQUIRED_FIELDS: tuple[str, ...] = ("job_id", "title", "required_skills", "min_experience", "min_education")

MAX_REQUIRED_EXPERIENCE = 30


class JobRole:
    """An open position and the requirements candidates are screened against."""

    def __init__(
        self,
        job_id: str,
        title: str,
        required_skills: list[str] | str,
        min_experience: float | str,
        min_education: str,
        description: str = "",
        created_at: str | None = None,
    ):
        self.job_id = validator.validate_record_id(job_id, field="job_id")
        self.title = validator.validate_job_title(title)
        self._required_skills: list[str] = validator.validate_required_skills(required_skills)
        self.min_experience = validator.validate_experience(
            min_experience, field="min_experience", maximum=MAX_REQUIRED_EXPERIENCE
        )
        self.min_education = validator.validate_education_level(min_education, field="min_education")
        self.description = " ".join(str(description or "").split())[:300]
        self.created_at = created_at or datetime.now().isoformat(timespec="seconds")

    @property
    def required_skills(self) -> tuple[str, ...]:
        return tuple(self._required_skills)

    @property
    def required_skill_map(self) -> dict[str, str]:
        """Normalised key -> display name, e.g. {'scikit-learn': 'Scikit-learn'}."""
        return {validator.skill_key(skill): skill for skill in self._required_skills}

    @property
    def min_education_rank(self) -> int:
        return validator.EDUCATION_LEVELS.index(self.min_education)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "required_skills": list(self._required_skills),
            "min_experience": self.min_experience,
            "min_education": self.min_education,
            "description": self.description,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRole":
        missing = [field for field in REQUIRED_FIELDS if field not in data]
        if missing:
            raise ValidationError(missing[0], f"Job record is missing: {', '.join(missing)}.")
        return cls(
            job_id=data["job_id"],
            title=data["title"],
            required_skills=data["required_skills"],
            min_experience=data["min_experience"],
            min_education=data["min_education"],
            description=data.get("description", ""),
            created_at=data.get("created_at"),
        )

    def __repr__(self) -> str:
        return f"JobRole({self.job_id!r}, {self.title!r})"
