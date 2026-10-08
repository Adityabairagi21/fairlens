# FairLens

### Explainable Resume Screening & Hiring Blind-Spot Analyzer

> **An explainable screening-audit system that examines what a candidate screening process captures, what it may miss, and how results change under different evaluation criteria.**
>
> FairLens is a screening-analysis and decision-support prototype. It does not make hiring decisions and does not establish whether a real-world hiring process is discriminatory.

Python · NumPy · Pandas · Streamlit · rule-based (no machine-learning model, no external API) · 95 unit tests

## 🎥 Video walkthrough

**[Download the video walkthrough (MP4, 50 min, 720p, 944 MB)](https://github.com/Adityabairagi21/fairlens/releases/download/v1.0/FairLens_Final_Video.mp4)** · [Release page](https://github.com/Adityabairagi21/fairlens/releases/tag/v1.0)

The video covers the basic code explanation, the end-to-end request flow, the purpose of each code file (main classes and functions), and a live demo of every page and chart.

---

## Contents

1. [Problem Statement](#1-problem-statement)
2. [Why This Problem Matters](#2-why-this-problem-matters)
3. [Product Concept](#3-product-concept)
4. [Key Features](#4-key-features)
5. [How FairLens Works](#5-how-fairlens-works)
6. [Screening Methodology](#6-screening-methodology)
7. [Sensitivity Analysis](#7-sensitivity-analysis)
8. [Blind-Spot Detection](#8-blind-spot-detection)
9. [Competence Audit](#9-competence-audit)
10. [What-If Analysis](#10-what-if-analysis)
11. [Human Review](#11-human-review)
12. [NumPy Usage](#12-numpy-usage)
13. [Pandas Usage](#13-pandas-usage)
14. [OOP Architecture](#14-oop-architecture)
15. [JSON/CSV Processing](#15-jsoncsv-processing)
16. [Validation](#16-validation)
17. [Exception Handling](#17-exception-handling)
18. [Testing](#18-testing)
19. [Limitations](#19-limitations)
20. [Ethical Considerations](#20-ethical-considerations)
21. [Assessment Requirement Mapping](#21-assessment-requirement-mapping)
22. [Installation](#22-installation)
23. [Running the Project](#23-running-the-project)
24. [GitHub Setup](#24-github-setup)
25. [Future Improvements](#25-future-improvements)

---

## 1. Problem Statement

FairLens asks two questions about any resume-screening process:

> **1. Is the score driven by relevant evidence, or disproportionately by a few criteria such as years of experience?**
>
> **2. Did the screening actually capture the candidate's evidence, or did it only match words against predefined criteria?**

A typical screener does **Resume → Score → Rank**. The score looks objective, but it depends on choices: which criteria count, how much each weighs, and how strictly a skill must be *worded* to count. "ML" is not "Machine Learning" to a keyword matcher. A Docker deployment described in a project is invisible if Docker is missing from the skills list.

## 2. Why This Problem Matters

- **Weights are decisions.** "Experience 25%" is a policy, not a fact. Changing it can reorder a shortlist.
- **Vocabulary is not competence.** The same skill written three ways ("PostgreSQL", "Postgres", "SQL") is counted, partly counted, or missed depending on the matcher.
- **Evidence lives outside the skills list.** Projects, outcomes and work history often show skills that the skills list does not name.
- **Nobody audits the screener.** Recruiters review candidates; rarely does anyone review the configuration and matching rules that ranked them.

## 3. Product Concept

FairLens is **an instrument panel for inspecting how resume screening behaves**: analytics + auditing + explainability + evidence + human review. It is not "upload resume → AI score → hire".

```
RESUME
  ↓
EXTRACT EVIDENCE        listed skills · projects (technologies, description, outcomes) · experience summary
  ↓
NORMALIZE SKILLS        skills taxonomy: synonyms and related terms (data/skills_taxonomy.json)
  ↓
EXACT MATCH             what a strict keyword matcher sees
  ↓
EVIDENCE MATCH          what the record actually contains
  ↓
BASELINE SCORE          e.g. Traditional: Skills 60 / Experience 25 / Education 15
  ↓
ALTERNATIVE SCORE       e.g. Skills-first: Skills 70 / Projects 20 / Experience 10
  ↓
SENSITIVITY ANALYSIS    the same evidence under every saved configuration
  ↓
COMPETENCE AUDIT        vocabulary vs evidence, two-pass screening, semantic-gap detection
  ↓
HUMAN REVIEW            the reviewer's own assessment; FairLens never recommends hire/reject
```

## 4. Key Features

| Feature | What it does | Page |
|---|---|---|
| Baseline & alternative screening | Transparent weighted score over four components; configurable weights (total 100%) | everywhere |
| Compare strategies | One candidate, two configurations, difference explained point by point | Compare strategies |
| "Why 68%?" explanation | Component % × weight = points; primary drivers; largest shortfall | Candidate, Compare |
| Score sensitivity | Score under every configuration; spread (max − min) and std | Overview, Audit, Candidate |
| Blind-spot detector | Six rules about how the configuration treats the evidence | Audit, Candidate |
| Ranking stability | Rank within each role under both configurations | Audit |
| **Competence audit** | Vocabulary match vs normalized match vs evidence coverage; evidence status per skill | Competence audit, Candidate |
| **What did the screening miss?** | Missed by exact matching → recovered through evidence → still unsupported | Competence audit, Candidate |
| **Two-pass screening** | Exact-match pass vs evidence-aware pass, same weights | Competence audit, Overview |
| **Semantic-gap detector** | Rule-based "Potential semantic gap" / "Possible semantic mismatch" | everywhere observations appear |
| **Audit trail** | Input evidence → normalized skills → exact → related → evidence → calculation → observation | Competence audit, Candidate |
| **Deep audit report** | Per-candidate text report, generated from the calculated audit | Candidate, Reports & data |
| **Human review** | Reviewer records *Strong fit / Possible fit / Needs review* and notes | Candidate |
| What-if analysis | Scenario simulation with the real engine | Candidate |
| Screening audit + history | Metrics, observations, CSV export, one history row per run | Screening audit |
| Signature views | *Skill coverage vs baseline score* and *Vocabulary match vs evidence coverage* | Overview, Competence audit |
| Evidence labels | FACT · CALCULATION · RULE-BASED · OBSERVATION · SCENARIO · SIMILARITY-BASED · REVIEWER NOTE | all pages |
| Records | Candidates (with structured projects), roles, configurations; CSV import; JSON backup | Candidates, Roles, Configurations, Reports |

## 5. How FairLens Works

**User flow**

1. **Overview**: headline metrics, the two signature charts, the largest score spreads, and *Where screening may miss evidence*.
2. **Screening audit**: pick a role and two configurations, then **Run audit**. You get the metrics (including semantic gaps), ranking stability, observations and sensitivity. The run is saved to `screening_history.json` and `reports/audit_results.csv`.
3. **Competence audit**: vocabulary vs evidence for the whole pool, two-pass screening, then one candidate in depth.
4. **Candidate**: Evidence → Competence audit → Why this score → Sensitivity → Potential blind spots → What-if → Human review.
5. **Compare strategies**, **Configurations**, **Method** (every rule and threshold, plus the taxonomy table).

**Architecture**

```
ui/ (Streamlit)                          modules/ (pure Python, no UI code)
┌─────────────────────────────┐          ┌──────────────────────────────────────────────────┐
│ app.py         navigation   │          │ candidate.py        Candidate (skills, projects,  │
│ state.py       shared engines│────────▶│                     experience summary, review)   │
│ theme.py       design system│          │ job.py              JobRole                       │
│ charts.py      Altair charts│          │ screening_engine.py ScreeningConfig/Engine/Result │
│ competence_ui.py            │          │ sensitivity.py      SensitivityAnalyzer, Scenario │
│   scorecard · miss panel ·  │          │ taxonomy.py         SkillTaxonomy (JSON-backed)   │
│   evidence table · trail ·  │          │ competence.py       CompetenceAuditEngine,        │
│   review form               │          │                     CompetenceResult, SkillEvidence│
│ views/  dashboard · audit · │          │ semantic_matcher.py optional TF-IDF similarity    │
│   competence · compare ·    │          │ audit.py            AuditEngine, AuditReport      │
│   candidates · candidate ·  │          │ observation.py      Observation (shared record)   │
│   roles · analytics ·       │          │ analytics.py        AnalyticsEngine, NumPy/Pandas │
│   configurations · reports ·│          │ data_manager.py     DataManager (JSON store)      │
│   method                    │          │ file_handler.py · validator.py · reports.py ·     │
└─────────────────────────────┘          │ exceptions.py                                     │
                                         └──────────────────────────────────────────────────┘
```

`python main.py --summary` runs the same audit (screening + competence) in the terminal without Streamlit.

**Folder structure**

```
ai_resume_screening/
├── main.py                       entry point (UI or --summary)
├── requirements.txt
├── data/
│   ├── candidates.json           15 sample candidates (projects + experience summaries)
│   ├── jobs.json                 3 roles
│   ├── screening_configs.json    4 preset configurations + baseline/alternative
│   ├── skills_taxonomy.json      28 skill concepts: synonyms and related terms
│   ├── screening_history.json    audit runs (runtime, git-ignored)
│   └── sample_candidates.csv     import demo (2 valid rows, 2 invalid)
├── modules/                      core logic (see above)
├── reports/                      audit_results.csv, candidate_report.csv (sample outputs)
├── tests/                        95 unittest cases
└── ui/                           Streamlit app
```

## 6. Screening Methodology

Four components, each a percentage, against the role the candidate applied for:

| Component | Formula | Evidence used |
|---|---|---|
| **Skills** | required skills shown ÷ required | listed skills ∪ project technologies (set union), with spelling aliases |
| **Project evidence** | required skills used in ≥ 1 project ÷ required | project technologies |
| **Experience** | min(years ÷ role minimum, 1) | years |
| **Education** | 100% if level ≥ minimum, 50% one level below, else 0% | education level |

```
score = Σ component% × weight% / 100        (the four weights total 100)
```

| Configuration | Skills | Projects | Experience | Education | Role |
|---|---:|---:|---:|---:|---|
| Traditional | 60 | 0 | 25 | 15 | default baseline |
| Skills-first | 70 | 20 | 10 | 0 | default alternative |
| Experience-weighted | 50 | 0 | 35 | 15 | sensitivity test |
| Balanced evidence | 45 | 20 | 20 | 15 | sensitivity test |

**Worked example: Ishita Banerjee (Data Analyst, fresher)**

```
                    Traditional                 Skills-first
Skills      83.3% × 60 = 50.0 / 60       83.3% × 70 = 58.3 / 70
Projects    83.3% ×  0 =  0.0 /  0       83.3% × 20 = 16.7 / 20
Experience   0.0% × 25 =  0.0 / 25        0.0% × 10 =  0.0 / 10
Education  100.0% × 15 = 15.0 / 15      100.0% ×  0 =  0.0 /  0
Total               65.0%                      75.0%     (+10.0 points)
```

## 7. Sensitivity Analysis

`SensitivityAnalyzer` builds a candidates × configurations score matrix and computes, per candidate, the spread (`np.ptp`), std (`np.std`) and the lowest/highest configuration (`np.argmin`/`np.argmax`). A spread of **≥ 20 points** is *high sensitivity*. With the sample data, 6 of 15 candidates are highly sensitive. Kabir Malhotra (9 years, 3 of 8 ML skills in exact wording) scores between 36% (Skills-first) and 69% (Experience-weighted). Siddharth Rao (all ML evidence, 0.5 years) scores between 60% and 81%. Sensitivity runs in both directions: it describes the evaluation, not the person.

## 8. Blind-Spot Detection

Six fixed rules in `modules/audit.py`, also listed on the in-app **Method** page:

| Observation | Kind | Rule |
|---|---|---|
| High evidence / low baseline score | potential blind spot | coverage ≥ 80% and baseline ≤ coverage − 15 |
| Score shaped mainly by one criterion | potential blind spot | a non-skill component causes ≥ 60% of the points lost, and ≥ 10 points |
| Project evidence not weighted | potential blind spot | projects show ≥ 50% of skills, the baseline weights projects 0%, the alternative scores higher |
| High score sensitivity | sensitivity | spread ≥ 20 points |
| Ranking changes with configuration | ranking | moves ≥ 2 places within a role of ≥ 3 |
| Listed skills without project evidence | evidence | coverage ≥ 70% but project evidence < 25% |

## 9. Competence Audit

**The question:** *did the screening understand the candidate, or only match words?* `CompetenceAuditEngine` (`modules/competence.py`) answers with rules, not a language model.

### 9.1 Skill normalization: `data/skills_taxonomy.json`

A small, editable taxonomy (28 concepts). Each concept has **terms** (synonyms: the same skill in other words) and optional **related** terms (neighbouring skills that count as *related* evidence, in one direction only):

```json
"sql": {
  "label": "SQL",
  "terms": ["sql", "structured query language", "relational databases"],
  "related": ["postgresql", "mysql", "sql server", "sqlite"]
}
```

PostgreSQL is related evidence for SQL, but SQL is not evidence for PostgreSQL. The app's spelling aliases (`sklearn`, `js`) are merged in automatically, so the taxonomy never contradicts the rest of the product. `SkillTaxonomy` validates the file. Duplicate terms, missing labels, missing terms or malformed JSON all produce one readable `DataFileError`, and the app falls back to exact wording.

### 9.2 Evidence status per required skill

| Status | Meaning |
|---|---|
| **EXPLICIT** | named in the skills list with the exact wording |
| **SUPPORTED** | not listed exactly, but used in a project (technologies, description, outcomes) or named in the experience summary |
| **RELATED** | listed under different wording: a synonym ("ML") or a related term ("Postgres" for SQL) |
| **MISSING** | no evidence anywhere in the record |

Text is searched with whole-word matching, longest wording first. Terms shorter than three characters ("ml", "tf") count when *listed* but are not searched for in prose, because they are ambiguous there. Every status keeps its **sources** (place, field, wording, match type), which feed the evidence table and the audit trail.

### 9.3 Three coverages, one score

| Metric | Counts a required skill when… | Question it answers |
|---|---|---|
| **Vocabulary match** | EXPLICIT | Does the resume use the exact vocabulary? |
| **Normalized match** | listed under any wording (exact, synonym, related) | Does it match after synonyms? |
| **Evidence coverage** | anything but MISSING | How much relevant evidence is present? |
| **Baseline score** | (unchanged screening score) | What did the configured screening produce? |

Always *vocabulary ≤ normalized ≤ evidence*. Evidence coverage **does not replace** the screening score. It sits next to it.

### 9.4 Two-pass screening

Both passes use the **baseline weights**; only the skills percentage changes:

```
Pass 1  exact-match pass     = baseline with skills% := vocabulary match
Pass 2  evidence-aware pass  = baseline with skills% := evidence coverage
```

The difference isolates the effect of the *matching method*, the same way the sensitivity analysis isolates the effect of the *weights*. Neither pass is the "correct" score.

### 9.5 Rules and signal

| Observation | Rule |
|---|---|
| **Potential semantic gap** | vocabulary ≤ 60% **and** evidence ≥ vocabulary + 25 points |
| Possible semantic mismatch | normalized ≥ vocabulary + 25 points |
| Evidence outside the skills list | a required skill appears only in projects/experience |
| Required skills without evidence | any MISSING skill |

**Signal:** *Review recommended* (semantic gap) · *Limited evidence* (evidence < 50%) · *Consistent* (evidence within 15 points of vocabulary) · otherwise *Partial gap*.

Example, generated from the sample data:

> **Potential semantic gap.** Exact terminology covers 17% of the required skills, while evidence coverage is 83%. The record contains relevant evidence that is not fully captured by exact skill matching. Evidence-aware pass: 65.0% vs exact pass 25.0%.
>
> **Possible semantic mismatch.** 4 of 6 required skills are listed under different wording ('Python programming' for Python, 'Structured Query Language' for SQL, 'MS Excel' for Excel). Strict keyword matching does not count them.

### 9.6 The five sample cases

| Case | Candidate(s) | Vocabulary → evidence | Two-pass | Signal |
|---|---|---|---|---|
| 1. Exact ≈ evidence | Aarav Sharma, Priya Nair, Sneha Kulkarni | 83 → 83 · 88 → 88 · 83 → 83 | no change | Consistent |
| 2. Low exact, high normalized | Ishita Banerjee, Meera Joshi | 17 → 83 · 25 → 75 | 25 → 65 · 55 → 85 | Review recommended |
| 3. Project evidence for a required skill | Nisha Verghese | 50 → 100 (REST APIs in a project description, Docker in project outcomes, Git in project technologies) | 42.5 → 72.5 | Review recommended |
| 4. High evidence + high sensitivity | Siddharth Rao | 88 → 100, spread 21 points across configurations | 66.2 → 73.8 | Consistent (sensitivity flagged separately) |
| 5. Genuinely missing skills | Sana Qureshi, Arjun Reddy | 17 → 33 · 33 → 33 | small or none | Limited evidence |

Across the pool: vocabulary match 56.1%, evidence coverage 71.9%, 3 potential semantic gaps, 3 large two-pass differences (≥ 15 points).

### 9.7 What did the screening miss? · Audit trail · Deep audit report

- **What did the screening miss?** Three columns: *missed by exact matching* → *recovered through evidence* (with the source) → *still unsupported*.
- **Audit trail**: seven steps. Input evidence → normalized skills (each wording → concept) → exact matches → related matches → evidence matches → score calculation (with the weights) → final observation.
- **Generate audit report**: a text report with candidate, role, baseline score, exact/normalized match, evidence coverage, sensitivity range, semantic gap (yes/no), missing/supported skills and observations, all from calculated values. The same figures for every candidate are columns in `audit_results.csv`.

### 9.8 Optional similarity layer: `modules/semantic_matcher.py`

Clearly separated from the rule-based evidence, and labelled **SIMILARITY-BASED** in the UI. It uses character-trigram **TF-IDF + cosine similarity** implemented in NumPy (smoothed idf, L2-normalised vectors), runs locally, and needs no API or key. For a *missing* skill it suggests the closest wording in the record (e.g. "Postgre SQL" for PostgreSQL, similarity 0.74). It measures **spelling** similarity, not meaning, and **never changes a figure**; a test enforces that.

## 10. What-If Analysis

Labelled **SCENARIO**, never "prediction". `SensitivityAnalyzer.simulate` scores an edited copy (`Candidate.from_dict({**candidate.to_dict(), **changes})`), so simulated values are validated like real ones and the stored record never changes. Options: configuration, experience, education, added skills (optionally shown in a project). There are also single-change scenarios and a projected-score curve over years of experience.

## 11. Human Review

The last step is always a person. On the candidate page, **Review finding** records the reviewer's own *Initial assessment* (**Strong fit / Possible fit / Needs review**, validated against a fixed tuple) plus notes and a timestamp, stored with the candidate record (`DataManager.record_review`). FairLens never fills this in, never suggests a value, and never uses it in a calculation. The deep audit report states the recorded assessment, or "not recorded".

## 12. NumPy Usage

| Where | Functions | Purpose |
|---|---|---|
| `analytics.score_statistics` | mean, median, std, min, max, percentile | headline score statistics |
| `sensitivity.sensitivity_frame` | ptp, std, min, max, argmin, argmax on a 2-D matrix | per-candidate sensitivity |
| `CompetenceAuditEngine.statistics` | mean, median, max, vector subtraction | vocabulary-vs-evidence gap statistics |
| `semantic_matcher.SemanticMatcher` | count_nonzero, log, linalg.norm, matrix product, argmax | TF-IDF cosine similarity |
| `AuditReport.summary` | mean, median, std, ptp | audit metrics |
| `sensitivity.experience_curve`, `analytics.score_distribution`, `experience_score_correlation` | arange, histogram, corrcoef | scenarios and pool analytics |

## 13. Pandas Usage

| Where | Operations |
|---|---|
| `CompetenceAuditEngine.frame` | the competence comparison table (one row per candidate) |
| `AuditEngine.run` | DataFrame build, `groupby().rank()`, `transform("count")`, two `merge`s (sensitivity, competence), `map`, `sort_values` |
| `SkillTaxonomy.to_frame` | taxonomy table on the Method page |
| `SensitivityAnalyzer.score_matrix` | `DataFrame.from_dict(orient="index")`, `join` |
| Charts | `groupby().agg()` to merge candidates at the same position; `melt` for two-pass and dumbbell charts |
| `analytics.*` | `explode`, `value_counts`, `pd.cut`, `describe`, `nlargest`, boolean masks |
| Export / import | `AuditReport.to_csv_frame`, `file_handler.read_csv/write_csv`, the project `data_editor` round trip |

## 14. OOP Architecture

| Class | Responsibility |
|---|---|
| `Candidate` | candidate information and evidence (skills, projects, experience summary, review); validated in `__init__`; private lists exposed as tuples |
| `JobRole` | requirements |
| `ScreeningConfig` | frozen dataclass; weights stored as a **tuple** |
| `ScreeningEngine` / `ScreeningResult` | transparent scoring; `contributions`, `points_lost`, `drivers`, `rescored()` |
| `SensitivityAnalyzer` / `Scenario` | configuration sensitivity and scenario simulation |
| `SkillTaxonomy` / `TermMatch` | JSON-backed normalization, one-directional related terms, text search |
| `CompetenceAuditEngine` / `CompetenceResult` / `SkillEvidence` / `EvidenceSource` | the competence audit |
| `SemanticMatcher` | optional similarity layer |
| `AuditEngine` / `AuditReport` / `Observation` | audits and rule-based observations |
| `AnalyticsEngine` | pool → engine → DataFrame → statistics |
| `DataManager` | JSON persistence, CRUD, configurations, history, taxonomy loading, reviews |
| `ScreeningAppError` + 5 subclasses | custom exceptions |

**Collections, each with a job:** `list` for candidate skills and evidence sources · `set` for skill intersection/difference (`matched = evidence ∩ required`) and one-directional related concepts (`frozenset`) · `dict` for the taxonomy term index, score breakdowns and ID-keyed stores · `tuple` for configuration weights, `EVIDENCE_STATUSES`, `REVIEW_ASSESSMENTS` and `MATCH_KINDS` · `collections.Counter` for status counts.

## 15. JSON/CSV Processing

| File | Contents |
|---|---|
| `data/candidates.json` | candidates incl. `projects` (`project_name`, `technologies`, `description`, `outcomes`), `experience_summary`, `review`, `notes`. Older records with `title/skills/summary` projects still load |
| `data/jobs.json` | roles |
| `data/screening_configs.json` | configurations + baseline/alternative |
| `data/skills_taxonomy.json` | the skills taxonomy (hand-edited reference data; never overwritten by the app) |
| `data/screening_history.json` | one row per audit, incl. semantic gaps and average evidence coverage |
| `reports/audit_results.csv` | one row per candidate: all scores, ranks, spread, vocabulary/normalized/evidence coverage, two-pass scores, signal, missing/supported skills, observations |
| `reports/candidate_report.csv` | baseline screening report |
| `data/sample_candidates.csv` | import demo; optional `projects` (`Name: tech; tech \| Name: tech`) and `experience_summary` columns |

All JSON writes are atomic (temp file + `os.replace`).

## 16. Validation

| Input | Rules |
|---|---|
| Name, email, phone, degree, IDs | length, characters, patterns |
| Experience | numeric, 0–50, not NaN/inf/bool |
| Skills | comma list, trimmed, de-duplicated through aliases, ≤ 30 |
| Projects | ≤ 8; name 2–80 chars, unique; ≥ 1 technology; description/outcomes ≤ 400 chars |
| Experience summary, notes | ≤ 600 chars |
| Review | assessment ∈ (*Strong fit, Possible fit, Needs review*) |
| Weights | known components, numeric, 0–100, **total exactly 100** |
| Configurations | unique names; baseline ≠ alternative; in-use configurations cannot be deleted; ≤ 8 |
| Taxonomy | labels, non-empty term lists, no term under two concepts, `related` must be a list |
| Duplicates | candidate ID/email, role title, configuration name, project name, taxonomy term |

## 17. Exception Handling

- `file_handler` converts `FileNotFoundError`, `JSONDecodeError`, `UnicodeDecodeError`, `PermissionError`, `OSError`, `TypeError` and pandas CSV errors into `DataFileError`.
- `DataManager.load` loads each file independently. A malformed taxonomy is reported, and the competence audit falls back to exact wording plus spelling aliases. A *missing* taxonomy (fresh data folder) is not an error. The app refuses to "reset" the taxonomy, because it is hand-edited.
- Invalid records are skipped with a reason; CSV rows are validated one by one.
- The UI catches specific exceptions only. There is no bare `except`.

## 18. Testing

```bash
python -m unittest discover -s tests -t . -v
```

**95 tests** in five files:

| File | Covers |
|---|---|
| `test_validator.py` | fields, experience, skills, education, weights, projects |
| `test_screening_engine.py` | skill intersection, aliases, components, weighted sum, ranking |
| `test_data_manager.py` | persistence, malformed JSON, duplicates, CSV import, search/filter/sort, NumPy stats |
| `test_fairlens.py` | project evidence, configurations, sensitivity, what-if, audit generation, blind spots, rankings, history/CSV |
| `test_competence.py` | taxonomy synonyms/related/direction, invalid & malformed taxonomy, **exact vs normalized match** (the brief's Python/ML/PostgreSQL example), **all four statuses**, project-text and experience evidence, semantic-gap rule and signals, **two-pass arithmetic**, neutral language, Pandas frame + NumPy statistics, audit integration, deep report, **human review** persistence/validation, legacy project keys, **similarity hints never change figures** |

## 19. Limitations

- **The taxonomy is finite.** A wording it does not list is not recognised. It is a maintained list, not language understanding.
- **Text search is literal.** "Containerised the service" does not match *Docker* unless the taxonomy lists that wording; negation ("no Docker experience") is not understood.
- **Evidence is self-reported.** FairLens records what the resume claims; it cannot verify it.
- **The similarity layer measures spelling, not meaning,** and is advisory only.
- Thresholds are documented judgement calls, not statistical tests. Ranking needs ≥ 3 candidates per role. Storage is single-user local JSON.

## 20. Ethical Considerations

FairLens does not infer gender, race, caste, religion, disability or socioeconomic status. It does not read names, locations, colleges, hobbies or languages in any rule, and it does not make or recommend hiring decisions. Its language follows from that. It says *"Evidence coverage is higher than exact terminology coverage"*, not *"the AI says this candidate is good"*. It says *"Potential screening sensitivity detected"*, not *"bias detected"*. It says *"Relevant evidence may not be fully represented by the baseline matching method"*, not *"wrongly rejected"*. FairLens does not know what any real screening system did with a candidate, so it never claims to. Tests enforce the neutral wording in both audit layers.

## 21. Assessment Requirement Mapping

| Requirement | Implementation | File / Module |
|---|---|---|
| **Collections** | lists of skills/evidence; set intersection for matching; dict taxonomy index and score breakdowns; tuple weights and status constants; Counter | `candidate.py`, `screening_engine.py`, `taxonomy.py`, `competence.py` |
| **Functions** | validators, scorers, taxonomy matching, text search, report builders | `validator.py`, `taxonomy.py`, `competence.py`, `reports.py`, `analytics.py` |
| **OOP** | 15+ classes incl. `CompetenceAuditEngine`, `SkillTaxonomy`, `ScreeningEngine`, `AuditEngine`, frozen dataclasses | `competence.py`, `taxonomy.py`, `screening_engine.py`, `audit.py`, … |
| **Exception handling** | custom hierarchy; file/JSON/CSV/taxonomy errors; per-file and per-row recovery | `exceptions.py`, `file_handler.py`, `taxonomy.py`, `data_manager.py` |
| **File processing / JSON** | candidates, roles, configurations, taxonomy, history; atomic writes | `data_manager.py`, `file_handler.py` |
| **CSV** | import (with projects), audit and candidate CSV export | `data_manager.py`, `audit.py`, `reports.py` |
| **Modules / packages** | `modules/`, `ui/`, `ui/views/`; one responsibility each | whole project |
| **Validation** | fields, projects, weights, reviews, configurations, taxonomy | `validator.py`, `taxonomy.py`, models |
| **NumPy** | score, sensitivity, competence-gap statistics; TF-IDF cosine similarity | `analytics.py`, `sensitivity.py`, `competence.py`, `semantic_matcher.py`, `audit.py` |
| **Pandas** | candidate/audit/competence DataFrames, ranking, merges, exports | `analytics.py`, `audit.py`, `competence.py` |
| **Testing** | 95 `unittest` cases | `tests/` |
| **GitHub** | `.gitignore`, requirements, commands (§24) | root |
| **README** | this document; in-app Method page | `README.md`, `ui/views/method.py` |

## 22. Installation

Requires **Python 3.10+**.

```bash
git clone https://github.com/<your-username>/fairlens.git
cd fairlens
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

## 23. Running the Project

```bash
python main.py                              # web app at http://localhost:8501
python main.py --summary                    # screening + competence audit in the terminal
python -m unittest discover -s tests -t .   # test suite
```

**A 3–5 minute demonstration**

1. **Overview (40 s).** *"FairLens doesn't score candidates. It audits the screening."* Show the metric strip, the *Skill coverage vs screening score* chart (Review zone), and scroll to **Where screening may miss evidence**: 3 potential semantic gaps, the *Vocabulary vs evidence* chart.
2. **Screening audit (50 s).** *All roles* → **Run audit**. Point at 6 high-sensitivity cases, 4 blind spots, 10 ranking changes and 3 semantic gaps. In the Data Analyst slope chart, Ananya moves 3rd → 1st between configurations. *"Same evidence, different weights, different order."*
3. **Competence audit (70 s).** Show the chart: Ishita, Meera and Nisha sit far above the diagonal. Inspect **Ishita**: vocabulary 17%, evidence 83%. **What did the screening miss?** shows 5 missed, 4 recovered and 1 still unsupported (Power BI). Show the two-pass result, 25% → 65%, and the audit trail. Then pick **Nisha**: REST APIs and Docker exist only in her project text. Then **Sana**: *Limited evidence*. The tool does not inflate thin records.
4. **Candidate page (40 s).** Open **Siddharth Rao**: 100% evidence but a 21-point sensitivity spread. Run a what-if (2 years of experience), then **Generate audit report**.
5. **Human review (20 s).** Record *Needs review* with a note. *"FairLens stops here. The decision is a person's."*
6. **Close (20 s).** Method page: every rule, the taxonomy table, and the rule-based vs similarity-based distinction. `python main.py --summary` and 95 passing tests.

## 24. GitHub Setup

```bash
cd ai_resume_screening
git init
git add .
git commit -m "FairLens: explainable screening audit with competence audit"
git branch -M main
git remote add origin https://github.com/<your-username>/fairlens.git
git push -u origin main
```

`.gitignore` excludes the virtual environment, caches, secrets, `screening_history.json`, backups and runtime reports; the two sample CSV reports are kept.

## 25. Future Improvements

- Grow the taxonomy from reviewer feedback (a reviewer marks a SIMILARITY hint as a true synonym → added to the JSON).
- Negation-aware text search ("no Docker experience").
- Per-skill weights ("must have" vs "nice to have").
- Compare two audit runs from history side by side.
- An embedding-based similarity layer as a second, optional, clearly labelled plug-in, still never counted in any figure.
