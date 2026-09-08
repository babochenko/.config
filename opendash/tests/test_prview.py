"""Level 4: the pure PR presentation helpers in prview.py.

These were extracted from dashboard.py precisely so they can be pinned
down without curses. Every test builds normalised PRs through
metadata._normalise_pr, the same shape the dashboard really renders.
"""
from __future__ import annotations

import time
import unittest

from support import ROOT  # noqa: F401  (ROOT puts opendash on sys.path)

import metadata
import prview


def pr(number, repository="revolut/parrot", **fields) -> dict:
    """A normalised PR, the exact shape metadata hands the view layer."""
    fields.setdefault("status", "opened")
    return metadata._normalise_pr(fields,
                                 {"repository": repository, "number": str(number)})


class TextUtils(unittest.TestCase):
    def test_clip_truncates_with_ellipsis(self):
        self.assertEqual(prview.clip("abcdef", 4), "abc…")
        self.assertEqual(prview.clip("abcdef", 10), "abcdef")

    def test_wide_characters_count_double(self):
        self.assertEqual(prview._w("あ"), 2)
        self.assertEqual(prview._tw("aあ"), 3)

    def test_variation_selectors_are_zero_width(self):
        self.assertEqual(prview._w("\ufe0e"), 0)
        self.assertEqual(prview._w("\ufe0f"), 0)


class PrLabel(unittest.TestCase):
    def test_label_basics(self):
        label = prview._pr_label(pr(12, approvals=2,
                                    unresolved_comments=[{"author": "A", "text": "t"},
                                                         {"author": "B", "text": "t"},
                                                         {"author": "C", "text": "t"}],
                                    unresolved_threads=3,
                                    builds={"ok": 4, "failed": 1}))
        self.assertEqual(label, "#12 ✓2 ⊟3 ⚙4✓/1✗")

    def test_merged_pr_is_just_the_number(self):
        self.assertEqual(prview._pr_label(pr(5, status="merged")), "✓#5")

    def test_all_green_builds_show_a_bare_gear(self):
        self.assertEqual(prview._pr_label(pr(7, builds={"ok": 5})), "#7 ⚙")

    def test_in_progress_builds_are_counted(self):
        label = prview._pr_label(pr(7, builds={"ok": 3, "in_progress": 2}))
        self.assertEqual(label, "#7 ⚙3✓/2◔")

    def test_all_in_progress_builds_still_show(self):
        self.assertEqual(prview._pr_label(pr(7, builds={"in_progress": 4})),
                         "#7 ⚙4◔")

    def test_loader_shows_a_spinner_without_stats(self):
        self.assertIn("⠋", prview._pr_label({"number": 12}, True, 0))


class RowColorsAndOrder(unittest.TestCase):
    def test_merged_is_green(self):
        self.assertEqual(prview._pr_row_pair(pr(1, status="merged")), prview.C_OK)

    def test_only_approvals_failing_is_ready_for_review(self):
        p = pr(1, merge_checks=[{"check": "2+ approvals", "passed": False},
                                {"check": "no failed builds", "passed": True}])
        self.assertEqual(prview._pr_row_pair(p), prview.C_WORK)

    def test_other_failures_block_the_ready_color(self):
        p = pr(1, merge_checks=[{"check": "2+ approvals", "passed": False},
                                {"check": "no failed builds", "passed": False}])
        self.assertEqual(prview._pr_row_pair(p), prview.C_TICKET)

    def test_prs_sort_blue_then_ready_then_merged(self):
        blue = pr(1424, merge_checks=[{"check": "no failed builds", "passed": False}])
        ready = pr(1419, merge_checks=[{"check": "2+ approvals", "passed": False}])
        merged = pr(2579, status="merged")
        ranked = [p["number"] for p in sorted([merged, ready, blue], key=prview._pr_rank)]
        self.assertEqual(ranked, ["1424", "1419", "2579"])


class GroupedLabels(unittest.TestCase):
    def test_prs_group_by_repo(self):
        groups = prview._grouped_pr_labels(
            [pr(1, "revolut/parrot"), pr(2, "revolut/parrot"), pr(3, "revolut/nest")])
        self.assertEqual(["".join(t for t, _ in g) for g in groups],
                         ["parrot(#1 #2)", "nest#3"])

    def test_long_repo_names_are_clipped(self):
        name = "%7Bd8405c1f-c933-443f-bd50-d74d8f098f16%7D"
        groups = prview._grouped_pr_labels([pr(1, f"revolut/{name}")])
        self.assertTrue(groups[0][0][0].endswith("…"))
        self.assertLessEqual(prview._tw(groups[0][0][0]), 16)

    def test_group_segments_carry_per_pr_colors(self):
        groups = prview._grouped_pr_labels(
            [pr(2, "revolut/parrot", merge_checks=[{"check": "2+ approvals", "passed": False}]),
             pr(1, "revolut/parrot", status="merged")])
        pairs = [p for _, p in groups[0]]
        # repo name white, ready PR yellow, merged PR green, parens white
        self.assertEqual(pairs, [prview.C_SEL, prview.C_WORK, prview.C_SEL,
                                 prview.C_OK, prview.C_SEL])


class OverlaySegments(unittest.TestCase):
    def test_merged_pr_stops_after_the_header(self):
        lines = prview._pr_overlay_segments(
            pr(1, status="merged", builds={"ok": 2}, unresolved_threads=5,
               unresolved_comments=[{"author": "A", "text": "x"}]))
        self.assertEqual(len(lines), 2)   # header + url, nothing else

    def test_checks_collapse_to_roundups(self):
        p = pr(1, merge_checks=[{"check": "2+ approvals", "passed": False},
                                {"check": "all tasks resolved", "passed": True}])
        lines = prview._pr_overlay_segments(p)
        joined = ["".join(t for t, _, _, _ in ln) for ln in lines]
        self.assertTrue(any("1 check failed — 2+ approvals" in l for l in joined))
        self.assertTrue(any("1 check passed — all tasks resolved" in l for l in joined))

    def test_comments_render_dim_and_clipped(self):
        p = pr(1, unresolved_comments=[
            {"author": "Clarity - AI Code Reviewer", "created": "2026-09-01 19:07",
             "text": "Major: " + "x" * 200}])
        lines = prview._pr_overlay_segments(p)
        comment = "".join(t for t, _, _, _ in lines[-1])
        self.assertIn("Clarity - AI Code Reviewer", comment)
        self.assertTrue(comment.endswith("…"))
        self.assertTrue(all(pair == prview.C_DIM for _, pair, _, _ in lines[-1]))


class Staleness(unittest.TestCase):
    def test_fresh_prs_have_no_badge(self):
        self.assertIsNone(prview._pr_stale_age([pr(1)]))

    def test_stale_prs_show_an_age(self):
        old = pr(1)
        old["fetched"] = time.time() - 45 * 60
        self.assertIsNotNone(prview._pr_stale_age([pr(2), old]))

    def test_errored_fetches_do_not_count_as_fresh(self):
        old = pr(1)
        old["fetched"] = time.time() - 45 * 60
        error = pr(2)
        error["fetched"] = time.time() - 45 * 60
        error["error"] = "timeout"
        self.assertIsNone(prview._pr_stale_age([error]))
        self.assertIsNotNone(prview._pr_stale_age([old, error]))


if __name__ == "__main__":
    unittest.main()