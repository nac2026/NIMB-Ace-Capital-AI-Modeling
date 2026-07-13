"""Speculative Analysis — review mode.

Multi-agent investigative review of an uploaded WRITTEN research report:
  report_parser   — PDF/DOCX → text → extract thesis/claims/recommendation/scrips
  claim_verifier  — verify each claim against ground-truth data
  aspect_assessors— independent multi-aspect assessment per scrip
  debate          — bull vs bear vs judge → unbiased RED/AMBER/GREEN verdict
  counter_report  — generate the COE-facing review report

Reuses the screen-mode data (speculative_pipeline.analyze_tickers) + the broker
/sentiment tools as the ground-truth substrate."""
from __future__ import annotations

from .report_parser import ParsedClaim, ParsedReport, extract_text, parse_report
from .review_pipeline import run_review, run_review_from_text

__all__ = ["ParsedReport", "ParsedClaim", "extract_text", "parse_report",
           "run_review", "run_review_from_text"]
