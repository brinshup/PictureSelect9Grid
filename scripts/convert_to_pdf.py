"""
将可视化报告 (.md) 转换为 PDF 文档。
方案：Markdown → HTML（base64 内嵌图片）→ Edge 无头模式打印 PDF
"""
import os, re, base64, subprocess, tempfile, shutil
from pathlib import Path
import markdown

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"
PDF_DIR = PROJECT_DIR / "pdfReport"
THUMB_DIR = PROJECT_DIR / "photos/thumbnails"
RESIZED_DIR = PROJECT_DIR / "photos/resized"

PDF_DIR.mkdir(parents=True, exist_ok=True)

# Edge 路径（可通过 EDGE_PATH 环境变量覆盖）
_EDGE_DEFAULT = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)
EDGE_PATH = os.environ.get("EDGE_PATH") or _EDGE_DEFAULT

REPORTS = [
    ("top9_options.md",       "九宫格选片方案_可视化版"),
    ("final_report.md",       "Final_Report_九宫格选片推荐"),
    ("top30_visual.md",       "Top30_候选照片评分矩阵"),
    ("USAGE_GUIDE.md",        "九宫格选片工具_使用教程"),
]


def embed_images_base64(html_text, md_path):
    """将 <img src=相对路径> 替换为 base64 内嵌"""
    def replacer(match):
        attr = match.group(0)
        src_match = re.search(r'src="([^"]+)"', attr)
        if not src_match:
            return attr
        src = src_match.group(1)
        img_path = (md_path.parent / src).resolve()
        if img_path.exists():
            try:
                data = img_path.read_bytes()
                ext = img_path.suffix.lower().lstrip('.')
                mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else 'image/png'
                b64 = base64.b64encode(data).decode()
                return attr.replace(f'src="{src}"', f'src="data:{mime};base64,{b64}"')
            except Exception as e:
                print(f"  ! 嵌入失败 {img_path.name}: {e}")
        else:
            print(f"  ! 图片不存在: {img_path}")
        return attr

    return re.sub(r'<img[^>]+src="[^"]+"[^>]*>', replacer, html_text)


def convert_md_to_pdf(md_path, pdf_name=None):
    md_path = Path(md_path)
    if pdf_name is None:
        pdf_name = md_path.stem

    print(f"\n{md_path.name} -> {pdf_name}.pdf")

    # 读取 markdown
    md_text = md_path.read_text(encoding='utf-8')

    # 转 HTML
    html_body = markdown.markdown(
        md_text,
        extensions=['extra', 'tables', 'sane_lists'],
        output_format='html5'
    )

    # 嵌入 base64 图片
    html_body = embed_images_base64(html_body, md_path)

    # 包装为完整 HTML
    html_full = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 1.8cm 1.5cm; }}
  body {{ font-family: 'Microsoft YaHei', 'SimHei', 'PingFang SC', sans-serif; font-size: 11pt; line-height: 1.6; color: #222; }}
  h1 {{ font-size: 18pt; color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 6px; }}
  h2 {{ font-size: 15pt; color: #16213e; margin-top: 20px; }}
  h3 {{ font-size: 13pt; color: #0f3460; margin-top: 16px; }}
  table {{ border-collapse: collapse; margin: 10px 0; width: 100%; }}
  td, th {{ border: 1px solid #bbb; padding: 5px 6px; text-align: center; vertical-align: middle; }}
  th {{ background: #f0f0f0; }}
  img {{ border-radius: 4px; max-width: 100%; }}
  a {{ color: #0066cc; text-decoration: none; }}
  code {{ background: #f4f4f4; padding: 1px 4px; border-radius: 3px; font-size: 9pt; }}
  pre {{ background: #f8f8f8; border: 1px solid #ddd; border-radius: 4px; padding: 8px; font-size: 9pt; overflow-x: auto; }}
  blockquote {{ border-left: 3px solid #e94560; padding-left: 10px; margin: 10px 0; color: #555; }}
</style>
</head>
<body>
{html_body}
</body>
</html>'''

    # 写入临时 HTML 文件
    tmp_html = PDF_DIR / f"_tmp_{pdf_name}.html"
    tmp_html.write_text(html_full, encoding='utf-8')

    # 调用 Edge 无头模式打印 PDF
    pdf_path = PDF_DIR / f"{pdf_name}.pdf"
    file_url = tmp_html.resolve().as_uri()

    cmd = [
        EDGE_PATH,
        '--headless',
        '--disable-gpu',
        '--no-margins',
        f'--print-to-pdf={pdf_path.resolve()}',
        file_url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        # Edge 即使成功也会输出一条日志
        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            size_kb = pdf_path.stat().st_size / 1024
            print(f"  OK: {pdf_path.name} ({size_kb:.0f} KB)")
            tmp_html.unlink(missing_ok=True)
            return True
        else:
            print(f"  失败 (输出为空或太小)")
            if result.stderr:
                print(f"  stderr: {result.stderr[:200]}")
            tmp_html.unlink(missing_ok=True)
            return False
    except subprocess.TimeoutExpired:
        print(f"  超时 (60s)")
        tmp_html.unlink(missing_ok=True)
        return False
    except FileNotFoundError:
        print(f"  未找到 Edge: {EDGE_PATH}")
        tmp_html.unlink(missing_ok=True)
        return False


# ========== 命令行入口 ==========
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Markdown → PDF (Edge headless)")
    ap.add_argument("inputs", nargs="*", help="要转换的 .md 文件路径（可多个）")
    ap.add_argument("--output-dir", "-o", default=None,
                    help="PDF 输出目录 (默认: 与 .md 同目录)")
    args = ap.parse_args()

    if args.inputs:
        # 指定文件模式
        success = 0
        for md_file in args.inputs:
            md_path = Path(md_file)
            if not md_path.exists():
                print(f"  跳过: {md_file} (不存在)")
                continue
            # 输出到指定目录或同目录
            out_dir = Path(args.output_dir) if args.output_dir else md_path.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            # 临时改 PDF_DIR（module-level reassign）
            PDF_DIR = out_dir
            pdf_name = md_path.stem
            if convert_md_to_pdf(md_path, pdf_name):
                success += 1
        print(f"\n  完成: {success}/{len(args.inputs)} 个 PDF")
    else:
        # 默认模式：批量转换 output/ 下已知报告
        print("=" * 50)
        print("  报告转 PDF （Edge 无头模式）")
        print("=" * 50)
        success = 0
        for md_name, pdf_name in REPORTS:
            md_path = OUTPUT_DIR / md_name
            if md_path.exists():
                if convert_md_to_pdf(md_path, pdf_name):
                    success += 1
            else:
                print(f"\n 跳过: {md_name} (不存在)")
        print(f"\n{'=' * 50}")
        print(f"  完成: {success}/{len(REPORTS)} 个 PDF -> pdfReport/")
        if success < len(REPORTS):
            print("  (部分文件可能因图片过多过大跳过)")
        print(f"{'=' * 50}")
