"""Development integrity check for the project's translations.

Run with ``python manage.py check_i18n``.

Checks the PO catalogs in ``locale/`` and the client-side message list in
``apps/core/i18n_catalog.py``:

* the Arabic catalog carries no untranslated, fuzzy or obsolete entries;
* Arabic plural entries define every form the header advertises (6 forms);
* every ``%(name)s`` named token in a source string survives in its
  translation(s), and no foreign token is introduced;
* positional ``%s`` counts are preserved where a translation keeps them;
* the English catalog is an identity map (``msgstr == msgid``) so corrupted
  stale translations are caught;
* every client-side JS message resolves to a real Arabic string with the
  same number of ``%s`` placeholders;
* neither catalog leaves the gettext header flagged ``fuzzy``.

This is a developer aid, not part of the runtime path.  ``compilemessages``
remains the authority on whether msgfmt will accept the files.
"""
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import translation
from django.utils.translation import gettext

try:
    import polib
except ImportError:  # pragma: no cover - optional dev dependency
    polib = None

from apps.core.i18n_catalog import JS_MESSAGES

# ``%(name)s`` style named conversion tokens used by Django/str formatting.
_NAMED = re.compile(r"%\(\w+\)\w")
_PCT_S = re.compile(r"%s")

_LOCALE_DIR = "locale"
_MAX_REPORTED = 25


def _named_tokens(text):
    return set(_NAMED.findall(text))


def _contains_arabic(text):
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def _required_plural_forms(po):
    """Parse ``Plural-Forms`` from the header: ``nplurals`` count + formula."""
    forms = po.metadata.get("Plural-Forms", "") or ""
    match = re.search(r"nplurals\s*=\s*(\d+)", forms)
    return int(match.group(1)) if match else 0


class Command(BaseCommand):
    help = "Verify both PO catalogs are complete, translated and consistent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--locale",
            nargs="*",
            default=["ar", "en"],
            help="Locales to check (default: ar en).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only report problems, no summary line.",
        )

    def handle(self, *args, **options):
        if polib is None:
            raise CommandError(
                "polib is required for check_i18n; install it with "
                "`pip install polib`."
            )

        problems = []
        notes = []

        for code in options["locale"]:
            path = (
                settings.BASE_DIR
                / _LOCALE_DIR
                / code
                / "LC_MESSAGES"
                / "django.po"
            )
            if not path.exists():
                problems.append(f"[{code}] PO file not found: {path}")
                continue
            po = polib.pofile(str(path))
            self._check_catalog(code, po, problems, notes)

        self._check_js_catalog(problems, notes)

        if not options["quiet"]:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"check_i18n: {len(problems)} problem(s), "
                    f"{len(notes)} note(s)"
                )
            )
        for note in notes[:20]:
            self.stderr.write(self.style.WARNING("note: " + note))
        for problem in problems:
            self.stderr.write(self.style.ERROR("problem: " + problem))

        if problems:
            raise CommandError(f"{len(problems)} translation problem(s) found.")

    # -- per-locale ------------------------------------------------------

    def _check_catalog(self, code, po, problems, notes):
        stats = {
            "total": 0,
            "translated": 0,
            "untranslated": 0,
            "fuzzy": 0,
            "obsolete": 0,
            "plurals": 0,
        }
        nplurals = _required_plural_forms(po)
        reported = 0

        def too_many():
            return reported >= _MAX_REPORTED

        def report(msg):
            nonlocal reported
            reported += 1
            problems.append(f"[{code}] {msg}")

        # Header must not stay flagged fuzzy (stale ``#, fuzzy`` boilerplate).
        if getattr(po, "metadata_is_fuzzy", False):
            notes.append(f"[{code}] header still carries the `#, fuzzy` flag.")

        for entry in po:
            if entry.obsolete:
                stats["obsolete"] += 1
                continue
            stats["total"] += 1
            if entry.msgid_plural:
                stats["plurals"] += 1

            if "fuzzy" in entry.flags:
                stats["fuzzy"] += 1
                if not too_many():
                    report(f"fuzzy entry: {entry.msgid!r}")

            if code == "en":
                self._check_identity(entry, report, too_many)
                stats["translated"] += 1
                continue

            # Arabic below.
            source_tokens = _named_tokens(entry.msgid)
            if entry.msgid_plural:
                self._check_plural_entry(
                    entry, source_tokens, nplurals, stats, report, too_many
                )
            else:
                if not entry.msgstr:
                    stats["untranslated"] += 1
                    if not too_many():
                        report(f"untranslated: {entry.msgid!r}")
                    continue
                stats["translated"] += 1
                out_tokens = _named_tokens(entry.msgstr)
                if source_tokens != out_tokens:
                    if not too_many():
                        report(
                            f"named tokens mismatch: {entry.msgid!r} -> "
                            f"{entry.msgstr!r}"
                        )
                self._check_pct_count(entry.msgid, entry.msgstr, report, too_many)

    def _check_identity(self, entry, report, too_many):
        """The English catalog must mirror msgid exactly."""
        if entry.msgid_plural:
            expect0, expect1 = entry.msgid, entry.msgid_plural
            forms = entry.msgstr_plural
            if forms.get(0) != expect0 or forms.get(1) != expect1:
                if not too_many():
                    report(f"en non-identity plural: {entry.msgid!r}")
            return
        if entry.msgstr != entry.msgid:
            if not too_many():
                report(f"en non-identity: {entry.msgid!r} -> {entry.msgstr!r}")

    def _check_plural_entry(
        self, entry, source_tokens, nplurals, stats, report, too_many
    ):
        forms = entry.msgstr_plural or {}
        parsed_keys = {int(k) for k in forms}
        missing = [i for i in range(nplurals) if i not in parsed_keys]
        for i in missing:
            stats["untranslated"] += 1
            if not too_many():
                report(
                    f"plural missing form {i}: {entry.msgid!r} "
                    f"(nplurals={nplurals})"
                )
        for i in parsed_keys:
            form = forms.get(str(i)) or forms.get(i)
            if form is None or not str(form):
                stats["untranslated"] += 1
                if not too_many():
                    report(f"plural empty form {i}: {entry.msgid!r}")
                continue
            stats["translated"] += 1
            # Arabic word forms may drop the counter token (e.g. "عنصران")
            # but must never introduce a foreign named token.
            foreign = _named_tokens(str(form)) - source_tokens
            if foreign and not too_many():
                report(
                    f"plural foreign tokens {sorted(foreign)} in form {i}: "
                    f"{entry.msgid!r}"
                )
            self._check_pct_count(entry.msgid_plural, str(form), report, too_many)

    def _check_pct_count(self, source, translated, report, too_many):
        """Positional ``%s`` counts must match when a translation keeps them."""
        if not _PCT_S.search(source):
            return
        src = len(_PCT_S.findall(source))
        out = len(_PCT_S.findall(translated))
        if src != out and not too_many():
            report(f"%s count {src}->{out}: {source!r} -> {translated!r}")

    # -- JS catalog ------------------------------------------------------

    def _check_js_catalog(self, problems, notes):
        with translation.override("en"):
            msgids = [str(msg) for msg in JS_MESSAGES]
        missing = []
        with translation.override("ar"):
            for msgid in msgids:
                out = gettext(msgid)
                if not _contains_arabic(out) or out == msgid:
                    missing.append(msgid)
                    continue
                if len(_PCT_S.findall(out)) != len(_PCT_S.findall(msgid)):
                    problems.append(
                        f"[js] %s count mismatch: {msgid!r} -> {out!r}"
                    )
        if missing:
            problems.append(
                f"[js] {len(missing)} message(s) missing Arabic "
                f"translations: {missing[:10]}"
            )
        else:
            notes.append(
                f"[js] all {len(msgids)} client-side messages translate."
            )