"""Phase 3 tests: no live API calls; all data lives in temporary databases."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_phase2 import OfflineCase, PROJECT, VALID
import ai
import db


HELP = (
    "如果你现在很难受，请联系澳门明爱生命热线 28525222，"
    "或向信任的大人/学校社工求助。你并不孤单。"
)


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            db, "DB_PATH", Path(self.temporary.name) / "test.db"
        )
        self.path_patch.start()
        db.init_db()

    def tearDown(self):
        self.path_patch.stop()
        self.temporary.cleanup()

    def post(self, content="测试心声", consent=True, intensity=2):
        return db.create_post(
            content, consent, category="情绪", intensity=intensity
        )

    def public_post(self, **kwargs):
        post_id = self.post(**kwargs)
        db.review_item("post", post_id, "approved")
        return post_id

    def row(self, table, item_id):
        with db._connection() as connection:
            return connection.execute(
                f"SELECT * FROM {table} WHERE id = ?", (item_id,)
            ).fetchone()


class DatabaseTests(DatabaseCase):
    def test_high_intensity_escalates_in_post_transaction(self):
        for intensity, expected in ((3, "pending"), (4, "crisis"), (5, "crisis")):
            post_id = self.post(intensity=intensity)
            self.assertEqual(self.row("posts", post_id)["status"], expected)

    def test_third_worry_escalates_and_hides_post(self):
        post_id = self.public_post()
        self.assertFalse(db.add_reaction(post_id, "worried"))
        self.assertFalse(db.add_reaction(post_id, "worried"))
        self.assertTrue(db.add_reaction(post_id, "worried"))
        self.assertEqual(db.get_reaction_counts(post_id)["worried"], 3)
        self.assertEqual(self.row("posts", post_id)["status"], "crisis")
        self.assertEqual(db.get_approved_posts(), [])
        self.assertTrue(db.escalate_crisis_if_needed(post_id))

    def test_three_concurrent_worries_are_atomic(self):
        post_id = self.public_post()
        with ThreadPoolExecutor(max_workers=3) as executor:
            outcomes = list(executor.map(
                lambda _: db.add_reaction(post_id, "worried"), range(3)
            ))
        self.assertEqual(sorted(outcomes), [False, False, True])
        self.assertEqual(db.get_reaction_counts(post_id)["worried"], 3)
        self.assertEqual(self.row("posts", post_id)["status"], "crisis")

    def test_each_reaction_count_and_no_unrelated_escalation(self):
        post_id = self.public_post()
        self.assertEqual(db.get_reaction_counts(post_id), {
            "understand": 0, "hug": 0, "metoo": 0, "worried": 0,
        })
        for reaction in db.REACTION_TYPES:
            self.assertFalse(db.add_reaction(post_id, reaction))
        self.assertTrue(all(value == 1 for value in db.get_reaction_counts(post_id).values()))

    def test_hidden_posts_reject_reactions_and_replies(self):
        for status in ("pending", "crisis", "rejected", "approved"):
            post_id = self.post(consent=status != "approved")
            with db._connection() as connection:
                connection.execute(
                    "UPDATE posts SET status = ? WHERE id = ?", (status, post_id)
                )
            with self.assertRaises(ValueError):
                db.add_reaction(post_id, "hug")
            with self.assertRaises(ValueError):
                db.create_reply(post_id, "reply")
            self.assertEqual(sum(db.get_reaction_counts(post_id).values()), 0)

    def test_bad_reactions_and_missing_posts_do_not_write(self):
        post_id = self.public_post()
        with self.assertRaises(ValueError):
            db.add_reaction(post_id, "invalid")
        with self.assertRaises(ValueError):
            db.add_reaction(999, "hug")
        self.assertEqual(sum(db.get_reaction_counts(post_id).values()), 0)

    def test_all_replies_pending_and_crisis_reply_escalates_parent(self):
        for moderation in ("safe", "need_review", "crisis"):
            post_id = self.public_post()
            reply_id = db.create_reply(post_id, "安慰测试", moderation=moderation)
            self.assertEqual(self.row("replies", reply_id)["status"], "pending")
            self.assertEqual(db.get_approved_replies(post_id), [])
            expected = "crisis" if moderation == "crisis" else "approved"
            self.assertEqual(self.row("posts", post_id)["status"], expected)

    def test_reply_approval_rejection_and_public_parent_gate(self):
        post_id = self.public_post()
        approved = db.create_reply(post_id, "通过的回复")
        rejected = db.create_reply(post_id, "退回的回复")
        pending = db.create_reply(post_id, "等待的回复")
        self.assertTrue(db.review_item("reply", approved, "approved"))
        self.assertTrue(db.review_item("reply", rejected, "rejected"))
        self.assertEqual(
            [row["id"] for row in db.get_approved_replies(post_id)], [approved]
        )
        self.assertEqual([row["id"] for row in db.get_review_replies()], [pending])
        with db._connection() as connection:
            connection.execute(
                "UPDATE posts SET consent_public = 0 WHERE id = ?", (post_id,)
            )
        self.assertEqual(db.get_approved_replies(post_id), [])

    def test_review_is_validated_and_does_not_overwrite_stale_decision(self):
        post_id = self.post()
        self.assertTrue(db.review_item("post", post_id, "approved"))
        self.assertFalse(db.review_item("post", post_id, "rejected"))
        self.assertEqual(self.row("posts", post_id)["status"], "approved")
        for kind, status in (("bad", "approved"), ("post", "crisis"), ("reply", "pending")):
            with self.assertRaises(ValueError):
                db.review_item(kind, post_id, status)

    def test_crisis_first_for_posts_and_associated_replies(self):
        pending = self.post(content="普通待审核")
        crisis = self.post(content="优先心声", intensity=4)
        self.assertEqual(
            [row["id"] for row in db.get_review_posts()], [crisis, pending]
        )
        normal_parent = self.public_post()
        critical_parent = self.public_post()
        normal_reply = db.create_reply(normal_parent, "normal")
        critical_reply = db.create_reply(
            critical_parent, "critical", moderation="crisis"
        )
        self.assertEqual(
            [row["id"] for row in db.get_review_replies()],
            [critical_reply, normal_reply],
        )

    def test_existing_risk_migration_once_and_no_approval_loop(self):
        high = self.post()
        worried = self.public_post()
        rejected = self.post()
        with db._connection() as connection:
            connection.execute("PRAGMA user_version = 0")
            connection.execute(
                "UPDATE posts SET intensity = 4 WHERE id = ?", (high,)
            )
            connection.execute(
                "UPDATE posts SET status = 'rejected', intensity = 5 WHERE id = ?",
                (rejected,),
            )
            for _ in range(3):
                connection.execute(
                    "INSERT INTO reactions(post_id, type) VALUES (?, 'worried')",
                    (worried,),
                )
        db.init_db()
        self.assertEqual(self.row("posts", high)["status"], "crisis")
        self.assertEqual(self.row("posts", worried)["status"], "crisis")
        self.assertEqual(self.row("posts", rejected)["status"], "rejected")
        self.assertTrue(db.review_item("post", high, "approved"))
        self.assertTrue(db.review_item("post", worried, "approved"))
        db.init_db()
        self.assertEqual(self.row("posts", high)["status"], "approved")
        self.assertEqual(self.row("posts", worried)["status"], "approved")
        self.assertFalse(db.escalate_crisis_if_needed(rejected))
        self.assertEqual(self.row("posts", rejected)["status"], "rejected")

    def test_private_approved_post_still_hidden(self):
        post_id = self.post(consent=False)
        self.assertTrue(db.review_item("post", post_id, "approved"))
        self.assertEqual(self.row("posts", post_id)["status"], "approved")
        self.assertEqual(db.get_approved_posts(), [])


class InterfaceTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            db, "DB_PATH", Path(self.temporary.name) / "test.db"
        )
        self.path_patch.start()
        self.admin_env = patch.dict(os.environ, {"ADMIN_PASS": "test-admin-password"})
        self.admin_env.start()
        db.init_db()

    def tearDown(self):
        self.admin_env.stop()
        self.path_patch.stop()
        self.temporary.cleanup()
        super().tearDown()

    def post(self, content="测试心声", consent=True, intensity=2):
        return db.create_post(content, consent, intensity=intensity)

    def row(self, table, item_id):
        with db._connection() as connection:
            return connection.execute(
                f"SELECT * FROM {table} WHERE id = ?", (item_id,)
            ).fetchone()

    def public_post(self, **kwargs):
        post_id = self.post(**kwargs)
        db.review_item("post", post_id, "approved")
        return post_id

    def app(self, page="写心声"):
        app = AppTest.from_file(str(PROJECT / "app.py")).run()
        if page != "写心声":
            app.radio[0].set_value(page).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def login(self, app=None, password="test-admin-password"):
        app = app or self.app("管理员")
        app.text_input[0].input(password)
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_missing_admin_password_fails_closed(self):
        self.post(content="PRIVATE")
        with patch.dict(os.environ, {"ADMIN_PASS": ""}):
            with patch.object(db, "get_review_posts", side_effect=AssertionError):
                app = self.app("管理员")
        self.assertEqual(len(app.text), 0)
        self.assertEqual(len(app.text_input), 0)
        self.assertIn("入口已关闭", app.warning[0].value)

    def test_logged_out_or_wrong_password_never_reads_queue(self):
        self.post(content="PRIVATE")
        with patch.object(db, "get_review_posts", side_effect=AssertionError):
            app = self.app("管理员")
            app = self.login(app, "wrong")
        self.assertEqual(len(app.error), 1)
        self.assertEqual(len(app.text), 0)
        self.assertEqual(app.text_input[0].value, "")
        self.assertNotIn("_admin_token", app.session_state)

    def test_login_shows_crisis_first_in_red_and_clears_password(self):
        self.post(content="NORMAL")
        self.post(content="CRITICAL", intensity=4)
        app = self.login()
        self.assertEqual(app.text[0].value, "CRITICAL")
        self.assertEqual(app.error[0].value, "危机 · 优先安全关注")
        self.assertTrue(any(item.value == HELP for item in app.error))
        self.assertNotIn("admin_password", app.session_state)
        self.assertEqual(len(app.text_input), 0)

    def test_password_rotation_and_logout_hide_queue(self):
        self.post(content="PRIVATE")
        app = self.login()
        with patch.dict(os.environ, {"ADMIN_PASS": "rotated"}):
            app.run()
            self.assertEqual(len(app.text), 0)
            self.assertEqual(len(app.text_input), 1)
        app = self.login(app)
        app.button(key="logout_admin").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.text), 0)
        self.assertNotIn("_admin_token", app.session_state)

    def test_login_is_session_local_and_supports_unicode_password(self):
        self.post(content="PRIVATE")
        first = self.login()
        second = self.app("管理员")
        self.assertTrue(first.text)
        self.assertFalse(second.text)
        with patch.dict(os.environ, {"ADMIN_PASS": "中文密码-test"}):
            second = self.login(second, "中文密码-test")
            self.assertTrue(second.text)

    def test_admin_post_approval_and_rejection(self):
        approved = self.post(content="TO APPROVE")
        rejected = self.post(content="TO REJECT", intensity=4)
        app = self.login()
        app.button(key=f"approve_post_{approved}").click().run()
        app.button(key=f"reject_post_{rejected}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.row("posts", approved)["status"], "approved")
        self.assertEqual(self.row("posts", rejected)["status"], "rejected")
        app.radio[0].set_value("心声墙").run()
        self.assertEqual([item.value for item in app.text], ["TO APPROVE"])

    def test_admin_private_approval_does_not_publish(self):
        post_id = self.post(consent=False)
        app = self.login()
        app.button(key=f"approve_post_{post_id}").click().run()
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(db.get_approved_posts(), [])
        self.assertEqual(len(app.text), 0)

    def test_reaction_counts_and_third_worry_resource_notice(self):
        post_id = self.public_post()
        app = self.app("心声墙")
        self.assertEqual(app.button(key=f"reaction_{post_id}_hug").label, "抱抱 · 0")
        app.button(key=f"reaction_{post_id}_hug").click().run()
        self.assertEqual(app.button(key=f"reaction_{post_id}_hug").label, "抱抱 · 1")
        for _ in range(3):
            app.button(key=f"reaction_{post_id}_worried").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.row("posts", post_id)["status"], "crisis")
        self.assertTrue(any(item.value == HELP for item in app.error))
        self.assertEqual(len(app.text), 0)
        self.assertEqual(len(self.requests), 0)

    def test_post_success_high_intensity_has_exact_help_box(self):
        import json
        self.content = json.dumps({**VALID, "intensity": 4})
        app = self.app()
        app.text_area[0].input("高强度测试")
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.row("posts", 1)["status"], "crisis")
        self.assertTrue(any(item.value == HELP for item in app.error))
        self.assertEqual(len(self.requests), 1)

    def test_reply_uses_ai_once_then_approval_makes_it_visible(self):
        post_id = self.public_post()
        app = self.app("心声墙")
        app.text_area[0].input("愿意陪你听你说说。")
        app.button(key=f"FormSubmitter:reply_form_{post_id}-提交回复").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.row("replies", 1)["status"], "pending")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(app.text_area[0].value, "")
        self.assertNotIn("愿意陪你听你说说。", [item.value for item in app.text])
        app.radio[0].set_value("管理员").run()
        app = self.login(app)
        app.button(key="approve_reply_1").click().run()
        app.radio[0].set_value("心声墙").run()
        self.assertIn("愿意陪你听你说说。", [item.value for item in app.text])
        self.assertEqual(len(self.requests), 1)

    def test_reply_rejection_stays_hidden(self):
        post_id = self.public_post()
        reply_id = db.create_reply(post_id, "REJECT ME")
        app = self.login()
        app.button(key=f"reject_reply_{reply_id}").click().run()
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(self.row("replies", reply_id)["status"], "rejected")
        self.assertNotIn("REJECT ME", [item.value for item in app.text])

    def test_crisis_reply_pending_but_parent_escalates(self):
        import json
        self.content = json.dumps({**VALID, "moderation": "crisis"})
        post_id = self.public_post()
        app = self.app("心声墙")
        app.text_area[0].input("危机回复测试")
        app.button(key=f"FormSubmitter:reply_form_{post_id}-提交回复").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.row("replies", 1)["status"], "pending")
        self.assertEqual(self.row("posts", post_id)["status"], "crisis")
        self.assertTrue(any(item.value == HELP for item in app.error))

    def test_reply_api_failure_stays_pending_without_crash(self):
        self.status_code = 503
        post_id = self.public_post()
        app = self.app("心声墙")
        app.text_area[0].input("回复失败兜底测试")
        app.button(key=f"FormSubmitter:reply_form_{post_id}-提交回复").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.row("replies", 1)["status"], "pending")
        self.assertEqual(len(self.requests), 1)

    def test_empty_reply_has_no_ai_request(self):
        post_id = self.public_post()
        app = self.app("心声墙")
        app.text_area[0].input("\u200b\u0336")
        app.button(key=f"FormSubmitter:reply_form_{post_id}-提交回复").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(self.requests), 0)
        self.assertEqual(len(app.error), 1)

    def test_stale_wall_cannot_write_after_parent_withdrawn(self):
        post_id = self.public_post()
        app = self.app("心声墙")
        with db._connection() as connection:
            connection.execute(
                "UPDATE posts SET status = 'crisis' WHERE id = ?", (post_id,)
            )
        app.button(key=f"reaction_{post_id}_hug").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(sum(db.get_reaction_counts(post_id).values()), 0)

    def test_high_post_manually_approved_stays_visible_with_resources(self):
        post_id = self.post(intensity=4)
        app = self.login()
        app.button(key=f"approve_post_{post_id}").click().run()
        self.assertEqual(self.row("posts", post_id)["status"], "approved")
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.text)
        self.assertTrue(any(item.value == HELP for item in app.error))
        self.assertEqual(self.row("posts", post_id)["status"], "approved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
