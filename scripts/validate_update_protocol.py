from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS_PATH = ROOT / "UPDATE_IDS.json"
LOG_PATH = ROOT / "UPDATE_LOG.md"
STATE_PATH = ROOT / "PROJECT_STATE.json"
VERSION_PATH = ROOT / "VERSION"

CHANGE_LINE = re.compile(
    r"^- (CHG-\d{4}) / (ARCH|FEAT|BUG|FIX|IMP)-(\d{4})(?: -> (BUG-\d{4}))? — ",
    re.MULTILINE,
)
VERSION_HEADING = re.compile(r"^##\s+v(\d+\.\d+\.\d+)\s*$", re.MULTILINE)
STATUS_PATTERN = re.compile(r"^Статус:\s*(\S+)\s*$", re.MULTILINE)


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    log = LOG_PATH.read_text(encoding="utf-8")
    release_version = VERSION_PATH.read_text(encoding="utf-8").strip()

    changes = CHANGE_LINE.findall(log)
    if not changes:
        fail("UPDATE_LOG.md contains no registered changes")

    primary_ids: list[str] = []
    declared_by_prefix: dict[str, list[int]] = {
        "CHG": [],
        "FEAT": [],
        "BUG": [],
        "FIX": [],
        "IMP": [],
        "ARCH": [],
    }
    bug_ids: set[str] = set()
    fix_refs: list[tuple[str, str]] = []

    for chg_id, kind, number_text, bug_ref in changes:
        typed_id = f"{kind}-{number_text}"
        primary_ids.extend([chg_id, typed_id])
        declared_by_prefix["CHG"].append(int(chg_id.split("-")[1]))
        declared_by_prefix[kind].append(int(number_text))
        if kind == "BUG":
            bug_ids.add(typed_id)
        if kind == "FIX":
            if not bug_ref:
                fail(f"{typed_id} has no BUG reference")
            fix_refs.append((typed_id, bug_ref))

    duplicates = sorted(
        identifier
        for identifier in set(primary_ids)
        if primary_ids.count(identifier) > 1
    )
    if duplicates:
        fail(f"Duplicate primary IDs in UPDATE_LOG.md: {duplicates}")

    for fix_id, bug_id in fix_refs:
        if bug_id not in bug_ids:
            fail(f"{fix_id} references missing {bug_id}")

    for prefix, last in ids["last_assigned"].items():
        actual_max = max(declared_by_prefix[prefix], default=0)
        if actual_max != int(last):
            fail(f"Counter mismatch for {prefix}: registry={last}, journal={actual_max}")
        expected_next = f"{prefix}-{int(last) + 1:04d}"
        if ids["next"].get(prefix) != expected_next:
            fail(f"Next ID mismatch for {prefix}: expected {expected_next}")

    sections = re.split(
        r"(?=^##\s+v\d+\.\d+\.\d+\s*$)",
        log,
        flags=re.MULTILINE,
    )
    completed_versions: list[str] = []
    in_progress_versions: list[str] = []

    for section in sections:
        match = VERSION_HEADING.search(section)
        if not match:
            continue
        version = match.group(1)
        status_match = STATUS_PATTERN.search(section)
        if not status_match:
            fail(f"Missing status for v{version}")
        status = status_match.group(1)
        if "next_action:" not in section:
            fail(f"Missing next_action for v{version}")
        if status == "completed":
            completed_versions.append(version)
        elif status == "in_progress":
            in_progress_versions.append(version)

    if not completed_versions:
        fail("No completed version in UPDATE_LOG.md")

    latest_completed = completed_versions[-1]
    if release_version != latest_completed:
        fail(
            f"VERSION={release_version}; latest completed journal version={latest_completed}"
        )

    if state.get("version") != release_version:
        fail("PROJECT_STATE version does not match VERSION")

    if in_progress_versions:
        active = ids.get("active_development", {}).get("version")
        expected = f"v{in_progress_versions[-1]}"
        if active != expected:
            fail(f"active_development={active}; expected {expected}")

    if not str(state.get("next_action", "")).strip():
        fail("PROJECT_STATE next_action is empty")

    print("Update protocol validation: PASS")
    print(f"Release version: v{release_version}")
    if in_progress_versions:
        print(f"Development version: v{in_progress_versions[-1]}")
    for prefix in ("CHG", "FEAT", "BUG", "FIX", "IMP", "ARCH"):
        print(f"{prefix}: last={ids['last_assigned'][prefix]} next={ids['next'][prefix]}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"Update protocol validation: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
