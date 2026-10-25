#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包入口：调用 PyInstaller 构建 dist/PaperCalc。

本机环境（Anaconda + PyInstaller 6.22）存在两个缺陷，此处做构建期规避，
不影响打包产物与程序逻辑：
1. PyInstaller 的 conda 元数据解析在部分 conda-meta 上会触发 0xC0000005
   崩溃 —— 打包本项目不需要 conda 支持，直接关闭；
2. PyInstaller 的隔离子进程在本机随机崩溃 —— 改为进程内执行同样的调用。
"""

import sys

import PyInstaller.compat as compat

# 关闭 conda 支持，避免解析 conda-meta 时崩溃（本应用不依赖 conda 收集逻辑）
compat.is_pure_conda = False
compat.is_conda = False

import PyInstaller.isolated as _iso  # noqa: E402
import PyInstaller.isolated._parent as _parent  # noqa: E402


def _inprocess(function, *args, **kwargs):
    return function(*args, **kwargs)


class _InprocPython:
    """替代 isolated.Python：同一进程内执行，不派生子进程。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def call(self, function, *args, **kwargs):
        return function(*args, **kwargs)


_parent.call = _inprocess
_iso.call = _inprocess
_iso.Python = _InprocPython

from PyInstaller.__main__ import run  # noqa: E402

args = ["--noconfirm"]
args += sys.argv[1:] or ["PaperCalc.spec"]
raise SystemExit(run(args))
