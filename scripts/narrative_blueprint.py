"""
叙事蓝图引擎 — Element Inventory + Blueprint Engine + 素材完备度评估
输入: output/analysis.json, output/vision_scores.json
输出: 素材清单 + 蓝图匹配度 + 位置要求

本次升级：通过 get_blueprints(photos) 动态生成蓝图，
不再使用硬编码的 4 套固定蓝图。

用法:
    python scripts/narrative_blueprint.py          # 打印元素清单 (静态蓝图参考)
    python -c "from scripts.narrative_blueprint import ..."
"""
import json, sys
from pathlib import Path
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"

# ── 动态蓝图缓存 ──
_DYNAMIC_BLUEPRINTS = None

# ── 翻译映射（同 score_and_group.py）──
CN_CONTENT_TYPE = {
    'landscape': '风景', 'portrait': '人像', 'architecture': '建筑',
    'street': '街拍', 'travel': '旅行', 'food': '美食', 'night': '夜景',
    'animal': '动物', 'macro': '微距', 'abstract': '抽象', 'group_photo': '合影',
    'still_life': '静物', 'unknown': '未知',
}
CN_MOOD = {
    'serene': '宁静', 'dramatic': '戏剧', 'warm': '温暖', 'melancholic': '忧郁',
    'energetic': '活力', 'peaceful': '平和', 'mysterious': '神秘', 'romantic': '浪漫',
    'joyful': '愉悦', 'quiet': '安静', 'cool': '冷调', 'nostalgic': '怀旧',
    'neutral': '中性',
}
CN_SHOT_TYPE = {
    'wide': '广角', 'long_shot': '远景', 'full': '全景', 'medium': '中景',
    'medium_full': '中全景', 'close_up': '特写', 'extreme_close_up': '极特写',
    'detail': '细节', 'medium_shot': '中景', 'unknown': '未知',
}

# ── 可裁剪性映射 ──
CAN_CROP_MAP = {
    'wide': ['wide'],
    'long_shot': ['wide', 'medium_full', 'medium', 'close_up', 'detail'],
    'full': ['medium_full', 'medium'],
    'medium_full': ['medium', 'close_up'],
    'medium': ['close_up', 'detail'],
    'medium_shot': ['close_up', 'detail'],
    'close_up': ['detail'],
    'extreme_close_up': ['detail'],
    'detail': ['detail'],
}


# ── 动态蓝图加载（静态 + 动态 合并）──

def get_blueprints(photos=None):
    """获取所有可用蓝图：4 套基础方案 + 动态发现主题

    基础方案：旅程叙事、情绪弧线、光影对比、极简留白（固定 4 套）
    动态发现：根据照片 element_tags 自动发现的叙事主题（0-5 套）

    返回: {"journey": {...}, "emotion_arc": {...}, ...,
           "discovered_0": {...}, ...}
    """
    global _DYNAMIC_BLUEPRINTS
    if _DYNAMIC_BLUEPRINTS is not None:
        return _DYNAMIC_BLUEPRINTS

    # 先加基础方案
    merged = dict(_STATIC_BLUEPRINTS)

    # 再加动态发现
    if photos:
        try:
            from scripts.theme_discovery import discover_and_generate_blueprints
            dynamic = discover_and_generate_blueprints(photos) or {}
            if dynamic:
                for k, v in dynamic.items():
                    # 标记为自动发现，避免与静态 key 冲突
                    merged[k] = v
                print(f"\n  🎯 另发现 {len(dynamic)} 个自动叙事主题")
        except ImportError as e:
            print(f"  ⚠️ 主题发现模块未加载: {e}")

    _DYNAMIC_BLUEPRINTS = merged
    return merged


def clear_blueprint_cache():
    """清除动态蓝图缓存（照片集变化时调用）"""
    global _DYNAMIC_BLUEPRINTS
    _DYNAMIC_BLUEPRINTS = None


# ========== 1. 数据加载 ==========

def load_data():
    """加载 analysis.json 和 vision_scores.json"""
    analysis_path = OUTPUT_DIR / "analysis.json"
    vision_path = OUTPUT_DIR / "vision_scores.json"

    if not analysis_path.exists():
        print(f"❌ {analysis_path} 不存在，请先运行预处理")
        sys.exit(1)

    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    vision_map = {}
    if vision_path.exists():
        with open(vision_path, "r", encoding="utf-8") as f:
            vs = json.load(f)
        for s in vs.get("scores", []):
            vision_map[s["filename"]] = s

    # 合并数据
    photos = []
    for ap in analysis.get("photos", []):
        jpg_name = ap["filename"].replace(".heic", ".jpg")
        v = vision_map.get(jpg_name, {})
        entry = {**ap, **v}
        entry["filename"] = jpg_name
        # 填充缺失字段
        entry.setdefault("content_type", "unknown")
        entry.setdefault("mood", "neutral")
        entry.setdefault("shot_type", "unknown")
        entry.setdefault("has_people", False)
        entry.setdefault("face_count", 0)
        entry.setdefault("element_tags", [])
        entry.setdefault("narrative_role", "supporting")
        entry.setdefault("visual_hook", 5)
        entry.setdefault("composition_assessment", {})
        entry.setdefault("negative_space", 5)
        entry["negative_space"] = entry["composition_assessment"].get("negative_space", 5)
        photos.append(entry)

    return photos


# ========== 2. Element Inventory ==========

def build_inventory(photos):
    """从候选照片生成元素清单"""
    if not photos:
        return {"error": "no photos"}

    inv = {
        "total": len(photos),
        "has_vision": any(p.get("aesthetic_score") for p in photos),
    }

    # 内容类型
    cts = Counter()
    for p in photos:
        for ct in p.get("content_type", "unknown").split("|"):
            cts[ct.strip()] += 1
    inv["content_type"] = dict(cts.most_common())

    # 心情
    moods = Counter()
    for p in photos:
        for m in p.get("mood", "neutral").split("|"):
            moods[m.strip()] += 1
    inv["mood"] = dict(moods.most_common())

    # 景别
    shots = Counter(p.get("shot_type", "unknown") for p in photos)
    inv["shot_type"] = dict(shots.most_common())

    # 角度
    angles = Counter(p.get("camera_angle", "unknown") for p in photos)
    inv["camera_angle"] = dict(angles.most_common())

    # 人物
    inv["people"] = sum(1 for p in photos if p.get("has_people"))
    inv["people_pct"] = round(inv["people"] / len(photos) * 100, 1)

    # 元素标签
    tag_counts = Counter()
    for p in photos:
        tags = p.get("element_tags", [])
        if isinstance(tags, list):
            for t in tags:
                tag_counts[t] += 1
    inv["top_element_tags"] = dict(tag_counts.most_common(20))

    # 色彩分析
    color_temps = [p.get("color_temp", 0) for p in photos if p.get("color_temp") is not None]
    inv["color_temp"] = {
        "min": round(min(color_temps), 1) if color_temps else 0,
        "max": round(max(color_temps), 1) if color_temps else 0,
        "avg": round(sum(color_temps) / len(color_temps), 1) if color_temps else 0,
    }

    # 留白照片（negative_space >= 7）
    inv["negative_space_photos"] = sum(1 for p in photos if p.get("negative_space", 0) >= 7)
    inv["negative_space_high"] = sum(1 for p in photos if p.get("negative_space", 0) >= 8)

    # 可裁剪出特写的照片（long_shot / full 类型）
    inv["close_up_potential"] = sum(
        1 for p in photos if p.get("shot_type", "") in ("long_shot", "full", "wide")
    )

    # 暖调/冷调
    warm = sum(1 for p in photos if p.get("color_temp", 0) > 15)
    cool = sum(1 for p in photos if p.get("color_temp", 0) < -15)
    neutral_t = len(photos) - warm - cool
    inv["color_tone"] = {"warm": warm, "cool": cool, "neutral": neutral_t}

    # 构图质量
    comp_scores = [p.get("composition_assessment", {}).get("rule_of_thirds", 5) for p in photos]
    inv["avg_rule_of_thirds"] = round(sum(comp_scores) / len(comp_scores), 1) if comp_scores else 0

    return inv


def print_inventory(photos):
    """打印可读的元素清单"""
    inv = build_inventory(photos)
    print(f"\n{'=' * 50}")
    print("  📊 元素清单 (Element Inventory)")
    print(f"{'=' * 50}")
    print(f"  总候选照片: {inv['total']} 张")
    if inv.get('has_vision'):
        print(f"  含视觉评分: ✅")
    print(f"\n  📷 内容类型:")
    for k, v in inv["content_type"].items():
        bar = "█" * max(v // 3, 1)
        print(f"    {CN_CONTENT_TYPE.get(k, k):<8} {v:>3}张 {bar}")
    print(f"\n  💫 心情:")
    for k, v in inv["mood"].items():
        bar = "█" * max(v // 3, 1)
        print(f"    {CN_MOOD.get(k, k):<8} {v:>3}张 {bar}")
    print(f"\n  🎬 景别:")
    for k, v in inv["shot_type"].items():
        bar = "█" * max(v // 3, 1)
        print(f"    {CN_SHOT_TYPE.get(k, k):<10} {v:>3}张 {bar}")
    print(f"\n  👤 有人物: {inv['people']}/{inv['total']} ({inv['people_pct']}%)")
    print(f"\n  🏷️  元素标签 Top 10:")
    for i, (k, v) in enumerate(list(inv["top_element_tags"].items())[:10]):
        print(f"    {i+1}. {k}: {v}张")
    print(f"\n  🌡️  色温: 冷调{inv['color_tone']['cool']} 暖调{inv['color_tone']['warm']} 中性{inv['color_tone']['neutral']}")
    print(f"     min={inv['color_temp']['min']} max={inv['color_temp']['max']} avg={inv['color_temp']['avg']}")
    print(f"\n  🖼️  留白照片 (negative>=7): {inv['negative_space_photos']}张")
    print(f"  ✂️  可裁特写: {inv['close_up_potential']}张 (远景/全景可裁切)")
    print(f"  📐 平均三分法得分: {inv['avg_rule_of_thirds']}/10")
    return inv


# ========== 3. Narrative Blueprints ==========

_STATIC_BLUEPRINTS = {
    "journey": {
        "name": "旅程叙事",
        "name_en": "Journey Arc",
        "description": "出发→路途→风景→人物→高潮→转折→沉淀→回味→归途。适合内容类型多样、有风景有人物的照片集。",
        "suitable_for": ["content_type_diverse", "has_people", "mixed_moods"],
        "positions": [
            {"role": "出发/建立", "shot_types": ["long_shot", "wide"], "moods": ["serene", "mysterious", "peaceful"], "content_types": ["landscape", "architecture", "travel"], "element_tags": ["sky", "horizon", "road"], "color_tone": "cool", "needs_people": False},
            {"role": "路途", "shot_types": ["medium", "medium_full"], "moods": ["warm", "energetic", "serene"], "content_types": ["street", "travel", "landscape"], "element_tags": ["road", "sign", "tree"], "color_tone": "cool", "needs_people": False},
            {"role": "风景过渡", "shot_types": ["long_shot", "wide"], "moods": ["serene", "dramatic", "peaceful"], "content_types": ["landscape", "architecture"], "element_tags": ["sky", "horizon", "water", "mountain"], "color_tone": "neutral", "needs_people": False},
            {"role": "遇见", "shot_types": ["medium_full", "medium"], "moods": ["warm", "mysterious", "serene"], "content_types": ["street", "architecture", "travel"], "element_tags": ["building", "shadow", "archway"], "color_tone": "neutral", "needs_people": False},
            {"role": "高潮/人物", "shot_types": ["medium", "close_up", "medium_full"], "moods": ["energetic", "romantic", "joyful", "warm"], "content_types": ["portrait", "travel", "street"], "element_tags": ["hand", "profile", "smile"], "color_tone": "neutral", "needs_people": True},
            {"role": "继续前行", "shot_types": ["medium", "medium_full"], "moods": ["warm", "energetic", "serene"], "content_types": ["travel", "street", "landscape"], "element_tags": ["road", "shadow", "tree"], "color_tone": "neutral", "needs_people": False},
            {"role": "沉淀", "shot_types": ["long_shot", "wide"], "moods": ["serene", "melancholic", "quiet"], "content_types": ["landscape", "architecture"], "element_tags": ["sky", "horizon", "silhouette"], "color_tone": "cool", "needs_people": False},
            {"role": "回味", "shot_types": ["medium_full", "medium"], "moods": ["warm", "serene", "nostalgic"], "content_types": ["street", "portrait", "travel"], "element_tags": ["back_view", "hand", "light_ray"], "color_tone": "cool", "needs_people": False},
            {"role": "归途/收束", "shot_types": ["long_shot", "wide"], "moods": ["serene", "mysterious", "peaceful", "nostalgic"], "content_types": ["landscape", "architecture", "travel"], "element_tags": ["horizon", "sky", "mountain", "silhouette"], "color_tone": "cool", "needs_people": False},
        ],
    },
    "emotion_arc": {
        "name": "情绪弧线",
        "name_en": "Emotion Arc",
        "description": "平静→温暖→欢乐→情绪高峰→核心→转折→沉淀→平复→余韵。适合有人物、情绪层次丰富的照片集。",
        "suitable_for": ["has_people", "mixed_moods", "street"],
        "positions": [
            {"role": "平静起点", "shot_types": ["long_shot", "wide"], "moods": ["serene", "peaceful", "quiet"], "content_types": ["landscape", "architecture"], "element_tags": ["sky", "horizon"], "color_tone": "cool", "needs_people": False},
            {"role": "温暖引入", "shot_types": ["medium_full", "medium"], "moods": ["warm", "serene"], "content_types": ["street", "travel", "landscape"], "element_tags": ["light_ray", "tree", "shadow"], "color_tone": "neutral", "needs_people": False},
            {"role": "情绪上升", "shot_types": ["medium", "close_up"], "moods": ["joyful", "energetic", "warm"], "content_types": ["portrait", "street", "travel"], "element_tags": ["hand", "smile", "crowd"], "color_tone": "warm", "needs_people": True},
            {"role": "情绪高峰", "shot_types": ["close_up", "medium"], "moods": ["romantic", "dramatic", "joyful"], "content_types": ["portrait", "street"], "element_tags": ["profile", "eye", "hand"], "color_tone": "warm", "needs_people": True},
            {"role": "核心情绪", "shot_types": ["medium", "medium_full"], "moods": ["energetic", "warm", "joyful"], "content_types": ["portrait", "travel", "street"], "element_tags": ["crowd", "smile", "backlight"], "color_tone": "warm", "needs_people": True},
            {"role": "情绪转折", "shot_types": ["long_shot", "wide"], "moods": ["mysterious", "melancholic", "dramatic"], "content_types": ["landscape", "architecture"], "element_tags": ["silhouette", "sky", "shadow"], "color_tone": "cool", "needs_people": False},
            {"role": "沉淀", "shot_types": ["medium", "medium_full"], "moods": ["serene", "quiet", "melancholic"], "content_types": ["travel", "street", "landscape"], "element_tags": ["back_view", "road", "shadow"], "color_tone": "neutral", "needs_people": False},
            {"role": "平复", "shot_types": ["medium_full", "long_shot"], "moods": ["serene", "peaceful", "quiet"], "content_types": ["landscape", "architecture", "street"], "element_tags": ["horizon", "water", "sky"], "color_tone": "neutral", "needs_people": False},
            {"role": "余韵", "shot_types": ["long_shot", "wide"], "moods": ["serene", "nostalgic", "peaceful", "quiet"], "content_types": ["landscape", "architecture"], "element_tags": ["horizon", "sky", "silhouette", "moon"], "color_tone": "cool", "needs_people": False},
        ],
    },
    "light_shadow": {
        "name": "光影对比",
        "name_en": "Light & Shadow",
        "description": "明亮→阳光→活跃→光影→阴影→暗夜→静谧→蓝调→夜色。适合街拍+建筑+冷暖色调对比的照片集。",
        "suitable_for": ["cool_warm_contrast", "street", "architecture"],
        "positions": [
            {"role": "明亮开场", "shot_types": ["long_shot", "wide"], "moods": ["serene", "warm", "energetic"], "content_types": ["landscape", "architecture"], "element_tags": ["sky", "horizon", "light_ray"], "color_tone": "warm", "needs_people": False},
            {"role": "阳光", "shot_types": ["medium_full", "medium"], "moods": ["warm", "energetic"], "content_types": ["street", "architecture"], "element_tags": ["light_ray", "shadow", "building"], "color_tone": "warm", "needs_people": False},
            {"role": "活跃", "shot_types": ["medium", "close_up"], "moods": ["energetic", "joyful", "warm"], "content_types": ["portrait", "street", "travel"], "element_tags": ["crowd", "smile", "hand"], "color_tone": "neutral", "needs_people": True},
            {"role": "光影对比", "shot_types": ["long_shot", "wide"], "moods": ["dramatic", "mysterious"], "content_types": ["landscape", "architecture", "street"], "element_tags": ["silhouette", "shadow", "pattern", "geometric"], "color_tone": "neutral", "needs_people": False},
            {"role": "阴影", "shot_types": ["medium", "medium_full"], "moods": ["mysterious", "dramatic", "cool"], "content_types": ["street", "architecture", "portrait"], "element_tags": ["shadow", "neon", "dark", "silhouette"], "color_tone": "cool", "needs_people": True},
            {"role": "暗夜", "shot_types": ["medium_full", "long_shot"], "moods": ["cool", "mysterious", "quiet"], "content_types": ["street", "architecture", "night"], "element_tags": ["neon", "shadow", "dark", "lamp"], "color_tone": "cool", "needs_people": False},
            {"role": "静谧", "shot_types": ["medium", "medium_full"], "moods": ["serene", "quiet", "cool"], "content_types": ["architecture", "street"], "element_tags": ["pattern", "geometric", "minimal"], "color_tone": "cool", "needs_people": False},
            {"role": "蓝色时刻", "shot_types": ["long_shot", "wide"], "moods": ["cool", "serene", "quiet"], "content_types": ["landscape", "architecture"], "element_tags": ["sky", "horizon", "cityscape"], "color_tone": "cool", "needs_people": False},
            {"role": "夜色收束", "shot_types": ["long_shot", "wide"], "moods": ["cool", "mysterious", "serene", "quiet"], "content_types": ["architecture", "landscape", "night"], "element_tags": ["night", "lamp", "moon", "star", "cityscape"], "color_tone": "cool", "needs_people": False},
        ],
    },
    "minimalist": {
        "name": "极简留白",
        "name_en": "Minimalist",
        "description": "空→出现→人物→再空→聚焦→纹理→留白→呼吸→空白收束。适合有大量留白/极简风格照片。",
        "suitable_for": ["negative_space", "minimal", "architecture"],
        "min_negative_space_7": 3,
        "positions": [
            {"role": "空", "shot_types": ["long_shot", "wide"], "moods": ["serene", "quiet", "peaceful"], "content_types": ["landscape", "architecture", "abstract"], "element_tags": ["minimal", "sky", "horizon", "water"], "color_tone": "neutral", "needs_people": False, "min_negative_space": 7},
            {"role": "出现", "shot_types": ["medium", "medium_full"], "moods": ["serene", "mysterious"], "content_types": ["architecture", "abstract", "street"], "element_tags": ["geometric", "pattern", "minimal", "texture"], "color_tone": "neutral", "needs_people": False},
            {"role": "人物", "shot_types": ["medium_full", "medium"], "moods": ["serene", "quiet", "warm"], "content_types": ["portrait", "street", "travel"], "element_tags": ["solo", "back_view", "profile", "hand"], "color_tone": "neutral", "needs_people": True},
            {"role": "再空", "shot_types": ["long_shot", "wide"], "moods": ["serene", "quiet", "peaceful"], "content_types": ["landscape", "architecture", "abstract"], "element_tags": ["minimal", "sky", "horizon"], "color_tone": "neutral", "needs_people": False, "min_negative_space": 7},
            {"role": "聚焦", "shot_types": ["close_up", "extreme_close_up", "detail"], "moods": ["serene", "dramatic", "mysterious"], "content_types": ["portrait", "macro", "abstract", "still_life"], "element_tags": ["eye", "hand", "texture", "pattern", "shallow_dof"], "color_tone": "neutral", "needs_people": False},
            {"role": "纹理", "shot_types": ["medium", "medium_full"], "moods": ["cool", "mysterious", "serene"], "content_types": ["architecture", "street", "abstract"], "element_tags": ["texture", "pattern", "geometric", "shadow"], "color_tone": "neutral", "needs_people": False},
            {"role": "留白", "shot_types": ["long_shot", "wide"], "moods": ["serene", "nostalgic", "quiet"], "content_types": ["landscape", "architecture"], "element_tags": ["horizon", "sky", "minimal"], "color_tone": "neutral", "needs_people": False, "min_negative_space": 7},
            {"role": "呼吸", "shot_types": ["medium_full", "long_shot"], "moods": ["serene", "quiet", "peaceful"], "content_types": ["architecture", "landscape", "street"], "element_tags": ["sky", "building", "minimal", "geometric"], "color_tone": "neutral", "needs_people": False},
            {"role": "空白收束", "shot_types": ["long_shot", "wide"], "moods": ["serene", "mysterious", "peaceful", "quiet"], "content_types": ["landscape", "architecture", "abstract"], "element_tags": ["horizon", "sky", "minimal", "water"], "color_tone": "neutral", "needs_people": False, "min_negative_space": 7},
        ],
    },
}
# ========== 4. 素材完备度评估 ==========

def compute_narrative_readiness(photos, blueprint_key, blueprints=None):
    """评估某个蓝图位置的素材完备度 (0.0 ~ 1.0)"""
    if blueprints is None:
        blueprints = get_blueprints(photos) or {}
    blueprint = blueprints.get(blueprint_key)
    if not blueprint:
        return 0.0

    positions = blueprint["positions"]
    if not positions:
        return 0.0

    match_counts = []
    for pos_req in positions:
        matches = 0
        for p in photos:
            # shot_type 匹配
            st = p.get("shot_type", "")
            if st in pos_req["shot_types"]:
                matches += 3
            elif CAN_CROP_MAP.get(st, []) and any(s in pos_req["shot_types"] for s in CAN_CROP_MAP[st]):
                matches += 2

            # mood 匹配
            mood = p.get("mood", "")
            if mood in pos_req["moods"]:
                matches += 2

            # content_type
            ct = p.get("content_type", "")
            if ct in pos_req["content_types"]:
                matches += 1

            # element_tags
            tags = set(p.get("element_tags", []))
            if isinstance(tags, set) and tags:
                shared = len(tags & set(pos_req["element_tags"]))
                matches += shared * 0.5

            # people
            if p.get("has_people") == pos_req.get("needs_people", False):
                matches += 1

            # negative_space 要求
            min_ns = pos_req.get("min_negative_space", 0)
            if min_ns > 0 and p.get("negative_space", 0) >= min_ns:
                matches += 2

        # 计算该位置的平均得分
        max_possible = 3 + 2 + 1 + 3 + 1 + 2  # = 12
        avg_match = matches / max(len(photos), 1)
        match_counts.append(min(avg_match, 1.0))

    # 整体完备度 = 各位置平均
    readiness = sum(match_counts) / len(match_counts) if match_counts else 0
    return round(readiness, 2)


def get_all_readiness(photos, blueprints=None):
    """计算所有蓝图素材完备度"""
    if blueprints is None:
        blueprints = get_blueprints(photos) or {}
    results = []
    for key, bp in blueprints.items():
        readiness = compute_narrative_readiness(photos, key)
        results.append({
            "key": key,
            "name": bp["name"],
            "name_en": bp["name_en"],
            "description": bp["description"],
            "readiness": readiness,
            "position_count": len(bp["positions"]),
        })
    results.sort(key=lambda x: x["readiness"], reverse=True)
    return results


def print_readiness(photos, blueprints=None):
    """打印可读的完备度评估"""
    if blueprints is None:
        blueprints = get_blueprints(photos) or {}
    print(f"\n{'=' * 50}")
    print("  🎯 叙事蓝图素材完备度评估")
    print(f"{'=' * 50}")
    for r in get_all_readiness(photos, blueprints):
        readiness = r["readiness"]
        bar_len = int(readiness * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"\n  {r['name']} ({r['name_en']})")
        print(f"  {bar} {readiness*100:.0f}%")
        print(f"  📝 {r['description']}")
    print()


# ========== 5. 计算叙事角色 ==========

def compute_narrative_role(photo):
    """根据 shot_type + content_type + element_tags + mood + negative_space 推断叙事角色

    返回: establishing | main_subject | supporting | transient | closure | atmosphere
    """
    st = photo.get("shot_type", "")
    ct = photo.get("content_type", "")
    tags = set(photo.get("element_tags", [])) if isinstance(photo.get("element_tags", []), list) else set()
    mood = photo.get("mood", "")
    neg = photo.get("negative_space", 5)
    has_people = photo.get("has_people", False)
    color_temp = photo.get("color_temp", 0) or 0
    face_count = photo.get("face_count", 0)

    # 留白/氛围
    if neg >= 8 or "minimal" in tags:
        return "atmosphere"

    # 主体（有人物的近景/中景）
    if has_people and st in ("close_up", "extreme_close_up", "medium", "medium_shot"):
        return "main_subject"

    # 建立场景（无人的远景）
    if st in ("wide", "long_shot") and ct in ("landscape", "architecture") and not has_people:
        return "establishing"

    # 辅助/陪伴（有人物的全景/远景）
    if has_people:
        return "supporting"

    # 过渡（街拍/旅行瞬景）
    if ct in ("street", "travel") and not has_people:
        return "transient"

    # 冷调收束
    if color_temp < -25 and st in ("long_shot", "medium"):
        return "closure"

    return "supporting"


# ========== 6. 命令行入口 ==========

def main():
    photos = load_data()
    print(f"\n📷 加载 {len(photos)} 张照片数据")
    print_inventory(photos)

    # 动态发现叙事主题
    blueprints = get_blueprints(photos)
    if blueprints:
        from scripts.theme_discovery import print_discovery_report
        print_discovery_report(photos, blueprints)
        print_readiness(photos, blueprints)
    else:
        print("\n⚠️  未发现动态叙事主题（照片素材不足或缺少评分数据）")
        print("   使用旧静态蓝图作为参考...")
        print_readiness(photos, _STATIC_BLUEPRINTS)

    # 示例：对前 5 张照片重算叙事角色
    print(f"\n{'=' * 50}")
    print("  🔄 叙事角色重算示例（前5张）")
    print(f"{'=' * 50}")
    for p in photos[:5]:
        old_role = p.get("narrative_role", "?")
        new_role = compute_narrative_role(p)
        print(f"  {p['filename'][:30]} 模型={old_role} → 计算={new_role}")


if __name__ == "__main__":
    main()
