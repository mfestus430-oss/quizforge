"""Extra AI providers — so MiPrep almost never runs out of AI.

Gemini stays first (best + multimodal). Groq and OpenRouter are independent
quota pools: when Google's daily quota is gone, the app silently re-routes.
Both use the OpenAI-compatible chat format (text only; images stay on Gemini).
"""
import json
import os
import time
import urllib.error
import urllib.request

GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"

GROQ_MODELS = [m.strip() for m in os.environ.get(
    "GROQ_MODELS", "llama-3.3-70b-versatile,llama-3.1-8b-instant").split(",") if m.strip()]
OR_MODELS = [m.strip() for m in os.environ.get(
    "OPENROUTER_MODELS", "meta-llama/llama-3.3-70b-instruct:free").split(",") if m.strip()]


def gemini_parts_to_messages(system, contents):
    """Convert Gemini format (system + contents/parts) into OpenAI chat messages (text only)."""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    for turn in contents or []:
        role = "assistant" if turn.get("role") == "model" else "user"
        texts, has_img = [], False
        for p in turn.get("parts", []):
            if not isinstance(p, dict):
                continue
            if p.get("text"):
                texts.append(p["text"])
            if "inline_data" in p:
                has_img = True
        text = "\n".join(texts)
        if has_img:
            text += "\n(image attachments are only supported by the primary AI)"
        if text.strip():
            msgs.append({"role": role, "content": text})
    return msgs


def _openai_call(url, key, model, messages, max_tokens, temperature, json_mode):
    body = {"model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"]


def fallback_generate(system, contents, max_tokens=2048, temperature=0.6, json_mode=False):
    """Try Groq, then OpenRouter. Returns the reply text, or raises RuntimeError."""
    msgs = gemini_parts_to_messages(system, contents)
    errors = []
    pools = (("groq", GROQ_URL, GROQ_KEY, GROQ_MODELS),
             ("openrouter", OR_URL, OPENROUTER_KEY, OR_MODELS))
    for label, url, key, models in pools:
        if not key or not models:
            continue
        for model in models:
            for attempt in range(2):
                try:
                    return _openai_call(url, key, model, msgs, max_tokens, temperature, json_mode)
                except urllib.error.HTTPError as e:
                    errors.append(f"{label}/{model}: HTTP {e.code}")
                    if e.code in (429, 500, 503) and attempt == 0:
                        time.sleep(2)
                        continue
                    break
                except Exception as e:
                    errors.append(f"{label}/{model}: {e}")
                    break
    raise RuntimeError("no fallback AI available (" + "; ".join(errors[:4]) + ")")


def available():
    """Which fallback providers are configured?"""
    return [label for label, key in (("groq", GROQ_KEY), ("openrouter", OPENROUTER_KEY)) if key]
