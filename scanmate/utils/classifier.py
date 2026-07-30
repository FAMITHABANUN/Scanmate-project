"""
Lightweight, rule-based classifier that figures out what kind of handwritten
content was scanned, and a matching tips engine. Keyword matching stays the
fast, free first pass (works with no API key); when it can't confidently
place non-English text, or when tips/answers need to speak the scan's own
language, we fall back to Google's free-tier Gemini AI - the same model
already used elsewhere in the app.
"""
from google.genai import types

from utils.ai_client import get_client, MISSING_KEY_MESSAGE

PROGRAMMING_KEYWORDS = [
    "def ", "class ", "function", "public static void", "import ", "#include",
    "console.log", "return ", "while(", "for(", "for (", "int main", "printf",
    "System.out", "var ", "let ", "const ", "if(", "if (", "elif", "else:",
]
GROCERY_KEYWORDS = [
    "kg", "litre", "liter", "pcs", "dozen", "buy", "grocery", "milk", "rice",
    "vegetables", "fruits", "sugar", "oil", "atta", "onion", "tomato",
]
TODO_KEYWORDS = [
    "todo", "to-do", "to do", "task", "complete by", "deadline", "reminder",
    "finish", "pending", "checklist",
]
BILL_KEYWORDS = [
    "total", "amount", "rs.", "inr", "invoice", "bill", "paid", "due",
    "subtotal", "qty", "price",
]
VALID_CATEGORIES = {"programming", "grocery", "todo", "bill", "study_notes"}


def _classify_with_ai(text: str) -> str | None:
    """Used only when the keyword pass finds nothing to go on - typically
    because the scan is in a language the keyword lists don't cover. Returns
    None (caller falls back to 'study_notes') if AI isn't available or
    fails."""
    client = get_client()
    if client is None:
        return None

    system_prompt = (
        "Classify this scanned handwritten text into exactly one category: "
        "programming, grocery, todo, bill, or study_notes. The text may be "
        "in any language. Respond with ONLY the category word, nothing else."
    )
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[text[:2000]],
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        guess = (response.text or "").strip().lower()
        return guess if guess in VALID_CATEGORIES else None
    except Exception:
        return None


def classify_text(text: str) -> str:
    if not text:
        return "study_notes"

    text_lower = text.lower()
    scores = {"programming": 0, "grocery": 0, "todo": 0, "bill": 0}

    for k in PROGRAMMING_KEYWORDS:
        if k in text_lower:
            scores["programming"] += 1
    for k in GROCERY_KEYWORDS:
        if k in text_lower:
            scores["grocery"] += 1
    for k in TODO_KEYWORDS:
        if k in text_lower:
            scores["todo"] += 1
    for k in BILL_KEYWORDS:
        if k in text_lower:
            scores["bill"] += 1

    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        ai_guess = _classify_with_ai(text)
        return ai_guess or "study_notes"
    return best_category


def _check_bracket_balance(text: str) -> str | None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for ch in text:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                return "Heads up: your brackets look unbalanced somewhere - double check matching ( ), [ ], { }."
            stack.pop()
    if stack:
        return "Heads up: you have an unclosed bracket - double check matching ( ), [ ], { }."
    return None


def _localize_tips(tips: list, text: str) -> list:
    """The tip strings above are hard-coded English. If the scan itself
    isn't English, translate/adapt them into the scan's dominant language so
    they're actually useful - otherwise leave them exactly as they are (no
    AI call, no behavior change) for the common English case."""
    if not text or text.isascii():
        return tips

    client = get_client()
    if client is None:
        return tips

    system_prompt = (
        "Translate/adapt the following tip strings into the dominant "
        "language of this sample of scanned text (keep any leading emoji "
        "on each line exactly as-is, translate only the words). Sample "
        f"text:\n\n{text[:500]}\n\n"
        "Return exactly one translated tip per line, in the same order, "
        "with no numbering, no extra commentary, and no blank lines."
    )
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=["\n".join(tips)],
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        translated = [line.strip() for line in (response.text or "").splitlines() if line.strip()]
        return translated if len(translated) == len(tips) else tips
    except Exception:
        return tips


def get_tips(category: str, text: str) -> list:
    if category == "programming":
        tips = [
            "💬 Add comments above tricky logic so future-you remembers the intent.",
            "📐 Keep indentation consistent - mixed tabs/spaces cause hard-to-spot bugs.",
            "🧩 Break long functions into smaller ones with a single clear purpose.",
            "🏷️ Give variables descriptive names instead of x, y, temp.",
        ]
        bracket_warning = _check_bracket_balance(text)
        if bracket_warning:
            tips.insert(0, f"⚠️ {bracket_warning}")
        return _localize_tips(tips, text)

    if category == "grocery":
        tips = [
            "🛒 Group items by store section (produce, dairy, staples) to shop faster.",
            "🔢 Add quantities next to each item so you don't over- or under-buy.",
            "🏠 Check what's already at home before finalizing - avoid duplicate buys.",
        ]
        return _localize_tips(tips, text)

    if category == "todo":
        tips = [
            "📅 Order tasks by deadline, not just the order you thought of them.",
            "🧩 Break any task that takes more than an hour into smaller sub-tasks.",
            "🎯 Mark 1-3 tasks as 'must finish today' so the list doesn't overwhelm you.",
        ]
        return _localize_tips(tips, text)

    if category == "bill":
        tips = [
            "🧮 Double check the total against the sum of individual items.",
            "🗂️ Keep a digital copy in case you need it for reimbursement or warranty.",
            "🚩 Flag any charge you don't recognize before paying.",
        ]
        return _localize_tips(tips, text)

    # study_notes / general fallback
    tips = [
        "✍️ Summarize this page in 2-3 lines at the top - it helps recall later.",
        "🗂️ Turn key terms into quick flashcards for spaced repetition.",
        "🔁 Highlight anything you're unsure about and revisit it within 24 hours.",
    ]
    return _localize_tips(tips, text)


def get_answer(category: str, question: str, extracted_text: str = "") -> str:
    """AI-powered 'ask a specific question' responder. Sends the scan's
    actual extracted text plus the user's question to Gemini so the answer
    is grounded in what was really scanned, not just a keyword guess."""
    question = (question or "").strip()
    if not question:
        return "Type your question above and I'll do my best to help! 🙂"

    client = get_client()
    if client is None:
        return MISSING_KEY_MESSAGE

    system_prompt = (
        "You are ScanMate's assistant, helping a student with something they "
        f"scanned. The scan was auto-categorized as '{category}'. Here is the "
        f"exact text extracted from their scan:\n\n---\n{extracted_text or '(no text was extracted)'}\n---\n\n"
        "Answer the user's question about this scan directly and helpfully, "
        "the way a knowledgeable tutor would. Be specific to their actual "
        "content when possible, not generic advice. Reply in the same "
        "language the user's question is written in (or, if that's "
        "ambiguous, the dominant language of the scanned text above). Keep "
        "the answer concise (2-5 sentences unless more detail is clearly "
        "needed). You may use one relevant emoji at the start if it fits "
        "naturally."
    )

    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[question],
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        answer = (response.text or "").strip()
        return answer if answer else "I couldn't come up with an answer for that - try rephrasing your question?"
    except Exception as e:
        return f"[AI couldn't answer right now: {e}]"


def translate_text(text: str, target_language: str = "English") -> str:
    """Translates a scan's extracted text into the given language (English
    by default) using Gemini."""
    text = (text or "").strip()
    if not text:
        return "There's no text on this scan to translate."

    client = get_client()
    if client is None:
        return MISSING_KEY_MESSAGE

    system_prompt = (
        f"Translate the following scanned text into {target_language}. "
        "Preserve the original structure (line breaks, lists, numbers) as "
        "closely as possible. Return ONLY the translated text - no "
        "commentary, no notes, no quotation marks around it."
    )
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[text],
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        translated = (response.text or "").strip()
        return translated if translated else "Couldn't translate that - try again?"
    except Exception as e:
        return f"[Translation couldn't complete right now: {e}]"