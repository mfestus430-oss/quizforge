"""Offline fallbacks — keep MiPrep useful when the AI quota is exhausted or no key is set.

Builds notes-style lessons, flashcards, courses and keyword-retrieval answers straight
from the uploaded material. No AI calls at all.
"""
import random
import re

DEF_RE = re.compile(r"^\s*([A-Z][\w \-']{2,40})\s*[:\u2014\u2013-]\s+(.{15,160})$")


def _app():
    """Lazily import app helpers (avoids circular imports at module load)."""
    import app
    return app


def definition_pairs(text, limit=8):
    """Pull 'Term: definition' style pairs out of the text."""
    out = []
    for ln in text.splitlines():
        m = DEF_RE.match(ln.strip())
        if m and m.group(1).lower() not in ("note", "example", "warning", "tip"):
            out.append((m.group(1).strip(), m.group(2).strip()))
        if len(out) >= limit * 2:
            break
    return out[:limit]


def top_sentences(text, n=10):
    """Rank sentences by keyword importance (same engine as the offline quiz)."""
    app = _app()
    sents = app.sentences_from(text)
    freq, _ = app.key_terms(text)

    def score(s):
        words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-']{3,}", s)]
        return sum(freq.get(w, 0) for w in words if w not in app.STOPWORDS) / (len(words) + 1)

    ranked = sorted(sents, key=score, reverse=True)
    out, seen = [], set()
    for s in ranked:
        k = s[:40].lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
        if len(out) >= n:
            break
    return out


def build_notes(text, topic=""):
    """A structured study-notes 'lesson' in markdown — no AI."""
    app = _app()
    freq, _ = app.key_terms(text)
    terms = [w for w, _ in freq.most_common(10)]
    defs = definition_pairs(text)
    mains = top_sentences(text, 8)
    parts = []
    title = topic.strip() or "your material"
    parts.append(f"# Study notes: {title}")
    parts.append("*Offline summary of your material — the AI tutor is unavailable "
                 "(quota or connection), but your studying continues.*")
    if terms:
        parts.append("## Key terms\n\n" + ", ".join(f"**{t}**" for t in terms))
    if defs:
        parts.append("## Key definitions\n\n" + "\n".join(f"- **{t}** — {d}" for t, d in defs))
    if mains:
        parts.append("## Main points\n\n" + "\n".join(f"- {s}" for s in mains))
    try:
        qs = [q for q in app.generate_quiz(text, 3) if q["type"] == "mcq"]
        if qs:
            qlines = [f"{i}. {q['question']}" for i, q in enumerate(qs, 1)]
            parts.append("## Quick practice\n\n" + "\n".join(qlines) +
                         "\n\n*Answer from memory, then check against the points above.*")
    except Exception:
        pass
    return "\n\n".join(parts)


def build_flashcards(text, count=20):
    """Definition cards → 'define this term' cards → fill-in-the-blank cards."""
    app = _app()
    cards = []
    for t, d in definition_pairs(text, limit=count):
        cards.append({"front": t, "back": d})
    freq, _ = app.key_terms(text)
    for term, _ in freq.most_common(count * 3):
        if len(cards) >= count:
            break
        for s in top_sentences(text, 60):
            if re.search(r"\b" + re.escape(term) + r"\b", s, re.I):
                cards.append({"front": f"Define / explain: {term}", "back": s})
                break
    if len(cards) < count:
        sents = app.sentences_from(text)
        random.shuffle(sents)
        for s in sents:
            if len(cards) >= count:
                break
            w = app.pick_blank_word(s, freq)
            if not w:
                continue
            blanked = re.sub(r"\b" + re.escape(w) + r"\b", "_____", s, count=1)
            cards.append({"front": f"Fill in the blank: {blanked}", "back": w})
    return cards[:count]


N_SESSIONS = 5


def _chunks(material):
    size = max(1, len(material) // N_SESSIONS)
    out = [material[i * size:(i + 1) * size] for i in range(N_SESSIONS)]
    return [c for c in out if len(c.split()) >= 25] or out[:1]


def build_syllabus(material, topic=""):
    """An offline 5-part course carved from the material."""
    app = _app()
    sessions = []
    for i, chunk in enumerate(_chunks(material), 1):
        freq, _ = app.key_terms(chunk)
        top = [w.capitalize() for w, _ in freq.most_common(2)]
        title = " · ".join(top) if top else f"Section {i}"
        sessions.append({"title": f"Part {i}: {title}",
                         "goal": "Work through the key ideas in this section of your material."})
    name = (topic.strip() or "Your material")
    return {"course_title": f"{name} — offline course", "sessions": sessions}


def build_session_lesson(material, num, title):
    """Offline lesson + checkpoint questions for course session `num` (1-based)."""
    app = _app()
    chunks = _chunks(material)
    chunk = chunks[min(num - 1, len(chunks) - 1)]
    lesson = build_notes(chunk, title)

    def mcqs(source):
        out = []
        for q in app.generate_quiz(source, 4):
            if q["type"] == "mcq":
                out.append({"question": q["question"], "options": q["options"],
                            "answer": q["answer"], "explanation": q.get("explanation", "")})
        return out

    qs = mcqs(chunk)
    if len(qs) < 2:
        qs = mcqs(material)   # tiny chunk — take questions from the whole material instead
    return {"lesson": lesson, "questions": qs[:3]}


def answer_from_material(material, question, max_sents=3):
    """Keyword retrieval: answer a question with the most relevant sentences of the material."""
    app = _app()
    qwords = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-']{3,}", question)
              if w.lower() not in app.STOPWORDS]
    if not qwords or not material:
        return ""
    scored = []
    for s in app.sentences_from(material):
        lw = s.lower()
        sc = sum(1 for w in qwords if w in lw)
        if sc:
            scored.append((sc, s))
    scored.sort(key=lambda x: -x[0])
    top = [s for _, s in scored[:max_sents]]
    if not top:
        return ""
    return ("**From your material** *(offline search — the AI tutor is unavailable)*\n\n"
            + "\n".join(f"- {s}" for s in top))
