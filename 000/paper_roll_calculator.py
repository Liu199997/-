#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘纸余量计算系统（PyQt5）

输入均使用“半径”（mm）：
    卷烟纸：内半径 r、外半径 R、盘纸长度 L（m）、消耗后半径差 Δr → 剩余长度 (m)
    水松纸：内半径 r、外半径 R、盘纸重量 W（kg）、消耗后半径差 Δr → 剩余重量 (kg)

参数记忆：
    用户输入的内外半径、盘纸长度、水松纸重量会保存为下一次运行的默认值；
    计算得到的剩余长度 / 剩余重量不保存（仅在界面显示）。

可视化：
    盘纸（卷烟纸）剩余纸层用半透明灰色，水松纸用半透明橙色，
    虚线圆为原始外半径，白色圆为内芯。

计算模型（螺旋卷绕等效面积法，半径为 r、R，纸厚 w，纸长 L）：
    pi (R^2 - r^2) = L * w
    消耗后剩余外半径 R' = r + Δr：
        剩余长度 L' = pi (R'^2 - r^2) / w
        剩余重量 W' = W * (R'^2 - r^2) / (R^2 - r^2)
"""

from __future__ import annotations

import math
import os
import sys

from PyQt5.QtCore import Qt, QRectF, QSettings, QTimer
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# 计算内核（半径制，单位 mm / m / kg）
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
    """水松纸：按已知总重计算消耗后的剩余重量。

    同幅宽、同厚度时重量与纸长（环截面积）成正比，与纸厚无关。
    """
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


# ---------------------------------------------------------------------------
# 盘纸截面可视化（半径制）
# ---------------------------------------------------------------------------

class RollPreview(QWidget):
    """盘纸截面示意。

    虚线圆   ：原始外半径 R
    半透明圆环：剩余纸层（盘纸为半透明灰，水松纸为半透明橙）
    白色圆   ：内芯（内半径 r）
    """

    def __init__(self, base_color: QColor, parent=None):
        super().__init__(parent)
        self.base = base_color
        self.r_in = 38.1
        self.r_out = 200.0
        self.r_now = 78.1
        self.percent = 0.0
        self.setMinimumSize(200, 210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_values(self, r_in: float, r_out: float, r_now: float,
                   percent: float) -> None:
        self.r_in = max(float(r_in), 0.5)
        self.r_out = max(float(r_out), self.r_in + 0.5)
        self.r_now = min(max(float(r_now), self.r_in), self.r_out)
        self.percent = float(percent)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        text_h = 24
        margin = 12
        size = min(self.width() - margin * 2, self.height() - margin * 2 - text_h)
        if size <= 30:
            return
        cx = self.width() / 2.0
        cy = (self.height() - text_h) / 2.0
        scale = (size / 2.0) / self.r_out  # 半径 1 mm 对应像素数

        def rect_for(radius: float) -> QRectF:
            pixels = radius * scale
            return QRectF(cx - pixels, cy - pixels, pixels * 2, pixels * 2)

        base = self.base

        # 1. 已消耗区域（原始整盘范围，极淡底色）
        consumed = QColor(base)
        consumed.setAlpha(24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(consumed))
        painter.drawEllipse(rect_for(self.r_out))

        # 2. 剩余纸层：半透明圆环（偶奇填充规则）
        remaining = QColor(base)
        remaining.setAlpha(115)
        ring = QPainterPath()
        ring.setFillRule(Qt.OddEvenFill)
        ring.addEllipse(rect_for(self.r_now))
        ring.addEllipse(rect_for(self.r_in))
        painter.setBrush(QBrush(remaining))
        painter.drawPath(ring)

        # 3. 轮廓：剩余外半径实线、原始外半径虚线
        edge = QColor(base)
        edge.setAlpha(200)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(edge, 1.6))
        painter.drawEllipse(rect_for(self.r_now))

        painter.setPen(QPen(edge, 1.1, Qt.DashLine))
        painter.drawEllipse(rect_for(self.r_out))

        # 4. 内芯
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#8b96ac"), 1.4))
        painter.drawEllipse(rect_for(self.r_in))

        # 5. 中心十字
        painter.setPen(QPen(QColor("#cfd6e4"), 1, Qt.DashLine))
        half = size / 2.0 - 2
        painter.drawLine(int(cx - half), int(cy), int(cx + half), int(cy))
        painter.drawLine(int(cx), int(cy - half), int(cx), int(cy + half))

        # 6. 底部文字
        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(QPen(QColor("#4b5568")))
        caption = f"剩余外半径 {self.r_now:.2f} mm · 剩余 {self.percent:.2f}%"
        painter.drawText(QRectF(0, self.height() - text_h, self.width(), text_h),
                         Qt.AlignCenter, caption)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def make_spin(lo: float, hi: float, value: float, decimals: int = 2,
              step: float = 1.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(lo, hi)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setValue(value)
    spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    spin.setKeyboardTracking(False)
    spin.setMinimumWidth(90)
    return spin


def grid_row(grid: QGridLayout, row: int, text: str, widget: QWidget,
             unit: str = "") -> None:
    label = QLabel(text)
    label.setStyleSheet("color:#4b5568;")
    grid.addWidget(label, row, 0)
    grid.addWidget(widget, row, 1)
    if unit:
        unit_label = QLabel(unit)
        unit_label.setStyleSheet("color:#8b96ac;")
        unit_label.setMinimumWidth(30)
        grid.addWidget(unit_label, row, 2)


# 内置默认值（首次运行）
DEFAULTS = {
    "paper/rin": 38.1,
    "paper/rout": 200.0,
    "paper/len": 4700.0,
    "paper/delta": 0.0,
    "tip/rin": 38.1,
    "tip/rout": 200.0,
    "tip/weight": 5.7,
    "tip/delta": 0.0,
}

# 需要保存为下次默认值的输入项（半径、长度、重量；不含差值，也不含计算结果）
SAVED_INPUTS = (
    "paper/rin", "paper/rout", "paper/len",
    "tip/rin", "tip/rout", "tip/weight",
)

CONFIG_PATH = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__)),
    "config.ini",
)

APP_STYLE = """
QWidget {
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px; color: #1f2a3d;
}
QMainWindow { background: #f4f6fb; }
QGroupBox {
    background: #ffffff; border: 1px solid #dde4f2; border-radius: 12px;
    margin-top: 18px; padding: 14px 12px 12px 12px; font-weight: 600; color: #2557c7;
}
QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; }
QGroupBox QLabel { font-weight: 400; }
QDoubleSpinBox, QComboBox {
    background: #ffffff; border: 1px solid #cfd8ea; border-radius: 6px;
    padding: 5px 8px; min-height: 18px; selection-background-color: #2557c7;
}
QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #2557c7; }
QDoubleSpinBox:disabled { background: #f1f4fa; color: #9aa4b8; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    border: 1px solid #cfd8ea; background: #ffffff; selection-background-color: #2557c7;
}
QPushButton {
    background: #2557c7; color: #ffffff; border: none; border-radius: 6px;
    padding: 9px 20px; font-weight: 600;
}
QPushButton:hover { background: #1b45a3; }
QPushButton:pressed { background: #163680; }
QPushButton#ghost {
    background: #eef2fc; color: #2557c7; border: 1px solid #c7d5f7; padding: 7px 16px;
}
QPushButton#ghost:hover { background: #e0e9fb; }
QFrame#resultFrame { background: #eef4ff; border: 1px solid #d3e0fa; border-radius: 10px; }
QFrame#previewFrame { background: #fbfcff; border: 1px solid #e3e9f5; border-radius: 10px; }
QLabel#caption { color: #7b879c; font-weight: 400; }
QLabel#error { color: #c0392b; font-weight: 600; }
"""


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class CalcWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("盘纸余量计算系统 · 卷烟纸 / 水松纸（半径制）")
        self.resize(1180, 720)
        self.setMinimumSize(1120, 640)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(8)

        title = QLabel("盘纸余量计算系统")
        title.setStyleSheet("font-size:23px; font-weight:700; color:#163a8d;")
        subtitle = QLabel(
            "输入均按半径（mm）· 内外半径、盘纸长度、盘纸重量自动保存为下次默认值"
            " · 计算结果（剩余长度 / 剩余重量）不保存，仅显示"
        )
        subtitle.setObjectName("caption")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self.build_paper_card(), 1)
        cards.addWidget(self.build_tip_card(), 1)
        root.addLayout(cards, 1)

        footer = QHBoxLayout()
        self.status = QLabel("就绪：计算结果仅在界面显示，不保存")
        self.status.setObjectName("caption")
        reset_button = QPushButton("恢复默认参数")
        reset_button.setObjectName("ghost")
        reset_button.clicked.connect(self.reset_defaults)
        footer.addWidget(self.status, 1)
        footer.addWidget(reset_button)
        root.addLayout(footer)

        self.load_inputs()
        self.recalc_paper()
        self.recalc_tip()

    # ------------------------------------------------------------- 卷烟纸卡片
    def build_paper_card(self) -> QWidget:
        card = QGroupBox("卷烟纸（按长度计算）")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(10)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)

        self.p_rin = make_spin(2, 1000, DEFAULTS["paper/rin"], 2, 1.0)
        self.p_rout = make_spin(5, 2000, DEFAULTS["paper/rout"], 2, 1.0)
        self.p_len = make_spin(1, 500000, DEFAULTS["paper/len"], 1, 100.0)
        self.p_mode = QComboBox()
        self.p_mode.addItems(["按半径差 Δr", "按消耗后外半径"])
        self.p_mode.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.p_mode.setMinimumWidth(110)
        self.p_delta = make_spin(0, 2000, DEFAULTS["paper/delta"], 2, 1.0)
        self.p_rnow = make_spin(2, 2000, DEFAULTS["paper/rin"] + DEFAULTS["paper/delta"], 2, 1.0)
        self.p_rnow.setEnabled(False)

        self.p_delta.setToolTip("消耗后纸盘剩余纸层的半径差：剩余外半径 − 内半径")
        self.p_rnow.setToolTip("卡尺实测的消耗后纸盘外半径")
        self.p_len.setToolTip("整盘纸的总长度，可修改（如 4700 m）")

        grid_row(grid, 0, "内半径 r", self.p_rin, "mm")
        grid_row(grid, 1, "外半径 R", self.p_rout, "mm")
        grid_row(grid, 2, "盘纸长度 L", self.p_len, "m")
        grid_row(grid, 3, "消耗参数", self.p_mode)
        grid_row(grid, 4, "半径差 Δr", self.p_delta, "mm")
        grid_row(grid, 5, "消耗后外半径 R′", self.p_rnow, "mm")
        left.addLayout(grid)

        self.p_calc_btn = QPushButton("计 算")
        self.p_calc_btn.clicked.connect(self.calc_paper_and_save)
        left.addWidget(self.p_calc_btn)

        self.p_error = QLabel("")
        self.p_error.setObjectName("error")
        self.p_error.setWordWrap(True)
        left.addWidget(self.p_error)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(6)
        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        pf = QVBoxLayout(preview_frame)
        pf.setContentsMargins(6, 6, 6, 6)
        self.p_preview = RollPreview(QColor(108, 116, 130))
        pf.addWidget(self.p_preview)
        legend = QLabel("半透明灰：剩余纸层　虚线：原始外半径")
        legend.setObjectName("caption")
        legend.setAlignment(Qt.AlignCenter)
        legend.setWordWrap(True)
        right.addWidget(preview_frame, 1)
        right.addWidget(legend)

        main_row.addLayout(left, 1)
        main_row.addLayout(right, 0)
        layout.addLayout(main_row)

        result_frame = QFrame()
        result_frame.setObjectName("resultFrame")
        rf = QVBoxLayout(result_frame)
        rf.setContentsMargins(14, 10, 14, 10)
        rf.setSpacing(4)
        top = QLabel("剩余盘纸长度（不保存，仅显示）")
        top.setObjectName("caption")
        value_row = QHBoxLayout()
        self.p_value = QLabel("—")
        self.p_value.setStyleSheet("font-size:30px; font-weight:700; color:#1b45a3;")
        unit = QLabel("m")
        unit.setStyleSheet("font-size:15px; color:#4b5568; padding-top:9px;")
        value_row.addWidget(self.p_value)
        value_row.addWidget(unit)
        value_row.addStretch(1)
        self.p_sub = QLabel("")
        self.p_sub.setObjectName("caption")
        self.p_sub.setWordWrap(True)
        rf.addWidget(top)
        rf.addLayout(value_row)
        rf.addWidget(self.p_sub)
        layout.addWidget(result_frame)
        layout.addStretch(1)

        for spin_box in (self.p_rin, self.p_rout, self.p_len,
                         self.p_delta, self.p_rnow):
            spin_box.valueChanged.connect(self.recalc_paper)
        self.p_mode.currentIndexChanged.connect(self.recalc_paper)
        return card

    def paper_delta(self) -> float:
        if self.p_mode.currentIndex() == 0:
            return self.p_delta.value()
        return self.p_rnow.value() - self.p_rin.value()

    def recalc_paper(self, *_):
        self.p_delta.setEnabled(self.p_mode.currentIndex() == 0)
        self.p_rnow.setEnabled(self.p_mode.currentIndex() == 1)
        r_in = self.p_rin.value()
        r_out = self.p_rout.value()
        total = self.p_len.value()
        try:
            res = compute_length_case(r_in, r_out, total, self.paper_delta())
        except ValueError as exc:
            self.p_value.setText("—")
            self.p_sub.setText("")
            self.p_error.setText(f"参数有误：{exc}")
            self.p_preview.set_values(r_in, r_out, r_in, 0.0)
            return
        self.p_error.setText("")
        self.p_value.setText(fmt(res["rem_len"], 1))
        self.p_sub.setText(
            f"剩余外半径 {res['r_now']:.2f} mm　·　已消耗 {fmt(res['used_len'], 1)} m"
            f"　·　推算纸厚 {res['wall']:.4f} mm"
        )
        self.p_preview.set_values(r_in, r_out, res["r_now"],
                                  res["rem_ratio"] * 100.0)

    def calc_paper_and_save(self) -> None:
        self.recalc_paper()
        if self.p_error.text():
            return
        self.save_inputs()
        self.status.setText(
            f"卷烟纸：剩余 {self.p_value.text()} m（仅显示）；输入参数已保存为下次默认值"
        )

    # ------------------------------------------------------------- 水松纸卡片
    def build_tip_card(self) -> QWidget:
        card = QGroupBox("水松纸（按重量计算）")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(10)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)

        self.t_rin = make_spin(2, 1000, DEFAULTS["tip/rin"], 2, 1.0)
        self.t_rout = make_spin(5, 2000, DEFAULTS["tip/rout"], 2, 1.0)
        self.t_weight = make_spin(0.001, 5000.0, DEFAULTS["tip/weight"], 3, 0.1)
        self.t_mode = QComboBox()
        self.t_mode.addItems(["按半径差 Δr", "按消耗后外半径"])
        self.t_mode.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.t_mode.setMinimumWidth(110)
        self.t_delta = make_spin(0, 2000, DEFAULTS["tip/delta"], 2, 1.0)
        self.t_rnow = make_spin(2, 2000, DEFAULTS["tip/rin"] + DEFAULTS["tip/delta"], 2, 1.0)
        self.t_rnow.setEnabled(False)

        self.t_delta.setToolTip("消耗后纸盘剩余纸层的半径差：剩余外半径 − 内半径")
        self.t_rnow.setToolTip("卡尺实测的消耗后纸盘外半径")
        self.t_weight.setToolTip("整盘水松纸的总重量，可修改（如 5.7 kg）")

        grid_row(grid, 0, "内半径 r", self.t_rin, "mm")
        grid_row(grid, 1, "外半径 R", self.t_rout, "mm")
        grid_row(grid, 2, "盘纸重量 W", self.t_weight, "kg")
        grid_row(grid, 3, "消耗参数", self.t_mode)
        grid_row(grid, 4, "半径差 Δr", self.t_delta, "mm")
        grid_row(grid, 5, "消耗后外半径 R′", self.t_rnow, "mm")
        left.addLayout(grid)

        self.t_calc_btn = QPushButton("计 算")
        self.t_calc_btn.clicked.connect(self.calc_tip_and_save)
        left.addWidget(self.t_calc_btn)

        self.t_error = QLabel("")
        self.t_error.setObjectName("error")
        self.t_error.setWordWrap(True)
        left.addWidget(self.t_error)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(6)
        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        pf = QVBoxLayout(preview_frame)
        pf.setContentsMargins(6, 6, 6, 6)
        self.t_preview = RollPreview(QColor(246, 145, 32))
        pf.addWidget(self.t_preview)
        legend = QLabel("半透明橙：剩余纸层　虚线：原始外半径")
        legend.setObjectName("caption")
        legend.setAlignment(Qt.AlignCenter)
        legend.setWordWrap(True)
        right.addWidget(preview_frame, 1)
        right.addWidget(legend)

        main_row.addLayout(left, 1)
        main_row.addLayout(right, 0)
        layout.addLayout(main_row)

        result_frame = QFrame()
        result_frame.setObjectName("resultFrame")
        rf = QVBoxLayout(result_frame)
        rf.setContentsMargins(14, 10, 14, 10)
        rf.setSpacing(4)
        top = QLabel("剩余水松纸重量（不保存，仅显示）")
        top.setObjectName("caption")
        value_row = QHBoxLayout()
        self.t_value = QLabel("—")
        self.t_value.setStyleSheet("font-size:30px; font-weight:700; color:#b35c00;")
        unit = QLabel("kg")
        unit.setStyleSheet("font-size:15px; color:#4b5568; padding-top:9px;")
        value_row.addWidget(self.t_value)
        value_row.addWidget(unit)
        value_row.addStretch(1)
        self.t_sub = QLabel("")
        self.t_sub.setObjectName("caption")
        self.t_sub.setWordWrap(True)
        rf.addWidget(top)
        rf.addLayout(value_row)
        rf.addWidget(self.t_sub)
        layout.addWidget(result_frame)
        layout.addStretch(1)

        for spin_box in (self.t_rin, self.t_rout, self.t_weight,
                         self.t_delta, self.t_rnow):
            spin_box.valueChanged.connect(self.recalc_tip)
        self.t_mode.currentIndexChanged.connect(self.recalc_tip)
        return card

    def tip_delta(self) -> float:
        if self.t_mode.currentIndex() == 0:
            return self.t_delta.value()
        return self.t_rnow.value() - self.t_rin.value()

    def recalc_tip(self, *_):
        self.t_delta.setEnabled(self.t_mode.currentIndex() == 0)
        self.t_rnow.setEnabled(self.t_mode.currentIndex() == 1)
        r_in = self.t_rin.value()
        r_out = self.t_rout.value()
        weight = self.t_weight.value()
        try:
            res = compute_weight_case(r_in, r_out, weight, self.tip_delta())
        except ValueError as exc:
            self.t_value.setText("—")
            self.t_sub.setText("")
            self.t_error.setText(f"参数有误：{exc}")
            self.t_preview.set_values(r_in, r_out, r_in, 0.0)
            return
        self.t_error.setText("")
        self.t_value.setText(fmt(res["rem_weight"], 3))
        self.t_sub.setText(
            f"剩余外半径 {res['r_now']:.2f} mm　·　已消耗 {fmt(res['used_weight'], 3)} kg"
        )
        self.t_preview.set_values(r_in, r_out, res["r_now"],
                                  res["rem_ratio"] * 100.0)

    def calc_tip_and_save(self) -> None:
        self.recalc_tip()
        if self.t_error.text():
            return
        self.save_inputs()
        self.status.setText(
            f"水松纸：剩余 {self.t_value.text()} kg（仅显示）；输入参数已保存为下次默认值"
        )

    # ------------------------------------------------------------- 配置读写
    def _input_widgets(self) -> dict:
        return {
            "paper/rin": self.p_rin,
            "paper/rout": self.p_rout,
            "paper/len": self.p_len,
            "tip/rin": self.t_rin,
            "tip/rout": self.t_rout,
            "tip/weight": self.t_weight,
        }

    def load_inputs(self) -> None:
        settings = QSettings(CONFIG_PATH, QSettings.IniFormat)
        restored = settings.contains("paper/rin")
        for key, widget in self._input_widgets().items():
            try:
                value = float(settings.value(key, DEFAULTS[key]))
            except (TypeError, ValueError):
                value = DEFAULTS[key]
            widget.setValue(value)

        # 防御：保存的几何参数异常时回退为内置默认值
        if self.p_rin.value() >= self.p_rout.value():
            self.p_rin.setValue(DEFAULTS["paper/rin"])
            self.p_rout.setValue(DEFAULTS["paper/rout"])
        if self.t_rin.value() >= self.t_rout.value():
            self.t_rin.setValue(DEFAULTS["tip/rin"])
            self.t_rout.setValue(DEFAULTS["tip/rout"])

        # 消耗参数不参与保存，每次启动使用内置默认值
        self.p_delta.setValue(DEFAULTS["paper/delta"])
        self.t_delta.setValue(DEFAULTS["tip/delta"])
        self.p_mode.setCurrentIndex(0)
        self.t_mode.setCurrentIndex(0)

        if restored:
            self.status.setText("已载入上次保存的输入参数（差值未保存，使用默认值）")
        else:
            self.status.setText("首次使用：当前为内置默认值，计算后自动保存输入参数")

    def save_inputs(self) -> None:
        settings = QSettings(CONFIG_PATH, QSettings.IniFormat)
        for key, widget in self._input_widgets().items():
            settings.setValue(key, widget.value())
        # 半径差、输入方式与计算结果均不落盘
        settings.sync()

    def reset_defaults(self) -> None:
        for key, widget in self._input_widgets().items():
            widget.setValue(DEFAULTS[key])
        self.p_mode.setCurrentIndex(0)
        self.t_mode.setCurrentIndex(0)
        self.p_delta.setValue(DEFAULTS["paper/delta"])
        self.t_delta.setValue(DEFAULTS["tip/delta"])
        settings = QSettings(CONFIG_PATH, QSettings.IniFormat)
        settings.clear()
        settings.sync()
        self.recalc_paper()
        self.recalc_tip()
        self.status.setText("已恢复内置默认值（保存的参数已清除）")

    def closeEvent(self, event):
        self.save_inputs()
        super().closeEvent(event)


def main() -> None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = CalcWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        def _finish():
            window.grab().save(os.path.join(
                os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                else os.getcwd(),
                "smoke_test.png",
            ))
            app.quit()
        QTimer.singleShot(120, _finish)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
