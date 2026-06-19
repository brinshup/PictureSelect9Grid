@echo off
chcp 65001 >nul
title 清理中间文件

:: 静默模式：/quiet 或 /q 跳过确认
if /i "%1"=="/quiet" goto :clean
if /i "%1"=="/q" goto :clean

echo.
echo ═══════════════════════════════════════
echo   清理生成文件 — pictureSelect-4.0
echo ═══════════════════════════════════════
echo.
set /p confirm="确定要删除所有中间文件和输出报告？(y/N): "
if /i not "%confirm%"=="y" (
    echo.
    echo ❌ 已取消
    pause
    exit /b
)

:clean
echo.
echo 正在清理...

:: 1. 输出报告（所有版本）
if exist output\ (
    rmdir /s /q output
    echo   [OK] output\ — 评分结果 + 报告
)

:: 2. 缩小图
if exist photos\resized\ (
    rmdir /s /q photos\resized
    echo   [OK] photos\resized\ — 缩小图片
)

:: 3. 缩略图
if exist photos\thumbnails\ (
    rmdir /s /q photos\thumbnails
    echo   [OK] photos\thumbnails\ — 缩略图
)

:: 4. PDF 报告
if exist pdfReport\ (
    rmdir /s /q pdfReport
    echo   [OK] pdfReport\ — PDF 导出
)

:: 5. Qwen3Process 老数据
if exist Qwen3Process\ (
    rmdir /s /q Qwen3Process
    echo   [OK] Qwen3Process\
)

:: 6. hist_output 老数据
if exist hist_output\ (
    rmdir /s /q hist_output
    echo   [OK] hist_output\
)

echo.
echo ═══════════════════════════════════════
echo   [OK] 清理完成！
echo.
echo   保留:
echo     image\          — 原始照片
echo     scripts\        — 源代码
echo     .env            — API 密钥
echo     .git\           — 版本控制
echo ═══════════════════════════════════════
echo.
if not "%1"=="/quiet" if not "%1"=="/q" pause
