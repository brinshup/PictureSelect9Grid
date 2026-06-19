@echo off
chcp 65001 > nul
echo ============================================
echo  九宫格选片 — 视觉增强模式（推荐）
echo  需先配置 .env 中的 QWEN_API_KEY
echo ============================================
echo.

cd /d %~dp0

echo [1/5] 预处理...
python scripts\preprocess.py
if %errorlevel% neq 0 ( echo ❌ 预处理失败 & pause & exit /b %errorlevel% )

echo.
echo [2/5] Qwen3 视觉评分...
python scripts\vision_score.py
if %errorlevel% neq 0 ( echo ❌ 视觉评分失败 & pause & exit /b %errorlevel% )

echo.
echo [3/5] 叙事评分与蓝图匹配...
python scripts\score_and_group.py --mode hybrid
if %errorlevel% neq 0 ( echo ❌ 评分失败 & pause & exit /b %errorlevel% )

echo.
echo [4/5] 生成可视化报告...
python scripts\generate_visual_report.py --mode hybrid

echo.
echo [5/5] 调色后处理（可选，跳过不影响）...
python scripts\color_grade.py

echo.
echo ✅ 全部完成！
echo 📂 结果: output/<最新版本>/hybrid/
echo 📄 报告: top9_options.md / final_report.md
pause
