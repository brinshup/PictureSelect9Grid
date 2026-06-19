@echo off
chcp 65001 > nul
echo ============================================
echo  九宫格选片 — 全流程（直方图 + 视觉增强）
echo  同时跑两种模式方便对比
echo ============================================
echo.

cd /d %~dp0

echo ========== [1/2] 纯直方图模式 ==========
echo.

python scripts\preprocess.py
if %errorlevel% neq 0 ( echo ❌ 预处理失败 & pause & exit /b %errorlevel% )

python scripts\score_and_group.py --mode histogram
python scripts\generate_visual_report.py --mode histogram

echo.
echo ✅ 直方图模式完成

echo.
echo ========== [2/2] 视觉增强模式 ==========
echo.

python scripts\vision_score.py
python scripts\score_and_group.py --mode hybrid
python scripts\generate_visual_report.py --mode hybrid

echo.
echo ============================================
echo  ✅ 全流程完成！
echo  📂 output/<版本>/histogram/   — 纯直方图结果
echo  📂 output/<版本>/hybrid/      — 视觉增强结果
echo ============================================
pause
