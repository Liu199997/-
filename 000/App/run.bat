@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv (
    echo [1/2] 首次运行，正在安装依赖...
    python -m pip install -r requirements.txt --quiet --disable-pip-version-check
)
echo [2/2] 启动盘纸余量计算（Kivy 竖屏版）...
python main.py
if errorlevel 1 pause