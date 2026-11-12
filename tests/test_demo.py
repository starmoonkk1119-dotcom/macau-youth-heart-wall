"""Final demo checks, using temporary databases and mocked model responses."""

from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_phase2 import OfflineCase, PROJECT, VALID
import ai
import db
import seed


DISCLAIMER = "本项目为黑客松原型，使用示例数据，不收集真实个人信息，不能替代专业帮助。"


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            db, "DB_PATH", Path(self.temporary.name) / "demo.db"
        )
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.temporary.cleanup()

    def rows(self, table="posts"):
        with db._connection() as connection:
            return connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()

    def test_seven_labelled_posts_categories_intensities_and_statuses(self):
        summary = seed.seed_demo()
        rows = self.rows()
        self.assertEqual(summary["posts_created"], 7)
        self.assertEqual(summary["replies_created"], 2)
        self.assertEqual(len(rows), 7)
        self.assertEqual({row["category"] for row in rows}, {"学业", "家庭", "社交", "情绪"})
        self.assertEqual({row["intensity"] for row in rows}, {1, 2, 3, 5})
        self.assertEqual(sum(row["intensity"] >= 4 for row in rows), 1)
        self.assertEqual(sum(row["status"] == "crisis" for row in rows), 1)
        self.assertEqual(sum(row["status"] == "pending" for row in rows), 2)
        self.assertEqual(len(db.get_approved_posts()), 4)
        for row in rows:
            self.assertTrue(row["content"].startswith("[DEMO 示例 "))
            self.assertIn("非真实个人数据", row["content"])
            self.assertTrue(row["ai_reply"].startswith("[DEMO 预设回应]"))
        for row in self.rows("replies"):
            self.assertIn("DEMO 示例回复", row["content"])
            self.assertIn("非真实个人数据", row["content"])
        self.assertEqual(db.get_review_posts()[0]["intensity"], 5)

    def test_repeated_seed_preserves_ids_review_results_and_reactions(self):
        seed.seed_demo()
        before_ids = [row["id"] for row in self.rows()]
        pending = self.rows()[3]["id"]
        target = self.rows()[-1]["id"]
        db.review_item("post", pending, "approved")
        db.add_reaction(target, "hug")
        summary = seed.seed_demo()
        self.assertEqual(summary["posts_created"], 0)
        self.assertEqual(summary["posts_skipped"], 7)
        self.assertEqual(summary["replies_created"], 0)
        self.assertEqual(summary["replies_skipped"], 2)
        self.assertEqual([row["id"] for row in self.rows()], before_ids)
        self.assertEqual(self.rows()[3]["status"], "approved")
        self.assertEqual(db.get_reaction_counts(target)["hug"], 1)

    def test_reset_only_rebuilds_exact_demo_posts_and_their_children(self):
        seed.seed_demo()
        other_id = db.create_post("不是本脚本生成的记录", True)
        db.review_item("post", other_id, "approved")
        other_reply = db.create_reply(other_id, "保留这条回复")
        db.add_reaction(other_id, "hug")
        target = self.rows()[-2]["id"]
        db.add_reaction(target, "worried")
        result = seed.seed_demo(reset_demo=True)
        self.assertEqual(result["posts_removed"], 7)
        self.assertEqual(result["posts_created"], 7)
        self.assertEqual(len(self.rows()), 8)
        self.assertEqual(len(self.rows("replies")), 3)
        self.assertTrue(any(row["id"] == other_id for row in self.rows()))
        self.assertTrue(any(row["id"] == other_reply for row in self.rows("replies")))
        self.assertEqual(db.get_reaction_counts(other_id)["hug"], 1)
        with db._connection() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(len(self.rows("reactions")), 1)

    def test_concurrent_runs_do_not_duplicate_fixtures(self):
        db.init_db()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: seed.seed_demo(), range(2)))
        self.assertEqual(sorted(row["posts_created"] for row in results), [0, 7])
        self.assertEqual(len(self.rows()), 7)
        self.assertEqual(len(self.rows("replies")), 2)

    def test_invalid_seed_data_does_not_write(self):
        db.init_db()
        invalid = copy.deepcopy(seed.DEMO_POSTS)
        invalid[-1]["category"] = "未知分类"
        with self.assertRaises(ValueError):
            db.seed_demo_posts(invalid)
        self.assertEqual(self.rows(), [])

    def test_seed_failure_rolls_back_all_insertions(self):
        db.init_db()
        with db._connection() as connection:
            connection.executescript("""
                CREATE TRIGGER reject_second_demo BEFORE INSERT ON posts
                WHEN NEW.content LIKE '[DEMO 示例 02%'
                BEGIN SELECT RAISE(ABORT, 'test failure'); END;
            """)
        with self.assertRaises(sqlite3.IntegrityError):
            seed.seed_demo()
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.rows("replies"), [])

    def test_help_command_runs_from_any_directory_without_writing(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT / "seed.py"), "--help"],
            cwd=self.temporary.name,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("--reset-demo", result.stdout)
        self.assertFalse(db.DB_PATH.exists())


class DemoInterfaceTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            db, "DB_PATH", Path(self.temporary.name) / "test.db"
        )
        self.path_patch.start()
        self.admin_env = patch.dict(os.environ, {"ADMIN_PASS": "test-demo-admin"})
        self.admin_env.start()
        seed.seed_demo()

    def tearDown(self):
        self.admin_env.stop()
        self.path_patch.stop()
        self.temporary.cleanup()
        super().tearDown()

    def app(self, page):
        app = AppTest.from_file(str(PROJECT / "app.py")).run()
        if page != "写心声":
            app.radio[0].set_value(page).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_footer_exact_text_once_on_each_page(self):
        for page in ("写心声", "心声墙", "管理员"):
            with self.subTest(page=page):
                app = self.app(page)
                self.assertEqual(
                    [item.value for item in app.caption].count(DISCLAIMER), 1
                )
        self.assertEqual(len(self.requests), 0)

    def test_footer_on_disabled_and_authenticated_admin_page(self):
        with patch.dict(os.environ, {"ADMIN_PASS": ""}):
            app = self.app("管理员")
            self.assertIn(DISCLAIMER, [item.value for item in app.caption])
        app = self.app("管理员")
        app.text_input[0].input("test-demo-admin")
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn(DISCLAIMER, [item.value for item in app.caption])
        self.assertEqual(app.text[0].value, seed.DEMO_POSTS[5]["content"])

    def test_seeded_wall_only_public_fixtures_and_approved_reply(self):
        app = self.app("心声墙")
        contents = [item.value for item in app.text]
        for index in (0, 1, 2, 6):
            self.assertIn(seed.DEMO_POSTS[index]["content"], contents)
        for index in (3, 4, 5):
            self.assertNotIn(seed.DEMO_POSTS[index]["content"], contents)
        self.assertIn(seed.DEMO_POSTS[0]["replies"][0]["content"], contents)
        self.assertNotIn(seed.DEMO_POSTS[3]["replies"][0]["content"], contents)
        self.assertEqual(len(app.text_area), 4)

    def test_demo_order_approval_reply_and_third_worry(self):
        app = self.app("管理员")
        app.text_input[0].input("test-demo-admin")
        app.button[0].click().run()
        app.button(key="approve_post_4").click().run()
        app.button(key="approve_reply_2").click().run()
        app.radio[0].set_value("心声墙").run()
        self.assertIn(
            seed.DEMO_POSTS[3]["replies"][0]["content"],
            [item.value for item in app.text],
        )
        for _ in range(3):
            app.button(key="reaction_7_worried").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn(seed.DEMO_POSTS[6]["content"], [item.value for item in app.text])
        self.assertTrue(any("28525222" in item.value for item in app.error))
        app.radio[0].set_value("管理员").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(db.get_review_posts()), 3)
        self.assertEqual([row["id"] for row in db.get_review_posts()[:2]], [6, 7])

    def test_invalid_unicode_model_reply_falls_back_before_sqlite(self):
        self.content = json.dumps({
            **VALID, "ai_reply": "这不是诊断。愿意陪你说说。\ud800",
        }, ensure_ascii=True)
        result = ai.analyze_post("虚构测试")
        self.assertEqual(result["moderation"], "need_review")
        self.assertEqual(result["ai_reply"], ai.FALLBACK_REPLY)

    def test_invalid_unicode_crisis_keeps_crisis_and_safe_reply(self):
        self.content = json.dumps({
            **VALID,
            "ai_reply": "这不是诊断。愿意陪你说说。\ud800",
            "moderation": "crisis",
        }, ensure_ascii=True)
        result = ai.analyze_post("虚构测试")
        self.assertEqual(result["moderation"], "crisis")
        self.assertEqual(result["ai_reply"], ai.CRISIS_REPLY)
        self.assertEqual(result["intensity"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
