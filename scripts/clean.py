#!/usr/bin/env python3
"""
清理中间文件和输出报告（跨平台）。
用法: python scripts/clean.py          # 交互确认
       python scripts/clean.py --force  # 静默清理
"""
import os, sys, shutil
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent

DIRS_TO_CLEAN = [
    ("output",            "评分结果 + 报告"),
    ("photos/resized",    "缩小图片"),
    ("photos/thumbnails", "缩略图"),
    ("pdfReport",         "PDF 导出"),
    ("Qwen3Process",      "旧版缓存"),
    ("hist_output",       "旧版直方图输出"),
]

def main():
    force = "--force" in sys.argv or "-f" in sys.argv

    print()
    print("=" * 50)
    print("  清理生成文件 — pictureSelect-4.0")
    print("=" * 50)
    print()

    if not force:
        resp = input("确定要删除所有中间文件和输出报告？(y/N): ").strip().lower()
        if resp != "y":
            print("❌ 已取消\n")
            return

    cleaned = 0
    for rel_path, label in DIRS_TO_CLEAN:
        target = PROJECT_DIR / rel_path
        if target.is_dir():
            shutil.rmtree(target)
            print(f"  [OK] {rel_path}/  — {label}")
            cleaned += 1

    print()
    print("=" * 50)
    if cleaned:
        print(f"  [OK] 清理完成！删除了 {cleaned} 个目录")
    else:
        print("  没有找到需要清理的目录")
    print()
    print("  保留:")
    print("    image/        — 原始照片")
    print("    scripts/      — 源代码")
    print("    .env          — API 密钥")
    print("    .git/         — 版本控制")
    print("=" * 50)
    print()

if __name__ == "__main__":
    main()
