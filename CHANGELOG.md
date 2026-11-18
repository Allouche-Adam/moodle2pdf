# Changelog

## 1.0.0 (2026-11-18)

First public release.

### Added
- Download a Moodle course into one folder per section, with `INDEX.md` (saved / skipped / failed).
- Sign-in in a visible browser window; cookies saved to `.moodle-session.json` for later runs.
- PDF kept, Word/PowerPoint → PDF (Office on Windows), zip extracted, HTML resources and Moodle
  pages printed to PDF (multi-page HTML resources merged), folders downloaded.
- `--list`, `--only`, `--choose`, `--out`, `--force`, `--max-mb`, `--include-software`.

### Fixed (before release)
- A file link that returned a Moodle notice page was saved as a fake PDF; it is now FAILED with
  the page title.
- Multi-page HTML resources kept only their first page; linked pages are now followed.
- The session was lost between runs with a persistent browser profile; cookies are now saved
  explicitly.
- `pywin32` is only installed on Windows, so `pip install -r requirements.txt` works elsewhere.
