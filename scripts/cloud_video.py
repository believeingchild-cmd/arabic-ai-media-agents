"""Cloud-first Arabic video pilot. Runs on GitHub Actions; no personal computer required.

Three independent model roles:
  OpenAI   -> Arabic script and scene plan
  Claude   -> safety/editorial review
  Gemini   -> independent fact/safety review
A video is rendered only when both reviewers explicitly approve.
Publishing is deliberately not implemented in this pilot.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(os.getenv("VIDEO_OUTPUT_DIR", "out/cloud"))
TOPIC = os.getenv("VIDEO_TOPIC", "مهنة الطبيب: كيف يساعد الناس؟").strip()
CHANNEL = os.getenv("VIDEO_CHANNEL", "children").strip()
VOICE = "ar-SA-ZariyahNeural"
OUT.mkdir(parents=True, exist_ok=True)


def request_json(url: str, payload: dict, headers: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def openai_text(system: str, user: str) -> str:
    result = request_json(
        "https://api.openai.com/v1/chat/completions",
        {"model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), "temperature": 0.4,
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
    )
    return result["choices"][0]["message"]["content"]


def claude_review(script_text: str) -> str:
    result = request_json(
        "https://api.anthropic.com/v1/messages",
        {"model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5"), "max_tokens": 900,
         "system": "أنت مراجع مستقل صارم لسلامة المحتوى العربي. لا تفترض صحة الادعاءات الدينية أو الطبية. أجب JSON فقط: {"decision":"APPROVE" أو "REJECT","issues":[...],"notes":"..."}. ارفض أي ادعاء غير مسند أو محتوى غير مناسب للأطفال.",
         "messages": [{"role": "user", "content": f"القناة: {CHANNEL}\nالموضوع: {TOPIC}\nراجع النص والمشاهد التاليين: \n{script_text}"}]},
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
    )
    return "".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")


def gemini_review(script_text: str) -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(os.environ['GEMINI_API_KEY'])}"
    result = request_json(
        url,
        {"systemInstruction": {"parts": [{"text": "أنت مراجع مستقل للتحقق من الدقة والملاءمة. أجب JSON فقط: {\"decision\":\"APPROVE\" أو \"REJECT\",\"issues\":[...],\"notes\":\"...\"}. لا تعتبر الادعاءات الدينية حقائق دون مراجع موثوقة. ارفض المحتوى الخطر أو غير المناسب."}]},
         "contents": [{"parts": [{"text": f"القناة: {CHANNEL}\nالموضوع: {TOPIC}\nراجع النص التالي: \n{script_text}"}]}],
         "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}},
        {},
    )
    return result["candidates"][0]["content"]["parts"][0]["text"]


def extract_json(text: str) -> dict:
    text = re.sub(r"^\s*```(?:json)?|\```\s*$", "", text.strip(), flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model response did not contain valid JSON")
    return json.loads(text[start:end + 1])


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, timeout=180)


def download_image(prompt: str, target: Path) -> None:
    # Best-effort image provider; image content is not trusted as factual evidence.
    query = urllib.parse.quote(prompt[:400])
    url = f"https://image.pollinations.ai/prompt/{query}?width=720&height=1280&nologo=true"
    req = urllib.request.Request(url, headers={"User-Agent": "ArabicVideoPilot/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        data = response.read()
    if len(data) < 10_000:
        raise RuntimeError("Image provider returned an unexpectedly small image")
    target.write_bytes(data)


def main() -> int:
    if CHANNEL not in {"children", "public"}:
        raise ValueError("VIDEO_CHANNEL must be children or public")
    if not TOPIC or len(TOPIC) > 300:
        raise ValueError("Topic must be 1-300 characters")
    if CHANNEL == "children":
        policy = "مناسب للأطفال: لغة بسيطة، لا تخويف أو عنف أو طلب بيانات شخصية. في العقيدة أو الدين، لا تخترع آيات أو أحاديث أو أحكامًا، وإذا لم تتوفر مراجع دقيقة فاكتب محتوى أخلاقيًا عامًا بلا نسبة دينية."
    else:
        policy = "للقناة العامة: لا تختلق خبرًا أو إحصائية أو اقتباسًا. هذا النموذج التجريبي لا يملك مصادر أخبار موثقة؛ تجنب صياغة الموضوع كخبر عاجل أو ادعاء واقعي غير متحقق."

    prompt = f"""أنشئ فيديو عموديًا عربيًا قصيرًا من 4 مشاهد حول: {TOPIC}
القناة: {CHANNEL}. قواعد السلامة: {policy}
أخرج JSON فقط بالشكل:
{{"title":"عنوان عربي","description":"وصف عربي","scenes":[{{"narration":"جملتان قصيرتان بالعربية","image_prompt":"English visual description, family-friendly, no text in image"}}]}}
يجب أن تحتوي scenes على 4 عناصر بالضبط. تجنب أي معلومة غير موثقة. لا تضف مراجع دينية مخترعة."""
    raw = openai_text("أنت كاتب سيناريو فيديو عربي دقيق وآمن. أخرج JSON صالحًا فقط.", prompt)
    plan = extract_json(raw)
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 4:
        raise ValueError("Script must contain exactly four scenes")
    if any(not isinstance(s.get("narration"), str) or not s["narration"].strip() or not isinstance(s.get("image_prompt"), str) for s in scenes):
        raise ValueError("Each scene needs narration and an image_prompt")
    script_text = json.dumps(plan, ensure_ascii=False, indent=2)
    (OUT / "script.json").write_text(script_text, encoding="utf-8")

    reviews = {}
    for name, fn in (("claude", claude_review), ("gemini", gemini_review)):
        try:
            reviews[name] = extract_json(fn(script_text))
        except Exception as exc:
            reviews[name] = {"decision": "REJECT", "issues": [f"Reviewer error: {type(exc).__name__}: {exc}"], "notes": "Fail-closed"}
    (OUT / "reviews.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
    if any(item.get("decision") != "APPROVE" or item.get("issues") for item in reviews.values()):
        raise RuntimeError("Review gate blocked rendering. Inspect reviews.json artifact; no video was rendered.")

    clips = []
    for i, scene in enumerate(scenes, start=1):
        image = OUT / f"scene_{i}.jpg"
        audio = OUT / f"scene_{i}.mp3"
        clip = OUT / f"scene_{i}.mp4"
        download_image(scene["image_prompt"], image)
        narration = scene["narration"].strip()
        (OUT / f"scene_{i}.txt").write_text(narration, encoding="utf-8")
        run([sys.executable, "-m", "edge_tts", "--voice", VOICE, "--text", narration, "--write-media", str(audio)])
        # Subtitles are burned with a system Arabic-capable font; FFmpeg handles Arabic shaping via libass.
        subtitle = OUT / f"scene_{i}.ass"
        escaped = narration.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        subtitle.write_text(
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Noto Sans Arabic,42,&H00FFFFFF,&H00000000,1,3,1,2,50,50,100,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,0:00:12.00,Default,,0,0,0,,{{\\fad(150,150)}}{escaped}\n",
            encoding="utf-8",
        )
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(image), "-i", str(audio),
             "-vf", f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,subtitles={subtitle.as_posix()}",
             "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k",
             "-pix_fmt", "yuv420p", "-shortest", "-r", "25", str(clip)])
        clips.append(clip)

    concat = OUT / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in clips), encoding="utf-8")
    final = OUT / "arabic_review_video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(final)])
    manifest = {
        "channel": CHANNEL, "topic": TOPIC, "title": plan.get("title", TOPIC),
        "video_path": str(final), "model_reviews": reviews,
        "human_review": False, "publishing_enabled": False,
        "warning": "AI review is not proof of factual accuracy. Human review is required before publication."
    }
    (OUT / "quality_gate.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VIDEO_READY={final} SIZE={final.stat().st_size}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"::error::{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
