import unittest

from question_counts import extract_amboss_count, extract_mksap_completed_count


class QuestionCountParsingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
