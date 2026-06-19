# -*- coding: utf-8 -*-
"""对比纯直方图版本 vs Qwen3-VL-Plus 增强版"""
import csv, sys, json, re
from pathlib import Path
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PROJECT_DIR = Path(__file__).resolve().parent.parent

def load(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row["total"] = float(row["总分(100)"])
            rows.append(row)
    return rows

# 扫描 output/ 下的最新版本目录自动取最新结果
_VERSIONS = sorted([d for d in (_PROJECT_DIR / "output").iterdir() if d.is_dir() and d.name.count("_") == 1])
_LATEST = str(_VERSIONS[-1]) if _VERSIONS else str(_PROJECT_DIR / "output")
HIST_DIR = _LATEST + "/histogram" if (_PROJECT_DIR / "output" / _VERSIONS[-1].name / "histogram").exists() else str(_PROJECT_DIR / "output/histogram")
VLM_DIR = _LATEST + "/hybrid" if (_PROJECT_DIR / "output" / _VERSIONS[-1].name / "hybrid").exists() else str(_PROJECT_DIR / "output/hybrid")

hist = load(f"{HIST_DIR}/score_matrix.csv")
vlm = load(f"{VLM_DIR}/score_matrix.csv")

hist_map = {r["filename"]: r for r in hist}
vlm_map = {r["filename"]: r for r in vlm}
has_v = "内容类型" in vlm[0] if vlm else False

print("=" * 72)
print("  Qwen3-VL-Plus 视觉评分 vs 纯直方图 对比报告")
print("=" * 72)

# ====== 1. Top 20 ======
print(f"\n{'─' * 72}")
print("  一、Top 20 排名变动")
print(f"{'─' * 72}")
print(f'{"#":>3} {"纯直方图版":<24} {"H分":>5} {"V分":>5} {"D":>5} {"视觉增强版":<24} {"内容类型":<12}')
print("-" * 72)

hist_top20 = sorted(hist, key=lambda x: x["total"], reverse=True)[:20]
for i, h in enumerate(hist_top20):
    fn = h["filename"]
    v = vlm_map.get(fn, {})
    ht = h["total"]
    vt = v.get("total", 0) if v else 0
    delta = vt - ht
    ct = v.get("内容类型", "") if v else ""
    short = fn.replace(".jpg", "")[-22:]
    print(f'{i+1:>2}  {short:<22}  {ht:5.1f}  {vt:5.1f}  {delta:+5.1f}  {short:<22}  {ct:<12}')

# ====== 2. 排名互换矩阵 ======
print(f"\n{'─' * 72}")
print("  二、关键位置排名互换")
print(f"{'─' * 72}")

h_sorted = sorted(hist, key=lambda x: x["total"], reverse=True)
v_sorted = sorted(vlm, key=lambda x: x["total"], reverse=True)

print("\n纯直方图 Top 5 在视觉版中的位置：")
for i, r in enumerate(h_sorted[:5]):
    v_rank = next((j+1 for j, vr in enumerate(v_sorted) if vr["filename"] == r["filename"]), "?")
    arrow = "→" if v_rank != (i+1) else "—"
    print(f"  #{i+1} {arrow} #{v_rank}  {r['filename']:40} {r['total']:5.1f}")

print("\n视觉增强 Top 5 在直方图版中的位置：")
for i, r in enumerate(v_sorted[:5]):
    h_rank = next((j+1 for j, hr in enumerate(h_sorted) if hr["filename"] == r["filename"]), "?")
    ct = vlm_map.get(r["filename"], {}).get("内容类型", "") if has_v else ""
    ppl = ""
    if has_v and vlm_map.get(r["filename"], {}).get("有人物") == "True":
        ppl = " [有人物]"
    arrow = "→" if h_rank != (i+1) else "—"
    print(f"  {h_rank} {arrow} #{i+1}  {r['filename']:40} {r['total']:5.1f} [{ct}]{ppl}")

# ====== 3. 视觉模型新增能力 ======
if has_v:
    print(f"\n{'─' * 72}")
    print("  三、视觉模型新增能力")
    print(f"{'─' * 72}")
    cts = Counter(r.get("内容类型", "?") for r in vlm)
    moods = Counter(r.get("心情", "?") for r in vlm)
    ppl = sum(1 for r in vlm if r.get("有人物") == "True")
    faces = sum(int(r.get("人脸数", 0)) for r in vlm if r.get("人脸数", ""))
    top20_ppl = sum(1 for r in v_sorted[:20] if r.get("有人物") == "True")

    print(f"  内容分类: {dict(cts)}")
    print(f"  心情识别: {dict(moods)}")
    print(f"  人物检测: {ppl}张有人物 (总人脸数={faces})")
    print(f"  Top20有人物: {top20_ppl}张")

    # 有人物的照片
    people_photos = [r for r in vlm if r.get("有人物") == "True"]
    if people_photos:
        print(f"\n  有人物的照片详情:")
        for p in sorted(people_photos, key=lambda x: x["total"], reverse=True)[:10]:
            ct = p.get("内容类型", "")
            fc = p.get("人脸数", "?")
            print(f"    总分{p['total']:5.1f}  [{ct}] 人脸={fc}  {p['filename'][:40]}")

# ====== 4. 相似组 ======
print(f"\n{'─' * 72}")
print("  四、相似分组对比")
print(f"{'─' * 72}")

with open(f"{HIST_DIR}/groups.json", encoding="utf-8") as f:
    h_groups = json.load(f)
with open(f"{VLM_DIR}/groups.json", encoding="utf-8") as f:
    v_groups = json.load(f)

print(f"  纯直方图: {len(h_groups)} 组 (仅按 serial 号分组)")
print(f"  视觉增强: {len(v_groups)} 组 (content_type 感知)")

if v_groups:
    show_first = 8
    for g in v_groups[:show_first]:
        cts = g.get("content_types", [])
        ct_str = f" 内容={cts}" if cts else ""
        print(f"    组{g['group_id']}: {g['size']}张{ct_str}")
    if len(v_groups) > show_first:
        print(f"    ... 还有 {len(v_groups)-show_first} 组")

# ====== 5. 方案对比 ======
print(f"\n{'─' * 72}")
print("  五、最终推荐方案（视觉冲击版）对比")
print(f"{'─' * 72}")

for ver_name, fpath in [
    ("纯直方图", f"{HIST_DIR}/final_report.md"),
    ("视觉增强", f"{VLM_DIR}/final_report.md"),
]:
    text = open(fpath, encoding="utf-8").read()
    photos = re.findall(r"`(微信图片_\d+_\d+_\d+\.jpg)`\s*→\s*位置(.+)", text)
    print(f"\n  {ver_name}:")
    for pos, fn in photos:
        extra = ""
        if has_v and ver_name == "视觉增强":
            v = vlm_map.get(fn, {})
            ct = v.get("内容类型", "")
            extra = f"  [{ct}"
            if v.get("有人物") == "True":
                extra += " 👤"
            extra += "]"
        short = fn.replace(".jpg", "")[-22:]
        print(f"    {pos:<10} {short}  {extra}")

# 相同位置统计
h_text = open(f"{HIST_DIR}/final_report.md", encoding="utf-8").read()
v_text = open(f"{VLM_DIR}/final_report.md", encoding="utf-8").read()
h_plan = re.findall(r"`(微信图片_\d+_\d+_\d+\.jpg)`\s*→\s*位置(.+)", h_text)
v_plan = re.findall(r"`(微信图片_\d+_\d+_\d+\.jpg)`\s*→\s*位置(.+)", v_text)

if h_plan and v_plan:
    same = sum(1 for (hp, hf), (vp, vf) in zip(h_plan, v_plan) if hf == vf)
    diff = sum(1 for (hp, hf), (vp, vf) in zip(h_plan, v_plan) if hf != vf)
    print(f"\n  相同选择: {same}/9 张")
    print(f"  不同选择: {diff}/9 张")
    if diff:
        print(f"\n  替换详情:")
        for (hp, hf), (vp, vf) in zip(h_plan, v_plan):
            if hf != vf:
                h_short = hf.replace(".jpg", "")[-18:]
                v_short = vf.replace(".jpg", "")[-18:]
                ct = vlm_map.get(vf, {}).get("内容类型", "")
                ppl = " 👤" if has_v and vlm_map.get(vf, {}).get("有人物") == "True" else ""
                print(f"    位置{hp}: {h_short} → {v_short} [{ct}{ppl}]")

# ====== 6. 统计摘要 ======
print(f"\n{'─' * 72}")
print("  六、统计摘要")
print(f"{'─' * 72}")

rank_changes = []
score_deltas = []
for h in hist:
    fn = h["filename"]
    v = vlm_map.get(fn)
    if v:
        h_rank = next(i+1 for i, r in enumerate(h_sorted) if r["filename"] == fn)
        v_rank = next(i+1 for i, r in enumerate(v_sorted) if r["filename"] == fn)
        rank_changes.append(abs(h_rank - v_rank))
        score_deltas.append(v["total"] - h["total"])

print(f"  平均排名变化: {sum(rank_changes)/len(rank_changes):.1f} 位")
print(f"  最大排名变动: {max(rank_changes)} 位")
print(f"  排名不变: {sum(1 for c in rank_changes if c == 0)} 张")
print(f"  变动 1-5 位: {sum(1 for c in rank_changes if 1 <= c <= 5)} 张")
print(f"  变动 6-10 位: {sum(1 for c in rank_changes if 6 <= c <= 10)} 张")
print(f"  变动 10+ 位: {sum(1 for c in rank_changes if c > 10)} 张")
print(f"  平均总分变化: {sum(score_deltas)/len(score_deltas):+.1f}")
print(f"  总分最大上升: {max(score_deltas):+.1f}  最大下降: {min(score_deltas):+.1f}")

print(f"\n{'=' * 72}")
print("  对比报告完成")
print(f"{'=' * 72}")
