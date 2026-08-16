"""Send explicitly authorized local BIFROST screenshots to the OMP Grok bridge.

This script is read-only: it sends only the two captured PNGs and a review
prompt, then writes the model's structured review locally. No UI, payload, or
Skill is modified.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIR = ROOT / ".omp" / "ui-review"
BRIDGE_URL = os.environ.get("OMP_BRIDGE_URL", "http://127.0.0.1:8000/v1/chat/completions")
MODEL = os.environ.get("MODEL_NAME", "grok-4.6")


def image_content(path: Path) -> dict[str, object]:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": "high"}}


def main() -> int:
    capture = json.loads((REVIEW_DIR / "capture.json").read_text(encoding="utf-8"))
    screenshots = capture["screenshots"]
    prompt = """
你是 BIFROST 制造业看板的只读视觉审查员。请审查下面两张真实 BIFROST UI 截图，不能重新设计页面，也不能假设截图外的功能。

审查重点：
1. 1440×900 桌面端是否能让厂长、线长、质量、设备、工艺、供应链快速阅读；
2. 390×844 移动端是否仍然可读、可操作，不能接受固定侧栏挤压主内容；
3. AI 助手、数据治理、角色切换、多产线和时间范围入口是否可发现；
4. 中文标签、KPI层级、异常/证据/待确认信息是否清楚；
5. 只把真正影响可用性的溢出、遮挡、重叠、不可读、关键入口缺失列为 must_fix。

请只返回 JSON，不要 Markdown 代码块，结构如下：
{
  "verdict": "pass" 或 "reject",
  "dimensions": {"readability":0,"role_fit":0,"hierarchy":0,"craft":0},
  "must_fix": [{"severity":"must_fix","viewport":"390x844","target":"...","problem":"...","fix":"..."}],
  "should_fix": [{"viewport":"...","target":"...","problem":"...","fix":"..."}],
  "summary":"不超过120字"
}
""".strip()
    content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
    for item in screenshots:
        content.append(image_content(Path(item["screenshot"])))

    body = {
        "model": MODEL,
        "temperature": 0.1,
        "max_tokens": 3000,
        "messages": [
            {"role": "system", "content": "只做视觉审查，不执行任何写入或修改。"},
            {"role": "user", "content": content},
        ],
    }
    request = urllib.request.Request(
        BRIDGE_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer omp-local-bridge-key"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = result["choices"][0]["message"]["content"]
    raw = {"review_version": "BIFROST_REAL_UI_GROK_REVIEW_v1", "model": MODEL, "capture": capture, "raw": text}
    (REVIEW_DIR / "grok-review.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(raw, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
