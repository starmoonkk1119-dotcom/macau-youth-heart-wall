"""Phase 1 verification; tests only use temporary SQLite databases."""

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1] / "outputs"
sys.path.insert(0, str(PROJECT))

import db
from streamlit.testing.v1 import AppTest


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "test.db"
        self.path_patch = patch.object(db, "DB_PATH", self.database_path)
        self.path_patch.start()
        db.init_db()

    def tearDown(self):
        self.path_patch.stop()
        self.temporary.cleanup()

    def rows(self):
        with db._connection() as connection:
            return connection.execute("SELECT * FROM posts ORDER BY id").fetchall()


class DatabaseTests(DatabaseTestCase):
    def test_exact_table_columns(self):
        expected = {
            "posts": [
                "id", "content", "category", "intensity", "ai_reply",
                "status", "consent_public", "created_at",
            ],
            "replies": ["id", "post_id", "content", "status", "created_at"],
            "reactions": ["id", "post_id", "type", "created_at"],
        }
        with db._connection() as connection:
            for table, columns in expected.items():
                actual = connection.execute(f"PRAGMA table_info({table})").fetchall()
                self.assertEqual([row["name"] for row in actual], columns)

    def test_post_defaults_and_persistence(self):
        post_id = db.create_post("  今天有点紧张，也想试着说出来。  ", True)
        db.init_db()
        row = self.rows()[0]
        self.assertEqual(row["id"], post_id)
        self.assertEqual(row["content"], "今天有点紧张，也想试着说出来。")
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["consent_public"], 1)
        self.assertTrue(row["created_at"].endswith("Z"))
        for field in ("category", "intensity", "ai_reply"):
            self.assertIsNone(row[field])

    def test_invalid_content_is_not_saved(self):
        for content in ("", " \t\n ", "\u3000", "a" * 3001, None):
            with self.assertRaises(ValueError):
                db.create_post(content, False)
        self.assertEqual(len(self.rows()), 0)

    def test_maximum_length_allowed(self):
        db.create_post("字" * 3000, False)
        self.assertEqual(len(self.rows()[0]["content"]), 3000)

    def test_consent_requires_boolean(self):
        for value in ("false", "true", 0, 1, None):
            with self.assertRaises(ValueError):
                db.create_post("test", value)
        self.assertEqual(len(self.rows()), 0)

    def test_sql_injection_is_literal_content(self):
        text = "'); DROP TABLE posts; -- 澳门 <script>alert(1)</script>"
        db.create_post(text, False)
        self.assertEqual(self.rows()[0]["content"], text)
        self.assertEqual(self.rows()[0]["consent_public"], 0)

    def test_only_approved_and_consented_posts_visible_newest_first(self):
        public_ids = []
        for status in ("pending", "approved", "rejected", "crisis"):
            for consent in (False, True):
                post_id = db.create_post(f"{status} {consent}", consent)
                with db._connection() as connection:
                    connection.execute(
                        "UPDATE posts SET status = ? WHERE id = ?",
                        (status, post_id),
                    )
                if status == "approved" and consent:
                    public_ids.append(post_id)
        second_id = db.create_post("second public post", True)
        with db._connection() as connection:
            connection.execute(
                "UPDATE posts SET status = 'approved' WHERE id = ?", (second_id,)
            )
        self.assertEqual(
            [row["id"] for row in db.get_approved_posts()],
            [second_id, *public_ids],
        )

    def test_status_consent_and_reaction_constraints(self):
        post_id = db.create_post("test", True)
        statements = [
            ("UPDATE posts SET status = ? WHERE id = ?", ("unknown", post_id)),
            ("UPDATE posts SET consent_public = ? WHERE id = ?", (2, post_id)),
            (
                "INSERT INTO reactions(post_id, type) VALUES (?, ?)",
                (post_id, "unknown"),
            ),
        ]
        for sql, values in statements:
            with self.assertRaises(sqlite3.IntegrityError):
                with db._connection() as connection:
                    connection.execute(sql, values)
        self.assertEqual(self.rows()[0]["status"], "pending")
        self.assertEqual(self.rows()[0]["consent_public"], 1)

    def test_foreign_keys_and_valid_reactions(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with db._connection() as connection:
                connection.execute(
                    "INSERT INTO replies(post_id, content) VALUES (999, 'test')"
                )
        post_id = db.create_post("test", False)
        with db._connection() as connection:
            for reaction in ("understand", "hug", "metoo", "worried"):
                connection.execute(
                    "INSERT INTO reactions(post_id, type) VALUES (?, ?)",
                    (post_id, reaction),
                )
            connection.execute(
                "INSERT INTO replies(post_id, content) VALUES (?, 'reply')",
                (post_id,),
            )
            self.assertEqual(
                connection.execute("SELECT status FROM replies").fetchone()[0],
                "pending",
            )
            connection.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            self.assertEqual(
                connection.execute("SELECT count(*) FROM reactions").fetchone()[0], 0
            )
            self.assertEqual(
                connection.execute("SELECT count(*) FROM replies").fetchone()[0], 0
            )


class InterfaceTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.analysis_patch = patch(
            "ai.analyze_post",
            return_value={
                "category": "情绪",
                "intensity": 3,
                "ai_reply": "谢谢你愿意说出自己的感受。",
                "moderation": "need_review",
            },
        )
        self.analysis_patch.start()

    def tearDown(self):
        self.analysis_patch.stop()
        super().tearDown()

    def app(self):
        app = AppTest.from_file(str(PROJECT / "app.py")).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_initial_form_and_empty_wall(self):
        app = self.app()
        self.assertEqual(len(app.text_area), 1)
        self.assertFalse(app.checkbox[0].value)
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("暂时还没有", app.info[0].value)

    def test_empty_submission_preserves_form_without_post(self):
        app = self.app()
        app.text_area[0].input(" \n ")
        app.checkbox[0].check()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertEqual(app.text_area[0].value, " \n ")
        self.assertTrue(app.checkbox[0].value)
        self.assertEqual(len(self.rows()), 0)

    def test_submit_persists_once_and_clears_form(self):
        app = self.app()
        app.text_area[0].input("希望明天轻松一点。")
        app.checkbox[0].check()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.success), 1)
        self.assertIn("心声编号 #1", app.success[0].value)
        self.assertEqual(app.text_area[0].value, "")
        self.assertFalse(app.checkbox[0].value)
        self.assertEqual(self.rows()[0]["consent_public"], 1)
        app.run()
        self.assertEqual(len(self.rows()), 1)
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("暂时还没有", app.info[0].value)

    def test_unchecked_consent_still_saves_pending(self):
        app = self.app()
        app.text_area[0].input("这条心声只想暂时留在这里。")
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.rows()[0]["status"], "pending")
        self.assertEqual(self.rows()[0]["consent_public"], 0)
        self.assertTrue(any("不会展示" in item.value for item in app.caption))

    def test_storage_failure_preserves_input(self):
        app = self.app()
        app.text_area[0].input("保存失败时不要丢掉这段话。")
        with patch.object(db, "create_post", side_effect=sqlite3.OperationalError):
            app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertEqual(app.text_area[0].value, "保存失败时不要丢掉这段话。")
        self.assertEqual(len(self.rows()), 0)

    def test_wall_renders_public_content_as_literal_text(self):
        public_id = db.create_post("<script>literal</script>\n**not bold**", True)
        private_id = db.create_post("PRIVATE CONTENT", False)
        with db._connection() as connection:
            connection.execute(
                "UPDATE posts SET status = 'approved' WHERE id IN (?, ?)",
                (public_id, private_id),
            )
        app = self.app()
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.text), 1)
        self.assertEqual(app.text[0].value, "<script>literal</script>\n**not bold**")
        self.assertTrue(any("澳门时间" in item.value for item in app.caption))


if __name__ == "__main__":
    unittest.main(verbosity=2)
