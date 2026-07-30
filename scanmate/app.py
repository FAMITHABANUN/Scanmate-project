import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from utils.ocr import extract_text_from_image
from utils.classifier import classify_text, get_tips, get_answer, translate_text
from utils.email_utils import _get_registration_html, _get_scan_summary_html, _send_email
from utils.export import text_to_image, text_to_pdf

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "scanmate.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            extracted_text TEXT,
            category TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )"""
    )
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


CATEGORY_LABELS = {
    "programming": "Programming / Code Notes",
    "grocery": "Grocery List",
    "todo": "To-Do List",
    "bill": "Bill / Invoice",
    "study_notes": "General / Study Notes",
}


# ---------------------------------------------------------------------------
# Routes - Auth
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    if "user_id" in session and not request.args.get("home"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("register"))

        conn = get_db()
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            flash("An account with this email already exists.", "error")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, password_hash, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

        # Send a pleasant welcome email (fails silently if Brevo isn't configured)
        html = _get_registration_html(name)
        _send_email(email, name, "Welcome to ScanMate!", html, f"Welcome, {name}!")

        flash("✅ Registration successful! Please check your email and log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash(f"👋 Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))

        flash("❌ Invalid email or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("👋 You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Routes - Dashboard & Scanning
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    scans = conn.execute(
        "SELECT * FROM scans WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return render_template("dashboard.html", scans=scans)


@app.route("/scan", methods=["POST"])
@login_required
def scan():
    file = request.files.get("camera_image") or request.files.get("file_image")
    if file is None or file.filename == "":
        flash("No file uploaded.", "error")
        return redirect(url_for("dashboard"))
    if file.filename == "" or not allowed_file(file.filename):
        flash("Please upload a valid image (png, jpg, jpeg, webp).", "error")
        return redirect(url_for("dashboard"))

    filename = secure_filename(f"{session['user_id']}_{int(datetime.utcnow().timestamp())}_{file.filename}")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    extracted_text = extract_text_from_image(filepath)
    category = classify_text(extracted_text)

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO scans (user_id, filename, extracted_text, category, created_at) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], filename, extracted_text, category, datetime.utcnow().isoformat()),
    )
    conn.commit()
    scan_id = cur.lastrowid

    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()

    # Email the user a copy of their scan summary (fails silently if Brevo isn't configured)
    if user:
        label = CATEGORY_LABELS.get(category, "General Notes")
        html = _get_scan_summary_html(user["name"], label, extracted_text)
        _send_email(
            user["email"], user["name"],
            "Your ScanMate Scan Summary", html, extracted_text,
        )

    return redirect(url_for("view_scan", scan_id=scan_id))


@app.route("/scan/<int:scan_id>")
@login_required
def view_scan(scan_id):
    conn = get_db()
    scan_row = conn.execute(
        "SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, session["user_id"])
    ).fetchone()
    conn.close()

    if not scan_row:
        flash("Scan not found.", "error")
        return redirect(url_for("dashboard"))

    return render_template(
        "scan_result.html",
        scan=scan_row,
        category_label=CATEGORY_LABELS.get(scan_row["category"], "General Notes"),
    )


@app.route("/scan/<int:scan_id>/help", methods=["POST"])
@login_required
def scan_help(scan_id):
    """AI assistant endpoint. Only called after the user explicitly agrees ('Yes')."""
    conn = get_db()
    scan_row = conn.execute(
        "SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, session["user_id"])
    ).fetchone()
    conn.close()

    if not scan_row:
        return jsonify({"error": "Scan not found"}), 404

    tips = get_tips(scan_row["category"], scan_row["extracted_text"])
    return jsonify({"category": scan_row["category"], "tips": tips})


@app.route("/scan/<int:scan_id>/ask", methods=["POST"])
@login_required
def scan_ask(scan_id):
    """Lets the user type a specific question about their scan and get a
    tailored, rule-based answer (no paid AI API involved)."""
    conn = get_db()
    scan_row = conn.execute(
        "SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, session["user_id"])
    ).fetchone()
    conn.close()

    if not scan_row:
        return jsonify({"error": "Scan not found"}), 404

    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    answer = get_answer(scan_row["category"], question, scan_row["extracted_text"])
    return jsonify({"answer": answer})


@app.route("/scan/<int:scan_id>/translate", methods=["POST"])
@login_required
def scan_translate(scan_id):
    """Translates the scan's extracted text (English by default)."""
    conn = get_db()
    scan_row = conn.execute(
        "SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, session["user_id"])
    ).fetchone()
    conn.close()

    if not scan_row:
        return jsonify({"error": "Scan not found"}), 404

    data = request.get_json(silent=True) or {}
    target_language = data.get("target_language", "English").strip() or "English"
    translation = translate_text(scan_row["extracted_text"], target_language)
    return jsonify({"translation": translation})


@app.route("/scan/<int:scan_id>/download/<fmt>")
@login_required
def download_scan(scan_id, fmt):
    """Download the extracted text as a branded PNG image or a PDF."""
    conn = get_db()
    scan_row = conn.execute(
        "SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, session["user_id"])
    ).fetchone()
    conn.close()

    if not scan_row:
        flash("Scan not found.", "error")
        return redirect(url_for("dashboard"))

    label = CATEGORY_LABELS.get(scan_row["category"], "General Notes")
    text = scan_row["extracted_text"] or ""

    if fmt == "image":
        buffer = text_to_image(text, label)
        return send_file(buffer, mimetype="image/png", as_attachment=True,
                          download_name=f"scanmate_scan_{scan_id}.png")

    if fmt == "pdf":
        buffer = text_to_pdf(text, label)
        return send_file(buffer, mimetype="application/pdf", as_attachment=True,
                          download_name=f"scanmate_scan_{scan_id}.pdf")

    flash("Unknown download format.", "error")
    return redirect(url_for("view_scan", scan_id=scan_id))


@app.route("/scan/<int:scan_id>/delete", methods=["POST"])
@login_required
def delete_scan(scan_id):
    conn = get_db()
    scan_row = conn.execute(
        "SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, session["user_id"])
    ).fetchone()
    if scan_row:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], scan_row["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)
        conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
        conn.commit()
    conn.close()
    flash("🗑️ Scan deleted.", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)