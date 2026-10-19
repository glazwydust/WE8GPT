"""Thin wrapper around the Gemini API (google-genai SDK). JSON-only output, one retry on bad JSON."""
import json
import re
import time
from . import config


class GeminiError(RuntimeError):
    pass


def _parse(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    return json.loads(t)


class GeminiClient:
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.model = model or config.GEMINI_MODEL
        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY is not set. Put it in .env (never in git).")
        from google import genai            # pip install google-genai
        from google.genai import types
        self._types = types
        self._client = genai.Client(api_key=self.api_key)

    def _call(self, system, user):
        cfg = self._types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.1,
        )
        last = None
        for attempt in range(2):            # one retry for transient API errors
            try:
                r = self._client.models.generate_content(model=self.model, contents=user, config=cfg)
                return r.text
            except Exception as e:           # noqa: BLE001 - SDK raises several types
                last = e
                time.sleep(2)
        raise GeminiError(f"Gemini call failed: {last}")

    def generate_json(self, system, user):
        text = self._call(system, user)
        try:
            return _parse(text)
        except (json.JSONDecodeError, TypeError):
            fix = user + "\n\nYour previous reply was not valid JSON. Reply again with ONLY valid JSON in the exact shape requested."
            text = self._call(system, fix)
            try:
                return _parse(text)
            except (json.JSONDecodeError, TypeError) as e:
                raise GeminiError(f"Gemini returned invalid JSON twice: {e}")
