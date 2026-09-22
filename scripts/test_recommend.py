"""Recommendation ranking accepts recorded RFC3339 timestamps without changing priorities."""

import unittest

from recommend import rank, tier_models

MODELS = ["preferred", "fallback"]


def recipe(accepted_at=None, model="preferred", engine="llama.cpp", context=8192, vision=None):
    return {
        "_model_id": model,
        "engine": {"name": engine},
        "serving": {"max_context_tokens": context},
        "capabilities": {"vision": vision},
        "metadata": {"acceptance": {"accepted_at": accepted_at}},
    }


class RecommendationRankTests(unittest.TestCase):
    def test_fractional_utc_offsets_and_missing_acceptance(self):
        utc = recipe("2026-09-11T20:49:14.598848Z")
        for equivalent in ("2026-09-12T02:19:14.598848+05:30", "2026-09-11T16:49:14.598848-04:00"):
            with self.subTest(equivalent=equivalent):
                self.assertEqual(rank(utc, MODELS), rank(recipe(equivalent), MODELS))
        newer = recipe("2026-09-11T20:49:14.598849Z")
        self.assertLess(rank(newer, MODELS), rank(utc, MODELS))
        missing = recipe()
        del missing["metadata"]["acceptance"]["accepted_at"]
        self.assertGreater(rank(missing, MODELS), rank(utc, MODELS))
        self.assertIs(min([missing, utc, newer], key=lambda r: rank(r, MODELS)), newer)

    def test_tier_engine_and_context_still_precede_recency(self):
        older, newer = "2026-09-10T00:00:00Z", "2026-09-11T20:49:14.598848Z"
        pairs = (
            (recipe(older, engine="unknown", context=1),
             recipe(newer, model="fallback", engine="tabbyapi", context=131072)),
            (recipe(older, engine="sglang", context=1), recipe(newer, context=131072)),
            (recipe(older, context=8192), recipe(newer, context=4096)),
        )
        for preferred, other in pairs:
            with self.subTest(preferred=preferred):
                self.assertLess(rank(preferred, MODELS), rank(other, MODELS))

    def test_vision_precedes_context_but_not_engine_or_tier(self):
        older, newer = "2026-09-10T00:00:00Z", "2026-09-11T20:49:14.598848Z"
        seeing = recipe(older, engine="tabbyapi", context=131072, vision=True)
        blind = recipe(newer, engine="tabbyapi", context=262144, vision=False)
        self.assertLess(rank(seeing, MODELS), rank(blind, MODELS))
        self.assertLess(rank(recipe(older, engine="tabbyapi"), MODELS), rank(recipe(newer, engine="sglang", vision=True), MODELS))
        self.assertLess(rank(recipe(older), MODELS), rank(recipe(newer, model="fallback", vision=True), MODELS))
        self.assertEqual(rank(recipe(older), MODELS), rank(recipe(older, vision=None), MODELS))

    def test_tier_map_by_vram(self):
        self.assertEqual(tier_models(96), ["qwen3-8-27b", "qwen3-5-9b", "lfm2-5-2-6b"])
        self.assertEqual(tier_models(16), ["qwen3-8-27b", "qwen3-5-9b", "lfm2-5-2-6b"])
        self.assertEqual(tier_models(12), ["qwen3-5-9b", "lfm2-5-2-6b"])
        self.assertEqual(tier_models(10), ["lfm2-5-2-6b"])
        self.assertEqual(tier_models(8), ["lfm2-5-2-6b"])


if __name__ == "__main__":
    unittest.main()
