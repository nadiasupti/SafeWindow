"""Help a native speaker review a draft translation, and record that they did.

`export_rows` makes a side-by-side sheet (English | current | corrected). `apply_corrections` takes the sheet back,
refuses any correction whose {placeholders} differ from English (that would crash the app in that language),
and records the reviewer. The "draft" label is removed only when the reviewer approves.
"""
from __future__ import annotations

import re
from datetime import date
from string import Formatter

# settings and metadata, not sentences a reviewer reads
SKIP = {"language_name", "name_column", "digits", "months", "date_format", "dir", "draft", "review"}
# non-English texts may use these extra placeholders that the code supplies (English simply leaves them out)
EXTRA_ALLOWED = {"sms_template": {"shelter"}, "sms_route": {"shelter"}}
_ITEM = re.compile(r"^(?P<key>[^\[]+)\[(?P<i>\d+)\]$")


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def flatten(data: dict) -> dict[str, str]:
    """{key: text} with list items as key[0], key[1] ... Settings and metadata are left out."""
    out = {}
    for key, value in data.items():
        if key in SKIP:
            continue
        if isinstance(value, list):
            out.update({f"{key}[{i}]": item for i, item in enumerate(value)})
        elif isinstance(value, str):
            out[key] = value
    return out


def export_rows(english: dict, current: dict) -> list[dict]:
    en, cur = flatten(english), flatten(current)
    return [{"key": k, "english": v, "current": cur.get(k, ""), "corrected": "", "comment": ""} for k, v in en.items()]


def check(key: str, text: str, english: dict, lang: str) -> str | None:
    """None if `text` may replace `key`, otherwise the reason it may not."""
    en = flatten(english)
    if key not in en:
        return f"{key}: not a reviewable key"
    want, got = placeholders(en[key]), placeholders(text)
    base = key.split("[")[0]
    allowed = EXTRA_ALLOWED.get(base, set()) if lang != "en" else set()
    if base in EXTRA_ALLOWED and lang != "en":
        ok = got <= (want | allowed)
    else:
        ok = got == want
    if not ok:
        return f"{key}: placeholders {sorted(got)} do not match English {sorted(want)}"
    return None


def apply_corrections(current: dict, english: dict, rows: list[dict], lang: str, reviewer: str = "",
                      affiliation: str = "", approve: bool = False, today: str | None = None) -> tuple[dict, list[str], int]:
    """Returns (new locale, problems, corrections applied). If there are any problems nothing is changed."""
    if approve and not (reviewer.strip() and affiliation.strip()):
        return current, ["approving needs a reviewer name and affiliation"], 0
    new = {k: (list(v) if isinstance(v, list) else v) for k, v in current.items()}
    problems, applied = [], 0
    for row in rows:
        text = (row.get("corrected") or "").strip()
        if not text:
            continue
        key = row["key"].strip()
        problem = check(key, text, english, lang)
        if problem:
            problems.append(problem)
            continue
        m = _ITEM.match(key)
        if m:
            new[m["key"]][int(m["i"])] = text
        else:
            new[key] = text
        applied += 1
    if problems:
        return current, problems, 0
    if reviewer.strip():
        new["review"] = {"reviewer": reviewer.strip(), "affiliation": affiliation.strip(),
                         "date": today or date.today().isoformat(), "corrections": applied, "approved": bool(approve)}
    if approve:
        new["draft"] = False
    return new, [], applied
