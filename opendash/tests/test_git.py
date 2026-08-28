"""Level 3: worktrees, against a real git repository in a temp directory."""
from __future__ import annotations

import unittest
from pathlib import Path

from support import SandboxCase, have, run


@unittest.skipUnless(have("git"), "git is not installed")
class Worktrees(SandboxCase):
    def setUp(self):
        super().setUp()
        self.repo = (self.box.dir / "codes").resolve()
        self.box.dir = self.box.dir.resolve()
        self.repo.mkdir()
        for args in (("init", "-q", "-b", "main", "."),
                     ("config", "user.email", "t@t"),
                     ("config", "user.name", "t")):
            run("git", "-C", str(self.repo), *args)
        (self.repo / "a.py").write_text("x = 1\n")
        run("git", "-C", str(self.repo), "add", "-A")
        run("git", "-C", str(self.repo), "commit", "-qm", "init")

    def branches(self) -> list[str]:
        out = run("git", "-C", str(self.repo), "branch", "--format=%(refname:short)")
        return out.stdout.split()

    # -- creating ------------------------------------------------------------

    def test_the_directory_is_project_dash_branch_beside_the_repo(self):
        tree, branch, repo = self.ocore.create_worktree(self.repo, "TIX-001-fix-tests")
        self.assertEqual(Path(tree).name, "codes-TIX-001-fix-tests")
        self.assertEqual(Path(tree).resolve().parent, self.repo.parent)
        self.assertEqual(branch, "TIX-001-fix-tests")
        self.assertEqual(Path(repo).resolve(), self.repo)
        self.assertTrue(Path(tree, "a.py").exists())
        self.assertIn("TIX-001-fix-tests", self.branches())

    def test_an_existing_branch_is_checked_out_rather_than_refused(self):
        run("git", "-C", str(self.repo), "branch", "already-here")
        run("git", "-C", str(self.repo), "commit", "-q", "--allow-empty", "-m", "x")
        tree, _, _ = self.ocore.create_worktree(self.repo, "already-here")
        head = run("git", "-C", tree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.assertEqual(head, "already-here")

    def test_asking_twice_returns_the_same_worktree(self):
        first, _, _ = self.ocore.create_worktree(self.repo, "same")
        second, _, _ = self.ocore.create_worktree(self.repo, "same")
        self.assertEqual(first, second)

    def test_a_bad_branch_name_is_refused_before_anything_is_created(self):
        with self.assertRaises(self.ocore.ApiError):
            self.ocore.create_worktree(self.repo, "bad name with spaces")
        self.assertFalse((self.repo.parent / "codes-bad name with spaces").exists())

    def test_a_directory_that_is_not_a_repository_is_refused(self):
        plain = self.box.dir / "plain"
        plain.mkdir()
        with self.assertRaises(self.ocore.ApiError):
            self.ocore.create_worktree(plain, "x")

    def test_naming_is_based_on_the_main_repo_even_from_inside_a_worktree(self):
        tree, _, _ = self.ocore.create_worktree(self.repo, "first")
        nested, _, repo = self.ocore.create_worktree(tree, "second")
        self.assertEqual(Path(nested).name, "codes-second")
        self.assertEqual(Path(repo).resolve(), self.repo)

    # -- removing ------------------------------------------------------------

    def test_removing_takes_the_worktree_and_leaves_the_branch(self):
        tree, branch, repo = self.ocore.create_worktree(self.repo, "keep-me")
        self.ocore.remove_worktree({"worktree": tree, "repo": repo})
        self.assertFalse(Path(tree).exists())
        self.assertIn("keep-me", self.branches())

    def test_committed_work_survives_removal(self):
        tree, branch, repo = self.ocore.create_worktree(self.repo, "with-work")
        (Path(tree) / "PROOF.txt").write_text("worktree\n")
        run("git", "-C", tree, "add", "-A")
        run("git", "-C", tree, "commit", "-qm", "agent work")
        self.ocore.remove_worktree({"worktree": tree, "repo": repo})
        log = run("git", "-C", str(self.repo), "log", "--oneline", "-1", "with-work")
        self.assertIn("agent work", log.stdout)

    def test_uncommitted_changes_stop_the_removal(self):
        tree, _, repo = self.ocore.create_worktree(self.repo, "dirty")
        (Path(tree) / "scratch.txt").write_text("unsaved\n")
        record = {"worktree": tree, "repo": repo}
        self.assertTrue(self.ocore.worktree_dirty(record))
        with self.assertRaises(self.ocore.ApiError):
            self.ocore.remove_worktree(record)
        self.assertTrue(Path(tree).exists())

    def test_force_discards_them(self):
        tree, _, repo = self.ocore.create_worktree(self.repo, "dirty2")
        (Path(tree) / "scratch.txt").write_text("unsaved\n")
        self.ocore.remove_worktree({"worktree": tree, "repo": repo}, force=True)
        self.assertFalse(Path(tree).exists())
        self.assertIn("dirty2", self.branches())

    def test_a_clean_worktree_is_not_dirty(self):
        tree, _, repo = self.ocore.create_worktree(self.repo, "clean")
        self.assertFalse(self.ocore.worktree_dirty({"worktree": tree, "repo": repo}))

    def test_an_instance_without_a_worktree_removes_nothing(self):
        self.ocore.remove_worktree({"worktree": None})      # must not raise

    def test_a_worktree_deleted_by_hand_is_just_pruned(self):
        tree, _, repo = self.ocore.create_worktree(self.repo, "vanished")
        run("rm", "-rf", tree)
        self.ocore.remove_worktree({"worktree": tree, "repo": repo})
        listing = run("git", "-C", str(self.repo), "worktree", "list").stdout
        self.assertNotIn("vanished", listing)


if __name__ == "__main__":
    unittest.main()
