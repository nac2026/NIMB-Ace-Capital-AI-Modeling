-- Hold the extracted report text on the session so review-mode analyze can run
-- the (slow, LLM-heavy) pipeline asynchronously after a fast upload. Extraction
-- (PDF/DOCX→text) happens at upload; the LLM verification happens at analyze.
ALTER TABLE analysis_sessions ADD COLUMN IF NOT EXISTS report_text TEXT;
