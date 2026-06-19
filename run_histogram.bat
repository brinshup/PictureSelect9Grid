@echo off
chcp 65001 > nul
echo ============================================
echo  九宫格选片 — 纯直方图模式（免费，秒级）
echo ============================================
echo.

cd /d %~dp0

echo [1/3] 预处理...
python scripts\preprocess.py
if %errorlevel% neq 0 ( echo ❌ 预处理失败 & pause & exit /b %errorlevel% )

echo.
echo [2/3] 评分与分组...
python scripts\score_and_group.py --mode histogram
if %errorlevel% neq 0 ( echo ❌ 评分失败 & pause & exit /b %errorlevel% )

echo.
echo [3/3] 生成可视化报告...
python scripts\generate_visual_report.py --mode histogram

echo.
echo ✅ 全部完成！结果在 output/ 目录下
pause
