# Decisions

## Fail loudly when Moodle answers with a page instead of a file
- **Chosen:** if a file link returns HTML while the filename isn't `.html`, mark the item FAILED
  with the page title.
- **Why:** a fake PDF looks fine in the folder and is useless later.
- **Rejected:** saving whatever comes back.

## Follow linked pages of HTML resources
- **Chosen:** print the HTML resource and every `.html` page it links to in the same folder
  (max 60), merged into one PDF in link order.
- **Why:** teachers often upload small multi-page sites; printing `index.html` alone loses most pages.
- **Rejected:** printing only the main file; crawling outside the resource's folder (would wander
  into Moodle itself).

## Skip software and big files by default, with switches to opt in
- **Chosen:** skip `.jar/.exe/.msi/.dmg/...` and files over 50 MB; `--include-software` and
  `--max-mb 0` turn this off. Size is read with a HEAD request first.
- **Why:** the goal is course documents; installers are huge and time out.

## Manual selection by item number
- **Chosen:** `--list` numbers every item; `--only` / `--choose` take those numbers. A partial run
  doesn't rewrite `INDEX.md`.
- **Why:** `INDEX.md` describes the whole course; a partial run would wipe entries it didn't touch.

## Sign-in by the user in a real browser window, cookies saved locally
- **Chosen:** Playwright Chromium. On Moodle's login page, open a visible window where the user
  signs in, then save cookies to `.moodle-session.json` (gitignored) for hidden runs.
- **Why:** the tool never handles the password, and it works with single sign-on. Moodle's login
  cookie is a session cookie, so a persistent browser profile lost it on close.
- **Rejected:** asking for the password in the CLI; pasting cookies by hand; a persistent profile.
- **Affects:** `.moodle-session.json` is a secret.

## Office for Word/PowerPoint, Chromium for HTML
- **Chosen:** Word/PowerPoint through COM (`pywin32`), HTML through Chromium `page.pdf()`.
- **Why:** Office gives the most faithful PDFs; Playwright brings its own Chromium.
- **Affects:** Office conversion is Windows-only; `pywin32` is installed only on Windows.
