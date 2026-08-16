"""Hard arbiter for the real BIFROST UI review.

The model is advisory. A mobile content area that is objectively unusable is
always a rejection, even if a model says pass. A provider vision limitation is
reported as blocked instead of being silently treated as success.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--grok", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    capture: dict[str, Any] = json.loads(args.capture.read_text(encoding="utf-8-sig"))
    grok: dict[str, Any] = json.loads(args.grok.read_text(encoding="utf-8-sig"))
    screenshots = capture.get("screenshots", [])
    local_findings: list[dict[str, str]] = []
    for shot in screenshots:
        layout = shot.get("layout", {})
        viewport = "x".join(str(value) for value in shot.get("viewport", []))
        if layout.get("responsive_issue"):
            local_findings.append({
                "severity": "must_fix",
                "viewport": viewport,
                "target": "main-content",
                "problem": f"移动端主内容宽度仅 {layout.get('main_content_width')}px，固定侧栏挤压业务内容。",
                "fix": "移动端将侧栏折叠为抽屉或底部导航，并保证主内容至少占满可用宽度。",
            })
        if layout.get("horizontal_overflow"):
            local_findings.append({
                "severity": "must_fix",
                "viewport": viewport,
                "target": "document",
                "problem": "页面存在水平溢出。",
                "fix": "修正固定宽度、最小宽度和响应式断点。",
            })
        for label, present in shot.get("label_presence", {}).items():
            if not present:
                local_findings.append({
                    "severity": "must_fix",
                    "viewport": viewport,
                    "target": label,
                    "problem": "关键入口或角色标签未在页面文本中出现。",
                    "fix": "恢复该入口并保持角色权限范围不变。",
                })
        if shot.get("console_errors"):
            local_findings.append({
                "severity": "must_fix",
                "viewport": viewport,
                "target": "console",
                "problem": "浏览器出现运行时错误。",
                "fix": "修复运行时错误后重新回归。",
            })

    raw = str(grok.get("raw", ""))
    vision_blocked = "Vision model returned no usable text" in raw or "无法分析" in raw or "image input" in raw
    if vision_blocked:
        local_findings.append({
            "severity": "blocked",
            "viewport": "desktop/mobile",
            "target": "custom-grok-vision",
            "problem": "custom-grok 返回视觉模型不可用，未能完成模型层截图判断。",
            "fix": "保留本地确定性布局检查；若需要模型视觉意见，切换到支持图片输入的模型或提供 OCR/结构化布局数据。",
        })

    result = {
        "arbiter_version": "BIFROST_REAL_UI_ARBITER_v1",
        "verdict": "reject" if any(item["severity"] == "must_fix" for item in local_findings) else "blocked" if vision_blocked else "pass",
        "local_checks": {
            "screenshots_captured": len(screenshots) == 2,
            "desktop_loaded": bool(screenshots and screenshots[0].get("body_text_length")),
            "mobile_loaded": bool(len(screenshots) > 1 and screenshots[1].get("body_text_length")),
            "vision_model_available": not vision_blocked,
        },
        "findings": local_findings,
        "grok_review": grok,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
