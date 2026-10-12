"""Deterministic pre-publish gate for Arabic AI-generated content.

This is a conservative baseline, not a substitute for human editorial review.
Input JSON example is documented in docs/quality-gate.md. Exit 0 = pass, 2 = blocked.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = (
    "guaranteed cure", "miracle cure", "make money fast", "get rich quick",
    "علاج مضمون", "شفاء مضمون", "معجزة علاجية", "اربح المال بسرعة",
    "مصدر مجهول", "انشر قبل الحذف",
)
BROKEN = (
    r"<think>|</think>", r'"thoughts"\s*:', r'"reasoning"\s*:',
    r"the user is asking", r"let me think", r"أنا نموذج لغوي",
)

def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    channel = payload.get("channel")
    if channel not in {"children", "public"}:
        errors.append("channel must be children or public")
    for field in ("title", "script", "video_path"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"missing required field: {field}")
    title = str(payload.get("title", "")).strip()
    script = str(payload.get("script", "")).strip()
    if len(title) > 100:
        errors.append("title exceeds 100 characters")
    if len(script) < 80:
        errors.append("script is too short for meaningful review")
    combined = (title + "\n" + script).casefold()
    for phrase in BLOCKED:
        if phrase.casefold() in combined:
            errors.append(f"blocked phrase detected: {phrase}")
    for pattern in BROKEN:
        if re.search(pattern, combined, flags=re.I):
            errors.append(f"broken/model-leak pattern detected: {pattern}")
    video = Path(str(payload.get("video_path", ""))).expanduser()
    if not video.is_file():
        errors.append("video_path does not point to an existing file")
    elif video.stat().st_size < 50_000:
        errors.append("video file is suspiciously small (< 50 KB)")
    if channel == "public":
        sources = payload.get("sources", [])
        valid = []
        if isinstance(sources, list):
            for source in sources:
                url = source.get("url", "") if isinstance(source, dict) else ""
                host = urlparse(url).hostname
                if host and "." in host and urlparse(url).scheme == "https":
                    valid.append(host.lower().removeprefix("www."))
        if len(set(valid)) < 2:
            errors.append("public/news content requires at least two HTTPS source domains")
    if channel == "children":
        refs = payload.get("religious_references", [])
        if not isinstance(refs, list) or not refs:
            errors.append("children channel requires religious_references for editorial verification")
        if payload.get("child_safety_review") is not True:
            errors.append("children channel requires child_safety_review=true")
    if payload.get("rights_review") is not True:
        errors.append("rights_review must be true before publishing")
    if payload.get("editorial_review") is not True:
        errors.append("editorial_review must be true before publishing")
    return errors

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", help="Path to a JSON metadata file")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
    except Exception as exc:
        print(json.dumps({"pass": False, "errors": [f"cannot read metadata: {exc}"]}, ensure_ascii=False))
        return 2
    errors = validate(payload)
    print(json.dumps({"pass": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2

if __name__ == "__main__":
    raise SystemExit(main())
