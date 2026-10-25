#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘纸余量计算 —— 纯计算内核（不依赖 Kivy / Qt，方便单测与复用）。

单位约定：半径 mm，长度 m，重量 kg。
"""

from __future__ import annotations

import math

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

# 需要持久化的输入项（半径、长度、重量）；半径差与计算结果均不保存
SAVED_KEYS = (
    "paper/rin", "paper/rout", "paper/len",
    "tip/rin", "tip/rout", "tip/weight",
)


def wall_from_length(r_in, r_out, total_length_m):
    """由内外半径与盘纸总长反推单层纸厚 (mm)。"""
    if r_out <= r_in:
        raise ValueError("外半径必须大于内半径")
    if total_length_m <= 0:
        raise ValueError("盘纸长度必须大于 0")
    return math.pi * (r_out ** 2 - r_in ** 2) / (total_length_m * 1000.0)


def length_from_radii(r_in, r_out, wall_mm):
    """已知内外半径与单层纸厚，求纸长 (m)。"""
    if r_out <= r_in:
        raise ValueError("外半径必须大于内半径")
    if wall_mm <= 0:
        raise ValueError("单层纸厚必须大于 0")
    return math.pi * (r_out ** 2 - r_in ** 2) / wall_mm / 1000.0


def checked_delta(r_in, r_out, delta_r_mm):
    """校验消耗后半径差并返回限幅后的值。"""
    if r_out <= r_in:
        raise ValueError("外半径必须大于内半径")
    full = r_out - r_in
    if delta_r_mm < -1e-9:
        raise ValueError("消耗后半径差不能为负数")
    if delta_r_mm > full + 1e-6:
        raise ValueError(f"消耗后半径差不能超过原始半径差 {full:.2f} mm")
    return min(max(delta_r_mm, 0.0), full)


def compute_length_case(r_in, r_out, total_length_m, delta_r_mm):
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


def compute_weight_case(r_in, r_out, total_weight_kg, delta_r_mm):
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


def fmt(value, digits=1):
    return f"{value:,.{digits}f}"