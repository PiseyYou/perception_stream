import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))


class ShadowReviewTest(unittest.TestCase):
    def _manifest(self, count=35):
        return {"images": [{"path": f"nested/image-{index:02d}.jpg", "branches": {"A": {"frame_id": index}, "B": {"frame_id": index}}} for index in range(count)]}

    def test_fixed_seed_selects_same_anonymous_samples_without_path_leakage(self):
        from prelabel_pipeline.shadow_review import create_review, public_payload

        first = create_review(self._manifest(), seed="stable-seed")
        second = create_review(self._manifest(), seed="stable-seed")
        self.assertEqual(first["samples"], second["samples"])
        self.assertEqual(len(first["samples"]), 30)
        payload = public_payload("run-123", first)
        serialized = str(payload)
        self.assertNotIn("image-", serialized)
        self.assertNotIn("nested", serialized)
        self.assertNotIn("branches", serialized)
        self.assertEqual(set(payload["samples"][0]), {"sample_id", "left", "right"})

    def test_submit_is_single_use_per_reviewer_and_early_reveal_is_rejected(self):
        from prelabel_pipeline.shadow_review import create_review, issue_reviewer_capability, reveal, submit_review

        review = create_review(self._manifest(2), seed="seed")
        answers = {sample["sample_id"]: "X better" for sample in review["samples"]}
        self.assertFalse(reveal(review)["allowed"])
        capability = issue_reviewer_capability(review)
        submit_review(review, capability, answers)
        with self.assertRaisesRegex(ValueError, "already submitted"):
            submit_review(review, capability, answers)

    def test_submit_requires_all_sample_answers_before_review_can_close(self):
        from prelabel_pipeline.shadow_review import create_review, issue_reviewer_capability, submit_review

        review = create_review(self._manifest(2), seed="seed")
        with self.assertRaisesRegex(ValueError, "every review sample"):
            submit_review(review, issue_reviewer_capability(review), {"s001": "tie"})
        self.assertEqual(review["decision"]["status"], "pending")

    def test_decision_requires_24_valid_votes_and_20_point_candidate_margin(self):
        from prelabel_pipeline.shadow_review import create_review, issue_reviewer_capability, submit_review

        review = create_review(self._manifest(23), seed="seed")
        answers = {sample["sample_id"]: "X better" for sample in review["samples"]}
        submit_review(review, issue_reviewer_capability(review), answers)
        self.assertEqual(review["decision"]["status"], "no_decision")

        review = create_review(self._manifest(30), seed="seed")
        answers = {sample_id: "X better" if private["X"] == "B" else "Y better" for sample_id, private in review["private_samples"].items()}
        submit_review(review, issue_reviewer_capability(review), answers)
        self.assertEqual(review["decision"]["valid_votes"], 30)
        self.assertEqual(review["decision"]["status"], "candidate_wins")

    def test_capability_is_required_once_and_is_not_in_public_payload(self):
        from prelabel_pipeline.shadow_review import create_review, issue_reviewer_capability, public_payload, submit_review

        review = create_review(self._manifest(2), seed="seed")
        with self.assertRaisesRegex(ValueError, "capability"):
            submit_review(review, "forged", {"s001": "tie", "s002": "tie"})
        capability = issue_reviewer_capability(review)
        self.assertNotIn(capability, str(public_payload("run-123", review)))
        submit_review(review, capability, {"s001": "tie", "s002": "tie"})
        self.assertNotIn(capability, str(review["submissions"]))
