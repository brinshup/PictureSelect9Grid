# Nine-Grid Selector — 九宫格叙事选片工具

从本地照片中智能挑选 9 张照片，构建有故事感的社交媒体九宫格。支持纯直方图（免费）和 Qwen3-VL-Plus 视觉增强（~¥1/次）两种评分模式。

## 核心特性

- **叙事优先** — 4 套叙事蓝图（旅程叙事/情绪弧线/光影对比/极简留白），先定叙事再匹配照片
- **三维评分** — 摄影(20) + 情绪(25) + 艺术(15) + 叙事(40) = 100 分
- **智能裁剪** — 远景→中景/特写裁剪建议，让低分照片也能用于叙事
- **统一调色** — 每套方案一套调色风格（Vintage Washed / Teal & Orange / Cool Minimal）
- **调色后处理** — 4 种电影级调色风格，按蓝图统一输出
- **可视化报告** — 内嵌缩略图的 HTML/Markdown 报告 + PDF 导出

## 快速开始

### 环境要求

```bash
# 安装依赖
pip install Pillow numpy tqdm pillow-heif aiohttp markdown
```

### 方式一：纯直方图（免费，秒级）

```bash
python scripts/preprocess.py
python scripts/score_and_group.py --mode histogram
# 输出: output/<版本>/histogram/
```

### 方式二：视觉增强（推荐，~¥1/次）

```bash
# 1. 配置 API 密钥
echo "QWEN_API_KEY=sk-你的密钥" > .env

# 2. 预处理
python scripts/preprocess.py

# 3. 视觉评分（~2分钟/150张）
python scripts/vision_score.py

# 4. 叙事评分+蓝图匹配
python scripts/score_and_group.py --mode hybrid

# 5. 可视化报告
python scripts/generate_visual_report.py --mode hybrid

# 6. 调色后处理（可选）
python scripts/color_grade.py --version <版本号>
```

## 系统架构

```
image/                    ← 原始照片（只读）
  │
  ▼
preprocess.py             ← 缩小 + EXIF + 缩略图
  │
  ├── photos/resized/     ← 缩小工作副本 + metadata.json
  ├── photos/thumbnails/  ← 缩略图 + contact_sheet.jpg
  │
  ▼
┌─────────────────────────────────────────┐
│           评分系统                        │
│                                         │
│  analysis.json (直方图数据)              │
│        +                                 │
│  vision_scores.json (Qwen视觉评分)        │
│        ↓                                 │
│  score_and_group.py                      │
│  ├── 淘汰低质照片                         │
│  ├── 综合评分 (摄影+情绪+艺术+叙事)        │
│  ├── 相似组聚类                           │
│  └── 叙事蓝图匹配                         │
└─────────────────────────────────────────┘
  │
  ├── output/<version>/hybrid/
  │   ├── score_matrix.csv    ← 全量评分表
  │   ├── groups.json         ← 相似组
  │   ├── narrative_plans.json← 4套叙事方案
  │   ├── top9_options.md     ← 方案可视化
  │   ├── final_report.md     ← 推荐方案
  │   └── top30_visual.md     ← Top30 矩阵
  │
  └── color_grade.py (可选)
      └── output/<version>/retouched/
          ├── journey_vintage/   ← 复古胶片调色
          ├── emotion_teal/      ← 橙蓝电影调色
          ├── light_cool/        ← 冷调极简
          ├── minimal_cool/      ← 柔和冷调
          └── retouched_report.md
```

## 评分模式详解

| 模式 | 命令 | 成本 | 速度 | 说明 |
|------|------|:----:|:----:|------|
| **hybrid** 🧠 | `--mode hybrid` | ~¥1/150张 | ~2min | **推荐**。70%视觉+30%直方图+叙事评分 |
| **histogram** 📊 | `--mode histogram` | 免费 | 秒级 | 仅亮度/对比度/清晰度数值指标 |
| **vision** 👁️ | `--mode vision` | ~¥1/150张 | ~2min | 仅用 Qwen 视觉评分 |

无 `--mode` 时自动检测：存在 `vision_scores.json` → hybrid，否则 → histogram。

## 4 套叙事蓝图

| 蓝图 | 叙事曲线 | 最佳素材 |
|------|----------|----------|
| **旅程叙事** 🚗 | 出发→路途→风景→人物→高潮→沉淀→回味→归途 | 内容多样+有人物 |
| **情绪弧线** 💖 | 平静→温暖→欢乐→高峰→转折→沉淀→平复→余韵 | 人物+多种情绪 |
| **光影对比** ☀️🌙 | 明亮→阳光→活跃→光影→阴影→暗夜→静谧→夜色 | 街拍+建筑+冷暖 |
| **极简留白** ▫️ | 空→出现→人物→再空→聚焦→纹理→留白→空白收束 | 留白+极简素材 |

## 调色方案

| 叙事方案 | 调色风格 | 效果 |
|----------|----------|------|
| 旅程叙事 | Vintage Washed 复古胶片 | 降饱和+暖色调+黑场提升，70s旅行回忆 |
| 情绪弧线 | Teal & Orange 电影调色 | 暗部青蓝+亮部橙红，戏剧性张力 |
| 光影对比 | Cool Minimal 冷调极简 | 蓝/青增强+高对比，强调光影结构 |
| 极简留白 | Cool Minimal 柔和版 | 冷调极简轻量版，干净不抢主体 |

## 输出目录结构

```
output/
├── analysis.json              ← 直方图分析数据（共享）
├── vision_scores.json         ← 视觉评分数据（共享）
├── USAGE_GUIDE.md             ← 使用手册
│
├── 1_0/                       ← 版本号（自动递增）
│   ├── histogram/             ← 纯直方图结果
│   ├── hybrid/                ← 混合评分结果
│   ├── vision/                ← 纯视觉结果
│   └── retouched/             ← 调色后处理结果
│
├── 3_0/                       ← 叙事升级版
│   └── hybrid/                ← 含 narrative_plans.json
│
└── 3_1/                       ← 色温调色版
    ├── hybrid/
    └── retouched/
```

## 脚本参考

| 脚本 | 功能 | 必选 |
|------|------|:----:|
| `scripts/preprocess.py` | 缩小图片、提取 EXIF、生成缩略图 | ✅ |
| `scripts/vision_score.py` | Qwen3-VL-Plus 异步视觉评分 | 视觉模式需要 |
| `scripts/score_and_group.py` | 综合评分 + 叙事蓝图匹配 + 分组 | ✅ |
| `scripts/narrative_blueprint.py` | 叙事蓝图引擎（被 score_and_group 调用） | 自动 |
| `scripts/generate_visual_report.py` | 生成带缩略图的可视化报告 | 推荐 |
| `scripts/color_grade.py` | 照片调色后处理（4 种风格） | 可选 |
| `scripts/convert_to_pdf.py` | Markdown → PDF 转换 | 可选 |
| `scripts/compare_versions.py` | 直方图 vs 视觉版对比 | 可选 |

## 版本号规则

- 格式：`主版本_次版本`（如 `1_0`, `3_1`）
- 自动递增：已有 `1_0` 时自动升为 `1_1`
- 手动指定：`--version 2_0`
- 输出路径：`output/<version>/<mode>/`

## .gitignore 说明

项目使用版本号通配 `output/[0-9]*/` 忽略所有版本化输出目录。输出文件不纳入版本控制，可按需重新生成。

## 获取 API 密钥

1. 访问 [DashScope (阿里云)](https://dashscope.aliyun.com/)
2. 创建 API Key
3. 写入 `.env`：`QWEN_API_KEY=sk-你的密钥`

## License

MIT
