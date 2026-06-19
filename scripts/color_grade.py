"""
照片后期调色 — 叙事风格化处理（统一风格版）
每个蓝图方案使用一种统一的调色风格，确保九宫格视觉一致。
用法: python scripts/color_grade.py
输出: output/<version>/retouched/<蓝图名_风格>/ + 报告
"""
import json, os, sys
from pathlib import Path
from PIL import Image, ImageEnhance
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESIZED_DIR = PROJECT_DIR / "photos" / "resized"

# ── 1. 调色风格函数 ──

def style_teal_orange(img, strength=0.7):
    """Teal & Orange 电影调色 — 暗部青蓝 + 亮部橙红"""
    arr = np.array(img).astype(float)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    norm = gray / 255.0
    shadow_mask = 1.0 - norm
    b += shadow_mask * 25 * strength
    g += shadow_mask * 10 * strength
    highlight_mask = norm
    r += highlight_mask * 20 * strength
    midtone = norm * 2.0 - 1.0
    contrast_boost = midtone * 1.15
    boost_map = (contrast_boost + 1.0) / 2.0 * 255.0
    r = r * (boost_map / 255.0) * 1.05
    g = g * (boost_map / 255.0) * 0.95
    b = b * (boost_map / 255.0) * 0.90
    arr = np.clip(np.stack([r, g, b], axis=2), 0, 255)
    return Image.fromarray(arr.astype("uint8"))


def style_vintage_washed(img, strength=0.6):
    """Vintage Washed 复古胶片 — 降饱和 + 提黑场 + 暖色调"""
    arr = np.array(img).astype(float)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    desat = strength * 0.3
    r = r * (1 - desat) + gray * desat
    g = g * (1 - desat) + gray * desat
    b = b * (1 - desat) + gray * desat
    fade = strength * 18
    r = np.minimum(r + fade, 255)
    g = np.minimum(g + fade, 255)
    b = np.minimum(b + fade, 255)
    r = np.minimum(r * 1.08, 255)
    b = b * 0.92
    enhancer = ImageEnhance.Contrast(Image.fromarray(np.stack([r, g, b], axis=2).astype("uint8")))
    return enhancer.enhance(0.85)


def style_earthy_organic(img, strength=0.6):
    """Earthy Organic 自然大地 — 绿/棕增强 + 蓝衰减"""
    arr = np.array(img).astype(float)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    g = g * 1.12
    r = r * 1.08
    b = b * 0.85
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    desat = strength * 0.15
    r = r * (1 - desat) + gray * desat
    g = g * (1 - desat) + gray * desat
    b = b * (1 - desat) + gray * desat
    r = np.minimum(r * 1.03, 255)
    b = b * 0.95
    arr = np.clip(np.stack([r, g, b], axis=2), 0, 255)
    return Image.fromarray(arr.astype("uint8"))


def style_cool_minimal(img, strength=0.5):
    """Cool Minimal 冷调极简 — 蓝/青增强 + 高对比"""
    arr = np.array(img).astype(float)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    b = np.minimum(b * (1.0 + 0.15 * strength * 2), 255)
    g = np.minimum(g * (1.0 + 0.05 * strength * 2), 255)
    r = r * (1.0 - 0.10 * strength * 2)
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    mid = gray / 255.0
    contrast = mid * (1.0 + 0.20 * strength)
    contrast = np.clip(contrast, 0, 1) * 255.0
    detail = gray - contrast
    r = np.clip(r - detail * 0.3, 0, 255)
    g = np.clip(g - detail * 0.3, 0, 255)
    b = np.clip(b - detail * 0.3, 0, 255)
    r = np.minimum(r * 1.05, 255)
    g = np.minimum(g * 1.05, 255)
    b = np.minimum(b * 1.05, 255)
    arr = np.clip(np.stack([r, g, b], axis=2), 0, 255)
    return Image.fromarray(arr.astype("uint8"))


STYLES = {
    "vintage_washed": {"fn": style_vintage_washed, "name": "Vintage Washed 复古胶片",
                       "desc": "降饱和+提黑场+暖色调，70s胶片感，温暖怀旧适合旅行回忆"},
    "teal_orange": {"fn": style_teal_orange, "name": "Teal & Orange 电影调色",
                    "desc": "暗部青蓝+亮部橙红，经典好莱坞风格，戏剧性情感张力"},
    "cool_minimal": {"fn": style_cool_minimal, "name": "Cool Minimal 冷调极简",
                     "desc": "蓝/青增强+高对比，干净克制，强调光影结构"},
    "cool_minimal_light": {"fn": lambda img: style_cool_minimal(img, strength=0.3),
                           "name": "Cool Minimal 柔和冷调",
                           "desc": "冷调极简的轻量版，干净克制不抢主体"},
}


# ── 2. 蓝图-风格映射 ──

# 每个蓝图: (narrative_plans_key, subdir_name, style_key, chinese_name, narrative_desc)
BLUEPRINT_GRADE = [
    ("plan_journey",     "journey_vintage",  "vintage_washed",    "旅程叙事", "温暖怀旧的旅行回忆，像一部公路电影的胶片片段"),
    ("plan_emotion_arc", "emotion_teal",     "teal_orange",       "情绪弧线", "戏剧性情感张力，橙蓝对比强化情绪起伏"),
    ("plan_light_shadow","light_cool",       "cool_minimal",      "光影对比", "高对比冷调，强调从明亮到阴影的光影变化"),
    ("plan_minimalist",  "minimal_cool",     "cool_minimal_light","极简留白", "柔和冷调，干净克制不干扰留白和呼吸感"),
]


# ── 3. 批量处理 ──

def process_all(version=None):
    if version is None:
        from datetime import datetime
        version = datetime.now().strftime("%Y%m%d_%H%M")
    plan_path = PROJECT_DIR / "output" / version / "hybrid" / "narrative_plans.json"
    if not plan_path.exists():
        print(f"❌ {plan_path} 不存在")
        return

    with open(plan_path, "r", encoding="utf-8") as f:
        np_data = json.load(f)

    base_out = PROJECT_DIR / "output" / version / "retouched"
    pos_order = ["角(1)", "位2", "位3", "位4", "C位(5)", "位6", "位7", "位8", "角(9)"]

    all_results = {}  # blueprint_key -> [result_item, ...]

    for plan_key, subdir, style_key, cn_name, narr_desc in BLUEPRINT_GRADE:
        plan = np_data.get(plan_key, [])
        if not plan:
            print(f"⚠️  {cn_name} 方案为空，跳过")
            continue

        out_dir = base_out / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        style_info = STYLES[style_key]
        results = []

        print(f"\n{'=' * 50}")
        print(f"  {cn_name} → {style_info['name']}")
        print(f"  📝 {narr_desc}")
        print(f"{'=' * 50}")

        for item in plan:
            pos = item["position"]
            filename = item["filename"]
            src_path = RESIZED_DIR / filename
            if not src_path.exists():
                print(f"  ⚠️  不存在: {filename}")
                continue

            img = Image.open(src_path).convert("RGB")
            result_img = style_info["fn"](img)
            out_name = f"{pos}_{filename}"
            out_path = out_dir / out_name
            result_img.save(out_path, "JPEG", quality=90)

            results.append({
                "position": pos,
                "filename": filename,
                "style_name": style_info["name"],
                "style_desc": style_info["desc"],
                "subdir": subdir,
                "out_name": out_name,
            })
            print(f"  ✅ {pos}: {filename[:30]}")

        all_results[plan_key] = {
            "cn_name": cn_name,
            "narr_desc": narr_desc,
            "style_name": style_info["name"],
            "style_desc": style_info["desc"],
            "style_key": style_key,
            "subdir": subdir,
            "results": results,
        }

    # 生成报告
    generate_report(version, all_results, pos_order)
    print(f"\n✅ 全部完成！处理了 {len(all_results)} 套方案")


# ── 4. 报告生成 ──

def generate_report(version, all_results, pos_order):
    lines = []
    lines.append("# 后期调色报告 — 叙事统一调色")
    lines.append("")
    lines.append("> 每套叙事方案使用统一的调色风格，确保九宫格视觉一致性。")
    lines.append("")

    # 风格总览
    lines.append("---")
    lines.append("## 调色方案总览")
    lines.append("")
    lines.append("| 叙事方案 | 调色风格 | 叙事逻辑 |")
    lines.append("|----------|----------|----------|")
    for pk, data in all_results.items():
        lines.append(f"| **{data['cn_name']}** | {data['style_name']} | {data['narr_desc']} |")
    lines.append("")

    thumb_rel = "../../../photos/thumbnails"

    # 每套方案
    for pk, data in all_results.items():
        lines.append("---")
        lines.append(f"## {data['cn_name']}")
        lines.append("")
        lines.append(f"**调色风格**: {data['style_name']}")
        lines.append("")
        lines.append(f"**叙事说明**: {data['narr_desc']}")
        lines.append("")
        lines.append(f"**风格描述**: {data['style_desc']}")
        lines.append("")

        # 九宫格预览
        lines.append("### 九宫格预览")
        lines.append("")
        lines.append('<table style="border-collapse:collapse">')
        result_map = {r["position"]: r for r in data["results"]}

        for row in range(3):
            lines.append("  <tr>")
            for col in range(3):
                idx = row * 3 + col
                if idx < len(pos_order):
                    pos = pos_order[idx]
                    r = result_map.get(pos)
                    if r:
                        bg = ' style="background:#fffff5"' if "C位" in pos else ""
                        img_src = f"{r['subdir']}/{r['out_name']}"
                        lines.append(f'    <td align="center" style="border:1px solid #ddd;padding:8px"{bg}>')
                        lines.append(f'      <div><b>{pos}</b></div>')
                        lines.append(f'      <img src="{img_src}" width="160" style="border-radius:6px">')
                        lines.append(f'    </td>')
            lines.append("  </tr>")
        lines.append("</table>")
        lines.append("")

        # 前后对比表
        lines.append("### 前后对比")
        lines.append("")
        lines.append("| 位置 | 原图 | 处理后 |")
        lines.append("|------|:----:|:------:|")
        for r in data["results"]:
            thumb_src = f"{thumb_rel}/{r['filename']}"
            retouched_src = f"{r['subdir']}/{r['out_name']}"
            lines.append(f"| {r['position']} | <img src=\"{thumb_src}\" width=\"100\"> | <img src=\"{retouched_src}\" width=\"100\"> |")
        lines.append("")

    # 调色参数
    lines.append("---")
    lines.append("## 调色参数说明")
    lines.append("")
    lines.append("### Vintage Washed 复古胶片")
    lines.append("- 饱和度降低 30%")
    lines.append("- 黑场提升 18 级（fade 效果）")
    lines.append("- 暖色调偏移 (R×1.08, B×0.92)")
    lines.append("- 整体对比度降低至 85%")
    lines.append("")
    lines.append("### Teal & Orange 电影调色")
    lines.append("- 暗部叠加青蓝色 (B+25, G+10)")
    lines.append("- 亮部叠加橙红色 (R+20)")
    lines.append("- S 曲线增加对比度 (15%)")
    lines.append("")
    lines.append("### Cool Minimal 冷调极简")
    lines.append("- 蓝色通道增强 (15% × strength)")
    lines.append("- 红色通道衰减 (10% × strength)")
    lines.append("- 局部对比度增强 (20% × strength)")
    lines.append("- 整体提亮 5%")
    lines.append("")
    lines.append("### Cool Minimal 柔和冷调（轻量版）")
    lines.append("- 同上，但 strength=0.3，效果更柔和")
    lines.append("")

    # 保存
    report_path = PROJECT_DIR / "output" / version / "retouched" / "retouched_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n📄 报告: {report_path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="后期调色 — 统一风格")
    ap.add_argument("--version", default="3_1")
    args = ap.parse_args()
    process_all(args.version)
