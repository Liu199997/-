[app]
# 应用身份
title = 盘纸余量计算
package.name = paperrollcalc
package.domain = com.paperroll

source.dir = .
source.include_exts = py,png,jpg,jpeg,ttf,ttc,json
source.include_patterns = fonts/*.ttf
source.exclude_dirs = bin,.git,__pycache__,tests

version = 1.0.0

# 依赖（Kivy 内置，无需 Qt）
requirements = python3,kivy==2.3.1

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
android.api = 33
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.presplash_color = #F4F6FB

# 中文界面：项目自带 fonts/simhei.ttf，已通过 include_patterns 打入
# 打包命令：buildozer -v android debug