---
name: Nine-Grid Selector
description: 从本地照片库挑选并排列九宫格发圈素材，支持纯直方图/Qwen3-VL-Plus视觉增强
---

## 项目结构

- `image/` — 原始照片（只读）
- `photos/resized/` — 缩小后工作副本
- `photos/thumbnails/` — 缩略图
- `scripts/` — Python 脚本
- `output/<版本>/<模式>/` — 评分结果
- `plans/` — 改进计划文档

## 流程

1. **预处理**: `python scripts/preprocess.py`
2. **视觉评分**: `python scripts/vision_score.py`（可选，需要 API 密钥）
3. **评分与蓝图**: `python scripts/score_and_group.py --mode hybrid`
4. **可视化报告**: `python scripts/generate_visual_report.py --mode hybrid`
5. **调色后处理**: `python scripts/color_grade.py`（可选）

## 评分权重

摄影(20) + 情绪(25) + 艺术(15) + 叙事(40) = 100

## 4 套叙事蓝图

旅程叙事、情绪弧线、光影对比、极简留白

## 规则

- 原始照片不可删除
- 每次分析前必须运行 preprocess.py
- 结果在 output/<版本>/ 下

## 参考

- `CLAUDE.md` — 详细命令参考
- `output/USAGE_GUIDE.md` — 完整使用手册
- `README.md` — 架构概览
