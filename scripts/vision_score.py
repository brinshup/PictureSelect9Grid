"""
视觉模型评分 — 使用 Qwen3-VL-Plus 异步批量打分。
特性：异步并发 (aiohttp), base64 编码, 结构化 JSON, 指数退避重试, 费用估算。
用法: python scripts/vision_score.py [--test N] [--dry-run] [--resume]
"""
import os, sys, json, base64, asyncio, argparse, time
from pathlib import Path

# Windows GBK 兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import aiohttp, shutil

# ── 常量 ──────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
RESIZED_DIR = PROJECT_DIR / "photos" / "resized"
OUTPUT_DIR = PROJECT_DIR / "output"
# Vision scores saved to global output/ so all modes can find it
VISION_SCORES_PATH = OUTPUT_DIR / "vision_scores.json"
ANALYSIS_PATH = OUTPUT_DIR / "analysis.json"

# 淘汰阈值（同 score_and_group.py）
ELIMINATION = {
    "sharpness_min": 5,
    "underexposed_max": 20,
    "aspect_ratio_min": 0.5,
}

# ── Prompt ────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a professional photography critic and cinematic storytelling analyst. "
    "Analyze every photo honestly. Do NOT inflate scores. "
    "A score of 7/10 means 'good work', 8+ means 'excellent and rare', 9+ means 'museum quality'. "
    "Be strict and note flaws. Pay special attention to narrative potential for social media grid storytelling. "
    "Always respond in valid JSON only, no extra text."
)

USER_PROMPT_TEMPLATE = (
    "Analyze this photo for a social media 3x3 photo grid story. "
    "Think of the 9-grid as a mini-film: each photo is a 'shot' that contributes to a narrative flow. "
    "Return a JSON object with these exact fields:\n\n"
    "{\n"
    '  "content_type": "portrait|landscape|food|architecture|night|street|animal|macro|abstract|group_photo|still_life|travel",\n'
    '  "has_people": true/false,\n'
    '  "face_count": 0-99,\n'
    '  "expression_quality": "excellent|natural|awkward|none",\n'
    '  "composition_assessment": {\n'
    '    "rule_of_thirds": 1-10,\n'
    '    "leading_lines": 1-10,\n'
    '    "balance": 1-10,\n'
    '    "framing": 1-10,\n'
    '    "negative_space": 1-10\n'
    '  },\n'
    '  "focus_and_exposure": {\n'
    '    "focus_quality": 1-10,\n'
    '    "exposure_quality": 1-10,\n'
    '    "lighting_quality": 1-10,\n'
    '    "lighting_direction": "front|side|back|top|diffuse|none"\n'
    '  },\n'
    '  "depth_of_field": "shallow|moderate|deep",\n'
    '  "color_harmony": 1-10,\n'
    '  "dominant_colors": ["list of 2-4 dominant color names in English"],\n'
    '  "color_palette_mood": "warm|cool|neutral|vibrant|muted",\n'
    '  "mood": "serene|dramatic|warm|melancholic|energetic|peaceful|mysterious|romantic|joyful|quiet|cool|nostalgic",\n'
    '  "emotional_impact": 1-10,\n'
    '  "storytelling_potential": 1-10,\n'
    '  "subject_prominence": 1-10,\n'
    '  "aesthetic_score": 1.0-10.0 (overall, be honest),\n'
    '  "shot_type": "wide|long_shot|full|medium|close_up|extreme_close_up|detail",\n'
    '  "camera_angle": "eye_level|high_angle|low_angle|dutch|birdseye|overhead",\n'
    '  "key_elements": ["list of 2-4 visible subjects/elements in Chinese, e.g. 天空, 建筑, 人物背影"],\n'
    '  "subject_description": "brief Chinese description of main subject",\n'
    '  "narrative_role": "establishing|main_subject|supporting|transient|closure|atmosphere",\n'
    '  "visual_hook": 1-10 (how strongly this photo grabs attention as a first impression),\n'
    '  "element_tags": ["list of 2-5 English tags: sky, water, architecture, silhouette, reflection, texture, pattern, symmetry, leading_line, frame_within_frame, shallow_dof, motion_blur, shadow, neon, greenery, road, window, door, stairs, bridge, crowd, solo, hand, eye, profile, back_view, food, drink, pet, flower, light_ray, fog, rainbow, star, moon, cityscape, landscape, seascape, mountain, forest, minimal, geometric, vintage, dark, bright, colorful, monochrome, golden_hour, blue_hour, night, indoor, outdoor, urban, rural, abstract"],\n'
    '  "dominant_line_direction": "horizontal|vertical|diagonal|curved|none",\n'
    '  "recommended_grid_positions": [array of grid numbers 1-9 the photo suits best],\n'
    '  "reasoning": "1-2 sentences in Chinese explaining narrative role and composition quality"\n'
    "}\n\n"
    "REMEMBER: respond with ONLY the JSON object, nothing else."
)


# ── 加载配置 ────────────────────────────────────────
def load_config():
    """从 .env 或环境变量加载配置"""
    env_path = PROJECT_DIR / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip()
                    if key not in os.environ:
                        os.environ[key] = val

    cfg = {
        "api_key": os.environ.get("QWEN_API_KEY", ""),
        "api_base": os.environ.get("QWEN_API_BASE",
                                   "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        "model": os.environ.get("QWEN_MODEL", "qwen3-vl-plus"),
        "max_concurrency": int(os.environ.get("QWEN_MAX_CONCURRENCY", "10")),
    }
    return cfg


# ── 数据准备 ────────────────────────────────────────
def should_skip(info, cfg_elim=None):
    """基于直方图数据判断是否应跳过"""
    if cfg_elim is None:
        cfg_elim = ELIMINATION
    reasons = []
    if info.get("sharpness", 99) < cfg_elim["sharpness_min"]:
        reasons.append("模糊")
    if info.get("underexposed_pct", 0) > cfg_elim["underexposed_max"]:
        reasons.append("严重欠曝")
    if info.get("aspect_ratio", 1) < cfg_elim["aspect_ratio_min"]:
        reasons.append("截屏")
    return reasons


def load_candidates(analysis_path=ANALYSIS_PATH):
    """加载候选照片列表（跳过已淘汰的）"""
    if not analysis_path.exists():
        print("⚠️  analysis.json 不存在，将处理所有 resized 照片")
        return sorted(p.name for p in RESIZED_DIR.glob("*.jpg")), {}, {}

    with open(analysis_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    info_map = {p["filename"]: p for p in data.get("photos", [])}

    candidates = []
    skipped = []
    for p in data.get("photos", []):
        jpg_name = Path(p["filename"]).with_suffix(".jpg").name
        reasons = should_skip(p)
        if reasons:
            skipped.append((jpg_name, reasons))
        else:
            candidates.append(jpg_name)

    # 检查文件实际存在
    existing = set(f.name for f in RESIZED_DIR.glob("*.jpg") if f.name != "metadata.json")
    candidates = [c for c in candidates if c in existing]

    return candidates, info_map, skipped


def encode_image(filename):
    """返回 (filename, base64_string)"""
    path = RESIZED_DIR / filename
    if not path.exists():
        return filename, None
    data = path.read_bytes()
    return filename, base64.b64encode(data).decode()


# ── API 调用 ────────────────────────────────────────
def parse_response(content):
    """解析模型返回的 JSON，容错处理"""
    if isinstance(content, dict):
        return content
    text = str(content).strip()
    # 去掉可能的 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text)


def validate_and_fill(result):
    """补全缺失字段，确保结构完整"""
    defaults = {
        "content_type": "unknown",
        "has_people": False,
        "face_count": 0,
        "expression_quality": "none",
        "composition_assessment": {"rule_of_thirds": 5, "leading_lines": 5, "balance": 5, "framing": 5, "negative_space": 5},
        "focus_and_exposure": {"focus_quality": 5, "exposure_quality": 5, "lighting_quality": 5, "lighting_direction": "none"},
        "depth_of_field": "moderate",
        "color_harmony": 5,
        "dominant_colors": [],
        "color_palette_mood": "neutral",
        "mood": "neutral",
        "emotional_impact": 5,
        "storytelling_potential": 5,
        "subject_prominence": 5,
        "aesthetic_score": 5.0,
        "shot_type": "medium",
        "camera_angle": "eye_level",
        "key_elements": [],
        "subject_description": "",
        "narrative_role": "supporting",
        "visual_hook": 5,
        "element_tags": [],
        "dominant_line_direction": "none",
        "recommended_grid_positions": [5],
        "reasoning": "",
    }
    for k, v in defaults.items():
        if k not in result:
            result[k] = v
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if sub_k not in result[k]:
                    result[k][sub_k] = sub_v
    return result


async def analyze_one(session, filename, image_b64, api_base, model):
    """分析单张照片"""
    url = f"{api_base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                    {"type": "text", "text": USER_PROMPT_TEMPLATE},
                ],
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 1200,
    }

    async with session.post(url, json=payload) as resp:
        if resp.status == 429:
            raise aiohttp.ClientResponseError(
                resp.request_info, resp.history, status=429, message="Rate limited"
            )
        resp.raise_for_status()
        data = await resp.json()

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    result = parse_response(content)
    result = validate_and_fill(result)
    result["filename"] = filename
    result["_usage"] = usage
    return result


async def analyze_with_retry(session, filename, image_b64, api_base, model, max_retries=3):
    """带指数退避重试的分析"""
    for attempt in range(max_retries):
        try:
            return await analyze_one(session, filename, image_b64, api_base, model)
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                wait = 2 ** (attempt + 1)
                print(f"\r  ⏳ 限流! {filename[:30]} 等待 {wait}s 重试 ({attempt+1}/{max_retries})...", end="", flush=True)
                await asyncio.sleep(wait)
                continue
            if attempt == max_retries - 1:
                return {"filename": filename, "error": str(e), "aesthetic_score": None}
            wait = 2 ** attempt
            print(f"\r  🔄 重试 {filename[:30]} ({attempt+1}/{max_retries}) 等待 {wait}s...  ", end="", flush=True)
            await asyncio.sleep(wait)
        except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError) as e:
            if attempt == max_retries - 1:
                return {"filename": filename, "error": str(e), "aesthetic_score": None}
            wait = 2 ** attempt
            print(f"\r  🔄 重试 {filename[:30]} ({attempt+1}/{max_retries}) 等待 {wait}s...  ", end="", flush=True)
            await asyncio.sleep(wait)
    return {"filename": filename, "error": "unknown", "aesthetic_score": None}


async def analyze_many(candidates, api_base, api_key, model, max_concurrency=10):
    """异步并发分析全部候选照片"""
    sem = asyncio.Semaphore(max_concurrency)
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=60, connect=15)

    total = len(candidates)
    completed = 0
    success_count = 0
    fail_count = 0
    total_input_tokens = 0
    total_output_tokens = 0
    t_start = time.time()

    # 终端宽度检测
    term_width = 80
    try:
        import shutil
        term_width = shutil.get_terminal_size((80, 20)).columns
    except Exception:
        pass

    def print_status_line():
        """打印一行实时状态（覆盖前一行）"""
        elapsed = time.time() - t_start
        rate = completed / elapsed if elapsed > 0 else 0
        eta_sec = (total - completed) / rate if rate > 0 else 0
        pct = completed / total * 100 if total > 0 else 0
        cost_est = (total_input_tokens / 1_000_000 * 0.20) + (total_output_tokens / 1_000_000 * 1.60)

        bar_len = min(20, term_width - 70)
        filled = int(bar_len * completed / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)

        line = (
            f"\r  {bar} {completed}/{total} ({pct:.0f}%) "
            f"✅{success_count} ❌{fail_count} "
            f"⏱{elapsed:.0f}s ETA{eta_sec:.0f}s "
            f"💰${cost_est:.4f}   "
        )
        # 截断到终端宽度
        print(line[:term_width], end="", flush=True)

    async def bounded_analyze(session, filename, idx):
        nonlocal completed, success_count, fail_count, total_input_tokens, total_output_tokens
        async with sem:
            # ── 编码阶段 ──
            print(f"\r  ▶ [{idx+1}/{total}] 编码 {filename[:40]}...    ", end="", flush=True)
            fname, b64 = encode_image(filename)
            if b64 is None:
                completed += 1
                fail_count += 1
                print(f"\r  ✗ [{idx+1}/{total}] {filename[:40]} — 文件不存在          ")
                return {"filename": filename, "error": "file not found", "aesthetic_score": None}

            # ── API 调用阶段 ──
            print(f"\r  ↻ [{idx+1}/{total}] 发送 {filename[:40]} → API...", end="", flush=True)
            result = await analyze_with_retry(session, fname, b64, api_base, model)

            completed += 1
            usage = result.get("_usage", {})
            total_input_tokens += usage.get("prompt_tokens", 0)
            total_output_tokens += usage.get("completion_tokens", 0)

            if result.get("aesthetic_score") is not None:
                success_count += 1
                score = result["aesthetic_score"]
                mood = result.get("mood", "?")
                shot = result.get("shot_type", "?")
                print(f"\r  ✓ [{completed}/{total}] {filename[:36]} 美学={score} 情绪={mood} 景别={shot}   ")
            else:
                fail_count += 1
                err = result.get("error", "unknown")[:30]
                print(f"\r  ✗ [{completed}/{total}] {filename[:36]} 失败: {err}   ")

            # 实时状态行
            print_status_line()
            return result

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        tasks = [bounded_analyze(session, f, i) for i, f in enumerate(candidates)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 展平异常
    final = []
    for r in results:
        if isinstance(r, Exception):
            final.append({"filename": "unknown", "error": str(r), "aesthetic_score": None})
        else:
            final.append(r)

    print()  # 换行结束状态行
    return final


# ── 费用估算 ────────────────────────────────────────
def estimate_cost(results):
    total_input = sum(r.get("_usage", {}).get("prompt_tokens", 0) for r in results if "_usage" in r)
    total_output = sum(r.get("_usage", {}).get("completion_tokens", 0) for r in results if "_usage" in r)
    cost = (total_input / 1_000_000 * 0.20) + (total_output / 1_000_000 * 1.60)
    return total_input, total_output, cost


# ── 文件保存 ────────────────────────────────────────
def save_results(results, model, candidates_count, skipped_info=None):
    """保存到 output/vision_scores.json"""
    successful = [r for r in results if r.get("aesthetic_score") is not None]
    failed = [r for r in results if r.get("aesthetic_score") is None]
    total_input, total_output, cost_est = estimate_cost(results)

    output = {
        "scored_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "prompt_version": 2,
        "total_candidates": candidates_count,
        "successful": len(successful),
        "failed": len(failed),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_estimate_usd": round(cost_est, 4),
        "skipped": skipped_info or [],
        "scores": successful,
        "errors": [{"filename": r["filename"], "error": r.get("error", "unknown")} for r in failed],
    }

    with open(VISION_SCORES_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output, successful, failed


# ── 主流程 ───────────────────────────────────────────
async def main_async(cfg, test_n=None, dry_run=False, resume=False, version=None):
    print(f"\n{'=' * 60}")
    print(f"  Qwen3-VL-Plus 视觉评分脚本")
    print(f"  模型: {cfg['model']}  并发: {cfg['max_concurrency']}")
    print(f"{'=' * 60}\n")

    # 1. 加载候选
    candidates, info_map, skipped = load_candidates()

    if test_n and test_n < len(candidates):
        candidates = candidates[:test_n]
        print(f"🧪 测试模式: 仅处理前 {test_n} 张\n")
    elif resume and VISION_SCORES_PATH.exists():
        with open(VISION_SCORES_PATH, "r", encoding="utf-8") as f:
            prev = json.load(f)
        done = {s["filename"] for s in prev.get("scores", [])}
        candidates = [c for c in candidates if c not in done]
        print(f"📋 恢复模式: {len(done)} 张已完成, {len(candidates)} 张待处理\n")

    print(f"📷 候选照片: {len(candidates)} 张")
    print(f"🗑️  跳过: {len(skipped)} 张")
    if test_n is None:
        print(f"💰 预估费用: ~${len(candidates) * 0.0005:.3f} (约 ¥{len(candidates) * 0.0005 * 7.2:.2f})")
    print()

    if dry_run:
        print("🔍 Dry-run 模式 — 仅打印将处理的文件，不调用 API:\n")
        for i, c in enumerate(candidates[:20]):
            print(f"  {i+1}. {c}")
        if len(candidates) > 20:
            print(f"  ... (还有 {len(candidates) - 20} 张)")
        return

    if not cfg["api_key"] or "请替换" in cfg["api_key"]:
        print("❌ 未设置 QWEN_API_KEY，请在 .env 文件中配置 API 密钥")
        print("   获取方式: https://dashscope.aliyun.com/")
        return

    # 2. 执行分析
    t_start = time.time()
    results = await analyze_many(
        candidates,
        api_base=cfg["api_base"],
        api_key=cfg["api_key"],
        model=cfg["model"],
        max_concurrency=cfg["max_concurrency"],
    )
    elapsed = time.time() - t_start

    # 3. 保存
    output, successful, failed = save_results(
        results, cfg["model"], len(candidates),
        skipped_info=[{"filename": f, "reasons": r} for f, r in skipped],
    )

    # 4. 详细摘要
    total_candidates = len(candidates)
    print(f"\n{'=' * 60}")
    print(f"  🏁 评分完成！耗时 {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  {'─' * 58}")
    succ_pct = len(successful) / total_candidates * 100 if total_candidates else 0
    avg_speed = total_candidates / elapsed if elapsed > 0 else 0
    print(f"  总候选:      {total_candidates} 张")
    print(f"  成功:        {len(successful)} 张 ({succ_pct:.0f}%)")
    print(f"  失败:        {len(failed)} 张")
    skipped_count = len(skipped) if skipped else 0
    print(f"  跳过:        {skipped_count} 张")
    print(f"  平均速度:    {avg_speed:.1f} 张/秒" if avg_speed else "")
    print(f"  {'─' * 58}")
    print(f"  输入 tokens: {output['input_tokens']:,}")
    print(f"  输出 tokens: {output['output_tokens']:,}")
    avg_input = output['input_tokens'] / len(successful) if successful else 0
    avg_output = output['output_tokens'] / len(successful) if successful else 0
    print(f"  平均/张:     {avg_input:.0f} in / {avg_output:.0f} out")
    if output["cost_estimate_usd"] > 0:
        cost_cny = output['cost_estimate_usd'] * 7.2
        per_photo = output['cost_estimate_usd'] / len(successful) if successful else 0
        print(f"  {'─' * 58}")
        print(f"  估算费用:    ${output['cost_estimate_usd']:.4f} (≈ ¥{cost_cny:.2f})")
        print(f"  单张均价:    ${per_photo:.6f} (≈ ¥{per_photo*7.2:.4f})")
    print(f"  {'─' * 58}")
    print(f"  结果文件:    {VISION_SCORES_PATH}")
    print(f"{'=' * 60}")
    # 同步到版本子目录（精确到分钟，与 score_and_group.py 一致）
    from datetime import datetime
    _ver = version or datetime.now().strftime("%Y%m%d_%H%M")
    for sub in ['hybrid', 'vision']:
        subdir = OUTPUT_DIR / _ver / sub
        subdir.mkdir(parents=True, exist_ok=True)
        shutil.copy(VISION_SCORES_PATH, subdir / 'vision_scores.json')

    print(f"\n  📋 下一步:")
    print(f"     python scripts/score_and_group.py --mode hybrid    # 混合评分 (推荐)")
    print(f"     python scripts/score_and_group.py --mode histogram  # 纯直方图 (对比)")
    print(f"     python scripts/score_and_group.py --mode vision     # 纯视觉评分")
    print(f"\n  📂 输出目录结构:")
    print(f"     output/{_ver}/hybrid/    ← 混合评分结果")
    print(f"     output/{_ver}/vision/    ← 纯视觉结果")
    print(f"     output/<版本>/histogram/ ← 纯直方图结果")
    print()


def main():
    parser = argparse.ArgumentParser(description="Qwen3-VL-Plus 视觉评分")
    parser.add_argument("--test", type=int, default=None, metavar="N", help="仅处理前 N 张")
    parser.add_argument("--dry-run", action="store_true", help="不调用 API，仅打印将处理哪些文件")
    parser.add_argument("--resume", action="store_true", help="断点续传（跳过已评分照片）")
    parser.add_argument("--version", type=str, default=None, help="版本标签 (默认: 自动时间戳 YYYYMMDD_HHMM)")
    args = parser.parse_args()

    cfg = load_config()
    asyncio.run(main_async(cfg, test_n=args.test, dry_run=args.dry_run, resume=args.resume, version=args.version))


if __name__ == "__main__":
    main()
