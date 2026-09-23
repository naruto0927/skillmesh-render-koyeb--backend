"""
SkillMesh — Deterministic Scoring Engine

This module implements the proficiency and confidence scoring algorithms.
All scores produced here are deterministic and reproducible.
No LLM is involved. SIH judges can ask how any score was computed —
this module is the answer.

────────────────────────────────────────────────────────────────────────────────
PROFICIENCY SCORE (0–100)
────────────────────────────────────────────────────────────────────────────────

Proficiency measures how capable the student is at a skill.

Base formula for a single assessment attempt:

  raw_score = correct_points / total_points * 100

Difficulty weighting — harder correct answers count more:
  easy   correct = 1.0 pt
  medium correct = 1.5 pt
  hard   correct = 2.0 pt

  difficulty_multiplier = correct_easy*1.0 + correct_medium*1.5 + correct_hard*2.0
                          / (total_easy*1.0 + total_medium*1.5 + total_hard*2.0)
  proficiency = raw_score * difficulty_multiplier

Recency weighting — if a student has multiple attempts, more recent results
carry more weight. The formula applies exponential decay:

  weight_i = exp(-λ * days_since_attempt_i)  where λ = 0.05
  proficiency = Σ(proficiency_i * weight_i) / Σ(weight_i)

Proficiency is clamped to [0, 100].

────────────────────────────────────────────────────────────────────────────────
CONFIDENCE SCORE (0–100)
────────────────────────────────────────────────────────────────────────────────

Confidence measures how trustworthy the evidence is.

Base confidence from assessment performance:
  questions_answered < 5  → base_confidence = 30
  questions_answered 5–9  → base_confidence = 50
  questions_answered 10+  → base_confidence = 70

Credibility ceiling (from EvidenceCredibility):
  claimed      → max_confidence = 30
  demonstrated → max_confidence = 75
  verified     → max_confidence = 100

Multi-attempt bonus (capped):
  1 attempt  → +0
  2 attempts → +5
  3 attempts → +10
  4+ attempts → +15

Flagged attempt penalty:
  -20 per flagged attempt

confidence = min(
    base_confidence + multi_attempt_bonus - flag_penalty,
    max_confidence (from credibility)
)
confidence = clamp(confidence, 0, 100)

────────────────────────────────────────────────────────────────────────────────
ADAPTIVE ROUTING
────────────────────────────────────────────────────────────────────────────────

The adaptive engine adjusts question difficulty based on streaks:

  correct_streak >= 2 → upgrade difficulty (easy→medium, medium→hard)
  incorrect_streak >= 2 → downgrade difficulty (hard→medium, medium→easy)
  otherwise → maintain current difficulty

This is the same algorithm described in project spec section 21.

────────────────────────────────────────────────────────────────────────────────
PROFICIENCY BANDS
────────────────────────────────────────────────────────────────────────────────

  0–39   → BEGINNER
  40–59  → ELEMENTARY
  60–74  → INTERMEDIATE
  75–89  → ADVANCED
  90–100 → EXPERT
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from app.models.assessment import DifficultyLevel, EvidenceCredibility


# ─── Constants ────────────────────────────────────────────────────────────────

DIFFICULTY_WEIGHTS: dict[DifficultyLevel, float] = {
    DifficultyLevel.EASY: 1.0,
    DifficultyLevel.MEDIUM: 1.5,
    DifficultyLevel.HARD: 2.0,
}

RECENCY_DECAY_LAMBDA: float = 0.05  # Per-day exponential decay

CREDIBILITY_CONFIDENCE_CAP: dict[EvidenceCredibility, float] = {
    EvidenceCredibility.CLAIMED: 30.0,
    EvidenceCredibility.DEMONSTRATED: 75.0,
    EvidenceCredibility.VERIFIED: 100.0,
}

PROFICIENCY_BANDS: list[tuple[float, str]] = [
    (90.0, "expert"),
    (75.0, "advanced"),
    (60.0, "intermediate"),
    (40.0, "elementary"),
    (0.0, "beginner"),
]


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class AnswerRecord:
    """Single answer in an attempt, used for scoring calculations."""
    is_correct: bool
    difficulty: DifficultyLevel
    question_points: float = 1.0


@dataclass
class AttemptRecord:
    """One completed attempt, used for multi-attempt aggregation."""
    proficiency_score: float
    question_count: int
    is_flagged: bool
    completed_at: datetime


@dataclass
class ScoringResult:
    """Output of the scoring engine for a single attempt."""
    raw_score: float            # Simple percentage correct
    proficiency_score: float    # Difficulty-weighted proficiency (0–100)
    confidence_score: float     # Evidence quality score (0–100)
    proficiency_level: str      # Named band (beginner, intermediate, etc.)
    total_questions: int
    correct_count: int


@dataclass
class AggregatedSkillScore:
    """
    Final aggregated skill score for a student,
    incorporating all attempts with recency weighting.
    """
    proficiency: float
    confidence: float
    credibility: EvidenceCredibility
    proficiency_level: str
    assessment_count: int


# ─── Core scoring functions ───────────────────────────────────────────────────

def score_attempt(answers: Sequence[AnswerRecord]) -> ScoringResult:
    """
    Score a single completed assessment attempt.

    Args:
        answers: All answers submitted in this attempt.

    Returns:
        ScoringResult with proficiency and confidence scores.

    This is the primary function called by the AssessmentService when
    an attempt is submitted.
    """
    if not answers:
        return ScoringResult(
            raw_score=0.0,
            proficiency_score=0.0,
            confidence_score=0.0,
            proficiency_level="beginner",
            total_questions=0,
            correct_count=0,
        )

    total_questions = len(answers)
    correct_count = sum(1 for a in answers if a.is_correct)

    # ── Raw score (simple percentage) ─────────────────────────────────────────
    raw_score = (correct_count / total_questions) * 100.0

    # ── Difficulty-weighted proficiency ───────────────────────────────────────
    total_weighted_possible = sum(
        DIFFICULTY_WEIGHTS[a.difficulty] * a.question_points for a in answers
    )
    total_weighted_earned = sum(
        DIFFICULTY_WEIGHTS[a.difficulty] * a.question_points
        for a in answers if a.is_correct
    )

    if total_weighted_possible > 0:
        difficulty_ratio = total_weighted_earned / total_weighted_possible
    else:
        difficulty_ratio = 0.0

    proficiency_score = _clamp(difficulty_ratio * 100.0, 0.0, 100.0)

    # ── Confidence from question count ────────────────────────────────────────
    if total_questions < 5:
        base_confidence = 30.0
    elif total_questions < 10:
        base_confidence = 50.0
    else:
        base_confidence = 70.0

    # Demonstrated credibility cap (single attempt always = demonstrated)
    confidence_score = _clamp(
        base_confidence,
        0.0,
        CREDIBILITY_CONFIDENCE_CAP[EvidenceCredibility.DEMONSTRATED],
    )

    proficiency_level = get_proficiency_level(proficiency_score)

    return ScoringResult(
        raw_score=round(raw_score, 2),
        proficiency_score=round(proficiency_score, 2),
        confidence_score=round(confidence_score, 2),
        proficiency_level=proficiency_level,
        total_questions=total_questions,
        correct_count=correct_count,
    )


def aggregate_skill_score(
    attempts: Sequence[AttemptRecord],
    credibility: EvidenceCredibility = EvidenceCredibility.DEMONSTRATED,
) -> AggregatedSkillScore:
    """
    Aggregate multiple attempt results into a single skill score.

    Uses recency-weighted averaging so recent performance matters more.
    This is the function that updates StudentSkill.proficiency and
    StudentSkill.confidence after each completed attempt.

    Args:
        attempts: All completed, non-abandoned attempts for this skill.
        credibility: Current evidence credibility level for this student+skill.

    Returns:
        AggregatedSkillScore with final proficiency and confidence values.
    """
    if not attempts:
        return AggregatedSkillScore(
            proficiency=0.0,
            confidence=0.0,
            credibility=EvidenceCredibility.CLAIMED,
            proficiency_level="beginner",
            assessment_count=0,
        )

    now = datetime.now(timezone.utc)
    assessment_count = len(attempts)

    # ── Recency-weighted proficiency ──────────────────────────────────────────
    weights: list[float] = []
    for attempt in attempts:
        completed = attempt.completed_at
        if completed.tzinfo is None:
            completed = completed.replace(tzinfo=timezone.utc)
        days_ago = max(0.0, (now - completed).total_seconds() / 86400.0)
        weight = math.exp(-RECENCY_DECAY_LAMBDA * days_ago)
        weights.append(weight)

    total_weight = sum(weights)
    if total_weight == 0:
        total_weight = 1.0

    weighted_proficiency = sum(
        attempt.proficiency_score * weight
        for attempt, weight in zip(attempts, weights)
    ) / total_weight

    proficiency = _clamp(weighted_proficiency, 0.0, 100.0)

    # ── Confidence calculation ─────────────────────────────────────────────────
    # Base confidence from question coverage (approximate from attempt count)
    avg_questions = sum(a.question_count for a in attempts) / assessment_count
    if avg_questions < 5:
        base_confidence = 30.0
    elif avg_questions < 10:
        base_confidence = 50.0
    else:
        base_confidence = 70.0

    # Multi-attempt bonus
    attempt_bonus = min(15.0, (assessment_count - 1) * 5.0)

    # Flag penalty
    flagged_count = sum(1 for a in attempts if a.is_flagged)
    flag_penalty = flagged_count * 20.0

    # Credibility ceiling
    credibility_cap = CREDIBILITY_CONFIDENCE_CAP[credibility]

    confidence = _clamp(
        base_confidence + attempt_bonus - flag_penalty,
        0.0,
        credibility_cap,
    )

    return AggregatedSkillScore(
        proficiency=round(proficiency, 2),
        confidence=round(confidence, 2),
        credibility=credibility,
        proficiency_level=get_proficiency_level(proficiency),
        assessment_count=assessment_count,
    )


# ─── Adaptive routing ─────────────────────────────────────────────────────────

def next_question_difficulty(
    current_difficulty: DifficultyLevel,
    recent_answers: Sequence[bool],
) -> DifficultyLevel:
    """
    Determine the next question's difficulty based on recent answer streak.

    Algorithm (from project spec section 21):
      correct_streak >= 2 → upgrade difficulty
      incorrect_streak >= 2 → downgrade difficulty
      otherwise → maintain

    Args:
        current_difficulty: Difficulty of the most recent question.
        recent_answers: Boolean list of recent answers (True=correct), most recent last.

    Returns:
        DifficultyLevel for the next question.
    """
    if len(recent_answers) < 2:
        return current_difficulty

    last_two = list(recent_answers[-2:])

    if all(last_two):  # Both correct → upgrade
        return _upgrade_difficulty(current_difficulty)
    elif not any(last_two):  # Both wrong → downgrade
        return _downgrade_difficulty(current_difficulty)
    else:
        return current_difficulty


def _upgrade_difficulty(d: DifficultyLevel) -> DifficultyLevel:
    if d == DifficultyLevel.EASY:
        return DifficultyLevel.MEDIUM
    if d == DifficultyLevel.MEDIUM:
        return DifficultyLevel.HARD
    return DifficultyLevel.HARD  # Already at max


def _downgrade_difficulty(d: DifficultyLevel) -> DifficultyLevel:
    if d == DifficultyLevel.HARD:
        return DifficultyLevel.MEDIUM
    if d == DifficultyLevel.MEDIUM:
        return DifficultyLevel.EASY
    return DifficultyLevel.EASY  # Already at min


# ─── Utilities ────────────────────────────────────────────────────────────────

def get_proficiency_level(score: float) -> str:
    """Map a numeric proficiency score to a named band."""
    for threshold, level in PROFICIENCY_BANDS:
        if score >= threshold:
            return level
    return "beginner"


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))
