"""moodle2pdf - download a Moodle course and turn its documents into PDFs.

Usage:
    python moodle2pdf.py <course-url> [--out DIR] [--force]

How it works, in short:
  1. It opens a hidden Chromium browser. When Moodle wants a sign-in (first
     run, or once your session expires), a visible window opens and you sign
     in yourself. The tool never sees your password; it only saves the login
     cookies to .moodle-session.json, like a browser would.
  2. It reads the course page and lists every section and activity.
  3. For each activity it saves what makes sense:
       - files (PDF, Word, PowerPoint, HTML, zip)  -> downloaded, then
         Word/PowerPoint -> PDF via your installed Office,
         HTML -> PDF via the browser's "print to PDF",
         zip -> extracted next to it
       - Moodle "page" activities -> printed to PDF
       - folders -> every file inside, same rules
       - links, quizzes, forums -> only listed in INDEX.md (nothing to download)
  4. It writes INDEX.md in the output folder: what was saved where, and what failed.

Anything it can't handle is reported as FAILED in the console and INDEX.md
instead of being guessed at.
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parent
# Your Moodle login cookies (like a browser keeps them). Private: never commit or share.
SESSION_FILE = ROOT / ".moodle-session.json"

WORD_EXT = {".doc", ".docx", ".odt", ".rtf"}
PPT_EXT = {".ppt", ".pptx", ".odp"}
HTML_EXT = {".html", ".htm"}
MAX_SITE_PAGES = 60  # safety stop when following the pages of an HTML course
# Installers and libraries: not something you revise from.
SOFTWARE_EXT = {".jar", ".exe", ".msi", ".dmg", ".pkg", ".iso", ".apk", ".deb", ".rpm"}

# Reads the course page structure. Runs inside the browser.
COURSE_JS = """
() => [...document.querySelectorAll('li.section')].map(s => ({
  section: (s.querySelector('.sectionname') || {}).innerText || 'Section',
  items: [...s.querySelectorAll('li.activity')].map(a => {
    const link = a.querySelector('a.aalink') || a.querySelector('a[href*="/mod/"]');
    const mod = [...a.classList].find(c => c.startsWith('modtype_')) || '';
    const name = (a.querySelector('.instancename') || a).innerText.split('\\n')[0];
    return { mod: mod.replace('modtype_', ''), name: name.trim(), url: link ? link.href : null };
  })
}))
"""


def safe_name(text, max_len=80):
    """Turn any title into a valid Windows file/folder name."""
    text = text.replace("\xa0", " ")  # French non-breaking spaces ("Cours :")
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .")
    return (text or "untitled")[:max_len].rstrip(" .")


def is_login_page(url):
    return "/login/" in url or "cas" in urlparse(url).netloc.lower()


def ensure_logged_in(pw, course_url):
    """Return (browser, context, page) for a hidden browser that can see the course.

    Moodle's login cookie is a session cookie: a browser drops it when it
    closes. So after the user signs in we save the cookies to SESSION_FILE
    and load them into the hidden browser, and into later runs, until Moodle
    expires the session. Then the login window simply appears again.
    """
    browser = pw.chromium.launch(headless=True)
    state = str(SESSION_FILE) if SESSION_FILE.exists() else None
    ctx = browser.new_context(storage_state=state)
    page = ctx.new_page()
    page.goto(course_url)
    if not is_login_page(page.url):
        return browser, ctx, page
    browser.close()

    print("Not signed in. A browser window is opening: sign in to Moodle there.")
    print("(Waiting up to 5 minutes; the window closes by itself afterwards.)")
    visible = pw.chromium.launch(headless=False)
    login_ctx = visible.new_context()
    login_page = login_ctx.new_page()
    login_page.goto(course_url)
    # Wait until we land back on the course page itself.
    login_page.wait_for_url(lambda u: "/course/view.php" in u, timeout=5 * 60 * 1000)
    login_ctx.storage_state(path=str(SESSION_FILE))
    visible.close()

    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state=str(SESSION_FILE))
    page = ctx.new_page()
    page.goto(course_url)
    if is_login_page(page.url):
        sys.exit("Still not signed in after the login window. Try again.")
    return browser, ctx, page


class Skipped(Exception):
    """A file left out on purpose (software, or over --max-mb); not an error."""


class Downloader:
    def __init__(self, ctx, page, force, max_bytes, include_software):
        self.ctx = ctx
        self.page = page  # one reusable tab for printing pages to PDF
        self.force = force
        self.max_bytes = max_bytes
        self.include_software = include_software
        self.log = []  # (section, name, status, detail) for INDEX.md

    # ---------- fetching ----------

    def fetch_file(self, url, dest_dir):
        """Download one Moodle file URL into dest_dir. Returns (saved path, file URL).

        Moodle resource links (mod/resource/view.php) either redirect straight
        to the file, or show an HTML page that embeds it. In the second case
        we look for the pluginfile.php link inside that page.
        """
        if "/mod/resource/view.php" in url and "redirect=1" not in url:
            url += "&redirect=1"
        # Ask for the size first (HEAD = headers only), so huge installers are
        # skipped instead of downloaded. No size given -> we just download it.
        head = self.ctx.request.head(url)
        if not self.include_software and Path(urlparse(head.url).path).suffix.lower() in SOFTWARE_EXT:
            raise Skipped("software, not a course document (--include-software to get it)")
        size = int(head.headers.get("content-length") or 0)
        if size > self.max_bytes:
            raise Skipped(f"too big: {size / 1e6:.0f} MB (--max-mb 0 to get it)")
        resp = self.ctx.request.get(url)
        if not resp.ok:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        final_url = resp.url
        ctype = resp.headers.get("content-type", "")

        if "pluginfile.php" not in final_url and "text/html" in ctype:
            match = re.search(r'https?://[^"\'<>\s]+/pluginfile\.php/[^"\'<>\s]+', resp.text())
            if not match:
                raise RuntimeError("page had no downloadable file in it")
            return self.fetch_file(match.group(0).replace("&amp;", "&"), dest_dir)

        filename = unquote(urlparse(final_url).path.rsplit("/", 1)[-1]) or "file"
        # Moodle answers some file links (e.g. no access) with an HTML notice
        # page. Saving that as "x.pdf" would look fine and be useless: fail loudly.
        if "text/html" in ctype and Path(filename).suffix.lower() not in HTML_EXT:
            page_title = re.search(r"<title>(.*?)</title>", resp.text(), re.S)
            raise RuntimeError(f"Moodle sent a page instead of {filename}: "
                               f"'{page_title.group(1).strip() if page_title else '?'}'")
        dest = dest_dir / safe_name(filename, 120)
        if not dest.exists() or self.force:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.body())
        return dest, final_url

    # ---------- converting ----------

    def to_pdf(self, path, source_url=None, title=None):
        """Convert a downloaded file to PDF where it makes sense.

        Returns the PDF path, the extracted folder for zips, or the file itself
        when no conversion applies (e.g. .sql, .java: kept as they are).
        `title` names the PDF after the Moodle activity; useful for HTML
        resources, whose file is usually just "index.html".
        """
        ext = path.suffix.lower()
        pdf = path.with_name(safe_name(title) + ".pdf") if title else path.with_suffix(".pdf")
        if ext == ".pdf":
            return path
        if ext == ".zip":
            return extract_zip(path)
        if pdf.exists() and not self.force:
            return pdf
        if ext in WORD_EXT:
            office_to_pdf(path, pdf, "word")
        elif ext in PPT_EXT:
            office_to_pdf(path, pdf, "powerpoint")
        elif ext in HTML_EXT:
            # Print from the original URL when we have it, so images and
            # stylesheets referenced relatively still load.
            self.print_site(source_url or path.as_uri(), pdf)
        else:
            return path
        return pdf

    def print_url(self, url, pdf):
        self.page.goto(url, wait_until="networkidle")
        pdf.parent.mkdir(parents=True, exist_ok=True)
        self.page.pdf(path=str(pdf), format="A4", print_background=True,
                      margin={"top": "15mm", "bottom": "15mm", "left": "12mm", "right": "12mm"})

    def print_site(self, start_url, pdf):
        """Print an HTML resource and every .html page it links to in the same
        folder, merged into one PDF in link order.

        Teachers often upload a small website (index.html + one page per part,
        e.g. made with MkDocs). Printing only index.html would silently drop
        most of the course.
        """
        base = start_url.rsplit("/", 1)[0] + "/"
        queue, seen = [start_url.split("#")[0]], set()
        writer = PdfWriter()
        tmp = pdf.with_suffix(".part.pdf")
        while queue and len(seen) < MAX_SITE_PAGES:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            self.print_url(url, tmp)
            writer.append(str(tmp))
            links = self.page.eval_on_selector_all("a[href]", "els => els.map(e => e.href.split('#')[0])")
            queue += [u for u in links if u.startswith(base) and u.endswith(".html") and u not in seen]
        tmp.unlink(missing_ok=True)
        with open(pdf, "wb") as f:
            writer.write(f)
        if queue:
            print(f"    note: stopped after {MAX_SITE_PAGES} pages of {start_url}")

    # ---------- per activity type ----------

    def handle(self, section, item, dest_dir):
        mod, name, url = item["mod"], item["name"], item["url"]
        if not url:
            return self.note(section, name, "skipped", "no link (hidden or restricted)")
        try:
            if mod == "resource":
                path, file_url = self.fetch_file(url, dest_dir)
                out = self.to_pdf(path, file_url, title=name)
                self.note(section, name, "saved", out)
            elif mod == "folder":
                self.handle_folder(section, name, url, dest_dir / safe_name(name))
            elif mod == "page":
                pdf = dest_dir / (safe_name(name) + ".pdf")
                if self.force or not pdf.exists():
                    self.print_url(url, pdf)
                self.note(section, name, "saved", pdf)
            elif mod == "url":
                target = self.resolve_url_module(url)
                # A "link" that points to a file on this Moodle is really a document.
                if "/pluginfile.php/" in target and urlparse(target).netloc == urlparse(url).netloc:
                    path, file_url = self.fetch_file(target, dest_dir)
                    self.note(section, name, "saved", self.to_pdf(path, file_url, title=name))
                else:
                    self.note(section, name, "link", target)
            else:
                self.note(section, name, "not downloadable", f"{mod}: {url}")
        except Skipped as exc:
            self.note(section, name, "skipped", exc)
        except Exception as exc:  # report and keep going with the other items
            # First line only: Playwright appends a call log to its errors that
            # contains the request's cookies, i.e. your Moodle session.
            self.note(section, name, "FAILED", str(exc).splitlines()[0])

    def handle_folder(self, section, name, url, dest_dir):
        self.page.goto(url)
        links = self.page.eval_on_selector_all(
            'a[href*="pluginfile.php"]', "els => [...new Set(els.map(e => e.href))]")
        if not links:
            return self.note(section, name, "FAILED", "folder shows no files")
        for link in links:
            path, file_url = self.fetch_file(link, dest_dir)
            out = self.to_pdf(path, file_url)
            self.note(section, f"{name} / {path.name}", "saved", out)

    def resolve_url_module(self, url):
        resp = self.ctx.request.get(url + "&redirect=1", max_redirects=0)
        return resp.headers.get("location") or url

    def note(self, section, name, status, detail):
        self.log.append((section, name, status, str(detail)))
        print(f"  [{status}] {name} -> {detail}")


def extract_zip(path):
    """Extract a zip next to itself, refusing entries that escape the folder."""
    target = path.with_suffix("")
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        for member in zf.namelist():
            dest = (target / member).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise RuntimeError(f"zip entry escapes folder: {member}")
        zf.extractall(target)
    return target


def office_to_pdf(src, pdf, app_name):
    """Convert with the installed Word or PowerPoint through COM automation."""
    import win32com.client  # only needed when there is an Office file

    src, pdf = str(src.resolve()), str(pdf.resolve())
    if app_name == "word":
        app = win32com.client.DispatchEx("Word.Application")
        app.Visible = False
        try:
            doc = app.Documents.Open(src, ReadOnly=True)
            doc.ExportAsFixedFormat(pdf, 17)  # 17 = wdExportFormatPDF
            doc.Close(False)
        finally:
            app.Quit()
    else:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        try:
            pres = app.Presentations.Open(src, ReadOnly=True, WithWindow=False)
            pres.SaveAs(pdf, 32)  # 32 = ppSaveAsPDF
            pres.Close()
        finally:
            app.Quit()


def write_index(out_dir, title, course_url, log):
    lines = [f"# {title}", "", f"Source: {course_url}", ""]
    current = None
    for section, name, status, detail in log:
        if section != current:
            lines += ["", f"## {section}", ""]
            current = section
        if status == "saved":
            rel = Path(detail).resolve().relative_to(out_dir.resolve()).as_posix()
            lines.append(f"- {name}: [{rel}](<{rel}>)")
        elif status == "link":
            lines.append(f"- {name}: link to {detail}")
        else:
            lines.append(f"- {name}: **{status}** ({detail})")
    failed = sum(1 for _, _, s, _ in log if s == "FAILED")
    lines += ["", f"_{failed} failed item(s)._", ""]
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Download a Moodle course as PDFs.")
    parser.add_argument("course_url", help="e.g. https://moodle.example.fr/course/view.php?id=1234")
    parser.add_argument("--out", help="output folder (default: courses/<course name>)")
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    parser.add_argument("--max-mb", type=int, default=50,
                        help="skip files bigger than this (default 50, 0 = no limit)")
    parser.add_argument("--include-software", action="store_true",
                        help="also download installers/libraries (.jar, .exe, .dmg...)")
    pick = parser.add_mutually_exclusive_group()
    pick.add_argument("--list", action="store_true", help="only show the numbered items, download nothing")
    pick.add_argument("--only", metavar="NUMS", help="download only these item numbers, e.g. 3,7-9")
    pick.add_argument("--choose", action="store_true", help="show the list, then ask which numbers to get")
    args = parser.parse_args()

    if "id" not in parse_qs(urlparse(args.course_url).query):
        sys.exit("The URL must be a course page like .../course/view.php?id=1234")
    selected = parse_selection(args.only) if args.only else None

    with sync_playwright() as pw:
        browser, ctx, page = ensure_logged_in(pw, args.course_url)
        # Page title looks like "Cours : <name> | Moodle". French puts a
        # non-breaking space before ":", hence \s rather than a plain space.
        title = re.sub(r"^Cours\s*:\s*", "", page.title().split("|")[0]).strip()
        sections = page.evaluate(COURSE_JS)
        if not sections:
            sys.exit("Found no sections on the page. Is this a Moodle course page?")

        # Number every item across the course: these are the numbers that
        # --list shows and --only / --choose take.
        numbered = []  # (number, section index, section name, item)
        for i, sec in enumerate(sections):
            for item in sec["items"]:
                numbered.append((len(numbered) + 1, i, sec["section"], item))

        print(f"Course: {title}")
        if args.list or args.choose:
            print_list(numbered)
        if args.list:
            browser.close()
            return
        if args.choose:
            selected = parse_selection(input("\nNumbers to download (e.g. 3,7-9; empty = all): "))
        if selected and (unknown := sorted(selected - {n for n, *_ in numbered})):
            sys.exit(f"No item numbered {unknown} (this course has 1-{len(numbered)}). Check with --list.")

        out_dir = Path(args.out) if args.out else ROOT / "courses" / safe_name(title)
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"Saving to: {out_dir}")

        max_bytes = args.max_mb * 1_000_000 if args.max_mb > 0 else float("inf")
        dl = Downloader(ctx, ctx.new_page(), args.force, max_bytes, args.include_software)
        current = None
        for num, i, section, item in numbered:
            if selected and num not in selected:
                continue
            if section != current:
                print(f"\n{section}")
                current = section
            dl.handle(section, item, out_dir / f"{i:02d} {safe_name(section, 60)}")

        # INDEX.md describes the whole course, so only a full run rewrites it;
        # a partial run would otherwise wipe the entries it didn't touch.
        if not selected:
            write_index(out_dir, title, args.course_url, dl.log)
        browser.close()

    failed = [entry for entry in dl.log if entry[2] == "FAILED"]
    where = f"See {out_dir / 'INDEX.md'}" if not selected else "(partial run: INDEX.md left as it was)"
    print(f"\nDone. {len(dl.log)} items, {len(failed)} failed. {where}")


def print_list(numbered):
    current = None
    for num, _, section, item in numbered:
        if section != current:
            print(f"\n{section}")
            current = section
        print(f"  {num:3d}. [{item['mod']}] {item['name']}")


def parse_selection(text):
    """'3,7-9' -> {3, 7, 8, 9}. Empty text -> None, meaning everything."""
    nums = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if not re.fullmatch(r"\d+(-\d+)?", part):
            sys.exit(f"Can't read '{part}': use numbers like 3,7-9")
        start, _, end = part.partition("-")
        nums.update(range(int(start), int(end or start) + 1))
    return nums or None


if __name__ == "__main__":
    main()
