# 九宫格选片工具 · 完整使用手册

> **项目路径**: `your-project-path`
> **Python**: 3.12 | **更新**: 2026-06-19
> 从本地照片中挑选 9 张构建有故事感的社交媒体九宫格

---

## 目录

1. [环境准备](#1-环境准备)
2. [快速开始](#2-快速开始)
3. [完整流程详解](#3-完整流程详解)
4. [评分模式选择](#4-评分模式选择)
5. [输出文件说明](#5-输出文件说明)
6. [叙事蓝图系统](#6-叙事蓝图系统)
7. [调色后处理](#7-调色后处理)
8. [PDF 导出](#8-pdf-导出)
9. [版本管理](#9-版本管理)
10. [常见问题](#10-常见问题)

---

## 1. 环境准备

### 安装 Python 依赖

```bash
pip install Pillow numpy tqdm pillow-heif aiohttp markdown
```

各依赖用途：

| 包 | 用途 |
|---|------|
| Pillow | 图片处理（缩放、EXIF 读取、格式转换） |
| numpy | 直方图分析、调色矩阵运算 |
| tqdm | 进度条显示 |
| pillow-heif | HEIC 格式支持（iPhone 照片） |
| aiohttp | 异步 HTTP 请求（视觉评分用） |
| markdown | Markdown → PDF 转换用 |

### API 密钥配置（视觉评分需要）

```bash
# 编辑 .env 文件
echo "QWEN_API_KEY=sk-你的密钥" > .env
```

获取密钥：访问 [DashScope (阿里云)](https://dashscope.aliyun.com/) → 创建 API Key

> 如果只使用纯直方图模式，无需配置 API 密钥。

### 照片准备

将需要筛选的照片放入 `image/` 目录：
- 支持的格式：JPG、JPEG、PNG、TIF、TIFF、HEIC（需 pillow-heif）
- 文件数量建议：20-500 张（超过 500 张建议分批次）

---

## 2. 快速开始

### 方案一：纯直方图（零成本，秒级完成）

适合快速预览、无 API 密钥的场景。

```bash
cd your-project-path

# 1. 预处理（必须先运行）
python scripts/preprocess.py

# 2. 评分与分组
python scripts/score_and_group.py --mode histogram

# 3. 生成可视化报告
python scripts/generate_visual_report.py --mode histogram
```

结果位置：`output/<版本号>/histogram/`

### 方案二：视觉增强（推荐，~¥1/150张）

适合最终选片、对质量有要求的场景。

```bash
cd your-project-path

# 1. 预处理
python scripts/preprocess.py

# 2. 视觉评分（~2分钟）
python scripts/vision_score.py

# 3. 叙事评分 + 蓝图匹配
python scripts/score_and_group.py --mode hybrid

# 4. 可视化报告
python scripts/generate_visual_report.py --mode hybrid

# 5. （可选）调色后处理
python scripts/color_grade.py --version <版本号>
```

结果位置：`output/<版本号>/hybrid/`

---

## 3. 完整流程详解

### 第一步：预处理 — `preprocess.py`

```bash
python scripts/preprocess.py
```

默认参数（通常无需修改）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | `image` | 原始照片目录 |
| `--output` | `photos/resized` | 缩小版输出目录 |
| `--thumbnails` | `photos/thumbnails` | 缩略图输出目录 |
| `--max-size` | `2560` | 长边最大像素 |
| `--quality` | `85` | JPEG 压缩质量 |

**执行效果：**
- 全部转为 JPG 格式（统一处理）
- 长边缩放到 2560px（平衡质量与速度）
- 生成 480px 缩略图
- 生成 `contact_sheet.jpg`（缩略图网格，便于全局浏览）
- 输出 `metadata.json`（EXIF 数据：拍摄时间、相机参数、镜头信息）

**耗时参考：** 150 张照片约 30-60 秒

### 第二步：视觉评分 — `vision_score.py`

```bash
python scripts/vision_score.py
```

Qwen3-VL-Plus 异步批量评分，特点：
- 并发 10 张同时评分
- 自动跳过低质照片（基于直方图预检）
- 指数退避重试（最多 3 次）
- 支持断点续传：`--resume`

**常用参数：**

```bash
# 测试模式（只测前 3 张，验证 API 连通性）
python scripts/vision_score.py --test 3

# 仅查看不运行（打印将处理哪些文件）
python scripts/vision_score.py --dry-run

# 断点续传（跳过已评分的照片）
python scripts/vision_score.py --resume
```

**输出：** `output/vision_scores.json`

每条评分包含：content_type、mood、shot_type、camera_angle、aesthetic_score、narrative_role、visual_hook、element_tags、composition_assessment 等 25+ 字段。

**耗时参考：** 150 张约 1-2 分钟

> **费用估算：** 约 ¥1/150 张（$0.0005/张）

### 第三步：评分与蓝图匹配 — `score_and_group.py`

```bash
python scripts/score_and_group.py --mode hybrid
```

**内部执行流程：**

```
1. 淘汰低质照片
   ├── 严重模糊（sharpness < 5）
   ├── 严重欠曝（underexposed > 20%）
   ├── 疑似截屏（aspect_ratio < 0.5）
   └── 极低美学分（aesthetic_score < 3.0）

2. 相似组聚类
   └── 基于 serial 号 + content_type

3. 综合评分
   └── 摄影(20) + 情绪(25) + 艺术(15) + 叙事(40)

4. 叙事蓝图匹配
   └── 4 套蓝图各贪心匹配 9 张照片

5. 裁剪建议
   └── 远景→中景/特写的裁剪参数

6. 保存输出 + 调用报告生成
```

**参数选项：**

```bash
# 手动指定版本
python scripts/score_and_group.py --mode hybrid --version 2_0

# 手动指定输出目录
python scripts/score_and_group.py --mode hybrid --output-dir output/2_0/hybrid

# 纯直方图模式
python scripts/score_and_group.py --mode histogram

# 纯视觉模式
python scripts/score_and_group.py --mode vision
```

**控制台输出示例：**

```
===== 方案 · 旅程叙事 =====
  📝 出发→路途→风景→人物→高潮→转折→沉淀→回味→归途
  匹配度: 78.5/100
  内容: {'风景': 2, '街拍': 3, '建筑': 2, '旅行': 2}
  景别: {'远景': 3, '中景': 4, '特写': 2}  有人物: 2/9
  角(1): 微信图片_202606...jpg  总分=85.3  [出发/建立] 内容=风景 景别=远景 心情=宁静
  C位(5): 微信图片_202606...jpg  总分=92.1  [高潮/人物] 内容=旅行 景别=中景 心情=温暖 👤
  ...
```

---

## 4. 评分模式选择

### 评分权重体系

| 维度 | 权重 | 数据来源（hybrid模式） | 评分内容 |
|:----:|:----:|:---------------------:|----------|
| 📷 **摄影** | **20** | 70% Qwen + 30% 直方图 | 构图、对焦、曝光、清晰度 |
| 💖 **情绪** | **25** | 70% Qwen + 30% 直方图 | 情感冲击、色彩氛围、亮度 |
| 🎨 **艺术** | **15** | 50% Qwen + 50% 直方图 | 美学质量、细节、饱和度 |
| 📖 **叙事** | **40** | Qwen 视觉评分 | 故事潜力、视觉钩子、景别角色、元素丰富度 |
| **总分** | **100** | | |

### 各模式对比

| 模式 | 摄影(20) | 情绪(25) | 艺术(15) | 叙事(40) | 成本 | 速度 |
|:----:|:--------:|:--------:|:--------:|:--------:|:----:|:----:|
| **histogram** | 直方图 | 直方图 | 直方图 | 0（无数据） | 免费 | 秒级 |
| **hybrid** ✅ | 70%Qwen+30%直方图 | 70%Qwen+30%直方图 | 50%Qwen+50%直方图 | Qwen | ~¥1 | ~2min |
| **vision** | Qwen | Qwen | Qwen | Qwen | ~¥1 | ~2min |

### 选择建议

| 场景 | 推荐模式 |
|------|:--------:|
| 快速测试、选片方向不明确 | histogram |
| 最终选片、发社交媒体的高质量需求 | **hybrid** ✅ |
| 研究 Qwen 评分效果、对比差异 | vision |
| 想对比直方图 vs 视觉评分的差异 | 两个都跑，看 compare_versions.py |

---

## 5. 输出文件说明

### 核心输出（`output/<版本>/<模式>/`）

| 文件 | 大小 | 内容说明 |
|------|:----:|----------|
| `score_matrix.csv` | ~30KB | 全量评分矩阵（排名、各维度分、总分、元数据） |
| `groups.json` | ~10KB | 相似组聚类（按 serial + content_type 分组） |
| `eliminated.json` | ~5KB | 淘汰照片及原因（模糊/欠曝/截屏/低分） |
| `narrative_plans.json` | ~20KB | 4 套叙事方案（蓝图→位置→照片→元数据） |
| `full_scored.json` | ~100KB | 全部候选评分数据（用于二次分析） |
| `top9_options.md` | ~50KB | **方案可视化报告** — 4 套方案的九宫格预览+叙事分析 |
| `final_report.md` | ~30KB | **最终推荐报告** — 推荐方案+检查清单+排除表 |
| `top30_visual.md` | ~20KB | Top30 评分矩阵（可视化版） |
| `copy_final_9.sh` | ~1KB | 一键复制选中照片到 `photos/selected/` |

### 全局共享文件（`output/`）

| 文件 | 说明 |
|------|------|
| `analysis.json` | 直方图分析数据（所有模式共用） |
| `vision_scores.json` | Qwen 视觉评分数据（所有模式共用） |

### 调色输出（`output/<版本>/retouched/`）

| 文件/目录 | 说明 |
|-----------|------|
| `journey_vintage/` | 旅程叙事 — Vintage Washed 风格 9 张 |
| `emotion_teal/` | 情绪弧线 — Teal & Orange 风格 9 张 |
| `light_cool/` | 光影对比 — Cool Minimal 风格 9 张 |
| `minimal_cool/` | 极简留白 — Cool Minimal 柔和版 9 张 |
| `retouched_report.md` | 调色前后对比报告 |
| `retouched_report.pdf` | 调色报告 PDF |

---

## 6. 叙事蓝图系统

### 4 套叙事方案

系统根据照片库的内容类型、情绪、景别等元素，自动评估 4 套蓝图的**素材完备度**，然后为各蓝图匹配最优的 9 张照片。

| 蓝图 | 叙事曲线 | 适合的照片库 |
|------|----------|-------------|
| 🚗 **旅程叙事** | 出发→路途→风景→人物→**高潮**→转折→沉淀→回味→归途 | 旅行、城市漫步、内容多样+有人物 |
| 💖 **情绪弧线** | 平静→温暖→**欢乐→高峰**→转折→沉淀→平复→余韵 | 人像、聚会、情感丰富的照片 |
| ☀️🌙 **光影对比** | 明亮→阳光→活跃→**光影**→阴影→暗夜→静谧→夜色 | 街拍、建筑、冷暖色调对比 |
| ▫️ **极简留白** | 空→出现→人物→再空→**聚焦**→纹理→留白→呼吸→空白 | 极简、建筑细节、大幅留白 |

### 查看素材完备度

```bash
python scripts/narrative_blueprint.py
```

输出示例：

```
🎯 叙事蓝图素材完备度评估
  旅程叙事    82%  ████████████████░░░░
  情绪弧线    70%  ██████████████░░░░░░
  光影对比    68%  ██████████████░░░░░░
  极简留白    52%  ██████████░░░░░░░░░░
```

匹配度 ≥ 60% = 该蓝图在当前素材库中可行。

### 匹配算法

每个蓝图定义了 9 个位置的约束条件（景别、情绪、内容类型、元素标签、人物需求、色温偏好），匹配算法计算每张照片对各位置的匹配度：

```
position_fit(照片, 位置要求) =
  shot_type匹配(25) + mood匹配(20) + content_type匹配(15)
  + element_tags共享×5 + people匹配(10) + color_tone匹配(10)
  + negative_space(10) + narrative_score×0.15
```

**裁剪加分：** 如果照片的 shot_type 可裁剪成目标景别（如 long_shot→close_up），获得 15 分（而非直接匹配的 25 分）。

**色温连续性：** 相邻位置色温差 > 40 → 匹配度 × 0.5；> 25 → × 0.75。

**C 位优先：** 最高分照片倾向于放置在中心位置（角(1)和 C 位优先级最高）。

---

## 7. 调色后处理

### 运行调色

```bash
python scripts/color_grade.py --version <版本号>
# 示例：python scripts/color_grade.py --version 3_1
```

> 必须先运行 `score_and_group.py --mode hybrid` 生成 `narrative_plans.json`

### 调色风格映射

| 叙事方案 | 调色风格 | 核心算法 |
|----------|----------|----------|
| **旅程叙事** | Vintage Washed 复古胶片 | 饱和-30%、黑场+18、R×1.08/B×0.92、对比度85% |
| **情绪弧线** | Teal & Orange 电影调色 | 暗部B+25/G+10、亮部R+20、S曲线15% |
| **光影对比** | Cool Minimal 冷调极简 | B+15%、R-10%、局部对比+20%、整体+5% |
| **极简留白** | Cool Minimal 柔和版 | 同上但强度0.3，效果更柔和 |

### 输出结构

每套方案的 9 张照片统一应用一种调色风格，确保九宫格视觉一致性。输出：

```
output/<版本>/retouched/
├── journey_vintage/           ← 9 张复古胶片调色
├── emotion_teal/              ← 9 张橙蓝电影调色
├── light_cool/                ← 9 张冷调极简
├── minimal_cool/              ← 9 张柔和冷调
├── retouched_report.md        ← 调色报告
└── retouched_report.pdf       ← 调色报告 PDF
```

---

## 8. PDF 导出

### 方式一：单文件转换

```bash
python scripts/convert_to_pdf.py output/3_0/hybrid/top9_options.md
python scripts/convert_to_pdf.py output/3_0/hybrid/final_report.md
```

### 方式二：批量默认转换

```bash
python scripts/convert_to_pdf.py
```

自动转换 `output/` 下的 4 个标准报告到 `pdfReport/`。

### 方式三：指定 PDF 输出目录

```bash
python scripts/convert_to_pdf.py output/3_0/hybrid/top9_options.md -o output/3_0/hybrid/
```

> **依赖：** Microsoft Edge 浏览器（使用 headless 无头模式打印）

---

## 9. 版本管理

### 版本格式

```
output/<主版本_次版本>/<模式>/
```

如：`output/3_1/hybrid/`

- **自动递增：** 已有 `1_0` 时自动升为 `1_1`
- **手动指定：** `--version 2_0`
- **输出目录：** `output/<version>/<mode>/`

### 版本历史

| 版本 | 里程碑 | 核心特性 |
|:----:|:------:|----------|
| 1_0 | 初始版 | 直方图评分 + 3 套方案 |
| 3_0 | 叙事升级 | 叙事蓝图引擎（4 套蓝图）+ 裁剪引擎 + 叙事评分(40%) |
| 3_1 | 色温调色 | 色温连续性检查 + 4 种统一调色风格 |

---

## 10. 常见问题

### Q: 如何更新照片库？
A: 把新照片放入 `image/`，然后重新运行完整流程：`preprocess.py` → `vision_score.py` → `score_and_group.py`。

### Q: 视觉评分失败/报错？
A: 
1. 检查 `.env` 中的 API 密钥是否正确
2. 用 `--test 3` 测试 API 连通性
3. 用 `--resume` 断点续传

### Q: 输出文件被 .gitignore 不显示在 git 中？
A: 这是预期的。输出文件不纳入版本控制。直接查看 `output/` 目录下的文件即可。

### Q: 如何跳过某些照片？
A: 直接移出 `image/` 目录。或在 `vision_score.py` 中调整 `ELIMINATION` 阈值。

### Q: 叙事方案不满意？
A: 叙事质量依赖 Qwen 视觉评分的准确性。确保先运行 `vision_score.py` 获得完整的 v2 评分数据。也可修改 `narrative_blueprint.py` 中的蓝图约束条件。

### Q: 如何查看上次选中的 9 张照片？
A: 查看 `photos/selected/` 目录，或查看 `output/<版本>/hybrid/copy_final_9.sh` 中列出的文件名。

### Q: 控制台中文乱码？
A: 脚本已内置 `sys.stdout.reconfigure(encoding="utf-8")` 处理 Windows GBK 兼容。如果仍有问题，在终端中执行 `chcp 65001` 切换到 UTF-8。

### Q: 如何只做调色不重新评分？
A: 直接运行 `python scripts/color_grade.py --version <现有版本>`，它会读取已存在的 `narrative_plans.json`。
