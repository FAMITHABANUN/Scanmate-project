"""
Shared Google Gemini client (free tier - no credit card needed).

Get a free API key:
  1. Go to https://aistudio.google.com/apikey
  2. Sign in with any Google account and click "Create API key"
  3. Copy it into your .env file as: GEMINI_API_KEY=your-key-here
  4. Restart the app

Free tier limits (as of 2026): ~1,500 requests/day, which is plenty for a
student project. No card, no expiration.
"""
import os
from google import genai

_client = None
_checked = False


def get_client():
    """Returns a configured Gemini client, or None if no API key is set."""
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        _client = genai.Client(api_key=api_key)
    return _client


MISSING_KEY_MESSAGE = (
    "[ScanMate needs a free Gemini API key to use AI features. Get one at "
    "https://aistudio.google.com/apikey (no credit card needed), add it to "
    "your .env file as GEMINI_API_KEY=your-key-here, then restart the app.]"
)
