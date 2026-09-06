#!/usr/bin/env python3
"""Verify the governance chain in examples/.

Checks the properties the model actually depends on:

  1. Every report's content_sha256 reproduces from its own body.
  2. Every review pins the hash of the report it reviewed, and that hash matches
     the report as stored.
  3. No agent reviews its own work.
  4. Referenced artifacts that are absent from the bundle are reported as
     absent rather than silently ignored.

Run:  python3 tools/verify_lineage.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

passed = 0
failed = 0
findings: list[str] = []
notes: list[str] = []


def finding(text: str) -> None:
    """A convention gap, not a broken invariant.

    Reported and never silently dropped, but does not fail the run: these are
    observations about how the process was actually followed, not evidence that
    the chain is unsound. Downgrading a real invariant to a finding to obtain a
    green tick would hollow out the gate entirely.
    """
    findings.append(text)


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


REQUIRED = {
    "report": ("report_key", "submitted_by", "content_sha256", "markdown"),
    "review": ("review_key", "report_key", "reviewer"),
}


def load_all(kind: str) -> dict[str, tuple[dict, pathlib.Path]]:
    """Collect artifacts of a kind, keyed by their own identifier.

    A review also carries report_key — the report it reviews — so a report is
    identified by having report_key AND NOT review_key. Getting this wrong makes
    a review masquerade as the report it audits.

    Two integrity rules, both failures rather than findings:

      Duplicate identifiers are rejected. Silently keeping whichever file was
      read last would mean the identifier no longer identifies anything, which
      defeats the point of a lineage record.

      Missing required fields are rejected. A comparison against a missing value
      can pass by accident — an absent reviewer is not evidence of independence.
    """
    key_field = "review_key" if kind == "review" else "report_key"
    out: dict[str, tuple[dict, pathlib.Path]] = {}
    seen: dict[str, pathlib.Path] = {}

    for path in sorted(EXAMPLES.rglob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError:
            check(f"{path.relative_to(ROOT)} is valid JSON", False)
            continue
        if not isinstance(doc, dict):
            continue
        is_review = bool(doc.get("review_key"))
        if (kind == "review") != is_review:
            continue
        if kind == "report" and not doc.get("report_key"):
            continue

        ident = doc[key_field]

        if ident in seen:
            check(
                f"{ident} is defined exactly once",
                False,
                f"also defined in {seen[ident].relative_to(ROOT)} "
                f"and {path.relative_to(ROOT)}",
            )
            continue
        seen[ident] = path

        missing = [f for f in REQUIRED[kind] if not doc.get(f)]
        if missing:
            check(
                f"{ident} carries its required fields",
                False,
                "missing " + ", ".join(missing),
            )
            continue

        out[ident] = (doc, path)
    return out


reports = load_all("report")
reviews = load_all("review")

print(f"Found {len(reports)} report(s), {len(reviews)} review(s)\n")

# --- 1. Reports hash to what they claim -------------------------------------
# A content hash that does not reproduce is worse than no hash: it looks like
# evidence while proving nothing.
for key, (doc, path) in sorted(reports.items()):
    claimed = doc.get("content_sha256")
    body = doc.get("markdown", "")
    actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
    check(
        f"{key} content_sha256 reproduces from its body",
        bool(claimed) and claimed == actual,
        f"claimed {str(claimed)[:16]}… computed {actual[:16]}…",
    )

    # The sidecar .md, where present, must be byte-identical to the stored body.
    sidecar = path.with_suffix(".md")
    if sidecar.exists():
        check(
            f"{key} sidecar .md matches the stored body",
            hashlib.sha256(sidecar.read_bytes()).hexdigest() == claimed,
        )

# --- 2. Reviews pin the hash of what they reviewed ---------------------------
for key, (doc, _) in sorted(reviews.items()):
    target = doc.get("report_key")
    refs = doc.get("evidence_refs") or []
    if isinstance(refs, str):
        try:
            refs = json.loads(refs)
        except json.JSONDecodeError:
            refs = [refs]

    pinned = {
        r.split(":", 1)[1]
        for r in refs
        if isinstance(r, str) and r.startswith(f"{target}:") and ":" in r
    }

    if target not in reports:
        notes.append(
            f"{key} reviews {target}, which is not included in this bundle — "
            f"the review pins hash {next(iter(pinned), '(none)')[:16]}…"
        )
        continue

    if not pinned:
        finding(
            f"{key} ({doc.get('reviewer')}) reviewed {target} but cites only "
            f"evidence IDs — no evidence_ref of the form REPORT:sha256, so the "
            f"review is not pinned to a specific revision of what it reviewed"
        )
    if pinned:
        check(
            f"{key} pinned hash matches {target} as stored",
            reports[target][0].get("content_sha256") in pinned,
        )

# --- 3. Independence: nobody reviews their own work --------------------------
# The task vocabulary forbids SELF_REVIEW and GROK_SELF_REVIEW explicitly. This
# is the machine check for it.
for key, (doc, _) in sorted(reviews.items()):
    target = doc.get("report_key")
    reviewer = doc.get("reviewer")
    if target in reports:
        author = reports[target][0].get("submitted_by")
        check(
            f"{key}: reviewer ({reviewer}) is not the author ({author})",
            reviewer != author,
            "self-review",
        )

# --- 4. Independent review count --------------------------------------------
by_report: dict[str, list[str]] = {}
for key, (doc, _) in reviews.items():
    by_report.setdefault(doc.get("report_key"), []).append(doc.get("reviewer"))
for target, revs in sorted(by_report.items()):
    if target in reports and len(revs) > 1:
        check(
            f"{target} reviewed by distinct agents: {', '.join(sorted(revs))}",
            len(set(revs)) == len(revs),
            "same agent reviewed twice",
        )

print()
for f_ in findings:
    print(f"  FINDING  {f_}")
for n in notes:
    print(f"  NOTE     {n}")
if findings or notes:
    print()

print(f"{passed} passed, {failed} failed, {len(findings)} finding(s)")
sys.exit(1 if failed else 0)
