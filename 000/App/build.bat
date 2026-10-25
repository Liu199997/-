@echo off
chcp 65001 >nul
cd /d %~dp0

echo [1/2] 清理旧打包产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] 开始打包（onedir，启动快）...
rem 通过 build_exe.py 调用 PyInstaller（规避部分环境下隔离子进程崩溃问题）
python build_exe.py --clean PaperCalc.spec
if errorlevel 1 (
    echo 打包失败，请检查上方日志。
    pause
    exit /b 1
)

echo.
echo 打包完成：dist\PaperCalc\PaperCalc.exe
echo 分发时请整体复制 dist\PaperCalc 文件夹（不能只复制 exe 文件）。
pause
