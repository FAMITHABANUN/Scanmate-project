# ScanMate

Turn any handwritten page — study notes, programming notes, a grocery list,
a to-do list, a bill — into clean digital text. After scanning, ScanMate
asks "Can I help you with this?" and, only if you say yes, offers tips
relevant to what you scanned (e.g. code-structure tips for programming
notes, prioritization tips for a to-do list).

100% free stack: Flask + SQLite + Tesseract OCR (open-source, no API key) +
Gmail SMTP for email. No paid services required to build, run, or deploy.

---

## 1. Run locally

### Install Tesseract (one-time, on your machine)
- **Windows:** download the installer from
  https://github.com/UB-Mannheim/tesseract/wiki and install it. Add the
  install folder to your PATH.
- **Mac:** `brew install tesseract`
- **Linux:** `sudo apt-get install tesseract-ocr`

### Set up the project
```bash
cd scanmate
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # then edit .env with your own values
```

### Run
```bash
python app.py
```
Visit `http://localhost:5000`

---

## 2. Email setup (optional but recommended)

The "Welcome to ScanMate" email is sent via **Brevo** (formerly Sendinblue) - a
free email API, no credit card required, up to 300 emails/day.

1. Sign up free at https://www.brevo.com
2. In your Brevo dashboard, go to **Senders & IP → Senders → Add a sender**,
   and verify the email address you want to send from (check that inbox for
   the verification link).
3. Go to **SMTP & API → API Keys → Generate a new API key**.
4. Copy the key into your `.env`:
   ```
   BREVO_API_KEY=your-key-here
   MAIL_FROM=the-verified-sender-address@example.com
   APP_URL=https://your-app-name.onrender.com
   ```

If you skip this, registration still works — the app just logs a message
instead of sending an email, so nothing breaks during a demo.

---

## 3. Push to GitHub

```bash
cd scanmate
git init
git add .
git commit -m "Initial commit - ScanMate"
git branch -M main
git remote add origin https://github.com/<your-username>/scanmate.git
git push -u origin main
```

---

## 4. Deploy free on Render

1. Go to https://render.com and sign up (free, no card required for the
   free web-service tier).
2. Click **New +** → **Web Service** → connect your GitHub repo.
3. Render will detect the `Dockerfile` automatically (the Dockerfile is
   what installs Tesseract, which the native Python buildpack can't do).
4. Under **Environment**, add:
   - `SECRET_KEY` — any random string (Render can auto-generate this)
   - `BREVO_API_KEY` — your Brevo API key
   - `MAIL_FROM` — your verified Brevo sender email
   - `APP_URL` — your live Render URL (fill this in after your first deploy,
     since it's used in the welcome email's button link)
5. Choose the **Free** instance type.
6. Click **Create Web Service**. First build takes a few minutes (it's
   installing Tesseract inside the container).
7. Your live URL will look like `https://scanmate-xxxx.onrender.com`.

**Note on Render's free tier:** the service spins down after ~15 minutes of
inactivity and takes ~30-50 seconds to wake back up on the next request.
For a live demo in front of judges, open the site a minute or two before
you present so it's already awake.

**Note on the database:** Render's free tier filesystem is not permanently
persistent across redeploys/restarts, so treat scan history as demo data —
don't rely on it surviving long-term without upgrading to a paid disk or an
external database later.

---

## Project structure
```
scanmate/
├── app.py                  # Flask app & all routes
├── requirements.txt
├── Dockerfile               # installs Tesseract + runs gunicorn
├── render.yaml               # Render deploy config
├── utils/
│   ├── ocr.py               # Tesseract OCR extraction
│   ├── classifier.py        # rule-based content classifier + tips
│   └── email_utils.py       # Brevo API welcome email
├── templates/                # HTML pages
├── static/
│   ├── css/style.css
│   └── uploads/              # scanned images saved here
└── instance/
    └── scanmate.db           # SQLite database (auto-created)
```

## How the AI assistant works
1. OCR extracts the text from the uploaded photo.
2. A rule-based classifier looks at the extracted text for category
   signals (code syntax, grocery words, to-do phrasing, bill/invoice
   terms) and picks the closest match.
3. The page shows: *"I noticed this looks like [category]. Can I help you
   with it?"*
4. Only if the user clicks **Yes**, the app calls `/scan/<id>/help`, which
   returns a small set of relevant tips for that category.

This keeps the whole "AI assistant" layer running at zero cost (no LLM API
calls) while still giving a genuinely different experience per content
type — useful to mention in your SIH pitch as a deliberate cost/consent
design choice, not a limitation.
