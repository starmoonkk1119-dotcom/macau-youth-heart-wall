"""Isolated browser/agent check. Never use as the production entrypoint."""

import json
import os
from pathlib import Path
import runpy
import sys
import tempfile

import httpx
from openai import OpenAI
import streamlit as st

PROJECT = Path(__file__).resolve().parents[1] / "outputs"
sys.path.insert(0, str(PROJECT))
import ai
import db
import seed


@st.cache_resource
def fixture_directory():
    directory = tempfile.TemporaryDirectory(prefix="heart-wall-ui-check-")
    db.DB_PATH = Path(directory.name) / "isolated.db"
    db.init_db()
    db.seed_demo_posts(seed.DEMO_POSTS)
    return directory


def fixture_response(request):
    payload = json.loads(request.content)
    english = "ai_reply must be in warm, natural English" in payload["messages"][0]["content"]
    # The provider fixture always reports crisis; it does not test model semantics.
    return httpx.Response(200, json={
        "id": "isolated-fixture",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek-chat",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "category": "情绪", "intensity": 5, "moderation": "crisis",
                    "ai_reply": ai.REPLY_TEXT["en" if english else "zh"]["crisis"],
                }),
            },
            "finish_reason": "stop",
        }],
    })


def fixture_client(*args, **kwargs):
    return OpenAI(
        *args, **kwargs,
        http_client=httpx.Client(transport=httpx.MockTransport(fixture_response)),
    )


db.DB_PATH = Path(fixture_directory().name) / "isolated.db"
os.environ["DEEPSEEK_API_KEY"] = "isolated-fake-key"
os.environ["ADMIN_PASS"] = "isolated-demo-only"
ai.OpenAI = fixture_client
runpy.run_path(str(PROJECT / "app.py"), run_name="__main__")
