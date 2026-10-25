# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置（Kivy 桌面版，目录模式 onedir）

启动快、不挑电脑的要点：
1. onedir：无需每次启动解压依赖（onefile 冷启动极慢）；
2. upx=False：避免启动解压和杀毒软件误报；
3. 目录内自带中文字体、图标，任何机器双击即可运行，无需安装 Python。
"""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# Kivy 本体（含 glsl/字体/图片等数据文件与全部子模块）
for pkg in ("kivy", "kivy_deps.sdl2", "kivy_deps.glew", "kivy_deps.angle"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue  # 非 Windows 平台可能缺少部分 kivy_deps
    datas += d
    binaries += b
    hiddenimports += h

# 运行时资源：窗口图标 + 自带中文字体
datas += [
    ("icon.png", "."),
    ("fonts/simhei.ttf", "fonts"),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
        "pdb",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "shiboken6",
        "setuptools",
        "pkg_resources",
        "_distutils_hack",
        "numpy",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PaperCalc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["icon.ico"],
    manifest="app.manifest",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PaperCalc",
)
