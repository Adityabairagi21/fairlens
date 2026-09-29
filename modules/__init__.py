"""FairLens core package — an explainable screening-audit system.

Modules
-------
exceptions        custom exception hierarchy
validator         input validation and cleaning (fields, skills, projects, weights, reviews)
candidate         Candidate model (listed skills, projects, experience summary, review)
job               JobRole model
screening_engine  ScreeningConfig, ScreeningEngine, ScreeningResult (transparent scoring)
sensitivity       SensitivityAnalyzer (scores across configurations, what-if scenarios)
taxonomy          SkillTaxonomy (synonyms and related terms from skills_taxonomy.json)
competence        CompetenceAuditEngine (vocabulary vs evidence, two-pass screening, semantic gaps)
semantic_matcher  optional TF-IDF similarity hints (never scored)
observation       Observation record shared by both audits
audit             AuditEngine, AuditReport (screening + competence audit in one run)
file_handler      JSON / CSV reading and writing
data_manager      DataManager plus search, filter and sort helpers
analytics         AnalyticsEngine, NumPy statistics and Pandas analysis
reports           CSV, text and competence audit reports
"""

__version__ = "3.0.0"
