# 🚀 QuizForge Deployment Guide (phone-friendly)

Follow these steps in order. Total time: ~15–20 minutes.
You can do ALL of this from your phone's browser.

---

## PART 1 — Create a GitHub account (5 min)
GitHub is where your app's code will live. (Skip to Part 2 if you have one.)

1. Go to **github.com/signup**
2. Enter your email, create a password and a username
3. Verify your email with the code they send you
4. Done — you're on the free plan, that's all you need

## PART 2 — Create the repository (2 min)

1. Go to **github.com/new**
2. Repository name: **quizforge**
3. Keep it **Private** (recommended) or Public — either works
4. DON'T tick "Add a README" (we already have one)
5. Tap **Create repository**
6. On the next page, copy the repository URL — it looks like:
   `https://github.com/YOUR_USERNAME/quizforge.git`

## PART 3 — Upload the code
Two ways — pick ONE:

### Easy way (phone, no commands): upload the zip contents
1. On your new empty repo page, tap **"uploading an existing file"**
2. Extract quizforge.zip (from our chat) on your device
3. Upload ALL the files and the templates folder
   (EXCEPT `gemini_key.txt` — never upload that one!)
4. Tap **Commit changes**

### Pro way (laptop, 1 minute): push with git
Tell the assistant "I created the repo, here's the URL" — you'll get a
Personal Access Token walkthrough and the exact commands, OR run these
in the extracted quiz-app folder:
```
git remote add origin https://github.com/YOUR_USERNAME/quizforge.git
git push -u origin main
```
(GitHub will ask you to sign in — use a Personal Access Token from
github.com/settings/tokens as the password.)

## PART 4 — Create a Render account (3 min)

1. Go to **render.com**
2. Tap **Get Started** → sign up with **GitHub** (easiest — one tap,
   and it auto-connects your repos)
3. Authorize Render when GitHub asks

## PART 5 — Deploy! (5 min)

1. In the Render dashboard tap **New +** → **Web Service**
2. Select your **quizforge** repository (tap "Configure account" if you
   don't see it, and grant access to the repo)
3. Render reads the Dockerfile automatically. Settings to confirm:
   - Name: **quizforge** (this becomes your URL!)
   - Region: **Frankfurt** (closest to Ghana)
   - Instance type: **Free**
4. Scroll to **Environment Variables** → tap **Add Environment Variable**:
   - Key: `GEMINI_API_KEY`
   - Value: (paste your Gemini key — it's in gemini_key.txt in the zip)
5. Tap **Deploy Web Service**
6. Wait ~5 minutes while it builds. When you see **"Live"** in green:

   🎉 Your app is at: **https://quizforge.onrender.com**
   (or quizforge-XXXX.onrender.com if the name was taken)

Save it to your phone's home screen: open the URL → browser menu →
**"Add to Home Screen"** → it now looks and opens like a real app! 📱

---

## ⚠️ Free tier quirks (good to know)
- **Cold starts:** after ~15 min with no visitors, the app naps.
  The first visit wakes it — takes ~30–60 seconds. Totally normal.
- **750 free hours/month** — more than enough for one app.

## 🔄 Updating the app later
Come back to the Arena conversation, ask for changes. After we build
and test them, you get updated files → upload them to GitHub (same as
Part 3) → Render redeploys automatically in ~5 minutes. Same URL.

## 🆘 If something goes wrong
Screenshot the error and paste it in the Arena conversation — logs are
in the Render dashboard under your service → "Logs".
