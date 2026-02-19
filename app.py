import os
import re
from collections import Counter
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader

# ----------------------------
# Basic Flask setup
# ----------------------------
app = Flask(__name__)
app.secret_key = "change-this-secret-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "txt"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB limit

# ----------------------------
# Helpers
# ----------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def read_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def read_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_parts.append(page_text)
    return "\n".join(text_parts)

def clean_text(text: str) -> str:
    # Normalize whitespace
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def split_sentences(text: str):
    # Simple sentence splitter (no extra libraries needed)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Split on ., ?, ! while keeping it simple
    sentences = re.split(r"(?<=[.!?])\s+", text)
    # Filter very short sentences
    return [s.strip() for s in sentences if len(s.strip()) >= 25]

def tokenize_words(text: str):
    # Lowercase and keep only letters/numbers
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    return words

STOPWORDS = set("""
a an and are as at be by for from has he in is it its of on or that the to was were will with you your
we they them this those these i my our us not can could should would may might about into than then
""".split())

def summarize_text(text: str, num_sentences: int = 6) -> str:
    """
    Frequency-based extractive summary:
    - Score sentences by word frequencies (excluding stopwords)
    - Pick top N sentences in original order
    """
    sentences = split_sentences(text)
    if not sentences:
        return "Could not extract enough text to summarise. Try a different file or a clearer PDF."

    words = tokenize_words(text)
    freq = Counter(w for w in words if w not in STOPWORDS and len(w) > 2)

    if not freq:
        return "Text was extracted, but it was too limited to summarise."

    # Score sentences
    scored = []
    for idx, s in enumerate(sentences):
        s_words = tokenize_words(s)
        score = sum(freq[w] for w in s_words if w in freq)
        scored.append((score, idx, s))

    scored.sort(reverse=True, key=lambda x: x[0])
    top = scored[: min(num_sentences, len(scored))]
    # Restore original order
    top_sorted = sorted(top, key=lambda x: x[1])
    summary = " ".join([s for _, _, s in top_sorted])
    return summary

def generate_questions(text: str, max_q: int = 6):
    """
    Very simple rule-based question generator (V1):
    - Finds key terms (most frequent non-stopwords)
    - Produces short questions around them
    """
    words = tokenize_words(text)
    freq = Counter(w for w in words if w not in STOPWORDS and len(w) > 3)
    key_terms = [w for w, _ in freq.most_common(10)]

    templates = [
        "Define: '{term}'.",
        "Explain the importance of '{term}' in the topic.",
        "Give one example of how '{term}' is used.",
        "What are the benefits or risks related to '{term}'?",
        "How does '{term}' impact users or systems?"
    ]

    questions = []
    t_i = 0
    for term in key_terms:
        if len(questions) >= max_q:
            break
        questions.append(templates[t_i % len(templates)].format(term=term))
        t_i += 1

    if not questions:
        questions = [
            "Summarise the main idea of the document in your own words.",
            "List 3 key points from the document.",
            "What problem is being discussed and what solution is suggested?"
        ]

    return questions

# ----------------------------
# Routes
# ----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part found.")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected.")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)

            ext = filename.rsplit(".", 1)[1].lower()
            try:
                if ext == "pdf":
                    raw_text = read_pdf(save_path)
                else:
                    raw_text = read_txt(save_path)
            except Exception as e:
                flash(f"Error reading file: {e}")
                return redirect(url_for("index"))

            text = clean_text(raw_text)
            if len(text) < 200:
                flash("Extracted text is too short. If it’s a scanned PDF, text extraction may not work.")
                return redirect(url_for("index"))

            summary = summarize_text(text, num_sentences=6)
            questions = generate_questions(text, max_q=6)

            return render_template(
                "result.html",
                filename=filename,
                summary=summary,
                questions=questions
            )

        flash("File type not allowed. Upload a PDF or TXT.")
        return redirect(request.url)

    return render_template("index.html")

if __name__ == "__main__":
    # Run locally
    app.run(host="127.0.0.1", port=5000, debug=True)
