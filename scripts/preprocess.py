"""
九宫格选片 - 预处理脚本
功能：缩小图片、抽 Exif、生成缩略图网格、输出 metadata.json
适配 Windows 11，支持 HEIC/JPG/PNG，无 ImageMagick 依赖
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# Windows GBK 编码兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from tqdm import tqdm
from PIL import Image, ImageOps, ExifTags

# ── HEIC 支持 ──────────────────────────────────────────────
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False
    print("⚠️  pillow-heif 未安装，HEIC 文件将被跳过")
    print("   安装: pip install pillow-heif")

PROJECT_DIR = Path(__file__).resolve().parent.parent

# ── 常量 ────────────────────────────────────────────────────
SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
if HEIC_SUPPORT:
    SUPPORTED_EXT.add('.heic')
    SUPPORTED_EXT.add('.heif')

DEFAULT_INPUT = "image"
DEFAULT_OUTPUT = "photos/resized"
DEFAULT_THUMBNAILS = "photos/thumbnails"
MAX_SIZE = 2560          # 长边最大像素
QUALITY = 85             # JPEG 压缩质量
CONTACT_SIZE = 480       # 缩略图网格单图尺寸
CONTACT_COLS = 5         # 每行几张


def extract_exif(img, filepath):
    """从图片/文件提取 Exif 元数据"""
    meta = {
        "filename": Path(filepath).name,
        "filepath": str(filepath),
        "filesize_bytes": os.path.getsize(filepath),
        "width": img.width,
        "height": img.height,
        "aspect_ratio": round(img.width / img.height, 4) if img.height else 0,
    }

    # 从文件修改时间拿时间戳
    mtime = os.path.getmtime(filepath)
    meta["file_modify_time"] = datetime.fromtimestamp(mtime).isoformat()

    # Exif 信息 (Pillow 10+ 使用 getexif())
    try:
        exif_data = img.getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))

                if tag_name == "DateTimeOriginal":
                    meta["datetime_original"] = str(value)
                elif tag_name == "Make":
                    meta["camera_make"] = str(value).strip()
                elif tag_name == "Model":
                    meta["camera_model"] = str(value).strip()
                elif tag_name == "LensModel":
                    meta["lens_model"] = str(value).strip()
                elif tag_name == "FocalLength":
                    try:
                        meta["focal_length"] = f"{float(value):.1f} mm"
                    except (ValueError, TypeError):
                        pass
                elif tag_name == "FNumber":
                    try:
                        meta["aperture"] = f"f/{float(value):.1f}"
                    except (ValueError, TypeError):
                        pass
                elif tag_name == "ISOSpeedRatings":
                    try:
                        meta["iso"] = int(value)
                    except (ValueError, TypeError):
                        pass
                elif tag_name == "ExposureTime":
                    try:
                        v = float(value)
                        meta["exposure"] = f"1/{int(1/v)}" if v < 1 else f"{v:.1f}s"
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                elif tag_name == "Orientation":
                    meta["orientation"] = int(value)
    except Exception:
        pass

    return meta


def compute_histogram_features(img):
    """计算直方图特征：brightness, contrast, sharpness, saturation, color_temp, underexposed_pct"""
    from PIL import ImageFilter

    img_rgb = img.convert("RGB")
    arr = np.array(img_rgb).astype(float)

    # RGB 通道分离
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    # 亮度 (加权灰度)
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    # 清晰度：拉普拉斯方差（8 邻域核）
    lap = img_rgb.convert("L").filter(
        ImageFilter.Kernel((3, 3), [-1, -1, -1, -1, 8, -1, -1, -1, -1], scale=1)
    )
    sharpness = float(np.array(lap).var())

    # 饱和度：HSV 空间的 S 通道均值
    hsv = np.array(img_rgb.convert("HSV")).astype(float)
    saturation = float(np.mean(hsv[:, :, 1]))

    # 色温代理：R - B 均值差
    color_temp = float(np.mean(r) - np.mean(b))

    # 欠曝比例：灰度 < 15 的像素占比
    underexposed_pct = float(np.mean(gray < 15) * 100)

    return {
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "sharpness": round(sharpness, 2),
        "saturation": round(saturation, 2),
        "color_temp": round(color_temp, 2),
        "underexposed_pct": round(underexposed_pct, 2),
    }


def resize_image(img, max_size=MAX_SIZE):
    """等比例缩小图片，长边不超过 max_size 像素"""
    w, h = img.size
    if max(w, h) <= max_size:
        return img
    if w >= h:
        new_w = max_size
        new_h = int(h * max_size / w)
    else:
        new_h = max_size
        new_w = int(w * max_size / h)
    return img.resize((new_w, new_h), Image.LANCZOS)


def make_contact_sheet(thumb_dir, output_path, cols=CONTACT_COLS, thumb_size=CONTACT_SIZE):
    """用 Pillow 生成缩略图网格 (contact sheet)"""
    images = sorted(Path(thumb_dir).glob("*.*"))
    image_files = [p for p in images if p.suffix.lower() in {'.jpg', '.jpeg', '.png'}]

    if not image_files:
        print("⚠️  没有缩略图可拼网格")
        return

    n = len(image_files)
    rows = (n + cols - 1) // cols

    sheet_w = cols * thumb_size
    sheet_h = rows * thumb_size

    sheet = Image.new('RGB', (sheet_w, sheet_h), (240, 240, 240))

    for idx, img_path in enumerate(tqdm(image_files, desc="拼 contact sheet")):
        try:
            thumb = Image.open(img_path).convert('RGB')
            thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)

            x = (idx % cols) * thumb_size + (thumb_size - thumb.width) // 2
            y = (idx // cols) * thumb_size + (thumb_size - thumb.height) // 2
            sheet.paste(thumb, (x, y))
        except Exception as e:
            print(f"  ⚠️  跳过 {img_path.name}: {e}")

    sheet.save(output_path, "JPEG", quality=85)
    print(f"✅ Contact sheet: {output_path} ({n} 张, {rows}×{cols} 网格)")


def main():
    parser = argparse.ArgumentParser(description="九宫格选片 - 图片预处理")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="原始照片目录")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="缩小后输出目录")
    parser.add_argument("--thumbnails", default=DEFAULT_THUMBNAILS, help="缩略图输出目录")
    parser.add_argument("--max-size", type=int, default=MAX_SIZE, help="长边最大像素")
    parser.add_argument("--quality", type=int, default=QUALITY, help="JPEG 压缩质量")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    thumb_dir = Path(args.thumbnails)

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    # 扫描输入 (Windows 下 glob 不区分大小写，无需重复扫)
    all_files_set = set()
    for ext in SUPPORTED_EXT:
        for f in input_dir.glob(f"*{ext}"):
            all_files_set.add(f)
        for f in input_dir.glob(f"*{ext.upper()}"):
            all_files_set.add(f)
    all_files = sorted(all_files_set)

    if not all_files:
        print(f"❌ 在 {input_dir} 中没有找到支持的图片 ({', '.join(SUPPORTED_EXT)})")
        print("   支持格式: JPG/JPEG/PNG/TIF/TIFF" + ("/HEIC" if HEIC_SUPPORT else ""))
        sys.exit(1)

    print(f"📷 找到 {len(all_files)} 张图片，开始处理...")

    metadata_list = []

    # 并行处理图片（I/O 密集型，线程池合适）
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def process_one(filepath):
        """处理单张图片，返回 metadata dict，失败返回 None"""
        try:
            img = Image.open(filepath)
            img = ImageOps.exif_transpose(img) or img

            # 提取 Exif
            meta = extract_exif(img, filepath)

            # 直方图特征（在原图上计算，缩小前更准确）
            hist_features = compute_histogram_features(img)
            meta.update(hist_features)

            # 缩小
            resized = resize_image(img, args.max_size)
            if resized.mode == 'RGBA':
                resized = resized.convert('RGB')

            # 保存缩小版
            out_name = Path(filepath).stem + ".jpg"
            out_path = output_dir / out_name
            resized.save(out_path, "JPEG", quality=args.quality)
            meta["resized_path"] = str(out_path)
            meta["resized_size"] = resized.size

            # 生成缩略图
            thumb = resized.copy()
            thumb.thumbnail((CONTACT_SIZE, CONTACT_SIZE), Image.LANCZOS)
            thumb_path = thumb_dir / out_name
            thumb.save(thumb_path, "JPEG", quality=75)
            meta["thumbnail_path"] = str(thumb_path)

            return meta
        except Exception as e:
            print(f"\n❌ 处理失败 {filepath.name}: {e}")
            return None

    workers = min(6, len(all_files) or 1)
    metadata_list = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_one, fp): fp for fp in sorted(all_files)}
        with tqdm(total=len(all_files), desc="处理图片") as pbar:
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    metadata_list.append(result)
                pbar.update(1)
    metadata_list.sort(key=lambda m: m.get("filename", ""))

    # 保存 metadata.json
    meta_path = output_dir / "metadata.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_list, f, ensure_ascii=False, indent=2)
    print(f"✅ metadata.json: {meta_path} ({len(metadata_list)} 条)")

    # 保存 analysis.json（供 score_and_group.py / vision_score.py 使用）
    analysis_path = PROJECT_DIR / "output" / "analysis.json"
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    with open(analysis_path, 'w', encoding='utf-8') as f:
        json.dump({"photos": metadata_list}, f, ensure_ascii=False, indent=2)
    print(f"✅ analysis.json: {analysis_path} ({len(metadata_list)} 条)")

    # 生成 contact sheet
    contact_path = thumb_dir / "contact_sheet.jpg"
    make_contact_sheet(thumb_dir, contact_path)

    # 统计
    ext_counts = {}
    for m in metadata_list:
        ext = Path(m["filename"]).suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    print(f"\n📊 处理完成: {len(metadata_list)} 张成功, {len(all_files) - len(metadata_list)} 张失败")
    print(f"   格式分布: {ext_counts}")
    print(f"   缩小图: {output_dir}")
    print(f"   缩略图: {thumb_dir}")
    print(f"   Contact sheet: {contact_path}")


if __name__ == '__main__':
    main()
