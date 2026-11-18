# moodle2pdf

**Turn a whole Moodle course into a clean folder of PDFs, in one command.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

Slides, Word handouts, multi-page HTML lessons, Moodle pages: everything becomes a PDF, sorted
by section, with an index. Read it offline, print it, annotate it on a tablet, keep it after the
semester ends, or hand it to an AI assistant to make revision notes.

```bash
python moodle2pdf.py "https://moodle.example.org/course/view.php?id=1234"
```

```
courses/Networks 101/
├── INDEX.md                      ← what was saved, skipped or failed
├── 01 Introduction/
│   └── Course outline.pdf
├── 02 Chapter 1 - TCP_IP/
│   ├── Slides chapter 1.pdf      ← was a .pptx
│   └── Lesson online.pdf         ← a 40-page HTML site, merged into one PDF
└── 03 Exercises/
    ├── Worksheet 1.pdf           ← was a .docx
    ├── Lab files.zip
    └── Lab files/                ← the zip, extracted
```

## Why moodle2pdf?

- **Everything ends up as PDF.** No more `.pptx`, `.docx` and loose HTML files you can't open on
  your phone. One format to read, search, annotate and print.
- **Multi-page HTML lessons become one PDF.** Many teachers upload small websites (MkDocs, exported
  slides). Downloading `index.html` alone gives you one page; moodle2pdf follows the links and merges
  every page in order.
- **Works like you do: through the normal course page.** It doesn't need Moodle's mobile-app web
  service, which some institutions disable.
- **Your password stays yours.** You sign in yourself in a real browser window, so university single
  sign-on (CAS) works. The tool only keeps the session cookies, locally.
- **Honest output.** If something can't be converted, it's marked FAILED in `INDEX.md` with the
  reason, never saved as a broken file.
- **Pick what you want.** `--list` numbers every item; `--only 3,7-9` gets just those.

## Quick start

```bash
git clone https://github.com/Allouche-Adam/moodle2pdf.git
cd moodle2pdf
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

python moodle2pdf.py "https://your-moodle/course/view.php?id=1234" --list   # see what's there
python moodle2pdf.py "https://your-moodle/course/view.php?id=1234"          # get it all
```

On the first run a browser window opens: sign in, wait until the course page shows, and the
window closes by itself. Later runs are silent until your Moodle session expires. Re-running only
fetches what's missing.

> **`.moodle-session.json` gives access to your Moodle account.** It stays next to the script, is
> in `.gitignore`, and must never be shared.

## Options

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

## What happens to each item

| Moodle item | Result |
|---|---|
| File: PDF | kept as is |
| File: Word / PowerPoint | converted to PDF with installed Microsoft Office (Windows only) |
| File: zip | extracted next to itself |
| File: HTML | printed to PDF, **with every page it links to in the same folder** (max 60), merged in link order |
| Page | printed to PDF |
| Folder | every file inside, same rules |
| Link to a file on the same Moodle | downloaded |
| Other links, quizzes, forums… | listed in `INDEX.md` only |

## Requirements

- Python 3.10+ and Chromium through Playwright (installed in the quick start).
- **Windows + Microsoft Office** only for converting Word/PowerPoint. Everything else works on
  Windows, macOS and Linux; elsewhere, Office files are reported as FAILED.

## Known limits

- **Sign-in detection** looks for `/login/` in the address or `cas` in the host name. Moodles that
  sign in through another provider (Microsoft, Shibboleth…) may not open the sign-in window and stop
  with *"Found no sections on the page"*. A fix is welcome.
- Reads the standard Moodle 3.x/4.x course page. Heavily customised themes or the "one section per
  page" layout may show fewer items.
- One saved session at a time: switching to another Moodle asks you to sign in again.

## Alternatives

| Tool | Best when |
|---|---|
| **moodle2pdf** | you want a readable folder of PDFs, including HTML lessons merged into one file |
| [Moodle-DL](https://github.com/C0D3D3V/Moodle-DL) | you want *everything* (assignments, forums, quizzes, videos) kept in sync, in original formats, and your Moodle has the mobile web service enabled |
| [moodle-downloader](https://github.com/harsilspatel/moodle-downloader) | you prefer a Chrome extension to batch-download files by hand |

## Contributing

Issues and pull requests are welcome, especially:
- sign-in detection for Microsoft / Shibboleth / other single sign-on providers;
- reports of Moodle themes or layouts where `--list` misses items (please include your Moodle
  version, not your course content);
- Office conversion on macOS/Linux (e.g. through LibreOffice).

If moodle2pdf saved you time, a ⭐ helps other students find it.

Only download material you're allowed to access, and respect your institution's rules on sharing it.

## License

MIT, see [LICENSE](LICENSE).
