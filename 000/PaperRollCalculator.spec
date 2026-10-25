# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置（目录模式 onedir）

为“打开快、不挑电脑”做的处理：
1. onedir 目录模式：启动时无需把依赖解压到临时目录，冷启动远快于 onefile；
2. upx=False：避免启动解压耗时，也避免杀毒软件误报/整包扫描拖慢；
3. optimize=1：剔除断言与文档字符串，减小字节码体积；
4. 按真实导入表精简二进制：只保留 QtCore/QtGui/QtWidgets 及其实际依赖，
   剔除 Qt5Quick/Qml/Network/Pdf/Svg/VirtualKeyboard/WebGL、opengl32sw 等
   用不到的大体积组件（已用 PE 导入表确认它们不被 Widgets 依赖）。
"""

EXCLUDES = [
    # 未使用的 PyQt5 模块（本项目只用 QtCore / QtGui / QtWidgets）
    'PyQt5.QtNetwork',
    'PyQt5.QtQml',
    'PyQt5.QtQuick',
    'PyQt5.QtQuickWidgets',
    'PyQt5.QtMultimedia',
    'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtWebChannel',
    'PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineCore',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtSql',
    'PyQt5.QtTest',
    'PyQt5.QtSvg',
    'PyQt5.QtOpenGL',
    'PyQt5.QtPrintSupport',
    'PyQt5.QtXml',
    'PyQt5.QtDBus',
    'PyQt5.QtBluetooth',
    'PyQt5.QtNfc',
    'PyQt5.QtPositioning',
    'PyQt5.QtLocation',
    'PyQt5.QtSerialPort',
    'PyQt5.QtDesigner',
    'PyQt5.QtHelp',
    'PyQt5.QtUiTools',
    # 未使用的标准库
    'tkinter',
    'unittest',
    'pydoc',
    'doctest',
    'pdb',
]

a = Analysis(
    ['paper_roll_calculator.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

# ---- 精简一：丢弃 Qt 翻译文件（界面文案为程序内置中文，无需 Qt 翻译包） ----
a.datas = [
    d for d in a.datas
    if '/translations/' not in d[0].replace('\\', '/')
]

# ---- 精简二：丢弃用不到的 Qt 运行库（依据 PE 导入表确认无引用） ----
UNUSED_DLLS = {
    'opengl32sw.dll',            # 软件 OpenGL 兜底，2D 绘制用不到
    'qt5network_conda.dll',
    'qt5pdf_conda.dll',
    'qt5quick_conda.dll',
    'qt5qml_conda.dll',
    'qt5qmlmodels_conda.dll',
    'qt5svg_conda.dll',
    'qt5virtualkeyboard_conda.dll',
    'qt5websockets_conda.dll',
    'qt5dbus_conda.dll',
    'libglesv2.dll',
    'libegl.dll',
    'libjpeg.dll',
}

# ---- 精简三：丢弃用不到的 Qt 插件目录（保留 platforms/styles 最小集） ----
UNUSED_PLUGIN_PARTS = (
    '/plugins/imageformats/',
    '/plugins/iconengines/',
    '/plugins/platforminputcontexts/',
    '/plugins/generic/',
    '/plugins/platformthemes/',
)
DROP_PLATFORM_PLUGINS = {'qwebgl.dll', 'qdirect2d.dll'}


def keep_binary(entry) -> bool:
    path = entry[0].replace('\\', '/').lower()
    if path.rsplit('/', 1)[-1] in UNUSED_DLLS:
        return False
    if any(part in path for part in UNUSED_PLUGIN_PARTS):
        return False
    if '/plugins/platforms/' in path and path.rsplit('/', 1)[-1] in DROP_PLATFORM_PLUGINS:
        return False
    return True


a.binaries = [b for b in a.binaries if keep_binary(b)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PaperRollCalculator',
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
    icon=['app.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='PaperRollCalculator',
)
