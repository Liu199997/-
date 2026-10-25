#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘纸余量计算系统 · Kivy 移动版（竖屏优化）

卷烟纸：内半径 r、外半径 R、盘纸长度 L、消耗后半径差 Δr → 剩余长度 (m)
水松纸：内半径 r、外半径 R、盘纸重量 W、消耗后半径差 Δr → 剩余重量 (kg)

- 两个计算界面以顶部“卷烟纸 / 水松纸”两个选项切换，不再上下堆叠；
- 界面无大标题，直接进入参数输入；
- 输入参数（内外半径、盘纸长度、水松纸重量）保存为下次运行的默认值；
  计算结果（剩余长度 / 剩余重量）不保存，仅显示；
- 盘纸剩余纸层为半透明灰，水松纸为半透明橙，虚线为原始外半径。

计算模型（螺旋卷绕等效面积法，半径为 r、R，纸厚 w，纸长 L）：
    pi (R^2 - r^2) = L * w
    消耗后剩余外半径 R' = r + Δr：
        剩余长度 L' = pi (R'^2 - r^2) / w
        剩余重量 W' = W * (R'^2 - r^2) / (R^2 - r^2)
"""

from __future__ import annotations

import configparser
import json
import math
import os
import site
import sys
import uuid
from datetime import datetime

# PyInstaller 打包后 site.USER_BASE 可能为 None，kivy_deps 会在导入时
# os.path.join(None, ...) 直接报错，这里先补齐（源码运行时无影响）。
if getattr(site, "USER_BASE", None) is None:
    try:
        site.USER_BASE = site.getuserbase()
    except Exception:
        site.USER_BASE = os.path.expanduser("~")

# 先摘出自定义参数，避免 Kivy 启动时把它们当成非法命令行选项
SMOKE_TEST = "--smoke" in sys.argv
sys.argv = [arg for arg in sys.argv if arg != "--smoke"]

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.graphics import Color, Ellipse, Line
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

Window.softinput_mode = "below_target"
Window.clearcolor = (0.957, 0.965, 0.984, 1)


# ---------------------------------------------------------------------------
# 计算内核（半径制，单位 mm / m / kg，与桌面版完全一致）
# ---------------------------------------------------------------------------

def wall_from_length(r_in: float, r_out: float, total_length_m: float) -> float:
    """由内外半径与盘纸总长反推单层纸厚 (mm)。"""
    if r_out <= r_in:
        raise ValueError("外半径必须大于内半径")
    if total_length_m <= 0:
        raise ValueError("盘纸长度必须大于 0")
    return math.pi * (r_out ** 2 - r_in ** 2) / (total_length_m * 1000.0)


def length_from_radii(r_in: float, r_out: float, wall_mm: float) -> float:
    """已知内外半径与单层纸厚，求纸长 (m)。"""
    if r_out <= r_in:
        raise ValueError("外半径必须大于内半径")
    if wall_mm <= 0:
        raise ValueError("单层纸厚必须大于 0")
    return math.pi * (r_out ** 2 - r_in ** 2) / wall_mm / 1000.0


def checked_delta(r_in: float, r_out: float, delta_r_mm: float) -> float:
    """校验消耗后半径差并返回限幅后的值。"""
    if r_out <= r_in:
        raise ValueError("外半径必须大于内半径")
    full = r_out - r_in
    if delta_r_mm < -1e-9:
        raise ValueError("消耗后半径差不能为负数")
    if delta_r_mm > full + 1e-6:
        raise ValueError(f"消耗后半径差不能超过原始半径差 {full:.2f} mm")
    return min(max(delta_r_mm, 0.0), full)


def compute_length_case(r_in: float, r_out: float,
                        total_length_m: float, delta_r_mm: float) -> dict:
    """卷烟纸：按已知总长计算消耗后的剩余长度。"""
    delta = checked_delta(r_in, r_out, delta_r_mm)
    wall = wall_from_length(r_in, r_out, total_length_m)
    r_now = r_in + delta
    rem_len = length_from_radii(r_in, r_now, wall) if delta > 0 else 0.0
    return {
        "wall": wall,
        "delta": delta,
        "r_now": r_now,
        "rem_len": rem_len,
        "used_len": total_length_m - rem_len,
        "rem_ratio": rem_len / total_length_m,
    }


def compute_weight_case(r_in: float, r_out: float, total_weight_kg: float,
                        delta_r_mm: float) -> dict:
    """水松纸：按已知总重计算消耗后的剩余重量（重量与环截面积成正比）。"""
    delta = checked_delta(r_in, r_out, delta_r_mm)
    if total_weight_kg <= 0:
        raise ValueError("盘纸重量必须大于 0")
    r_now = r_in + delta
    ratio = (r_now ** 2 - r_in ** 2) / (r_out ** 2 - r_in ** 2)
    rem_weight = total_weight_kg * ratio
    return {
        "delta": delta,
        "r_now": r_now,
        "rem_weight": rem_weight,
        "used_weight": total_weight_kg - rem_weight,
        "rem_ratio": ratio,
    }


def fmt(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def resource_path(relative: str) -> str:
    """兼容源码运行与 PyInstaller 打包后的资源路径。"""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


# ---------------------------------------------------------------------------
# 中文字体（Kivy 默认字体不含中文，运行时注册系统字体）
# ---------------------------------------------------------------------------

FONT_CANDIDATES = [
    # 项目自带字体：保证任何电脑/手机上中文都能显示
    resource_path(os.path.join("fonts", "simhei.ttf")),
    resource_path(os.path.join("fonts", "NotoSansSC-Regular.otf")),
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "simhei.ttf"),
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "msyh.ttc"),
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "Deng.ttf"),
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/DroidSansFallback.ttf",
    "/System/Library/Fonts/PingFang.ttc",
]


def register_cjk_font() -> str:
    for path in FONT_CANDIDATES:
        if path and os.path.exists(path):
            try:
                LabelBase.register(name="CJK", fn_regular=path,
                                   fn_bold=path, fn_italic=path, fn_bolditalic=path)
                return "CJK"
            except Exception:
                continue
    return "Roboto"


# ---------------------------------------------------------------------------
# 内置默认值
# ---------------------------------------------------------------------------

DEFAULTS = {
    "paper_rin": 38.1,
    "paper_rout": 200.0,
    "paper_len": 4700.0,
    "tip_rin": 38.1,
    "tip_rout": 200.0,
    "tip_weight": 5.7,
}

DEFAULT_DELTA_TEXT = "0"


# ---------------------------------------------------------------------------
# 盘纸截面可视化（Kivy Canvas 绘制）
# ---------------------------------------------------------------------------

class RollPreview(Widget):
    """盘纸截面示意。

    虚线圆   ：原始外半径 R
    半透明圆：剩余纸层（盘纸为半透明灰，水松纸为半透明橙）
    白色圆   ：内芯（内半径 r）
    """

    base_color = ListProperty([0.42, 0.45, 0.51, 1.0])
    r_in = NumericProperty(38.1)
    r_out = NumericProperty(200.0)
    r_now = NumericProperty(38.1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=lambda *a: self.redraw(), pos=lambda *a: self.redraw())

    def set_values(self, r_in: float, r_out: float, r_now: float) -> None:
        self.r_in = max(float(r_in), 0.5)
        self.r_out = max(float(r_out), self.r_in + 0.5)
        self.r_now = min(max(float(r_now), self.r_in), self.r_out)
        self.redraw()

    def redraw(self) -> None:
        self.canvas.clear()
        w, h = self.width, self.height
        side = min(w, h) - dp(16)
        if side <= 40:
            return
        cx, cy = self.center
        scale = (side / 2.0) / self.r_out
        cr, cg, cb = self.base_color[0], self.base_color[1], self.base_color[2]

        def ellipse(radius: float, rgba):
            Color(*rgba)
            rpx = radius * scale
            Ellipse(pos=(cx - rpx, cy - rpx), size=(rpx * 2, rpx * 2))

        with self.canvas:
            # 1. 已消耗区域（原始整盘范围，极淡底色）
            ellipse(self.r_out, (cr, cg, cb, 0.10))
            # 2. 剩余纸层（半透明圆）
            ellipse(self.r_now, (cr, cg, cb, 0.45))
            # 3. 挖出内芯（卡片底色）
            ellipse(self.r_in, (1, 1, 1, 1))
            # 4. 内芯轮廓
            Color(0.55, 0.59, 0.67, 1)
            Line(circle=(cx, cy, self.r_in * scale, 0, 360), width=dp(1.2))
            # 5. 原始外半径：虚线圆
            Color(cr, cg, cb, 0.85)
            for i in range(40):
                start = i * 9 + 1.0
                Line(circle=(cx, cy, self.r_out * scale, start, start + 5.2),
                     width=dp(1.0))
            # 6. 剩余外半径：实线圆
            Line(circle=(cx, cy, self.r_now * scale, 0, 360), width=dp(1.5))


# ---------------------------------------------------------------------------
# 界面（KV）
# ---------------------------------------------------------------------------

KV = """
#:import dp kivy.metrics.dp

<Label>:
    font_name: app.font_name
    color: (0.12, 0.16, 0.24, 1)

<Button>:
    font_name: app.font_name

<TextInput>:
    font_name: app.font_name
    font_size: '16sp'
    multiline: False
    write_tab: False
    foreground_color: (0.12, 0.16, 0.24, 1)
    cursor_color: (0.145, 0.341, 0.78, 1)
    background_normal: ''
    background_active: ''
    background_color: (1, 1, 1, 1)
    padding: dp(10), dp(10)

<FieldRow@BoxLayout>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(46)
    spacing: dp(8)

<RowLabel@Label>:
    size_hint_x: None
    width: dp(112)
    font_size: '14sp'
    halign: 'left'
    valign: 'middle'
    text_size: self.size

<UnitLabel@Label>:
    size_hint_x: None
    width: dp(30)
    font_size: '13sp'
    color: (0.48, 0.53, 0.61, 1)
    halign: 'left'
    valign: 'middle'
    text_size: self.size

<Card@BoxLayout>:
    orientation: 'vertical'
    padding: dp(14)
    spacing: dp(8)
    size_hint_y: None
    height: self.minimum_height
    canvas.before:
        Color:
            rgba: (1, 1, 1, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: (0.85, 0.89, 0.95, 1)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(12))
            width: 1

<ResultCard@BoxLayout>:
    orientation: 'vertical'
    padding: dp(14)
    spacing: dp(6)
    size_hint_y: None
    height: self.minimum_height
    canvas.before:
        Color:
            rgba: (0.933, 0.957, 1, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: (0.827, 0.878, 0.98, 1)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(12))
            width: 1

<CaptionLabel@Label>:
    font_size: '12sp'
    color: (0.48, 0.53, 0.61, 1)
    size_hint_y: None
    height: self.texture_size[1]
    text_size: self.width, None
    halign: 'left'

<ErrorLabel@Label>:
    font_size: '13sp'
    color: (0.75, 0.22, 0.17, 1)
    size_hint_y: None
    height: self.texture_size[1]
    text_size: self.width, None
    halign: 'left'

<PrimaryButton@Button>:
    font_size: '15sp'
    background_normal: ''
    background_down: ''
    background_color: (0.145, 0.341, 0.78, 1)
    color: (1, 1, 1, 1)

<GhostButton@Button>:
    font_size: '15sp'
    background_normal: ''
    background_down: ''
    background_color: (0.933, 0.949, 0.988, 1)
    color: (0.145, 0.341, 0.78, 1)

BoxLayout:
    orientation: 'vertical'

    # 顶部：两个选项（卷烟纸 / 水松纸）
    BoxLayout:
        orientation: 'horizontal'
        size_hint_y: None
        height: dp(54)
        padding: dp(12), dp(10), dp(12), dp(4)
        spacing: dp(8)
        Button:
            id: tab_paper
            text: '卷烟纸'
            font_size: '15sp'
            background_normal: ''
            background_down: ''
            on_release: app.switch_tab('paper')
        Button:
            id: tab_tip
            text: '水松纸'
            font_size: '15sp'
            background_normal: ''
            background_down: ''
            on_release: app.switch_tab('tip')
        Button:
            id: tab_records
            text: '记录'
            font_size: '15sp'
            background_normal: ''
            background_down: ''
            on_release: app.switch_tab('records')

    ScreenManager:
        id: sm

        # ================= 卷烟纸 =================
        Screen:
            name: 'paper'
            ScrollView:
                do_scroll_x: False
                bar_width: dp(3)
                BoxLayout:
                    orientation: 'vertical'
                    padding: dp(12)
                    spacing: dp(12)
                    size_hint_y: None
                    height: self.minimum_height

                    Card:
                        FieldRow:
                            RowLabel:
                                text: '内半径 r'
                            TextInput:
                                id: p_rin
                                input_type: 'number'
                                on_text: app.recalc_paper()
                            UnitLabel:
                                text: 'mm'
                        FieldRow:
                            RowLabel:
                                text: '外半径 R'
                            TextInput:
                                id: p_rout
                                input_type: 'number'
                                on_text: app.recalc_paper()
                            UnitLabel:
                                text: 'mm'
                        FieldRow:
                            RowLabel:
                                text: '盘纸长度 L'
                            TextInput:
                                id: p_len
                                input_type: 'number'
                                on_text: app.recalc_paper()
                            UnitLabel:
                                text: 'm'

                        CaptionLabel:
                            text: '消耗参数'
                        BoxLayout:
                            orientation: 'horizontal'
                            size_hint_y: None
                            height: dp(38)
                            spacing: dp(8)
                            Button:
                                id: p_mode_delta
                                text: '半径差 Δr'
                                font_size: '13sp'
                                background_normal: ''
                                background_down: ''
                                on_release: app.set_paper_mode('delta')
                            Button:
                                id: p_mode_rnow
                                text: '外半径 R′'
                                font_size: '13sp'
                                background_normal: ''
                                background_down: ''
                                on_release: app.set_paper_mode('rnow')

                        FieldRow:
                            RowLabel:
                                text: '半径差 Δr'
                            TextInput:
                                id: p_delta
                                input_type: 'number'
                                disabled: app.paper_mode == 'rnow'
                                opacity: 0.35 if self.disabled else 1
                                on_text: app.recalc_paper()
                            UnitLabel:
                                text: 'mm'
                        FieldRow:
                            RowLabel:
                                text: '消耗后外半径 R′'
                            TextInput:
                                id: p_rnow
                                input_type: 'number'
                                disabled: app.paper_mode == 'delta'
                                opacity: 0.35 if self.disabled else 1
                                on_text: app.recalc_paper()
                            UnitLabel:
                                text: 'mm'

                        ErrorLabel:
                            text: app.paper_error

                    ResultCard:
                        CaptionLabel:
                            text: '剩余盘纸长度（仅显示，不保存）'
                        BoxLayout:
                            orientation: 'horizontal'
                            size_hint_y: None
                            height: dp(50)
                            spacing: dp(6)
                            Label:
                                text: app.paper_value
                                font_size: '32sp'
                                color: (0.106, 0.271, 0.639, 1)
                                halign: 'left'
                                valign: 'bottom'
                                text_size: self.size
                            Label:
                                text: 'm'
                                font_size: '15sp'
                                color: (0.29, 0.33, 0.41, 1)
                                size_hint_x: None
                                width: dp(24)
                                halign: 'left'
                                valign: 'bottom'
                                text_size: self.size
                        CaptionLabel:
                            text: app.paper_sub

                    Card:
                        CaptionLabel:
                            text: '盘纸截面示意'
                        RollPreview:
                            id: p_preview
                            base_color: (0.42, 0.45, 0.51, 1)
                            size_hint_y: None
                            height: dp(228)
                        Label:
                            text: app.paper_caption
                            font_size: '13sp'
                            color: (0.29, 0.33, 0.41, 1)
                            size_hint_y: None
                            height: dp(20)
                        CaptionLabel:
                            text: '半透明灰：剩余纸层　虚线：原始外半径'
                            halign: 'center'

                    BoxLayout:
                        orientation: 'horizontal'
                        size_hint_y: None
                        height: dp(48)
                        spacing: dp(10)
                        PrimaryButton:
                            text: '保存并记录'
                            on_release: app.save_inputs('卷烟纸')
                        GhostButton:
                            text: '恢复默认参数'
                            on_release: app.reset_defaults()

        # ================= 水松纸 =================
        Screen:
            name: 'tip'
            ScrollView:
                do_scroll_x: False
                bar_width: dp(3)
                BoxLayout:
                    orientation: 'vertical'
                    padding: dp(12)
                    spacing: dp(12)
                    size_hint_y: None
                    height: self.minimum_height

                    Card:
                        FieldRow:
                            RowLabel:
                                text: '内半径 r'
                            TextInput:
                                id: t_rin
                                input_type: 'number'
                                on_text: app.recalc_tip()
                            UnitLabel:
                                text: 'mm'
                        FieldRow:
                            RowLabel:
                                text: '外半径 R'
                            TextInput:
                                id: t_rout
                                input_type: 'number'
                                on_text: app.recalc_tip()
                            UnitLabel:
                                text: 'mm'
                        FieldRow:
                            RowLabel:
                                text: '盘纸重量 W'
                            TextInput:
                                id: t_weight
                                input_type: 'number'
                                on_text: app.recalc_tip()
                            UnitLabel:
                                text: 'kg'

                        CaptionLabel:
                            text: '消耗参数'
                        BoxLayout:
                            orientation: 'horizontal'
                            size_hint_y: None
                            height: dp(38)
                            spacing: dp(8)
                            Button:
                                id: t_mode_delta
                                text: '半径差 Δr'
                                font_size: '13sp'
                                background_normal: ''
                                background_down: ''
                                on_release: app.set_tip_mode('delta')
                            Button:
                                id: t_mode_rnow
                                text: '外半径 R′'
                                font_size: '13sp'
                                background_normal: ''
                                background_down: ''
                                on_release: app.set_tip_mode('rnow')

                        FieldRow:
                            RowLabel:
                                text: '半径差 Δr'
                            TextInput:
                                id: t_delta
                                input_type: 'number'
                                disabled: app.tip_mode == 'rnow'
                                opacity: 0.35 if self.disabled else 1
                                on_text: app.recalc_tip()
                            UnitLabel:
                                text: 'mm'
                        FieldRow:
                            RowLabel:
                                text: '消耗后外半径 R′'
                            TextInput:
                                id: t_rnow
                                input_type: 'number'
                                disabled: app.tip_mode == 'delta'
                                opacity: 0.35 if self.disabled else 1
                                on_text: app.recalc_tip()
                            UnitLabel:
                                text: 'mm'

                        ErrorLabel:
                            text: app.tip_error

                    ResultCard:
                        CaptionLabel:
                            text: '剩余水松纸重量（仅显示，不保存）'
                        BoxLayout:
                            orientation: 'horizontal'
                            size_hint_y: None
                            height: dp(50)
                            spacing: dp(6)
                            Label:
                                text: app.tip_value
                                font_size: '32sp'
                                color: (0.702, 0.361, 0, 1)
                                halign: 'left'
                                valign: 'bottom'
                                text_size: self.size
                            Label:
                                text: 'kg'
                                font_size: '15sp'
                                color: (0.29, 0.33, 0.41, 1)
                                size_hint_x: None
                                width: dp(24)
                                halign: 'left'
                                valign: 'bottom'
                                text_size: self.size
                        CaptionLabel:
                            text: app.tip_sub

                    Card:
                        CaptionLabel:
                            text: '盘纸截面示意'
                        RollPreview:
                            id: t_preview
                            base_color: (0.964, 0.569, 0.125, 1)
                            size_hint_y: None
                            height: dp(228)
                        Label:
                            text: app.tip_caption
                            font_size: '13sp'
                            color: (0.29, 0.33, 0.41, 1)
                            size_hint_y: None
                            height: dp(20)
                        CaptionLabel:
                            text: '半透明橙：剩余纸层　虚线：原始外半径'
                            halign: 'center'

                    BoxLayout:
                        orientation: 'horizontal'
                        size_hint_y: None
                        height: dp(48)
                        spacing: dp(10)
                        PrimaryButton:
                            text: '保存并记录'
                            on_release: app.save_inputs('水松纸')
                        GhostButton:
                            text: '恢复默认参数'
                            on_release: app.reset_defaults()

    Label:
        text: app.status
        font_size: '12sp'
        color: (0.48, 0.53, 0.61, 1)
        size_hint_y: None
        height: dp(24)
        padding: dp(12), 0
        halign: 'left'
        valign: 'middle'
        text_size: self.size
"""


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class PaperCalcApp(App):
    font_name = StringProperty("Roboto")
    current_tab = StringProperty("paper")
    paper_mode = StringProperty("delta")
    tip_mode = StringProperty("delta")

    paper_value = StringProperty("—")
    paper_sub = StringProperty("")
    paper_caption = StringProperty("")
    paper_error = StringProperty("")

    tip_value = StringProperty("—")
    tip_sub = StringProperty("")
    tip_caption = StringProperty("")
    tip_error = StringProperty("")

    status = StringProperty("就绪：计算结果仅在界面显示，不保存")

    # ------------------------------------------------------------ 生命周期
    def build(self):
        from kivy.logger import Logger

        self.title = "盘纸余量计算"
        self.font_name = register_cjk_font()
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.icon = icon_path
        if platform not in ("android", "ios"):
            Window.size = (410, 800)
        root = Builder.load_string(KV)
        Logger.info(
            "App: frozen=%s platform=%s size=%s font=%s root_children=%d",
            getattr(sys, "frozen", False), platform, Window.size,
            self.font_name, len(root.children),
        )
        return root

    def on_start(self):
        from kivy.logger import Logger
        from kivy.metrics import Metrics

        # 冻结版（exe）启动时窗口可能尚未就绪，这里再设定一次目标尺寸
        if platform not in ("android", "ios"):
            Window.size = (410, 800)

        self._style_tab_buttons()
        self._load_inputs()
        self._style_mode_buttons()
        self._create_records_screen()
        self.recalc_paper()
        self.recalc_tip()
        Logger.info(
            "App: on_start size=%s system_size=%s dpi=%s density=%s root=%s",
            Window.size, Window.system_size, Window.dpi, Metrics.density,
            self.root.size,
        )
        from kivy.clock import Clock
        Clock.schedule_once(self._log_late, 1.0)

    def _log_late(self, _dt):
        from kivy.logger import Logger
        Logger.info(
            "App: delayed size=%s system_size=%s root=%s",
            Window.size, Window.system_size, self.root.size,
        )

    def on_stop(self):
        self._save_inputs(silent=True)

    # ------------------------------------------------------------ 配置
    def _config_path(self) -> str:
        return os.path.join(self.user_data_dir, "config.ini")

    def _load_inputs(self) -> None:
        ids = self.root.ids
        restored = False
        values = dict(DEFAULTS)
        path = self._config_path()
        if os.path.exists(path):
            try:
                cfg = configparser.ConfigParser()
                cfg.read(path, encoding="utf-8")
                for key in DEFAULTS:
                    section, option = key.split("_", 1)
                    if cfg.has_option(section, option):
                        values[key] = cfg.getfloat(section, option)
                restored = True
            except Exception:
                values = dict(DEFAULTS)

        # 防御：保存的几何参数异常时回退为内置默认值
        if values["paper_rin"] >= values["paper_rout"]:
            values["paper_rin"] = DEFAULTS["paper_rin"]
            values["paper_rout"] = DEFAULTS["paper_rout"]
        if values["tip_rin"] >= values["tip_rout"]:
            values["tip_rin"] = DEFAULTS["tip_rin"]
            values["tip_rout"] = DEFAULTS["tip_rout"]

        ids.p_rin.text = f"{values['paper_rin']:g}"
        ids.p_rout.text = f"{values['paper_rout']:g}"
        ids.p_len.text = f"{values['paper_len']:g}"
        ids.t_rin.text = f"{values['tip_rin']:g}"
        ids.t_rout.text = f"{values['tip_rout']:g}"
        ids.t_weight.text = f"{values['tip_weight']:g}"

        # 半径差与输入方式不保存，每次启动使用默认值
        ids.p_delta.text = DEFAULT_DELTA_TEXT
        ids.t_delta.text = DEFAULT_DELTA_TEXT
        ids.p_rnow.text = ""
        ids.t_rnow.text = ""
        self.paper_mode = "delta"
        self.tip_mode = "delta"

        if restored:
            self.status = "已载入上次保存的参数（半径差未保存，使用默认值）"
        else:
            self.status = "首次使用：当前为内置默认值，点“保存为默认”后记住输入"

    def _save_inputs(self, status_from: str | None = None, silent: bool = False) -> None:
        ids = self.root.ids
        try:
            cfg = configparser.ConfigParser()
            cfg["paper"] = {
                "rin": ids.p_rin.text.strip(),
                "rout": ids.p_rout.text.strip(),
                "len": ids.p_len.text.strip(),
            }
            cfg["tip"] = {
                "rin": ids.t_rin.text.strip(),
                "rout": ids.t_rout.text.strip(),
                "weight": ids.t_weight.text.strip(),
            }
            os.makedirs(self.user_data_dir, exist_ok=True)
            with open(self._config_path(), "w", encoding="utf-8") as file:
                cfg.write(file)
            message = "输入参数已保存为下次默认值"
        except Exception as exc:  # 磁盘异常时仅提示，不影响计算
            message = f"保存失败：{exc}"
        if silent:
            return
        # 自动存储：每次成功保存参数时，自动追加一条计算记录
        appended = False
        if status_from in ("卷烟纸", "水松纸"):
            try:
                if status_from == "卷烟纸":
                    appended = self._append_record("卷烟纸", self.paper_value, "m")
                else:
                    appended = self._append_record("水松纸", self.tip_value, "kg")
            except Exception:
                appended = False
        if status_from:
            message = f"{status_from}：{message}"
        if appended:
            message += "，已自动存储一条记录"
        self.status = message

    def save_inputs(self, status_from: str | None = None) -> None:
        self._save_inputs(status_from=status_from)

    def reset_defaults(self) -> None:
        ids = self.root.ids
        ids.p_rin.text = f"{DEFAULTS['paper_rin']:g}"
        ids.p_rout.text = f"{DEFAULTS['paper_rout']:g}"
        ids.p_len.text = f"{DEFAULTS['paper_len']:g}"
        ids.t_rin.text = f"{DEFAULTS['tip_rin']:g}"
        ids.t_rout.text = f"{DEFAULTS['tip_rout']:g}"
        ids.t_weight.text = f"{DEFAULTS['tip_weight']:g}"
        ids.p_delta.text = DEFAULT_DELTA_TEXT
        ids.t_delta.text = DEFAULT_DELTA_TEXT
        ids.p_rnow.text = ""
        ids.t_rnow.text = ""
        self.paper_mode = "delta"
        self.tip_mode = "delta"
        self._style_mode_buttons()
        try:
            if os.path.exists(self._config_path()):
                os.remove(self._config_path())
        except OSError:
            pass
        self.recalc_paper()
        self.recalc_tip()
        self.status = "已恢复内置默认参数（保存的参数已清除）"

    # ------------------------------------------------------------ 记录存储
    def _history_path(self) -> str:
        return os.path.join(self.user_data_dir, "history.json")

    def _load_history(self) -> list:
        path = self._history_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_history(self, records: list) -> None:
        os.makedirs(self.user_data_dir, exist_ok=True)
        with open(self._history_path(), "w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)

    def _append_record(self, material: str, remaining_text: str, unit: str) -> bool:
        try:
            remaining = float(str(remaining_text).replace(",", "").strip())
        except (ValueError, TypeError):
            return False
        records = self._load_history()
        records.append({
            "id": uuid.uuid4().hex,
            "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "material": material,
            "remaining": remaining,
            "unit": unit,
        })
        self._save_history(records)
        self.refresh_records()
        return True

    def _delete_record(self, rid: str) -> None:
        records = [r for r in self._load_history() if r.get("id") != rid]
        self._save_history(records)
        self.refresh_records()

    def _update_record(self, rid: str, dt: str, material: str, remaining: float) -> None:
        records = self._load_history()
        for rec in records:
            if rec.get("id") == rid:
                rec["dt"] = dt
                rec["material"] = material
                rec["remaining"] = remaining
                rec["unit"] = "m" if material == "卷烟纸" else "kg"
        self._save_history(records)
        self.refresh_records()

    def clear_history(self) -> None:
        self._save_history([])
        self.refresh_records()
        self.status = "所有存储记录已清空"

    def _create_records_screen(self) -> None:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.screenmanager import Screen
        from kivy.uix.scrollview import ScrollView

        screen = Screen(name="records")
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        box = BoxLayout(orientation="vertical", padding=dp(4), spacing=dp(10),
                        size_hint_y=None)
        box.bind(minimum_height=box.setter("height"))
        scroll.add_widget(box)
        root.add_widget(scroll)

        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        clear_btn = Button(
            text="清空全部记录", font_size="14sp",
            background_normal="", background_down="",
            background_color=(0.933, 0.949, 0.988, 1),
            color=(0.75, 0.22, 0.17, 1),
        )
        clear_btn.bind(on_release=lambda *_: self.clear_history())
        btn_row.add_widget(clear_btn)
        root.add_widget(btn_row)
        screen.add_widget(root)
        self.root.ids.sm.add_widget(screen)
        self._records_box = box
        self.refresh_records()

    def refresh_records(self) -> None:
        if not hasattr(self, "_records_box"):
            return
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label

        box = self._records_box
        box.clear_widgets()
        records = self._load_history()
        if not records:
            box.add_widget(Label(
                text="暂无存储记录", font_size="14sp",
                color=(0.48, 0.53, 0.61, 1), size_hint_y=None, height=dp(40),
                halign="center", valign="middle", text_size=(None, None),
            ))
            return
        for rec in reversed(records):
            box.add_widget(self._make_record_card(rec))

    def _make_record_card(self, rec: dict):
        from kivy.graphics import Color, Line, RoundedRectangle
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label

        card = BoxLayout(orientation="vertical", size_hint_y=None,
                         padding=dp(12), spacing=dp(4))
        card.bind(minimum_height=card.setter("height"))

        with card.canvas.before:
            Color(1, 1, 1, 1)
            rrect = RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(10)])
            Color(0.85, 0.89, 0.95, 1)
            line = Line(rounded_rectangle=(card.x, card.y, card.width, card.height, dp(10)), width=1)
        card.bind(pos=lambda w, v: (setattr(rrect, "pos", v), setattr(line, "rounded_rectangle", (w.x, w.y, w.width, w.height, dp(10)))),
                  size=lambda w, v: (setattr(rrect, "size", v), setattr(line, "rounded_rectangle", (w.x, w.y, w.width, w.height, dp(10)))))

        row1 = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(8))
        row1.add_widget(Label(
            text=rec.get("dt", ""), font_size="13sp",
            color=(0.29, 0.33, 0.41, 1), halign="left", valign="middle",
            text_size=(None, None),
        ))
        row1.add_widget(Label(
            text=rec.get("material", ""), font_size="13sp", bold=True,
            color=(0.145, 0.341, 0.78, 1), size_hint_x=None, width=dp(72),
            halign="right", valign="middle", text_size=(None, None),
        ))
        card.add_widget(row1)

        unit = rec.get("unit", "m")
        remaining = rec.get("remaining", 0)
        row2 = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(8))
        row2.add_widget(Label(
            text=f"余量：{fmt(remaining, 3 if unit == 'kg' else 1)} {unit}",
            font_size="16sp", color=(0.12, 0.16, 0.24, 1),
            halign="left", valign="middle", text_size=(None, None),
        ))
        card.add_widget(row2)

        btns = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        eb = Button(text="编辑", font_size="13sp", background_normal="", background_down="",
                    background_color=(0.933, 0.949, 0.988, 1), color=(0.145, 0.341, 0.78, 1))
        db = Button(text="删除", font_size="13sp", background_normal="", background_down="",
                    background_color=(0.99, 0.92, 0.92, 1), color=(0.75, 0.22, 0.17, 1))
        eb.bind(on_release=lambda *_: self._open_edit_popup(rec))
        db.bind(on_release=lambda *_: self._confirm_delete(rec))
        btns.add_widget(eb)
        btns.add_widget(db)
        card.add_widget(btns)
        return card

    def _open_edit_popup(self, rec: dict) -> None:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.spinner import Spinner
        from kivy.uix.textinput import TextInput

        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(text="日期时间", size_hint_y=None, height=dp(20),
                                font_size="13sp", halign="left", text_size=(None, None)))
        dt_input = TextInput(text=rec.get("dt", ""), size_hint_y=None, height=dp(40),
                             font_size="14sp", multiline=False)
        content.add_widget(dt_input)

        content.add_widget(Label(text="物料类型", size_hint_y=None, height=dp(20),
                                font_size="13sp", halign="left", text_size=(None, None)))
        mat_spinner = Spinner(text=rec.get("material", "卷烟纸"),
                              values=["卷烟纸", "水松纸"], size_hint_y=None, height=dp(40),
                              font_size="14sp")
        content.add_widget(mat_spinner)

        content.add_widget(Label(text="余量", size_hint_y=None, height=dp(20),
                                font_size="13sp", halign="left", text_size=(None, None)))
        rem_input = TextInput(text=str(rec.get("remaining", "")), size_hint_y=None,
                              height=dp(40), font_size="14sp", input_type="number",
                              multiline=False)
        content.add_widget(rem_input)

        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        save_btn = Button(text="保存", font_size="14sp", background_normal="", background_down="",
                          background_color=(0.145, 0.341, 0.78, 1), color=(1, 1, 1, 1))
        cancel_btn = Button(text="取消", font_size="14sp", background_normal="", background_down="",
                            background_color=(0.933, 0.949, 0.988, 1),
                            color=(0.145, 0.341, 0.78, 1))
        btns.add_widget(save_btn)
        btns.add_widget(cancel_btn)
        content.add_widget(btns)

        popup = Popup(title="编辑记录", content=content, size_hint=(0.92, None),
                      height=dp(340), auto_dismiss=False)

        def do_save(*_):
            try:
                remaining = float(rem_input.text.strip())
            except ValueError:
                self.status = "余量不是有效数字"
                return
            self._update_record(rec["id"], dt_input.text.strip(), mat_spinner.text, remaining)
            popup.dismiss()
            self.status = "记录已更新"

        save_btn.bind(on_release=do_save)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _confirm_delete(self, rec: dict) -> None:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup

        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(
            text=f"确定删除 {rec.get('dt')} 的记录？", font_size="14sp",
            halign="center", valign="middle", text_size=(None, None),
        ))
        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        yes_btn = Button(text="删除", font_size="14sp", background_normal="", background_down="",
                         background_color=(0.75, 0.22, 0.17, 1), color=(1, 1, 1, 1))
        no_btn = Button(text="取消", font_size="14sp", background_normal="", background_down="",
                        background_color=(0.933, 0.949, 0.988, 1),
                        color=(0.145, 0.341, 0.78, 1))
        btns.add_widget(yes_btn)
        btns.add_widget(no_btn)
        content.add_widget(btns)
        popup = Popup(title="删除记录", content=content, size_hint=(0.85, None),
                      height=dp(160), auto_dismiss=False)
        yes_btn.bind(on_release=lambda *_: (self._delete_record(rec["id"]), popup.dismiss(),
                                            setattr(self, "status", "记录已删除")))
        no_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    # ------------------------------------------------------------ 界面状态
    def switch_tab(self, name: str) -> None:
        self.current_tab = name
        self.root.ids.sm.current = "paper" if name == "paper" else ("tip" if name == "tip" else "records")
        self._style_tab_buttons()
        if name == "records":
            self.refresh_records()

    def _style_tab_buttons(self) -> None:
        ids = self.root.ids
        for tid, active_name in (("tab_paper", "paper"), ("tab_tip", "tip"), ("tab_records", "records")):
            button = ids.get(tid)
            if button is None:
                continue
            if active_name == self.current_tab:
                button.background_color = (0.145, 0.341, 0.78, 1)
                button.color = (1, 1, 1, 1)
            else:
                button.background_color = (0.894, 0.918, 0.969, 1)
                button.color = (0.15, 0.31, 0.71, 1)

    def set_paper_mode(self, mode: str) -> None:
        self.paper_mode = mode
        self._style_mode_buttons()
        self.recalc_paper()

    def set_tip_mode(self, mode: str) -> None:
        self.tip_mode = mode
        self._style_mode_buttons()
        self.recalc_tip()

    def _style_mode_buttons(self) -> None:
        ids = self.root.ids
        pairs = (
            ("p_mode_delta", self.paper_mode == "delta"),
            ("p_mode_rnow", self.paper_mode == "rnow"),
            ("t_mode_delta", self.tip_mode == "delta"),
            ("t_mode_rnow", self.tip_mode == "rnow"),
        )
        for bid, active in pairs:
            button = ids.get(bid)
            if button is None:
                continue
            if active:
                button.background_color = (0.145, 0.341, 0.78, 1)
                button.color = (1, 1, 1, 1)
            else:
                button.background_color = (0.894, 0.918, 0.969, 1)
                button.color = (0.15, 0.31, 0.71, 1)

    # ------------------------------------------------------------ 输入解析
    def _text(self, name: str) -> str:
        ids = getattr(self.root, "ids", None)
        if not ids:
            return ""
        widget = ids.get(name)
        return widget.text if widget is not None else ""

    def _num(self, name: str, label: str) -> float:
        raw = self._text(name).strip().replace("，", "").replace(",", "")
        if not raw:
            raise ValueError(f"请输入{label}")
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"{label}不是有效数字")

    def _preview(self, name: str):
        ids = getattr(self.root, "ids", None)
        return ids.get(name) if ids else None

    # ------------------------------------------------------------ 卷烟纸计算
    def recalc_paper(self, *_):
        if not self.root or "p_rin" not in self.root.ids:
            return
        try:
            r_in = self._num("p_rin", "内半径")
            r_out = self._num("p_rout", "外半径")
            total = self._num("p_len", "盘纸长度")
            if self.paper_mode == "delta":
                delta = self._num("p_delta", "半径差")
            else:
                delta = self._num("p_rnow", "消耗后外半径") - r_in
            res = compute_length_case(r_in, r_out, total, delta)
        except ValueError as exc:
            self.paper_value = "—"
            self.paper_sub = ""
            self.paper_caption = ""
            self.paper_error = f"参数有误：{exc}"
            self._reset_preview("p_preview")
            return

        self.paper_error = ""
        self.paper_value = fmt(res["rem_len"], 1)
        self.paper_sub = (
            f"剩余外半径 {res['r_now']:.2f} mm · 已消耗 {fmt(res['used_len'], 1)} m"
            f" · 推算纸厚 {res['wall']:.4f} mm"
        )
        self.paper_caption = (
            f"剩余外半径 {res['r_now']:.2f} mm · 剩余 {res['rem_ratio'] * 100:.2f}%"
        )
        preview = self._preview("p_preview")
        if preview is not None:
            preview.set_values(r_in, r_out, res["r_now"])

    # ------------------------------------------------------------ 水松纸计算
    def recalc_tip(self, *_):
        if not self.root or "t_rin" not in self.root.ids:
            return
        try:
            r_in = self._num("t_rin", "内半径")
            r_out = self._num("t_rout", "外半径")
            weight = self._num("t_weight", "盘纸重量")
            if self.tip_mode == "delta":
                delta = self._num("t_delta", "半径差")
            else:
                delta = self._num("t_rnow", "消耗后外半径") - r_in
            res = compute_weight_case(r_in, r_out, weight, delta)
        except ValueError as exc:
            self.tip_value = "—"
            self.tip_sub = ""
            self.tip_caption = ""
            self.tip_error = f"参数有误：{exc}"
            self._reset_preview("t_preview")
            return

        self.tip_error = ""
        self.tip_value = fmt(res["rem_weight"], 3)
        self.tip_sub = (
            f"剩余外半径 {res['r_now']:.2f} mm · 已消耗 {fmt(res['used_weight'], 3)} kg"
        )
        self.tip_caption = (
            f"剩余外半径 {res['r_now']:.2f} mm · 剩余 {res['rem_ratio'] * 100:.2f}%"
        )
        preview = self._preview("t_preview")
        if preview is not None:
            preview.set_values(r_in, r_out, res["r_now"])

    def _reset_preview(self, name: str) -> None:
        preview = self._preview(name)
        if preview is None:
            return
        prefix = "paper" if name.startswith("p_") else "tip"
        try:
            r_in = self._num(f"{name.split('_')[0]}_rin", "内半径")
            r_out = self._num(f"{name.split('_')[0]}_rout", "外半径")
        except ValueError:
            r_in, r_out = DEFAULTS[f"{prefix}_rin"], DEFAULTS[f"{prefix}_rout"]
        preview.set_values(r_in, max(r_out, r_in + 1.0), r_in)


def main() -> None:
    app = PaperCalcApp()
    if SMOKE_TEST:
        from kivy.clock import Clock

        def step_paper(_dt):
            app.root.ids.p_delta.text = "40"

        def shot_paper(_dt):
            Window.screenshot(name="_smoke_paper.png")
            print("SMOKE paper value:", app.paper_value, "|", app.paper_sub)
            app.switch_tab("tip")

        def step_tip(_dt):
            app.root.ids.t_delta.text = "40"

        def shot_tip(_dt):
            Window.screenshot(name="_smoke_tip.png")
            print("SMOKE tip value:", app.tip_value, "|", app.tip_sub)
            app.stop()

        Clock.schedule_once(step_paper, 0.6)
        Clock.schedule_once(shot_paper, 1.0)
        Clock.schedule_once(step_tip, 1.4)
        Clock.schedule_once(shot_tip, 1.8)
    app.run()


if __name__ == "__main__":
    main()
