"""Wires the Telegram alert into app/api/routes/bookings.py by exact-text edits.

Use this instead of the bookings.py part of the patch when `git apply` rejects it
(the file differs slightly from the one the patch was made against).

    python hook_telegram_into_bookings.py            # run from the repo root
    python hook_telegram_into_bookings.py --check    # report only, change nothing

Every edit is checked first. If any expected line is missing, nothing is written.
Safe to run twice. Line endings (LF or CRLF) are preserved.
"""
import re
import sys
from pathlib import Path

PATH = Path("app/api/routes/bookings.py")

# (name, pattern, replacement, expected match count, already-done marker)
EDITS = [
    ("import BackgroundTasks",
     r"from fastapi import APIRouter, Form, Request\b",
     "from fastapi import APIRouter, BackgroundTasks, Form, Request", 1, "BackgroundTasks, Form"),
    ("import notify",
     r"^(from app\.services import bookings as service)[ \t]*$",
     r"\1\nfrom app.services import notify", 1, "from app.services import notify"),
    ("_handle signature",
     r"def _handle\(request: Request, website: str,",
     "def _handle(request: Request, background: BackgroundTasks, website: str,", 1, "def _handle(request: Request, background"),
    ("queue the alert after save",
     r"^([ \t]*)(return JSONResponse\(\{\"ok\": True, \"reference\": booking\.reference\}, status_code=201\))",
     r"\1background.add_task(notify.notify_new_booking, booking)  # runs after the response is sent\n\1\2", 1,
     "notify.notify_new_booking"),
    ("car route takes BackgroundTasks",
     r"request: Request, car: str = Form",
     "request: Request, background: BackgroundTasks, car: str = Form", 1, "background: BackgroundTasks, car:"),
    ("tour route takes BackgroundTasks",
     r"request: Request, tour: str = Form",
     "request: Request, background: BackgroundTasks, tour: str = Form", 1, "background: BackgroundTasks, tour:"),
    ("routes pass it to _handle",
     r"return _handle\(request, website,",
     "return _handle(request, background, website,", 2, "_handle(request, background, website"),
]


def main() -> int:
    check_only = "--check" in sys.argv
    if not PATH.exists():
        print(f"{PATH} not found. Run this from the repo root.")
        return 1
    raw = PATH.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    problems, todo = [], []
    for name, pattern, repl, count, done_marker in EDITS:
        found = len(re.findall(pattern, text, flags=re.M))
        if done_marker in text:
            print(f"  already done: {name}")
        elif found == count:
            todo.append((name, pattern, repl))
        else:
            problems.append(f"  CANNOT APPLY: {name} (expected {count} match(es), found {found})")
    if problems:
        print("\n".join(problems))
        print("Nothing was changed. Send me the top 20 lines of bookings.py and the two route functions.")
        return 1
    for name, pattern, repl in todo:
        text = re.sub(pattern, repl, text, flags=re.M)
        print(f"  {'would apply' if check_only else 'applied'}: {name}")
    if todo and not check_only:
        PATH.write_bytes(text.replace("\n", eol).encode("utf-8"))
    print("Done." if todo else "Nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
