"""Thin wrapper around the Gemini API (google-genai SDK). JSON-only output, retries busy errors, one retry on bad JSON."""
import json
import re
import threading
import time
from . import config


class GeminiError(RuntimeError):
    pass


def _parse(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    return json.loads(t)


CALL_TIMEOUT = 90          # seconds: a call that takes longer is treated as a failure instead of freezing the app


def _with_timeout(fn, seconds):
    """Run fn() in a background thread; raise TimeoutError if it does not finish in time."""
    box = {}

    def run():
        try:
            box["value"] = fn()
        except Exception as e:               # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError(f"Timeout: Gemini did not answer within {seconds}s")
    if "error" in box:
        raise box["error"]
    return box["value"]


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

    def _config(self, system, fast, thinking):
        kw = {}
        if fast and thinking and config.GEMINI_THINKING_BUDGET is not None:
            kw["thinking_config"] = self._types.ThinkingConfig(thinking_budget=config.GEMINI_THINKING_BUDGET)
        return self._types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                                 temperature=0.1, **kw)

    def _call(self, system, user, fast=False):
        """fast=True is for the chat box. It has a hard overall time limit (config.CHAT_DEADLINE seconds): if Gemini has not
        answered by then this raises GeminiError at once, so the caller can show a saved-results answer instead of making the user wait."""
        end = time.time() + config.CHAT_DEADLINE
        thinking = getattr(self, "_thinking_ok", True)        # remembered once a model rejects the thinking setting
        primary = config.GEMINI_CHAT_MODEL if (fast and config.GEMINI_CHAT_MODEL) else self.model
        models = [primary]
        for m in (config.GEMINI_FALLBACK_MODEL, self.model):          # then the backup model, then the main model
            if m and m not in models:
                models.append(m)
        last = None
        for model in models:
            waits = [0, 2] if fast else ([0, 5, 15] if model != models[-1] else [0, 5, 15, 30])
            for attempt, wait in enumerate(waits):
                if fast:
                    if time.time() + wait >= end:
                        raise GeminiError(f"Gemini did not answer within {config.CHAT_DEADLINE}s: {last or 'slow'}")
                    timeout = max(1.0, min(config.CHAT_ATTEMPT_TIMEOUT, end - time.time() - wait))
                else:
                    timeout = CALL_TIMEOUT
                if wait:
                    print(f"  Gemini busy, retrying in {wait}s (attempt {attempt + 1}/{len(waits)})...", flush=True)
                    time.sleep(wait)
                try:
                    cfg = self._config(system, fast, thinking)
                    r = _with_timeout(lambda: self._client.models.generate_content(model=model, contents=user, config=cfg), timeout)
                    return r.text
                except Exception as e:           # noqa: BLE001 - SDK raises several types
                    last = e
                    msg = str(e)
                    if thinking and fast and "thinking" in msg.lower():   # this model does not accept the thinking setting: drop it and retry now
                        thinking = self._thinking_ok = False
                        try:
                            cfg = self._config(system, fast, False)
                            r = _with_timeout(lambda: self._client.models.generate_content(model=model, contents=user, config=cfg), timeout)
                            return r.text
                        except Exception as e2:  # noqa: BLE001
                            last, msg = e2, str(e2)
                    transient = any(k in msg for k in ("503", "429", "500", "502", "504", "UNAVAILABLE",
                                                       "RESOURCE_EXHAUSTED", "DEADLINE", "timed out", "Timeout"))
                    if "PerDay" in msg or "per day" in msg.lower():   # this model's daily quota is used up: try the backup, if any
                        break
                    if not transient:            # wrong key / wrong model name etc: retrying won't help
                        break
            if model != models[-1]:
                print(f"  {model} is not answering; trying {models[models.index(model) + 1]}...", flush=True)
        raise GeminiError(f"Gemini call failed: {last}")

    def generate_json(self, system, user, fast=False):
        text = self._call(system, user, fast)
        try:
            return _parse(text)
        except (json.JSONDecodeError, TypeError):
            if fast:
                raise GeminiError("Gemini returned invalid JSON")
            fix = user + "\n\nYour previous reply was not valid JSON. Reply again with ONLY valid JSON in the exact shape requested."
            text = self._call(system, fix, fast)
            try:
                return _parse(text)
            except (json.JSONDecodeError, TypeError) as e:
                raise GeminiError(f"Gemini returned invalid JSON twice: {e}")

    def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
        """Turn texts into vectors (list of lists). task: RETRIEVAL_DOCUMENT for evidence, RETRIEVAL_QUERY for questions/claims.
        Embeddings have their own quota, separate from the text model. Retries busy errors like _call."""
        cfg = self._types.EmbedContentConfig(task_type=task, output_dimensionality=config.EMBED_DIM)
        out, last = [], None
        for k in range(0, len(texts), 100):                      # the API takes up to 100 texts per call
            batch = texts[k: k + 100]
            for attempt, wait in enumerate([0, 5, 15]):
                if wait:
                    time.sleep(wait)
                try:
                    r = _with_timeout(lambda: self._client.models.embed_content(
                        model=config.EMBED_MODEL, contents=batch, config=cfg), CALL_TIMEOUT)
                    out += [list(e.values) for e in r.embeddings]
                    break
                except Exception as e:           # noqa: BLE001
                    last = e
                    if not any(x in str(e) for x in ("503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "Timeout")) \
                            or "PerDay" in str(e):
                        raise GeminiError(f"Embedding call failed: {e}")
            else:
                raise GeminiError(f"Embedding call failed: {last}")
        return out
