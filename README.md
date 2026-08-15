# ⚡ MiPrep

**Designed & built by Festus Mensah** — Accra, Ghana 🇬🇭

Upload slides/notes/images → get an AI quiz, or get taught from scratch (7-year-old to university level) with rendered math.

## Run it on your own computer

1. Install Python 3.10+ from python.org
2. Install Tesseract OCR (needed for reading text in images):
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki (run the installer)
   - Mac: `brew install tesseract`
   - Linux: `sudo apt install tesseract-ocr`
3. Open a terminal in this folder, then:
   ```
   pip install -r requirements.txt
   python app.py
   ```
4. Open http://localhost:5000 in your browser. Done!

## API key
The Gemini API key is read from `gemini_key.txt` (already included) or the
`GEMINI_API_KEY` environment variable. If the key is missing or over its daily
free quota, quizzes fall back to the built-in (non-AI) engine and Teach Me
mode shows an error until the quota resets.

## Files
- `app.py` — Flask server: upload, quiz, and teach endpoints
- `ai_quiz.py` — AI quiz generation (Gemini)
- `ai_teach.py` — AI tutor (multimodal: sees images)
- `templates/index.html` — the whole frontend (UI, quiz player, lesson viewer, KaTeX math)
- `gemini_key.txt` — your API key (keep private!)
