from app.reports.sanitize import plain_text, safe_filename


def test_report_text_and_filenames_strip_active_content_and_formula_prefixes() -> None:
    sanitized = plain_text('=HYPERLINK("javascript:alert(1)") <script>x</script> **bold**')
    assert sanitized.startswith("'HYPERLINK")
    assert "javascript:" not in sanitized.casefold()
    assert "<script>" not in sanitized
    assert "\\*\\*bold\\*\\*" in sanitized
    assert "\n" not in plain_text("first\nsecond")

    filename = safe_filename("../../Campus Services <script>", "weekly", "2026-07-23")
    assert filename == "campus-services-script-weekly-report-2026-07-23.md"
    assert "/" not in filename
    assert "\\" not in filename
