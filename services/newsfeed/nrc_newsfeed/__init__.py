"""Live NEPSE news intelligence — ambient sentiment for the desk.

Pulls fresh news (Sharesansar RSS + Google News RSS, no API key), tags to
scrips, enriches with Gemini (summary + sentiment + event), stores, and builds
a per-scrip sentiment rollup for the dashboard, company-360 page, and chat
context. See memory: news-sentiment-approach, nepse-news-sources."""
from __future__ import annotations

__version__ = "0.1.0"

from .pipeline import run_newsfeed, run_once

__all__ = ["run_newsfeed", "run_once"]
