"""Input validation and cleaning.

Every function takes raw input (usually a string typed by the user or read
from a CSV cell), returns a cleaned value, and raises ``ValidationError``
with a readable message when the input is not acceptable.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Mapping

from modules.exceptions import ValidationError

# The parts a screening score is built from. A tuple: the order is used for
# the weight tuple stored in every ScreeningConfig and must never change.
SCORE_COMPONENTS: tuple[str, ...] = ("skills", "projects", "experience", "education")

# Ordered from lowest to highest. A tuple because the order carries meaning
# (it is used to rank education) and must never change at runtime.
EDUCATION_LEVELS: tuple[str, ...] = (
    "High School",
    "Diploma",
    "Bachelor's",
    "Master's",
    "PhD",
)

# Common short forms people type for the same skill. Keys and values are
# normalised (lower-case) so "SKLearn" and "scikit-learn" compare equal.
SKILL_ALIASES: dict[str, str] = {
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "ml": "machine learning",
    "dl": "deep learning",
    "nodejs": "node.js",
    "node": "node.js",
    "k8s": "kubernetes",
    "tf": "tensorflow",
    "powerbi": "power bi",
    "ms excel": "excel",
}

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
PHONE_PATTERN = re.compile(r"^\+?\d{10,13}$")
SKILL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 +#./&-]*$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")

MAX_SKILLS = 30
MAX_EXPERIENCE_YEARS = 50
MAX_PROJECTS = 8
MAX_PROJECT_TEXT = 400

# A human reviewer's own call, recorded after reading the audit. FairLens never sets it.
REVIEW_ASSESSMENTS: tuple[str, ...] = ("Strong fit", "Possible fit", "Needs review")


def _clean_text(value: object) -> str:
    """Convert any value to a stripped string with single spaces."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):  # empty cell from pandas
        return ""
    return " ".join(str(value).split())


def skill_key(skill: str) -> str:
    """Return the comparison key for a skill ("  SKLearn " -> "scikit-learn")."""
    key = " ".join(skill.split()).casefold()
    return SKILL_ALIASES.get(key, key)


def validate_name(value: object) -> str:
    name = _clean_text(value)
    if not name:
        raise ValidationError("name", "Please enter the candidate's full name.")
    if not 2 <= len(name) <= 60:
        raise ValidationError("name", "Name must be between 2 and 60 characters.")
    allowed_symbols = {" ", ".", "'", "-"}
    if not all(ch.isalpha() or ch in allowed_symbols for ch in name):
        raise ValidationError("name", "Name can only contain letters, spaces, dots, hyphens and apostrophes.")
    if sum(ch.isalpha() for ch in name) < 2:
        raise ValidationError("name", "Name must contain at least two letters.")
    return name


def validate_email(value: object) -> str:
    email = _clean_text(value).lower()
    if not email:
        raise ValidationError("email", "Please enter an email address.")
    if ".." in email or not EMAIL_PATTERN.match(email):
        raise ValidationError("email", "Please enter a valid email address.")
    return email


def validate_phone(value: object, required: bool = False) -> str:
    """Accept formats like '+91 98765 43210' or '98765-43210'; store digits only."""
    raw = _clean_text(value)
    if not raw:
        if required:
            raise ValidationError("phone", "Please enter a phone number.")
        return ""
    # CSV readers can turn 9876543210 into 9876543210.0
    if re.fullmatch(r"\d+\.0", raw):
        raw = raw[:-2]
    compact = re.sub(r"[\s\-()]", "", raw)
    if not PHONE_PATTERN.match(compact):
        raise ValidationError("phone", "Please enter a valid phone number (10 to 13 digits, optional +country code).")
    return compact


def validate_experience(value: object, field: str = "experience", maximum: float = MAX_EXPERIENCE_YEARS) -> float:
    """Validate years of experience and round to one decimal place."""
    if isinstance(value, bool):  # bool is a subclass of int, reject it explicitly
        raise ValidationError(field, "Experience must be a number of years, e.g. 2 or 3.5.")
    text = _clean_text(value)
    if not text:
        raise ValidationError(field, "Please enter years of experience (use 0 for freshers).")
    try:
        years = float(text)
    except ValueError:
        raise ValidationError(field, "Experience must be a number of years, e.g. 2 or 3.5.") from None
    if math.isnan(years) or math.isinf(years):
        raise ValidationError(field, "Experience must be a number of years, e.g. 2 or 3.5.")
    if years < 0:
        raise ValidationError(field, "Experience cannot be negative.")
    if years > maximum:
        raise ValidationError(field, f"Experience cannot be more than {maximum:g} years.")
    return round(years, 1)


def validate_skills(value: object, field: str = "skills") -> list[str]:
    """Split, clean and de-duplicate a skill list.

    Accepts either a comma-separated string or any iterable of strings.
    Duplicates are detected case-insensitively (and through aliases), but
    the first spelling the user typed is kept for display.
    """
    if isinstance(value, str) or value is None or isinstance(value, float):
        parts = _clean_text(value).split(",")
    elif isinstance(value, Iterable):
        parts = [_clean_text(item) for item in value]
    else:
        raise ValidationError(field, "Skills must be a comma-separated list.")

    skills: list[str] = []
    seen_keys: set[str] = set()
    for part in parts:
        skill = _clean_text(part)
        if not skill:
            continue
        if len(skill) > 40:
            raise ValidationError(field, f"'{skill[:20]}...' is too long for a skill name (max 40 characters).")
        if not SKILL_PATTERN.match(skill):
            raise ValidationError(field, f"'{skill}' contains characters that are not allowed in a skill name.")
        key = skill_key(skill)
        if key not in seen_keys:
            seen_keys.add(key)
            skills.append(skill)

    if not skills:
        label = "required skill" if field == "required_skills" else "skill"
        raise ValidationError(field, f"Please enter at least one {label}, separated by commas.")
    if len(skills) > MAX_SKILLS:
        raise ValidationError(field, f"Please list at most {MAX_SKILLS} skills.")
    return skills


def validate_education_level(value: object, field: str = "education_level") -> str:
    level = _clean_text(value)
    # Be forgiving about case and a missing apostrophe ("bachelors").
    lookup = {lvl.casefold().replace("'", ""): lvl for lvl in EDUCATION_LEVELS}
    match = lookup.get(level.casefold().replace("'", ""))
    if match is None:
        options = ", ".join(EDUCATION_LEVELS)
        raise ValidationError(field, f"Education level must be one of: {options}.")
    return match


def validate_degree(value: object) -> str:
    degree = _clean_text(value)
    if not degree:
        raise ValidationError("degree", "Please enter the degree or course, e.g. 'B.Tech in Computer Science'.")
    if not 2 <= len(degree) <= 80:
        raise ValidationError("degree", "Degree must be between 2 and 80 characters.")
    return degree


def validate_job_title(value: object) -> str:
    title = _clean_text(value)
    if not title:
        raise ValidationError("title", "Please enter a job title.")
    if not 2 <= len(title) <= 60:
        raise ValidationError("title", "Job title must be between 2 and 60 characters.")
    if not any(ch.isalpha() for ch in title):
        raise ValidationError("title", "Job title must contain letters.")
    return title


def validate_required_skills(value: object) -> list[str]:
    return validate_skills(value, field="required_skills")


def validate_record_id(value: object, field: str = "id") -> str:
    record_id = _clean_text(value).upper()
    if not ID_PATTERN.match(record_id):
        raise ValidationError(field, "IDs may only contain letters, digits, '-' and '_' (max 20 characters).")
    return record_id


def validate_weights(weights: Mapping[str, object]) -> dict[str, float]:
    """Validate a {component: percent} mapping. Components left out count as 0.

    Every weight must be a number from 0 to 100 and together they must add
    up to exactly 100, otherwise the score would not be a percentage.
    """
    if not isinstance(weights, Mapping):
        raise ValidationError("weights", "Weights must be given as component: percent pairs.")
    unknown = set(weights) - set(SCORE_COMPONENTS)
    if unknown:
        raise ValidationError("weights", f"Unknown score component: {', '.join(sorted(unknown))}.")

    cleaned: dict[str, float] = {}
    for component in SCORE_COMPONENTS:
        raw = weights.get(component, 0)
        if isinstance(raw, bool):
            raise ValidationError("weights", f"The {component} weight must be a number.")
        try:
            value = float(_clean_text(raw) or 0)
        except ValueError:
            raise ValidationError("weights", f"The {component} weight must be a number.") from None
        if math.isnan(value) or math.isinf(value):
            raise ValidationError("weights", f"The {component} weight must be a number.")
        if value < 0:
            raise ValidationError("weights", "Weights cannot be negative.")
        if value > 100:
            raise ValidationError("weights", "A single weight cannot be more than 100%.")
        cleaned[component] = value

    total = sum(cleaned.values())
    if round(total, 6) != 100:
        raise ValidationError("weights", f"Weights must add up to 100% (currently {total:g}%).")
    return cleaned


def validate_notes(value: object, maximum: int = 600) -> str:
    """Free-text reviewer notes: optional, trimmed, length-limited. Line breaks are kept."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = "\n".join(" ".join(line.split()) for line in str(value).strip().splitlines())
    if len(text) > maximum:
        raise ValidationError("notes", f"Notes can be at most {maximum} characters.")
    return text


def validate_config_name(value: object) -> str:
    name = _clean_text(value)
    if not 2 <= len(name) <= 40:
        raise ValidationError("name", "Configuration name must be between 2 and 40 characters.")
    if not any(ch.isalpha() for ch in name):
        raise ValidationError("name", "Configuration name must contain letters.")
    return name


def _first(item: Mapping[str, object], *keys: str) -> object:
    """The first key present, so older records ('title', 'skills', 'summary') still load."""
    return next((item[k] for k in keys if k in item and item[k] not in (None, "")), None)


def validate_projects(value: object) -> list[dict[str, object]]:
    """Validate a candidate's projects.

    Each project is stored as::

        {"project_name": str, "technologies": [str, ...], "description": str, "outcomes": str}

    Projects are optional, so None or an empty list is valid. A text value is
    parsed with ``parse_projects`` so CSV cells can use a one-line format.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, str):
        value = parse_projects(value)
    if not isinstance(value, (list, tuple)):
        raise ValidationError("projects", "Projects must be a list.")
    if len(value) > MAX_PROJECTS:
        raise ValidationError("projects", f"Please list at most {MAX_PROJECTS} projects.")

    projects: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise ValidationError("projects", "Each project needs a name and the technologies it used.")
        name = _clean_text(_first(item, "project_name", "title"))
        if not 2 <= len(name) <= 80:
            raise ValidationError("projects", "Each project name must be between 2 and 80 characters.")
        if name.casefold() in seen_names:
            raise ValidationError("projects", f"The project '{name}' is listed twice.")
        seen_names.add(name.casefold())
        raw = _first(item, "technologies", "skills")
        if isinstance(raw, str):
            raw = raw.replace(";", ",")   # "SQL; Power BI" is the documented format
        try:
            technologies = validate_skills(raw, field="projects")
        except ValidationError as error:
            raise ValidationError("projects", f"Project '{name}': {error.message}") from None
        description = _clean_text(_first(item, "description", "summary"))
        outcomes = _clean_text(item.get("outcomes"))
        if len(description) > MAX_PROJECT_TEXT or len(outcomes) > MAX_PROJECT_TEXT:
            raise ValidationError("projects", f"Project '{name}': description and outcomes can be at most "
                                              f"{MAX_PROJECT_TEXT} characters each.")
        projects.append({"project_name": name, "technologies": technologies,
                         "description": description, "outcomes": outcomes})
    return projects


def parse_projects(text: str) -> list[dict[str, object]]:
    """Parse "Name: technology; technology" entries separated by new lines or "|".

    Example: "Sales dashboard: Power BI; SQL | Churn model: Python; Scikit-learn"
    """
    projects = []
    for entry in re.split(r"[\n|]", text or ""):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise ValidationError(
                "projects", f"'{entry[:30]}' needs a colon between the name and its technologies, "
                            "e.g. 'Dashboard: SQL; Power BI'."
            )
        name, technologies = entry.split(":", 1)
        projects.append({"project_name": name, "technologies": technologies})
    return projects


def validate_review(value: object) -> dict[str, str]:
    """A reviewer's own assessment. Empty means not reviewed yet."""
    if value in (None, "", {}):
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError("review", "The review must record an assessment.")
    assessment = _clean_text(value.get("assessment"))
    if assessment not in REVIEW_ASSESSMENTS:
        raise ValidationError("review", f"Assessment must be one of: {', '.join(REVIEW_ASSESSMENTS)}.")
    return {"assessment": assessment, "reviewed_at": _clean_text(value.get("reviewed_at"))[:25]}
