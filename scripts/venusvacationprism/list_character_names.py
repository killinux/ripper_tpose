#!/usr/bin/env python3
"""List character names accepted by the PRISM complete-character exporter."""

from __future__ import annotations

import argparse
import json
from typing import Any, Iterable

from character_profiles import CHARACTER_PROFILES


SUPPORT_LABELS = {
    "full": "可自动导出",
    "legacy_verified": "已登记，暂未开放",
    "fallback_required": "需要兼容处理，暂未开放",
}


def character_rows(exportable_only: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile in CHARACTER_PROFILES.values():
        if exportable_only and not profile.automated_export_enabled:
            continue
        rows.append({
            "name": profile.name_en,
            "name_zh": profile.name_zh,
            "code": profile.code,
            "accepted_names": [profile.name_en, profile.name_zh, profile.code],
            "automated_export": profile.automated_export_enabled,
            "support": profile.support_level,
            "support_zh": SUPPORT_LABELS.get(
                profile.support_level, profile.support_level
            ),
            "default_components": {
                role.lower(): {
                    "label": component.label,
                    "model_index": component.model_index,
                    "g1m": f"0x{component.g1m:08x}",
                }
                for role, component in profile.components.items()
            },
            "limitations": list(profile.limitations),
        })
    return rows


def render_text(rows: Iterable[dict[str, Any]], details: bool = False) -> str:
    rows = list(rows)
    exportable = [row for row in rows if row["automated_export"]]
    unavailable = [row for row in rows if not row["automated_export"]]
    lines = ["Venus Vacation PRISM 完整人物导出名称", ""]

    def append_group(title: str, values: list[dict[str, Any]]) -> None:
        if not values:
            return
        lines.append(title)
        for row in values:
            names = " / ".join(row["accepted_names"])
            lines.append(f"- {names}  [{row['support_zh']}]")
            if details:
                components = row["default_components"]
                for role in ("body", "face", "hair"):
                    item = components[role]
                    lines.append(
                        f"    {role.upper()}: index {item['model_index']}, "
                        f"{item['g1m']}, {item['label']}"
                    )
        lines.append("")

    append_group("可直接传给 export_character.py 的名字：", exportable)
    append_group("已登记但当前不会自动导出：", unavailable)
    lines.extend([
        "示例：",
        "  scripts\\venusvacationprism\\export_character.ps1 --name 七海 "
        "--output D:\\venusvacationprism_exports\\nanami",
    ])
    return "\n".join(lines) + "\n"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--exportable-only",
        action="store_true",
        help="Only show names currently enabled for unattended export",
    )
    result.add_argument(
        "--details",
        action="store_true",
        help="Show default BODY/FACE/HAIR model indices and G1M IDs",
    )
    result.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the text list",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    rows = character_rows(args.exportable_only)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(render_text(rows, args.details), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
