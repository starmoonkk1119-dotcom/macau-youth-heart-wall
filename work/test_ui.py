"""Presentation regressions with temporary storage and mocked AI only."""

from pathlib import Path
import tempfile
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_phase2 import OfflineCase, PROJECT
import db
import seed


class PresentationTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            db, "DB_PATH", Path(self.temporary.name) / "ui.db"
        )
        self.path_patch.start()
        seed.seed_demo()

    def tearDown(self):
        self.path_patch.stop()
        self.temporary.cleanup()
        super().tearDown()

    def app(self, page="写心声"):
        app = AppTest.from_file(str(PROJECT / "app.py")).run()
        if page != "写心声":
            app.radio[0].set_value(page).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_welcome_placeholder_and_soft_submit(self):
        app = self.app()
        self.assertTrue(any(
            "澳门青少年心声墙" in item.value for item in app.markdown
        ))
        self.assertIn("虚构", app.text_area[0].placeholder)
        self.assertEqual(app.button[0].label, "轻轻放下")
        self.assertFalse(app.checkbox[0].value)
        self.assertEqual(len(self.requests), 0)

    def test_all_four_category_chips_match_stored_values(self):
        post_id = db.create_post("虚构的学业示例", True, category="学业")
        db.review_item("post", post_id, "approved")
        app = self.app("心声墙")
        chips = [
            item.value for item in app.markdown
            if 'class="category-chip ' in item.value
        ]
        for category in ("学业", "家庭", "社交", "情绪"):
            self.assertTrue(any(f">{category}</span>" in chip for chip in chips))
        self.assertEqual(len(chips), len(db.get_approved_posts()))
        self.assertEqual(len(self.requests), 0)

    def test_null_category_has_neutral_label(self):
        post_id = db.create_post("虚构的未分类示例", True)
        db.review_item("post", post_id, "approved")
        app = self.app("心声墙")
        self.assertTrue(any(">未分类</span>" in item.value for item in app.markdown))

    def test_reaction_icons_keep_labels_and_stable_keys(self):
        app = self.app("心声墙")
        for reaction, icon, label in (
            ("understand", "💚", "我懂你"),
            ("hug", "🫂", "抱抱"),
            ("metoo", "🌷", "我也是"),
            ("worried", "🤍", "我有点担心你"),
        ):
            button = app.button(key=f"reaction_7_{reaction}")
            self.assertEqual(button.label, f"{label} · 0")
            self.assertEqual(button.proto.icon, icon)
        self.assertEqual(len(self.requests), 0)

    def test_companion_card_retains_literal_safe_text(self):
        app = self.app()
        app.text_area[0].input("虚构界面测试")
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(any("AI 陪伴回应" in item.value for item in app.caption))
        self.assertTrue(any("这不是诊断" in item.value for item in app.text))
        with db._connection() as connection:
            row = connection.execute(
                "SELECT status FROM posts WHERE content = ?", ("虚构界面测试",)
            ).fetchone()
        self.assertEqual(row["status"], "pending")

    def test_category_html_never_interpolates_untrusted_content(self):
        post_id = db.create_post("<img src=x onerror=alert(1)>", True)
        db.review_item("post", post_id, "approved")
        with db._connection() as connection:
            connection.execute(
                "UPDATE posts SET category = ? WHERE id = ?",
                ('<script>alert("category")</script>', post_id),
            )
        app = self.app("心声墙")
        self.assertIn("<img src=x onerror=alert(1)>", [item.value for item in app.text])
        self.assertFalse(any(
            '<script>alert("category")</script>' in item.value
            for item in app.markdown
        ))
        self.assertTrue(any(">未分类</span>" in item.value for item in app.markdown))
