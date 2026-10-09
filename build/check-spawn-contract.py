#!/usr/bin/env python3
"""
check-spawn-contract.py — validator for the spawn-contract dispatch format
(choreography/subagent-fleet-runbook.md §2, templates/contracts/spawn-contract.md.tmpl).

Dependency-free: Python 3 stdlib only, zero network. Parses the same
line-oriented contract format as check-artifact-contract.py and enforces:

  1. required fields present + non-empty
  2. refuse-to-spawn: any required value empty/TBD/TODO/unsubstituted {TOKEN} -> reject
  3. stability enum enforced (STABLE | DRAFT)
  4. deliverable_path / resume_from are repo-relative (never absolute, never "context memory")
  5. handoff_brief sub-fields present (context + next required non-empty; lists may be empty)
  6. unknown fields fail (catches typos)

USAGE
  python3 build/check-spawn-contract.py <contract.yaml>   # validate a file
  python3 build/check-spawn-contract.py --self-test       # pass/fail tests
  python3 build/check-spawn-contract.py --example-check   # repo examples

EXIT  0 = valid (all tests pass)   1 = invalid (violations listed with fields)
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCALAR_REQUIRED = ["contract_version", "role_id", "entry_gate",
                   "deliverable_path", "verification_bar",
                   "restart_budget", "timeout", "resume_from", "stability"]
DICT_FIELDS = ["handoff_brief"]
BRIEF_SCALARS_REQUIRED = ["context", "next"]
BRIEF_LISTS = ["locked_decisions", "assumptions", "done", "open"]

STABILITY_ENUM = {"STABLE", "DRAFT"}
REFUSE_TOKENS = {"TBD", "TODO", "TBC", "..."}
TOKEN_RE = re.compile(r"\{[A-Z_0-9]+\}")

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
_TRAILING_COMMENT_RE = re.compile(r"\s+#.*$")


def strip_comment(value):
    if value.lstrip().startswith("#"):
        return ""
    return _TRAILING_COMMENT_RE.sub("", value).strip()


def parse_contract(text):
    """Contract text -> (scalars, lists, dicts, parse_errors)."""
    scalars, lists, dicts, errors = {}, {}, {}, []
    cur_list = None
    cur_dict = None
    item = None

    def close_item():
        nonlocal item
        if item is not None:
            lists[cur_list].append(item)
            item = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = stripped

        if indent == 0:
            close_item()
            cur_list = cur_dict = None
            m = _KEY_RE.match(body)
            if not m:
                errors.append(f"line {lineno}: not a field: '{body[:40]}'")
                continue
            key, val = m.group(1), strip_comment(m.group(2))
            if key in scalars or key in lists or key in dicts:
                errors.append(f"line {lineno}: duplicate field '{key}'")
                continue
            if val == "[]":
                lists[key] = []
            elif val == "":
                if key in DICT_FIELDS:
                    cur_dict = key
                    dicts[key] = {}
                else:
                    cur_list = key
                    lists.setdefault(key, [])
            else:
                scalars[key] = val
            continue

        if body.startswith("- "):
            if cur_dict is not None and cur_list is None:
                # list item inside handoff_brief: "  key:\n    - item"
                # find the most recent list-typed sub-key: last key set with empty value
                errors.append(f"line {lineno}: list item outside a list section")
                continue
            if cur_list is None:
                errors.append(f"line {lineno}: list item outside a list section")
                continue
            close_item()
            rest = body[2:].strip()
            m = _KEY_RE.match(rest)
            if m:
                item = {m.group(1): strip_comment(m.group(2))}
            elif rest.endswith(":"):
                item = {rest[:-1].strip(): ""}
            elif rest:
                lists[cur_list].append(strip_comment(rest))
            else:
                errors.append(f"line {lineno}: empty list item")
            continue

        m = _KEY_RE.match(body)
        if m and (item is not None or cur_dict is not None):
            key, val = m.group(1), strip_comment(m.group(2))
            if item is not None:
                if key in item and item[key]:
                    errors.append(f"line {lineno}: duplicate field '{key}'")
                else:
                    item[key] = val
            else:
                target = dicts[cur_dict]
                if val == "[]" or val == "":
                    # sub-list inside handoff_brief; collect following "- " items
                    # by treating "brief.<key>" as the active list
                    lists["brief." + key] = [] if val == "[]" else None
                    target[key] = val
                    if val == "":
                        cur_list = "brief." + key
                        lists[cur_list] = []
                else:
                    target[key] = val
            continue
        if item is not None and not m:
            k = list(item)[-1]
            item[k] = (item[k] + " " + stripped).strip()
            continue
        errors.append(f"line {lineno}: misplaced line: '{body[:40]}'")

    close_item()
    # drop placeholder Nones for empty sub-lists that never got items
    for k in [k for k, v in lists.items() if v is None]:
        lists[k] = []
    return scalars, lists, dicts, errors


def _is_refused(value):
    v = (value or "").strip().strip("'\"")
    if not v:
        return True
    if v.upper() in REFUSE_TOKENS:
        return True
    if TOKEN_RE.search(v):
        return True
    return False


def validate(scalars, lists, dicts):
    """Return a list of violation strings (empty = valid)."""
    v = []

    # 1. required scalars present + non-empty
    for key in SCALAR_REQUIRED:
        if key not in scalars or not scalars[key]:
            v.append(f"MISSING REQUIRED FIELD: '{key}' is absent or empty")

    # 2. refuse-to-spawn
    for key in SCALAR_REQUIRED:
        if key in scalars and _is_refused(scalars[key]):
            v.append(f"REFUSE-TO-SPAWN: '{key}' is empty/TBD/unsubstituted "
                     f"(got '{scalars[key]}')")

    # 3. stability enum
    if "stability" in scalars and scalars["stability"]:
        if scalars["stability"].upper() not in STABILITY_ENUM:
            v.append(f"ILLEGAL ENUM: stability='{scalars['stability']}' "
                     f"(want STABLE | DRAFT)")

    # 4. paths are repo-relative; resume is durable, never memory
    for key in ("deliverable_path", "resume_from"):
        if key in scalars and scalars[key] and not _is_refused(scalars[key]):
            p = scalars[key].strip().strip("'\"")
            if os.path.isabs(p) or p.startswith("~"):
                v.append(f"ABSOLUTE PATH: '{key}' must be repo-relative "
                         f"(got '{p}')")
    if "resume_from" in scalars and scalars["resume_from"]:
        rm = scalars["resume_from"].lower()
        if "memory" in rm or "context" in rm:
            v.append("RESUME-FROM-MEMORY: 'resume_from' must be a durable "
                     "artifact path, never context memory")

    # 5. handoff_brief present with required sub-fields
    if "handoff_brief" not in dicts:
        v.append("MISSING REQUIRED FIELD: 'handoff_brief' mapping is absent")
    else:
        brief = dicts["handoff_brief"]
        for key in BRIEF_SCALARS_REQUIRED:
            if key not in brief or _is_refused(brief.get(key, "")):
                v.append(f"REFUSE-TO-SPAWN: 'handoff_brief.{key}' is "
                         f"absent/empty/TBD")
        for key in BRIEF_LISTS:
            lkey = "brief." + key
            if key in brief and brief[key] not in ("", "[]"):
                v.append(f"MISPLACED: 'handoff_brief.{key}' must be a list "
                         f"(use [] when empty)")
            elif lkey not in lists:
                v.append(f"MISSING REQUIRED FIELD: 'handoff_brief.{key}' "
                         f"list is absent")

    # 6. unknown top-level keys fail
    known = set(SCALAR_REQUIRED) | set(DICT_FIELDS)
    for key in list(scalars) + list(lists) + list(dicts):
        if key.startswith("brief."):
            continue
        if key not in known:
            v.append(f"UNKNOWN FIELD: '{key}' (typo? check the template)")

    return v


def check_text(text):
    scalars, lists, dicts, errors = parse_contract(text)
    return errors + validate(scalars, lists, dicts)


def check_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return check_text(fh.read())
    except OSError as e:
        return [f"UNREADABLE: {e}"]


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
VALID_CONTRACT = """\
contract_version: 1
role_id: RESEARCHER-001
entry_gate: build-passed
deliverable_path: reports/summary.md
verification_bar: python3 tools/render.py --check
restart_budget: 3/5min
timeout: 10m
resume_from: reports/summary.md
stability: DRAFT
handoff_brief:
  context: summarize the build output for review
  locked_decisions: []
  assumptions: []
  done: []
  next: draft the summary section
  open: []
"""


def _with(text, drop=None, subs=()):
    if drop:
        lines, out, skipping = text.splitlines(), [], False
        for ln in lines:
            if re.match(rf"^{re.escape(drop)}\b", ln):
                skipping = True
                continue
            if skipping and (not ln.strip() or ln.startswith((" ", "\t"))):
                continue
            skipping = False
            out.append(ln)
        text = "\n".join(out) + "\n"
    for old, new in subs:
        text = text.replace(old, new, 1)
    return text


def self_test():
    cases = []

    v = check_text(VALID_CONTRACT)
    cases.append(("valid contract passes", v == [], v))

    v = check_text(_with(VALID_CONTRACT, drop="resume_from"))
    cases.append(("missing required field (resume_from) fails",
                  any("resume_from" in x for x in v), v))

    v = check_text(_with(VALID_CONTRACT,
                         subs=[("role_id: RESEARCHER-001", "role_id: TBD")]))
    cases.append(("TBD role_id refused (no dispatch)",
                  any("REFUSE-TO-SPAWN" in x for x in v), v))

    v = check_text(_with(VALID_CONTRACT,
                         subs=[("stability: DRAFT", "stability: FINAL")]))
    cases.append(("illegal stability enum fails",
                  any("ILLEGAL ENUM" in x for x in v), v))

    v = check_text(_with(VALID_CONTRACT,
                         subs=[("deliverable_path: reports/summary.md",
                                "deliverable_path: /tmp/summary.md")]))
    cases.append(("absolute deliverable path fails",
                  any("ABSOLUTE PATH" in x for x in v), v))

    v = check_text(_with(VALID_CONTRACT,
                         subs=[("resume_from: reports/summary.md",
                                "resume_from: context memory")]))
    cases.append(("resume-from-memory fails",
                  any("RESUME-FROM-MEMORY" in x for x in v), v))

    v = check_text(VALID_CONTRACT + "typo_field: oops\n")
    cases.append(("unknown field fails",
                  any("UNKNOWN FIELD" in x for x in v), v))

    failed = 0
    for name, ok, detail in cases:
        print(("PASS" if ok else "FAIL") + f": {name}")
        if not ok:
            failed += 1
            for d in detail:
                print(f"    {d}")
    print(f"check-spawn-contract — self-test: "
          f"{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


def example_check():
    failed = 0
    for path, want_valid in (
            (os.path.join(ROOT, "examples", "spawn-contract.valid.yaml"), True),
            (os.path.join(ROOT, "examples", "spawn-contract.invalid.yaml"), False)):
        violations = check_file(path)
        ok = (violations == []) == want_valid
        print(("PASS" if ok else "FAIL") +
              f": {path} -> {'valid' if want_valid else 'invalid'}")
        if not ok:
            failed += 1
            for d in violations:
                print(f"    {d}")
    return 1 if failed else 0


def main(argv):
    if "--self-test" in argv:
        print("check-spawn-contract — self-test")
        return self_test()
    if "--example-check" in argv:
        print("check-spawn-contract — example-check")
        return example_check()
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip().splitlines()[0])
        print("usage: check-spawn-contract.py <contract.yaml> | --self-test | --example-check")
        return 2
    failed = 0
    for path in argv:
        violations = check_file(path)
        if violations:
            print(f"INVALID: {path}")
            for d in violations:
                print(f"  - {d}")
            failed += 1
        else:
            print(f"VALID: {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
