# -*- coding: utf-8 -*-
"""
PHẦN MỀM TÍNH TOÁN THỦY VĂN - THỦY LỰC CẦU NHỎ
TIÊU CHUẨN TCVN 9845:2013 & 22 TCN 220-95
Phiên bản: V5.1 (Đã chuẩn hóa dữ liệu bảng tra, liên kết nhám và xuất báo cáo)
"""

import os, csv, math, statistics, re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from scipy.stats import pearson3, gumbel_r
    SCIPY_OK = True
except Exception:
    SCIPY_OK = False

# ============================================================
# 1. DỮ LIỆU BẢNG TRA ĐÃ CHUẨN HÓA VÀ NHÚNG TRỰC TIẾP
# ============================================================

A1 = {
    'F': [0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.5, 1, 3, 6, 10, 50, 100],
    'rows': [
        ('II', 0.0, [0.96, 0.94, 0.93, 0.9, 0.88, 0.85, 0.81, 0.78, 0.76, 0.74, 0.67, 0.65, 0.6]),
        ('II', 101.0, [0.97, 0.96, 0.94, 0.91, 0.9, 0.87, 0.85, 0.78, 0.76, 0.74, 0.67, 0.65, 0.6]),
        ('II', 151.0, [0.97, 0.96, 0.95, 0.93, 0.92, 0.9, 0.89, 0.85, 0.83, 0.81, 0.75, 0.73, 0.7]),
        ('II', 201.0, [0.97, 0.96, 0.96, 0.95, 0.94, 0.93, 0.92, 0.89, 0.89, 0.85, 0.85, 0.85, 0.85]),
        ('II', 251.0, [0.97, 0.96, 0.96, 0.96, 0.95, 0.95, 0.94, 0.93, 0.93, 0.88, 0.88, 0.88, 0.86]),
        ('II', 301.0, [0.97, 0.96, 0.96, 0.96, 0.95, 0.95, 0.95, 0.93, 0.93, 0.91, 0.91, 0.91, 0.91]),
        ('II', 401.0, [0.97, 0.96, 0.96, 0.96, 0.95, 0.95, 0.95, 0.93, 0.93, 0.91, 0.91, 0.91, 0.91]),
        ('III', 0.0, [0.94, 0.89, 0.86, 0.8, 0.77, 0.74, 0.65, 0.6, 0.58, 0.55, 0.53, 0.53, 0.5]),
        ('III', 101.0, [0.95, 0.93, 0.9, 0.85, 0.81, 0.77, 0.72, 0.63, 0.62, 0.6, 0.55, 0.55, 0.55]),
        ('III', 151.0, [0.95, 0.93, 0.91, 0.88, 0.86, 0.82, 0.79, 0.72, 0.68, 0.68, 0.63, 0.63, 0.62]),
        ('III', 201.0, [0.95, 0.93, 0.92, 0.91, 0.9, 0.85, 0.85, 0.75, 0.72, 0.73, 0.73, 0.73, 0.65]),
        ('III', 251.0, [0.95, 0.93, 0.921, 0.91, 0.9, 0.85, 0.85, 0.77, 0.74, 0.74, 0.69, 0.69, 0.67]),
        ('III', 301.0, [0.95, 0.93, 0.921, 0.912, 0.9, 0.855, 0.87, 0.78, 0.76, 0.75, 0.71, 0.71, 0.69]),
        ('III', 351.0, [0.95, 0.93, 0.922, 0.912, 0.902, 0.88, 0.89, 0.79, 0.77, 0.77, 0.73, 0.73, 0.7]),
        ('III', 401.0, [0.95, 0.93, 0.922, 0.913, 0.902, 0.885, 0.895, 0.8, 0.79, 0.78, 0.75, 0.75, 0.71]),
        ('III', 451.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.79, 0.75, 0.75, 0.71]),
        ('III', 501.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.8, 0.76, 0.76, 0.71]),
        ('III', 551.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.8, 0.76, 0.76, 0.71]),
        ('III', 601.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.8, 0.76, 0.76, 0.71]),
        ('IV', 0.0, [0.9, 0.81, 0.76, 0.66, 0.65, 0.6, 0.55, 0.51, 0.5, 0.5, 0.44, 0.4, 0.37]),
        ('IV', 101.0, [0.9, 0.84, 0.8, 0.76, 0.68, 0.64, 0.62, 0.58, 0.56, 0.55, 0.52, 0.5, 0.46]),
        ('IV', 151.0, [0.9, 0.88, 0.85, 0.82, 0.78, 0.75, 0.72, 0.66, 0.63, 0.6, 0.6, 0.57, 0.55]),
        ('IV', 201.0, [0.9, 0.88, 0.822, 0.823, 0.79, 0.78, 0.74, 0.7, 0.67, 0.67, 0.65, 0.6, 0.58]),
        ('IV', 251.0, [0.9, 0.88, 0.822, 0.825, 0.79, 0.79, 0.76, 0.74, 0.7, 0.7, 0.69, 0.65, 0.61]),
        ('IV', 301.0, [0.9, 0.88, 0.828, 0.828, 0.8, 0.8, 0.78, 0.76, 0.72, 0.71, 0.71, 0.67, 0.64]),
        ('IV', 351.0, [0.9, 0.88, 0.828, 0.83, 0.82, 0.82, 0.81, 0.77, 0.74, 0.73, 0.72, 0.69, 0.65]),
        ('IV', 401.0, [0.9, 0.88, 0.86, 0.84, 0.84, 0.84, 0.83, 0.77, 0.75, 0.75, 0.73, 0.71, 0.67]),
        ('IV', 451.0, [0.9, 0.88, 0.86, 0.85, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.68]),
        ('IV', 501.0, [0.9, 0.88, 0.87, 0.86, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.69]),
        ('IV', 551.0, [0.9, 0.88, 0.87, 0.86, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.69]),
        ('IV', 601.0, [0.9, 0.88, 0.87, 0.86, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.69]),
        ('V', 0.0, [0.68, 0.46, 0.35, 0.26, 0.24, 0.22, 0.22, 0.2, 0.18, 0.18, 0.17, 0.16, 0.15]),
        ('V', 101.0, [0.71, 0.56, 0.46, 0.41, 0.4, 0.34, 0.32, 0.28, 0.27, 0.25, 0.23, 0.22, 0.2]),
        ('V', 151.0, [0.75, 0.65, 0.59, 0.5, 0.48, 0.46, 0.46, 0.42, 0.45, 0.38, 0.34, 0.32, 0.3]),
        ('V', 201.0, [0.76, 0.68, 0.63, 0.543, 0.5, 0.5, 0.5, 0.46, 0.49, 0.43, 0.38, 0.36, 0.34]),
        ('V', 251.0, [0.77, 0.71, 0.66, 0.58, 0.58, 0.54, 0.54, 0.49, 0.51, 0.46, 0.41, 0.4, 0.36]),
        ('V', 301.0, [0.77, 0.73, 0.66, 0.58, 0.58, 0.54, 0.56, 0.49, 0.54, 0.46, 0.41, 0.43, 0.37]),
        ('V', 351.0, [0.78, 0.75, 0.7, 0.65, 0.64, 0.57, 0.57, 0.53, 0.55, 0.52, 0.46, 0.46, 0.4]),
        ('V', 401.0, [0.79, 0.76, 0.72, 0.67, 0.67, 0.58, 0.58, 0.54, 0.55, 0.53, 0.47, 0.47, 0.41]),
        ('V', 451.0, [0.79, 0.77, 0.73, 0.68, 0.68, 0.6, 0.6, 0.55, 0.55, 0.53, 0.48, 0.48, 0.41]),
        ('V', 501.0, [0.79, 0.78, 0.73, 0.7, 0.7, 0.6, 0.6, 0.55, 0.55, 0.53, 0.49, 0.5, 0.41]),
        ('V', 551.0, [0.79, 0.78, 0.73, 0.7, 0.7, 0.6, 0.6, 0.55, 0.55, 0.53, 0.5, 0.5, 0.41]),
        ('V', 601.0, [0.79, 0.78, 0.73, 0.7, 0.7, 0.6, 0.6, 0.55, 0.55, 0.53, 0.5, 0.5, 0.41])
    ]
}

A2 = {
    'phi': [1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 17, 20, 25, 30, 35, 40],
    'regions': {
        'I':    [9.6, 10, 17, 24, 35, 40, 53, 62, 70, 75, 80, 90, 100, 130, 160, 200, 260, 325, 370, 470],
        'II':   [9.7, 10, 15, 22, 28, 37, 45, 60, 70, 78, 87, 95, 115, 150, 165, 220, 280, 360, 430, 530],
        'III':  [9.7, 10, 17, 20, 25, 32, 50, 60, 72, 80, 90, 100, 120, 150, 180, 230, 265, 365, 435, 520],
        'IV':   [9.0, 9.0, 9.5, 10, 18, 22, 30, 45, 60, 68, 80, 86, 95, 120, 165, 200, 235, 320, 400, 470],
        'V':    [9.6, 10, 14, 20, 30, 35, 44, 60, 75, 85, 90, 95, 100, 120, 170, 200, 260, 320, 370, 480],
        'VI':   [9.6, 10, 10, 15, 22, 30, 38, 50, 70, 78, 82, 88, 93, 120, 150, 185, 230, 310, 370, 470],
        'VII':  [16.0, 18, 25, 32, 37, 42, 50, 55, 65, 75, 85, 90, 100, 125, 165, 205, 250, 320, 400, 570],
        'VIII': [8.4, 8.5, 9.0, 10, 20, 30, 40, 55, 65, 70, 80, 90, 115, 135, 190, 235, 305, 370, 480, 495],
        'IX':   [9.7, 10, 13, 15, 18, 25, 30, 40, 65, 70, 80, 95, 115, 135, 170, 220, 290, 370, 430, 520],
        'X':    [9.8, 10, 15, 18, 25, 40, 45, 60, 75, 85, 90, 95, 110, 135, 170, 220, 265, 335, 345, 410],
        'XI':   [9.5, 10, 20, 28, 35, 55, 65, 72, 80, 90, 95, 110, 130, 160, 200, 230, 300, 400, 470, 560],
        'XII':  [10.0, 13, 20, 23, 30, 35, 50, 60, 75, 80, 87, 105, 120, 150, 190, 235, 300, 380, 450, 540],
        'XIII': [9.8, 10, 15, 20, 25, 30, 40, 55, 65, 70, 82, 90, 100, 125, 160, 200, 250, 330, 400, 510],
        'XIV':  [8.7, 9.0, 9.3, 9.5, 11, 20, 30, 35, 50, 70, 80, 85, 90, 115, 160, 200, 250, 320, 400, 480],
        'XV':   [8.5, 8.7, 9.3, 9.5, 10, 20, 25, 32, 50, 65, 70, 80, 90, 125, 150, 190, 250, 320, 400, 490],
        'XVI':  [8.7, 9.0, 9.5, 9.6, 12, 20, 30, 37, 50, 65, 78, 80, 90, 115, 140, 175, 225, 285, 355, 425],
        'XVII': [9.3, 9.4, 9.7, 10, 20, 25, 35, 40, 60, 70, 80, 90, 97, 120, 145, 190, 240, 320, 380, 465],
        'XVIII':[9.2, 9.3, 9.5, 9.7, 12, 20, 23, 30, 40, 60, 70, 80, 83, 100, 130, 165, 230, 300, 370, 450] # Sửa None thành 450 (ngoại suy)
    }
}

# Đã sửa các lỗi gõ số thập phân OCR: 0.816->0.0816, 0.461->0.0461, 0.0106->0.106, 0.0149->0.149, lỗi Vùng XVIII...
A3 = {
    'phi_ls': [0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 150, 200, 220],
    'regions': {
        'I': [
            (20, [0.28, 0.26, 0.218, 0.152, 0.112, 0.092, 0.076, 0.064, 0.054, 0.047, 0.04, 0.035, 0.03, 0.018, 0.015, 0.013]),
            (30, [0.21, 0.19, 0.16, 0.136, 0.104, 0.085, 0.072, 0.061, 0.052, 0.045, 0.038, 0.033, 0.029, 0.017, 0.014, 0.0125]),
            (60, [0.15, 0.143, 0.125, 0.111, 0.091, 0.076, 0.065, 0.055, 0.047, 0.04, 0.034, 0.03, 0.026, 0.016, 0.013, 0.012]),
            (90, [0.114, 0.112, 0.102, 0.093, 0.077, 0.065, 0.056, 0.048, 0.041, 0.035, 0.031, 0.027, 0.024, 0.015, 0.012, 0.0115]),
            (180, [0.072, 0.071, 0.057, 0.063, 0.055, 0.048, 0.043, 0.037, 0.033, 0.029, 0.025, 0.022, 0.021, 0.014, 0.0115, 0.011])
        ],
        'II': [
            (20, [0.117, 0.114, 0.104, 0.093, 0.087, 0.065, 0.055, 0.047, 0.04, 0.034, 0.03, 0.026, 0.024, 0.018, 0.015, 0.014]),
            (30, [0.1, 0.098, 0.091, 0.083, 0.07, 0.06, 0.052, 0.044, 0.038, 0.033, 0.028, 0.025, 0.023, 0.0175, 0.014, 0.013]),
            (60, [0.082, 0.081, 0.076, 0.07, 0.06, 0.052, 0.045, 0.039, 0.034, 0.03, 0.027, 0.024, 0.022, 0.016, 0.013, 0.0125]),
            (90, [0.067, 0.066, 0.063, 0.059, 0.052, 0.046, 0.04, 0.035, 0.031, 0.027, 0.025, 0.022, 0.02, 0.015, 0.012, 0.012]),
            (180, [0.052, 0.051, 0.048, 0.046, 0.041, 0.036, 0.032, 0.028, 0.025, 0.022, 0.02, 0.018, 0.017, 0.014, 0.011, 0.011])
        ],
        'III': [
            (20, [0.159, 0.153, 0.137, 0.112, 0.0985, 0.0831, 0.0708, 0.0618, 0.0544, 0.0492, 0.045, 0.041, 0.0378, 0.0281, 0.0218, 0.0183]),
            (30, [0.132, 0.129, 0.116, 0.104, 0.0866, 0.074, 0.065, 0.0573, 0.0507, 0.0462, 0.042, 0.039, 0.0358, 0.0272, 0.0211, 0.018]),
            (60, [0.095, 0.092, 0.087, 0.079, 0.0695, 0.0611, 0.053, 0.0497, 0.0447, 0.041, 0.038, 0.035, 0.0325, 0.0252, 0.0197, 0.017]),
            (90, [0.073, 0.068, 0.0659, 0.0612, 0.0549, 0.05, 0.0443, 0.0414, 0.0384, 0.0355, 0.033, 0.0307, 0.0292, 0.0228, 0.0185, 0.016]),
            (180, [0.058, 0.054, 0.0517, 0.049, 0.045, 0.042, 0.0383, 0.036, 0.033, 0.0303, 0.03, 0.0268, 0.0256, 0.0205, 0.0165, 0.015])
        ],
        'IV': [
            (20, [0.273, 0.214, 0.188, 0.163, 0.128, 0.104, 0.0865, 0.0743, 0.0654, 0.0565, 0.0499, 0.0448, 0.0408, 0.0279, 0.0216, 0.0184]),
            (30, [0.2, 0.184, 0.163, 0.142, 0.1153, 0.095, 0.0816, 0.0703, 0.0615, 0.0545, 0.0479, 0.0429, 0.039, 0.0269, 0.0212, 0.0182]),
            (60, [0.129, 0.124, 0.117, 0.107, 0.0903, 0.079, 0.0688, 0.0593, 0.0553, 0.0473, 0.0427, 0.0382, 0.0351, 0.0256, 0.02, 0.0174]),
            (90, [0.102, 0.093, 0.089, 0.084, 0.0735, 0.0645, 0.0579, 0.0508, 0.046, 0.041, 0.037, 0.034, 0.0315, 0.023, 0.0189, 0.0164]),
            (180, [0.072, 0.071, 0.067, 0.063, 0.0555, 0.0503, 0.0456, 0.0413, 0.0378, 0.0328, 0.0315, 0.031, 0.0275, 0.021, 0.0178, 0.0155])
        ],
        'V': [
            (20, [0.12, 0.1185, 0.1115, 0.1087, 0.094, 0.0786, 0.069, 0.063, 0.0525, 0.0457, 0.0397, 0.0347, 0.0304, 0.0195, 0.014, 0.013]),
            (30, [0.112, 0.11, 0.1035, 0.0965, 0.084, 0.0733, 0.0638, 0.056, 0.0485, 0.0423, 0.037, 0.032, 0.028, 0.0169, 0.0133, 0.0124]),
            (60, [0.098, 0.0965, 0.0855, 0.0815, 0.0748, 0.0655, 0.0577, 0.0506, 0.0445, 0.0393, 0.0345, 0.0304, 0.0268, 0.0163, 0.0126, 0.0119]),
            (90, [0.083, 0.0817, 0.0775, 0.0726, 0.0642, 0.0565, 0.05, 0.0443, 0.039, 0.0345, 0.031, 0.0276, 0.0247, 0.0152, 0.0118, 0.0114]),
            (180, [0.0595, 0.0587, 0.056, 0.0583, 0.048, 0.043, 0.039, 0.035, 0.0317, 0.0285, 0.0263, 0.024, 0.0223, 0.0148, 0.011, 0.0108])
        ],
        'VI': [
            (20, [0.1215, 0.1195, 0.113, 0.1053, 0.0916, 0.0803, 0.0703, 0.0617, 0.0543, 0.0478, 0.0417, 0.0377, 0.0324, 0.0195, 0.015, 0.014]),
            (30, [0.1135, 0.1117, 0.106, 0.087, 0.0865, 0.0757, 0.0666, 0.0585, 0.0515, 0.0452, 0.0397, 0.035, 0.031, 0.0189, 0.0145, 0.0135]),
            (60, [0.105, 0.0995, 0.0944, 0.086, 0.0798, 0.0686, 0.0606, 0.0536, 0.0474, 0.042, 0.0373, 0.0333, 0.0295, 0.0183, 0.014, 0.0129]),
            (90, [0.0863, 0.0858, 0.0816, 0.077, 0.069, 0.0617, 0.0553, 0.049, 0.044, 0.039, 0.035, 0.031, 0.0278, 0.0172, 0.0135, 0.0124]),
            (180, [0.0645, 0.0637, 0.061, 0.058, 0.0513, 0.0457, 0.0407, 0.0363, 0.0323, 0.0292, 0.0265, 0.0242, 0.0222, 0.0167, 0.013, 0.012])
        ],
        'VII': [
            (20, [0.106, 0.105, 0.1, 0.0934, 0.0817, 0.0716, 0.0633, 0.0555, 0.049, 0.043, 0.0382, 0.0337, 0.03, 0.019, 0.015, 0.0133]),
            (30, [0.097, 0.096, 0.091, 0.0786, 0.0763, 0.0677, 0.0603, 0.0534, 0.0474, 0.0417, 0.037, 0.0327, 0.029, 0.0181, 0.0142, 0.0129]),
            (60, [0.085, 0.084, 0.08, 0.0757, 0.0676, 0.0606, 0.054, 0.0482, 0.043, 0.038, 0.034, 0.0303, 0.0272, 0.0175, 0.0135, 0.0125]),
            (90, [0.071, 0.07, 0.067, 0.0632, 0.0565, 0.0506, 0.0455, 0.0407, 0.04, 0.033, 0.0298, 0.0271, 0.0247, 0.0168, 0.0127, 0.0117]),
            (180, [0.057, 0.056, 0.054, 0.051, 0.046, 0.0408, 0.0365, 0.0326, 0.0293, 0.0265, 0.0238, 0.0218, 0.02, 0.016, 0.0121, 0.011])
        ],
        'VIII': [
            (20, [0.162, 0.156, 0.136, 0.121, 0.0963, 0.0805, 0.0676, 0.0572, 0.0483, 0.0422, 0.0375, 0.0334, 0.0298, 0.024, 0.017, 0.016]),
            (30, [0.146, 0.142, 0.127, 0.112, 0.0905, 0.076, 0.0645, 0.055, 0.0477, 0.0416, 0.0366, 0.0327, 0.0292, 0.0225, 0.016, 0.015]),
            (60, [0.119, 0.116, 0.104, 0.0933, 0.0773, 0.0656, 0.056, 0.0486, 0.0435, 0.0386, 0.0345, 0.0309, 0.028, 0.021, 0.015, 0.014]),
            (90, [0.101, 0.0987, 0.091, 0.0824, 0.0693, 0.0593, 0.0513, 0.0445, 0.0394, 0.0352, 0.032, 0.0293, 0.0265, 0.019, 0.014, 0.013]),
            (180, [0.062, 0.0615, 0.0587, 0.055, 0.05, 0.045, 0.0403, 0.0365, 0.033, 0.03, 0.0275, 0.0253, 0.0235, 0.0173, 0.013, 0.012])
        ],
        'IX': [
            (20, [0.1923, 0.1825, 0.157, 0.143, 0.1152, 0.0956, 0.081, 0.0705, 0.0616, 0.0549, 0.0489, 0.0443, 0.0407, 0.029, 0.022, 0.02]),
            (30, [0.1912, 0.1555, 0.1395, 0.1233, 0.103, 0.0868, 0.0762, 0.0663, 0.0587, 0.0527, 0.0469, 0.0425, 0.039, 0.0279, 0.021, 0.019]),
            (60, [0.1095, 0.105, 0.1015, 0.0931, 0.0811, 0.0724, 0.0642, 0.0563, 0.0534, 0.0463, 0.0425, 0.0385, 0.0355, 0.0262, 0.02, 0.0178]),
            (90, [0.0905, 0.082, 0.08, 0.0756, 0.074, 0.0607, 0.0553, 0.0493, 0.0452, 0.0407, 0.0372, 0.0345, 0.0322, 0.0233, 0.019, 0.0165]),
            (180, [0.064, 0.0635, 0.061, 0.0572, 0.051, 0.0468, 0.0433, 0.0396, 0.0367, 0.0336, 0.0317, 0.03, 0.028, 0.022, 0.0178, 0.0155])
        ],
        'X': [
            (20, [0.0946, 0.0932, 0.0887, 0.0833, 0.0733, 0.0645, 0.0568, 0.05, 0.0443, 0.0388, 0.0345, 0.0305, 0.0277, 0.02, 0.015, 0.013]),
            (30, [0.0893, 0.088, 0.0836, 0.0788, 0.069, 0.0608, 0.0537, 0.0473, 0.0417, 0.037, 0.033, 0.0293, 0.0263, 0.0192, 0.0145, 0.0128]),
            (60, [0.0806, 0.0796, 0.0757, 0.071, 0.0628, 0.0555, 0.0487, 0.0433, 0.0383, 0.034, 0.0303, 0.027, 0.0246, 0.0183, 0.014, 0.0125]),
            (90, [0.0717, 0.0707, 0.067, 0.0635, 0.0557, 0.0495, 0.0437, 0.0387, 0.0346, 0.0307, 0.0277, 0.0253, 0.023, 0.0179, 0.0135, 0.0122]),
            (180, [0.0525, 0.052, 0.05, 0.0472, 0.0425, 0.0382, 0.0435, 0.0313, 0.0283, 0.0262, 0.0243, 0.0242, 0.0216, 0.0173, 0.013, 0.0115])
        ],
        'XI': [
            (20, [0.0888, 0.0862, 0.08, 0.0714, 0.0607, 0.0524, 0.0461, 0.0406, 0.0364, 0.033, 0.0304, 0.028, 0.0267, 0.0216, 0.0182, 0.0161]),
            (30, [0.0712, 0.0696, 0.0667, 0.0612, 0.0541, 0.0478, 0.043, 0.0385, 0.0348, 0.0317, 0.0294, 0.0273, 0.0258, 0.0211, 0.0176, 0.0157]),
            (60, [0.0631, 0.0615, 0.0582, 0.0542, 0.048, 0.0431, 0.0388, 0.036, 0.0315, 0.0286, 0.0268, 0.0251, 0.0234, 0.0196, 0.0164, 0.0149]),
            (90, [0.0518, 0.0508, 0.0479, 0.0459, 0.0403, 0.0364, 0.0327, 0.0304, 0.0283, 0.0261, 0.0255, 0.0233, 0.0222, 0.0185, 0.0157, 0.0143]),
            (180, [0.0431, 0.042, 0.0398, 0.0375, 0.0339, 0.0316, 0.0286, 0.0264, 0.0245, 0.023, 0.0218, 0.021, 0.0204, 0.0172, 0.0148, 0.0136])
        ],
        'XII': [
            (20, [0.09, 0.088, 0.0807, 0.0727, 0.06, 0.0503, 0.0423, 0.036, 0.0307, 0.027, 0.0242, 0.0225, 0.0218, 0.0185, 0.015, 0.0138]),
            (30, [0.079, 0.0755, 0.0705, 0.0647, 0.055, 0.0466, 0.0397, 0.0344, 0.0297, 0.026, 0.0237, 0.022, 0.0213, 0.0175, 0.0142, 0.0134]),
            (60, [0.0614, 0.0604, 0.0567, 0.0527, 0.0455, 0.0396, 0.0345, 0.0303, 0.027, 0.0244, 0.0224, 0.0214, 0.0208, 0.017, 0.0138, 0.0129]),
            (90, [0.052, 0.051, 0.0487, 0.046, 0.0406, 0.0357, 0.0317, 0.0283, 0.0253, 0.0232, 0.0217, 0.0205, 0.0197, 0.0165, 0.013, 0.0122]),
            (180, [0.041, 0.0404, 0.0387, 0.0365, 0.0327, 0.0295, 0.0265, 0.0243, 0.0222, 0.0207, 0.0197, 0.0188, 0.0185, 0.0153, 0.012, 0.0115])
        ],
        'XIII': [
            (20, [0.154, 0.149, 0.139, 0.105, 0.0901, 0.0763, 0.0658, 0.057, 0.0506, 0.0449, 0.0403, 0.0366, 0.0334, 0.0253, 0.0208, 0.0183]),
            (30, [0.129, 0.126, 0.112, 0.099, 0.0834, 0.0713, 0.0624, 0.0539, 0.0476, 0.0428, 0.0382, 0.035, 0.0319, 0.0241, 0.0198, 0.0177]),
            (60, [0.0975, 0.0954, 0.0878, 0.0808, 0.0694, 0.0611, 0.0534, 0.0477, 0.0427, 0.0383, 0.0315, 0.0319, 0.0294, 0.0227, 0.0185, 0.0168]),
            (90, [0.0756, 0.074, 0.0684, 0.0648, 0.0542, 0.0515, 0.0478, 0.0417, 0.0375, 0.0345, 0.0317, 0.0296, 0.0268, 0.0214, 0.0184, 0.016]),
            (180, [0.0543, 0.053, 0.0513, 0.0491, 0.0448, 0.0415, 0.0378, 0.0315, 0.032, 0.0297, 0.0278, 0.0257, 0.0246, 0.02, 0.0175, 0.0152])
        ],
        'XIV': [
            (20, [0.23, 0.215, 0.207, 0.175, 0.119, 0.0937, 0.0756, 0.0622, 0.0517, 0.0435, 0.037, 0.0315, 0.0273, 0.0185, 0.014, 0.012]),
            (30, [0.178, 0.171, 0.15, 0.131, 0.105, 0.0855, 0.0703, 0.0585, 0.0493, 0.0415, 0.0353, 0.0303, 0.0263, 0.0178, 0.0132, 0.0112]),
            (60, [0.137, 0.134, 0.122, 0.11, 0.092, 0.0757, 0.0633, 0.0533, 0.0437, 0.0383, 0.0326, 0.0284, 0.025, 0.017, 0.0125, 0.0103]),
            (90, [0.11, 0.107, 0.097, 0.09, 0.076, 0.0646, 0.0552, 0.0467, 0.0405, 0.035, 0.0305, 0.0266, 0.0236, 0.016, 0.0118, 0.0095]),
            (180, [0.086, 0.066, 0.063, 0.051, 0.053, 0.0464, 0.041, 0.0363, 0.0317, 0.028, 0.0247, 0.022, 0.0197, 0.014, 0.01, 0.0085])
        ],
        'XV': [
            (20, [0.261, 0.251, 0.233, 0.21, 0.153, 0.121, 0.0965, 0.0786, 0.0719, 0.063, 0.0508, 0.044, 0.0375, 0.0259, 0.0211, 0.0191]),
            (30, [0.225, 0.22, 0.191, 0.166, 0.133, 0.106, 0.0875, 0.073, 0.0632, 0.059, 0.0478, 0.042, 0.037, 0.0252, 0.0206, 0.0189]),
            (60, [0.158, 0.117, 0.136, 0.11, 0.099, 0.084, 0.0723, 0.062, 0.0548, 0.0485, 0.043, 0.039, 0.0354, 0.0234, 0.0195, 0.0181]),
            (90, [0.105, 0.103, 0.094, 0.087, 0.0755, 0.066, 0.059, 0.052, 0.0463, 0.0418, 0.0383, 0.0345, 0.0313, 0.0215, 0.0185, 0.0166]),
            (180, [0.074, 0.073, 0.0687, 0.064, 0.057, 0.0514, 0.0463, 0.0421, 0.0386, 0.035, 0.0321, 0.0295, 0.0274, 0.0202, 0.0172, 0.0155])
        ],
        'XVI': [
            (20, [0.3, 0.29, 0.249, 0.229, 0.184, 0.155, 0.129, 0.106, 0.09, 0.0768, 0.0674, 0.0593, 0.053, 0.0403, 0.0298, 0.0231]),
            (30, [0.252, 0.243, 0.215, 0.2, 0.166, 0.138, 0.114, 0.096, 0.082, 0.0717, 0.0627, 0.0555, 0.0507, 0.0368, 0.0287, 0.0227]),
            (60, [0.194, 0.189, 0.173, 0.155, 0.13, 0.11, 0.092, 0.079, 0.0692, 0.0617, 0.0552, 0.0493, 0.0445, 0.0324, 0.027, 0.0218]),
            (90, [0.148, 0.143, 0.13, 0.119, 0.099, 0.087, 0.074, 0.066, 0.059, 0.053, 0.0469, 0.0428, 0.0392, 0.029, 0.0242, 0.0205]),
            (180, [0.094, 0.092, 0.089, 0.081, 0.071, 0.063, 0.057, 0.052, 0.0473, 0.0433, 0.0397, 0.0357, 0.033, 0.0265, 0.0228, 0.0193])
        ],
        'XVII': [
            (20, [0.2, 0.19, 0.166, 0.146, 0.117, 0.096, 0.08, 0.068, 0.0575, 0.049, 0.042, 0.036, 0.0305, 0.016, 0.014, 0.0125]),
            (30, [0.18, 0.172, 0.154, 0.137, 0.112, 0.092, 0.077, 0.065, 0.056, 0.047, 0.04, 0.0345, 0.0295, 0.0155, 0.0135, 0.0122]),
            (60, [0.15, 0.147, 0.134, 0.121, 0.1, 0.084, 0.07, 0.0539, 0.05, 0.043, 0.037, 0.0315, 0.027, 0.015, 0.013, 0.0118]),
            (90, [0.13, 0.128, 0.127, 0.105, 0.086, 0.078, 0.062, 0.053, 0.0455, 0.0387, 0.0335, 0.0295, 0.025, 0.0145, 0.0125, 0.0115]),
            (180, [0.085, 0.084, 0.078, 0.072, 0.06, 0.051, 0.044, 0.0375, 0.0325, 0.029, 0.0262, 0.0235, 0.021, 0.014, 0.012, 0.011])
        ],
        'XVIII': [
            (20, [0.302, 0.276, 0.236, 0.221, 0.167, 0.139, 0.114, 0.0963, 0.0819, 0.0707, 0.0615, 0.0543, 0.0478, 0.0329, 0.0254, 0.0223]),
            (30, [0.236, 0.229, 0.202, 0.181, 0.15, 0.125, 0.105, 0.0978, 0.0765, 0.066, 0.058, 0.0513, 0.0433, 0.0312, 0.0246, 0.0213]),
            (60, [0.184, 0.179, 0.138, 0.142, 0.118, 0.1, 0.0857, 0.0746, 0.0647, 0.0567, 0.0505, 0.0541, 0.0409, 0.0285, 0.0228, 0.02]),
            (90, [0.129, 0.126, 0.114, 0.098, 0.088, 0.077, 0.067, 0.0596, 0.0534, 0.0477, 0.0431, 0.0396, 0.0357, 0.0264, 0.0213, 0.0182]),
            (180, [0.092, 0.089, 0.082, 0.075, 0.0652, 0.058, 0.0513, 0.0467, 0.0428, 0.039, 0.0357, 0.0326, 0.0303, 0.0232, 0.019, 0.0172])
        ]
    }
}

BRIDGE = {
    'm': [
        ('N.A Slovinski (Mố nhẹ)', 0.32),
        ('Mố tường cánh', 0.35),
        ('Mố chữ U', 0.34),
        ('Mố chân dê', 0.32)
    ],
    'b8': [
        (0.32, 1.42, 0.59, 0.45, 0.84, 2.56, 0.76, 0.58),
        (0.33, 1.46, 0.60, 0.47, 0.83, 2.35, 0.78, 0.62),
        (0.34, 1.50, 0.61, 0.49, 0.81, 2.05, 0.81, 0.65),
        (0.35, 1.55, 0.63, 0.52, 0.80, 1.85, 0.83, 0.68),
        (0.36, 1.60, 0.64, 0.54, 0.78, 1.64, 0.84, 0.71)
    ]
}

REGIONS = ["I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII","XIII","XIV","XV","XVI","XVII","XVIII"]
SOILS = ["II","III","IV","V"]

# Danh mục tra hệ số nhám sườn dốc m_sd (Bảng 4)
MSD_OPTIONS = [
    ("Đất trọc, sỏi đá, thực vật cằn cỗi (0.50)", 0.50),
    ("Cỏ mọc thưa, cây bụi thấp (0.35)", 0.35),
    ("Cỏ mọc trung bình, đất canh tác hoa màu (0.25)", 0.25),
    ("Cỏ mọc dày, đồi cây cối rậm rạp (0.15)", 0.15),
    ("Rừng nguyên sinh, rậm rạp nhiều tầng tán (0.10)", 0.10),
]

# Danh mục tra hệ số nhám lòng sông m_ls (Bảng 5)
MLS_OPTIONS = [
    ("Sông đồng bằng ổn định, lòng sông sạch, suối chảy thuận lợi (mls = 11)", 11.0),
    ("Sông lớn/trung bình, quanh co, có cỏ rác dạt bãi, mùa lũ cuốn sỏi cuội (mls = 9)", 9.0),
    ("Sông suối miền núi, lòng đá gồ ghề, quanh co, dòng chảy xiết cản trở (mls = 7)", 7.0),
    ("Suối vùng núi cao nhiều thác ghềnh, lòng lòng suối tắc nghẽn nặng (mls = 5)", 5.0)
]

# ============================================================
# 2. CÁC HÀM TÍNH TOÁN NỘI SUY VÀ THỐNG KÊ
# ============================================================

def num(v, name="Giá trị"):
    try:
        x = float(str(v).replace(",", ".").strip())
    except Exception:
        raise ValueError(f"{name} không phải số hợp lệ.")
    if not math.isfinite(x):
        raise ValueError(f"{name} không thể là vô cùng.")
    return x

def pos(v, name):
    x = num(v, name)
    if x <= 0:
        raise ValueError(f"{name} phải mang giá trị dương (> 0).")
    return x

def interp1(x, xs, ys):
    if x <= xs[0]: return float(ys[0])
    if x >= xs[-1]: return float(ys[-1])
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x1, x2 = xs[i-1], xs[i]
            y1, y2 = ys[i-1], ys[i]
            return y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return float(ys[-1])

def bilinear(x, y, xs, ys, z):
    x = max(min(float(x), float(xs[-1])), float(xs[0]))
    y = max(min(float(y), float(ys[-1])), float(ys[0]))

    def bracket(v, arr):
        if v <= arr[0]: return 0, 0
        if v >= arr[-1]: return len(arr)-1, len(arr)-1
        for i in range(1, len(arr)):
            if v <= arr[i]: return i-1, i
        return len(arr)-1, len(arr)-1

    j1, j2 = bracket(x, xs)
    i1, i2 = bracket(y, ys)

    if i1 == i2 and j1 == j2:
        return float(z[i1][j1])
    if i1 == i2:
        return interp1(x, xs, z[i1])
    if j1 == j2:
        return interp1(y, ys, [row[j1] for row in z])

    r1 = interp1(x, [xs[j1], xs[j2]], [z[i1][j1], z[i1][j2]])
    r2 = interp1(x, [xs[j1], xs[j2]], [z[i2][j1], z[i2][j2]])
    return interp1(y, [ys[i1], ys[i2]], [r1, r2])

def lookup_phi(soil, hp, F):
    rows = [r for r in A1["rows"] if r[0] == soil]
    if not rows:
        raise ValueError(f"Không có cấp đất {soil} trong Bảng A.1.")
    rows = sorted(rows, key=lambda x: x[1])
    ys = [r[1] for r in rows]
    z = [r[2] for r in rows]
    return bilinear(F, hp, A1["F"], ys, z)

def lookup_tsd(region, phi_sd):
    if region not in A2["regions"]:
        raise ValueError("Vùng mưa không hợp lệ trong Bảng A.2.")
    return interp1(phi_sd, A2["phi"], A2["regions"][region])

def lookup_ap(region, tsd, phi_ls):
    rows = A3["regions"][region]
    ts = [float(r[0]) for r in rows]
    z = [r[1] for r in rows]
    return bilinear(phi_ls, tsd, A3["phi_ls"], ts, z)

def rainfall_stats(values):
    x = []
    for v in values:
        try: q = float(v)
        except Exception: continue
        if math.isfinite(q) and q > 0: x.append(q)
    n = len(x)
    if n < 3:
        raise ValueError("Cần ít nhất 3 năm số liệu mưa cực trị để phân tích thống kê.")
    mean = sum(x) / n
    s = math.sqrt(sum((v - mean)**2 for v in x) / (n - 1))
    if s <= 0:
        raise ValueError("Độ lệch chuẩn S = 0, chuỗi lượng mưa không biến động.")
    cv = s / mean
    cs = (n / ((n - 1) * (n - 2))) * sum(((v - mean) / s)**3 for v in x)
    return {"n": n, "mean": mean, "std": s, "cv": cv, "cs": cs, "min": min(x), "max": max(x), "values": x}

def hp_pearson3(mean, cv, cs, p):
    if not SCIPY_OK:
        raise RuntimeError("Cần cài đặt scipy: pip install scipy")
    if not (0 < p < 100):
        raise ValueError("Tần suất P phải nằm trong khoảng (0; 100)%.")
    q = 1.0 - p / 100.0
    phi = float(pearson3.ppf(q, skew=float(cs)))
    kp = 1.0 + float(cv) * phi
    hp = float(mean) * kp
    if not math.isfinite(hp) or hp <= 0:
        raise ValueError(f"Không tính được Hp tại P={p:g}%. Vui lòng kiểm tra lại Cs/Cv.")
    return hp, kp, phi

def hp_gumbel(mean, cv, p):
    if not SCIPY_OK:
        raise RuntimeError("Cần thư viện scipy để tính Gumbel.")
    if not (0 < p < 100):
        raise ValueError("P phải nằm trong (0; 100)%.")
    s = float(cv) * float(mean)
    beta = s * math.sqrt(6) / math.pi
    loc = float(mean) - 0.5772156649 * beta
    hp = float(gumbel_r.ppf(1 - p/100.0, loc=loc, scale=beta))
    return hp, hp / mean

def empirical_frequency(values):
    vals = sorted([float(v) for v in values if float(v) > 0], reverse=True)
    n = len(vals)
    return [(i, vals[i-1], 100.0 * i / (n + 1.0)) for i in range(1, n+1)]

def calc_hydro(hp, p, F, L, suml, Jlv, Jsd, mls, msd, delta, soil, region, n_slope):
    if F >= 100:
        raise ValueError("Diện tích F >= 100 km²: Không thuộc phạm vi áp dụng công thức cường độ giới hạn TCVN 9845:2013.")
    phi = lookup_phi(soil, hp, F)
    c = 0.9 if n_slope == 1 else 1.8
    Lsd = 1000.0 * F / (c * (L + suml))
    phi_sd = (Lsd**0.6) / (msd * (Jsd**0.3) * ((phi * hp)**0.4))
    tsd = lookup_tsd(region, phi_sd)
    phi_ls = 1000.0 * L / (mls * (Jlv**(1.0/3.0)) * ((F * phi * hp)**0.25))
    Ap = lookup_ap(region, tsd, phi_ls)
    Q = Ap * phi * hp * F * delta
    return {
        "P": p, "Hp": hp, "F": F, "L": L, "suml": suml, "Jlv": Jlv, "Jsd": Jsd,
        "mls": mls, "msd": msd, "delta": delta, "soil": soil, "region": region,
        "n_slope": n_slope, "phi": phi, "Lsd": Lsd, "phi_sd": phi_sd,
        "tsd": tsd, "phi_ls": phi_ls, "Ap": Ap, "Qp": Q
    }

def bridge8(m):
    for row in BRIDGE["b8"]:
        if abs(float(row[0]) - m) < 1e-4:
            return {
                "m": float(row[0]), "k1": float(row[3]), "N": float(row[2]),
                "a": float(row[4]), "Y": float(row[5]), "Y2": float(row[7])
            }
    # Ngoại suy gần nhất
    row = min(BRIDGE["b8"], key=lambda r: abs(r[0] - m))
    return {
        "m": float(row[0]), "k1": float(row[3]), "N": float(row[2]),
        "a": float(row[4]), "Y": float(row[5]), "Y2": float(row[7])
    }

def calc_bridge_free(Q, m, h0, Vcp, Lnc):
    b = bridge8(m)
    sigma = 1.0
    # Cột nước tính toán H theo công thức thủy lực cầu nhỏ TCVN / 22TCN 220
    H = b["Y2"] * (Vcp**2) / (sigma * 9.81 * b["N"])
    Lc = Q / (sigma * m * (H**1.5) * math.sqrt(2 * 9.81))
    if Lnc is None or Lnc <= 0:
        Lnc = Lc
    H1 = H * ((Lc / Lnc)**(2.0 / 3.0))
    htt = b["k1"] * H1
    Vt = Q / (htt * Lnc)
    # Điều kiện chảy không ngập: h0 <= a * H1
    free_final = (h0 <= b["a"] * H1)
    vel_ok = (Vt <= Vcp)
    return {
        "m": m, "k1": b["k1"], "N": b["N"], "a": b["a"], "Y2": b["Y2"],
        "sigma": sigma, "H": H, "Lc": Lc, "Lnc": Lnc, "H1": H1, "htt": htt,
        "Vt": Vt, "Vcp": Vcp, "free_final": free_final, "vel_ok": vel_ok
    }

# ============================================================
# 3. GIAO DIỆN PHẦN MỀM (TKINTER GUI)
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TÍNH TOÁN THỦY VĂN & THỦY LỰC CẦU NHỎ | TCVN 9845:2013 | V5.1")
        self.geometry("1240x840")
        self.minsize(1050, 700)

        self.rain_stats = None
        self.hydro = None
        self.bridge = None

        self.vars = {}
        self._init_vars()
        self._apply_style()
        self._build_ui()

    def _init_vars(self):
        defaults = {
            "P": "4", "method": "Pearson III", "hp": "285.5", "region": "XII", "soil": "III",
            "F": "5.78", "L": "6.91", "suml": "1.39", "Jlv": "50", "Jsd": "95",
            "mls": "7.0", "msd": "0.25", "delta": "1.0", "n_slope": "2",
            "abutment": "Mố chữ U", "h0": "1.15", "Vcp": "4.0", "Lnc": "18.0",
            "use_hydro_Q": True, "custom_Q": "45.0"
        }
        for k, v in defaults.items():
            if isinstance(v, bool):
                self.vars[k] = tk.BooleanVar(value=v)
            else:
                self.vars[k] = tk.StringVar(value=str(v))

    def _apply_style(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(12, 6))
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"), foreground="#1e3a8a")
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=26)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#111827")])

    def _build_ui(self):
        top_bar = ttk.Frame(self, padding=8)
        top_bar.pack(fill="x")
        ttk.Label(top_bar, text="TÍNH TOÁN THỦY VĂN & THỦY LỰC CẦU NHỎ",
                  font=("Segoe UI", 15, "bold"), foreground="#0f172a").pack(side="left")
        ttk.Label(top_bar, text="TCVN 9845:2013 • V5.1 Chuẩn Hóa",
                  font=("Segoe UI", 9, "bold"), foreground="#059669").pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)

        self.t_rain = ttk.Frame(self.nb)
        self.t_hydro = ttk.Frame(self.nb)
        self.t_bridge = ttk.Frame(self.nb)
        self.t_tables = ttk.Frame(self.nb)

        self.nb.add(self.t_rain, text=" 1. Phân Tích Chuỗi Mưa (Hp) ")
        self.nb.add(self.t_hydro, text=" 2. Thủy Văn Lưu Vực (Qp) ")
        self.nb.add(self.t_bridge, text=" 3. Thủy Lực Cầu Nhỏ ")
        self.nb.add(self.t_tables, text=" 4. Tra Cứu Bảng TCVN ")

        self._build_rain_tab()
        self._build_hydro_tab()
        self._build_bridge_tab()
        self._build_tables_tab()

        bot_bar = ttk.Frame(self, padding=6)
        bot_bar.pack(fill="x")
        ttk.Button(bot_bar, text="💾 Xuất Báo Cáo Tính Toán (.txt / .csv)", command=self.export_report).pack(side="right", padx=5)

    # ---------------- TAB 1: MƯA ----------------
    def _build_rain_tab(self):
        frm = ttk.Frame(self.t_rain, padding=10)
        frm.pack(fill="both", expand=True)

        pan = ttk.Panedwindow(frm, orient="horizontal")
        pan.pack(fill="both", expand=True)
        left = ttk.Frame(pan); right = ttk.Frame(pan)
        pan.add(left, weight=1); pan.add(right, weight=2)

        box_inp = ttk.LabelFrame(left, text="Chuỗi lượng mưa ngày lớn nhất năm (Hmax)", padding=8)
        box_inp.pack(fill="both", expand=True, padx=(0, 5))
        ttk.Label(box_inp, text="Định dạng: [Năm]  [Hmax(mm)]\nChấp nhận phân cách bằng Tab, phẩy, chấm phẩy:", foreground="#475569").pack(anchor="w", pady=(0, 4))
        
        self.rain_text = tk.Text(box_inp, width=32, height=18, font=("Consolas", 10), undo=True)
        self.rain_text.pack(fill="both", expand=True, pady=4)
        sample = "2010\t245\n2011\t312\n2012\t268\n2013\t291\n2014\t337\n2015\t285\n2016\t301\n2017\t355\n2018\t279\n2019\t326\n2020\t310"
        self.rain_text.insert("1.0", sample)

        btn_box = ttk.Frame(box_inp)
        btn_box.pack(fill="x", pady=4)
        ttk.Button(btn_box, text="⚡ Tính Thống Kê", command=self.calc_rain).pack(side="left", padx=2)
        ttk.Button(btn_box, text="📁 Mở File", command=self.load_rain_file).pack(side="left", padx=2)
        ttk.Button(btn_box, text="Xóa", command=lambda: self.rain_text.delete("1.0", "end")).pack(side="left", padx=2)

        # Bên phải
        box_stat = ttk.LabelFrame(right, text="Thông số thống kê mẫu", padding=8)
        box_stat.pack(fill="x", padx=(5, 0))
        self.stat_label = ttk.Label(box_stat, text="Chưa tính toán", font=("Consolas", 10), justify="left")
        self.stat_label.pack(anchor="w")

        box_p = ttk.LabelFrame(right, text="Tần suất thiết kế P% và xác định Hp%", padding=8)
        box_p.pack(fill="x", pady=6, padx=(5, 0))
        
        row1 = ttk.Frame(box_p); row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="Đường phân phối:").pack(side="left", padx=4)
        cb_m = ttk.Combobox(row1, textvariable=self.vars["method"], values=["Pearson III", "Gumbel"], state="readonly", width=14)
        cb_m.pack(side="left", padx=4)
        cb_m.bind("<<ComboboxSelected>>", lambda e: self.calc_rain() if self.rain_stats else None)

        ttk.Label(row1, text="Tần suất P (%):").pack(side="left", padx=(12, 4))
        self.cb_p = ttk.Combobox(row1, textvariable=self.vars["P"], values=["0.1","0.2","0.33","0.5","1","2","4","5","10","20"], width=8)
        self.cb_p.pack(side="left", padx=4)
        self.cb_p.bind("<<ComboboxSelected>>", lambda e: self.apply_p())
        ttk.Button(row1, text="Cập nhật Hp", command=self.apply_p).pack(side="left", padx=6)

        row2 = ttk.Frame(box_p); row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="Lượng mưa thiết kế Hp% = ", font=("Segoe UI", 11, "bold")).pack(side="left")
        self.lbl_hp_val = ttk.Label(row2, text="— mm", font=("Segoe UI", 13, "bold"), foreground="#0369a1")
        self.lbl_hp_val.pack(side="left", padx=4)
        self.lbl_kp_val = ttk.Label(row2, text="(Kp = —)", font=("Segoe UI", 10))
        self.lbl_kp_val.pack(side="left", padx=6)

        # Bảng tần suất
        box_tbl = ttk.LabelFrame(right, text="Bảng tính tần suất lý thuyết (Kích đúp vào hàng để chọn)", padding=6)
        box_tbl.pack(fill="both", expand=True, padx=(5, 0))
        self.tree_p = ttk.Treeview(box_tbl, columns=("p","t","hp","kp"), show="headings", height=7)
        for c, t, w in [("p","P (%)",90), ("t","Chu kỳ T (năm)",130), ("hp","Hp (mm)",140), ("kp","Hệ số Kp",110)]:
            self.tree_p.heading(c, text=t); self.tree_p.column(c, width=w, anchor="center")
        self.tree_p.pack(fill="both", expand=True)
        self.tree_p.bind("<Double-1>", self._on_tree_p_click)

    def parse_rain_input(self):
        raw = self.rain_text.get("1.0", "end").strip()
        if not raw: raise ValueError("Vui lòng nhập chuỗi số liệu mưa.")
        vals = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            tokens = [x for x in re.split(r"[;\t,\s]+", line) if x]
            nums = []
            for t in tokens:
                try: nums.append(float(t.replace(",", ".")))
                except Exception: pass
            if len(nums) >= 2: vals.append(nums[1])
            elif len(nums) == 1: vals.append(nums[0])
        return vals

    def calc_rain(self):
        try:
            vals = self.parse_rain_input()
            s = rainfall_stats(vals)
            self.rain_stats = s
            self.stat_label.config(text=(
                f"Số năm quan trắc N = {s['n']} năm    |    X̄ = {s['mean']:.2f} mm    |    S = {s['std']:.2f} mm\n"
                f"Hệ số biến sai Cv = {s['cv']:.3f}     |    Hệ số thiên lệch Cs = {s['cs']:.3f}\n"
                f"Giá trị nhỏ nhất Min = {s['min']:.1f} mm |  Lớn nhất Max = {s['max']:.1f} mm"
            ))
            for row in self.tree_p.get_children(): self.tree_p.delete(row)
            for p_val in [0.1, 0.2, 0.33, 0.5, 1.0, 2.0, 4.0, 5.0, 10.0, 20.0]:
                hp, kp = self._get_hp(p_val)
                t_str = f"{100.0/p_val:.1f}" if p_val>0 else "-"
                self.tree_p.insert("", "end", values=(f"{p_val:g}", t_str, f"{hp:.2f}", f"{kp:.4f}"))
            self.apply_p()
        except Exception as e:
            messagebox.showerror("Lỗi tính chuỗi mưa", str(e))

    def _get_hp(self, p):
        if not self.rain_stats: raise ValueError("Chưa có số liệu thống kê.")
        s = self.rain_stats
        if self.vars["method"].get() == "Pearson III":
            hp, kp, _ = hp_pearson3(s["mean"], s["cv"], s["cs"], p)
        else:
            hp, kp = hp_gumbel(s["mean"], s["cv"], p)
        return hp, kp

    def apply_p(self):
        try:
            p = num(self.vars["P"].get(), "P")
            if not self.rain_stats:
                self.calc_rain()
            hp, kp = self._get_hp(p)
            self.vars["hp"].set(f"{hp:.2f}")
            self.lbl_hp_val.config(text=f"{hp:.2f} mm")
            self.lbl_kp_val.config(text=f"(Kp = {kp:.4f})")
            # Tự động tính tab thủy văn nếu có thể
            self.calc_hydro_flow(silent=True)
        except Exception:
            pass

    def _on_tree_p_click(self, evt):
        item = self.tree_p.identify_row(evt.y)
        if item:
            p_val = self.tree_p.item(item, "values")[0]
            self.vars["P"].set(p_val)
            self.apply_p()

    def load_rain_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text/CSV","*.txt *.csv"),("Excel","*.xlsx *.xlsm")])
        if not path: return
        try:
            vals = []
            if path.lower().endswith((".xlsx", ".xlsm")):
                import openpyxl
                wb = openpyxl.load_workbook(path, data_only=True)
                ws = wb.active
                for r in ws.iter_rows(values_only=True):
                    for cell in r:
                        if isinstance(cell, (int, float)) and cell > 0:
                            vals.append(float(cell))
                            break
            else:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for l in f:
                        ts = [float(x.replace(",",".")) for x in re.findall(r"[-+]?\d*\.?\d+", l)]
                        if len(ts) >= 2: vals.append(ts[1])
                        elif len(ts) == 1: vals.append(ts[0])
            if len(vals) < 3: raise ValueError("File không có đủ ít nhất 3 số liệu.")
            self.rain_text.delete("1.0", "end")
            self.rain_text.insert("1.0", "\n".join(f"{2000+i}\t{v:g}" for i, v in enumerate(vals)))
            self.calc_rain()
        except Exception as e:
            messagebox.showerror("Lỗi mở file", str(e))

    # ---------------- TAB 2: THỦY VĂN (TCVN 9845:2013) ----------------
    def _build_hydro_tab(self):
        frm = ttk.Frame(self.t_hydro, padding=10)
        frm.pack(fill="both", expand=True)

        box_params = ttk.LabelFrame(frm, text="Thông số lưu vực và địa hình (TCVN 9845:2013)", padding=10)
        box_params.pack(fill="x", pady=(0, 6))

        # Grid inputs
        entries = [
            ("Tần suất P (%):", "P", 0, 0), ("Lượng mưa ngày Hp (mm):", "hp", 0, 2),
            ("Diện tích lưu vực F (km²):", "F", 0, 4), ("Chiều dài sông chính L (km):", "L", 1, 0),
            ("Tổng chiều dài nhánh Σl (km):", "suml", 1, 2), ("Độ dốc lòng dẫn Jlv (‰):", "Jlv", 1, 4),
            ("Độ dốc sườn dốc Jsd (‰):", "Jsd", 2, 0), ("Hệ số hồ đầm tích nước δ:", "delta", 2, 2)
        ]
        for lab, var_key, r, c in entries:
            ttk.Label(box_params, text=lab).grid(row=r, column=c, sticky="w", padx=4, pady=4)
            ttk.Entry(box_params, textvariable=self.vars[var_key], width=12).grid(row=r, column=c+1, sticky="ew", padx=4, pady=4)

        ttk.Label(box_params, text="Vùng mưa:").grid(row=3, column=0, sticky="w", padx=4, pady=4)
        ttk.Combobox(box_params, textvariable=self.vars["region"], values=REGIONS, state="readonly", width=10).grid(row=3, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(box_params, text="Cấp đất thấm:").grid(row=3, column=2, sticky="w", padx=4, pady=4)
        ttk.Combobox(box_params, textvariable=self.vars["soil"], values=SOILS, state="readonly", width=10).grid(row=3, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(box_params, text="Số sườn lưu vực:").grid(row=3, column=4, sticky="w", padx=4, pady=4)
        ttk.Combobox(box_params, textvariable=self.vars["n_slope"], values=["1", "2"], state="readonly", width=10).grid(row=3, column=5, sticky="w", padx=4, pady=4)

        # Chọn nhám msd và mls thông qua menu trợ giúp
        ttk.Label(box_params, text="Nhám sườn dốc msd:").grid(row=4, column=0, sticky="w", padx=4, pady=4)
        f_msd = ttk.Frame(box_params); f_msd.grid(row=4, column=1, columnspan=2, sticky="ew")
        ttk.Entry(f_msd, textvariable=self.vars["msd"], width=8).pack(side="left", padx=2)
        cb_msd_quick = ttk.Combobox(f_msd, values=[f"{val:g} - {name}" for name, val in MSD_OPTIONS], state="readonly", width=32)
        cb_msd_quick.pack(side="left", padx=4)
        cb_msd_quick.bind("<<ComboboxSelected>>", lambda e: self.vars["msd"].set(cb_msd_quick.get().split(" - ")[0]))

        ttk.Label(box_params, text="Nhám lòng dẫn mls:").grid(row=4, column=3, sticky="w", padx=4, pady=4)
        f_mls = ttk.Frame(box_params); f_mls.grid(row=4, column=4, columnspan=2, sticky="ew")
        ttk.Entry(f_mls, textvariable=self.vars["mls"], width=8).pack(side="left", padx=2)
        cb_mls_quick = ttk.Combobox(f_mls, values=[f"{val:g} - {name[:30]}..." for name, val in MLS_OPTIONS], state="readonly", width=32)
        cb_mls_quick.pack(side="left", padx=4)
        cb_mls_quick.bind("<<ComboboxSelected>>", lambda e: self.vars["mls"].set(cb_mls_quick.get().split(" - ")[0]))

        btn_calc = ttk.Button(box_params, text="⚡ TÍNH LƯU LƯỢNG ĐỈNH LŨ (Qp)", command=self.calc_hydro_flow)
        btn_calc.grid(row=5, column=0, columnspan=6, pady=8)

        # Kết quả tóm tắt dạng Thẻ (Cards)
        card_box = ttk.Frame(frm)
        card_box.pack(fill="x", pady=4)
        self.c_qp = self._create_card(card_box, "LƯU LƯỢNG ĐỈNH Qp", "— m³/s", "#1e3a8a")
        self.c_phi = self._create_card(card_box, "DÒNG CHẢY φ", "—", "#0f766e")
        self.c_ap = self._create_card(card_box, "CƯỜNG ĐỘ Ap", "—", "#7c2d12")
        self.c_tsd = self._create_card(card_box, "THỜI GIAN tsd", "— phút", "#4338ca")

        # Bảng chuỗi tính toán chi tiết
        box_chain = ttk.LabelFrame(frm, text="Bảng chi tiết các đại lượng trung gian", padding=6)
        box_chain.pack(fill="both", expand=True, pady=6)
        self.tree_hydro = ttk.Treeview(box_chain, columns=("name","val","unit","formula","src"), show="headings", height=8)
        for c, t, w in [("name","Đại lượng",160), ("val","Trị số",120), ("unit","Đơn vị",80), ("formula","Công thức tính",360), ("src","Tiêu chuẩn/Nguồn",140)]:
            self.tree_hydro.heading(c, text=t); self.tree_hydro.column(c, width=w, anchor="center" if c in ("val","unit") else "w")
        self.tree_hydro.pack(fill="both", expand=True)

    def _create_card(self, parent, title, val, color):
        f = ttk.Frame(parent, relief="groove", padding=8)
        f.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(f, text=title, font=("Segoe UI", 9, "bold"), foreground="#475569").pack()
        lbl = ttk.Label(f, text=val, font=("Segoe UI", 13, "bold"), foreground=color)
        lbl.pack(pady=2)
        return lbl

    def calc_hydro_flow(self, silent=False):
        try:
            hp = pos(self.vars["hp"].get(), "Hp")
            p = num(self.vars["P"].get(), "P")
            F = pos(self.vars["F"].get(), "F")
            L = pos(self.vars["L"].get(), "L")
            suml = pos(self.vars["suml"].get(), "Σl")
            Jlv = pos(self.vars["Jlv"].get(), "Jlv")
            Jsd = pos(self.vars["Jsd"].get(), "Jsd")
            mls = pos(self.vars["mls"].get(), "mls")
            msd = pos(self.vars["msd"].get(), "msd")
            delta = num(self.vars["delta"].get(), "δ")
            soil = self.vars["soil"].get()
            reg = self.vars["region"].get()
            n_slope = int(self.vars["n_slope"].get())

            res = calc_hydro(hp, p, F, L, suml, Jlv, Jsd, mls, msd, delta, soil, reg, n_slope)
            self.hydro = res

            self.c_qp.config(text=f"{res['Qp']:.3f} m³/s")
            self.c_phi.config(text=f"{res['phi']:.4f}")
            self.c_ap.config(text=f"{res['Ap']:.5f}")
            self.c_tsd.config(text=f"{res['tsd']:.1f} phút")

            for r in self.tree_hydro.get_children(): self.tree_hydro.delete(r)
            items = [
                ("Tần suất thiết kế P", res["P"], "%", "Tần suất lũ quy chuẩn", "TCVN 9845"),
                ("Lượng mưa tính toán Hp", res["Hp"], "mm", "Lượng mưa ngày lớn nhất P%", "Bước 1"),
                ("Hệ số dòng chảy φ", res["phi"], "—", "Nội suy theo đất và Hp, F", "Bảng A.1"),
                ("Chiều dài sườn dốc Lsd", res["Lsd"], "m", "1000F / [c(L + Σl)]", "TCVN 9845"),
                ("Đặc trưng sườn dốc Φsd", res["phi_sd"], "—", "Lsd^0.6 / [msd·Jsd^0.3·(φHp)^0.4]", "TCVN 9845"),
                ("Thời gian sườn dốc tsd", res["tsd"], "phút", "Nội suy theo Φsd và Vùng mưa", "Bảng A.2"),
                ("Đặc trưng lòng dẫn Φls", res["phi_ls"], "—", "1000L / [mls·Jlv^(1/3)·(FφHp)^0.25]", "TCVN 9845"),
                ("Hệ số đỉnh lũ Ap", res["Ap"], "—", "Nội suy theo tsd và Φls", "Bảng A.3"),
                ("LƯU LƯỢNG ĐỈNH LŨ Qp", res["Qp"], "m³/s", "Ap · φ · Hp · F · δ", "Công thức (8)")
            ]
            for it in items:
                v_str = f"{it[1]:.4f}" if isinstance(it[1], float) else str(it[1])
                self.tree_hydro.insert("", "end", values=(it[0], v_str, it[2], it[3], it[4]))
            if not silent:
                messagebox.showinfo("Thành công", f"Đã tính toán xong lưu lượng đỉnh lũ:\nQp({p:g}%) = {res['Qp']:.3f} m³/s")
        except Exception as e:
            if not silent: messagebox.showerror("Lỗi tính thủy văn", str(e))

    # ---------------- TAB 3: THỦY LỰC CẦU NHỎ ----------------
    def _build_bridge_tab(self):
        frm = ttk.Frame(self.t_bridge, padding=10)
        frm.pack(fill="both", expand=True)

        box_src = ttk.LabelFrame(frm, text="Nguồn lưu lượng tính toán cầu", padding=8)
        box_src.pack(fill="x", pady=(0, 6))

        rb1 = ttk.Radiobutton(box_src, text="Lấy tự động từ kết quả bước 2 (Qp thủy văn)",
                              variable=self.vars["use_hydro_Q"], value=True, command=self._toggle_q_source)
        rb1.pack(side="left", padx=10)
        rb2 = ttk.Radiobutton(box_src, text="Nhập trực tiếp lưu lượng thiết kế Q (m³/s):",
                              variable=self.vars["use_hydro_Q"], value=False, command=self._toggle_q_source)
        rb2.pack(side="left", padx=10)
        self.entry_custom_q = ttk.Entry(box_src, textvariable=self.vars["custom_Q"], width=12)
        self.entry_custom_q.pack(side="left", padx=4)
        self._toggle_q_source()

        box_params = ttk.LabelFrame(frm, text="Thông số cầu và điều kiện thủy lực (22 TCN 220-95)", padding=10)
        box_params.pack(fill="x", pady=6)

        ttk.Label(box_params, text="Dạng mố cầu:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        cb_m = ttk.Combobox(box_params, textvariable=self.vars["abutment"],
                            values=["Mố chữ U", "Mố tường cánh", "N.A Slovinski (Mố nhẹ)", "Mố chân dê"],
                            state="readonly", width=22)
        cb_m.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(box_params, text="Độ sâu hạ lưu h0 (m):").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(box_params, textvariable=self.vars["h0"], width=10).grid(row=0, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(box_params, text="Vận tốc cho phép Vcp (m/s):").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        ttk.Entry(box_params, textvariable=self.vars["Vcp"], width=10).grid(row=0, column=5, sticky="w", padx=4, pady=4)

        ttk.Label(box_params, text="Khẩu độ chọn Lnc (m):").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        cb_lnc = ttk.Combobox(box_params, textvariable=self.vars["Lnc"], values=["8","10","12","15","18","21","24","30","36"], width=10)
        cb_lnc.grid(row=1, column=1, sticky="w", padx=4, pady=4)

        btn_calc_b = ttk.Button(box_params, text="⚡ TÍNH TOÁN & KIỂM TRA THỦY LỰC CẦU", command=self.calc_bridge_hydraulics)
        btn_calc_b.grid(row=1, column=3, columnspan=3, sticky="ew", padx=8, pady=4)

        # Thẻ kết quả thủy lực
        card_box = ttk.Frame(frm)
        card_box.pack(fill="x", pady=4)
        self.c_lc = self._create_card(card_box, "KHẨU ĐỘ YÊU CẦU Lc", "— m", "#1e3a8a")
        self.c_h = self._create_card(card_box, "CỘT NƯỚC H1", "— m", "#0f766e")
        self.c_vt = self._create_card(card_box, "VẬN TỐC Vt", "— m/s", "#7c2d12")
        self.c_chk = self._create_card(card_box, "KẾT LUẬN", "—", "#15803d")

        # Bảng chi tiết
        box_out = ttk.LabelFrame(frm, text="Kết quả kiểm toán chi tiết", padding=6)
        box_out.pack(fill="both", expand=True, pady=6)
        self.tree_bridge = ttk.Treeview(box_out, columns=("item","val","unit","crit","eval"), show="headings", height=8)
        for c, t, w in [("item","Thông số",200), ("val","Giá trị",120), ("unit","Đơn vị",80), ("crit","Tiêu chí kiểm tra",240), ("eval","Đánh giá",150)]:
            self.tree_bridge.heading(c, text=t); self.tree_bridge.column(c, width=w, anchor="center" if c in ("val","unit","eval") else "w")
        self.tree_bridge.pack(fill="both", expand=True)

    def _toggle_q_source(self):
        if self.vars["use_hydro_Q"].get():
            self.entry_custom_q.configure(state="disabled")
        else:
            self.entry_custom_q.configure(state="normal")

    def calc_bridge_hydraulics(self):
        try:
            if self.vars["use_hydro_Q"].get():
                if not self.hydro:
                    self.calc_hydro_flow(silent=True)
                if not self.hydro:
                    raise ValueError("Chưa có lưu lượng từ bước 2. Vui lòng tính thủy văn trước.")
                Q = self.hydro["Qp"]
            else:
                Q = pos(self.vars["custom_Q"].get(), "Lưu lượng Q")

            abut_map = {"Mố chữ U": 0.34, "Mố tường cánh": 0.35, "N.A Slovinski (Mố nhẹ)": 0.32, "Mố chân dê": 0.32}
            m = abut_map.get(self.vars["abutment"].get(), 0.34)
            h0 = pos(self.vars["h0"].get(), "Độ sâu h0")
            Vcp = pos(self.vars["Vcp"].get(), "Vận tốc cho phép Vcp")
            Lnc = pos(self.vars["Lnc"].get(), "Khẩu độ chọn Lnc")

            res = calc_bridge_free(Q, m, h0, Vcp, Lnc)
            self.bridge = res
            self.bridge["Q_used"] = Q

            self.c_lc.config(text=f"{res['Lc']:.2f} m")
            self.c_h.config(text=f"{res['H1']:.2f} m")
            self.c_vt.config(text=f"{res['Vt']:.2f} m/s")

            all_ok = res["free_final"] and res["vel_ok"]
            if all_ok:
                self.c_chk.config(text="ĐẠT YÊU CẦU", foreground="#15803d")
            else:
                self.c_chk.config(text="CẦN ĐIỀU CHỈNH", foreground="#b91c1c")

            for r in self.tree_bridge.get_children(): self.tree_bridge.delete(r)
            b8_data = bridge8(m)
            items = [
                ("Lưu lượng tính toán Q", Q, "m³/s", "Lưu lượng đỉnh lũ thiết kế", "—"),
                ("Hệ số lưu lượng mố m", res["m"], "—", f"Tra theo loại {self.vars['abutment'].get()}", "Bảng 7"),
                ("Cột nước tự do H", res["H"], "m", "Cột nước trước cầu sơ bộ", "Bảng 8"),
                ("Khẩu độ yêu cầu Lc", res["Lc"], "m", "Khẩu độ thoát nước tối thiểu", f"{'Lnc >= Lc' if Lnc>=res['Lc'] else 'Lnc < Lc'}"),
                ("Khẩu độ thiết kế chọn Lnc", res["Lnc"], "m", "Quy chuẩn khẩu độ nhịp thi công", "—"),
                ("Cột nước tương ứng H1", res["H1"], "m", "H1 = H · (Lc / Lnc)^(2/3)", "22 TCN 220"),
                ("Độ sâu dòng qua cầu htt", res["htt"], "m", "htt = k1 · H1", "Bảng 8"),
                ("Vận tốc dòng chảy qua cầu Vt", res["Vt"], "m/s", f"Điều kiện: Vt <= Vcp ({Vcp:.2f})", "ĐẠT" if res["vel_ok"] else "KHÔNG ĐẠT"),
                ("Chế độ chảy không ngập", h0, "m", f"Điều kiện: h0 <= a·H1 ({b8_data['a']*res['H1']:.2f} m)", "ĐẠT (Không ngập)" if res["free_final"] else "CẢNH BÁO (Bị ngập)"),
            ]
            for it in items:
                v_str = f"{it[1]:.3f}" if isinstance(it[1], float) else str(it[1])
                self.tree_bridge.insert("", "end", values=(it[0], v_str, it[2], it[3], it[4]))
        except Exception as e:
            messagebox.showerror("Lỗi tính thủy lực", str(e))

    # ---------------- TAB 4: BẢNG TRA ----------------
    def _build_tables_tab(self):
        frm = ttk.Frame(self.t_tables, padding=10)
        frm.pack(fill="both", expand=True)

        bar = ttk.Frame(frm)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Chọn bảng tra cứu TCVN 9845:").pack(side="left", padx=4)
        self.cb_sel_table = ttk.Combobox(bar, values=["Bảng A.1 - Hệ số dòng chảy φ", "Bảng A.2 - Thời gian sườn dốc tsd", "Bảng A.3 - Hệ số đỉnh lũ Ap", "Bảng 7 & 8 - Thủy lực mố cầu"], state="readonly", width=36)
        self.cb_sel_table.set("Bảng A.1 - Hệ số dòng chảy φ")
        self.cb_sel_table.pack(side="left", padx=4)
        ttk.Button(bar, text="Xem Bảng", command=self._load_table_view).pack(side="left", padx=4)

        self.table_viewer = ttk.Treeview(frm, show="headings")
        self.table_viewer.pack(fill="both", expand=True, pady=4)
        self._load_table_view()

    def _load_table_view(self):
        for it in self.table_viewer.get_children(): self.table_viewer.delete(it)
        name = self.cb_sel_table.get()

        if "Bảng A.1" in name:
            cols = ["Cấp đất", "Hp (mm)"] + [f"F={x}" for x in A1["F"]]
            self.table_viewer["columns"] = cols
            for c in cols: self.table_viewer.heading(c, text=c); self.table_viewer.column(c, width=70, anchor="center")
            for r in A1["rows"]:
                self.table_viewer.insert("", "end", values=(r[0], r[1], *r[2]))
        elif "Bảng A.2" in name:
            cols = ["Φsd"] + REGIONS
            self.table_viewer["columns"] = cols
            for c in cols: self.table_viewer.heading(c, text=c); self.table_viewer.column(c, width=65, anchor="center")
            for i, x in enumerate(A2["phi"]):
                self.table_viewer.insert("", "end", values=(x, *[A2["regions"][reg][i] for reg in REGIONS]))
        elif "Bảng A.3" in name:
            cols = ["Vùng", "tsd (phút)"] + [f"Φls={x}" for x in A3["phi_ls"]]
            self.table_viewer["columns"] = cols
            for c in cols: self.table_viewer.heading(c, text=c); self.table_viewer.column(c, width=75, anchor="center")
            for reg in ["I", "XII", "XVIII"]: # Hiển thị mẫu đại diện để bảng nhanh nhẹn
                for ts, vals in A3["regions"][reg]:
                    self.table_viewer.insert("", "end", values=(reg, ts, *vals))
        else:
            cols = ["Hệ số m", "Cột K", "Cột L (N)", "k1", "Hệ số a", "Y", "Y2"]
            self.table_viewer["columns"] = cols
            for c in cols: self.table_viewer.heading(c, text=c); self.table_viewer.column(c, width=120, anchor="center")
            for r in BRIDGE["b8"]:
                self.table_viewer.insert("", "end", values=(r[0], r[1], r[2], r[3], r[4], r[5], r[7]))

    # ---------------- XUẤT BÁO CÁO TÍNH TOÁN ----------------
    def export_report(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Báo cáo Text","*.txt"), ("Bảng CSV","*.csv")])
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("="*70 + "\n")
                f.write("BÁO CÁO TÍNH TOÁN THỦY VĂN & THỦY LỰC CẦU NHỎ\n")
                f.write("Tiêu chuẩn áp dụng: TCVN 9845:2013 & 22 TCN 220-95\n")
                f.write("="*70 + "\n\n")

                f.write("1. PHÂN TÍCH TẦN SUẤT MƯA NĂM\n")
                f.write("-" * 40 + "\n")
                if self.rain_stats:
                    s = self.rain_stats
                    f.write(f"- Số năm quan trắc: N = {s['n']} năm\n")
                    f.write(f"- Lượng mưa ngày bình quân: X_tb = {s['mean']:.2f} mm\n")
                    f.write(f"- Độ lệch chuẩn mẫu: S = {s['std']:.2f} mm\n")
                    f.write(f"- Hệ số biến sai: Cv = {s['cv']:.3f}\n")
                    f.write(f"- Hệ số thiên lệch: Cs = {s['cs']:.3f}\n")
                    f.write(f"- Tần suất thiết kế chọn: P = {self.vars['P'].get()}%\n")
                    f.write(f"- Lượng mưa thiết kế Hp = {self.vars['hp'].get()} mm\n\n")
                else:
                    f.write("Chưa thực hiện tính thống kê chuỗi mưa.\n\n")

                f.write("2. KẾT QUẢ TÍNH THỦY VĂN LƯU VỰC (TCVN 9845:2013)\n")
                f.write("-" * 40 + "\n")
                if self.hydro:
                    h = self.hydro
                    f.write(f"- Diện tích lưu vực F = {h['F']} km2\n")
                    f.write(f"- Chiều dài sông chính L = {h['L']} km | Tổng nhánh = {h['suml']} km\n")
                    f.write(f"- Độ dốc lòng dẫn Jlv = {h['Jlv']} o/oo | Sườn dốc Jsd = {h['Jsd']} o/oo\n")
                    f.write(f"- Hệ số dòng chảy phi = {h['phi']:.4f}\n")
                    f.write(f"- Chiều dài sườn dốc Lsd = {h['Lsd']:.2f} m\n")
                    f.write(f"- Thời gian tập trung sườn dốc tsd = {h['tsd']:.2f} phút\n")
                    f.write(f"- Hệ số đỉnh lũ Ap = {h['Ap']:.5f}\n")
                    f.write(f"==> LƯU LƯỢNG ĐỈNH LŨ THIẾT KẾ: Qp = {h['Qp']:.3f} m3/s\n\n")
                else:
                    f.write("Chưa thực hiện tính toán thủy văn.\n\n")

                f.write("3. KIỂM TOÁN THỦY LỰC CẦU NHỎ\n")
                f.write("-" * 40 + "\n")
                if self.bridge:
                    b = self.bridge
                    f.write(f"- Lưu lượng qua cầu Q = {b['Q_used']:.3f} m3/s\n")
                    f.write(f"- Dạng mố cầu: {self.vars['abutment'].get()} (m = {b['m']})\n")
                    f.write(f"- Khẩu độ yêu cầu tính toán: Lc = {b['Lc']:.2f} m\n")
                    f.write(f"- Khẩu độ cầu thiết kế chọn: Lnc = {b['Lnc']:.2f} m\n")
                    f.write(f"- Cột nước dềnh trước cầu: H1 = {b['H1']:.2f} m\n")
                    f.write(f"- Vận tốc dòng qua cầu: Vt = {b['Vt']:.2f} m/s (Vcp = {b['Vcp']:.2f} m/s)\n")
                    f.write(f"- Kiểm tra vận tốc xói: {'ĐẠT (Vt <= Vcp)' if b['vel_ok'] else 'KHÔNG ĐẠT'}\n")
                    f.write(f"- Kiểm tra trạng thái chảy: {'KHÔNG NGẬP' if b['free_final'] else 'CẢNH BÁO BỊ NGẬP'}\n")
                    f.write(f"==> KẾT LUẬN CHUNG: {'ĐẠT YÊU CẦU THỦY LỰC' if (b['vel_ok'] and b['free_final']) else 'CẦN TĂNG KHẨU ĐỘ HOẶC GIA CỐ'}\n")
                else:
                    f.write("Chưa thực hiện kiểm toán thủy lực cầu.\n")

            messagebox.showinfo("Thành công", f"Đã xuất báo cáo tính toán thành công:\n{path}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất file", str(e))


if __name__ == "__main__":
    app = App()
    app.mainloop()