@echo off
chcp 65001 >nul
cd /d %~dp0

echo [1/3] 检查并安装依赖...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
python -m pip install pyinstaller --quiet --disable-pip-version-check

echo [2/3] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] 开始打包（onedir 目录模式，无 UPX，启动快）...
python -m PyInstaller --noconfirm PaperRollCalculator.spec
if errorlevel 1 (
    echo 打包失败，请检查上方输出。
    pause
    exit /b 1
)

echo.
echo 打包完成：
echo   dist\PaperRollCalculator\PaperRollCalculator.exe
echo 分发时请整体复制 dist\PaperRollCalculator 文件夹（不要只拷 exe）。
pause
