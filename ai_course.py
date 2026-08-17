"""Course mode — structured multi-session teaching with understanding checkpoints."""
from ai_quiz import API_KEY, call_gemini, _call_json, material_chunks


def spread_material(material, budget=24000):
    """For big books: sample evenly across the WHOLE text so the syllabus covers everything."""
    if not material or len(material) <= budget:
        return material
    chunks = material_chunks(material)
    per = max(800, budget // len(chunks))
    return "\n[...]\n".join(ch[:per] for ch in chunks)

LEVEL_STYLE = {
    "std": "Explain naturally and clearly, the way ChatGPT would in a normal chat: plain, "
           "well-organized language, brief definitions of new terms, one good example. "
           "Full technical substance, no gimmicks.",
    "kid": "Simple words a 7-year-old could follow: tiny sentences, everyday examples "
           "(mangoes, candies, football), a few emojis, every math step shown with tiny numbers. "
           "IMPORTANT: language is simple but the CONTENT keeps full depth — real concepts, real "
           "formulas (each symbol explained in a friendly way), the real 'why'. Never dumb it down.",
    "teen": "High-school level language: clear wording, define every term in one line, one worked "
            "example. Keep full content depth — including the advanced parts — just accessibly worded.",
    "facts": "Fact-sheet style: minimal prose. Teach through tight bullet-point facts, "
             "formulas in LaTeX with symbols explained in one line each, and 2-3 classic "
             "traps/exceptions. Scannable, no filler.",
}

SYLLABUS_PROMPT = """You are a master teacher designing a course.
Based on the {source}, design a step-by-step course of 4-8 short sessions that takes a
beginner to solid understanding, in logical teaching order (fundamentals first, each
session builds on the previous one).

Return ONLY JSON:
{{"course_title":"...","sessions":[{{"title":"...","goal":"one line: what the student will be able to do after this session"}}]}}

{material_block}"""


def make_syllabus(material, topic, level):
    if not API_KEY:
        raise RuntimeError("no API key configured")
    if material:
        source = "study material below (a book, slides or notes)"
        material_block = "STUDY MATERIAL:\n" + spread_material(material)
    else:
        source = f'topic "{topic}"'
        material_block = ""
    parsed = _call_json(SYLLABUS_PROMPT.format(source=source, material_block=material_block))
    sessions = [{"title": str(s.get("title", "")).strip(), "goal": str(s.get("goal", "")).strip()}
                for s in parsed.get("sessions", []) if s.get("title")][:10]
    if len(sessions) < 2:
        raise RuntimeError("could not build a syllabus from this input")
    return {"course_title": str(parsed.get("course_title", topic or "Your course")).strip(),
            "sessions": sessions}


LESSON_PROMPT = """You are teaching session {num} of the course "{course}".
Session title: {title}
Session goal: {goal}
Teaching style: {style}
{reteach}

Teach THIS SESSION ONLY, step by step: 3-6 small numbered steps, each step one small idea
with a tiny example. When the content involves maths or statistics, write formulas in LaTeX
wrapped in $...$ (the app renders them) and show the steps of any worked example.
Maximum ~300 words total. Use markdown headings/bullets. Do not
preview future sessions. Base the teaching on the study material if provided; otherwise
on solid general knowledge of the subject.

Then write exactly 3 multiple-choice checkpoint questions that test THIS session only
(4 options each, exactly one correct, plausible distractors).

Return ONLY JSON:
{{"lesson":"markdown lesson text","questions":[{{"question":"...","options":["a","b","c","d"],"answer":0,"explanation":"one short sentence"}}]}}

{material_block}"""


def teach_session(material, course, num, title, goal, level, reteach=False):
    if not API_KEY:
        raise RuntimeError("no API key configured")
    parsed = _call_json(LESSON_PROMPT.format(
        num=num, course=course, title=title, goal=goal,
        style=LEVEL_STYLE.get(level, LEVEL_STYLE["std"]),
        reteach=("IMPORTANT: The student did NOT understand your previous explanation of this "
                 "session. Re-teach it a DIFFERENT way: new angle, different examples, even "
                 "simpler and slower. Do not repeat the same wording." if reteach else ""),
        material_block=("STUDY MATERIAL:\n" + spread_material(material)) if material else ""),
        max_tokens=4096)
    lesson = str(parsed.get("lesson", "")).strip()
    qs = []
    for q in parsed.get("questions", []):
        opts = q.get("options", [])
        if (isinstance(q.get("question"), str) and isinstance(opts, list)
                and len(opts) == 4 and isinstance(q.get("answer"), int)):
            qs.append({"question": q["question"].strip(),
                       "options": [str(o).strip() for o in opts],
                       "answer": q["answer"] % 4,
                       "explanation": str(q.get("explanation", "")).strip()})
    if not lesson or len(qs) < 2:
        raise RuntimeError("bad session payload")
    return {"lesson": lesson, "questions": qs[:3]}


ASK_PROMPT = """A student in a course session titled "{title}" asks: {question}

The session's lesson content:
{lesson}

Teaching style: {style}
Answer the question directly in the first sentence, max ~120 words total.
Stay true to the study material if provided.
{material_block}"""


def ask_course(material, title, lesson, question, level, extra_parts=None):
    if not API_KEY:
        raise RuntimeError("no API key configured")
    parts = list(extra_parts or [])   # attached images/docs first, then the prompt
    parts.append({"text": ASK_PROMPT.format(
        title=title, question=question[:600], lesson=lesson[:6000],
        style=LEVEL_STYLE.get(level, LEVEL_STYLE["std"]),
        material_block=("STUDY MATERIAL:\n" + spread_material(material, 15000)) if material else "")})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 2048},
    }
    data = call_gemini(body)
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip()
