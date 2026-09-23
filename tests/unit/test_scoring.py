"""
Tests for the deterministic scoring engine.
These tests verify the algorithms described in app/core/scoring.py.

Every test has a comment explaining WHY the expected value is what it is —
so SIH judges can trace the calculation.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.scoring import (
    AnswerRecord,
    AttemptRecord,
    AggregatedSkillScore,
    aggregate_skill_score,
    get_proficiency_level,
    next_question_difficulty,
    score_attempt,
    _clamp,
    DIFFICULTY_WEIGHTS,
)
from app.models.assessment import DifficultyLevel, EvidenceCredibility


# ─── Proficiency band tests ───────────────────────────────────────────────────

class TestProficiencyBands:
    def test_expert_band(self):
        assert get_proficiency_level(95.0) == "expert"
        assert get_proficiency_level(90.0) == "expert"

    def test_advanced_band(self):
        assert get_proficiency_level(89.9) == "advanced"
        assert get_proficiency_level(75.0) == "advanced"

    def test_intermediate_band(self):
        assert get_proficiency_level(74.9) == "intermediate"
        assert get_proficiency_level(60.0) == "intermediate"

    def test_elementary_band(self):
        assert get_proficiency_level(59.9) == "elementary"
        assert get_proficiency_level(40.0) == "elementary"

    def test_beginner_band(self):
        assert get_proficiency_level(39.9) == "beginner"
        assert get_proficiency_level(0.0) == "beginner"


# ─── Single attempt scoring ───────────────────────────────────────────────────

class TestScoreAttempt:
    def test_empty_answers_returns_zero(self):
        result = score_attempt([])
        assert result.proficiency_score == 0.0
        assert result.confidence_score == 0.0
        assert result.total_questions == 0
        assert result.correct_count == 0

    def test_perfect_score_all_easy(self):
        """10 easy correct answers → difficulty_ratio = 1.0 → proficiency = 100."""
        answers = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY)
            for _ in range(10)
        ]
        result = score_attempt(answers)
        assert result.proficiency_score == 100.0
        assert result.raw_score == 100.0
        assert result.correct_count == 10

    def test_zero_score(self):
        """All wrong answers → proficiency = 0."""
        answers = [
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.MEDIUM)
            for _ in range(10)
        ]
        result = score_attempt(answers)
        assert result.proficiency_score == 0.0
        assert result.raw_score == 0.0
        assert result.correct_count == 0

    def test_difficulty_weighting_hard_beats_easy(self):
        """
        Student A: 5/10 correct, all EASY    → weighted = 5*1.0 / 10*1.0 = 50.0
        Student B: 5/10 correct, all HARD    → weighted = 5*2.0 / 10*2.0 = 50.0
        BUT Student B answered harder questions correctly, so same ratio.
        Let's test mixed: 5 hard correct vs 5 easy correct with same total.
        """
        # 5 correct HARD + 5 wrong EASY
        answers_hard = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.EASY),
        ]
        # 5 correct EASY + 5 wrong HARD
        answers_easy = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.HARD),
        ]

        result_hard = score_attempt(answers_hard)
        result_easy = score_attempt(answers_easy)

        # Hard correct: earned = 5*2.0=10, possible = 5*2.0 + 5*1.0 = 15 → 66.7
        # Easy correct: earned = 5*1.0=5,  possible = 5*1.0 + 5*2.0 = 15 → 33.3
        assert result_hard.proficiency_score > result_easy.proficiency_score

    def test_raw_score_is_simple_percentage(self):
        """raw_score = correct/total * 100, ignoring difficulty."""
        answers = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY),
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.MEDIUM),
            AnswerRecord(is_correct=False, difficulty=DifficultyLevel.EASY),
        ]
        result = score_attempt(answers)
        # 2 correct out of 4 → 50.0
        assert result.raw_score == 50.0
        assert result.correct_count == 2
        assert result.total_questions == 4

    def test_confidence_low_for_few_questions(self):
        """< 5 questions → base_confidence = 30."""
        answers = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.EASY)
            for _ in range(4)
        ]
        result = score_attempt(answers)
        assert result.confidence_score == 30.0

    def test_confidence_medium_for_5_to_9_questions(self):
        """5–9 questions → base_confidence = 50."""
        answers = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.MEDIUM)
            for _ in range(7)
        ]
        result = score_attempt(answers)
        assert result.confidence_score == 50.0

    def test_confidence_high_for_10_plus_questions(self):
        """10+ questions → base_confidence = 70 (capped at demonstrated = 75)."""
        answers = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.MEDIUM)
            for _ in range(15)
        ]
        result = score_attempt(answers)
        assert result.confidence_score == 70.0

    def test_proficiency_score_clamped_to_100(self):
        answers = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD)
            for _ in range(10)
        ]
        result = score_attempt(answers)
        assert result.proficiency_score <= 100.0

    def test_proficiency_level_assigned(self):
        answers = [
            AnswerRecord(is_correct=True, difficulty=DifficultyLevel.HARD)
            for _ in range(10)
        ]
        result = score_attempt(answers)
        assert result.proficiency_level == "expert"


# ─── Multi-attempt aggregation ────────────────────────────────────────────────

class TestAggregateSkillScore:
    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def test_single_attempt(self):
        attempts = [
            AttemptRecord(
                proficiency_score=75.0,
                question_count=10,
                is_flagged=False,
                completed_at=self._now(),
            )
        ]
        result = aggregate_skill_score(attempts, EvidenceCredibility.DEMONSTRATED)
        assert result.proficiency == 75.0
        assert result.assessment_count == 1
        assert result.credibility == EvidenceCredibility.DEMONSTRATED

    def test_empty_attempts_returns_zero(self):
        result = aggregate_skill_score([], EvidenceCredibility.CLAIMED)
        assert result.proficiency == 0.0
        assert result.confidence == 0.0
        assert result.assessment_count == 0

    def test_recency_weights_recent_higher(self):
        """
        Recent attempt (score=90) should pull the aggregate above a simple average.
        Old attempt (score=40, 30 days ago) should be downweighted.
        Simple average would be 65.0. Recency-weighted should be > 65.
        """
        now = self._now()
        attempts = [
            AttemptRecord(
                proficiency_score=40.0,
                question_count=10,
                is_flagged=False,
                completed_at=now - timedelta(days=30),
            ),
            AttemptRecord(
                proficiency_score=90.0,
                question_count=10,
                is_flagged=False,
                completed_at=now,
            ),
        ]
        result = aggregate_skill_score(attempts, EvidenceCredibility.DEMONSTRATED)
        # Recency-weighted avg should be > 65 (simple average)
        assert result.proficiency > 65.0

    def test_multi_attempt_bonus_increases_confidence(self):
        now = self._now()
        one_attempt = [
            AttemptRecord(proficiency_score=70.0, question_count=10,
                         is_flagged=False, completed_at=now)
        ]
        three_attempts = [
            AttemptRecord(proficiency_score=70.0, question_count=10,
                         is_flagged=False, completed_at=now)
            for _ in range(3)
        ]
        result_one = aggregate_skill_score(one_attempt, EvidenceCredibility.DEMONSTRATED)
        result_three = aggregate_skill_score(three_attempts, EvidenceCredibility.DEMONSTRATED)
        # 3 attempts should have higher confidence than 1
        assert result_three.confidence > result_one.confidence

    def test_flagged_attempt_reduces_confidence(self):
        now = self._now()
        clean = [
            AttemptRecord(proficiency_score=80.0, question_count=10,
                         is_flagged=False, completed_at=now)
        ]
        flagged = [
            AttemptRecord(proficiency_score=80.0, question_count=10,
                         is_flagged=True, completed_at=now)
        ]
        result_clean = aggregate_skill_score(clean, EvidenceCredibility.DEMONSTRATED)
        result_flagged = aggregate_skill_score(flagged, EvidenceCredibility.DEMONSTRATED)
        assert result_clean.confidence > result_flagged.confidence

    def test_credibility_cap_claimed(self):
        """Claimed credibility caps confidence at 30."""
        now = self._now()
        attempts = [
            AttemptRecord(proficiency_score=95.0, question_count=15,
                         is_flagged=False, completed_at=now)
            for _ in range(5)
        ]
        result = aggregate_skill_score(attempts, EvidenceCredibility.CLAIMED)
        assert result.confidence <= 30.0

    def test_credibility_cap_verified(self):
        """Verified credibility allows confidence up to 100."""
        now = self._now()
        attempts = [
            AttemptRecord(proficiency_score=95.0, question_count=15,
                         is_flagged=False, completed_at=now)
            for _ in range(5)
        ]
        result = aggregate_skill_score(attempts, EvidenceCredibility.VERIFIED)
        # Should be higher than demonstrated cap (75)
        assert result.confidence > 75.0

    def test_confidence_never_exceeds_100(self):
        now = self._now()
        attempts = [
            AttemptRecord(proficiency_score=100.0, question_count=20,
                         is_flagged=False, completed_at=now)
            for _ in range(10)
        ]
        result = aggregate_skill_score(attempts, EvidenceCredibility.VERIFIED)
        assert result.confidence <= 100.0

    def test_proficiency_always_in_range(self):
        now = self._now()
        attempts = [
            AttemptRecord(proficiency_score=100.0, question_count=10,
                         is_flagged=False, completed_at=now)
        ]
        result = aggregate_skill_score(attempts, EvidenceCredibility.DEMONSTRATED)
        assert 0.0 <= result.proficiency <= 100.0


# ─── Adaptive routing ─────────────────────────────────────────────────────────

class TestAdaptiveRouting:
    def test_two_correct_upgrades_easy_to_medium(self):
        result = next_question_difficulty(DifficultyLevel.EASY, [True, True])
        assert result == DifficultyLevel.MEDIUM

    def test_two_correct_upgrades_medium_to_hard(self):
        result = next_question_difficulty(DifficultyLevel.MEDIUM, [True, True])
        assert result == DifficultyLevel.HARD

    def test_already_hard_stays_hard(self):
        result = next_question_difficulty(DifficultyLevel.HARD, [True, True])
        assert result == DifficultyLevel.HARD

    def test_two_wrong_downgrades_hard_to_medium(self):
        result = next_question_difficulty(DifficultyLevel.HARD, [False, False])
        assert result == DifficultyLevel.MEDIUM

    def test_two_wrong_downgrades_medium_to_easy(self):
        result = next_question_difficulty(DifficultyLevel.MEDIUM, [False, False])
        assert result == DifficultyLevel.EASY

    def test_already_easy_stays_easy(self):
        result = next_question_difficulty(DifficultyLevel.EASY, [False, False])
        assert result == DifficultyLevel.EASY

    def test_mixed_results_maintains_difficulty(self):
        """One correct, one wrong → no change."""
        result = next_question_difficulty(DifficultyLevel.MEDIUM, [True, False])
        assert result == DifficultyLevel.MEDIUM

        result = next_question_difficulty(DifficultyLevel.MEDIUM, [False, True])
        assert result == DifficultyLevel.MEDIUM

    def test_only_last_two_matter(self):
        """
        Even if earlier answers were all correct, only last 2 are checked.
        Streak of 5 correct but last 2 include a wrong: no upgrade.
        """
        result = next_question_difficulty(
            DifficultyLevel.EASY, [True, True, True, True, False]
        )
        # Last two: [True, False] → mixed → no change
        assert result == DifficultyLevel.EASY

    def test_fewer_than_two_answers_no_change(self):
        """Cannot determine streak with < 2 answers."""
        result = next_question_difficulty(DifficultyLevel.MEDIUM, [True])
        assert result == DifficultyLevel.MEDIUM

        result = next_question_difficulty(DifficultyLevel.MEDIUM, [])
        assert result == DifficultyLevel.MEDIUM


# ─── Clamp utility ────────────────────────────────────────────────────────────

class TestClamp:
    def test_value_within_range(self):
        assert _clamp(50.0, 0.0, 100.0) == 50.0

    def test_value_below_min(self):
        assert _clamp(-10.0, 0.0, 100.0) == 0.0

    def test_value_above_max(self):
        assert _clamp(150.0, 0.0, 100.0) == 100.0

    def test_exactly_at_boundaries(self):
        assert _clamp(0.0, 0.0, 100.0) == 0.0
        assert _clamp(100.0, 0.0, 100.0) == 100.0


# ─── SIH demo scenario ────────────────────────────────────────────────────────

class TestSIHDemoScenario:
    """
    Validates the exact SIH demo scenario from project spec section 52 & 82.
    Student:
      Python: 87, SQL: 81, REST API: 73, Docker: 31, AWS: 22
    These are proficiency scores after assessment.
    """

    def _make_attempt_with_score(self, score: float) -> AttemptRecord:
        return AttemptRecord(
            proficiency_score=score,
            question_count=15,
            is_flagged=False,
            completed_at=datetime.now(timezone.utc),
        )

    def test_python_87_is_advanced(self):
        assert get_proficiency_level(87.0) == "advanced"

    def test_sql_81_is_advanced(self):
        assert get_proficiency_level(81.0) == "advanced"

    def test_rest_api_73_is_intermediate(self):
        assert get_proficiency_level(73.0) == "intermediate"

    def test_docker_31_is_beginner(self):
        assert get_proficiency_level(31.0) == "beginner"

    def test_aws_22_is_beginner(self):
        assert get_proficiency_level(22.0) == "beginner"

    def test_aggregated_scores_match_demo(self):
        """
        After a single assessment that yielded the demo scores,
        the aggregated proficiency should match within 0.1.
        """
        for expected_score in [87.0, 81.0, 73.0, 31.0, 22.0]:
            attempts = [self._make_attempt_with_score(expected_score)]
            result = aggregate_skill_score(attempts, EvidenceCredibility.DEMONSTRATED)
            assert abs(result.proficiency - expected_score) < 0.1, (
                f"Expected proficiency ~{expected_score}, got {result.proficiency}"
            )
