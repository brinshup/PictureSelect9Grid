# Nine-Grid Selector — 项目说明

从本地照片中挑选 9 张构建有故事感的社交媒体九宫格。

## 快速命令

```bash
# 纯直方图（免费，秒级）
python scripts/preprocess.py
python scripts/score_and_group.py --mode histogram

# 视觉增强（推荐，~¥1/150张）
python scripts/preprocess.py
python scripts/vision_score.py           # Qwen3-VL-Plus 异步评分
python scripts/score_and_group.py --mode hybrid
python scripts/generate_visual_report.py --mode hybrid

# 调色后处理（可选）
python scripts/color_grade.py --version <版本>

# PDF 导出
python scripts/convert_to_pdf.py output/<version>/hybrid/top9_options.md
```

## 评分权重

摄影(20) + 情绪(25) + 艺术(15) + 叙事(40) = 100

## 核心脚本

| 脚本 | 说明 |
|------|------|
| `preprocess.py` | 缩小图片 + EXIF 提取 + 缩略图网格（必须先运行） |
| `vision_score.py` | Qwen3-VL-Plus 异步并发打分，base64 编码，指数退避重试 |
| `score_and_group.py` | 综合评分 + 淘汰低质 + 相似组 + 叙事蓝图匹配 |
| `narrative_blueprint.py` | 被 `score_and_group.py` import，提供蓝图引擎 |
| `generate_visual_report.py` | 内嵌缩略图的可视化报告 (top9_options.md / final_report.md / top30_visual.md) |
| `color_grade.py` | 4 种调色风格，按蓝图统一输出 |
| `convert_to_pdf.py` | Edge headless → PDF |
| `compare_versions.py` | 直方图 vs 视觉版对比 |

## 项目规则

- `image/` 原始照片只能读取不可删除
- 所有生成文件放在 `photos/resized/`、`photos/thumbnails/`、`output/`
- 每次分析前必须先运行 `preprocess.py`
- 输出版本化：`output/<version>/<mode>/`
- `.gitignore` 用 `output/[0-9]*/` 忽略所有版本输出

## 4 套叙事蓝图

旅程叙事 / 情绪弧线 / 光影对比 / 极简留白 — 见 `scripts/narrative_blueprint.py`

## 调色方案

| 蓝图 | 风格 |
|------|------|
| 旅程叙事 | Vintage Washed 复古胶片 |
| 情绪弧线 | Teal & Orange 电影调色 |
| 光影对比 | Cool Minimal 冷调极简 |
| 极简留白 | Cool Minimal 柔和冷调 |
