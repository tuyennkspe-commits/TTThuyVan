# -*- coding: utf-8 -*-
"""
PHẦN MỀM TÍNH TOÁN THỦY VĂN - THỦY LỰC CẦU NHỎ
TCVN 9845:2013

V5:
- Toàn bộ bảng tra sử dụng trong workbook nguồn đã được NHÚNG trực tiếp vào mã nguồn.
- Không cần mang theo file Excel bảng tra khi chạy phần mềm.
- Nhập/dán chuỗi lượng mưa ngày lớn nhất năm.
- Tính X̄, S, Cv, Cs và đường tần suất Pearson III.
- Chọn P% -> tự động lấy Hp% -> liên kết sang tính Qp, phi, Lsd, Phi_sd, tsd,
  Phi_ls, Ap.
- Tính thủy lực cầu nhỏ theo các bảng 7-10 của workbook nguồn.
- Có xuất kết quả Excel/CSV.
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
# DỮ LIỆU BẢNG TRA ĐÃ NHÚNG TỪ FILE EXCEL NGUỒN
# ============================================================

A1 = {'F': [0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.5, 1, 3, 6, 10, 50, 100], 'rows': [('II', 0.0, [0.96, 0.94, 0.93, 0.9, 0.88, 0.85, 0.81, 0.78, 0.76, 0.74, 0.67, 0.65, 0.6]), ('II', 101.0, [0.97, 0.96, 0.94, 0.91, 0.9, 0.87, 0.85, 0.78, 0.76, 0.74, 0.67, 0.65, 0.6]), ('II', 151.0, [0.97, 0.96, 0.95, 0.93, 0.92, 0.9, 0.89, 0.85, 0.83, 0.81, 0.75, 0.73, 0.7]), ('II', 201.0, [0.97, 0.96, 0.96, 0.95, 0.94, 0.93, 0.92, 0.89, 0.89, 0.85, 0.85, 0.85, 0.85]), ('II', 251.0, [0.97, 0.96, 0.96, 0.96, 0.95, 0.95, 0.94, 0.93, 0.93, 0.88, 0.88, 0.88, 0.86]), ('II', 301.0, [0.97, 0.96, 0.96, 0.96, 0.95, 0.95, 0.95, 0.93, 0.93, 0.91, 0.91, 0.91, 0.91]), ('II', 401.0, [0.97, 0.96, 0.96, 0.96, 0.95, 0.95, 0.95, 0.93, 0.93, 0.91, 0.91, 0.91, 0.91]), ('III', 0.0, [0.94, 0.89, 0.86, 0.8, 0.77, 0.74, 0.65, 0.6, 0.58, 0.55, 0.53, 0.53, 0.5]), ('III', 101.0, [0.95, 0.93, 0.9, 0.85, 0.81, 0.77, 0.72, 0.63, 0.62, 0.6, 0.55, 0.55, 0.55]), ('III', 151.0, [0.95, 0.93, 0.91, 0.88, 0.86, 0.82, 0.79, 0.72, 0.68, 0.68, 0.63, 0.63, 0.62]), ('III', 201.0, [0.95, 0.93, 0.92, 0.91, 0.9, 0.85, 0.85, 0.75, 0.72, 0.73, 0.73, 0.73, 0.65]), ('III', 251.0, [0.95, 0.93, 0.921, 0.91, 0.9, 0.85, 0.85, 0.77, 0.74, 0.74, 0.69, 0.69, 0.67]), ('III', 301.0, [0.95, 0.93, 0.921, 0.912, 0.9, 0.855, 0.87, 0.78, 0.76, 0.75, 0.71, 0.71, 0.69]), ('III', 351.0, [0.95, 0.93, 0.922, 0.912, 0.902, 0.88, 0.89, 0.79, 0.77, 0.77, 0.73, 0.73, 0.7]), ('III', 401.0, [0.95, 0.93, 0.922, 0.913, 0.902, 0.885, 0.895, 0.8, 0.79, 0.78, 0.75, 0.75, 0.71]), ('III', 451.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.79, 0.75, 0.75, 0.71]), ('III', 501.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.8, 0.76, 0.76, 0.71]), ('III', 551.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.8, 0.76, 0.76, 0.71]), ('III', 601.0, [0.95, 0.93, 0.923, 0.913, 0.91, 0.89, 0.94, 0.8, 0.8, 0.8, 0.76, 0.76, 0.71]), ('IV', 0.0, [0.9, 0.81, 0.76, 0.66, 0.65, 0.6, 0.55, 0.51, 0.5, 0.5, 0.44, 0.4, 0.37]), ('IV', 101.0, [0.9, 0.84, 0.8, 0.76, 0.68, 0.64, 0.62, 0.58, 0.56, 0.55, 0.52, 0.5, 0.46]), ('IV', 151.0, [0.9, 0.88, 0.85, 0.82, 0.78, 0.75, 0.72, 0.66, 0.63, 0.6, 0.6, 0.57, 0.55]), ('IV', 201.0, [0.9, 0.88, 0.822, 0.823, 0.79, 0.78, 0.74, 0.7, 0.67, 0.67, 0.65, 0.6, 0.58]), ('IV', 251.0, [0.9, 0.88, 0.822, 0.825, 0.79, 0.79, 0.76, 0.74, 0.7, 0.7, 0.69, 0.65, 0.61]), ('IV', 301.0, [0.9, 0.88, 0.828, 0.828, 0.8, 0.8, 0.78, 0.76, 0.72, 0.71, 0.71, 0.67, 0.64]), ('IV', 351.0, [0.9, 0.88, 0.828, 0.83, 0.82, 0.82, 0.81, 0.77, 0.74, 0.73, 0.72, 0.69, 0.65]), ('IV', 401.0, [0.9, 0.88, 0.86, 0.84, 0.84, 0.84, 0.83, 0.77, 0.75, 0.75, 0.73, 0.71, 0.67]), ('IV', 451.0, [0.9, 0.88, 0.86, 0.85, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.68]), ('IV', 501.0, [0.9, 0.88, 0.87, 0.86, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.69]), ('IV', 551.0, [0.9, 0.88, 0.87, 0.86, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.69]), ('IV', 601.0, [0.9, 0.88, 0.87, 0.86, 0.84, 0.84, 0.83, 0.78, 0.76, 0.77, 0.73, 0.72, 0.69]), ('V', 0.0, [0.68, 0.46, 0.35, 0.26, 0.24, 0.22, 0.22, 0.2, 0.18, 0.18, 0.17, 0.16, 0.15]), ('V', 101.0, [0.71, 0.56, 0.46, 0.41, 0.4, 0.34, 0.32, 0.28, 0.27, 0.25, 0.23, 0.22, 0.2]), ('V', 151.0, [0.75, 0.65, 0.59, 0.5, 0.48, 0.46, 0.46, 0.42, 0.45, 0.38, 0.34, 0.32, 0.3]), ('V', 201.0, [0.76, 0.68, 0.63, 0.543, 0.5, 0.5, 0.5, 0.46, 0.49, 0.43, 0.38, 0.36, 0.34]), ('V', 251.0, [0.77, 0.71, 0.66, 0.58, 0.58, 0.54, 0.54, 0.49, 0.51, 0.46, 0.41, 0.4, 0.36]), ('V', 301.0, [0.77, 0.73, 0.66, 0.58, 0.58, 0.54, 0.56, 0.49, 0.54, 0.46, 0.41, 0.43, 0.37]), ('V', 351.0, [0.78, 0.75, 0.7, 0.65, 0.64, 0.57, 0.57, 0.53, 0.55, 0.52, 0.46, 0.46, 0.4]), ('V', 401.0, [0.79, 0.76, 0.72, 0.67, 0.67, 0.58, 0.58, 0.54, 0.55, 0.53, 0.47, 0.47, 0.41]), ('V', 451.0, [0.79, 0.77, 0.73, 0.68, 0.68, 0.6, 0.6, 0.55, 0.55, 0.53, 0.48, 0.48, 0.41]), ('V', 501.0, [0.79, 0.78, 0.73, 0.7, 0.7, 0.6, 0.6, 0.55, 0.55, 0.53, 0.49, 0.5, 0.41]), ('V', 551.0, [0.79, 0.78, 0.73, 0.7, 0.7, 0.6, 0.6, 0.55, 0.55, 0.53, 0.5, 0.5, 0.41]), ('V', 601.0, [0.79, 0.78, 0.73, 0.7, 0.7, 0.6, 0.6, 0.55, 0.55, 0.53, 0.5, 0.5, 0.41])]}
A2 = {'phi': [1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 17, 20, 25, 30, 35, 40], 'regions': {'I': [9.6, 10, 17, 24, 35, 40, 53, 62, 70, 75, 80, 90, 100, 130, 160, 200, 260, 325, 370, 470], 'II': [9.7, 10, 15, 22, 28, 37, 45, 60, 70, 78, 87, 95, 115, 150, 165, 220, 280, 360, 430, 530], 'III': [9.7, 10, 17, 20, 25, 32, 50, 60, 72, 80, 90, 100, 120, 150, 180, 230, 265, 365, 435, 520], 'IV': [9, 9, 9.5, 10, 18, 22, 30, 45, 60, 68, 80, 86, 95, 120, 165, 200, 235, 320, 400, 470], 'V': [9.6, 10, 14, 20, 30, 35, 44, 60, 75, 85, 90, 95, 100, 120, 170, 200, 260, 320, 370, 480], 'VI': [9.6, 10, 10, 15, 22, 30, 38, 50, 70, 78, 82, 88, 93, 120, 150, 185, 230, 310, 370, 470], 'VII': [16, 18, 25, 32, 37, 42, 50, 55, 65, 75, 85, 90, 100, 125, 165, 205, 250, 320, 400, 570], 'VIII': [8.4, 8.5, 9, 10, 20, 30, 40, 55, 65, 70, 80, 90, 115, 135, 190, 235, 305, 370, 480, 495], 'IX': [9.7, 10, 13, 15, 18, 25, 30, 40, 65, 70, 80, 95, 115, 135, 170, 220, 290, 370, 430, 520], 'X': [9.8, 10, 15, 18, 25, 40, 45, 60, 75, 85, 90, 95, 110, 135, 170, 220, 265, 335, 345, 410], 'XI': [9.5, 10, 20, 28, 35, 55, 65, 72, 80, 90, 95, 110, 130, 160, 200, 230, 300, 400, 470, 560], 'XII': [10, 13, 20, 23, 30, 35, 50, 60, 75, 80, 87, 105, 120, 150, 190, 235, 300, 380, 450, 540], 'XIII': [9.8, 10, 15, 20, 25, 30, 40, 55, 65, 70, 82, 90, 100, 125, 160, 200, 250, 330, 400, 510], 'XIV': [8.7, 9, 9.3, 9.5, 11, 20, 30, 35, 50, 70, 80, 85, 90, 115, 160, 200, 250, 320, 400, 480], 'XV': [8.5, 8.7, 9.3, 9.5, 10, 20, 25, 32, 50, 65, 70, 80, 90, 125, 150, 190, 250, 320, 400, 490], 'XVI': [8.7, 9, 9.5, 9.6, 12, 20, 30, 37, 50, 65, 78, 80, 90, 115, 140, 175, 225, 285, 355, 425], 'XVII': [9.3, 9.4, 9.7, 10, 20, 25, 35, 40, 60, 70, 80, 90, 97, 120, 145, 190, 240, 320, 380, 465], 'XVIII': [9.2, 9.3, 9.5, 9.7, 12, 20, 23, 30, 40, 60, 70, 80, 83, 100, 130, 165, 230, 300, 370, None]}}
A3 = {'phi_ls': [0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 150, 200, 220], 'regions': {'I': [(20, [0.28, 0.26, 0.218, 0.152, 0.112, 0.092, 0.076, 0.064, 0.054, 0.047, 0.04, 0.035, 0.03, 0.018, 0.015, 0.013]), (30, [0.21, 0.19, 0.16, 0.136, 0.104, 0.085, 0.072, 0.061, 0.052, 0.045, 0.038, 0.033, 0.029, 0.017, 0.014, 0.0125]), (60, [0.15, 0.143, 0.125, 0.111, 0.091, 0.076, 0.065, 0.055, 0.047, 0.04, 0.034, 0.03, 0.026, 0.016, 0.013, 0.012]), (90, [0.114, 0.112, 0.102, 0.093, 0.017, 0.065, 0.056, 0.048, 0.041, 0.035, 0.031, 0.027, 0.024, 0.015, 0.012, 0.0115]), (180, [0.072, 0.071, 0.057, 0.063, 0.055, 0.048, 0.043, 0.037, 0.033, 0.029, 0.025, 0.022, 0.021, 0.014, 0.0115, 0.011])], 'II': [(20, [0.117, 0.114, 0.104, 0.093, 0.087, 0.065, 0.055, 0.047, 0.04, 0.034, 0.03, 0.026, 0.024, 0.018, 0.015, 0.014]), (30, [0.1, 0.098, 0.091, 0.083, 0.07, 0.06, 0.052, 0.044, 0.038, 0.033, 0.028, 0.025, 0.023, 0.0175, 0.014, 0.013]), (60, [0.082, 0.081, 0.076, 0.07, 0.06, 0.052, 0.045, 0.039, 0.034, 0.03, 0.027, 0.024, 0.022, 0.016, 0.013, 0.0125]), (90, [0.067, 0.066, 0.063, 0.059, 0.052, 0.046, 0.04, 0.035, 0.031, 0.027, 0.025, 0.022, 0.02, 0.015, 0.012, 0.012]), (180, [0.052, 0.051, 0.048, 0.046, 0.041, 0.036, 0.032, 0.028, 0.025, 0.022, 0.02, 0.018, 0.017, 0.014, 0.011, 0.011])], 'III': [(20, [0.159, 0.153, 0.137, 0.112, 0.0985, 0.0831, 0.0708, 0.0618, 0.0544, 0.0492, 0.045, 0.041, 0.0378, 0.0281, 0.0218, 0.0183]), (30, [0.132, 0.129, 0.116, 0.104, 0.0866, 0.074, 0.065, 0.0573, 0.0507, 0.0462, 0.042, 0.039, 0.0358, 0.0272, 0.0211, 0.018]), (60, [0.095, 0.092, 0.087, 0.079, 0.0695, 0.0611, 0.053, 0.0497, 0.0447, 0.041, 0.038, 0.035, 0.0325, 0.0252, 0.0197, 0.017]), (90, [0.073, 0.068, 0.0659, 0.0612, 0.0549, 0.05, 0.0443, 0.0414, 0.0384, 0.0355, 0.033, 0.0307, 0.0292, 0.0228, 0.0185, 0.016]), (180, [0.058, 0.054, 0.0517, 0.049, 0.045, 0.042, 0.0383, 0.036, 0.033, 0.0303, 0.03, 0.0268, 0.0256, 0.0205, 0.0165, 0.015])], 'IV': [(20, [0.273, 0.214, 0.188, 0.163, 0.128, 0.104, 0.0865, 0.0743, 0.0654, 0.0565, 0.0499, 0.0448, 0.0408, 0.0279, 0.0216, 0.0184]), (30, [0.2, 0.184, 0.163, 0.142, 0.1153, 0.095, 0.816, 0.0703, 0.0615, 0.0545, 0.0479, 0.0429, 0.039, 0.0269, 0.0212, 0.0182]), (60, [0.129, 0.124, 0.117, 0.107, 0.0903, 0.079, 0.0688, 0.0593, 0.0553, 0.0473, 0.0427, 0.0382, 0.0351, 0.0256, 0.02, 0.0174]), (90, [0.102, 0.093, 0.089, 0.084, 0.0735, 0.0645, 0.0579, 0.0508, 0.046, 0.041, 0.037, 0.034, 0.0315, 0.023, 0.0189, 0.0164]), (180, [0.072, 0.071, 0.067, 0.063, 0.0555, 0.0503, 0.0456, 0.0413, 0.0378, 0.0328, 0.0315, 0.031, 0.0275, 0.021, 0.0178, 0.0155])], 'V': [(20, [0.12, 0.1185, 0.1115, 0.1087, 0.094, 0.0786, 0.069, 0.063, 0.0525, 0.0457, 0.0397, 0.0347, 0.0304, 0.0195, 0.014, 0.013]), (30, [0.112, 0.11, 0.1035, 0.0965, 0.084, 0.0733, 0.0638, 0.056, 0.0485, 0.0423, 0.037, 0.032, 0.028, 0.0169, 0.0133, 0.0124]), (60, [0.098, 0.0965, 0.0855, 0.0815, 0.0748, 0.0655, 0.0577, 0.0506, 0.0445, 0.0393, 0.0345, 0.0304, 0.0268, 0.0163, 0.0126, 0.0119]), (90, [0.083, 0.0817, 0.0775, 0.0726, 0.0642, 0.0565, 0.05, 0.0443, 0.039, 0.0345, 0.031, 0.0276, 0.0247, 0.0152, 0.0118, 0.0114]), (180, [0.0595, 0.0587, 0.056, 0.0583, 0.048, 0.043, 0.039, 0.035, 0.0317, 0.0285, 0.0263, 0.024, 0.0223, 0.0148, 0.011, 0.0108])], 'VI': [(20, [0.1215, 0.1195, 0.113, 0.1053, 0.0916, 0.0803, 0.0703, 0.0617, 0.0543, 0.0478, 0.0417, 0.0377, 0.0324, 0.0195, 0.015, 0.014]), (30, [0.1135, 0.1117, 0.106, 0.087, 0.0865, 0.0757, 0.0666, 0.0585, 0.0515, 0.0452, 0.0397, 0.035, 0.031, 0.0189, 0.0145, 0.0135]), (60, [0.105, 0.0995, 0.0944, 0.086, 0.0798, 0.0686, 0.0606, 0.0536, 0.0474, 0.042, 0.0373, 0.0333, 0.0295, 0.0183, 0.014, 0.0129]), (90, [0.0863, 0.0858, 0.0816, 0.077, 0.069, 0.0617, 0.0553, 0.049, 0.044, 0.039, 0.035, 0.031, 0.0278, 0.0172, 0.0135, 0.0124]), (180, [0.0645, 0.0637, 0.061, 0.058, 0.0513, 0.0457, 0.0407, 0.0363, 0.0323, 0.0292, 0.0265, 0.0242, 0.0222, 0.0167, 0.013, 0.012])], 'VII': [(20, [0.106, 0.105, 0.1, 0.0934, 0.0817, 0.0716, 0.0633, 0.0555, 0.049, 0.043, 0.0382, 0.0337, 0.03, 0.019, 0.015, 0.0133]), (30, [0.097, 0.096, 0.091, 0.0786, 0.0763, 0.0677, 0.0603, 0.0534, 0.0474, 0.0417, 0.037, 0.0327, 0.029, 0.0181, 0.0142, 0.0129]), (60, [0.085, 0.084, 0.08, 0.0757, 0.0676, 0.0606, 0.054, 0.0482, 0.043, 0.038, 0.034, 0.0303, 0.0272, 0.0175, 0.0135, 0.0125]), (90, [0.071, 0.07, 0.067, 0.0632, 0.0565, 0.0506, 0.0455, 0.0407, 0.04, 0.033, 0.0298, 0.0271, 0.0247, 0.0168, 0.0127, 0.0117]), (180, [0.057, 0.056, 0.054, 0.051, 0.046, 0.0408, 0.0365, 0.0326, 0.0293, 0.0265, 0.0238, 0.0218, 0.02, 0.016, 0.0121, 0.011])], 'VIII': [(20, [0.162, 0.156, 0.136, 0.121, 0.0963, 0.0805, 0.0676, 0.0572, 0.0483, 0.0422, 0.0375, 0.0334, 0.0298, 0.024, 0.017, 0.016]), (30, [0.146, 0.142, 0.127, 0.112, 0.0905, 0.076, 0.0645, 0.055, 0.0477, 0.0416, 0.0366, 0.0327, 0.0292, 0.0225, 0.016, 0.015]), (60, [0.119, 0.116, 0.104, 0.0933, 0.0773, 0.0656, 0.056, 0.0486, 0.0435, 0.0386, 0.0345, 0.0309, 0.028, 0.021, 0.015, 0.014]), (90, [0.101, 0.0987, 0.091, 0.0824, 0.0693, 0.0593, 0.0513, 0.0445, 0.0394, 0.0352, 0.032, 0.0293, 0.0265, 0.019, 0.014, 0.013]), (180, [0.062, 0.0615, 0.0587, 0.055, 0.05, 0.045, 0.0403, 0.0365, 0.033, 0.03, 0.0275, 0.0253, 0.0235, 0.0173, 0.013, 0.012])], 'IX': [(20, [0.1923, 0.1825, 0.157, 0.143, 0.1152, 0.0956, 0.081, 0.0705, 0.0616, 0.0549, 0.0489, 0.0443, 0.0407, 0.029, 0.022, 0.02]), (30, [0.1912, 0.1555, 0.1395, 0.1233, 0.103, 0.0868, 0.0762, 0.0663, 0.0587, 0.0527, 0.0469, 0.0425, 0.039, 0.0279, 0.021, 0.019]), (60, [0.1095, 0.105, 0.1015, 0.0931, 0.0811, 0.0724, 0.0642, 0.0563, 0.0534, 0.0463, 0.0425, 0.0385, 0.0355, 0.0262, 0.02, 0.0178]), (90, [0.0905, 0.082, 0.08, 0.0756, 0.074, 0.0607, 0.0553, 0.0493, 0.0452, 0.0407, 0.0372, 0.0345, 0.0322, 0.0233, 0.019, 0.0165]), (180, [0.064, 0.0635, 0.061, 0.0572, 0.051, 0.0468, 0.0433, 0.0396, 0.0367, 0.0336, 0.0317, 0.03, 0.028, 0.022, 0.0178, 0.0155])], 'X': [(20, [0.0946, 0.0932, 0.0887, 0.0833, 0.0733, 0.0645, 0.0568, 0.05, 0.0443, 0.0388, 0.0345, 0.0305, 0.0277, 0.02, 0.015, 0.013]), (30, [0.0893, 0.088, 0.0836, 0.0788, 0.069, 0.0608, 0.0537, 0.0473, 0.0417, 0.037, 0.033, 0.0293, 0.0263, 0.0192, 0.0145, 0.0128]), (60, [0.0806, 0.0796, 0.0757, 0.071, 0.0628, 0.0555, 0.0487, 0.0433, 0.0383, 0.034, 0.0303, 0.027, 0.0246, 0.0183, 0.014, 0.0125]), (90, [0.0717, 0.0707, 0.067, 0.0635, 0.0557, 0.0495, 0.0437, 0.0387, 0.0346, 0.0307, 0.0277, 0.0253, 0.023, 0.0179, 0.0135, 0.0122]), (180, [0.0525, 0.052, 0.05, 0.0472, 0.0425, 0.0382, 0.0435, 0.0313, 0.0283, 0.0262, 0.0243, 0.0242, 0.0216, 0.0173, 0.013, 0.0115])], 'XI': [(20, [0.0888, 0.0862, 0.08, 0.0714, 0.0607, 0.0524, 0.461, 0.0406, 0.0364, 0.033, 0.0304, 0.028, 0.0267, 0.0216, 0.0182, 0.0161]), (30, [0.0712, 0.0696, 0.0667, 0.0612, 0.0541, 0.0478, 0.043, 0.0385, 0.0348, 0.0317, 0.0294, 0.0273, 0.0258, 0.0211, 0.0176, 0.0157]), (60, [0.0631, 0.0615, 0.0582, 0.0542, 0.048, 0.0431, 0.0388, 0.036, 0.0315, 0.0286, 0.0268, 0.0251, 0.0234, 0.0196, 0.0164, 0.0149]), (90, [0.0518, 0.0508, 0.0479, 0.0459, 0.0403, 0.0364, 0.0327, 0.0304, 0.0283, 0.0261, 0.0255, 0.0233, 0.0222, 0.0185, 0.0157, 0.0143]), (180, [0.0431, 0.042, 0.0398, 0.0375, 0.0339, 0.0316, 0.0286, 0.0264, 0.0245, 0.023, 0.0218, 0.021, 0.0204, 0.0172, 0.0148, 0.0136])], 'XII': [(20, [0.09, 0.088, 0.0807, 0.0727, 0.06, 0.0503, 0.0423, 0.036, 0.0307, 0.027, 0.0242, 0.0225, 0.0218, 0.0185, 0.015, 0.0138]), (30, [0.079, 0.0755, 0.0705, 0.0647, 0.055, 0.0466, 0.0397, 0.0344, 0.0297, 0.026, 0.0237, 0.022, 0.0213, 0.0175, 0.0142, 0.0134]), (60, [0.0614, 0.0604, 0.0567, 0.0527, 0.0455, 0.0396, 0.0345, 0.0303, 0.027, 0.0244, 0.0224, 0.0214, 0.0208, 0.017, 0.0138, 0.0129]), (90, [0.052, 0.051, 0.0487, 0.046, 0.0406, 0.0357, 0.0317, 0.0283, 0.0253, 0.0232, 0.0217, 0.0205, 0.0197, 0.0165, 0.013, 0.0122]), (180, [0.041, 0.0404, 0.0387, 0.0365, 0.0327, 0.0295, 0.0265, 0.0243, 0.0222, 0.0207, 0.0197, 0.0188, 0.0185, 0.0153, 0.012, 0.0115])], 'XIII': [(20, [0.154, 0.0149, 0.139, 0.105, 0.0901, 0.0763, 0.0658, 0.057, 0.0506, 0.0449, 0.0403, 0.0366, 0.0334, 0.0253, 0.0208, 0.0183]), (30, [0.129, 0.126, 0.112, 0.099, 0.0834, 0.0713, 0.0624, 0.0539, 0.0476, 0.0428, 0.0382, 0.035, 0.0319, 0.0241, 0.0198, 0.0177]), (60, [0.0975, 0.0954, 0.0878, 0.0808, 0.0694, 0.0611, 0.0534, 0.0477, 0.0427, 0.0383, 0.0315, 0.0319, 0.0294, 0.0227, 0.0185, 0.0168]), (90, [0.0756, 0.074, 0.0684, 0.0648, 0.0542, 0.0515, 0.0478, 0.0417, 0.0375, 0.0345, 0.0317, 0.0296, 0.0268, 0.0214, 0.0184, 0.016]), (180, [0.0543, 0.053, 0.0513, 0.0491, 0.0448, 0.0415, 0.0378, 0.0315, 0.032, 0.0297, 0.0278, 0.0257, 0.0246, 0.02, 0.0175, 0.0152])], 'XIV': [(20, [0.23, 0.215, 0.207, 0.175, 0.119, 0.0937, 0.0756, 0.0622, 0.0517, 0.0435, 0.037, 0.0315, 0.0273, 0.0185, 0.014, 0.012]), (30, [0.178, 0.171, 0.15, 0.131, 0.105, 0.0855, 0.0703, 0.0585, 0.0493, 0.0415, 0.0353, 0.0303, 0.0263, 0.0178, 0.0132, 0.0112]), (60, [0.137, 0.134, 0.122, 0.11, 0.092, 0.0757, 0.0633, 0.0533, 0.0437, 0.0383, 0.0326, 0.0284, 0.025, 0.017, 0.0125, 0.0103]), (90, [0.11, 0.107, 0.097, 0.09, 0.076, 0.0646, 0.0552, 0.0467, 0.0405, 0.035, 0.0305, 0.0266, 0.0236, 0.016, 0.0118, 0.0095]), (180, [0.086, 0.066, 0.063, 0.051, 0.053, 0.0464, 0.041, 0.0363, 0.0317, 0.028, 0.0247, 0.022, 0.0197, 0.014, 0.01, 0.0085])], 'XV': [(20, [0.261, 0.251, 0.233, 0.21, 0.153, 0.121, 0.0965, 0.0786, 0.0719, 0.063, 0.0508, 0.044, 0.0375, 0.0259, 0.0211, 0.0191]), (30, [0.225, 0.22, 0.191, 0.166, 0.133, 0.106, 0.0875, 0.073, 0.0632, 0.059, 0.0478, 0.042, 0.037, 0.0252, 0.0206, 0.0189]), (60, [0.158, 0.117, 0.136, 0.11, 0.099, 0.084, 0.0723, 0.062, 0.0548, 0.0485, 0.043, 0.039, 0.0354, 0.0234, 0.0195, 0.0181]), (90, [0.105, 0.103, 0.094, 0.087, 0.0755, 0.066, 0.059, 0.052, 0.0463, 0.0418, 0.0383, 0.0345, 0.0313, 0.0215, 0.0185, 0.0166]), (180, [0.074, 0.073, 0.0687, 0.064, 0.057, 0.0514, 0.0463, 0.0421, 0.0386, 0.035, 0.0321, 0.0295, 0.0274, 0.0202, 0.0172, 0.0155])], 'XVI': [(20, [0.3, 0.29, 0.249, 0.229, 0.184, 0.155, 0.129, 0.0106, 0.09, 0.0768, 0.0674, 0.0593, 0.053, 0.0403, 0.0298, 0.0231]), (30, [0.252, 0.243, 0.215, 0.2, 0.166, 0.138, 0.114, 0.096, 0.082, 0.0717, 0.0627, 0.0555, 0.0507, 0.0368, 0.0287, 0.0227]), (60, [0.194, 0.189, 0.173, 0.155, 0.13, 0.11, 0.092, 0.079, 0.0692, 0.0617, 0.0552, 0.0493, 0.0445, 0.0324, 0.027, 0.0218]), (90, [0.148, 0.143, 0.13, 0.119, 0.099, 0.087, 0.074, 0.066, 0.059, 0.053, 0.0469, 0.0428, 0.0392, 0.029, 0.0242, 0.0205]), (180, [0.094, 0.092, 0.089, 0.081, 0.071, 0.063, 0.057, 0.052, 0.0473, 0.0433, 0.0397, 0.0357, 0.033, 0.0265, 0.0228, 0.0193])], 'XVII': [(20, [0.2, 0.19, 0.166, 0.146, 0.117, 0.096, 0.08, 0.068, 0.0575, 0.049, 0.042, 0.036, 0.0305, 0.016, 0.014, 0.0125]), (30, [0.18, 0.172, 0.154, 0.137, 0.112, 0.092, 0.077, 0.065, 0.056, 0.047, 0.04, 0.0345, 0.0295, 0.0155, 0.0135, 0.0122]), (60, [0.15, 0.147, 0.134, 0.121, 0.1, 0.084, 0.07, 0.0539, 0.05, 0.043, 0.037, 0.0315, 0.027, 0.015, 0.013, 0.0118]), (90, [0.13, 0.128, 0.127, 0.105, 0.086, 0.078, 0.062, 0.053, 0.0455, 0.0387, 0.0335, 0.0295, 0.025, 0.0145, 0.0125, 0.0115]), (180, [0.085, 0.084, 0.078, 0.072, 0.06, 0.051, 0.044, 0.0375, 0.0325, 0.029, 0.0262, 0.0235, 0.021, 0.014, 0.012, 0.011])], 'XVIII': [(20, [0.302, 0.276, 0.236, 0.221, 0.0167, 0.0139, 0.0114, 0.963, 0.0819, 0.0707, 0.0615, 0.0543, 0.0478, 0.0329, 0.0254, 0.0223]), (30, [0.236, 0.229, 0.202, 0.181, 0.015, 0.0125, 0.0105, 0.0978, 0.0765, 0.066, 0.058, 0.0513, 0.0433, 0.0312, 0.0246, 0.0213]), (60, [0.184, 0.179, 0.138, 0.142, 0.0118, 0.01, 0.0857, 0.0746, 0.0647, 0.0567, 0.0505, 0.0541, 0.0409, 0.0285, 0.0228, 0.02]), (90, [0.129, 0.126, 0.114, 0.098, 0.088, 0.077, 0.067, 0.0596, 0.0534, 0.0477, 0.0431, 0.0396, 0.0357, 0.0264, 0.0213, 0.0182]), (180, [0.092, 0.089, 0.082, 0.075, 0.0652, 0.058, 0.0513, 0.0467, 0.0428, 0.039, 0.0357, 0.0326, 0.303, 0.0232, 0.019, 0.0172])]}}
BRIDGE = {'m': [('N.A Slovinski (Mố nhẹ)', 0.32), ('Mố tường cánh', 0.35), ('Mố chữ U', 0.34), ('Mố chân dê', 0.32)], 'b8': [(0.32, 1.42, 0.59, 0.45, 0.84, 2.56, 0.76, 0.58), (0.33, 1.46, 0.6, 0.47, 0.83, 2.35, 0.78, 0.62), (0.34, 1.5, 0.61, 0.49, 0.81, 2.05, 0.81, 0.65), (0.35, 1.55, 0.63, 0.52, 0.8, 1.85, 0.83, 0.68), (0.36, 1.6, 0.64, 0.54, 0.78, 1.64, 0.84, 0.71)], 'b9': [(0.81, None, None, None, None, None, None, None, None, None, None, 1, 0.61, 1, 1.23), (0.82, None, None, None, None, None, None, None, None, None, None, 0.98, 0.63, 1.1, 1.2), (0.83, None, None, None, None, None, 1, 0.6, 1.1, 1.2, 7.1, 0.96, 0.65, 1.2, 1.17), (0.84, 1, 0.59, 1, 1.19, 6.9, 0.98, 0.62, 1.25, 1.17, 6.1, 0.94, 0.67, 1.31, 1.14), (0.86, 0.96, 0.64, 1.26, 1.13, 4.8, 0.93, 0.67, 1.5, 1.11, 4.3, 0.9, 0.71, 1.56, 1.08), (0.88, 0.9, 0.69, 1.57, 1.07, 3.4, 0.88, 0.72, 1.8, 1.05, 3, 0.85, 0.75, 1.88, 1.02), (0.9, 0.84, 0.74, 2.04, 1, 2.25, 0.82, 0.76, 2.08, 0.97, 2.1, 0.79, 0.8, 2.35, 0.95), (0.92, 0.76, 0.8, 2.65, 0.92, 1.4, 0.75, 0.81, 2.68, 0.9, 1.35, 0.72, 0.84, 2.9, 0.88), (0.94, 0.67, 0.85, 3.52, 0.82, 0.8, 0.66, 0.86, 3.87, 0.81, 0.8, 0.64, 0.88, 3.3, 0.78), (0.96, 0.56, 0.9, 5, 0.71, 0.4, 0.55, 0.91, 5.2, 0.7, 0.35, 0.53, 0.92, 5.3, 0.68), (0.98, 0.4, 0.95, 8.6, 0.55, 0.1, 0.39, 0.95, 8.65, 0.54, 0.1, 0.38, 0.96, 8.65, 0.53), (0.99, 0.28, 0.97, 15, 0.43, 0.05, 0.28, 0.98, 15, 0.43, 0.05, 0.27, 0.98, 15, 0.42)], 'b10': [[1, 'Lát cỏ nằm (trên nền chắc)', None, None, None, None], [None, 'Lát cỏ trồng thành tường', None, None, None, None], [2, 'Đổ đá ba và đá hộc với kích thước đá từ 7.5 cm và lớn hơn', None, None, None, None], [3, 'Đổ đá 2 lớp trong lưới đan với kích thước khác nhau', None, None, None, None], [4, 'Lát đá một lớp trên guột hay rơm rạ (lớp này không bé hơn 5 cm) - a - Loại đường kính 15 cm', None, None, None, None], [None, 'Lát đá một lớp trên guột hay rơm rạ (lớp này không bé hơn 5 cm) - b - Loại đường kính 20 cm', None, None, None, None], [None, 'Lát đá một lớp trên guột hay rơm rạ (lớp này không bé hơn 5 cm) - c - Loại đường kính 25 cm', None, None, None, None], [5, 'Lát đá một lớp trên guột hay rơm rạ (lớp đá dăm không bé hơn 10 cm) - a - bằng cỡ đá 15 cm', None, None, None, None], [None, 'Lát đá một lớp trên guột hay rơm rạ (lớp đá dăm không bé hơn 10 cm) - b - bằng cỡ đá 20 cm', None, None, None, None], [None, 'Lát đá một lớp trên guột hay rơm rạ (lớp đá dăm không bé hơn 10 cm) - c - bằng cỡ đá 25 cm', None, None, None, None], [6, 'Lát đá cẩn thận, các kẽ đá có chèn chặt đá con, trên lớp đá dăm hay sỏi (lớp đá dăm không bé hơn 10 cm) -a - bằng cỡ đá 20 cm', None, None, None, None], [None, 'Lát đá cẩn thận, các kẽ đá có chèn chặt đá con, trên lớp đá dăm hay sỏi (lớp đá dăm không bé hơn 10 cm) -b - bằng cỡ đá 25 cm', None, None, None, None], [None, 'Lát đá cẩn thận, các kẽ đá có chèn chặt đá con, trên lớp đá dăm hay sỏi (lớp đá dăm không bé hơn 10 cm) - c - bằng cỡ đá 30 cm', None, None, None, None], [7, 'Lát đá 2 lớp trên lớp đá dăm hay sỏi lớp dưới đá cỡ 15cm, lớp trên 20 cm (lớp đá dăm không bé hơn 10 cm)', None, None, None, None], [8, 'Gia cố bằng bó thân cây hay cành cây trên nền đá đầm chặt (để gia cố tạm thời)', None, None, None, 2.5], [None, 'a - lớp gia cố 20 - 25 cm', None, None, None, None], [None, 'b - với chiều dày khác', None, None, None, None], [9, 'Gia cố mềm bằng thân cây:', 3, 3.5, '-', None], [None, 'a - khi chiều dày là 50 cm', None, None, None, None], [None, 'b - khi chiều dày khác', None, None, None, None], [10, 'Lát đá tảng 0.5 x 0.5 x 1.0 m', 5, 5.5, 6, None], [11, 'Lát đá khan bằng đá vôi có cường độ > 100 kg/cm2', 3.5, 4, 4.5, None], [12, 'Lát đá khan bằng đá vôi có cường độ > 300 kg/cm2', 8, 10, 12, None], [13, 'Gia cố bằng lớp áo BT - Mác 200', 8, 9, 10, None], [None, 'Gia cố bằng lớp áo BT - Mác 150', 7, 8, 9, None], [None, 'Gia cố bằng lớp áo BT - Mác 100', 6, 7, 7.5, None], [14, 'Máng gỗ nhẵn, móng chắc chắn, dòng nước chảy theo thớ gỗ', 10, 12, 14, None], [15, 'Máng BT có trát nhẵn mặt - Mác 200', 16, 19, 20, None], [None, 'Máng BT có trát nhẵn mặt - Mác 150', 14, 16, 18, None], [None, 'Máng BT có trát nhẵn mặt - Mác 100', 12, 13, 15, None]]}

REGIONS = ["I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII","XIII","XIV","XV","XVI","XVII","XVIII"]
SOILS = ["II","III","IV","V"]

# Bảng 4 - m_sd theo workbook
MSD_TABLE = {
    "Cỏ thưa": [0.50, 0.40, 0.30, 0.20],
    "Trung bình": [None, 0.30, 0.25, 0.15],
    "Cỏ dày": [None, 0.25, 0.20, 0.10],
}

# Bảng 5 - m_ls
MLS_TABLE = [
    ("Sông đồng bằng ổn định, lòng sông khá sạch, suối không có nước thường xuyên chảy trong điều kiện tương đối thuận lợi.", 11),
    ("Sông lớn và trung bình, quanh co, bị tắc nghẽn, lòng sông có cỏ mọc, có đá, chảy không lặng, suối không có nước thường xuyên, mùa lũ dòng nước cuốn theo nhiều sỏi cuội, bùn cát.", 9),
    ("Sông vùng núi, lòng sông nhiều đá, mặt nước không phẳng, suối chảy không thường xuyên, quanh co, lòng sông tắc nghẽn.", 7),
]

# Bảng 6 - delta
DELTA_TABLE = {
    "hạ lưu": ([2,4,6,8,10,15,20,30,40,50], [1,0.85,0.75,0.65,0.55,0.5,0.4,0.35,0.2,0.15,0.1]),
    "thượng lưu": ([2,4,6,8,10,15,20,30,40,50], [1,0.95,0.9,0.85,0.8,0.75,0.65,0.55,0.45,0.35,0.25]),
}

# ============================================================
# HÀM TOÁN
# ============================================================

def num(v, name="Giá trị"):
    try:
        x=float(str(v).replace(",", ".").strip())
    except Exception:
        raise ValueError(f"{name} không phải số.")
    if not math.isfinite(x):
        raise ValueError(f"{name} không hợp lệ.")
    return x

def pos(v, name):
    x=num(v,name)
    if x<=0:
        raise ValueError(f"{name} phải > 0.")
    return x

def interp1(x, xs, ys):
    if x<=xs[0]: return float(ys[0])
    if x>=xs[-1]: return float(ys[-1])
    for i in range(1,len(xs)):
        if x<=xs[i]:
            x1,x2=xs[i-1],xs[i]
            y1,y2=ys[i-1],ys[i]
            return y1+(y2-y1)*(x-x1)/(x2-x1)
    return float(ys[-1])

def bilinear(x,y,xs,ys,z):
    # z theo thứ tự [y][x]
    x=max(min(float(x),float(xs[-1])),float(xs[0]))
    y=max(min(float(y),float(ys[-1])),float(ys[0]))

    def bracket(v, arr):
        if v<=arr[0]: return 0,0
        if v>=arr[-1]: return len(arr)-1,len(arr)-1
        for i in range(1,len(arr)):
            if v<=arr[i]: return i-1,i
        return len(arr)-1,len(arr)-1

    j1,j2=bracket(x,xs)
    i1,i2=bracket(y,ys)

    if i1==i2 and j1==j2:
        return float(z[i1][j1])
    if i1==i2:
        return interp1(x,xs,z[i1])
    if j1==j2:
        return interp1(y,ys,[row[j1] for row in z])

    r1=interp1(x,[xs[j1],xs[j2]],[z[i1][j1],z[i1][j2]])
    r2=interp1(x,[xs[j1],xs[j2]],[z[i2][j1],z[i2][j2]])
    return interp1(y,[ys[i1],ys[i2]],[r1,r2])

# ============================================================
# BẢNG A.1 - PHI
# ============================================================

def lookup_phi(soil, hp, F):
    rows=[r for r in A1["rows"] if r[0]==soil]
    if not rows:
        raise ValueError(f"Không có cấp đất {soil} trong Bảng A.1.")
    rows=sorted(rows,key=lambda x:x[1])
    ys=[r[1] for r in rows]
    z=[r[2] for r in rows]
    return bilinear(F,hp,A1["F"],ys,z)

# ============================================================
# BẢNG A.2 - tsd
# ============================================================

def lookup_tsd(region, phi_sd):
    if region not in A2["regions"]:
        raise ValueError("Vùng mưa không có trong Bảng A.2.")
    return interp1(phi_sd,A2["phi"],A2["regions"][region])

# ============================================================
# BẢNG A.3 - Ap
# ============================================================

def lookup_ap(region, tsd, phi_ls):
    rows=A3["regions"][region]
    ts=[float(r[0]) for r in rows]
    z=[r[1] for r in rows]
    return bilinear(phi_ls,tsd,A3["phi_ls"],ts,z)

# ============================================================
# THỐNG KÊ MƯA
# ============================================================

def rainfall_stats(values):
    """Thống kê mẫu cho chuỗi mưa cực trị năm.

    Cs dùng hệ số hiệu chỉnh mẫu:
        Cs = n/[(n-1)(n-2)] * Σ[(Xi-Xbar)/S]^3
    """
    x=[]
    for v in values:
        try:
            q=float(v)
        except Exception:
            continue
        if math.isfinite(q) and q>0:
            x.append(q)
    n=len(x)
    if n<3:
        raise ValueError("Cần ít nhất 3 năm số liệu mưa dương.")
    mean=sum(x)/n
    s=math.sqrt(sum((v-mean)**2 for v in x)/(n-1))
    if s <= 0:
        raise ValueError("Chuỗi mưa không có độ phân tán (S=0), không thể tính tần suất Pearson III.")
    cv=s/mean
    cs=(n/((n-1)*(n-2)))*sum(((v-mean)/s)**3 for v in x)
    # Độ lệch mẫu không chệch theo moment bậc 3.
    return {"n":n,"mean":mean,"std":s,"cv":cv,"cs":cs,"min":min(x),"max":max(x),"values":x}

def hp_pearson3(mean,cv,cs,p):
    """Tính Hp theo Pearson III như mô-đun phân tích tần suất bổ trợ.

    TCVN 9845:2013 yêu cầu Hp% là lượng mưa ngày lớn nhất ứng với P% và
    yêu cầu cập nhật chuỗi mưa; tiêu chuẩn không quy định trong Điều 5.2
    một thuật toán duy nhất để khớp Pearson III/Gumbel. Vì vậy kết quả của
    hàm này phải được xem là bước xác định Hp từ chuỗi quan trắc, sau đó
    mới đưa Hp vào công thức Qp của TCVN 9845.

    scipy.stats.pearson3 dùng tham số skew là hệ số lệch Cs chuẩn hóa,
    phù hợp với Cs tính từ chuỗi mẫu ở trên. Xác suất dùng là F(X)=1-P/100
    vì P là tần suất vượt quá của trị số cực đại.
    """
    if not SCIPY_OK:
        raise RuntimeError("Cần scipy để tính Pearson III. Cài: pip install scipy")
    if not (0 < p < 100):
        raise ValueError("P phải nằm trong khoảng 0 < P < 100%.")
    if mean<=0 or cv<=0:
        raise ValueError("X̄ và Cv phải > 0 để tính Pearson III.")
    q=1.0-p/100.0
    phi=float(pearson3.ppf(q,skew=float(cs)))
    kp=1.0+float(cv)*phi
    hp=float(mean)*kp
    if not math.isfinite(hp) or hp<=0:
        raise ValueError(f"Hp không hợp lệ tại P={p:g}% (Kp={kp:.6g}). Kiểm tra chuỗi mưa/Cv/Cs.")
    return hp,kp,phi

def hp_gumbel(mean,cv,p):
    """Gumbel-I theo moment: beta=S*sqrt(6)/pi, a=mean-gamma*beta."""
    if not SCIPY_OK:
        raise RuntimeError("Cần scipy để tính Gumbel. Cài: pip install scipy")
    if not (0 < p < 100):
        raise ValueError("P phải nằm trong khoảng 0 < P < 100%.")
    s=float(cv)*float(mean)
    if s<=0:
        raise ValueError("S phải > 0 để tính Gumbel.")
    beta=s*math.sqrt(6)/math.pi
    loc=float(mean)-0.5772156649015329*beta
    hp=float(gumbel_r.ppf(1-p/100.0,loc=loc,scale=beta))
    if not math.isfinite(hp) or hp<=0:
        raise ValueError(f"Hp Gumbel không hợp lệ tại P={p:g}%.")
    return hp,hp/mean

def empirical_frequency(values):
    """Tần suất thực nghiệm Weibull cho chuỗi cực trị năm.
    Pm = m/(n+1)*100, m=1 là giá trị lớn nhất.
    """
    vals=sorted([float(v) for v in values if float(v)>0], reverse=True)
    n=len(vals)
    return [(i, vals[i-1], 100.0*i/(n+1.0)) for i in range(1,n+1)]


def frequency_diagnostics(values, method, ps=(0.1,0.2,0.5,1,2,4,5,10,20,50)):
    """Kiểm tra nhanh tính hợp lý của đường tần suất trước khi dùng cho Qp."""
    s=rainfall_stats(values)
    out=[]
    last=None
    for p in ps:
        if method=="Pearson III":
            hp,kp,_=hp_pearson3(s["mean"],s["cv"],s["cs"],p)
        else:
            hp,kp=hp_gumbel(s["mean"],s["cv"],p)
        if last is not None and hp > last:
            raise ValueError("Đường tần suất không đơn điệu: Hp phải tăng khi P giảm.")
        out.append((p,hp,kp))
        last=hp
    return s,out

# ============================================================
# TÍNH TCVN 9845 - F < 100 km2
# ============================================================

def calc_hydro(hp,p,F,L,suml,Jlv,Jsd,mls,msd,delta,soil,region,n_slope):
    if F>=100:
        raise ValueError("F >= 100 km²: không dùng công thức cường độ giới hạn (8). Cần chuyển sang phương pháp phù hợp tại Điều 5.3 TCVN 9845:2013.")
    if min(F,L,suml,Jlv,Jsd,mls,msd,hp)<=0:
        raise ValueError("Các thông số F, L, Σl, Jlv, Jsd, mls, msd, Hp phải > 0.")
    if not (0<delta<=1):
        raise ValueError("δ phải trong (0;1].")
    phi=lookup_phi(soil,hp,F)
    c=0.9 if n_slope==1 else 1.8
    Lsd=1000*F/(c*(L+suml))
    phi_sd=(Lsd**0.6)/(msd*(Jsd**0.3)*((phi*hp)**0.4))
    tsd=lookup_tsd(region,phi_sd)
    phi_ls=1000*L/(mls*(Jlv**(1/3))*((F*phi*hp)**0.25))
    Ap=lookup_ap(region,tsd,phi_ls)
    Q=Ap*phi*hp*F*delta
    return {
        "P":p,"Hp":hp,"F":F,"L":L,"suml":suml,"Jlv":Jlv,"Jsd":Jsd,
        "mls":mls,"msd":msd,"delta":delta,"soil":soil,"region":region,
        "n_slope":n_slope,"phi":phi,"Lsd":Lsd,"phi_sd":phi_sd,
        "tsd":tsd,"phi_ls":phi_ls,"Ap":Ap,"Qp":Q
    }

# ============================================================
# THỦY LỰC CẦU - THEO CÔNG THỨC TRONG WORKBOOK
# ============================================================

def m_for_abutment(name):
    mapping={
        "N.A Slovinski (Mố nhẹ)":0.32,
        "Mố tường cánh":0.35,
        "Mố chữ U":0.34,
        "Mố chân dê":0.32
    }
    return mapping[name]

def bridge8(m):
    rows=BRIDGE["b8"]
    # J=m, K-L-M-N-O-P-Q; workbook dùng VLOOKUP theo m.
    for row in rows:
        if abs(float(row[0])-m)<1e-12:
            return {
                "m":float(row[0]),
                # Bảng 8 trong workbook có bố cục tiêu đề lệch cột.
                # Các công thức Excel thực tế dùng: k1=M, N=L, Y2=Q.
                "K":float(row[1]), "L":float(row[2]),
                "k1":float(row[3]), "N":float(row[2]),
                "a":float(row[4]), "Y":float(row[5]),
                "Y2":float(row[7]), "formula_H_coeff":float(row[7]), "check_coeff":float(row[4])
            }
    raise ValueError("Không tìm thấy m trong Bảng 8.")

def calc_bridge_free(Q,m,h0,Vcp,Lnc):
    b=bridge8(m)
    sigma=1.0
    # Công thức G128 trong workbook:
    H=b["Y2"]*Vcp**2/(sigma*9.81*b["N"])
    Lc=Q/(sigma*m*(H**1.5)*math.sqrt(2*9.81))
    if Lnc is None or Lnc<=0:
        Lnc=Lc
    H1=H*(Lc/Lnc)**(2/3)
    htt=b["k1"]*H1
    Vt=Q/(htt*Lnc)
    check1=h0 <= b["check_coeff"]*H
    check2=h0 <= b["check_coeff"]*H1
    return {
        "m":m,"k1":b["k1"],"N":b["N"],"a":b["a"],"Y":b["Y"],"Y2":b["Y2"],"Y2_formula":b["formula_H_coeff"],"check_coeff":b["check_coeff"],
        "sigma":sigma,"H":H,"Lc":Lc,"Lnc":Lnc,"H1":H1,"htt":htt,
        "Vt":Vt,"Vcp":Vcp,"free_initial":check1,"free_final":check2
    }

# ============================================================
# GIAO DIỆN
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TÍNH TOÁN THỦY VĂN - THỦY LỰC CẦU NHỎ | TCVN 9845:2013 | V5")
        self.geometry("1380x900")
        self.minsize(1180,760)

        self.rain_records=[]
        self.rain_stats=None
        self.rain_results=[]
        self.hydro=None
        self.bridge=None

        self.vars={}
        self._make_vars()
        self._style()
        self._build()

    def _style(self):
        style=ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("TNotebook.Tab",font=("Segoe UI",10,"bold"),padding=(14,7))
        style.configure("TLabelframe.Label",font=("Segoe UI",10,"bold"))
        style.configure("Treeview",font=("Segoe UI",9),rowheight=27)
        style.configure("Treeview.Heading",font=("Segoe UI",9,"bold"))
        style.map("Treeview",background=[("selected","#dbeafe")],foreground=[("selected","#111827")])

    def _make_vars(self):
        d={
            "P":"4","method":"Pearson III","hp":"","region":"XII","soil":"III",
            "F":"5.78","L":"6.91","suml":"1.39","Jlv":"50","Jsd":"95",
            "mls":"7","msd":"0.25","delta":"1","n_slope":"2",
            "h0":"1.15","abutment":"Mố chữ U","Vcp":"4","Lnc":"18",
        }
        for k,v in d.items(): self.vars[k]=tk.StringVar(value=v)

    def _build(self):
        head=ttk.Frame(self,padding=8); head.pack(fill="x")
        ttk.Label(head,text="PHẦN MỀM TÍNH TOÁN THỦY VĂN - THỦY LỰC CẦU NHỎ",
                  font=("Segoe UI",17,"bold")).pack(side="left")
        ttk.Label(head,text="V5 • BẢNG TRA ĐÃ NHÚNG",foreground="darkgreen",
                  font=("Segoe UI",10,"bold")).pack(side="right")

        nb=ttk.Notebook(self); nb.pack(fill="both",expand=True,padx=8,pady=5)
        self.t_rain=ttk.Frame(nb); self.t_hydro=ttk.Frame(nb); self.t_bridge=ttk.Frame(nb); self.t_tables=ttk.Frame(nb)
        nb.add(self.t_rain,text="1. Số liệu mưa & tần suất")
        nb.add(self.t_hydro,text="2. Tính Qp theo TCVN 9845")
        nb.add(self.t_bridge,text="3. Thủy lực cầu nhỏ")
        nb.add(self.t_tables,text="4. Bảng tra tích hợp")

        self.build_rain()
        self.build_hydro()
        self.build_bridge()
        self.build_tables()

    def entry(self,parent,row,col,label,key,width=14):
        ttk.Label(parent,text=label).grid(row=row,column=col,sticky="w",padx=5,pady=4)
        ttk.Entry(parent,textvariable=self.vars[key],width=width).grid(row=row,column=col+1,sticky="ew",padx=5,pady=4)

    # ---------------- Rain ----------------
    def build_rain(self):
        top=ttk.Frame(self.t_rain,padding=12); top.pack(fill="both",expand=True)

        title=ttk.Frame(top); title.pack(fill="x",pady=(0,8))
        ttk.Label(title,text="PHÂN TÍCH CHUỖI MƯA VÀ XÁC ĐỊNH HP%",
                  font=("Segoe UI",15,"bold")).pack(side="left")
        self.rain_status=ttk.Label(title,text="● Chưa có chuỗi mưa",foreground="#9a6700",
                                   font=("Segoe UI",10,"bold")); self.rain_status.pack(side="right")

        pan=ttk.Panedwindow(top,orient="horizontal"); pan.pack(fill="both",expand=True)
        left=ttk.Frame(pan); right=ttk.Frame(pan)
        pan.add(left,weight=1); pan.add(right,weight=2)

        inp=ttk.LabelFrame(left,text="① Chuỗi lượng mưa ngày lớn nhất năm",padding=10); inp.pack(fill="both",expand=True,padx=(0,6))
        ttk.Label(inp,text="Nhập: Năm [Tab/space/;] Hp_max (mm). Dùng được cả 245,3 và 245.3.",foreground="#555").pack(anchor="w")
        self.rain_text=tk.Text(inp,height=24,width=42,font=("Consolas",10),undo=True)
        self.rain_text.pack(fill="both",expand=True,pady=6)
        self.rain_text.insert("1.0","2010\t245\n2011\t312\n2012\t268\n2013\t291\n2014\t337\n2015\t285\n2016\t301\n2017\t355\n2018\t279\n2019\t326\n2020\t310")
        bb=ttk.Frame(inp); bb.pack(fill="x")
        ttk.Button(bb,text="TÍNH THỐNG KÊ",command=self.calc_rain).pack(side="left",padx=3)
        ttk.Button(bb,text="Nạp CSV/TXT/Excel",command=self.load_rain_file).pack(side="left",padx=3)
        ttk.Button(bb,text="Xóa",command=lambda:self.rain_text.delete("1.0","end")).pack(side="left",padx=3)

        # Thống kê + lựa chọn P
        stat=ttk.LabelFrame(right,text="② Thống kê mẫu",padding=10); stat.pack(fill="x",padx=(6,0))
        self.stat_label=ttk.Label(stat,text="Chưa tính",justify="left",font=("Consolas",10)); self.stat_label.pack(anchor="w")

        sel=ttk.LabelFrame(right,text="③ Chọn phân phối và tần suất thiết kế",padding=10); sel.pack(fill="x",pady=8,padx=(6,0))
        ttk.Label(sel,text="Phân phối").grid(row=0,column=0,padx=5,pady=4,sticky="w")
        method=ttk.Combobox(sel,textvariable=self.vars["method"],values=["Pearson III","Gumbel"],state="readonly",width=18)
        method.grid(row=0,column=1,padx=5); method.bind("<<ComboboxSelected>>",lambda e:self.calc_rain() if self.rain_stats else None)
        ttk.Label(sel,text="P (%)").grid(row=0,column=2,padx=5)
        self.p_combo=ttk.Combobox(sel,textvariable=self.vars["P"],values=["0.1","0.2","0.5","1","2","4","5","10","20","50"],width=10)
        self.p_combo.grid(row=0,column=3,padx=5); self.p_combo.bind("<<ComboboxSelected>>",lambda e:self.select_p())
        ttk.Button(sel,text="ÁP DỤNG P",command=self.select_p).grid(row=0,column=4,padx=6)
        ttk.Label(sel,text="Hp thiết kế:",font=("Segoe UI",10,"bold")).grid(row=1,column=0,padx=5,pady=8,sticky="w")
        self.hp_label=ttk.Label(sel,text="—",font=("Segoe UI",18,"bold"),foreground="#005cc5"); self.hp_label.grid(row=1,column=1,padx=5,sticky="w")
        ttk.Label(sel,text="mm").grid(row=1,column=2,sticky="w")
        ttk.Label(sel,text="Kp =").grid(row=1,column=3,sticky="e")
        self.kp_label=ttk.Label(sel,text="—",font=("Consolas",11,"bold")); self.kp_label.grid(row=1,column=4,sticky="w")
        self.freq_note=ttk.Label(sel,text="",foreground="#555",wraplength=700); self.freq_note.grid(row=2,column=0,columnspan=5,sticky="w",pady=3)

        # Hai bảng song song theo chiều dọc
        f1=ttk.LabelFrame(right,text="④ Bảng tần suất lý thuyết — dùng để liên kết sang Qp",padding=6); f1.pack(fill="both",expand=True,padx=(6,0),pady=(0,6))
        self.freq_tree=ttk.Treeview(f1,columns=("P","T","Hp","Kp"),show="headings",height=8)
        for c,t,w in [("P","P (%)",100),("T","Chu kỳ T (năm)",140),("Hp","Hp(P) (mm)",150),("Kp","Kp",120)]:
            self.freq_tree.heading(c,text=t); self.freq_tree.column(c,width=w,anchor="center")
        self.freq_tree.pack(fill="both",expand=True); self.freq_tree.bind("<Double-1>",self.freq_click)

        f2=ttk.LabelFrame(right,text="⑤ Tần suất thực nghiệm (Weibull) — kiểm tra chuỗi",padding=6); f2.pack(fill="both",expand=True,padx=(6,0))
        self.emp_tree=ttk.Treeview(f2,columns=("rank","x","p"),show="headings",height=7)
        for c,t,w in [("rank","Thứ hạng m",100),("x","Hp quan trắc (mm)",180),("p","P thực nghiệm (%)",170)]:
            self.emp_tree.heading(c,text=t); self.emp_tree.column(c,width=w,anchor="center")
        self.emp_tree.pack(fill="both",expand=True)

    def parse_rain(self):
        """Đọc chuỗi mưa robust với cả dấu thập phân . và ,.

        Hỗ trợ:
        - Năm<TAB>Hp
        - Năm;Hp
        - Năm,Hp khi số thập phân dùng dấu chấm
        - Chỉ một cột Hp
        """
        raw=self.rain_text.get("1.0","end").strip()
        if not raw:
            raise ValueError("Chưa nhập chuỗi mưa.")
        rec=[]
        for line_no,line in enumerate(raw.splitlines(),1):
            line=line.strip()
            if not line or line.startswith('#'):
                continue
            # Ưu tiên tab/semicolon; nếu có dấu tab/; thì coi đó là cột.
            if '\t' in line or ';' in line:
                parts=[x.strip() for x in re.split(r'[;\t]+',line) if x.strip()]
            else:
                # Trường hợp "2010 245,3" hoặc "2010 245.3"
                parts=line.split()
                # Trường hợp "2010,245.3" hoặc "2010,245" -> dấu phẩy là phân cách cột
                if len(parts)==1 and ',' in parts[0]:
                    bits=parts[0].split(',')
                    if len(bits)==2 and re.fullmatch(r'\d{4}',bits[0].strip()):
                        parts=bits
                    elif re.fullmatch(r'[-+]?\d+(?:,\d+)?',parts[0].strip()):
                        parts=[parts[0].replace(',','.')]
                    else:
                        parts=[x.strip() for x in bits if x.strip()]
            nums=[]
            for token in parts:
                token=token.strip()
                try:
                    nums.append(float(token.replace(',','.')))
                except Exception:
                    # Bỏ tiêu đề chữ, không coi là lỗi.
                    continue
            if len(nums)>=2:
                rec.append((nums[0],nums[1]))
            elif len(nums)==1:
                rec.append((len(rec)+1,nums[0]))
        if len(rec)<3:
            raise ValueError("Không đọc được ít nhất 3 giá trị mưa hợp lệ. Kiểm tra định dạng dữ liệu.")
        vals=[r[1] for r in rec]
        return rec,vals

    def calc_rain(self):
        try:
            self.rain_records,vals=self.parse_rain()
            self.rain_stats=rainfall_stats(vals)
            s=self.rain_stats
            self.stat_label.config(text=(
                f"N = {s['n']} năm     X̄ = {s['mean']:.3f} mm     S = {s['std']:.3f} mm\n"
                f"Cv = {s['cv']:.5f}        Cs = {s['cs']:.5f}\n"
                f"Min = {s['min']:.2f} mm     Max = {s['max']:.2f} mm"
            ))
            warn = ""
            if s["n"] < 10:
                warn = "  ⚠ Chuỗi < 10 năm: Cs và các giá trị tần suất xa trung bình có độ bất định lớn."
            self.freq_note.config(text=(
                f"Đã đọc {s['n']} giá trị. Phân phối: {self.vars['method'].get()}. "
                "P là tần suất vượt quá của trị số cực đại năm." + warn
            ))
            for item in self.freq_tree.get_children(): self.freq_tree.delete(item)
            for p in [0.1,0.2,0.5,1,2,4,5,10,20,50]:
                hp,kp=self._hp(p)
                self.freq_tree.insert("", "end", values=(f"{p:g}",f"{100/p:.1f}",f"{hp:.3f}",f"{kp:.5f}"))
            self.emp_tree.delete(*self.emp_tree.get_children())
            for rank, value, pe in empirical_frequency(vals):
                self.emp_tree.insert("", "end", values=(rank,f"{value:.3f}",f"{pe:.3f}"))
            self.select_p()
        except Exception as e:
            messagebox.showerror("Lỗi tính tần suất",str(e))

    def _hp(self,p):
        if not self.rain_stats: raise ValueError("Hãy tính thống kê chuỗi mưa trước.")
        s=self.rain_stats
        if self.vars["method"].get()=="Pearson III":
            hp,kp,_=hp_pearson3(s["mean"],s["cv"],s["cs"],p)
        else:
            hp,kp=hp_gumbel(s["mean"],s["cv"],p)
        return hp,kp

    def select_p(self):
        try:
            p=num(self.vars["P"].get(),"P")
            hp,kp=self._hp(p)
            self.vars["hp"].set(f"{hp:.6f}")
            self.hp_label.config(text=f"{hp:.3f}")
            self.kp_label.config(text=f"{kp:.5f}")
            self.calc_hydro(silent=True)
        except Exception as e:
            if self.rain_stats:
                messagebox.showerror("Không xác định được Hp",str(e))

    def freq_click(self,event):
        item=self.freq_tree.identify_row(event.y)
        if item:
            p=self.freq_tree.item(item,"values")[0]
            self.vars["P"].set(p); self.select_p()

    def load_rain_file(self):
        p=filedialog.askopenfilename(filetypes=[("CSV/TXT","*.csv *.txt"),("Excel","*.xlsx *.xlsm"),("Tất cả","*.*")])
        if not p:return
        try:
            rows=[]
            if p.lower().endswith((".xlsx",".xlsm")):
                try:
                    import openpyxl
                except ImportError:
                    raise RuntimeError("Cần openpyxl để đọc Excel. Cài: pip install openpyxl")
                wb=openpyxl.load_workbook(p,data_only=True)
                ws=wb.active
                for row in ws.iter_rows(values_only=True):
                    numeric=[]
                    for v in row:
                        if isinstance(v,(int,float)) and math.isfinite(v): numeric.append(float(v))
                    if len(numeric)>=2:
                        # Giả định cột đầu là năm, cột kế tiếp là Hp.
                        rows.append((numeric[0],numeric[1]))
                    elif len(numeric)==1:
                        rows.append((len(rows)+1,numeric[0]))
            else:
                # Đọc toàn bộ TXT/CSV rồi phân tích một lần. Không gọi parse_rain()
                # theo từng dòng vì parser yêu cầu tối thiểu 3 giá trị cho cả chuỗi.
                with open(p,"r",encoding="utf-8-sig",newline="") as f:
                    raw=f.read()
                old=self.rain_text.get("1.0","end")
                try:
                    self.rain_text.delete("1.0","end")
                    self.rain_text.insert("1.0",raw)
                    rr,_=self.parse_rain()
                    rows.extend(rr)
                finally:
                    self.rain_text.delete("1.0","end")
                    self.rain_text.insert("1.0",old)
            if len(rows)<3:
                raise ValueError("File không chứa ít nhất 3 giá trị mưa hợp lệ.")
            self.rain_text.delete("1.0","end")
            self.rain_text.insert("1.0","\n".join(
                f"{int(y) if float(y).is_integer() else y}\t{r:g}" for y,r in rows
            ))
            self.calc_rain()
        except Exception as e:
            messagebox.showerror("Lỗi đọc chuỗi mưa",str(e))

    # ---------------- Hydro ----------------
    def build_hydro(self):
        frm=ttk.Frame(self.t_hydro,padding=12); frm.pack(fill="both",expand=True)
        head=ttk.Frame(frm); head.pack(fill="x")
        ttk.Label(head,text="TÍNH LƯU LƯỢNG ĐỈNH LŨ THEO TCVN 9845:2013",font=("Segoe UI",15,"bold")).pack(side="left")
        self.q_status=ttk.Label(head,text="● Chưa tính",foreground="#9a6700",font=("Segoe UI",10,"bold")); self.q_status.pack(side="right")
        inp=ttk.LabelFrame(frm,text="① Thông số lưu vực — Hp được lấy tự động từ tab Tần suất",padding=10); inp.pack(fill="x",pady=8)
        fields=[("P (%)","P"),("Hp (%) (mm)","hp"),("F (km²)","F"),("L (km)","L"),("Σl (km)","suml"),("Jlv (‰)","Jlv"),("Jsd (‰)","Jsd"),("mls","mls"),("msd","msd"),("δ","delta")]
        for i,(lab,key) in enumerate(fields): self.entry(inp,i//4,(i%4)*2,lab,key)
        ttk.Label(inp,text="Vùng mưa").grid(row=3,column=0,padx=5,pady=4,sticky="w")
        ttk.Combobox(inp,textvariable=self.vars["region"],values=REGIONS,state="readonly",width=12).grid(row=3,column=1,padx=5)
        ttk.Label(inp,text="Cấp đất").grid(row=3,column=2,padx=5,pady=4,sticky="w")
        ttk.Combobox(inp,textvariable=self.vars["soil"],values=SOILS,state="readonly",width=12).grid(row=3,column=3,padx=5)
        ttk.Label(inp,text="Sườn lưu vực").grid(row=3,column=4,padx=5,pady=4,sticky="w")
        ttk.Combobox(inp,textvariable=self.vars["n_slope"],values=["1","2"],state="readonly",width=12).grid(row=3,column=5,padx=5)
        ttk.Button(inp,text="TÍNH LẠI Qp",command=lambda:self.calc_hydro()).grid(row=3,column=7,padx=8)

        cards=ttk.Frame(frm); cards.pack(fill="x",pady=4)
        self.q_card=ttk.Label(cards,text="Qp\n— m³/s",anchor="center",font=("Segoe UI",14,"bold"),relief="groove",padding=10)
        self.q_card.pack(side="left",fill="x",expand=True,padx=3)
        self.phi_card=ttk.Label(cards,text="φ\n—",anchor="center",font=("Segoe UI",12,"bold"),relief="groove",padding=10); self.phi_card.pack(side="left",fill="x",expand=True,padx=3)
        self.ap_card=ttk.Label(cards,text="Ap\n—",anchor="center",font=("Segoe UI",12,"bold"),relief="groove",padding=10); self.ap_card.pack(side="left",fill="x",expand=True,padx=3)
        self.tsd_card=ttk.Label(cards,text="tsd\n— phút",anchor="center",font=("Segoe UI",12,"bold"),relief="groove",padding=10); self.tsd_card.pack(side="left",fill="x",expand=True,padx=3)

        box=ttk.LabelFrame(frm,text="② Chuỗi tính toán",padding=6); box.pack(fill="both",expand=True,pady=8)
        cols=("name","value","unit","formula","source")
        self.htree=ttk.Treeview(box,columns=cols,show="headings")
        for c,t,w in [("name","Thông số",180),("value","Giá trị",130),("unit","Đơn vị",90),("formula","Công thức",500),("source","Bảng/nguồn",190)]:
            self.htree.heading(c,text=t); self.htree.column(c,width=w)
        self.htree.pack(fill="both",expand=True)
        self.hmsg=ttk.Label(frm,text="",foreground="#116329",font=("Segoe UI",10,"bold")); self.hmsg.pack(anchor="w")

    def calc_hydro(self,silent=False):
        try:
            hp=pos(self.vars["hp"].get(),"Hp")
            p=num(self.vars["P"].get(),"P")
            r=calc_hydro(hp,p,pos(self.vars["F"].get(),"F"),pos(self.vars["L"].get(),"L"),
                         pos(self.vars["suml"].get(),"Σl"),pos(self.vars["Jlv"].get(),"Jlv"),
                         pos(self.vars["Jsd"].get(),"Jsd"),pos(self.vars["mls"].get(),"mls"),
                         pos(self.vars["msd"].get(),"msd"),num(self.vars["delta"].get(),"δ"),
                         self.vars["soil"].get(),self.vars["region"].get(),int(self.vars["n_slope"].get()))
            self.hydro=r
            self.htree.delete(*self.htree.get_children())
            rows=[
                ("P",r["P"],"%","Tần suất thiết kế đã chọn","Tần suất"),
                ("Hp%",r["Hp"],"mm","Hp(P) từ mô-đun tần suất","Tần suất"),
                ("φ",r["phi"],"-","Nội suy theo Hp và F","A.1"),
                ("Lsd",r["Lsd"],"m","1000F/[c(L+Σl)]","TCVN 9845"),
                ("Φsd",r["phi_sd"],"-","Lsd^0,6/[msd·Jsd^0,3·(φHp)^0,4]","TCVN 9845"),
                ("tsd",r["tsd"],"phút","Nội suy theo Φsd","A.2"),
                ("Φls",r["phi_ls"],"-","1000L/[mls·Jlv^(1/3)·(FφHp)^0,25]","TCVN 9845"),
                ("Ap%",r["Ap"],"-","Nội suy theo tsd và Φls","A.3"),
                ("Qp%",r["Qp"],"m³/s","Ap·φ·Hp·F·δ","TCVN 9845")]
            for a,b,c,d,e in rows:
                self.htree.insert("", "end", values=(a,f"{b:.8g}" if isinstance(b,float) else b,c,d,e))
            self.q_card.config(text=f"Qp\n{r['Qp']:.3f} m³/s")
            self.phi_card.config(text=f"φ\n{r['phi']:.5f}")
            self.ap_card.config(text=f"Ap\n{r['Ap']:.6f}")
            self.tsd_card.config(text=f"tsd\n{r['tsd']:.2f} phút")
            self.q_status.config(text="● Đã tính Qp",foreground="#116329")
            self.hmsg.config(text=f"✓ Đã liên kết P={p:g}% → Hp={hp:.3f} mm → Qp={r['Qp']:.4f} m³/s")
            if not silent: messagebox.showinfo("Hoàn thành",f"Qp = {r['Qp']:.4f} m³/s")
            return r
        except Exception as e:
            self.q_status.config(text="● Lỗi tính toán",foreground="#b42318")
            if not silent: messagebox.showerror("Lỗi tính thủy văn",str(e))
            else: raise

    # ---------------- Bridge ----------------
    def build_bridge(self):
        frm=ttk.Frame(self.t_bridge,padding=12); frm.pack(fill="both",expand=True)
        head=ttk.Frame(frm); head.pack(fill="x")
        ttk.Label(head,text="THỦY LỰC CẦU NHỎ",font=("Segoe UI",15,"bold")).pack(side="left")
        self.b_status=ttk.Label(head,text="● Chưa tính",foreground="#9a6700",font=("Segoe UI",10,"bold")); self.b_status.pack(side="right")
        inp=ttk.LabelFrame(frm,text="① Điều kiện thủy lực",padding=10); inp.pack(fill="x",pady=8)
        ttk.Label(inp,text="Loại mố").grid(row=0,column=0,padx=5,pady=5,sticky="w")
        ttk.Combobox(inp,textvariable=self.vars["abutment"],values=["N.A Slovinski (Mố nhẹ)","Mố tường cánh","Mố chữ U","Mố chân dê"],state="readonly",width=30).grid(row=0,column=1,padx=5)
        self.entry(inp,0,2,"h0 hạ lưu (m)","h0")
        self.entry(inp,0,4,"Vcp (m/s)","Vcp")
        ttk.Label(inp,text="Lnc chọn (m)").grid(row=1,column=0,padx=5,pady=5,sticky="w")
        ttk.Combobox(inp,textvariable=self.vars["Lnc"],values=["10","13","15","18","21","24","30"],width=15).grid(row=1,column=1,padx=5)
        ttk.Button(inp,text="TÍNH THỦY LỰC",command=self.calc_bridge).grid(row=1,column=4,padx=8)

        cards=ttk.Frame(frm); cards.pack(fill="x",pady=4)
        self.blc_card=ttk.Label(cards,text="Lc yêu cầu\n— m",anchor="center",font=("Segoe UI",13,"bold"),relief="groove",padding=10); self.blc_card.pack(side="left",fill="x",expand=True,padx=3)
        self.bh_card=ttk.Label(cards,text="H\n— m",anchor="center",font=("Segoe UI",13,"bold"),relief="groove",padding=10); self.bh_card.pack(side="left",fill="x",expand=True,padx=3)
        self.bv_card=ttk.Label(cards,text="Vt\n— m/s",anchor="center",font=("Segoe UI",13,"bold"),relief="groove",padding=10); self.bv_card.pack(side="left",fill="x",expand=True,padx=3)
        self.bcheck_card=ttk.Label(cards,text="Kiểm tra\n—",anchor="center",font=("Segoe UI",13,"bold"),relief="groove",padding=10); self.bcheck_card.pack(side="left",fill="x",expand=True,padx=3)

        box=ttk.LabelFrame(frm,text="② Kết quả và kiểm tra",padding=8); box.pack(fill="both",expand=True,pady=8)
        cols=("name","value","unit","meaning")
        self.btree=ttk.Treeview(box,columns=cols,show="headings")
        for c,t,w in [("name","Thông số",220),("value","Giá trị",150),("unit","Đơn vị",100),("meaning","Ý nghĩa / kiểm tra",650)]:
            self.btree.heading(c,text=t); self.btree.column(c,width=w)
        self.btree.pack(fill="both",expand=True)

    def calc_bridge(self):
        try:
            if not self.hydro: self.calc_hydro(silent=True)
            m=m_for_abutment(self.vars["abutment"].get())
            r=calc_bridge_free(self.hydro["Qp"],m,pos(self.vars["h0"].get(),"h0"),
                               pos(self.vars["Vcp"].get(),"Vcp"),pos(self.vars["Lnc"].get(),"Lnc"))
            self.bridge=r
            okv=r["Vt"]<=r["Vcp"]
            ok=(r["free_final"] and okv)
            self.btree.delete(*self.btree.get_children())
            rows=[
                ("Qp",self.hydro["Qp"],"m³/s","Lưu lượng thiết kế từ tab 2"),
                ("m",r["m"],"-","Hệ số lưu lượng theo loại mố"),
                ("N",r["N"],"-","Bảng 8"),
                ("k1",r["k1"],"-","Bảng 8"),
                ("Y2",r["Y2"],"-","Hệ số trong công thức H"),
                ("H",r["H"],"m","Cột nước tính toán"),
                ("Lc",r["Lc"],"m","Khẩu độ yêu cầu"),
                ("Lnc",r["Lnc"],"m","Khẩu độ được chọn"),
                ("H1",r["H1"],"m","Cột nước tương ứng Lnc"),
                ("htt",r["htt"],"m","Chiều sâu dòng qua khẩu độ"),
                ("Vt",r["Vt"],"m/s","Vận tốc tính toán"),
                ("Vcp",r["Vcp"],"m/s","Vận tốc cho phép"),
                ("h0 ≤ N·H1", "ĐẠT" if r["free_final"] else "KHÔNG ĐẠT", "", "Điều kiện chảy không ngập"),
                ("Vt ≤ Vcp", "ĐẠT" if okv else "KHÔNG ĐẠT", "", "Điều kiện vận tốc"),
                ("Kết luận kiểm tra", "ĐẠT" if ok else "CẦN KIỂM TRA", "", "Tổng hợp hai điều kiện trên"),
            ]
            for a,b,c,d in rows:
                val=f"{b:.8g}" if isinstance(b,float) else str(b)
                self.btree.insert("", "end", values=(a,val,c,d))
            self.blc_card.config(text=f"Lc yêu cầu\n{r['Lc']:.3f} m")
            self.bh_card.config(text=f"H\n{r['H']:.3f} m")
            self.bv_card.config(text=f"Vt\n{r['Vt']:.3f} m/s")
            self.bcheck_card.config(text=f"Kiểm tra\n{'ĐẠT' if ok else 'CẦN KIỂM TRA'}")
            self.b_status.config(text=("● Đạt kiểm tra" if ok else "● Cần kiểm tra lại"),foreground=("#116329" if ok else "#b42318"))
        except Exception as e:
            self.b_status.config(text="● Lỗi tính toán",foreground="#b42318")
            messagebox.showerror("Lỗi thủy lực",str(e))

    # ---------------- Tables viewer ----------------
    def build_tables(self):
        frm=ttk.Frame(self.t_tables,padding=8); frm.pack(fill="both",expand=True)
        bar=ttk.Frame(frm); bar.pack(fill="x")
        self.table_choice=tk.StringVar(value="Bảng A.1 - φ")
        ttk.Combobox(bar,textvariable=self.table_choice,
                     values=["Bảng A.1 - φ","Bảng A.2 - tsd","Bảng A.3 - Ap","Bảng 7 - m","Bảng 8 - cầu","Bảng 9 - chảy ngập","Bảng 10 - Vcp"],
                     state="readonly",width=30).pack(side="left")
        ttk.Button(bar,text="Hiển thị",command=self.show_table).pack(side="left",padx=5)
        self.tview=ttk.Treeview(frm,show="headings"); self.tview.pack(fill="both",expand=True,pady=8)

    def show_table(self):
        for it in self.tview.get_children(): self.tview.delete(it)
        for c in self.tview["columns"]: self.tview.heading(c,text="")
        name=self.table_choice.get()
        if name=="Bảng A.1 - φ":
            cols=["Cấp đất","Hp"]+[str(x) for x in A1["F"]]
            data=[(r[0],r[1],*r[2]) for r in A1["rows"]]
        elif name=="Bảng A.2 - tsd":
            cols=["Φsd"]+REGIONS
            data=[(x,*[A2["regions"][reg][i] for reg in REGIONS]) for i,x in enumerate(A2["phi"])]
        elif name=="Bảng A.3 - Ap":
            cols=["Vùng","tsd"]+[str(x) for x in A3["phi_ls"]]
            data=[]
            for reg in REGIONS:
                for ts,vals in A3["regions"][reg]: data.append((reg,ts,*vals))
        elif name=="Bảng 7 - m":
            cols=["Loại mố","m"]
            data=[("N.A Slovinski (Mố nhẹ)",.32),("Mố tường cánh",.35),("Mố chữ U",.34),("Mố chân dê",.32)]
        elif name=="Bảng 8 - cầu":
            cols=["m","k1","N","a","Y","Y2","Cột K","Cột L"]
            data=BRIDGE["b8"]
        elif name=="Bảng 9 - chảy ngập":
            cols=["n","m=.32: sng Kng Y2 q q1","m=.33: sng Kng Y2 q q1","m=.34: sng Kng Y2 q q1"]
            data=[]
            for row in BRIDGE["b9"]:
                data.append((row[0],str(row[1:6]),str(row[6:11]),str(row[11:16])))
        else:
            cols=["TT","Loại gia cố","0.4m","1m","2m","3m"]
            data=BRIDGE["b10"]
        self.tview["columns"]=tuple(f"c{i}" for i in range(len(cols)))
        for i,c in enumerate(cols):
            self.tview.heading(f"c{i}",text=str(c)); self.tview.column(f"c{i}",width=max(90,min(300, len(str(c))*9)))
        for row in data:
            self.tview.insert("", "end", values=row)

# ============================================================
# TIỆN ÍCH
# ============================================================

def re_split(line):
    # Giữ dấu phẩy trong số thập phân; hàm này chỉ còn dùng ở các đường đọc cũ.
    return [x for x in re.split(r"[;\t ]+",line.strip()) if x]


if __name__=="__main__":
    app=App()
    app.mainloop()
