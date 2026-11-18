# moodle2pdf

Download a whole **Moodle course** and turn its documents into **PDFs**, one folder per section,
with an `INDEX.md` listing what was saved, skipped or failed.

Useful for offline revision, archiving a course before you lose access, or feeding course
material to other tools.

- Works with your normal sign-in (including university single sign-on): **you** sign in in a real
  browser window; the tool never sees your password.
- PDFs kept as is; Word/PowerPoint converted to PDF; HTML resources (even multi-page ones) printed
  to PDF; Moodle "pages" printed to PDF; folders and zips unpacked.
- Re-running only fetches what's missing.

## Requirements

- Python 3.10+
- Chromium via Playwright (installed below)
- **Windows + Microsoft Office** only for converting `.doc/.docx/.ppt/.pptx`. Everything else
  works on Windows, macOS and Linux; on other systems Office files are reported as FAILED.

## Install

```bash
git clone https://github.com/<owner>/moodle2pdf.git
cd moodle2pdf
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Use

```bash
python moodle2pdf.py "https://moodle.example.org/course/view.php?id=1234"
```

1. First run (or when your Moodle session expires): a browser window opens. Sign in there and
   wait until the course page shows; the window then closes by itself (5-minute limit).
2. The login cookies are saved in `.moodle-session.json` next to the script so later runs are
   silent. **This file gives access to your Moodle account: never commit or share it.** It is in
   `.gitignore`.
3. Files land in `courses/<course name>/`, one folder per section, plus `INDEX.md`.

| Option | Does |
|---|---|
| `--list` | show every item with a number, download nothing (try this first on a new Moodle) |
| `--only 3,7-9` | download only those items |
| `--choose` | show the list, then ask for numbers |
| `--out DIR` | output folder (default `courses/<course name>`) |
| `--force` | re-download files that already exist |
| `--max-mb N` | skip files bigger than N MB (default 50, `0` = no limit) |
| `--include-software` | also get `.jar`, `.exe`, `.dmg`… (skipped by default) |

A partial run (`--only`, `--choose`) doesn't rewrite `INDEX.md`, so the index keeps describing the
whole course.

## What it does with each item

| Moodle item | Result |
|---|---|
| File: PDF | kept as is |
| File: Word / PowerPoint | converted to PDF with installed Office (Windows) |
| File: zip | extracted next to itself |
| File: HTML | printed to PDF, **with every page it links to in the same folder** (max 60), merged in link order |
| Page | printed to PDF |
| Folder | every file inside, same rules |
| Link to a file on the same Moodle | downloaded |
| Other links, quizzes, forums… | listed in `INDEX.md` only |

It fails loudly instead of guessing: if Moodle answers with a web page where a file was expected
(a notice, an error page), the item is marked FAILED with the page title rather than saved as a
fake PDF.

## Known limits

- **Sign-in detection** looks for `/login/` in the address or `cas` in the host name. Moodles that
  sign in through another provider (e.g. Microsoft, Shibboleth) may not open the sign-in window and
  stop with *"Found no sections on the page"*. Contributions welcome.
- Reads the standard Moodle 3.x/4.x course page (`li.section`, `li.activity`). Heavily customised
  themes or the "one section per page" layout may show fewer items.
- One saved session at a time: switching to another Moodle asks you to sign in again.

Only download material you're allowed to access, and respect your institution's rules on sharing it.

## License

MIT, see [LICENSE](LICENSE).
