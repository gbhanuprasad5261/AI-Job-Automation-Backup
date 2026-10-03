"""Small, non-invasive JSONL diagnostics for controlled runtime checks."""

from datetime import datetime, timezone
import json
import os
from execution_policy import EXECUTION_POLICY


DIAGNOSTIC_FILE = os.path.join("screenshots", "phase7g_diagnostics.jsonl")


def _read_attribute(element, name):
    try:
        return element.get_attribute(name) or ""
    except Exception:
        return ""


def _read_text(element, limit=240):
    try:
        value = " ".join((element.inner_text() or "").split())
        return value[:limit]
    except Exception:
        return ""


def element_diagnostic(element, text_limit=240):
    """Return concise DOM metadata; absent or unreadable fields stay empty."""
    try:
        tag = element.evaluate("el => el.tagName.toLowerCase()") or ""
    except Exception:
        tag = ""

    return {
        "tag": tag,
        "href": _read_attribute(element, "href"),
        "aria_label": _read_attribute(element, "aria-label"),
        "title": _read_attribute(element, "title"),
        "class": _read_attribute(element, "class"),
        "id": _read_attribute(element, "id"),
        "role": _read_attribute(element, "role"),
        "aria_modal": _read_attribute(element, "aria-modal"),
        "text_preview": _read_text(element, text_limit),
    }


def page_diagnostic(page, include_page_count=False):
    result = {}
    try:
        result["url"] = page.url or ""
    except Exception:
        result["url"] = ""
    try:
        result["title"] = page.title() or ""
    except Exception:
        result["title"] = ""
    if include_page_count:
        try:
            result["page_count"] = len(page.context.pages)
        except Exception:
            result["page_count"] = None
    return result


def selector_diagnostics(page, selectors, candidates_per_selector=4):
    """Count selector matches/visible matches and preview visible candidates."""
    results = []
    for selector in selectors:
        item = {
            "selector": selector,
            "match_count": None,
            "visible_match_count": 0,
            "candidates": [],
        }
        try:
            locator = page.locator(selector)
            item["match_count"] = locator.count()
            for index in range(item["match_count"]):
                element = locator.nth(index)
                try:
                    visible = element.is_visible()
                except Exception:
                    visible = False
                if not visible:
                    continue
                item["visible_match_count"] += 1
                if len(item["candidates"]) < candidates_per_selector:
                    item["candidates"].append(element_diagnostic(element))
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"[:240]
        results.append(item)
    return results


OVERLAY_DIAGNOSTIC_SELECTORS = (
    '[role="alert"]',
    '[role="dialog"]',
    '[aria-modal="true"]',
    '[id*="alert" i]',
    '[class*="alert" i]',
    '[id*="overlay" i]',
    '[class*="overlay" i]',
    '[id*="modal" i]',
    '[class*="modal" i]',
)


def overlay_diagnostics(page, candidate_limit=25):
    """Observe visible alert/dialog/overlay-like nodes without interacting."""
    selectors = selector_diagnostics(
        page,
        OVERLAY_DIAGNOSTIC_SELECTORS,
        candidates_per_selector=candidate_limit,
    )
    visible = []
    seen = set()
    for selector_result in selectors:
        for candidate in selector_result["candidates"]:
            key = (
                candidate.get("tag"),
                candidate.get("id"),
                candidate.get("class"),
                candidate.get("role"),
                candidate.get("text_preview"),
            )
            if key in seen:
                continue
            seen.add(key)
            visible.append(candidate)
            if len(visible) >= candidate_limit:
                break
        if len(visible) >= candidate_limit:
            break
    return {
        "selectors": selectors,
        "visible_candidates": visible,
        "visible_candidates_truncated": len(visible) >= candidate_limit,
    }


def write_diagnostic(event, path=None):
    """Append one bounded JSONL record; logging failures never escape."""
    if not EXECUTION_POLICY.allows_diagnostic_artifacts():
        return False
    try:
        record = dict(event)
        record.setdefault(
            "timestamp_utc",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        target = path or DIAGNOSTIC_FILE
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(target, "a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False
