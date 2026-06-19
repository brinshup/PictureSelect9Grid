"""
叙事主题自动发现引擎 — 基于 element_tags 共现分析的聚类 + 动态蓝图生成
从照片中自动发现自然的叙事主题，替代硬编码的 4 套蓝图。
用法:
    python scripts/theme_discovery.py   # 独立运行查看发现报告
"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 确保可以从 scripts/ 目录外导入
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

PROJECT_DIR = _PROJECT_ROOT
OUTPUT_DIR = PROJECT_DIR / "output"

# ── 标签中文语义映射 ──
_TAG_CN = {
    "sky": "天空", "horizon": "地平线", "road": "道路", "tree": "树木",
    "sign": "路标", "water": "水面", "reflection": "倒影", "silhouette": "剪影",
    "building": "建筑", "archway": "拱门", "pattern": "几何图案", "shadow": "阴影",
    "window": "窗户", "backlight": "逆光", "texture": "纹理", "flower": "花朵",
    "hand": "手", "lamp": "灯光", "cloud": "云", "crane": "吊车",
    "vertical": "竖线", "staircase": "楼梯", "bridge": "桥", "neon": "霓虹",
    "crowd": "人群", "solo": "独处", "profile": "侧脸", "back_view": "背影",
    "light_ray": "光束", "fog": "雾", "mountain": "山", "seascape": "海景",
    "forest": "森林", "minimal": "极简", "geometric": "几何", "vintage": "复古",
    "dark": "暗调", "bright": "明亮", "monochrome": "黑白", "golden_hour": "黄金时刻",
    "leaf": "树叶", "rock": "岩石", "sand": "沙", "wave": "海浪",
    "lens_flare": "镜头光晕", "backlight": "逆光", "cloud": "云彩",
    "crane": "吊车", "vertical": "竖线", "staircase": "楼梯", "bridge": "桥",
    "neon": "霓虹", "crowd": "人群", "solo": "独处", "profile": "侧脸",
    "back_view": "背影",
}

# ── 主题命名模板 ──
_THEME_NAMES = [
    # (匹配标签集合片段, 中文名, 英文名, 描述模板)
    ({"road", "horizon", "sky", "tree", "sign"}, "开阔旅途", "Open Road",
     "开阔旅途叙事。核心元素: {tags}。适合风景与街拍，展现旅途的开阔与延伸感。"),
    ({"building", "archway", "pattern", "window", "geometric", "vertical"}, "城市几何", "Urban Geometry",
     "城市几何叙事。核心元素: {tags}。以建筑线条和几何构图构建理性秩序感。"),
    ({"silhouette", "shadow", "lamp", "backlight", "neon", "dark"}, "暮色光影", "Twilight Glow",
     "暮色光影叙事。核心元素: {tags}。利用逆光与阴影对比营造神秘氛围。"),
    ({"water", "reflection", "sky", "horizon", "wave", "seascape"}, "水光潋滟", "Water & Light",
     "水光潋滟叙事。核心元素: {tags}。以水面光影与倒影构建宁静诗意的视觉节奏。"),
    ({"flower", "tree", "leaf", "texture", "hand", "forest", "rock"}, "草木物语", "Nature Details",
     "草木物语叙事。核心元素: {tags}。聚焦自然细节，用微距和纹理传递细腻感受。"),
    ({"crowd", "solo", "profile", "back_view", "hand", "shadow"}, "街角故事", "Street Stories",
     "街角故事叙事。核心元素: {tags}。以街拍记录城市中的人物瞬间和生活气息。"),
    ({"minimal", "geometric", "pattern", "texture", "monochrome"}, "极简秩序", "Minimal Order",
     "极简秩序叙事。核心元素: {tags}。用简洁构图和几何重复构建视觉韵律。"),
    ({"golden_hour", "light_ray", "warm", "bright", "backlight"}, "金色时刻", "Golden Hour",
     "金色时刻叙事。核心元素: {tags}。捕捉黄金时段的光影质感，温暖而富有戏剧性。"),
    ({"night", "lamp", "neon", "moon", "star", "dark", "silhouette"}, "城市夜色", "City Night",
     "城市夜色叙事。核心元素: {tags}。以夜景光影展现城市的另一种面貌。"),
]

# ── 位置角色模板（9 个位置的叙事弧线）──
_POSITION_ROLES = [
    ("开场 · 建立场景", "start"),
    ("启程 · 引入", "early"),
    ("风景 · 过渡", "early-mid"),
    ("探索 · 展开", "mid"),
    ("核心 · 情感锚点", "peak"),
    ("转折 · 沉淀", "mid-late"),
    ("回味 · 思绪", "late"),
    ("深呼吸 · 留白", "late"),
    ("收束 · 余韵", "end"),
]

# shot_type 分配模板
_POSITION_SHOT_TYPES = [
    ["wide", "long_shot"],
    ["long_shot", "medium_full"],
    ["long_shot", "medium_full", "wide"],
    ["medium_full", "medium"],
    ["medium", "medium_full", "close_up"],
    ["medium", "medium_full"],
    ["medium_full", "long_shot", "medium"],
    ["long_shot", "medium_full"],
    ["long_shot", "wide"],
]

# mood 弧线模板
_POSITION_MOODS = [
    ["serene", "peaceful", "quiet"],
    ["serene", "warm", "peaceful"],
    ["serene", "peaceful", "melancholic"],
    ["warm", "energetic", "serene"],
    ["energetic", "joyful", "romantic", "warm"],
    ["mysterious", "melancholic", "dramatic"],
    ["serene", "nostalgic", "quiet"],
    ["serene", "quiet", "peaceful"],
    ["serene", "nostalgic", "peaceful", "quiet"],
]

# ── 可裁剪性映射（与 narrative_blueprint.py 一致）──
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
    'unknown': [],
}


# ========== 1. 标签共现分析 ==========

def count_tags(photos):
    """统计所有 element_tags 的频率"""
    counter = Counter()
    for p in photos:
        tags = p.get("element_tags", [])
        if isinstance(tags, list):
            for t in tags:
                if t:  # 跳过空字符串
                    counter[t] += 1
    return counter


def build_cooccurrence_matrix(photos, frequent_tags):
    """构建标签共现矩阵和 Jaccard 相似度矩阵"""
    tag_list = sorted(frequent_tags)  # 确定顺序
    n = len(tag_list)
    tag_index = {t: i for i, t in enumerate(tag_list)}
    index_tag = {i: t for t, i in tag_index.items()}

    # 共现计数矩阵
    cooccur = [[0] * n for _ in range(n)]

    # 每张照片的标签索引集合
    for p in photos:
        tags = p.get("element_tags", [])
        if not isinstance(tags, list):
            continue
        indices = set()
        for t in tags:
            if t in tag_index:
                indices.add(tag_index[t])
        for i in indices:
            for j in indices:
                if i < j:
                    cooccur[i][j] += 1
                    cooccur[j][i] += 1

    # 构造稀疏 dict 输出和 Jaccard
    raw_matrix = defaultdict(lambda: defaultdict(int))
    jaccard_matrix = defaultdict(lambda: defaultdict(float))

    for i in range(n):
        tag_i = index_tag[i]
        for j in range(n):
            if i == j:
                continue
            tag_j = index_tag[j]
            c = cooccur[i][j]
            if c > 0:
                raw_matrix[tag_i][tag_j] = c
                raw_matrix[tag_j][tag_i] = c
                count_i = frequent_tags[tag_i]
                count_j = frequent_tags[tag_j]
                jac = c / (count_i + count_j - c)
                jaccard_matrix[tag_i][tag_j] = jac
                jaccard_matrix[tag_j][tag_i] = jac

    return raw_matrix, jaccard_matrix


# ========== 2. 聚类提取 ==========

def extract_tag_clusters(raw_matrix, jaccard_matrix, tag_counts,
                         min_clusters=3, max_clusters=5,
                         min_tags=2, max_tags=6, jaccard_threshold=0.12):
    """贪心聚类提取 - 确定性的，每次运行结果一致"""
    tags_sorted = sorted(tag_counts.keys(),
                          key=lambda t: sum(raw_matrix[t].values()),
                          reverse=True)

    used = set()
    clusters = []

    for seed in tags_sorted:
        if seed in used:
            continue
        if len(clusters) >= max_clusters:
            break

        cluster = [seed]
        used.add(seed)

        # 按 Jaccard 排序邻居
        neighbors = sorted(
            [(n, jaccard_matrix[seed].get(n, 0)) for n in tags_sorted if n not in used],
            key=lambda x: -x[1]
        )

        for neighbor, jac in neighbors:
            if len(cluster) >= max_tags:
                break
            if jac < jaccard_threshold:
                continue

            # 检查加入后聚类内部密度变化
            current_density = _cluster_density(cluster, jaccard_matrix)
            if current_density == 0:
                cluster.append(neighbor)
                used.add(neighbor)
                continue

            test_cluster = cluster + [neighbor]
            new_density = _cluster_density(test_cluster, jaccard_matrix)
            if new_density >= current_density * 0.9:  # 允许最多降 10%
                cluster.append(neighbor)
                used.add(neighbor)

        if len(cluster) >= min_tags:
            clusters.append(cluster)
        else:
            # 不够最小标签数，释放回来
            for t in cluster:
                used.discard(t)

    return clusters


def _cluster_density(cluster, jaccard_matrix):
    """计算聚类内部平均 Jaccard 相似度"""
    if len(cluster) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(len(cluster)):
        for j in range(i + 1, len(cluster)):
            total += jaccard_matrix[cluster[i]].get(cluster[j], 0)
            pairs += 1
    return total / pairs if pairs > 0 else 0.0


# ========== 3. 主题统计 ==========

def compute_theme_statistics(photos, cluster):
    """统计聚类对应的照片子集特征"""
    # 匹配照片：至少包含 cluster 中 2 个标签
    matching = []
    cluster_set = set(cluster)
    for p in photos:
        tags = p.get("element_tags", [])
        if not isinstance(tags, list):
            continue
        if len(set(tags) & cluster_set) >= 2:
            matching.append(p)

    if not matching:
        return None

    cts = Counter()
    moods = Counter()
    shots = Counter()
    color_temps = []
    has_people = 0
    neg_spaces = []

    for p in matching:
        ct = p.get("content_type", "unknown")
        for part in ct.split("|"):
            cts[part.strip()] += 1
        md = p.get("mood", "neutral")
        for part in md.split("|"):
            moods[part.strip()] += 1
        shots[p.get("shot_type", "unknown")] += 1
        ct_val = p.get("color_temp", 0)
        if ct_val is not None:
            color_temps.append(float(ct_val))
        if p.get("has_people"):
            has_people += 1
        neg_spaces.append(p.get("negative_space", 5))

    avg_ct = sum(color_temps) / len(color_temps) if color_temps else 0
    avg_ns = sum(neg_spaces) / len(neg_spaces) if neg_spaces else 5

    if avg_ct > 15:
        tone_majority = "warm"
    elif avg_ct < -15:
        tone_majority = "cool"
    else:
        tone_majority = "neutral"

    return {
        "matching_photos": matching,
        "coverage": len(matching),
        "coverage_pct": round(len(matching) / len(photos) * 100, 1),
        "content_types": dict(cts.most_common(5)),
        "moods": dict(moods.most_common(5)),
        "shot_types": dict(shots.most_common(8)),
        "avg_color_temp": round(avg_ct, 1),
        "color_tone_majority": tone_majority,
        "people_pct": round(has_people / len(matching) * 100, 1),
        "has_people_count": has_people,
        "avg_negative_space": round(avg_ns, 1),
    }


# ========== 4. 主题命名 ==========

# 全局名称去重
_USED_THEME_NAMES = set()


def name_theme(cluster, stats, cluster_index=None):
    """根据聚类标签和统计数据生成主题名称（自动去重）"""
    cluster_set = set(cluster)
    _USED_THEME_NAMES_REF = _USED_THEME_NAMES  # module-level ref

    def _unique_name(base_name):
        """确保名称不重复"""
        if base_name not in _USED_THEME_NAMES_REF:
            _USED_THEME_NAMES_REF.add(base_name)
            return base_name
        suffix = 2
        while f"{base_name}{suffix}" in _USED_THEME_NAMES_REF:
            suffix += 1
        unique = f"{base_name}{suffix}"
        _USED_THEME_NAMES_REF.add(unique)
        return unique

    # 尝试匹配预定义模板
    best_match = None
    best_overlap = 0
    for match_tags, cn_name, en_name, desc_tmpl in _THEME_NAMES:
        overlap = len(cluster_set & match_tags)
        if overlap > best_overlap and overlap >= max(2, len(cluster_set) // 2):
            best_overlap = overlap
            best_match = (cn_name, en_name, desc_tmpl)

    if best_match:
        cn_name, en_name, desc_tmpl = best_match
        top_tags = _pick_display_tags(cluster, stats)
        tags_cn = "、".join(_TAG_CN.get(t, t) for t in top_tags[:3])
        description = desc_tmpl.format(tags=tags_cn)
        return _unique_name(cn_name), en_name, description

    # 回退：基于最突出的单个标签命名
    # 选聚类中覆盖量最低的标签（最有区分度）
    matching = stats.get("matching_photos", [])
    tag_freq_in_cluster = {}
    if matching:
        for tag in cluster:
            count = sum(1 for p in matching
                        if isinstance(p.get("element_tags", []), list)
                        and tag in p["element_tags"])
            tag_freq_in_cluster[tag] = count
        distinctive = min(cluster, key=lambda t: tag_freq_in_cluster.get(t, len(matching)))
    else:
        distinctive = cluster[0]

    tag_cn = _TAG_CN.get(distinctive, distinctive)
    ct_cn_map = {
        "landscape": "风景", "portrait": "人像", "architecture": "建筑",
        "street": "街拍", "travel": "旅行", "night": "夜景",
        "food": "美食", "animal": "动物", "abstract": "抽象",
        "unknown": "视觉",
    }
    top_ct = list(stats["content_types"].keys())[:2]
    ct_names = [ct_cn_map.get(ct, ct) for ct in top_ct]

    cn_name = f"{tag_cn}·{''.join(ct_names[:2])}"
    description = f"以{tag_cn}为核心的{''.join(ct_names[:2])}叙事。"
    return _unique_name(cn_name), f"{distinctive.title()} Theme", description


def _pick_display_tags(cluster, stats):
    """从聚类中选择最具区分度的标签展示"""
    matching = stats.get("matching_photos", [])
    if not matching:
        return cluster[:3]

    total = stats.get("coverage_pct", 50) / 100 * 100  # 粗略
    # 按在匹配集中出现率排序（出现率适中的最有区分度）
    tag_in_cluster = Counter()
    for p in matching:
        tags = p.get("element_tags", [])
        if isinstance(tags, list):
            tag_in_cluster.update(t for t in tags if t in set(cluster))

    sorted_tags = sorted(cluster,
                          key=lambda t: tag_in_cluster.get(t, 0))
    return sorted_tags[:3]


# ========== 5. 蓝图位置生成 ==========

def generate_blueprint_positions(photos, cluster, stats):
    """为聚类生成 9 个位置要求，匹配 BLUEPRINTS 格式"""
    cluster_set = set(cluster)
    positions = []

    for idx in range(9):
        role, arc_pos = _POSITION_ROLES[idx]

        # shot_types：从模板取，但需要确保聚类中有匹配的照片
        shot_types = _select_shot_types_for_position(idx, stats, cluster_set)

        # moods：从模板取，过滤为聚类中实际存在的
        moods = _select_moods_for_position(idx, stats)

        # content_types：使用聚类中出现 >=3 张的类型
        content_types = [ct for ct, cnt in stats["content_types"].items()
                         if cnt >= 3] or list(stats["content_types"].keys())[:2]

        # element_tags：核心标签 + 位置特定附加标签
        tags = _select_tags_for_position(idx, cluster, stats)

        # color_tone
        color_tone = _select_color_tone_for_position(idx, stats)

        # needs_people
        needs_people = _select_needs_people(idx, stats)

        pos_req = {
            "role": role,
            "shot_types": shot_types,
            "moods": moods,
            "content_types": content_types,
            "element_tags": tags,
            "color_tone": color_tone,
            "needs_people": needs_people,
        }

        # negative_space
        if stats["avg_negative_space"] >= 7 and idx in (0, 4, 8):
            pos_req["min_negative_space"] = 7

        positions.append(pos_req)

    # 验证：每个位置至少有一些可匹配的照片
    positions = _validate_positions(positions, stats, cluster_set)

    return positions


def _select_shot_types_for_position(idx, stats, cluster_set):
    """为位置选择合适的 shot_types，确保聚类中有匹配"""
    template = _POSITION_SHOT_TYPES[idx]
    matching = stats["matching_photos"]

    # 检查模板 shot_types 是否有至少 1 张可匹配照片
    viable = []
    for st in template:
        # 直接匹配
        count = sum(1 for p in matching if p.get("shot_type") == st)
        if count > 0:
            viable.append(st)
        else:
            # 检查是否有照片可通过裁剪匹配
            for p in matching:
                p_st = p.get("shot_type", "")
                if p_st in CAN_CROP_MAP and st in CAN_CROP_MAP.get(p_st, []):
                    count += 1
            if count > 0:
                viable.append(st)

    if viable:
        return viable

    # 回退：使用聚类中最常见的 2 种 shot_type
    common = sorted(stats["shot_types"].keys(),
                    key=lambda k: stats["shot_types"][k], reverse=True)[:2]
    return common or ["medium", "long_shot"]


def _select_moods_for_position(idx, stats):
    """从模板选取聚类中实际存在的 mood"""
    template = _POSITION_MOODS[idx]
    available = set(stats["moods"].keys())
    viable = [m for m in template if m in available]
    if viable:
        return viable
    # 回退：用聚类中最常见的 mood
    common = list(stats["moods"].keys())[:2]
    return common or ["serene"]


def _select_tags_for_position(idx, cluster, stats):
    """为位置选择 element_tags：核心标签 + 位置特定附加标签"""
    tags = list(cluster[:4])  # 核心标签

    # 位置特定附加标签
    extra_tag_map = {
        0: ["sky", "horizon"],
        1: ["road", "tree"],
        2: ["sky", "water"],
        3: ["building", "archway"],
        4: ["hand", "profile", "crowd"],
        5: ["shadow", "silhouette"],
        6: ["texture", "pattern"],
        7: ["sky", "horizon"],
        8: ["horizon", "silhouette"],
    }

    available_tags = set()
    for p in stats.get("matching_photos", []):
        tgs = p.get("element_tags", [])
        if isinstance(tgs, list):
            available_tags.update(tgs)

    for extra in extra_tag_map.get(idx, []):
        if extra in available_tags and extra not in tags:
            tags.append(extra)

    return tags[:5]  # 最多 5 个


def _select_color_tone_for_position(idx, stats):
    """为位置选择 color_tone 偏好"""
    majority = stats["color_tone_majority"]
    if majority == "cool":
        # 开场收束偏冷，中间部分偏中性
        cool_positions = {0, 1, 3, 5, 7, 8}
        return "cool" if idx in cool_positions else "neutral"
    elif majority == "warm":
        warm_positions = {0, 1, 4, 8}
        return "warm" if idx in warm_positions else "neutral"
    else:
        return "neutral"


def _select_needs_people(idx, stats):
    """判断位置是否需要有人物"""
    pct = stats["people_pct"]
    count = stats["has_people_count"]

    if count == 0:
        return False
    if count <= 2:
        return False
    if count <= 5:
        # 只有 1 个位置需人物
        return idx == 4
    # 6+ 有人物照片：2-3 个位置需人物
    people_positions = {3, 4}
    if count >= 10:
        people_positions = {3, 4, 8}
    return idx in people_positions


def _validate_positions(positions, stats, cluster_set):
    """验证每个位置有至少 1 张可匹配照片；否则放宽约束"""
    matching = stats["matching_photos"]

    def count_matches(pos_req):
        """简易匹配计数，模拟 position_fit 的逻辑"""
        count = 0
        for p in matching:
            score = 0
            st = p.get("shot_type", "")
            if st in pos_req["shot_types"]:
                score += 25
            elif CAN_CROP_MAP.get(st, []) and any(
                s in pos_req["shot_types"] for s in CAN_CROP_MAP.get(st, [])
            ):
                score += 15
            p_moods = p.get("mood", "").split("|")
            if any(m in pos_req["moods"] for m in p_moods):
                score += 20
            ct = p.get("content_type", "")
            if ct in pos_req["content_types"]:
                score += 15
            if p.get("has_people") == pos_req.get("needs_people", False):
                score += 10
            if score >= 20:
                count += 1
        return count

    for i, pos in enumerate(positions):
        if count_matches(pos) > 0:
            continue

        # 放宽：扩展 shot_types
        all_shots = list(stats["shot_types"].keys())
        pos["shot_types"] = all_shots[:4] if len(all_shots) >= 4 else all_shots
        if count_matches(pos) > 0:
            continue

        # 放宽：扩展 moods
        all_moods = list(stats["moods"].keys())
        pos["moods"] = all_moods[:3] if len(all_moods) >= 3 else all_moods
        if count_matches(pos) > 0:
            continue

        # 放宽：去除 needs_people
        if pos["needs_people"]:
            pos["needs_people"] = False
            if count_matches(pos) > 0:
                continue

        # 最坏情况：选最宽松的 content_types
        pos["content_types"] = list(stats["content_types"].keys())
        pos["needs_people"] = False

    return positions


# ========== 6. 编排器 ==========

def discover_and_generate_blueprints(photos):
    """发现叙事主题并生成蓝图 — 主入口

    返回: {"discovered_0": {blueprint}, "discovered_1": {...}, ...}
    无可用主题时返回空 dict
    """
    if not photos:
        return {}

    # 重置名称去重
    _USED_THEME_NAMES.clear()

    # 1. 标签统计
    tag_counts = count_tags(photos)

    # 2. 筛选高频标签（出现在 >= 9 张照片中）
    frequent_tags = {tag: count for tag, count in tag_counts.items() if count >= 9}
    if len(frequent_tags) < 3:
        return {}

    # 3. 共现分析
    raw_matrix, jaccard_matrix = build_cooccurrence_matrix(photos, frequent_tags)

    # 4. 聚类
    clusters = extract_tag_clusters(raw_matrix, jaccard_matrix, frequent_tags)
    if not clusters:
        return {}

    # 5. 为每个聚类生成蓝图
    blueprints = {}
    for i, cluster in enumerate(clusters):
        stats = compute_theme_statistics(photos, cluster)
        if stats is None or stats["coverage"] < 9:
            continue

        cn_name, en_name, description = name_theme(cluster, stats)
        positions = generate_blueprint_positions(photos, cluster, stats)

        key = f"discovered_{i}"
        blueprints[key] = {
            "name": cn_name,
            "name_en": en_name,
            "description": description,
            "suitable_for": [f"auto_{t}" for t in cluster[:3]],
            "positions": positions,
        }

    return blueprints


def save_discovered_themes(photos, blueprints, output_path=None):
    """将发现的主题保存到 JSON 文件"""
    if output_path is None:
        output_path = OUTPUT_DIR / "discovered_themes.json"

    from datetime import datetime
    data = {
        "discovered_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total_photos": len(photos),
        "has_vision": any(p.get("aesthetic_score") for p in photos),
        "themes": [],
    }

    for key, bp in blueprints.items():
        # 提取统计信息
        cluster_tags = bp.get("suitable_for", [])
        cluster_tags = [t.replace("auto_", "") for t in cluster_tags if t.startswith("auto_")]

        # 为 JSON 输出收集统计数据
        theme_entry = {
            "id": key,
            "name": bp["name"],
            "name_en": bp.get("name_en", ""),
            "description": bp["description"],
            "core_tags": cluster_tags,
            "readiness": 0.0,  # 将在 save 时由调用者填充
            "coverage": 0,
            "content_types": {},
            "blueprint": bp,
        }
        data["themes"].append(theme_entry)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return output_path


# ========== 7. 发现报告输出 ==========

def print_discovery_report(photos, blueprints):
    """打印可读的发现报告"""
    if not blueprints:
        print("\n❌ 未发现可行叙事主题（照片素材不足或标签信息不够）")
        print("   建议: 确保照片已通过 vision_score.py 获得完整的 element_tags 评分")
        return

    print(f"\n{'=' * 50}")
    print("  🎯 自动发现叙事主题")
    print(f"{'=' * 50}")
    print(f"  共 {len(blueprints)} 个可行主题\n")

    # 计算每个主题的素材完备度
    for key, bp in blueprints.items():
        cn_name = bp["name"]
        positions = bp.get("positions", [])
        tags = bp.get("suitable_for", [])

        # 粗略完备度估计（基于位置约束的平均匹配度）
        readiness = _estimate_readiness(photos, positions)
        bar_len = int(readiness * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        print(f"  {cn_name}")
        print(f"  {bar} {readiness*100:.0f}%")
        print(f"  位置数: {len(positions)}")
        print()

    # 标签组合提示
    print(f"  💡 使用 --interactive 交互选择主题")
    print(f"  或 --discover-only 先查看再 --themes 指定\n")


def _estimate_readiness(photos, positions):
    """粗略估算蓝图素材完备度 (0-1)"""
    if not photos or not positions:
        return 0.0
    match_scores = []
    for pos in positions:
        matches = 0
        for p in photos:
            score = 0
            st = p.get("shot_type", "")
            if st in pos.get("shot_types", []):
                score += 25
            moods = p.get("mood", "").split("|")
            if any(m in pos.get("moods", []) for m in moods):
                score += 20
            ct = p.get("content_type", "")
            if ct in pos.get("content_types", []):
                score += 15
            if score >= 20:
                matches += 1
        match_scores.append(min(matches / max(len(photos), 1) * 5, 1.0))
    return sum(match_scores) / len(match_scores) if match_scores else 0.0


# ========== 8. 交互式选择 ==========

def interactive_select_themes(blueprints):
    """交互式选择主题 — 显示列表并读取用户输入"""
    if not blueprints:
        print("❌ 没有可用的叙事主题")
        return []

    bp_list = list(blueprints.items())
    print(f"\n{'=' * 50}")
    print("  🎯 请选择要使用的叙事主题")
    print(f"{'=' * 50}\n")

    for i, (key, bp) in enumerate(bp_list):
        positions = bp.get("positions", [])
        tags = bp.get("suitable_for", [])
        tag_str = ", ".join(_TAG_CN.get(t.replace("auto_", ""), t.replace("auto_", ""))
                           for t in tags[:3] if t.startswith("auto_"))
        print(f"  {i+1}. {bp['name']}")
        print(f"     标签: {tag_str}")
        print()

    while True:
        try:
            inp = input("请输入要使用的主题编号（逗号分隔，如 1,3,5；或输入 all 使用全部）: ")
            inp = inp.strip()
            if not inp:
                print("  输入不能为空，请重新输入")
                continue
            if inp.lower() == "all":
                return [key for key, _ in bp_list]

            indices = []
            for part in inp.split(","):
                part = part.strip()
                if not part:
                    continue
                idx = int(part) - 1
                if 0 <= idx < len(bp_list):
                    indices.append(idx)
                else:
                    print(f"  ⚠️ 编号 {part} 超出范围，忽略")

            if not indices:
                print("  没有有效的选择，请重新输入")
                continue

            selected = [bp_list[i][0] for i in indices]
            names = [bp_list[i][1]["name"] for i in indices]
            print(f"\n  已选择: {', '.join(names)}")
            return selected

        except ValueError:
            print("  输入格式错误，请输入逗号分隔的数字")
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消")
            return []


# ========== 命令行入口 ==========

def main():
    """独立运行：加载照片并打印发现报告"""
    # 复用 narrative_blueprint 的数据加载
    from scripts.narrative_blueprint import load_data
    photos = load_data()
    print(f"\n📷 加载 {len(photos)} 张照片数据")

    blueprints = discover_and_generate_blueprints(photos)
    print_discovery_report(photos, blueprints)

    if blueprints:
        save_discovered_themes(photos, blueprints)
        print(f"✅ 发现结果已保存到: {OUTPUT_DIR / 'discovered_themes.json'}")
        print(f"   共发现 {len(blueprints)} 个主题")


if __name__ == "__main__":
    main()
