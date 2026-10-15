"""Tests for the smart theme search helpers in main.py.

Run with: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

# main.py imports the `decky` module that only exists inside Decky Loader.
sys.modules.setdefault("decky", types.ModuleType("decky"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


def _result(title: str, duration: int | None = 200, uploader: str = "Someone") -> dict:
    return {
        "id": title,
        "title": title,
        "uploader": uploader,
        "duration": duration,
        "webpage_url": f"https://www.youtube.com/watch?v={abs(hash(title))}",
    }


class TrademarkTest(unittest.TestCase):
    def test_only_symbols_are_removed(self) -> None:
        self.assertEqual(main.strip_trademark_symbols("Need for Speed™ Heat"), "Need for Speed Heat")
        self.assertEqual(main.strip_trademark_symbols("Crimson Desert Enhanced"), "Crimson Desert Enhanced")
        self.assertEqual(main.strip_trademark_symbols("Sid Meier's Civilization® VI"), "Sid Meier's Civilization VI")


class PickWikidataLabelTest(unittest.TestCase):
    def test_prefers_base_game_matching_steam_name(self) -> None:
        self.assertEqual(
            main.pick_wikidata_label(
                "Divinity: Original Sin 2 - Definitive Edition",
                ["Divinity: Original Sin 2 - Definitive Edition", "Divinity: Original Sin 2"],
            ),
            "Divinity: Original Sin 2",
        )

    def test_edition_removed_by_wikidata(self) -> None:
        self.assertEqual(
            main.pick_wikidata_label("Crimson Desert Enhanced", ["Crimson Desert"]),
            "Crimson Desert",
        )

    def test_ignores_entity_ids_and_empty(self) -> None:
        self.assertIsNone(main.pick_wikidata_label("ELDEN RING", ["Q64826862"]))
        self.assertIsNone(main.pick_wikidata_label("ELDEN RING", []))

    def test_case_differences(self) -> None:
        self.assertEqual(main.pick_wikidata_label("ELDEN RING", ["Elden Ring"]), "Elden Ring")


class ScoreThemeResultTest(unittest.TestCase):
    names = ["Crimson Desert", "Crimson Desert Enhanced"]

    def score(self, *args, **kwargs) -> float:
        return main.score_theme_result(_result(*args, **kwargs), self.names)

    def test_main_theme_beats_trailer_and_covers(self) -> None:
        main_theme = self.score("Crimson Desert - Main Theme (Official Soundtrack)")
        trailer = self.score("Crimson Desert - Official Gameplay Trailer")
        cover = self.score("Crimson Desert Main Theme | Piano Cover")
        long_mix = self.score("Crimson Desert OST - 1 Hour Extended", duration=590)
        self.assertGreater(main_theme, main.THEME_CONFIDENT_SCORE)
        self.assertLess(trailer, main.THEME_MIN_ACCEPT_SCORE)
        self.assertLess(cover, main_theme)
        self.assertLess(long_mix, main_theme)

    def test_other_games_are_rejected(self) -> None:
        self.assertEqual(self.score("Black Desert Online - Main Theme"), -100.0)

    def test_ost_is_a_whole_word(self) -> None:
        names = ["Ghost of Tsushima"]
        plain = main.score_theme_result(_result("Ghost of Tsushima gameplay part 1", duration=1500), names)
        self.assertLess(plain, main.THEME_MIN_ACCEPT_SCORE)

    def test_keywords_in_game_name_are_not_penalised(self) -> None:
        names = ["Darkest Hour"]
        theme = main.score_theme_result(_result("Darkest Hour - Main Theme"), names)
        self.assertGreaterEqual(theme, main.THEME_CONFIDENT_SCORE)

    def test_topic_channel_bonus(self) -> None:
        topic = self.score("Crimson Desert", uploader="Pearl Abyss - Topic")
        other = self.score("Crimson Desert", uploader="Random")
        self.assertGreater(topic, other)


class RankThemeResultsTest(unittest.TestCase):
    def test_orders_best_first_and_drops_weak(self) -> None:
        results = [
            _result("Crimson Desert Gameplay Walkthrough Part 1", duration=3000),
            _result("Crimson Desert OST - Battle Theme 3"),
            _result("Crimson Desert - Main Menu Theme"),
            _result("Black Desert Remastered OST"),
        ]
        ranked = main.rank_theme_results(results, ["Crimson Desert"])
        self.assertEqual(
            [r["title"] for r in ranked],
            ["Crimson Desert - Main Menu Theme", "Crimson Desert OST - Battle Theme 3"],
        )
        self.assertIn("score", ranked[0])

    def test_empty_when_nothing_matches(self) -> None:
        self.assertEqual(
            main.rank_theme_results([_result("Totally unrelated video")], ["Crimson Desert"]),
            [],
        )


class RealSearchResultsTest(unittest.TestCase):
    """Search results captured from YouTube for "Crimson Desert main theme" (2026-10-15)."""

    @staticmethod
    def _yt(title: str, duration: int, views: int, uploader: str) -> dict:
        return {**_result(title, duration=duration, uploader=uploader), "view_count": views}

    def test_crimson_desert(self) -> None:
        results = [
            self._yt("Crimson Desert - Main Menu Theme", 500, 33723, "Ruba"),
            self._yt("Crimson Desert - Main Theme - Soundtrack", 243, 31817, "HeXenkingTV"),
            self._yt("Crimson Desert | Loading Screen Theme 1 (Entering Pywel) - Lone Wolf", 308, 61513, "Finding Purposes"),
            self._yt("Lone Wolf", 113, 37362, "PearlAbyssMusic - Topic"),
            self._yt("Crimson Desert Main Theme OST | Full Version (Loading Soundtrack)", 275, 3879, "Jin Sakai"),
            self._yt("Crimson Desert Main Menu Music (1 Hour) | Deep Focus, Study & Relaxing", 4869, 323, "Dark Fantasy Lofi"),
        ]
        ranked = main.rank_theme_results(results, ["Crimson Desert", "Crimson Desert Enhanced"])
        titles = [r["title"] for r in ranked]
        # An 8:20 menu loop is a real track, and more views break the keyword tie.
        self.assertEqual(titles[0], "Crimson Desert - Main Menu Theme")
        self.assertEqual(titles[1], "Crimson Desert - Main Theme - Soundtrack")
        self.assertNotIn("Crimson Desert Main Menu Music (1 Hour) | Deep Focus, Study & Relaxing", titles)

    def test_view_bonus_is_capped(self) -> None:
        names = ["Crimson Desert"]
        theme = main.score_theme_result(
            self._yt("Crimson Desert - Main Theme", 200, 1000, "Someone"), names
        )
        viral_trailer = main.score_theme_result(
            self._yt("Crimson Desert - Gameplay Trailer", 200, 50_000_000, "Someone"), names
        )
        self.assertGreater(theme, viral_trailer)


class SortThemeResultsTest(unittest.TestCase):
    def test_sorts_without_dropping_anything(self) -> None:
        results = [
            _result("Totally unrelated video"),
            _result("Crimson Desert Gameplay Walkthrough Part 1", duration=800),
            _result("Crimson Desert - Main Menu Theme"),
        ]
        ordered = main.sort_theme_results(results, ["Crimson Desert"])
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[0]["title"], "Crimson Desert - Main Menu Theme")
        self.assertEqual(
            {r["title"] for r in ordered}, {r["title"] for r in results}
        )
        self.assertTrue(all("score" in r for r in ordered))

    def test_ties_keep_youtube_order(self) -> None:
        results = [_result("Unrelated A"), _result("Unrelated B"), _result("Unrelated C")]
        ordered = main.sort_theme_results(results, ["Crimson Desert"])
        self.assertEqual([r["title"] for r in ordered], ["Unrelated A", "Unrelated B", "Unrelated C"])


class BuildQueriesTest(unittest.TestCase):
    def test_queries(self) -> None:
        self.assertEqual(
            main.build_theme_queries("Crimson Desert"),
            ["Crimson Desert main theme", "Crimson Desert main menu music", "Crimson Desert OST"],
        )


if __name__ == "__main__":
    unittest.main()
