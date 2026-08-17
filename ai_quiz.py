"""AI question/flashcard generation + grading via the Gemini API."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def _load_keys():
    """ALL Gemini keys: GEMINI_API_KEY plus any GEMINI_API_KEY_2, _3, _4...
    Each key has its own daily quota — rotating them multiplies the free tier."""
    keys = []
    main = os.environ.get("GEMINI_API_KEY", "").strip()
    if main:
        keys.append(main)
    for i in range(2, 9):
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if k and k not in keys:
            keys.append(k)
    if not keys:
        key_file = os.path.join(os.path.dirname(__file__), "gemini_key.txt")
        if os.path.exists(key_file):
            with open(key_file) as f:
                k = f.read().strip()
                if k:
                    keys.append(k)
    return keys


API_KEYS = _load_keys()
API_KEY = API_KEYS[0] if API_KEYS else ""   # backwards compat

# Free-tier daily quotas are PER MODEL — if one model is exhausted (429),
# we rotate to the next. All of these are strong multimodal Gemini models.
MODELS = [
    "gemini-3.1-flash-lite",      # fast (~1-2s), great quality for Q&A
    "gemini-flash-lite-latest",   # fast fallback
    "gemini-3.6-flash",           # stronger, ~10s
    "gemini-3.5-flash",           # stronger, may be quota-limited
]

MODEL = MODELS[0]  # for backwards compat (ai_teach imports MODEL)


def _url(model):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

BATCH_SIZE = 25          # max questions per AI call
MAX_PARALLEL = 2         # concurrent AI calls (free tier is rate-limited per minute)
MAX_RETRIES = 4          # retries on 429/5xx with exponential backoff

PROMPT = """You are an expert exam-question writer. Based ONLY on the study material below,
write {n} high-quality quiz questions at {difficulty} difficulty.

Difficulty guide:
- easy: direct recall of facts and definitions.
- medium: mix of recall and understanding; some "why/how" questions.
- hard: conceptual, applied and comparative questions ("why", "what would happen if",
  "which best explains", questions synthesizing multiple parts of the material).

{short_rule}

Rules:
- Every question must be answerable from the material alone.
- Aim for HIGHER-ORDER THINKING: application, analysis, comparison, cause-effect and
  multi-step reasoning — not just plain recall. Mix a few easy warm-ups with genuinely
  challenging questions that make students THINK.
- Multiple-choice questions: exactly 4 options, only one correct, distractors plausible.
- When the material involves maths or statistics, prioritise definitions, formulas,
  calculations and interpretation questions, and write notation in LaTeX wrapped in $...$
  (e.g. $x^2$, $\\bar{{x}}$, $\\sigma$) — the app renders it. Numeric options must look plausible.
- Vary question styles. Do not repeat topics already covered in this list of
  existing questions (write about DIFFERENT facts/aspects): {avoid}
- Include a ONE short sentence explanation of the correct answer (max 20 words).
- Keep questions and options concise — no unnecessary wordiness.

Return ONLY valid JSON, no markdown fences, in this exact shape:
{{"questions":[
  {{"type":"mcq","question":"...","options":["A","B","C","D"],"answer":0,"explanation":"..."}},
  {{"type":"short","question":"...","answer":"concise model answer","explanation":"..."}}
]}}
For "mcq", "answer" is the 0-based index of the correct option.

STUDY MATERIAL:
{material}
"""

SHORT_RULE_ON = ('About 1 in 4 questions should be typed short-answer questions '
                 '(type "short") where the student writes the answer in their own '
                 'words; the rest are multiple-choice (type "mcq").')
SHORT_RULE_OFF = 'All questions must be multiple-choice (type "mcq").'


def _gemini_url(model, stream=False):
    base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:"
    return base + ("streamGenerateContent?alt=sse" if stream else "generateContent")


RETRY_5XX_DELAYS = (1, 2)   # short backoffs only — never make the user wait 30s


# ---- quota self-healing: combos that hit the DAILY limit are skipped for hours,
# then automatically re-tested when the cooldown expires ----
_dead = {}                                  # (key_idx, model_idx) -> expiry timestamp
DEAD_COOLDOWN = 6 * 3600                    # hours; roughly one quota reset cycle


def _mark_dead(ki, mi):
    _dead[(ki, mi)] = time.time() + DEAD_COOLDOWN


def _alive(ki, mi):
    return _dead.get((ki, mi), 0) < time.time()


def _all_combos():
    return [(ki, mi) for ki in range(len(API_KEYS)) for mi in range(len(MODELS))
            if _alive(ki, mi)]


def _headers(ki):
    return {"Content-Type": "application/json", "x-goog-api-key": API_KEYS[ki]}


def _retry_delay(e):
    """Google's suggested retry delay (seconds) from a 429 body, if present.

    Per-MINUTE rate limits return a short delay (worth waiting for);
    daily quota exhaustion returns none (not worth waiting for)."""
    try:
        info = json.loads(e.read().decode())
        for d in info.get("error", {}).get("details", []):
            rd = str(d.get("retryDelay", ""))
            if rd.endswith("s"):
                return float(rd[:-1])
    except Exception:
        pass
    return None


def call_gemini(body):
    """POST a raw Gemini request. Sweeps every alive KEY x MODEL combo:
    waits out short per-minute limits, marks daily-quota combos dead for hours
    (self-heals when the cooldown expires), then fails fast to fallbacks."""
    payload = json.dumps(body).encode()
    combos = _all_combos()
    if not combos:
        raise RuntimeError("all Gemini quota is cooling down")
    short_waits = 0
    last_err = None
    for ki, mi in combos:
        for attempt in range(3):
            req = urllib.request.Request(_gemini_url(MODELS[mi]), data=payload,
                                         headers=_headers(ki), method="POST")
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 429:
                    wait = _retry_delay(e)
                    if wait and wait <= 45 and short_waits < 2:
                        short_waits += 1
                        time.sleep(wait + 1)
                        continue              # per-minute limit — worth the wait
                    _mark_dead(ki, mi)        # daily quota — cool this combo down
                    break
                if e.code >= 500 and attempt < 2:
                    time.sleep(RETRY_5XX_DELAYS[min(attempt, len(RETRY_5XX_DELAYS) - 1)])
                    continue
                raise
            except (TimeoutError, urllib.error.URLError, OSError) as e:
                last_err = e
                break                         # network issue — next combo
    if last_err:
        raise last_err
    raise RuntimeError("Gemini unavailable")


def call_gemini_stream(body):
    """Streaming variant: same key x model sweep, yields text chunks as they arrive."""
    payload = json.dumps(body).encode()
    combos = _all_combos()
    if not combos:
        raise RuntimeError("all Gemini quota is cooling down")
    short_waits = 0
    for ki, mi in combos:
        for attempt in range(3):
            req = urllib.request.Request(_gemini_url(MODELS[mi], stream=True), data=payload,
                                         headers=_headers(ki), method="POST")
            try:
                resp = urllib.request.urlopen(req, timeout=90)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = _retry_delay(e)
                    if wait and wait <= 45 and short_waits < 2:
                        short_waits += 1
                        time.sleep(wait + 1)
                        continue
                    _mark_dead(ki, mi)
                    break
                if e.code >= 500 and attempt < 2:
                    time.sleep(RETRY_5XX_DELAYS[min(attempt, len(RETRY_5XX_DELAYS) - 1)])
                    continue
                raise
            except (TimeoutError, urllib.error.URLError, OSError):
                break
            try:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:])
                        for part in data["candidates"][0]["content"]["parts"]:
                            t = part.get("text")
                            if t:
                                yield t
                    except (KeyError, IndexError, ValueError):
                        continue
            finally:
                resp.close()
            return


def _call_json(prompt_text, max_tokens=8192, temperature=0.8):
    body = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    import providers
    raw = None
    if API_KEY:
        try:
            data = call_gemini(body)
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            raw = None
    if raw is None:
        # Gemini is out (quota/5xx) — re-route to Groq / OpenRouter (separate quotas)
        raw = providers.fallback_generate(
            None, [{"role": "user", "parts": [{"text": prompt_text}]}],
            max_tokens=max_tokens, temperature=temperature, json_mode=True)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    return json.loads(raw)


def _validate(qlist):
    out = []
    for q in qlist:
        qtype = q.get("type", "mcq")
        text = q.get("question")
        if not isinstance(text, str) or not text.strip():
            continue
        if qtype == "short":
            ans = q.get("answer")
            if isinstance(ans, str) and ans.strip():
                out.append({"type": "short", "question": text.strip(),
                            "answer": ans.strip(),
                            "explanation": str(q.get("explanation", "")).strip()})
        else:
            opts = q.get("options", [])
            ans = q.get("answer")
            if (isinstance(opts, list) and len(opts) == 4
                    and isinstance(ans, int) and 0 <= ans < 4):
                out.append({"type": "mcq", "question": text.strip(),
                            "options": [str(o).strip() for o in opts],
                            "answer": ans,
                            "explanation": str(q.get("explanation", "")).strip()})
    return out


def _one_batch(material, n, difficulty, include_short, avoid_topics):
    avoid = "; ".join(avoid_topics[:40]) if avoid_topics else "none yet"
    prompt = PROMPT.format(
        n=n, difficulty=difficulty, material=material,
        short_rule=SHORT_RULE_ON if include_short else SHORT_RULE_OFF,
        avoid=avoid)
    parsed = _call_json(prompt)
    return _validate(parsed.get("questions", []))


CHUNK = 24000            # chars of material per AI call


def material_chunks(text, max_chunks=24):
    """Split large material into chunks so ALL of it can be used, not just the start."""
    text = text.strip()
    if len(text) <= CHUNK:
        return [text]
    chunks, start = [], 0
    while start < len(text) and len(chunks) < max_chunks:
        end = min(start + CHUNK, len(text))
        # try to break at a paragraph boundary
        cut = text.rfind("\n", start + CHUNK // 2, end)
        if cut == -1 or end == len(text):
            cut = end
        chunks.append(text[start:cut])
        start = cut
    return chunks


def ai_generate_quiz(text, num_questions=10, difficulty="medium", include_short=False, progress_cb=None):
    """Generate up to num_questions; large counts/materials are batched in parallel
    across chunks of the material so big books are fully covered.
    progress_cb(done, total) is called (from worker threads) as questions arrive."""
    if not API_KEY:
        raise RuntimeError("no API key configured")

    chunks = material_chunks(text)
    seen, questions = set(), []

    def add(qs):
        for q in qs:
            key = re.sub(r"\W+", "", q["question"].lower())[:80]
            if key and key not in seen:
                seen.add(key)
                questions.append(q)
        if progress_cb:
            try:
                progress_cb(len(questions), num_questions)
            except Exception:
                pass

    # first batch from the first chunk (fast path for small quizzes)
    first_n = min(num_questions, BATCH_SIZE)
    add(_one_batch(chunks[0], first_n, difficulty, include_short, []))

    remaining = num_questions - len(questions)
    if remaining > 0:
        n_batches = min((remaining + BATCH_SIZE - 1) // BATCH_SIZE, 24)
        topics_hint = [q["question"][:60] for q in questions]
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
            futures = [ex.submit(_one_batch, chunks[i % len(chunks)], BATCH_SIZE,
                                 difficulty, include_short, topics_hint)
                       for i in range(n_batches)]
            for fut in as_completed(futures):
                try:
                    add(fut.result())
                except Exception:
                    pass  # a failed batch just yields fewer questions

    if len(questions) < 3:
        raise RuntimeError("AI returned too few valid questions")
    return questions[:num_questions]


GRADE_PROMPT = """You are grading a student's typed answer to a short-answer question.

Question: {question}
Model answer: {model}
Student's answer: {student}

Judge the answer on meaning, NOT exact wording. For maths, treat equivalent forms as correct
(e.g. 0.5 = 1/2 = 50%, factored vs expanded when equal, √16 = 4); ignore missing units unless
the question asked for them. Return ONLY JSON:
{{"verdict":"correct" or "partial" or "wrong","feedback":"ONE short sentence (max 20 words): why, plus the missing bit if any"}}"""


def grade_short_answer(question, model_answer, student_answer):
    if not API_KEY:
        raise RuntimeError("no API key configured")
    parsed = _call_json(GRADE_PROMPT.format(
        question=question[:800], model=model_answer[:500],
        student=student_answer[:500]), max_tokens=1024, temperature=0.2)
    verdict = parsed.get("verdict", "wrong")
    if verdict not in ("correct", "partial", "wrong"):
        verdict = "wrong"
    return {"verdict": verdict, "feedback": str(parsed.get("feedback", "")).strip()}


CARDS_PROMPT = """From the study material below, create {n} high-quality flashcards
covering the most important facts, terms, formulas and concepts.
Front = a clear question or term. Back = a concise answer/definition (max 2 sentences).
Write any formulas in LaTeX wrapped in $...$ — the app renders them.
Cover different points — no duplicates.
Return ONLY JSON: {{"cards":[{{"front":"...","back":"..."}}]}}

STUDY MATERIAL:
{material}"""


def ai_flashcards(text, count=20):
    if not API_KEY:
        raise RuntimeError("no API key configured")
    parsed = _call_json(CARDS_PROMPT.format(n=count, material=text[:24000]))
    cards = []
    for c in parsed.get("cards", []):
        f, b = c.get("front"), c.get("back")
        if isinstance(f, str) and isinstance(b, str) and f.strip() and b.strip():
            cards.append({"front": f.strip(), "back": b.strip()})
    if len(cards) < 3:
        raise RuntimeError("AI returned too few cards")
    return cards[:count]
