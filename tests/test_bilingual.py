"""Bilingual regression checks with temporary SQLite and mocked provider HTTP."""

import json
import os
from pathlib import Path
from string import Formatter
import tempfile
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_phase2 import OfflineCase, PROJECT, VALID, ai, db
import app as ui


ENGLISH = {
    **VALID,
    "ai_reply": (
        "This is not a diagnosis, just a little support. "
        "It sounds like things have felt heavy lately. "
        "A trusted adult could help you talk it through."
    ),
}


class BilingualAITests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.content = json.dumps(ENGLISH)

    def test_english_response_single_request_and_fixed_enums(self):
        result = ai.analyze_post("ＡＢＣ\u200b 今天有点累", language="en")
        self.assertEqual(result, ENGLISH)
        self.assertEqual(len(self.requests), 1)
        payload = json.loads(self.requests[0].content)
        self.assertEqual(payload["model"], "deepseek-chat")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        system = payload["messages"][0]["content"]
        self.assertIn("ai_reply must be in warm, natural English", system)
        self.assertIn("凡语义涉及自伤、自杀、伤害他人，一律判 crisis", system)
        self.assertIn("学业、家庭、社交、情绪", system)
        self.assertEqual(
            json.loads(payload["messages"][1]["content"])["normalized_text"],
            "ABC 今天有点累",
        )

    def test_default_and_unknown_language_keep_chinese(self):
        self.content = json.dumps(VALID)
        self.assertEqual(ai.analyze_post("虚构测试"), VALID)
        self.assertEqual(ai.analyze_post("虚构测试", language="fr"), VALID)

    def test_english_invalid_json_fails_closed(self):
        for content in ("not json", "[]", "{}", '{"intensity":NaN}',
                        '{"moderation":"crisis","moderation":"safe"}'):
            with self.subTest(content=content):
                self.content = content
                result = ai.analyze_post("Fictional example", language="en")
                self.assertEqual(result["moderation"], "need_review")
                self.assertEqual(result["category"], "情绪")
                self.assertEqual(result["intensity"], 3)
                self.assertEqual(result["ai_reply"], ai.REPLY_TEXT["en"]["fallback"])

    def test_english_http_error_fails_closed_once(self):
        self.status_code = 503
        result = ai.analyze_post("Fictional example", language="en")
        self.assertEqual(result["moderation"], "need_review")
        self.assertEqual(result["ai_reply"], ai.REPLY_TEXT["en"]["fallback"])
        self.assertEqual(len(self.requests), 1)

    def test_english_missing_key_fails_closed_without_request(self):
        with patch.dict(os.environ, {}, clear=True):
            result = ai.analyze_post("Fictional example", language="en")
        self.assertEqual(result["moderation"], "need_review")
        self.assertEqual(result["ai_reply"], ai.REPLY_TEXT["en"]["fallback"])
        self.assertEqual(len(self.requests), 0)

    def test_english_mode_pinyin_and_flower_text_still_reviewed(self):
        for content in ("紫砂", "自\u200b殺", "ｚｉ ｓｈａ", "𝕫𝕚𝕤𝕙𝕒", "z\u0301i\u0308sha"):
            with self.subTest(content=content):
                result = ai.analyze_post(content, language="en")
                self.assertEqual(result["moderation"], "need_review")
                self.assertEqual(result["ai_reply"], ENGLISH["ai_reply"])

    def test_english_crisis_preserved_with_bad_other_fields(self):
        for updates in ({"intensity": "5"}, {"ai_reply": None},
                        {"ai_reply": "\ud800"}, {"category": "Feelings"}, {"extra": 1}):
            with self.subTest(updates=updates):
                self.content = json.dumps({**ENGLISH, "moderation": "crisis", **updates})
                result = ai.analyze_post("Fictional crisis example", language="en")
                self.assertEqual(result["moderation"], "crisis")
                self.assertEqual(result["intensity"], 5)
                self.assertEqual(result["ai_reply"], ai.REPLY_TEXT["en"]["crisis"])

    def test_english_truncated_parsed_crisis_not_downgraded(self):
        self.content = json.dumps({**ENGLISH, "moderation": "crisis"})
        self.finish_reason = "length"
        result = ai.analyze_post("Fictional crisis example", language="en")
        self.assertEqual(result["moderation"], "crisis")
        self.assertEqual(result["ai_reply"], ai.REPLY_TEXT["en"]["crisis"])

    def test_english_schema_and_reply_validation_remain_strict(self):
        for updates in ({"category": "School"}, {"moderation": "approved"},
                        {"intensity": True}, {"ai_reply": "Only one sentence."},
                        {"ai_reply": "You matter. Reach out to an adult."}):
            with self.subTest(updates=updates):
                self.content = json.dumps({**ENGLISH, **updates})
                self.assertEqual(
                    ai.analyze_post("Fictional example", language="en")["moderation"],
                    "need_review",
                )


class BilingualUITests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(db, "DB_PATH", Path(self.temporary.name) / "test.db")
        self.path_patch.start()
        self.admin_patch = patch.dict(os.environ, {"ADMIN_PASS": "offline-test-password"})
        self.admin_patch.start()
        self.content = json.dumps(ENGLISH)

    def tearDown(self):
        self.admin_patch.stop()
        self.path_patch.stop()
        self.temporary.cleanup()
        super().tearDown()

    def start(self, language="en"):
        app = AppTest.from_file(str(PROJECT / "app.py")).run()
        if language == "en":
            app.selectbox(key="language").select("en").run()
        self.assertFalse(app.exception)
        return app

    def posts(self):
        with db._connection() as connection:
            return connection.execute("SELECT * FROM posts ORDER BY id").fetchall()

    def public_post(self):
        db.init_db()
        post_id = db.create_post("[DEMO] 虚构心声，不翻译。", True, category="学业", intensity=2)
        db.review_item("post", post_id, "approved")
        return post_id

    def submit(self, app, text="[DEMO] A fictional feeling.", consent=True):
        app.text_area(key="draft_content").input(text)
        app.checkbox(key="consent_public").set_value(consent)
        app.button(key="submit_post").click().run()
        self.assertFalse(app.exception)

    def login(self, app):
        app.radio(key="navigation").set_value("管理员").run()
        app.text_input(key="admin_password").input("offline-test-password")
        app.button(key="admin_login_submit").click().run()
        self.assertFalse(app.exception)

    def test_text_key_and_placeholder_parity(self):
        self.assertEqual(set(ui.TEXT["zh"]), set(ui.TEXT["en"]))
        formatter = Formatter()
        for key in ui.TEXT["zh"]:
            with self.subTest(key=key):
                self.assertTrue(ui.TEXT["en"][key].strip())
                fields = [
                    {name for _, name, _, _ in formatter.parse(ui.TEXT[lang][key])
                     if name is not None}
                    for lang in ("zh", "en")
                ]
                self.assertEqual(*fields)
        for lang in ("zh", "en"):
            self.assertIn("28525222", ui.TEXT[lang]["help_resources"])

    def test_default_language_and_english_static_ui(self):
        app = self.start("zh")
        self.assertEqual(app.session_state["language"], "zh")
        self.assertEqual(app.selectbox[0].options, ["中文", "English"])
        app.selectbox(key="language").select("en").run()
        self.assertEqual(app.session_state["language"], "en")
        self.assertEqual(app.subheader[0].value, ui.TEXT["en"]["write_page"])
        self.assertEqual(app.text_area[0].placeholder, ui.TEXT["en"]["post_placeholder"])
        self.assertEqual(app.button(key="submit_post").label, ui.TEXT["en"]["submit_post"])
        self.assertEqual(
            app.radio[0].options, ["Share a feeling", "Heart wall", "Admin"]
        )
        self.assertIn(ui.TEXT["en"]["disclaimer"], [item.value for item in app.caption])
        self.assertTrue(any(ui.TEXT["en"]["brand"] in item.value for item in app.markdown))

    def test_language_is_session_local_and_persists(self):
        app = self.start()
        app.run()
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(app.session_state["language"], "en")
        another = self.start("zh")
        self.assertEqual(another.session_state["language"], "zh")
        self.assertEqual(app.session_state["language"], "en")

    def test_page_preserved_on_language_switch_without_writes_or_api(self):
        app = self.start()
        app.radio[0].set_value("心声墙").run()
        app.selectbox[0].select("zh").run()
        self.assertEqual(app.radio[0].value, "心声墙")
        self.assertEqual(app.subheader[0].value, ui.TEXT["zh"]["wall_page"])
        app.selectbox[0].select("en").run()
        self.assertEqual(app.subheader[0].value, ui.TEXT["en"]["wall_page"])
        self.assertEqual(len(self.posts()), 0)
        self.assertEqual(len(self.requests), 0)

    def test_saved_draft_and_consent_preserved_during_switch(self):
        app = self.start("zh")
        # Seed already committed widget state; unrelated reruns don't submit a form.
        app.session_state["draft_content"] = "[DEMO] 保留原文"
        app.session_state["consent_public"] = True
        app.run()
        app.selectbox[0].select("en").run()
        self.assertEqual(app.text_area[0].value, "[DEMO] 保留原文")
        self.assertTrue(app.checkbox[0].value)
        self.assertEqual(len(self.requests), 0)
        self.assertEqual(len(self.posts()), 0)

    def test_safe_post_pending_english_reply_original_body_and_category(self):
        app = self.start()
        body = "[DEMO] 今天ＡＢＣ\u200b让我紧张。"
        self.submit(app, body)
        post = self.posts()[0]
        self.assertEqual(post["content"], body)
        self.assertEqual(post["category"], "学业")
        self.assertEqual(post["status"], "pending")
        self.assertEqual(post["ai_reply"], ENGLISH["ai_reply"])
        self.assertEqual(app.text[0].value, ENGLISH["ai_reply"])
        self.assertEqual(len(self.requests), 1)
        app.selectbox[0].select("zh").run()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.posts()[0]["ai_reply"], ENGLISH["ai_reply"])

    def test_english_mode_crisis_posts_in_both_input_languages(self):
        self.content = json.dumps({**ENGLISH, "moderation": "crisis", "intensity": 5})
        for body in ("[DEMO] 虚构：我想伤害自己。", "[DEMO] Fictional: I want to hurt myself."):
            with self.subTest(body=body):
                app = self.start()
                self.submit(app, body)
                self.assertEqual(self.posts()[-1]["status"], "crisis")
                self.assertEqual(self.posts()[-1]["content"], body)
                self.assertEqual(app.warning[0].value, ui.TEXT["en"]["crisis_notice"])
                self.assertIn(ui.TEXT["en"]["help_resources"], [e.value for e in app.error])
        self.assertEqual(len(self.requests), 2)

    def test_english_high_intensity_still_crisis(self):
        self.content = json.dumps({**ENGLISH, "intensity": 4})
        app = self.start()
        self.submit(app)
        self.assertEqual(self.posts()[0]["status"], "crisis")
        self.assertTrue(app.warning)

    def test_invalid_json_english_post_pending_with_fallback(self):
        self.content = "not json"
        app = self.start()
        self.submit(app)
        self.assertEqual(self.posts()[0]["status"], "pending")
        self.assertEqual(app.text[0].value, ai.REPLY_TEXT["en"]["fallback"])

    def test_admin_private_approval_hidden_and_language_session_preserved(self):
        app = self.start()
        self.submit(app, consent=False)
        self.login(app)
        post_id = self.posts()[0]["id"]
        app.selectbox[0].select("zh").run()
        self.assertTrue(app.button(key="approve_post_" + str(post_id)))
        app.selectbox[0].select("en").run()
        app.button(key="approve_post_" + str(post_id)).click().run()
        self.assertEqual(self.posts()[0]["status"], "approved")
        self.assertEqual(len(db.get_approved_posts()), 0)
        app.button(key="logout_admin").click().run()
        self.assertEqual(app.button(key="admin_login_submit").label, "Sign in")

    def test_english_category_and_original_public_content(self):
        self.public_post()
        app = self.start()
        app.radio[0].set_value("心声墙").run()
        self.assertTrue(any(">School<" in m.value for m in app.markdown))
        self.assertIn("[DEMO] 虚构心声，不翻译。", [t.value for t in app.text])
        self.assertEqual(app.text_area[0].placeholder, ui.TEXT["en"]["reply_placeholder"])

    def test_english_reply_pending_until_admin_approval(self):
        post_id = self.public_post()
        app = self.start()
        app.radio[0].set_value("心声墙").run()
        body = "[DEMO] 我愿意听听你说。"
        app.text_area(key=f"reply_draft_{post_id}").input(body)
        app.button(key=f"FormSubmitter:reply_form_{post_id}-提交回复").click().run()
        self.assertFalse(app.exception)
        replies = db.get_review_replies()
        self.assertEqual(replies[0]["content"], body)
        self.assertEqual(replies[0]["status"], "pending")
        self.assertEqual(len(db.get_approved_replies(post_id)), 0)
        self.assertIn("ai_reply must be in warm, natural English",
                      json.loads(self.requests[0].content)["messages"][0]["content"])
        self.login(app)
        app.button(key=f"approve_reply_{replies[0]['id']}").click().run()
        self.assertEqual(db.get_approved_replies(post_id)[0]["content"], body)

    def test_english_crisis_reply_still_escalates_parent(self):
        post_id = self.public_post()
        self.content = json.dumps({**ENGLISH, "moderation": "crisis", "intensity": 5})
        app = self.start()
        app.radio[0].set_value("心声墙").run()
        app.text_area[0].input("[DEMO] Fictional crisis reply.")
        app.button(key=f"FormSubmitter:reply_form_{post_id}-提交回复").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.posts()[0]["status"], "crisis")
        self.assertEqual(db.get_review_replies()[0]["status"], "pending")
        self.assertIn(ui.TEXT["en"]["help_resources"], [e.value for e in app.error])

    def test_third_worried_english_reaction_escalates(self):
        post_id = self.public_post()
        app = self.start()
        app.radio[0].set_value("心声墙").run()
        for _ in range(3):
            app.button(key=f"reaction_{post_id}_worried").click().run()
            self.assertFalse(app.exception)
        self.assertEqual(self.posts()[0]["status"], "crisis")
        self.assertEqual(db.get_reaction_counts(post_id)["worried"], 3)
        self.assertEqual(len(db.get_approved_posts()), 0)
        self.assertIn(ui.TEXT["en"]["help_resources"], [e.value for e in app.error])
        self.assertEqual(len(self.requests), 0)

    def test_english_empty_form_error_is_localised_without_api(self):
        app = self.start()
        self.submit(app, " ")
        self.assertEqual(app.error[0].value, ui.TEXT["en"]["post_empty"])
        self.assertEqual(len(self.requests), 0)
        self.assertEqual(len(self.posts()), 0)
