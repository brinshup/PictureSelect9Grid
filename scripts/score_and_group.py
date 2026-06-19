"""
九宫格选片 - 评分与分组（含动态叙事发现）
输入: output/analysis.json[, output/vision_scores.json]
输出: score_matrix.csv, groups.json, full_scored.json, 叙事方案
用法: python scripts/score_and_group.py [--mode histogram|vision|hybrid]
       python scripts/score_and_group.py --mode hybrid --discover-only
       python scripts/score_and_group.py --mode hybrid --interactive
       python scripts/score_and_group.py --mode hybrid --themes 1,3,5
"""
import json, csv, os, sys, argparse, re, subprocess
from datetime import datetime
from pathlib import Path
from collections import Counter

# 加入项目根目录到 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 叙事蓝图引擎
from scripts.narrative_blueprint import (
    CAN_CROP_MAP, compute_narrative_role,
    build_inventory, print_inventory,
    get_blueprints, clear_blueprint_cache,
)

# Windows GBK 兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 中英文翻译映射 ──
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
    'detail': '细节', 'unknown': '未知',
}
CN_CAMERA_ANGLE = {
    'eye_level': '平视', 'high_angle': '俯视', 'low_angle': '仰拍',
    'dutch': '斜角', 'birdseye': '鸟瞰', 'overhead': '俯拍', 'none': '无',
}
CN_NARRATIVE_ROLE = {
    'establishing': '建立场景', 'main_subject': '主体', 'supporting': '辅助',
    'transient': '过渡', 'closure': '收束', 'atmosphere': '氛围',
}
CN_ELEMENT_TAGS = {
    'sky': '天空', 'water': '水面', 'architecture': '建筑', 'silhouette': '剪影',
    'reflection': '倒影', 'texture': '纹理', 'pattern': '图案', 'symmetry': '对称',
    'leading_line': '引导线', 'frame_within_frame': '框景', 'shallow_dof': '浅景深',
    'motion_blur': '动感模糊', 'shadow': '阴影', 'neon': '霓虹', 'greenery': '绿植',
    'road': '道路', 'window': '窗户', 'door': '门', 'stairs': '楼梯', 'bridge': '桥',
    'crowd': '人群', 'solo': '独处', 'hand': '手', 'eye': '眼睛', 'profile': '侧脸',
    'back_view': '背影', 'food': '食物', 'drink': '饮品', 'pet': '宠物', 'flower': '花',
    'light_ray': '光束', 'fog': '雾', 'rainbow': '彩虹', 'star': '星星', 'moon': '月亮',
    'cityscape': '城市景观', 'landscape': '风景', 'seascape': '海景', 'mountain': '山',
    'forest': '森林', 'minimal': '极简', 'geometric': '几何', 'vintage': '复古',
    'dark': '暗调', 'bright': '明亮', 'colorful': '多彩', 'monochrome': '黑白',
    'golden_hour': '黄金时刻', 'blue_hour': '蓝调时分', 'night': '夜晚',
    'indoor': '室内', 'outdoor': '户外', 'urban': '城市', 'rural': '乡村',
    'abstract': '抽象', 'horizon': '地平线', 'tree': '树木', 'sign': '路标',
    'leaf': '树叶', 'archway': '拱门', 'rock': '岩石', 'sand': '沙', 'wave': '海浪',
}


def cn(text, mapping):
    """中文化：查找翻译映射，未找到则返回原文"""
    if not text or text == '?':
        return text
    return mapping.get(text, text)

# ── 解析命令行参数 ──
parser = argparse.ArgumentParser(description="九宫格选片评分与分组")
parser.add_argument(
    "--mode", choices=["histogram", "vision", "hybrid"], default="auto",
    help="评分模式: histogram=纯直方图, vision=仅视觉模型, hybrid=混合(默认), auto=自动检测"
)
parser.add_argument(
    "--output-dir", type=str, default=None,
    help="输出目录 (默认: 根据模式自动确定)"
)
parser.add_argument(
    "--version", type=str, default=None,
    help="版本标签 (如 1_0, 2_0)。默认: 自动检测最新版本并增量"
)
# ── 动态叙事发现参数 ──
parser.add_argument(
    "--discover-only", action="store_true",
    help="仅发现叙事主题，不生成方案（保存到 output/discovered_themes.json）"
)
parser.add_argument(
    "--themes", type=str, default=None,
    help="指定使用的主题编号（逗号分隔，如 1,3,5 或 discovered_0,discovered_2）"
)
parser.add_argument(
    "--interactive", action="store_true",
    help="交互模式：先发现主题，再选择使用哪些"
)
args = parser.parse_args()

# ── 加载直方图分析数据 ──
with open('output/analysis.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

photos = data['photos']
print(f'总照片: {len(photos)} 张')

# ── 确定模式 ──
_VISION_GLOBAL = 'output/vision_scores.json'
use_vision = False
if args.mode == "histogram":
    print("🔧 模式: 纯直方图（--mode histogram，跳过视觉评分）")
elif args.mode == "vision":
    if not os.path.exists(_VISION_GLOBAL):
        print(f"❌ 模式要求视觉评分文件但 {_VISION_GLOBAL} 不存在")
        print("   请先运行: python scripts/vision_score.py")
        sys.exit(1)
    use_vision = True
    print("🔧 模式: 纯视觉评分（--mode vision）")
elif args.mode == "hybrid":
    use_vision = os.path.exists(_VISION_GLOBAL)
    if not use_vision:
        print("⚠️  视觉评分文件不存在，回退到纯直方图")
    else:
        print("🔧 模式: 混合评分（--mode hybrid，70%视觉+30%直方图 + 叙事评分）")
else:  # auto
    use_vision = os.path.exists(_VISION_GLOBAL)
    print(f"🔧 模式: 自动检测 → {'混合评分 (视觉+直方图+叙事)' if use_vision else '纯直方图 (无视觉评分文件)'}")

# ── 确定输出目录 ──
_resolved = args.mode
if _resolved == "auto":
    _resolved = "hybrid" if use_vision else "histogram"

# 确定版本号（时间戳精确到分钟，支持 --version 覆盖）
if args.version:
    version = args.version
else:
    version = datetime.now().strftime("%Y%m%d_%H%M")

if args.output_dir:
    OUT_DIR = args.output_dir
else:
    OUT_DIR = f"output/{version}/{_resolved}"
os.makedirs(OUT_DIR, exist_ok=True)
print(f"📂 输出目录: {OUT_DIR}/ (版本={version}, 模式={_resolved})")

# ── 加载视觉评分 ──
VISION_PATH = f'{OUT_DIR}/vision_scores.json'
if not os.path.exists(VISION_PATH):
    VISION_PATH = _VISION_GLOBAL  # 全局回退
vision_map = {}
vision_meta = {}

if use_vision:
    with open(VISION_PATH, 'r', encoding='utf-8') as f:
        vs = json.load(f)
    for s in vs.get('scores', []):
        vision_map[s['filename']] = s
    vision_meta = {k: vs[k] for k in ['model', 'successful', 'failed', 'cost_estimate_usd', 'prompt_version'] if k in vs}
    pv = vision_meta.get('prompt_version', 1)
    print(f'✅ 加载视觉评分: {len(vision_map)} 张 (模型: {vision_meta.get("model", "?")}, prompt_v{pv})')
    if pv < 2:
        print('   ⚠️  建议升级 vision_score.py 到 v2 prompt 以获取叙事字段')

# ========== 1. 淘汰低质 ==========
eliminated = []
candidates = []

for p in photos:
    jpg_name = p['filename'].replace('.heic', '.jpg')
    reasons = []

    # 直方图淘汰
    if p['sharpness'] < 5:
        reasons.append('严重模糊')
    if p['underexposed_pct'] > 20:
        reasons.append('严重欠曝')
    if p['aspect_ratio'] < 0.5:
        reasons.append('疑似截屏/超窄图')

    # 视觉评分淘汰（如果有）
    v = vision_map.get(jpg_name)
    if v:
        aesth = v.get('aesthetic_score')
        if aesth is not None and aesth < 3.0:
            reasons.append(f'极低美学分({aesth}/10)')
        fq = v.get('focus_and_exposure', {}).get('focus_quality')
        if fq is not None and fq < 3:
            reasons.append(f'对焦严重失准({fq}/10)')

    if reasons:
        eliminated.append({
            'filename': p['filename'],
            'jpg_name': jpg_name,
            'reasons': reasons,
            'sharpness': p['sharpness'],
            'underexposed_pct': p['underexposed_pct'],
        })
    else:
        candidates.append(p)

print(f'\n淘汰 {len(eliminated)} 张, 候选 {len(candidates)} 张')
if vision_map:
    vision_rejects = [e for e in eliminated if any('美学' in r or '对焦严重' in r for r in e['reasons'])]
    if vision_rejects:
        print(f'  其中视觉评分淘汰 {len(vision_rejects)} 张')

# ========== 2. 基于 serial 号 + content_type 分组 ==========
def extract_serial(fname):
    parts = fname.replace('.jpg', '').split('_')
    if len(parts) >= 4:
        return int(parts[2])
    return 0

def get_content_type(fname):
    """获取视觉模型判定的内容类型，无数据则返回 'unknown'"""
    v = vision_map.get(fname)
    return v.get('content_type', 'unknown') if v else 'unknown'

candidates_sorted = sorted(candidates, key=lambda x: extract_serial(x['filename']))

groups = []
current_group = []
prev_serial = -100

for p in candidates_sorted:
    serial = extract_serial(p['filename'])
    jpg_name = p['filename'].replace('.heic', '.jpg')
    ct = get_content_type(jpg_name)

    # 相邻 serial 分组，但如果 content_type 不同则不强并组
    if prev_serial > 0 and serial - prev_serial <= 3:
        prev_ct = get_content_type(current_group[-1]['filename'].replace('.heic', '.jpg'))
        if ct != 'unknown' and prev_ct != 'unknown' and ct != prev_ct:
            # 内容类型不同，分开
            groups.append(current_group)
            current_group = [p]
        else:
            current_group.append(p)
    else:
        if current_group:
            groups.append(current_group)
        current_group = [p]
    prev_serial = serial

if current_group:
    groups.append(current_group)

content_aware = vision_map and any(get_content_type(p['filename'].replace('.heic', '.jpg')) != 'unknown' for p in candidates)
print(f'\n分成 {len(groups)} 个相似组 {"(内容感知)" if content_aware else ""}')

# ========== 3. 综合评分（叙事权重）==========
# 新权重: 摄影(20) + 情绪(25) + 艺术(15) + 叙事(40) = 100

def histogram_scores(p):
    """纯直方图评分（保留作为回退和混合基，max 35/35/30）"""
    # 摄影 (35)
    s_sharp = min(p['sharpness'] / 5, 10)
    s_exposure = max(0, 5 - p['underexposed_pct'] * 0.3)
    comp = 10 - abs(p['contrast'] - 60) * 0.15
    s_composition = max(2, min(comp, 10))
    s_saturation = min(p['saturation'] / 5, 5)
    hist_photo = min(s_sharp + s_exposure + s_composition + s_saturation, 35)

    # 情绪 (35)
    mood_bright = 10 - abs(p['brightness'] - 110) * 0.08
    mood_bright = max(2, min(mood_bright, 10))
    mood_color = min(abs(p['color_temp']) / 15 * 5, 10)
    mood_contrast = 10 - abs(p['contrast'] - 60) * 0.12
    mood_contrast = max(2, min(mood_contrast, 10))
    portrait_bonus = 5 if p['aspect_ratio'] < 0.9 else 3
    hist_emotion = min(mood_bright + mood_color + mood_contrast + portrait_bonus, 35)

    # 艺术 (30)
    art_color = 10 - abs(p['saturation'] - 15) * 0.3
    art_color = max(3, min(art_color, 10))
    art_detail = min(p['sharpness'] / 6, 10)
    art_impact = min(p['contrast'] / 8, 10)
    hist_art = min(art_color + art_detail + art_impact, 30)

    return hist_photo, hist_emotion, hist_art


def narrative_score(v):
    """从 v2 视觉字段计算叙事分 (max 40)

    分解:
      - storytelling_potential /10 × 12   (max 12)
      - narrative_role 映射               (max 10)
      - visual_hook /10 × 8               (max 8)
      - element_tags 丰富度                (max 6)
      - shot_type 可用性                   (max 4)
    """
    if not v:
        return 0, {k: 0 for k in ('narrative_story', 'narrative_role', 'narrative_hook',
                                   'narrative_tags', 'narrative_shot', 'narrative_total')}

    # storytelling_potential × 1.2 → max 12
    s_story = v.get('storytelling_potential', 5) * 1.2

    # narrative_role → max 10
    role_map = {'establishing': 8, 'main_subject': 10, 'supporting': 6,
                'transient': 4, 'closure': 8, 'atmosphere': 6}
    s_role = role_map.get(v.get('narrative_role', ''), 5)

    # visual_hook × 0.8 → max 8
    s_hook = v.get('visual_hook', 5) * 0.8

    # element_tags 丰富度 → max 6
    tags = v.get('element_tags', [])
    if isinstance(tags, list) and tags:
        s_tags = min(len(tags) / 4.0, 1.0) * 6
    else:
        s_tags = 3

    # shot_type 可用性 → max 4
    shot = v.get('shot_type', '')
    s_shot = 4 if shot and shot not in ('unknown', 'medium') else 2

    total = min(round(s_story + s_role + s_hook + s_tags + s_shot, 1), 40)
    return total, {
        'narrative_story': round(s_story, 1),
        'narrative_role': round(s_role, 1),
        'narrative_hook': round(s_hook, 1),
        'narrative_tags': round(s_tags, 1),
        'narrative_shot': round(s_shot, 1),
        'narrative_total': total,
    }


def score_photo(p, v=None):
    """混合评分 + 叙事评分。返回新权重值 (max 20/25/15/40/100)"""
    hp, he, ha = histogram_scores(p)

    if v and v.get('aesthetic_score') is not None:
        # 从视觉评分提取构图分数
        comp = v.get('composition_assessment', {})
        v_comp = (
            comp.get('rule_of_thirds', 5) * 0.3 +
            comp.get('leading_lines', 5) * 0.2 +
            comp.get('balance', 5) * 0.25 +
            comp.get('framing', 5) * 0.25
        )
        fe = v.get('focus_and_exposure', {})
        v_focus = fe.get('focus_quality', 5)
        v_exposure = fe.get('exposure_quality', 5)
        v_lighting = fe.get('lighting_quality', 5)
        v_color = v.get('color_harmony', 5)

        # 视觉摄影分 (max 35)
        v_photo = min((v_comp * 0.7 + v_focus * 0.15 + v_exposure * 0.07 + v_lighting * 0.08) * 3.5, 35)
        # 视觉情绪分 (max 35)
        v_emotion = min(
            (v.get('emotional_impact', 5) * 0.4 +
             v.get('storytelling_potential', 5) * 0.3 +
             v.get('subject_prominence', 5) * 0.15 +
             v_color * 0.15) * 3.5, 35
        )
        # 视觉艺术分 (max 30)
        v_art = min(v.get('aesthetic_score', 5) * 3.0, 30)

        # 混合 (max 35/35/30)
        photo_mix = round(hp * 0.3 + v_photo * 0.7, 1)
        emo_mix = round(he * 0.3 + v_emotion * 0.7, 1)
        art_mix = round(ha * 0.5 + v_art * 0.5, 1)

        # 叙事评分 (max 40)
        nar_total, nar_details = narrative_score(v)
    else:
        photo_mix = round(hp, 1)
        emo_mix = round(he, 1)
        art_mix = round(ha, 1)
        nar_total, nar_details = 0, {k: 0 for k in ('narrative_story', 'narrative_role',
                                                      'narrative_hook', 'narrative_tags',
                                                      'narrative_shot', 'narrative_total')}

    # 新权重: 摄影(20) + 情绪(25) + 艺术(15) + 叙事(40) = 100
    photo_weighted = round(photo_mix * 20 / 35, 1)
    emo_weighted = round(emo_mix * 25 / 35, 1)
    art_weighted = round(art_mix * 15 / 30, 1)
    total = round(photo_weighted + emo_weighted + art_weighted + nar_total, 1)

    return photo_weighted, emo_weighted, art_weighted, nar_total, total, nar_details


# 视觉增强字段
extra_fields = {}
if vision_map:
    extra_fields['content_type'] = lambda p, v: v.get('content_type', '') if v else ''
    extra_fields['mood'] = lambda p, v: v.get('mood', '') if v else ''
    extra_fields['aesthetic_score_raw'] = lambda p, v: v.get('aesthetic_score', '') if v else ''
    extra_fields['has_people'] = lambda p, v: v.get('has_people', False) if v else False
    extra_fields['face_count'] = lambda p, v: v.get('face_count', 0) if v else 0
    extra_fields['recommended_positions'] = lambda p, v: ','.join(map(str, v.get('recommended_grid_positions', []))) if v else ''
    extra_fields['shot_type'] = lambda p, v: v.get('shot_type', '') if v else ''
    extra_fields['narrative_role'] = lambda p, v: v.get('narrative_role', '') if v else ''
    extra_fields['visual_hook'] = lambda p, v: v.get('visual_hook', 0) if v else 0
    extra_fields['element_tags'] = lambda p, v: ','.join(v.get('element_tags', [])) if v else ''
    extra_fields['camera_angle'] = lambda p, v: v.get('camera_angle', '') if v else ''

# 评分所有候选
scored = []
for p in candidates:
    jpg_name = p['filename'].replace('.heic', '.jpg')
    v = vision_map.get(jpg_name)
    photo_s, emo_s, art_s, nar_s, total, nar_details = score_photo(p, v)

    entry = {
        'filename': jpg_name,
        'score_photography': photo_s,
        'score_emotion': emo_s,
        'score_art': art_s,
        'score_narrative': nar_s,
        'total': total,
        'sharpness': p['sharpness'],
        'brightness': p['brightness'],
        'contrast': p['contrast'],
        'saturation': p['saturation'],
        'color_temp': p['color_temp'],
        'aspect_ratio': p['aspect_ratio'],
        'underexposed_pct': p['underexposed_pct'],
        'filesize_bytes': p['filesize_bytes'],
    }
    entry.update(nar_details)
    for key, fn in extra_fields.items():
        entry[key] = fn(p, v)
    scored.append(entry)

scored.sort(key=lambda x: x['total'], reverse=True)

# 输出 Top 30
print(f'\n===== Top 30 (新权重: 摄影20 + 情绪25 + 艺术15 + 叙事40 = 100) =====')
header = f'{"排名":>3} {"文件名(简称)":<22} {"摄影":>5} {"情绪":>5} {"艺术":>5} {"叙事":>5} {"总分":>5}'
if vision_map:
    header += f' {"内容":<10} {"心情":<10} {"景别":<10}'
print(header)
print('-' * (120 if vision_map else 90))
for i, s in enumerate(scored[:30]):
    short = s['filename'].replace('.jpg', '')[-18:]
    line = f'  {i+1:>2}  {short:<20}  {s["score_photography"]:>5.1f}  {s["score_emotion"]:>5.1f}  {s["score_art"]:>5.1f}  {s["score_narrative"]:>5.1f}  {s["total"]:>5.1f}'
    if vision_map:
        line += f' {cn(s.get("content_type","?"), CN_CONTENT_TYPE):<10} {cn(s.get("mood","?"), CN_MOOD):<10} {cn(s.get("shot_type","?"), CN_SHOT_TYPE):<10}'
    print(line)

# ========== 4. 统计 ==========
top30 = scored[:30]
print(f'\nTop30中: 竖图={sum(1 for p in top30 if p["aspect_ratio"]<0.9)} 横图={sum(1 for p in top30 if p["aspect_ratio"]>1.1)}')
print(f'Top30中: 暖调={sum(1 for p in top30 if p["color_temp"]>10)} 冷调={sum(1 for p in top30 if p["color_temp"]<-10)}')

if vision_map:
    cts = Counter(s.get('content_type', '?') for s in top30)
    moods = Counter(s.get('mood', '?') for s in top30)
    shots = Counter(s.get('shot_type', '?') for s in top30)
    has_ppl = sum(1 for s in top30 if s.get('has_people'))
    # 英文→中文翻译
    cts_cn = {cn(k, CN_CONTENT_TYPE): v for k, v in cts.items()}
    moods_cn = {cn(k, CN_MOOD): v for k, v in moods.items()}
    shots_cn = {cn(k, CN_SHOT_TYPE): v for k, v in shots.items()}
    print(f'Top30中: {cts_cn}')
    print(f'Top30中: 有人物={has_ppl} 心情={moods_cn} 景别={shots_cn}')
    nar_avg = sum(s.get('score_narrative', 0) for s in top30) / len(top30)
    print(f'Top30中: 平均叙事分={nar_avg:.1f}/40')

# ========== 5. 叙事蓝图驱动匹配 ==========

POS_LABELS = ['角(1)', '位2', '位3', '位4', 'C位(5)', '位6', '位7', '位8', '角(9)']


def position_fit(photo, pos_req):
    """计算照片对某个蓝图位置的匹配度 (0-100)"""
    score = 0
    st = photo.get('shot_type', '')
    target_shots = pos_req.get('shot_types', [])
    if st in target_shots:
        score += 25
    elif CAN_CROP_MAP.get(st, []) and any(s in target_shots for s in CAN_CROP_MAP.get(st, [])):
        score += 15
    photo_moods = photo.get('mood', '').split('|')
    if any(m in pos_req.get('moods', []) for m in photo_moods):
        score += 20
    ct = photo.get('content_type', '')
    if ct in pos_req.get('content_types', []):
        score += 15
    tags = set(photo.get('element_tags', [])) if isinstance(photo.get('element_tags', []), list) else set()
    if tags:
        shared = len(tags & set(pos_req.get('element_tags', [])))
        score += shared * 5
    if photo.get('has_people') == pos_req.get('needs_people', False):
        score += 10
    min_ns = pos_req.get('min_negative_space', 0)
    if min_ns > 0 and photo.get('negative_space', 0) >= min_ns:
        score += 10
    # 色调匹配
    pref_tone = pos_req.get('color_tone', 'any')
    ct_val = photo.get('color_temp', 0) or 0
    if pref_tone != 'any':
        if (pref_tone == 'warm' and ct_val > 15) or \
           (pref_tone == 'cool' and ct_val < -15) or \
           (pref_tone == 'neutral' and -15 <= ct_val <= 15):
            score += 10
        elif (pref_tone == 'warm' and ct_val > 0) or \
             (pref_tone == 'cool' and ct_val < 0):
            score += 5
    score += photo.get('score_narrative', 0) * 0.15
    return min(score, 100)


def plan_build_from_blueprint(blueprint_key, scored_all, blueprints=None):
    """基于叙事蓝图构建九宫格方案
    返回 (plan, diversity_notes): plan=[(pos_label, entry), ...]
    """
    if blueprints is None:
        blueprints = get_blueprints(scored_all) or {}
    blueprint = blueprints.get(blueprint_key)
    if not blueprint or not blueprint.get('positions'):
        return [], []

    positions = blueprint['positions']
    available = sorted(scored_all, key=lambda x: x['total'], reverse=True)
    used_filenames = set()
    plan = []
    diversity_notes = []

    pos_indices = sorted(
        range(len(positions)),
        key=lambda i: -(len(positions[i].get('shot_types', [])) * 3
                        + len(positions[i].get('moods', [])) * 2
                        + len(positions[i].get('element_tags', [])) * 1)
    )

    for idx in pos_indices:
        pos_req = positions[idx]
        best_photo = None
        best_score = -1

        # 检查已选相邻位置的色温，构建 penalty 函数
        def color_continuity_penalty(p, idx):
            """跨位置色温连续性检查：相邻格色温差越大惩罚越大"""
            ct_p = p.get('color_temp', 0) or 0
            for adj in [idx - 1, idx + 1]:
                if adj < 0 or adj >= len(positions):
                    continue
                # 检查该相邻位置是否已选
                adj_photo = None
                for pos_label, ap in plan:
                    pos_i = POS_LABELS.index(pos_label) if pos_label in POS_LABELS else -1
                    if pos_i == adj:
                        adj_photo = ap
                        break
                if adj_photo:
                    ct_adj = adj_photo.get('color_temp', 0) or 0
                    diff = abs(ct_p - ct_adj)
                    if diff > 40:
                        return 0.5   # 剧烈跳跃 → 扣50%
                    elif diff > 25:
                        return 0.75  # 明显跳跃 → 扣25%
            return 1.0  # 无惩罚

        for p in available:
            if p['filename'] in used_filenames:
                continue
            f = position_fit(p, pos_req)
            # 色温连续性惩罚
            f *= color_continuity_penalty(p, idx)
            if f > best_score:
                best_score = f
                best_photo = p

        if best_photo:
            used_filenames.add(best_photo['filename'])
            pos_label = POS_LABELS[idx] if idx < len(POS_LABELS) else f'位{idx+1}'
            plan.append((pos_label, best_photo))
        else:
            for p in available:
                if p['filename'] not in used_filenames:
                    used_filenames.add(p['filename'])
                    pos_label = POS_LABELS[idx] if idx < len(POS_LABELS) else f'位{idx+1}'
                    plan.append((pos_label, p))
                    diversity_notes.append(p['filename'])
                    break

    return plan, diversity_notes


# ========== 6. 裁剪引擎 ==========

SUGGESTED_CROP_REASONS = {
    'long_shot_to_medium': '远景→中景：裁切多余天空和远景，聚焦主体区域',
    'long_shot_to_close_up': '远景→特写：放大主体元素，突出细节',
    'center_1_1': '1:1中心裁切：保留核心构图，统一网格比例',
    'rule_of_thirds': '三分法裁切：将主体移至左侧/右侧三分点',
    'subject_focus': '主体聚焦：围绕检测到的人物/主体裁切，排除干扰',
    'negative_space_preserve': '保留留白区域，强化呼吸感',
    'leading_line_crop': '沿引导线方向裁切，强化纵深感',
    'remove_distraction': '移除边角干扰元素，纯净画面',
}


def suggest_crop(photo, target_shot_type, resized_w=2560, resized_h=2560):
    """根据目标景别和构图分析生成裁剪建议"""
    sp = photo.get('subject_prominence', 5)
    neg = photo.get('negative_space', 5)
    st = photo.get('shot_type', '')
    has_people = photo.get('has_people', False)
    aspect = photo.get('aspect_ratio', 1.0)

    if st == target_shot_type or target_shot_type == st:
        if aspect > 1.0:
            crop_w = int(resized_h)
            crop_h = resized_h
            x1 = (resized_w - crop_w) // 2
            y1 = 0
        else:
            crop_w = resized_w
            crop_h = resized_w
            x1 = 0
            y1 = (resized_h - crop_h) // 2
        return {
            'crop_box': [x1, y1, x1 + crop_w, y1 + crop_h],
            'crop_aspect': '1:1',
            'reason': SUGGESTED_CROP_REASONS['center_1_1'],
            'focus_point': [crop_w // 2, crop_h // 2],
        }

    if st == 'long_shot' and target_shot_type in ('medium', 'medium_full', 'close_up'):
        w, h = resized_w, resized_h
        if has_people and sp >= 6:
            crop_h = int(h * 0.45)
            crop_w = int(crop_h * 1.0)
            x1 = (w - crop_w) // 2
            y1 = h - crop_h - int(h * 0.05)
            reason = SUGGESTED_CROP_REASONS['long_shot_to_medium']
        elif sp >= 7:
            crop_size = min(w, h) * 0.6
            crop_w = crop_h = int(crop_size)
            x1 = (w - crop_w) // 2
            y1 = int(h * 0.25)
            reason = SUGGESTED_CROP_REASONS['subject_focus']
        else:
            crop_h = int(h * 0.40)
            crop_w = int(crop_h * 1.0)
            x1 = (w - crop_w) // 2
            y1 = int(h * 0.35)
            reason = SUGGESTED_CROP_REASONS['long_shot_to_medium']
        return {
            'crop_box': [x1, y1, x1 + crop_w, y1 + crop_h],
            'crop_aspect': '1:1',
            'reason': reason,
            'focus_point': [crop_w // 2, crop_h // 3],
        }

    if neg >= 7:
        w, h = resized_w, resized_h
        crop_w = int(w * 0.7)
        crop_h = int(h * 0.7)
        return {
            'crop_box': [0, 0, crop_w, crop_h],
            'crop_aspect': '1:1',
            'reason': SUGGESTED_CROP_REASONS['negative_space_preserve'],
            'focus_point': [crop_w // 4, crop_h // 4],
        }

    return None


# ========== 7. 基础方案 + 动态叙事发现 + 构建方案 ==========

# 4 套基础方案（顺序：旅程叙事 → 情绪弧线 → 光影对比 → 极简留白）
STATIC_KEYS = ['journey', 'emotion_arc', 'light_shadow', 'minimalist']

active_blueprints = {}
if vision_map:
    # 使用 scored 数据发现主题（转换 element_tags 为列表格式）
    scored_for_discovery = []
    for s in scored:
        et = s.get('element_tags', '')
        if isinstance(et, str) and et:
            s = dict(s)
            s['element_tags'] = [t.strip() for t in et.split(',') if t.strip()]
        elif not et:
            continue
        scored_for_discovery.append(s)
    # get_blueprints() 现在返回 4 套基础方案 + 动态发现主题
    active_blueprints = get_blueprints(scored_for_discovery if scored_for_discovery else scored)

    if active_blueprints:
        # 分离静态（基础方案）和动态（自动发现）
        static_keys = [k for k in STATIC_KEYS if k in active_blueprints]
        dynamic_keys = [k for k in active_blueprints if k not in STATIC_KEYS]

        # 仅对动态主题输出发现报告
        if dynamic_keys:
            from scripts.theme_discovery import (
                print_discovery_report, interactive_select_themes, save_discovered_themes
            )
            dynamic_bps = {k: active_blueprints[k] for k in dynamic_keys}
            print_discovery_report(scored, dynamic_bps)

        # 根据 CLI 参数决定选择哪些动态主题（基础方案始终包含）
        selected_keys = list(static_keys)

        if args.discover_only:
            # --discover-only: 只打印动态发现报告，保存，退出
            if dynamic_keys:
                save_discovered_themes(scored, {k: active_blueprints[k] for k in dynamic_keys})
                print(f"✅ 发现结果已保存到: output/discovered_themes.json")
                print(f"   使用 --themes 指定自动发现主题编号（基础方案始终包含）")
                print(f"   python scripts/score_and_group.py --mode {args.mode or _resolved} --themes 1,2")
            sys.exit(0)

        elif args.interactive and dynamic_keys:
            selected_dynamic = interactive_select_themes(dynamic_bps)
            if not selected_dynamic:
                print("⚠️  未选择自动发现主题，仅使用基础方案")
            selected_keys = static_keys + selected_dynamic

        elif args.themes and dynamic_keys:
            themes_path = _PROJECT_ROOT / "output" / "discovered_themes.json"
            selected_dynamic = []
            if themes_path.exists():
                for part in args.themes.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(dynamic_keys):
                            selected_dynamic.append(dynamic_keys[idx])
                    else:
                        if part in active_blueprints:
                            selected_dynamic.append(part)
            if not selected_dynamic:
                print(f"⚠️  未找到指定主题编号，仅使用基础方案")
            selected_keys = static_keys + selected_dynamic

        else:
            # 默认：基础方案 + 全部动态主题
            selected_keys = static_keys + dynamic_keys

        # 打印选择的主题
        static_names = [active_blueprints[k]["name"] for k in selected_keys if k in static_keys]
        dynamic_names = [active_blueprints[k]["name"] for k in selected_keys if k in dynamic_keys]
        parts = []
        if static_names:
            parts.append(f"📋 基础方案({len(static_names)}套): {', '.join(static_names)}")
        if dynamic_names:
            parts.append(f"🎯 自动发现({len(dynamic_names)}套): {', '.join(dynamic_names)}")
        for p in parts:
            print(f"\n{p}")

# 用选择的蓝图构建方案
plan_data = {}
div_data = {}

for bk in selected_keys if active_blueprints else []:
    plan, div = plan_build_from_blueprint(bk, scored, active_blueprints)
    plan_data[bk] = plan
    div_data[bk] = div

# 显示方案
for bk in plan_data:
    plan = plan_data.get(bk, [])
    div_notes = div_data.get(bk, [])
    if not plan:
        continue

    bp_info = active_blueprints.get(bk, {})
    tag = "📋 基础方案" if bk in STATIC_KEYS else "🎯 自动发现"
    plan_name = f"{tag} · {bp_info.get('name', bk)}"
    plan_desc = bp_info.get('description', '')

    print()
    print(f"===== {plan_name} =====")
    print(f"  📝 {plan_desc}")
    if vision_map:
        cts = [p.get('content_type', '?') for _, p in plan]
        mds = [p.get('mood', '?') for _, p in plan]
        shots = [p.get('shot_type', '?') for _, p in plan]
        angles = [p.get('camera_angle', '?') for _, p in plan]
        ppl = sum(1 for _, p in plan if p.get('has_people'))
        total_fit = sum(position_fit(p, bp_info['positions'][i])
                        for i, (_, p) in enumerate(plan) if i < len(bp_info['positions']))
        avg_fit = round(total_fit / min(len(plan), 9), 1)
        print(f"  匹配度: {avg_fit}/100")
        print(f"  内容: {dict((cn(k, CN_CONTENT_TYPE), v) for k, v in Counter(cts).items())}  心情: {dict((cn(k, CN_MOOD), v) for k, v in Counter(mds).items())}")
        print(f"  景别: {dict((cn(k, CN_SHOT_TYPE), v) for k, v in Counter(shots).items())}  角度: {dict((cn(k, CN_CAMERA_ANGLE), v) for k, v in Counter(angles).items())}  有人物: {ppl}/9")
        if div_notes:
            print(f"  ⚠️ 降级填充: {[n[-12:] for n in div_notes]}")
    for i, (pos, p) in enumerate(plan):
        extra = ''
        b_role = bp_info['positions'][i]['role'] if i < len(bp_info['positions']) else ''
        target_st = bp_info['positions'][i]['shot_types'][0] if i < len(bp_info['positions']) and bp_info['positions'][i]['shot_types'] else p.get('shot_type', '')
        crop = suggest_crop(p, target_st)
        crop_note = ''
        if crop and crop['reason']:
            crop_note = f' ✂️{crop["reason"][:20]}'
        if vision_map:
            extra = f' 内容={cn(p.get("content_type","?"), CN_CONTENT_TYPE)} 景别={cn(p.get("shot_type","?"), CN_SHOT_TYPE)}'
            if p.get('has_people'):
                extra += f' 👤{p.get("face_count",0)}'
            extra += f' 心情={cn(p.get("mood","?"), CN_MOOD)} 叙事={p.get("score_narrative",0):.1f}'
        print(f'  {pos}: {p["filename"][:30]} 总分={p["total"]} [{b_role}]{crop_note}{extra}')

# 推荐方案（按匹配度自动选择）
best_bk = list(plan_data.keys())[0] if plan_data else None
best_fit = -1
for bk in plan_data:
    plan = plan_data.get(bk, [])
    bp_info = active_blueprints.get(bk, {})
    if plan and bp_info.get('positions'):
        total_fit = sum(position_fit(p, bp_info['positions'][i])
                        for i, (_, p) in enumerate(plan) if i < len(bp_info['positions']))
        avg_fit = total_fit / min(len(plan), 9)
        if avg_fit > best_fit:
            best_fit = avg_fit
            best_bk = bk
best_plan = plan_data.get(best_bk, []) if best_bk else []
# ========== 保存输出 ==========
# score_matrix.csv
csv_cols = ['排名', 'filename', '摄影(20)', '情绪(25)', '艺术(15)', '叙事(40)', '总分(100)',
            '亮度', '清晰度', '对比度', '饱和度', '色温', '比例']
if vision_map:
    csv_cols.extend(['内容类型', '心情', '景别', '叙事角色', '美学原始分', '有人物', '人脸数', '推荐位置',
                     'visual_hook', 'element_tags', 'camera_angle'])

with open(f'{OUT_DIR}/score_matrix.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(csv_cols)
    for i, s in enumerate(scored):
        row = [i+1, s['filename'], s['score_photography'], s['score_emotion'], s['score_art'],
               s['score_narrative'], s['total'],
               s['brightness'], s['sharpness'], s['contrast'], s['saturation'], s['color_temp'],
               round(s['aspect_ratio'], 2)]
        if vision_map:
            row.extend([
                s.get('content_type', ''), s.get('mood', ''), s.get('shot_type', ''),
                s.get('narrative_role', ''), s.get('aesthetic_score_raw', ''),
                s.get('has_people', False), s.get('face_count', 0),
                s.get('recommended_positions', ''), s.get('visual_hook', ''),
                s.get('element_tags', ''), s.get('camera_angle', '')
            ])
        writer.writerow(row)

print(f'\n评分矩阵已保存: {OUT_DIR}/score_matrix.csv')

# full_scored.json
with open(f'{OUT_DIR}/full_scored.json', 'w', encoding='utf-8') as f:
    json.dump(scored, f, ensure_ascii=False, indent=2)

# groups.json
groups_output = []
for i, g in enumerate(groups):
    fnames = [p['filename'].replace('.heic', '.jpg') for p in g]
    content_types = list(set(get_content_type(fn) for fn in fnames))
    group_info = {
        'group_id': i + 1,
        'size': len(g),
        'filenames': fnames,
        'avg_brightness': round(sum(p['brightness'] for p in g) / len(g), 1),
        'avg_sharpness': round(sum(p['sharpness'] for p in g) / len(g), 1),
        'content_types': content_types if content_types != ['unknown'] else [],
        'keep': fnames[0] if fnames else '',
        'reject': fnames[1:] if len(fnames) > 1 else [],
    }
    groups_output.append(group_info)

with open(f'{OUT_DIR}/groups.json', 'w', encoding='utf-8') as f:
    json.dump(groups_output, f, ensure_ascii=False, indent=2)
print(f'相似组已保存: {OUT_DIR}/groups.json ({len(groups)} 组)')

# 保存淘汰信息
with open(f'{OUT_DIR}/eliminated.json', 'w', encoding='utf-8') as f:
    json.dump(eliminated, f, ensure_ascii=False, indent=2)

# 叙事方案保存为 JSON（动态蓝图 → 动态 keys）
narrative_plans = {
    'version': version,
    'mode': _resolved,
    'plan_names': {bk: {"name": active_blueprints.get(bk, {}).get("name", bk),
                         "description": active_blueprints.get(bk, {}).get("description", ""),
                         "category": "基础方案" if bk in STATIC_KEYS else "自动发现"}
                   for bk in plan_data if bk in active_blueprints},
}
for bk in plan_data:
    plan = plan_data[bk]
    plan_key = f"plan_{bk}"
    narrative_plans[plan_key] = [
        {'position': pos, 'filename': p['filename'], 'total': p['total'],
         'content_type': p.get('content_type', ''),
         'mood': p.get('mood', ''),
         'shot_type': p.get('shot_type', ''),
         'narrative_role': p.get('narrative_role', ''),
         'visual_hook': p.get('visual_hook', ''),
         'has_people': p.get('has_people', False)}
        for pos, p in plan
    ]

with open(f'{OUT_DIR}/narrative_plans.json', 'w', encoding='utf-8') as f:
    json.dump(narrative_plans, f, ensure_ascii=False, indent=2)
print(f'叙事方案已保存: {OUT_DIR}/narrative_plans.json')

# ========== 调用可视化报告生成 ==========
print(f'\n{"─" * 50}')
print(f'  正在生成可视化报告…')
vis_result = subprocess.run(
    [sys.executable, 'scripts/generate_visual_report.py',
     '--input-dir', OUT_DIR],
    capture_output=False,
).returncode
if vis_result != 0:
    print(f'  ⚠️ 可视化报告生成失败 (exit={vis_result})')
    print(f'  请手动运行: python scripts/generate_visual_report.py --input-dir {OUT_DIR}')

# 推荐方案输出
best_name = active_blueprints.get(best_bk, {}).get("name", best_bk) if best_bk and best_bk in active_blueprints else "推荐方案"
best_tag = "📋 基础方案" if best_bk and best_bk in STATIC_KEYS else "🎯 自动发现"
print(f'\n{"=" * 60}')
print(f'  🎯 推荐方案: {best_tag} · {best_name}（匹配度最高）')
print(f'{"=" * 60}')

# copy 脚本（使用推荐方案）
with open(f'{OUT_DIR}/copy_final_9.sh', 'w', encoding='utf-8') as f:
    f.write('#!/bin/bash\n')
    f.write('# 复制最终 9 张到 photos/selected/\n')
    f.write('mkdir -p ../photos/selected\n\n')
    for pos, p in best_plan:
        src = f'../photos/resized/{p["filename"]}'
        dst = f'../photos/selected/{pos}_{p["filename"]}'
        f.write(f'cp "{src}" "{dst}"\n')

print(f'复制脚本已保存: {OUT_DIR}/copy_final_9.sh')
print('\n全部完成！')
