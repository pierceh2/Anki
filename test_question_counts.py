import unittest
from datetime import datetime

from question_counts import (
    EASTERN,
    extract_amboss_count,
    extract_mksap_completed_count,
    login_failure_reason,
    scheduled_run_target,
)


class QuestionCountParsingTests(unittest.TestCase):
    def test_scheduled_run_target_uses_fixed_noon_time(self) -> None:
        now = datetime(2025, 1, 15, 11, 45, tzinfo=EASTERN)
        self.assertEqual(
            scheduled_run_target(now),
            datetime(2025, 1, 15, 12, 0, tzinfo=EASTERN),
        )

    def test_scheduled_run_target_rejects_times_outside_windows(self) -> None:
        now = datetime(2025, 1, 15, 13, 0, tzinfo=EASTERN)
        self.assertIsNone(scheduled_run_target(now))

    def test_extract_mksap_completed_count_handles_live_text_variants(self) -> None:
        self.assertEqual(extract_mksap_completed_count("56 Completed QuestionsReview"), 56)
        self.assertEqual(
            extract_mksap_completed_count("Your progress: 56 completed questions"), 56
        )
        self.assertEqual(extract_mksap_completed_count("Questions answered 56 out of 200"), 56)

    def test_extract_amboss_count_handles_analysis_text(self) -> None:
        text = "Your performance analysis for Cardiology\nQuestions answered 56 out of 200"
        bank, count = extract_amboss_count(text)
        self.assertEqual(bank, "Cardiology")
        self.assertEqual(count, 56)

    def test_extract_amboss_count_uses_attempts_not_unique_questions(self) -> None:
        text = (
            "Your performance analysis for Cardiology\n"
            "Overall you answered 108 attempts across 99 unique questions."
        )
        bank, count = extract_amboss_count(text)
        self.assertEqual(bank, "Cardiology")
        self.assertEqual(count, 108)

    def test_login_failure_reason_detects_real_auth_blockers(self) -> None:
        self.assertIn("rejected the submitted credentials", login_failure_reason("Invalid password", "AMBOSS"))
        self.assertIn("rejected the submitted credentials", login_failure_reason("Your username or password is incorrect.", "MKSAP"))
        self.assertIn("second-factor", login_failure_reason("We need your verification code", "AMBOSS"))
        self.assertIsNone(login_failure_reason("Welcome back", "AMBOSS"))
        self.assertIsNone(login_failure_reason("Login page with A Robust Question Bank", "MKSAP"))


if __name__ == "__main__":
    unittest.main()
