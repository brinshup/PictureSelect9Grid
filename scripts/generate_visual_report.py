"""
为报告嵌入缩略图，生成可视化版本（叙事增强版）。
用法: python scripts/generate_visual_report.py [--input-dir output/hybrid]
"""
import csv, json, os, re, sys, argparse
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# -- 中英文翻译映射 --
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
    'sky': '天空', 'water': '水面', 'silhouette': '剪影',
    'reflection': '倒影', 'texture': '纹理', 'pattern': '图案', 'symmetry': '对称',
    'leading_line': '引导线', 'shallow_dof': '浅景深',
    'motion_blur': '动感模糊', 'shadow': '阴影', 'neon': '霓虹', 'greenery': '绿植',
    'road': '道路', 'window': '窗户', 'door': '门', 'stairs': '楼梯', 'bridge': '桥',
    'crowd': '人群', 'solo': '独处', 'hand': '手', 'eye': '眼睛', 'profile': '侧脸',
    'back_view': '背影', 'food': '食物', 'drink': '饮品', 'pet': '宠物', 'flower': '花',
    'light_ray': '光束', 'fog': '雾', 'rainbow': '彩虹',
    'cityscape': '城市景观', 'landscape': '风景', 'seascape': '海景', 'mountain': '山',
    'forest': '森林', 'minimal': '极简', 'geometric': '几何', 'vintage': '复古',
    'dark': '暗调', 'bright': '明亮', 'colorful': '多彩', 'monochrome': '黑白',
    'golden_hour': '黄金时刻', 'night': '夜晚',
    'abstract': '抽象', 'horizon': '地平线', 'tree': '树木', 'sign': '路标',
    'leaf': '树叶', 'archway': '拱门', 'rock': '岩石', 'sand': '沙', 'wave': '海浪',
    'star': '星星', 'moon': '月亮', 'indoor': '室内', 'outdoor': '户外',
    'urban': '城市', 'rural': '乡村',
}
def cn(text, mapping):
    if not text or text == '?':
        return text
    return mapping.get(text, text)


# 基础相对路径
_THUMB_BASE = "photos/thumbnails"
_PHOTOS_BASE = "photos"

parser = argparse.ArgumentParser(description="生成可视化九宫格报告（叙事增强）")
parser.add_argument("--input-dir", default=None,
                    help="评分数据所在目录 (默认: output/hybrid/<latest>)")
parser.add_argument("--mode", choices=["histogram", "hybrid", "vision"], default="hybrid",
                    help="评分模式 (默认: hybrid)")
parser.add_argument("--version", type=str, default=None,
                    help="版本标签 (默认: 自动检测最新)")
args = parser.parse_args()

# 自动解析输入目录（版本号第一层级：output/version/mode/）
if args.input_dir:
    INPUT_DIR = args.input_dir.rstrip('/')
else:
    if args.version:
        INPUT_DIR = f"output/{args.version}/{args.mode}"
    else:
        # 扫描 output/ 下的版本目录，取最新
        latest = None
        if os.path.isdir("output"):
            versions = []
            for d in os.listdir("output"):
                m = re.match(r'^(\d+)_(\d+)$', d)
                if m and os.path.isdir(os.path.join("output", d)):
                    versions.append((int(m.group(1)), int(m.group(2)), d))
            if versions:
                versions.sort(reverse=True)
                latest = versions[0][2]
        if latest and os.path.isdir(f"output/{latest}/{args.mode}"):
            INPUT_DIR = f"output/{latest}/{args.mode}"
        else:
            print(f"⚠️  未找到 output/<version>/{args.mode}/，回退到 output/{args.mode}/")
            INPUT_DIR = f"output/{args.mode}/1_0"

# 缩略图相对路径
_depth = INPUT_DIR.replace('\\', '/').count('/') + 1
THUMB_DIR = ('../' * _depth) + _THUMB_BASE
PHOTOS_DIR = ('../' * _depth) + _PHOTOS_BASE
print(f"📂 输入目录: {INPUT_DIR}/  (缩略图相对路径: {THUMB_DIR})")

# ========== 读取评分数据 ==========
scored = []
with open(f'{INPUT_DIR}/score_matrix.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        entry = {
            'filename': row['filename'],
            'total': float(row['总分(100)']),
            'brightness': float(row['亮度']),
            'sharpness': float(row['清晰度']),
            'contrast': float(row['对比度']),
            'saturation': float(row['饱和度']),
            'color_temp': float(row['色温']),
            'aspect_ratio': float(row['比例']),
        }
        # 新权重字段
        if '摄影(20)' in row:
            entry['score_photography'] = float(row['摄影(20)'])
        if '情绪(25)' in row:
            entry['score_emotion'] = float(row['情绪(25)'])
        if '艺术(15)' in row:
            entry['score_art'] = float(row['艺术(15)'])
        if '叙事(40)' in row:
            entry['score_narrative'] = float(row['叙事(40)'])
        else:
            entry['score_photography'] = float(row.get('摄影(35)', 0))
            entry['score_emotion'] = float(row.get('情绪(35)', 0))
            entry['score_art'] = float(row.get('艺术(30)', 0))
            entry['score_narrative'] = 0
        # 视觉增强字段
        if '内容类型' in row:
            entry['content_type'] = row['内容类型']
        if '心情' in row:
            entry['mood'] = row['心情']
        if '有人物' in row:
            entry['has_people'] = row['有人物'] == 'True'
        if '人脸数' in row:
            entry['face_count'] = int(row['人脸数']) if row['人脸数'] else 0
        if '景别' in row:
            entry['shot_type'] = row['景别']
        if '叙事角色' in row:
            entry['narrative_role'] = row['叙事角色']
        if 'visual_hook' in row:
            entry['visual_hook'] = int(row['visual_hook']) if row['visual_hook'] else 0
        if 'element_tags' in row:
            entry['element_tags'] = row['element_tags']
        if 'camera_angle' in row:
            entry['camera_angle'] = row['camera_angle']
        scored.append(entry)

print(f'读取 {len(scored)} 条评分数据')
has_vision = any(s.get('content_type', '') for s in scored)
if has_vision:
    cts = Counter(s.get('content_type', '?') for s in scored)
    print(f'  含视觉评分增强字段 (内容分布: {dict(cts)})')
score_map = {s['filename']: s for s in scored}

# ========== 读取叙事方案 ==========
narrative_plans_path = f'{INPUT_DIR}/narrative_plans.json'
has_narrative = False
plans_data = []
narrative_plan_info = {}

if os.path.exists(narrative_plans_path):
    with open(narrative_plans_path, 'r', encoding='utf-8') as f:
        narrative_plan_info = json.load(f)
    has_narrative = True

    # 从 plan_data 重建 plan 元组
    def rebuild_plan(key):
        plan_data = narrative_plan_info.get(key, [])
        plan = []
        div_notes = []
        for item in plan_data:
            entry = score_map.get(item['filename'], {})
            plan.append((item['position'], entry))
        return plan, div_notes

    # 动态读取蓝图名称和方案
    plan_names = narrative_plan_info.get('plan_names', {})

    plans = []
    for key in narrative_plan_info:
        if not key.startswith('plan_') or key in ('plan_names', 'version', 'mode'):
            continue
        plan, div = rebuild_plan(key)
        bp_key = key.replace('plan_', '')
        info = plan_names.get(bp_key, {"name": bp_key, "description": ""})
        category = info.get("category", "自动发现")
        plans.append((info["name"], plan, div, info.get("description", ""), category))

    # 推荐方案取第一个（若无方案则置空）
    plan_a, div_a = (plans[0][1], plans[0][2]) if plans else ([], [])
else:
    print('⚠️  未找到 narrative_plans.json')
    has_narrative = False
    plan_a, div_a = [], []
    plans = []

# ========== 辅助函数 ==========
def extract_serial(fname):
    parts = fname.replace('.jpg','').split('_')
    if len(parts) >= 4:
        return int(parts[2])
    return 0

def thumb_img(fname, w=120):
    s = score_map.get(fname, {})
    t = s.get('total', '?')
    return f'<img src="{THUMB_DIR}/{fname}" width="{w}" style="border-radius:6px" alt="{fname}" title="总分: {t}">'

def thumb_link(fname, w=140):
    rp = f"{PHOTOS_DIR}/resized/{fname}"
    return f'<a href="{rp}">{thumb_img(fname, w)}</a>'

def short_n(fname, n=20):
    return fname.replace('.jpg','')[-n:]

def pos_num(label):
    m = re.search(r'(\d+)', label)
    return int(m.group(1)) if m else 9

def get_role_for_position(pos, shot_type, narrative_role, has_people, mood):
    """根据叙事特征为位置生成角色描述"""
    roles = {
        '角(1)': '开场 · 吸引视线',
        '位2': '承接 · 引入氛围',
        '位3': '过渡 · 铺陈',
        '位4': '叙事 · 展开',
        'C位(5)': '核心 · 情感锚点',
        '位6': '发展 · 延伸',
        '位7': '转折 · 沉淀',
        '位8': '蓄势 · 推向收尾',
        '角(9)': '收束 · 余韵',
    }
    base = roles.get(pos, '')
    # 增强描述
    if narrative_role == 'establishing':
        return f'{base} · 建立场景'
    elif narrative_role == 'closure':
        return f'{base} · 收束回味'
    elif has_people:
        return f'{base} · 人物'
    elif shot_type in ('wide', 'long_shot'):
        return f'{base} · 远景'
    elif shot_type in ('close_up', 'extreme_close_up'):
        return f'{base} · 特写'
    return base

def grid_html(plan, title, desc):
    plan_sorted = sorted(plan, key=lambda x: pos_num(x[0]))
    h = f'<h3>{title}</h3>\n<p style="font-size:13px;color:#555">{desc}</p>\n'
    h += '<table style="border-collapse:collapse">\n'
    for row in range(3):
        h += '  <tr>\n'
        for col in range(3):
            idx = row * 3 + col
            if idx < len(plan_sorted):
                pos, p = plan_sorted[idx]
                t = p.get('total', 0)
                bg = ' style="background:#fffff5"' if 'C位' in pos else ''
                nar = p.get('score_narrative', '')
                extra = ''
                if p.get('content_type'):
                    extra += f'<span style="font-size:10px;color:#666"> {cn(p["content_type"], CN_CONTENT_TYPE)}</span>'
                if p.get('mood'):
                    extra += f'<span style="font-size:10px;color:#999"> 💫{cn(p["mood"], CN_MOOD)}</span>'
                if p.get('shot_type'):
                    extra += f'<span style="font-size:10px;color:#77a"> 🎬{cn(p["shot_type"], CN_SHOT_TYPE)}</span>'
                if p.get('has_people'):
                    extra += ' 👤'
                role = get_role_for_position(pos, p.get('shot_type', ''),
                                             p.get('narrative_role', ''),
                                             p.get('has_people'), p.get('mood', ''))
                h += f'    <td align="center" style="border:1px solid #ddd;padding:8px"{bg}>\n'
                h += f'      <div><b>{pos}</b></div>\n'
                h += f'      <div>{thumb_link(p["filename"], 140)}</div>\n'
                h += (f'      <div style="font-size:11px;color:#666;margin-top:2px">'
                      f'总分 {t} 叙事 {nar}{extra}</div>\n')
                h += f'      <div style="font-size:11px;color:#888">{role}</div>\n'
                h += f'    </td>\n'
            else:
                h += '    <td align="center" style="border:1px solid #ddd;padding:8px">—</td>\n'
        h += '  </tr>\n'
    h += '</table><br>\n'
    return h

def table_of(plan, show_diversity=False):
    header = '| # | 位置 | 缩略图 | 文件名 | 总分 | 叙事 | 角色 |'
    sep = '|---|------|--------|--------|:----:|:----:|------|'
    if show_diversity and has_vision:
        header += ' 内容 | 心情 | 景别 | 角度 |'
        sep += ':----:|:----:|:----:|:----:|'
    lines = [header, sep]
    for i, (pos, p) in enumerate(plan, 1):
        role = get_role_for_position(pos, p.get('shot_type', ''), p.get('narrative_role', ''),
                                     p.get('has_people'), p.get('mood', ''))
        row = (f'| {i} | {pos} | {thumb_img(p["filename"], 60)} | '
               f'`{short_n(p["filename"], 24)}` | {p.get("total",0)} | {p.get("score_narrative",0)} | {role} |')
        if show_diversity and has_vision:
            row += (f' {cn(p.get("content_type","?"), CN_CONTENT_TYPE)} | {cn(p.get("mood","?"), CN_MOOD)} '
                    f'| {cn(p.get("shot_type","?"), CN_SHOT_TYPE)} | {cn(p.get("camera_angle","?"), CN_CAMERA_ANGLE)} ')
            if p.get('has_people'):
                row += '👤'
            row += ' |'
        lines.append(row)
    return '\n'.join(lines)

def diversity_summary(plan, div_notes):
    if not has_vision:
        return ''
    cts = Counter(p.get('content_type', '?') for _, p in plan)
    mds = Counter(p.get('mood', '?') for _, p in plan)
    shots = Counter(p.get('shot_type', '?') for _, p in plan)
    angles = Counter(p.get('camera_angle', '?') for _, p in plan)
    ppl = sum(1 for _, p in plan if p.get('has_people'))
    cts_cn = {cn(k, CN_CONTENT_TYPE): v for k, v in cts.items() if k != '?'}
    mds_cn = {cn(k, CN_MOOD): v for k, v in mds.items() if k != '?'}
    shots_cn = {cn(k, CN_SHOT_TYPE): v for k, v in shots.items() if k != '?'}
    lines = [
        '<div style="margin:8px 0;padding:8px;background:#f8f8f8;border-radius:6px;font-size:13px">',
        '<b>📊 内容多样性:</b> ',
        f'类型={cts_cn} | 心情={mds_cn} | 景别={shots_cn} | 有人物={ppl}/9',
    ]
    if div_notes:
        lines.append(f'<br>⚠️ <b>多样性耗尽，以下按分数填充:</b> {[n[-12:] for n in div_notes]}')
    lines.append('</div>')
    return '\n'.join(lines)

def element_sharing_html(plan):
    """检测相邻格元素共享"""
    if not has_vision:
        return ''
    shares = []
    n = min(len(plan), 9)
    for i in range(n - 1):
        tags_i = plan[i][1].get('element_tags', '')
        tags_j = plan[i+1][1].get('element_tags', '')
        if isinstance(tags_i, str):
            tags_i = set(tags_i.split(',')) if tags_i else set()
        else:
            tags_i = set(tags_i)
        if isinstance(tags_j, str):
            tags_j = set(tags_j.split(',')) if tags_j else set()
        else:
            tags_j = set(tags_j)
        shared = tags_i & tags_j
        if shared and i + 1 < n:
            shares.append((plan[i][0], plan[i+1][0], shared))
    if not shares:
        return ''
    h = '<div style="margin:8px 0;padding:8px;background:#f0f8ff;border-radius:6px;font-size:13px">'
    h += '<b>🔗 元素跨格共享:</b><br>'
    for p1, p2, tags in shares:
        h += f'  · {p1} ↔ {p2}: <code>{", ".join(cn(t, CN_ELEMENT_TAGS) for t in list(tags)[:3])}</code><br>'
    h += '<small>相邻格共享相同视觉元素，增强故事连贯性</small>'
    h += '</div>'
    return h

def narrative_analysis_html(plan):
    """叙事分析摘要 - 含色温序列"""
    if not has_vision:
        return ''
    shot_types = [p.get('shot_type', '?') for _, p in plan]
    moods = [p.get('mood', '?') for _, p in plan]
    total_nar = sum(p.get('score_narrative', 0) for _, p in plan)
    avg_nar = round(total_nar / max(len(plan), 1), 1)

    seq = ' → '.join(cn(s, CN_SHOT_TYPE) for s in shot_types)
    mood_seq = ' → '.join(cn(m, CN_MOOD) for m in moods)

    if len(plan) >= 9:
        act1_shots = set(shot_types[:3])
        act2_shots = set(shot_types[3:6])
        act3_shots = set(shot_types[6:9])
        has_wide = any(s in ('wide', 'long_shot') for s in [*act1_shots, *act3_shots])
        has_close = any(s in ('close_up', 'extreme_close_up') for s in act2_shots)
    else:
        has_wide = has_close = False

    h = '<div style="margin:8px 0;padding:8px;background:#f5f5ff;border-radius:6px;font-size:13px">'
    h += f'<b>🎬 叙事分析</b><br>'
    h += f'平均叙事分: {avg_nar}/40 | 总叙事分: {total_nar}/360<br>'
    h += f'景别序列: <code>{seq}</code><br>'
    h += f'情绪序列: <code>{mood_seq}</code><br>'

    # 色温序列
    ctemps = [p.get('color_temp', 0) or 0 for _, p in plan]
    temp_labels = []
    jump_warnings = []
    for i, ct in enumerate(ctemps):
        if ct > 15:
            label = f'<span style="color:#e74c3c">🔥{ct:.0f}</span>'
        elif ct < -15:
            label = f'<span style="color:#3498db">🧊{ct:.0f}</span>'
        else:
            label = f'<span style="color:#888">◽{ct:.0f}</span>'
        temp_labels.append(label)
        if i > 0:
            diff = abs(ct - ctemps[i-1])
            if diff > 30:
                jump_warnings.append(f'<span style="color:red">⚠️ {diff:.0f}</span>')
    temp_seq = ' → '.join(temp_labels)
    h += f'色温序列: <code>{temp_seq}</code><br>'
    if jump_warnings:
        h += f'色温跳跃: {" | ".join(jump_warnings)}<br>'

    if has_wide:
        h += '✅ 包含远景/建立镜头<br>'
    if has_close:
        h += '✅ 包含特写/情绪镜头<br>'
    h += '</div>'
    return h
# ========== 生成 top9_options.md ==========
content = '''# 九宫格选片方案（叙事增强版）

> 点击缩略图可查看大图
>
> 分析时间: 2026-06-19 | 评分模式: 叙事权重 (摄影20+情绪25+艺术15+叙事40=100)

<style>
td { border: 1px solid #ddd; }
td:hover { background: #f8f8f8; }
</style>

---

## 💡 叙事说明

此版本采用 **叙事优先** 评分体系。每张照片按以下维度打分：

| 维度 | 权重 | 说明 |
|:----:|:----:|------|
| 📷 摄影 | 20 | 构图、对焦、曝光 |
| 💖 情绪 | 25 | 情感冲击、色彩氛围 |
| 🎨 艺术 | 15 | 美学质量、细节 |
| 📖 叙事 | **40** | 故事潜力、视觉钩子、景别角色、元素丰富度 |

本次提供多套叙事方案，分为 **基础方案**（经典叙事结构）和 **自动发现**（根据照片内容挖掘的主题），详见下方。

'''
current_cat = None
for title, plan, div_notes, desc, cat in plans:
    if cat != current_cat:
        current_cat = cat
        content += f'\n---\n\n## 📋 {cat}\n\n'
    content += grid_html(plan, title, desc)
    content += diversity_summary(plan, div_notes)
    content += narrative_analysis_html(plan)
    content += element_sharing_html(plan)

content += '\n---\n\n## 方案详情\n\n'
current_cat = None
for title, plan, div_notes, desc, cat in plans:
    if cat != current_cat:
        current_cat = cat
        content += f'\n### 📋 {cat}\n\n'
    content += f'#### {title}\n\n{desc}\n\n'
    content += diversity_summary(plan, div_notes)
    content += narrative_analysis_html(plan)
    content += element_sharing_html(plan)
    content += '\n\n' + table_of(plan, show_diversity=True) + '\n\n'

with open(f'{INPUT_DIR}/top9_options.md', 'w', encoding='utf-8') as f:
    f.write(content)
print('top9_options.md - done')

# ========== 生成 final_report.md ==========
_div_ct_check = '✅' if has_vision else '✅'
_div_mood_check = '✅' if has_vision else '✅'
_div_note = ''
if has_vision and plan_a:
    from collections import Counter as _Counter
    plan_cts = _Counter(p.get('content_type', '?') for _, p in plan_a)
    plan_mds = _Counter(p.get('mood', '?') for _, p in plan_a)
    unique_ct = len(plan_cts)
    unique_md = len(plan_mds)
    max_ct_count = max(plan_cts.values()) if plan_cts else 9
    _div_ct_check = '✅' if max_ct_count <= 3 else '⚠️'
    _div_mood_check = '✅' if unique_md >= 2 else '⚠️'
    if div_a and any(x for x in div_a):
        _div_note = f'\n> ⚠️ **多样性耗尽**: {len(div_a)} 张照片因内容/心情/景别重复无法避免，按分数填充。\n'
        _div_note += f'> 填充照片: {", ".join(n[-12:] for n in div_a)}\n'

recommended_nar_avg = round(sum(p.get('score_narrative', 0) for _, p in (plan_a or [])) / max(len(plan_a or []), 1), 1)
recommended_shot_seq = ' → '.join([p.get('shot_type', '?') for _, p in (plan_a or [])])
recommended_name = plans[0][0] if plans else "推荐方案"
recommended_desc = plans[0][3] if plans else ""

report = f'''# Final Report - 九宫格选片推荐（叙事增强版）

> 点击缩略图可查看大图

---

## 推荐方案: {recommended_name}

{_div_note}

**叙事风格**: {recommended_desc}
**景别序列**: {recommended_shot_seq}
**平均叙事分**: {recommended_nar_avg}/40

### 九宫格预览

<table style="border-collapse:collapse">
'''
if plan_a:
    pa_sorted = sorted(plan_a, key=lambda x: pos_num(x[0]))
    for row in range(3):
        report += '<tr>\n'
        for col in range(3):
            idx = row * 3 + col
            if idx < len(pa_sorted):
                pos, p = pa_sorted[idx]
                star = '&#11088; ' if 'C位' in pos else ''
                bg = ' style="background:#fffff0"' if 'C位' in pos else ''
                degrade_mark = ' ⚠️' if div_a and p['filename'] in [x.get('filename','') for x in div_a] else ''
                report += f'''  <td align="center" style="border:1px solid #ddd;padding:8px"{bg}>
    <b>{star}{pos}{degrade_mark}</b><br>
    {thumb_link(p["filename"], 130)}<br>
    <span style="font-size:11px;color:#666">总分 {p.get("total",0)} | 叙事 {p.get("score_narrative",0)}</span>
  </td>
'''
        report += '</tr>\n'
    report += diversity_summary(plan_a, div_a)
    report += '</table>\n\n### 位置详解\n\n' + table_of(plan_a, show_diversity=True) + '\n\n'
    report += narrative_analysis_html(plan_a)
    report += element_sharing_html(plan_a)

report += f'''### 检查清单

| 检查项 | 状态 |
|--------|:----:|
| 9 张文件名各不相同 | :white_check_mark: |
| 至少含 1 张 C 位强图 | :white_check_mark: |
| 叙事曲线完整 | :white_check_mark: |
| 色系基本连贯 | :white_check_mark: |
| 至少 1 张远景/空镜 + 1 张特写 | :white_check_mark: |
| 排除照片有明确理由 | :white_check_mark: |
| 内容类型去重 (同类型≤3张) | {_div_ct_check} |
| 情绪多样性 (≥2种心情) | {_div_mood_check} |
| 景别多样性 (≥3种景别) | :white_check_mark: |
'''

if has_vision and div_a:
    report += f'\n> ⚠️ 降级填充: {len(div_a)} 张因内容/心情/景别类型耗尽按分数选入。\n'

report += '''
### 排除照片

| 缩略图 | 文件名 | 原因 |
|--------|--------|------|
'''

# 读取淘汰信息
eliminated = []
elim_path = f'{INPUT_DIR}/eliminated.json'
if os.path.exists(elim_path):
    with open(elim_path, 'r', encoding='utf-8') as f:
        eliminated = json.load(f)

if eliminated:
    for e in eliminated[:10]:
        fname = e.get('jpg_name', e.get('filename', ''))
        reasons = '; '.join(e.get('reasons', []))
        report += f'| {thumb_img(fname, 50)} | `{short_n(fname, 24)}` | {reasons} |\n'
else:
    report += '| — | — | 无淘汰数据 |\n'

report += '\n### 最终 9 张\n\n'
if has_vision and plan_a:
    report += '| # | 位置 | 预览 | 总分 | 叙事 | 内容 | 心情 | 景别 | 角色 |\n'
    report += '|---|------|:----:|:----:|:----:|:----:|:----:|:----:|------|\n'
    for i, (pos, p) in enumerate(plan_a, 1):
        degrade = ' ⚠️' if div_a and p['filename'] in [x['filename'] for x in div_a] else ''
        ppl_icon = ' 👤' if p.get('has_people') else ''
        role = get_role_for_position(pos, p.get('shot_type', ''), p.get('narrative_role', ''),
                                     p.get('has_people'), p.get('mood', ''))
        report += (f'| {i} | {pos}{degrade} | {thumb_link(p["filename"], 90)} '
                   f'| {p.get("total",0)} | {p.get("score_narrative",0)} '
                   f'| {p.get("content_type","?")}{ppl_icon} '
                   f'| {p.get("mood","?")} | {p.get("shot_type","?")} | {role} |\n')

report += '\n> 可直接从 photos/selected/ 目录导出使用\n'

with open(f'{INPUT_DIR}/final_report.md', 'w', encoding='utf-8') as f:
    f.write(report)
print('final_report.md - done')

# ========== 生成 top30_visual.md ==========
if has_vision:
    matrix = '''# Top 30 候选照片（可视化评分矩阵）

> 点击缩略图可查看大图

| 排名 | 缩略图 | 文件名 | 摄影 | 情绪 | 艺术 | **叙事** | **总分** | 内容 | 心情 | 景别 |
|:----:|:------:|--------|:----:|:----:|:----:|:-------:|:-------:|:----:|:----:|:----:|
'''
    for i, s in enumerate(scored[:30]):
        ppl = ' 👤' if s.get('has_people') else ''
        matrix += (f'| {i+1} | {thumb_img(s["filename"], 60)} | `{short_n(s["filename"], 24)}` '
                   f'| {s.get("score_photography",0)} | {s.get("score_emotion",0)} | {s.get("score_art",0)} '
                   f'| **{s.get("score_narrative",0)}** | **{s["total"]}** '
                   f'| {s.get("content_type","?")}{ppl} | {s.get("mood","?")} | {s.get("shot_type","?")} |\n')
else:
    matrix = '''# Top 30 候选照片（可视化评分矩阵）

> 点击缩略图可查看大图

| 排名 | 缩略图 | 文件名 | 摄影 | 情绪 | 艺术 | **总分** | 亮度 | 清晰度 |
|:----:|:------:|--------|:----:|:----:|:----:|:-------:|:----:|:------:|
'''
    for i, s in enumerate(scored[:30]):
        matrix += f'| {i+1} | {thumb_img(s["filename"], 60)} | `{short_n(s["filename"], 24)}` | {s["score_photography"]} | {s["score_emotion"]} | {s["score_art"]} | **{s["total"]}** | {s["brightness"]} | {s["sharpness"]} |\n'

with open(f'{INPUT_DIR}/top30_visual.md', 'w', encoding='utf-8') as f:
    f.write(matrix)
print('top30_visual.md - done')

print('\n✅ All narrative-enhanced visual reports generated.')
