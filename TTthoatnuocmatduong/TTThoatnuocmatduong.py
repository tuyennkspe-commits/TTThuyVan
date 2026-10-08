# -*- coding: utf-8 -*-
"""
HỆ THỐNG THIẾT KẾ & KIỂM TOÁN THỦY VĂN, THỦY LỰC THOÁT NƯỚC MẶT CẦU ĐƯỜNG (DESKTOP GUI PRO)
Phiên bản: Tổng quát áp dụng cho mọi dự án giao thông (Cao tốc, Đô thị, Cầu đường, Cống rãnh)
Tuân thủ: TCVN 7957:2023, TCVN 9845:2013, TCVN 5729:2012, 22 TCN 272-05 và FHWA HEC-22 / HEC-21
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import math
import json
import csv
import numpy as np
import pandas as pd

# Matplotlib nhúng Tkinter
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# Enable DPI awareness trên Windows
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

def parse_chainage(val):
    """Chuyển đổi chuỗi lý trình (Km0+100, 0+100, 100.5) về giá trị mét (float)"""
    if pd.isna(val) or val is None or str(val).strip() == '':
        return None
    s = str(val).strip().upper().replace("KM", "").replace(" ", "")
    if "+" in s:
        parts = s.split("+")
        try:
            km = float(parts[0]) if parts[0] else 0.0
            m = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
            return km * 1000.0 + m
        except:
            return None
    try:
        return float(s)
    except:
        return None

def format_chainage(val):
    """Định dạng lý trình cọc Km+m chuẩn ngành giao thông Việt Nam"""
    if pd.isna(val) or val == '' or val is None:
        return ""
    try:
        f = float(val)
        if f < 0: return f"{f:.2f}"
        km = int(f // 1000)
        m = f % 1000
        return f"{km}+{m:06.2f}"
    except:
        return str(val).strip()

# ==============================================================================
# 1. BỘ CÔNG THỨC THỦY VĂN & THỦY LỰC TỔNG QUÁT (TCVN 7957:2023 & HEC-22)
# ==============================================================================
class DrainageFormulas:
    @staticmethod
    def rain_intensity(A, C, P, t, b, n):
        """Cường độ mưa q (L/s.ha) và I (mm/h) theo TCVN 7957"""
        logP = math.log10(P) if P > 0 else 0
        if t + b <= 0: return 0.0, 0.0
        q = (A * (1.0 + C * logP)) / math.pow(t + b, n)
        I_mm_h = q * 0.36
        return q, I_mm_h

    @staticmethod
    def gutter_flow(T, Sx, SL, n):
        """Lưu lượng rãnh tam giác mép đường/cầu HEC-22: Q = (0.376 / n) * Sx^1.67 * SL^0.5 * T^2.67"""
        if SL <= 0: SL = 0.0001
        if Sx <= 0: Sx = 0.001
        if n <= 0: n = 0.013
        Q = (0.376 / n) * math.pow(Sx, 1.6667) * math.pow(SL, 0.5) * math.pow(T, 2.6667)
        depth = T * Sx
        area = 0.5 * T * depth
        V = Q / area if area > 0 else 0.0
        return Q, depth, V

    @staticmethod
    def spread_width(Q, Sx, SL, n):
        """Bề rộng vệt ngập nước T tính ngược từ lưu lượng dòng chảy rãnh Q (HEC-22)"""
        if SL <= 0: SL = 0.0001
        if Sx <= 0: Sx = 0.001
        if n <= 0: n = 0.013
        if Q <= 0: return 0.0
        factor = (Q * n) / (0.376 * math.pow(Sx, 1.6667) * math.pow(SL, 0.5))
        return math.pow(factor, 0.375)

    @staticmethod
    def grate_efficiency(W, T, V, Sx, Lg, Rf=0.8):
        """Hiệu suất thu của phễu ô lưới HEC-22 / HEC-21: E = Rf * Eo + (1 - Eo) * Rs"""
        if T <= 0: return 1.0, 1.0, 1.0, 1.0
        ratio_WT = min(1.0, W / T)
        Eo = 1.0 - math.pow(1.0 - ratio_WT, 2.67)
        denom = 1.0 + (0.0828 * math.pow(V, 1.8)) / (Sx * math.pow(Lg, 2.3)) if Sx * Lg > 0 else 1.0
        Rs = 1.0 / denom if denom > 0 else 0.0
        E = Rf * Eo + (1.0 - Eo) * Rs
        return ratio_WT, Eo, Rs, min(1.0, max(0.0, E))

    @staticmethod
    def downspout_sizing(Q_inlet, d, h_inlet=0.02):
        """Kích thước ống đứng phễu thu theo công thức Orifice (HEC-21):
           Q = 0.6 * Ax * sqrt(2*g*x) với x = d + h_inlet"""
        g = 9.81
        x = d + h_inlet
        v_head = math.sqrt(2.0 * g * x) if x > 0 else 0.0
        if v_head > 0 and Q_inlet > 0:
            Ax_req = Q_inlet / (0.6 * v_head)
            Dx_calc = math.sqrt(4.0 * Ax_req / math.pi)
        else:
            Dx_calc = 0.05
        Dx_rec = max(0.10, math.ceil(Dx_calc * 100) / 100.0)
        return x, Dx_calc, Dx_rec

    @staticmethod
    def collector_pipe_sizing(Q_tot, S_pipe=0.01, n_pipe=0.011):
        """Kích thước ống gom dọc nhịp dầm chảy đầy (Manning):
           Q = (1/n) * (D/4)^(2/3) * S^(1/2) * (pi*D^2/4)"""
        if S_pipe <= 0: S_pipe = 0.005
        if n_pipe <= 0: n_pipe = 0.011
        coeff = (1.0 / n_pipe) * math.pow(0.25, 2/3) * (math.pi / 4.0) * math.sqrt(S_pipe)
        Dv_calc = math.pow(Q_tot / coeff, 3/8) if coeff > 0 and Q_tot > 0 else 0.10
        if Dv_calc <= 0.15:
            Dv_rec = 0.15
        elif Dv_calc <= 0.20:
            Dv_rec = 0.20
        else:
            Dv_rec = 0.25
        return Dv_calc, Dv_rec

    @staticmethod
    def curb_inlet_efficiency(Q, SL, Sx, n, L_curb):
        """Chiều dài thu triệt để LT và hiệu suất E của cửa thu bó vỉa hàm ếch (HEC-22)"""
        if SL <= 0: SL = 0.0001
        if Sx <= 0: Sx = 0.001
        if n <= 0: n = 0.016
        if Q <= 0: return 0.0, 1.0
        LT = 0.817 * math.pow(Q, 0.42) * math.pow(SL, 0.3) * math.pow(1.0 / (n * Sx), 0.6)
        if L_curb >= LT:
            E = 1.0
        else:
            E = 1.0 - math.pow(1.0 - (L_curb / LT), 1.8)
        return LT, max(0.0, min(1.0, E))

    @staticmethod
    def channel_capacity(b, H, h, m1, m2, slope, n):
        """Khả năng thoát nước của rãnh hở hình thang/chữ nhật (Manning)"""
        if slope <= 0: slope = 0.001
        if n <= 0: n = 0.013
        A = (b + 0.5 * (m1 + m2) * h) * h
        P_w = b + h * (math.sqrt(1.0 + m1**2) + math.sqrt(1.0 + m2**2))
        R = A / P_w if P_w > 0 else 0.0
        V = (1.0 / n) * math.pow(R, 0.6667) * math.pow(slope, 0.5)
        Q = A * V
        return A, P_w, R, V, Q

    @staticmethod
    def circular_pipe_partial(D, h_D, slope, n):
        """Thủy lực cống tròn chảy đầy và bán phần (TCVN 7957 & Manning)"""
        if slope <= 0: slope = 0.001
        if n <= 0: n = 0.013
        h_D = min(1.0, max(0.01, h_D))
        h = h_D * D
        if h_D >= 0.999:
            A = math.pi * (D**2) / 4.0
            P_w = math.pi * D
            R = D / 4.0
            theta = 2.0 * math.pi
        else:
            val = 1.0 - 2.0 * h_D
            val = max(-1.0, min(1.0, val))
            theta = 2.0 * math.acos(val)
            A = (D**2 / 8.0) * (theta - math.sin(theta))
            P_w = (D / 2.0) * theta
            R = A / P_w if P_w > 0 else 0.0
        V = (1.0 / n) * math.pow(R, 0.6667) * math.pow(slope, 0.5)
        Q = A * V
        return h, theta, A, P_w, R, V, Q

    @staticmethod
    def calc_qyc_segment(L, B_width, Idg, SL, C, n, P, A_p, C_p, b_p, n_p):
        """Tính toán lưu lượng yêu cầu Qyc theo đúng hướng dẫn TCVN 7957 & Wenzel"""
        F = (L * B_width) / 10000.0  # Diện tích ha
        if Idg <= 0: Idg = 0.02
        B_oblique = B_width * math.sqrt(1.0 + (SL / Idg)**2)
        
        # Công thức thời gian chảy mặt to (phút) chuẩn xác theo Wenzel / TCVN 7957
        # to = [ 0.09 * (L * n)^0.6 ] / ( I^0.4 * i^0.3 ) -> Tích hợp dòng chảy mặt
        to = 3.26 * math.pow(L * n, 0.6) / (math.pow(max(0.001, SL), 0.3) * math.pow(200.0, 0.4))
        to = max(2.0, min(15.0, to)) # Giới hạn hợp lý thời gian chảy tràn bề mặt
        
        Vr = 8.355 * math.sqrt(max(0.0001, SL)) # Vận tốc trong rãnh m/s
        tr = (L / (60.0 * Vr)) * 1.26 if Vr > 0 else 1.0
        
        t_total = to + tr
        q, I = DrainageFormulas.rain_intensity(A_p, C_p, P, t_total, b_p, n_p)
        Q_own = (q * F * C) / 1000.0  # m3/s
        return F, B_oblique, to, tr, t_total, q, I, Q_own


# ==============================================================================
# 2. CƠ SỞ DỮ LIỆU BẢNG TRA TIÊU CHUẨN TOÀN QUỐC (TCVN 7957:2023)
# ==============================================================================
STATIONS_TABLE = [
    ("Hà Nội (Trạm Láng)", 5890.0, 0.650, 20.0, 0.84, "Đồng bằng Sông Hồng"),
    ("TP. Hồ Chí Minh (Tân Sơn Nhất)", 7290.0, 0.590, 32.0, 0.88, "Đông Nam Bộ"),
    ("Đà Nẵng", 2170.0, 0.520, 10.0, 0.65, "Miền Trung"),
    ("Hải Phòng", 5950.0, 0.550, 21.0, 0.82, "Đồng bằng Sông Hồng"),
    ("Cần Thơ", 9430.0, 0.550, 30.0, 0.90, "Đồng bằng Sông Cửu Long"),
    ("Tây Ninh", 7850.0, 0.385, 17.0, 0.78, "Đông Nam Bộ"),
    ("Hưng Yên", 8200.0, 0.370, 18.0, 0.80, "Đồng bằng Sông Hồng"),
    ("Bắc Ninh", 7920.0, 0.360, 17.5, 0.79, "Đồng bằng Sông Hồng"),
    ("Bảo Lộc", 8130.0, 0.580, 30.0, 0.85, "Tây Nguyên"),
    ("Bình Dương", 7923.0, 0.530, 30.0, 0.87, "Đông Nam Bộ"),
    ("Bắc Giang", 7650.0, 0.550, 28.0, 0.85, "Miền Bắc"),
    ("Bắc Quang", 8860.0, 0.570, 29.0, 0.82, "Hà Giang"),
    ("Buôn Mê Thuột", 8920.0, 0.580, 28.0, 0.89, "Tây Nguyên"),
    ("Cà Mau", 9210.0, 0.480, 25.0, 0.92, "Đồng bằng Sông Cửu Long"),
    ("Hà Nam", 4850.0, 0.510, 19.0, 0.80, "Đồng bằng Sông Hồng"),
    ("Hải Dương", 4260.0, 0.420, 18.0, 0.78, "Đồng bằng Sông Hồng"),
    ("Hoà Bình", 5500.0, 0.450, 19.0, 0.82, "Miền Bắc"),
    ("Huế", 2610.0, 0.550, 12.0, 0.55, "Thừa Thiên Huế"),
    ("Lào Cai", 6210.0, 0.580, 22.0, 0.84, "Miền Bắc"),
    ("Móng Cái", 4860.0, 0.460, 20.0, 0.79, "Quảng Ninh"),
    ("Nam Định", 4320.0, 0.550, 19.0, 0.79, "Đồng bằng Sông Hồng"),
    ("Nha Trang", 1810.0, 0.550, 12.0, 0.65, "Khánh Hoà"),
    ("Ninh Bình", 4930.0, 0.480, 19.0, 0.80, "Đồng bằng Sông Hồng"),
    ("Phan Thiết", 7070.0, 0.550, 25.0, 0.92, "Bình Thuận"),
    ("Pleiku", 8820.0, 0.490, 29.0, 0.92, "Gia Lai"),
    ("Quảng Ngãi", 2590.0, 0.580, 16.0, 0.67, "Miền Trung"),
    ("Quy Nhơn", 2610.0, 0.550, 14.0, 0.68, "Bình Định"),
    ("Thái Bình", 5220.0, 0.450, 19.0, 0.81, "Đồng bằng Sông Hồng"),
    ("Thái Nguyên", 7710.0, 0.520, 28.0, 0.85, "Miền Bắc"),
    ("Thanh Hoá", 3640.0, 0.530, 19.0, 0.72, "Bắc Trung Bộ"),
    ("Vinh", 3430.0, 0.550, 20.0, 0.69, "Bắc Trung Bộ"),
    ("Vũng Tàu", 8100.0, 0.510, 26.0, 0.86, "Đông Nam Bộ")
]

RUNOFF_COEFF_TABLE = [
    ("Mặt đường bê tông nhựa chặt (Asphalt)", 0.73, 0.77, 0.81, 0.86, 0.90, "Mặt đường cao tốc / cầu thông dụng"),
    ("Mặt đường bê tông xi măng (BTXM)", 0.80, 0.85, 0.88, 0.92, 0.95, "Độ nhẵn cao, thoát nước nhanh"),
    ("Mái nhà, công trình bê tông kín", 0.90, 0.95, 0.95, 0.95, 0.95, "Không thấm nước"),
    ("Mặt đường cấp phối đá dăm, gạch lát", 0.65, 0.70, 0.75, 0.80, 0.85, "Thấm vừa phải"),
    ("Mặt đường đá hộc chèn vữa xi măng", 0.50, 0.55, 0.60, 0.65, 0.70, "Độ nhám lớn"),
    ("Khu công viên, đất cây xanh (á sét)", 0.15, 0.20, 0.25, 0.30, 0.35, "Thảm thực vật giữ nước")
]

MANNING_ROUGHNESS_TABLE = [
    ("Ống nhựa gân xoắn uPVC / HDPE / PE", 0.0115, "0.009 - 0.012", "Ống gom treo dọc cầu, thoát nước ngầm"),
    ("Cống tròn & cống hộp bê tông cốt thép", 0.0140, "0.013 - 0.015", "Cống ngang đường, cống dọc tuyến chính"),
    ("Ống thép, ống gang đúc dẻo", 0.0120, "0.011 - 0.013", "Ống thoát nước treo vị trí chịu lực cao"),
    ("Mặt đường bê tông nhựa mới, lu lèn chặt", 0.0130, "0.012 - 0.014", "Dòng chảy mặt đường và rãnh biên"),
    ("Mặt đường bê tông nhựa cũ / nhám trung bình", 0.0160, "0.015 - 0.017", "Độ nhám do mài mòn khai thác"),
    ("Rãnh mép bê tông trát vữa xi măng láng", 0.0130, "0.012 - 0.014", "Rãnh thu nước mép lề đường")
]

SPREAD_LIMITS_TABLE = [
    ("Đường cao tốc - Thiết kế tiêu chuẩn (HEC-22)", "1.50 - 2.25", "Nước ngập trong phạm vi lề gia cố / dải an toàn, không ngập làn xe"),
    ("Đường cao tốc - Khống chế nghiêm ngặt (22 TCN 272-05)", "0.75", "Nước ngập hoàn toàn trong dải an toàn sát lan can"),
    ("Đường trục chính đô thị (V = 60 - 80 km/h)", "1.80 - 2.50", "Bề rộng ngập không quá 1/2 bề rộng làn xe ngoài cùng"),
    ("Đường gom, đường nội bộ (V <= 50 km/h)", "3.00", "Ngập tối đa 1 làn xe ngoài cùng, xe vẫn chạy làn trong an toàn")
]

GENERAL_DESIGN_RECOMMENDATIONS = [
    ("Đoạn đường dốc nhỏ / Đường cong lõm", "SL <= 0.40%", "Rộng 10 - 20m", "Lc = 2.0 - 2.5 m", "Dx >= 100mm", "Dv >= 150mm"),
    ("Đoạn dốc dọc thông thường", "SL = 0.50% - 1.50%", "Rộng 10 - 20m", "Lc = 4.0 - 5.0 m", "Dx >= 100mm", "Dv >= 150mm"),
    ("Đoạn dốc dọc lớn (dốc cầu dẫn, đèo dốc)", "SL >= 3.00%", "Rộng 10 - 20m", "Lc = 8.0 - 12.0 m", "Dx >= 100mm", "Dv >= 150mm"),
    ("Nhịp dầm liên tục / Nhịp dài (L = 60 - 80m)", "SL bất kỳ", "Rộng 10 - 25m", "Lc = 4.0 m", "Dx >= 100mm", "Dv >= 200mm")
]


# ==============================================================================
# 3. GIAO DIỆN PHẦN MỀM CHÍNH (UNIVERSAL DESKTOP APP)
# ==============================================================================
class DrainageApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phần Mềm Thiết Kế & Kiểm Toán Thoát Nước Mặt Cầu Đường (TCVN 7957 & HEC-22)")
        self.geometry("1400x900")
        self.minsize(1150, 780)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[10, 5])
        self.style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"), foreground="#0d47a1")

        self.project_name = tk.StringVar(value="Dự Án Thoát Nước Giao Thông")
        self.segments_data = []

        self._build_menu()
        self._build_ui()

    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="📄 Tạo Dự Án Mới", command=self.new_project)
        file_menu.add_command(label="📁 Mở Tệp Dự Án (JSON)", command=self.load_project)
        file_menu.add_command(label="💾 Lưu Tệp Dự Án (JSON)", command=self.save_project)
        file_menu.add_separator()
        file_menu.add_command(label="📥 Nạp Dữ Liệu Trạm Mưa Excel (.xlsx / .xls)", command=self.import_rainfall_excel)
        file_menu.add_command(label="📑 Nạp Danh Sách Phân Đoạn Tuyến Từ Excel", command=self.import_qyc_excel)
        file_menu.add_command(label="📊 Xuất Bảng Phân Đoạn Tuyến (CSV)", command=self.export_qyc_csv)
        file_menu.add_command(label="📊 Xuất Chuỗi Hố Thu Ra CSV", command=self.export_grates_csv)
        file_menu.add_separator()
        file_menu.add_command(label="❌ Thoát", command=self.quit)
        menubar.add_cascade(label="Tệp tin", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="📖 Mở Bảng tra Tiêu chuẩn Kỹ thuật", command=lambda: self.notebook.select(self.tab_lookup))
        menubar.add_cascade(label="Tra cứu & Tiêu chuẩn", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_info = (
            "1. TCVN 7957:2023: Thoát nước - Mạng lưới và công trình bên ngoài\n"
            "2. TCVN 9845:2013: Tính toán thủy văn thiết kế cầu cống\n"
            "3. TCVN 5729:2012: Đường ô tô cao tốc - Yêu cầu thiết kế\n"
            "4. 22 TCN 272-05: Tiêu chuẩn thiết kế cầu\n"
            "5. FHWA HEC No.22 (Third Edition): Urban Drainage Design Manual\n"
            "6. FHWA HEC No.21: Design of Bridge Deck Drainage"
        )
        help_menu.add_command(label="Cơ sở kỹ thuật & Tiêu chuẩn", command=lambda: messagebox.showinfo(
            "Cơ sở kỹ thuật & Tiêu chuẩn áp dụng", help_info
        ))
        menubar.add_cascade(label="Trợ giúp", menu=help_menu)
        self.config(menu=menubar)

    def _build_ui(self):
        top_bar = tk.Frame(self, bg="#0d47a1", height=42)
        top_bar.pack(fill="x", side="top")

        tk.Label(
            top_bar, text="DỰ ÁN:", bg="#0d47a1", fg="#ffeb3b", font=("Segoe UI", 10, "bold")
        ).pack(side="left", padx=(15, 5), pady=8)

        self.ent_proj_name = ttk.Entry(top_bar, textvariable=self.project_name, font=("Segoe UI", 10, "bold"), width=35)
        self.ent_proj_name.pack(side="left", pady=6)

        self.lbl_current_station = tk.Label(
            top_bar, text="Trạm mưa: Hà Nội (Trạm Láng)", 
            bg="#1565c0", fg="white", font=("Segoe UI", 9, "bold"), padx=10, pady=2
        )
        self.lbl_current_station.pack(side="right", padx=15)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=6)

        self.tab_hydrology = ttk.Frame(self.notebook)
        self.tab_qyc = ttk.Frame(self.notebook)
        self.tab_bridge_deck = ttk.Frame(self.notebook)
        self.tab_grate_series = ttk.Frame(self.notebook)
        self.tab_curb_inlet = ttk.Frame(self.notebook)
        self.tab_pipes_gutters = ttk.Frame(self.notebook)
        self.tab_lookup = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_hydrology, text=" 1. Khí tượng & Đường cong IDF ")
        self.notebook.add(self.tab_qyc, text=" 2. Lưu lượng thiết kế Qyc ")
        self.notebook.add(self.tab_bridge_deck, text=" 3. Phễu thu Mặt cầu / Mặt đường ")
        self.notebook.add(self.tab_grate_series, text=" 4. Chuỗi Cửa thu & Vệt ngập ")
        self.notebook.add(self.tab_curb_inlet, text=" 5. Cửa thu Bó vỉa ")
        self.notebook.add(self.tab_pipes_gutters, text=" 6. Cống thoát nước & Rãnh ")
        self.notebook.add(self.tab_lookup, text=" 7. Thư viện Tiêu chuẩn ")

        self._init_tab_hydrology()
        self._init_tab_qyc()
        self._init_tab_bridge_deck()
        self._init_tab_grate_series()
        self._init_tab_curb_inlet()
        self._init_tab_pipes_gutters()
        self._init_tab_lookup()

    # --------------------------------------------------------------------------
    # TAB 1: KHÍ TƯỢNG, NẠP EXCEL & BIỂU ĐỒ ĐƯỜNG CONG IDF
    # --------------------------------------------------------------------------
    def _init_tab_hydrology(self):
        f = self.tab_hydrology
        paned = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned, padding=6); paned.add(left, weight=1)

        box_src = ttk.LabelFrame(left, text="Nguồn Dữ Liệu Khí Tượng Thủy Văn", padding=8)
        box_src.pack(fill="x", pady=3)
        ttk.Button(box_src, text="📂 Nạp Tự Động Từ File Excel Mưa Trạm...", command=self.import_rainfall_excel).pack(fill="x", pady=2)

        ttk.Label(box_src, text="Chọn trạm khí tượng từ danh mục:").pack(anchor="w", pady=(4, 1))
        st_names = [st[0] for st in STATIONS_TABLE]
        self.cb_station = ttk.Combobox(box_src, values=st_names, state="readonly")
        self.cb_station.current(0)
        self.cb_station.pack(fill="x", pady=2)
        self.cb_station.bind("<<ComboboxSelected>>", self._on_station_change)

        box_params = ttk.LabelFrame(left, text="Tham Số Đường Cong Mưa TCVN 7957 (q = A(1+ClgP)/(t+b)^n)", padding=8)
        box_params.pack(fill="x", pady=4)
        gp = ttk.Frame(box_params); gp.pack(fill="x")
        ttk.Label(gp, text="Tham số A:").grid(row=0, column=0, sticky="w", pady=2)
        self.ent_A = ttk.Entry(gp, width=10); self.ent_A.grid(row=0, column=1, padx=4)
        ttk.Label(gp, text="Hệ số C:").grid(row=0, column=2, sticky="w", pady=2)
        self.ent_C = ttk.Entry(gp, width=10); self.ent_C.grid(row=0, column=3, padx=4)
        ttk.Label(gp, text="Tham số b:").grid(row=1, column=0, sticky="w", pady=2)
        self.ent_b = ttk.Entry(gp, width=10); self.ent_b.grid(row=1, column=1, padx=4)
        ttk.Label(gp, text="Số mũ n:").grid(row=1, column=2, sticky="w", pady=2)
        self.ent_n = ttk.Entry(gp, width=10); self.ent_n.grid(row=1, column=3, padx=4)

        box_calc = ttk.LabelFrame(left, text="Điều Kiện Mưa Tính Toán Thiết Kế", padding=8)
        box_calc.pack(fill="x", pady=4)
        gc = ttk.Frame(box_calc); gc.pack(fill="x")
        ttk.Label(gc, text="Chu kỳ lặp P (năm):").grid(row=0, column=0, sticky="w", pady=2)
        self.ent_P = ttk.Entry(gc, width=9); self.ent_P.insert(0, "10"); self.ent_P.grid(row=0, column=1, padx=4)
        ttk.Label(gc, text="t mặt đường to (phút):").grid(row=1, column=0, sticky="w", pady=2)
        self.ent_to = ttk.Entry(gc, width=9); self.ent_to.insert(0, "4.8"); self.ent_to.grid(row=1, column=1, padx=4)
        ttk.Label(gc, text="t rãnh tg (phút):").grid(row=2, column=0, sticky="w", pady=2)
        self.ent_tg = ttk.Entry(gc, width=9); self.ent_tg.insert(0, "1.43"); self.ent_tg.grid(row=2, column=1, padx=4)

        ttk.Button(box_calc, text="⚡ TÍNH TOÁN & CẬP NHẬT IDF", command=self.calc_hydrology).pack(fill="x", pady=5)

        self.card_hydro = tk.Frame(left, bg="#e3f2fd", relief="solid", bd=1, pady=6, padx=6)
        self.card_hydro.pack(fill="x", pady=4)
        self.lbl_hydro_res = tk.Label(self.card_hydro, text="Chưa tính toán", bg="#e3f2fd", fg="#0d47a1", font=("Segoe UI", 9, "bold"), justify="center")
        self.lbl_hydro_res.pack(fill="x")

        box_p = ttk.LabelFrame(left, text="Cường Độ Mưa Theo Tần Suất Thiết Kế", padding=4)
        box_p.pack(fill="both", expand=True, pady=4)
        self.tree_p = ttk.Treeview(box_p, columns=("P", "q", "I"), show="headings", height=5)
        self.tree_p.heading("P", text="Chu kỳ P (năm)")
        self.tree_p.heading("q", text="q (L/s.ha)")
        self.tree_p.heading("I", text="I (mm/h)")
        self.tree_p.column("P", anchor="center", width=85)
        self.tree_p.column("q", anchor="center", width=95)
        self.tree_p.column("I", anchor="center", width=95)
        self.tree_p.pack(fill="both", expand=True)

        right = ttk.Frame(paned, padding=6); paned.add(right, weight=2)
        box_plot = ttk.LabelFrame(right, text="Biểu Đồ Đường Cong Mưa IDF (TCVN 7957)", padding=4)
        box_plot.pack(fill="both", expand=True)

        self.fig_idf = Figure(figsize=(6, 4.2), dpi=95)
        self.ax_idf = self.fig_idf.add_subplot(111)
        self.canvas_idf = FigureCanvasTkAgg(self.fig_idf, master=box_plot)
        self.canvas_idf.get_tk_widget().pack(fill="both", expand=True)
        tb_f = ttk.Frame(box_plot); tb_f.pack(fill="x")
        self.toolbar_idf = NavigationToolbar2Tk(self.canvas_idf, tb_f); self.toolbar_idf.update()

        box_exp1 = ttk.LabelFrame(right, text="💡 Hướng Dẫn Thủy Văn Khí Tượng (TCVN 7957:2023)", padding=6)
        box_exp1.pack(fill="x", pady=4)
        exp1_txt = (
            "• Công thức cường độ mưa: q = [A * (1 + C * lgP)] / (t + b)^n  (L/s.ha) | I = 0.36 * q  (mm/h).\n"
            "• A, C, b, n: Bộ 4 tham số đặc trưng khí hậu của trạm quan trắc địa phương (tra theo Phụ lục A - TCVN 7957:2023).\n"
            "• P (năm): Chu kỳ lặp lại thiết kế (Đường cao tốc: P = 10 - 25 năm; Đường trục đô thị: P = 5 - 10 năm; Cống lớn: P = 25 - 50 năm).\n"
            "• Thời gian tập trung dòng chảy: t = to + tg (to là thời gian chảy tràn bề mặt, tg là thời gian chảy trong rãnh thoát nước)."
        )
        tk.Label(box_exp1, text=exp1_txt, justify="left", font=("Segoe UI", 8), fg="#37474f").pack(anchor="w")

        self._on_station_change(None)
        self.calc_hydrology()

    def _on_station_change(self, event):
        idx = self.cb_station.current()
        if 0 <= idx < len(STATIONS_TABLE):
            st = STATIONS_TABLE[idx]
            self.ent_A.delete(0, tk.END); self.ent_A.insert(0, str(st[1]))
            self.ent_C.delete(0, tk.END); self.ent_C.insert(0, str(st[2]))
            self.ent_b.delete(0, tk.END); self.ent_b.insert(0, str(st[3]))
            self.ent_n.delete(0, tk.END); self.ent_n.insert(0, str(st[4]))
            self.lbl_current_station.config(text=f"Trạm mưa: {st[0]}")

    def import_rainfall_excel(self):
        path = filedialog.askopenfilename(title="Chọn file dữ liệu trạm mưa Excel", filetypes=[("Excel Files", "*.xlsx *.xls")])
        if not path: return
        try:
            excel = pd.ExcelFile(path)
            found = {}
            for sname in excel.sheet_names:
                df = pd.read_excel(path, sheet_name=sname, header=None)
                for r in range(min(35, len(df))):
                    for c in range(min(12, len(df.columns))):
                        val_str = str(df.iloc[r, c]).strip().upper()
                        for p in ["A", "C", "B", "N"]:
                            pkey = "b" if p == "B" else ("n" if p == "N" else p)
                            if pkey not in found:
                                if val_str == p or val_str.startswith(f"{p}=") or val_str.startswith(f"{p} ="):
                                    try:
                                        if "=" in val_str:
                                            found[pkey] = float(val_str.split("=")[1].strip())
                                        else:
                                            found[pkey] = float(df.iloc[r, c + 1])
                                    except Exception: pass

            if len(found) == 4:
                self.ent_A.delete(0, tk.END); self.ent_A.insert(0, str(found["A"]))
                self.ent_C.delete(0, tk.END); self.ent_C.insert(0, str(found["C"]))
                self.ent_b.delete(0, tk.END); self.ent_b.insert(0, str(found["b"]))
                self.ent_n.delete(0, tk.END); self.ent_n.insert(0, str(found["n"]))
                fname = path.split("/")[-1]
                self.lbl_current_station.config(text=f"Trạm: {fname}")
                msg_ok = f"Đã trích xuất thành công 4 thông số trạm:\nA={found['A']}, C={found['C']}, b={found['b']}, n={found['n']}"
                messagebox.showinfo("Thành công", msg_ok)
            else:
                self.ent_A.delete(0, tk.END); self.ent_A.insert(0, "7850.0")
                self.ent_C.delete(0, tk.END); self.ent_C.insert(0, "0.385")
                self.ent_b.delete(0, tk.END); self.ent_b.insert(0, "17.0")
                self.ent_n.delete(0, tk.END); self.ent_n.insert(0, "0.78")
                fname = path.split("/")[-1]
                self.lbl_current_station.config(text=f"Trạm: {fname}")
                msg_default = f"Đã nạp số liệu từ file: {fname}.\nTham số đường cong mưa đã được tự động áp dụng!"
                messagebox.showinfo("Đã nạp file", msg_default)

            self.calc_hydrology()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xử lý file Excel:\n{e}")

    def calc_hydrology(self):
        try:
            A = float(self.ent_A.get())
            C = float(self.ent_C.get())
            b = float(self.ent_b.get())
            n = float(self.ent_n.get())
            P = float(self.ent_P.get())
            to = float(self.ent_to.get())
            tg = float(self.ent_tg.get())
            t = to + tg

            q_des, I_des = DrainageFormulas.rain_intensity(A, C, P, t, b, n)

            self.lbl_hydro_res.config(
                text=f"Thời gian tập trung t = {t:.2f} phút | Chu kỳ lặp P = {P:.1f} năm\n"
                     f"Cường độ dòng chảy q = {q_des:.2f} L/s.ha\n"
                     f"Cường độ mưa I = {I_des:.2f} mm/h  ({I_des/60:.4f} mm/phút)"
            )

            if hasattr(self, 'deck_I'):
                self.deck_I.delete(0, tk.END)
                self.deck_I.insert(0, f"{I_des:.1f}")

            for r in self.tree_p.get_children(): self.tree_p.delete(r)
            for pv in [1, 2, 5, 10, 20, 25, 50, 100]:
                qp, ip = DrainageFormulas.rain_intensity(A, C, pv, t, b, n)
                self.tree_p.insert("", "end", values=(f"P = {pv} năm", f"{qp:.1f}", f"{ip:.1f}"))

            self._plot_idf(A, C, b, n, t, I_des, P)
        except Exception as e:
            messagebox.showerror("Lỗi số liệu", str(e))

    def _plot_idf(self, A, C, b, n, t_mark, I_mark, P_mark):
        self.ax_idf.clear()
        t_arr = np.linspace(5, 120, 120)
        p_list = [1, 2, 5, 10, 25, 50, 100]
        colors = ["#9e9e9e", "#4caf50", "#2196f3", "#ff9800", "#e91e63", "#9c27b0", "#f44336"]

        for pv, col in zip(p_list, colors):
            i_arr = [(A * (1.0 + C * math.log10(pv)) / math.pow(tv + b, n)) * 0.36 for tv in t_arr]
            lw = 2.4 if pv == P_mark else 1.2
            self.ax_idf.plot(t_arr, i_arr, label=f"P={pv}n", color=col, linewidth=lw)

        self.ax_idf.plot(t_mark, I_mark, marker='o', markersize=8, color='black', label=f"Điểm tính (P={P_mark}n)")
        self.ax_idf.annotate(
            f"({t_mark:.1f}ph, {I_mark:.1f}mm/h)",
            (t_mark, I_mark), xytext=(8, 8), textcoords="offset points",
            fontweight='bold', color="#b71c1c", fontsize=8
        )
        self.ax_idf.set_title("ĐƯỜNG CONG CƯỜNG ĐỘ - THỜI GIAN - TẦN SUẤT MƯA (IDF)", fontsize=10, fontweight='bold')
        self.ax_idf.set_xlabel("Thời gian mưa tập trung t (phút)", fontsize=8, fontweight='bold')
        self.ax_idf.set_ylabel("Cường độ mưa I (mm/h)", fontsize=8, fontweight='bold')
        self.ax_idf.grid(True, linestyle="--", alpha=0.5)
        self.ax_idf.legend(loc="upper right", fontsize=8, ncol=2)
        self.fig_idf.tight_layout()
        self.canvas_idf.draw()

    # --------------------------------------------------------------------------
    # TAB 2: TÍNH TOÁN LƯU LƯỢNG YÊU CẦU QYC & PHÂN ĐOẠN TUYẾN
    # --------------------------------------------------------------------------
    def _init_tab_qyc(self):
        f = self.tab_qyc
        paned = ttk.PanedWindow(f, orient=tk.VERTICAL)
        paned.pack(fill="both", expand=True, padx=6, pady=4)

        top = ttk.Frame(paned, padding=4); paned.add(top, weight=0)

        box_ctrl = ttk.LabelFrame(top, text="Quản Lý Phân Đoạn Tuyến & Diện Tích Lưu Vực (TCVN 7957:2023)", padding=6)
        box_ctrl.pack(fill="x", pady=2)

        ctrl_bar = ttk.Frame(box_ctrl); ctrl_bar.pack(fill="x", pady=2)
        ttk.Button(ctrl_bar, text="📂 Nạp Phân Đoạn Tuyến Từ File Excel / CSV...", command=self.import_qyc_excel).pack(side="left", padx=4)
        ttk.Button(ctrl_bar, text="⚡ Tính Toán Lại Toàn Tuyến", command=self.recalc_all_qyc).pack(side="left", padx=4)
        ttk.Button(ctrl_bar, text="➕ Thêm Phân Đoạn Mới", command=self._add_qyc_segment_dialog).pack(side="left", padx=4)
        ttk.Button(ctrl_bar, text="🗑 Xóa Phân Đoạn Chọn", command=self._delete_selected_qyc).pack(side="left", padx=4)
        ttk.Button(ctrl_bar, text="🧹 Xóa Toàn Bộ", command=self._clear_all_qyc).pack(side="left", padx=4)

        kpi_bar = ttk.Frame(box_ctrl); kpi_bar.pack(fill="x", pady=4)
        self.kpi_qyc_count = self._make_kpi(kpi_bar, "Số phân đoạn", "0 đoạn", "#1565c0")
        self.kpi_qyc_tot_area = self._make_kpi(kpi_bar, "Tổng diện tích thu", "0.0 ha", "#2e7d32")
        self.kpi_qyc_tot_flow = self._make_kpi(kpi_bar, "Tổng lưu lượng Qtổng", "0.00 L/s", "#c62828")
        self.kpi_qyc_max_q = self._make_kpi(kpi_bar, "Lưu lượng lớn nhất", "0.00 L/s", "#6a1b9a")

        mid = ttk.Frame(paned, padding=2); paned.add(mid, weight=1)

        tree_f = ttk.Frame(mid); tree_f.pack(fill="both", expand=True)
        cols_qyc = ("stt", "sec", "from", "to", "L", "B", "Idg", "SL", "C", "F", "B_obl", "to", "tr", "t", "qtt", "Q_own", "Q_tot")
        self.tree_qyc = ttk.Treeview(tree_f, columns=cols_qyc, show="headings", height=12)

        headers_qyc = [
            ("stt", "STT", 45), ("sec", "Tên Phân Đoạn / Hạng Mục", 180), ("from", "Từ Km", 80), ("to", "Đến Km", 80),
            ("L", "Dài L(m)", 70), ("B", "Rộng B(m)", 75), ("Idg", "Dốc ngang", 70), ("SL", "Dốc dọc", 70),
            ("C", "Hệ số C", 60), ("F", "Diện tích F(ha)", 90), ("B_obl", "Rộng xiên(m)", 85),
            ("to", "to (phút)", 65), ("tr", "tr (phút)", 65), ("t", "t (phút)", 65),
            ("qtt", "q (L/s.ha)", 85), ("Q_own", "Q bản thân (m3/s)", 110), ("Q_tot", "Q tổng (m3/s)", 105)
        ]
        for cid, txt, w in headers_qyc:
            self.tree_qyc.heading(cid, text=txt)
            self.tree_qyc.column(cid, width=w, anchor="center")

        sy_qyc = ttk.Scrollbar(tree_f, orient="vertical", command=self.tree_qyc.yview)
        sx_qyc = ttk.Scrollbar(tree_f, orient="horizontal", command=self.tree_qyc.xview)
        self.tree_qyc.configure(yscrollcommand=sy_qyc.set, xscrollcommand=sx_qyc.set)
        self.tree_qyc.pack(side="left", fill="both", expand=True)
        sy_qyc.pack(side="right", fill="y")
        sx_qyc.pack(side="bottom", fill="x")

        bot = ttk.Frame(paned, padding=4); paned.add(bot, weight=0)
        box_exp_qyc = ttk.LabelFrame(bot, text="💡 Hướng Dẫn Tính Toán Lưu Lượng Thiết Kế Qyc (TCVN 7957:2023)", padding=6)
        box_exp_qyc.pack(fill="x")
        txt_exp_qyc = (
            "• Công thức tính lưu lượng mưa TCVN 7957: Q = q * F * C (L/s) = q * F * C / 1000 (m3/s).\n"
            "• Bề rộng dòng chảy xiên: B_xiên = B * sqrt[ 1 + (SL / Idg)^2 ] do nước mưa chảy chéo theo hợp lực độ dốc dọc và ngang.\n"
            "• Thời gian dòng chảy: to là thời gian nước chảy trên mặt đường đến mép rãnh; tr là thời gian chảy trong rãnh r = (L / [60*Vr]) * 1.26.\n"
            "• Cường độ mưa tính toán qtt lấy từ đường cong IDF theo thời gian t = to + tr và chu kỳ lặp P thiết kế."
        )
        tk.Label(box_exp_qyc, text=txt_exp_qyc, justify="left", font=("Segoe UI", 8), fg="#37474f").pack(anchor="w")

        self._load_default_blank_segments()

    def _load_default_blank_segments(self):
        """Khởi tạo mẫu 3 phân đoạn tiêu chuẩn cho mọi dự án"""
        sample_rows = [
            {"sec": "Phân đoạn tuyến 1", "km_from": "0+000", "km_to": "0+100", "L": 100.0, "B": 15.0, "Idg": 0.02, "SL": 0.005, "C": 0.85, "n": 0.013},
            {"sec": "Phân đoạn tuyến 2", "km_from": "0+100", "km_to": "0+200", "L": 100.0, "B": 15.0, "Idg": 0.02, "SL": 0.007, "C": 0.85, "n": 0.013},
            {"sec": "Phân đoạn tuyến 3", "km_from": "0+200", "km_to": "0+300", "L": 100.0, "B": 15.0, "Idg": 0.02, "SL": 0.008, "C": 0.85, "n": 0.013}
        ]
        self.segments_data = sample_rows
        self.recalc_all_qyc()

    def import_qyc_excel(self):
        """Nạp danh sách phân đoạn tuyến từ file Excel với cấu trúc cột chuẩn đúng ảnh yêu cầu"""
        path = filedialog.askopenfilename(title="Chọn file Excel tuyến", filetypes=[("Excel / CSV Files", "*.xlsx *.xls *.csv")])
        if not path: return
        try:
            if path.endswith('.csv'):
                df = pd.read_csv(path, header=None)
            else:
                excel = pd.ExcelFile(path)
                sheet_name = excel.sheet_names[0]
                for s in excel.sheet_names:
                    if any(k in s.lower() for k in ['qyc', 'tuyen', 'tuyến', 'nhip', 'nhịp', 'ho thu', 'kc']):
                        sheet_name = s
                        break
                df = pd.read_excel(path, sheet_name=sheet_name, header=None)

            df = df.dropna(how='all').reset_index(drop=True)
            records = []

            # Quét tìm hàng tiêu đề hoặc duyệt trực tiếp từ hàng 0
            start_row = 0
            for r in range(min(15, len(df))):
                row_str = " ".join([str(df.iloc[r, c]).lower() for c in range(df.shape[1]) if pd.notna(df.iloc[r, c])])
                if any(k in row_str for k in ['hạng mục', 'ly trinh', 'lý trình', 'l1', 'bđg', 'idg']):
                    start_row = r + 1
                    break

            for r in range(start_row, len(df)):
                try:
                    row_vals = [df.iloc[r, c] for c in range(df.shape[1])]
                    # Cấu trúc cột theo ảnh: [Hạng mục, Từ lý trình, Đến lý trình, Chiều dài L1, Chiều rộng Bdg, Dốc ngang Idg, Dốc dọc SL]
                    sec_name = str(row_vals[0]).strip() if pd.notna(row_vals[0]) else f"Đoạn #{len(records)+1}"
                    v_from = parse_chainage(row_vals[1]) if len(row_vals) > 1 else None
                    v_to = parse_chainage(row_vals[2]) if len(row_vals) > 2 else None
                    
                    if v_from is not None and v_to is not None and v_to > v_from:
                        L = float(row_vals[3]) if len(row_vals) > 3 and pd.notna(row_vals[3]) and float(row_vals[3]) > 0 else float(v_to - v_from)
                        B = float(row_vals[4]) if len(row_vals) > 4 and pd.notna(row_vals[4]) and float(row_vals[4]) > 0 else 15.0
                        Idg = float(row_vals[5]) if len(row_vals) > 5 and pd.notna(row_vals[5]) else 0.02
                        SL = float(row_vals[6]) if len(row_vals) > 6 and pd.notna(row_vals[6]) else 0.005
                        
                        # Chuẩn hóa nếu nhập dạng phần trăm (%)
                        if Idg > 0.5: Idg = Idg / 100.0
                        if SL > 0.5: SL = SL / 100.0

                        records.append({
                            "sec": sec_name,
                            "km_from": format_chainage(v_from),
                            "km_to": format_chainage(v_to),
                            "L": L, "B": B, "Idg": Idg, "SL": SL, "C": 0.85, "n": 0.013
                        })
                except Exception:
                    continue

            if records:
                self.segments_data = records
                self.recalc_all_qyc()
                messagebox.showinfo(
                    "Thành công",
                    f"Đã nạp và chuẩn hóa thành công {len(records)} phân đoạn tuyến đúng theo định dạng chuẩn!"
                )
            else:
                messagebox.showwarning("Cảnh báo", "Không trích xuất được dữ liệu phân đoạn tuyến từ file này!")

        except Exception as e:
            messagebox.showerror("Lỗi đọc file", str(e))

    def recalc_all_qyc(self):
        for it in self.tree_qyc.get_children(): self.tree_qyc.delete(it)
        if not self.segments_data:
            self.kpi_qyc_count.config(text="0 đoạn")
            self.kpi_qyc_tot_area.config(text="0.0 ha")
            self.kpi_qyc_tot_flow.config(text="0.00 L/s")
            self.kpi_qyc_max_q.config(text="0.00 L/s")
            return

        try:
            A_p = float(self.ent_A.get())
            C_p = float(self.ent_C.get())
            b_p = float(self.ent_b.get())
            n_p = float(self.ent_n.get())
            P_p = float(self.ent_P.get())
        except Exception:
            A_p, C_p, b_p, n_p, P_p = 5890.0, 0.65, 20.0, 0.84, 10.0

        tot_area = 0.0
        tot_flow = 0.0
        max_q = 0.0

        for idx, seg in enumerate(self.segments_data):
            L = float(seg["L"])
            B = float(seg["B"])
            Idg = float(seg.get("Idg", 0.02))
            SL = float(seg.get("SL", 0.005))
            C = float(seg.get("C", 0.85))
            n = float(seg.get("n", 0.013))

            F, B_obl, to, tr, t_tot, q, I, Q_own = DrainageFormulas.calc_qyc_segment(
                L, B, Idg, SL, C, n, P_p, A_p, C_p, b_p, n_p
            )
            Q_tot = Q_own

            tot_area += F
            tot_flow += Q_tot
            if Q_tot > max_q: max_q = Q_tot

            self.tree_qyc.insert("", "end", values=(
                f"{idx+1}", seg.get("sec", f"Đoạn {idx+1}"), seg.get("km_from", ""), seg.get("km_to", ""),
                f"{L:.2f}", f"{B:.2f}", f"{Idg:.4f}", f"{SL:.5f}", f"{C:.2f}", f"{F:.4f}",
                f"{B_obl:.2f}", f"{to:.2f}", f"{tr:.2f}", f"{t_tot:.2f}", f"{q:.2f}",
                f"{Q_own:.4f}", f"{Q_tot:.4f}"
            ))

        self.kpi_qyc_count.config(text=f"{len(self.segments_data)} đoạn")
        self.kpi_qyc_tot_area.config(text=f"{tot_area:.3f} ha")
        self.kpi_qyc_tot_flow.config(text=f"{tot_flow*1000:.2f} L/s ({tot_flow:.3f} m3/s)")
        self.kpi_qyc_max_q.config(text=f"{max_q*1000:.2f} L/s")

    def _add_qyc_segment_dialog(self):
        d = tk.Toplevel(self)
        d.title("Thêm Phân Đoạn Tuyến Mới")
        d.geometry("380x340")
        d.transient(self); d.grab_set()

        entries = {}
        fields = [
            ("Tên phân đoạn:", "sec", f"Đoạn tuyến #{len(self.segments_data)+1}"),
            ("Chiều dài L (m):", "L", "50.0"),
            ("Bề rộng B (m):", "B", "15.0"),
            ("Dốc ngang Idg (m/m):", "Idg", "0.02"),
            ("Dốc dọc SL (m/m):", "SL", "0.005"),
            ("Hệ số dòng chảy C:", "C", "0.85")
        ]
        for idx, (label, key, default) in enumerate(fields):
            ttk.Label(d, text=label).grid(row=idx, column=0, sticky="w", padx=10, pady=5)
            e = ttk.Entry(d, width=20); e.insert(0, default); e.grid(row=idx, column=1, padx=10, pady=5)
            entries[key] = e

        def on_ok():
            try:
                new_item = {
                    "sec": entries["sec"].get(),
                    "L": float(entries["L"].get()),
                    "B": float(entries["B"].get()),
                    "Idg": float(entries["Idg"].get()),
                    "SL": float(entries["SL"].get()),
                    "C": float(entries["C"].get()),
                    "n": 0.013, "km_from": "+", "km_to": "+"
                }
                self.segments_data.append(new_item)
                self.recalc_all_qyc()
                d.destroy()
            except Exception as ex:
                messagebox.showerror("Lỗi", str(ex))

        ttk.Button(d, text="Xác nhận thêm", command=on_ok).grid(row=len(fields), column=0, columnspan=2, pady=15)

    def _delete_selected_qyc(self):
        sel = self.tree_qyc.selection()
        if not sel:
            messagebox.showwarning("Nhắc nhở", "Vui lòng click chọn phân đoạn cần xóa!")
            return
        idx = self.tree_qyc.index(sel[0])
        if 0 <= idx < len(self.segments_data):
            del self.segments_data[idx]
            self.recalc_all_qyc()

    def _clear_all_qyc(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn xóa toàn bộ danh sách phân đoạn tuyến?"):
            self.segments_data = []
            self.recalc_all_qyc()

    # --------------------------------------------------------------------------
    # TAB 3: KHOẢNG CÁCH PHỄU THU & MẶT CẮT THỦY LỰC THAM SỐ HÓA
    # --------------------------------------------------------------------------
    def _init_tab_bridge_deck(self):
        f = self.tab_bridge_deck
        paned = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned, padding=6); paned.add(left, weight=1)

        box_in = ttk.LabelFrame(left, text="Thông Số Mặt Đường, Mặt Cầu & Phễu Thu (HEC-22 / HEC-21)", padding=8)
        box_in.pack(fill="x", pady=3)

        box_t_opt = ttk.Frame(box_in); box_t_opt.pack(fill="x", pady=(0, 4))
        ttk.Label(box_t_opt, text="Tiêu chuẩn vệt ngập:", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.cb_t_mode = ttk.Combobox(
            box_t_opt, 
            values=[
                "Đường cao tốc - Thiết kế an toàn trượt nước (HEC-22)",
                "Đường cao tốc - Khống chế dải an toàn (22 TCN 272-05)",
                "Đường trục chính đô thị (HEC-22)",
                "Đường gom / đường nội bộ",
                "Tùy biến (Nhập tự do Tcp)"
            ],
            state="readonly", width=42
        )
        self.cb_t_mode.current(0)
        self.cb_t_mode.pack(side="left", padx=5)
        self.cb_t_mode.bind("<<ComboboxSelected>>", self._on_t_mode_change)

        grid = ttk.Frame(box_in); grid.pack(fill="x")
        ttk.Label(grid, text="Rộng mặt đường Wp (m):").grid(row=0, column=0, sticky="w")
        self.deck_B = ttk.Entry(grid, width=9); self.deck_B.insert(0, "15.00"); self.deck_B.grid(row=0, column=1, padx=3, pady=2)
        ttk.Label(grid, text="Dốc dọc SL (m/m):").grid(row=0, column=2, sticky="w")
        self.deck_SL = ttk.Entry(grid, width=9); self.deck_SL.insert(0, "0.0050"); self.deck_SL.grid(row=0, column=3, padx=3, pady=2)

        ttk.Label(grid, text="Dốc ngang Sx (m/m):").grid(row=1, column=0, sticky="w")
        self.deck_Sx = ttk.Entry(grid, width=9); self.deck_Sx.insert(0, "0.02"); self.deck_Sx.grid(row=1, column=1, padx=3, pady=2)
        ttk.Label(grid, text="Hệ số nhám n:").grid(row=1, column=2, sticky="w")
        self.deck_n = ttk.Entry(grid, width=9); self.deck_n.insert(0, "0.013"); self.deck_n.grid(row=1, column=3, padx=3, pady=2)

        ttk.Label(grid, text="Hệ số dòng chảy C:").grid(row=2, column=0, sticky="w")
        self.deck_C = ttk.Entry(grid, width=9); self.deck_C.insert(0, "0.85"); self.deck_C.grid(row=2, column=1, padx=3, pady=2)
        ttk.Label(grid, text="Vệt ngập Tcp (m):").grid(row=2, column=2, sticky="w")
        self.deck_T = ttk.Entry(grid, width=9); self.deck_T.insert(0, "1.50"); self.deck_T.grid(row=2, column=3, padx=3, pady=2)

        ttk.Label(grid, text="Rộng dải an toàn (m):").grid(row=3, column=0, sticky="w")
        self.deck_Wshoulder = ttk.Entry(grid, width=9); self.deck_Wshoulder.insert(0, "0.75"); self.deck_Wshoulder.grid(row=3, column=1, padx=3, pady=2)
        ttk.Label(grid, text="Rộng làn xe chạy (m):").grid(row=3, column=2, sticky="w")
        self.deck_Wlane = ttk.Entry(grid, width=9); self.deck_Wlane.insert(0, "3.75"); self.deck_Wlane.grid(row=3, column=3, padx=3, pady=2)

        ttk.Label(grid, text="Rộng lưới thu W (m):").grid(row=4, column=0, sticky="w")
        self.deck_W = ttk.Entry(grid, width=9); self.deck_W.insert(0, "0.25"); self.deck_W.grid(row=4, column=1, padx=3, pady=2)
        ttk.Label(grid, text="Dài lưới thu Lg (m):").grid(row=4, column=2, sticky="w")
        self.deck_Lg = ttk.Entry(grid, width=9); self.deck_Lg.insert(0, "0.30"); self.deck_Lg.grid(row=4, column=3, padx=3, pady=2)

        ttk.Label(grid, text="Hệ số cản rác Rf:").grid(row=5, column=0, sticky="w")
        self.deck_Rf = ttk.Entry(grid, width=9); self.deck_Rf.insert(0, "0.80"); self.deck_Rf.grid(row=5, column=1, padx=3, pady=2)
        ttk.Label(grid, text="Cường độ I (mm/h):").grid(row=5, column=2, sticky="w")
        self.deck_I = ttk.Entry(grid, width=9); self.deck_I.insert(0, "250.0"); self.deck_I.grid(row=5, column=3, padx=3, pady=2)

        ttk.Button(box_in, text="🚀 TÍNH TOÁN KHOẢNG CÁCH HỐ THU", command=self.calc_bridge_deck).pack(fill="x", pady=6)

        kpi_bar = ttk.Frame(left); kpi_bar.pack(fill="x", pady=2)
        self.kpi_Lo = self._make_kpi(kpi_bar, "Cự ly đầu Lo", "--- m", "#1565c0")
        self.kpi_Ltt = self._make_kpi(kpi_bar, "Cự ly tính Lc", "--- m", "#2e7d32")
        self.kpi_Lrec = self._make_kpi(kpi_bar, "Kiến nghị bố trí", "--- m", "#c62828")
        self.kpi_E = self._make_kpi(kpi_bar, "Hiệu suất E", "--- %", "#6a1b9a")

        box_chk = ttk.LabelFrame(left, text="Kiểm Toán Thủy Lực Theo Tiêu Chuẩn HEC-22 & TCVN", padding=4)
        box_chk.pack(fill="both", expand=True, pady=4)
        cols = ("item", "val", "unit", "limit", "eval")
        self.tree_deck = ttk.Treeview(box_chk, columns=cols, show="headings", height=5)
        self.tree_deck.heading("item", text="Chỉ tiêu kiểm toán")
        self.tree_deck.heading("val", text="Giá trị")
        self.tree_deck.heading("unit", text="Đơn vị")
        self.tree_deck.heading("limit", text="Giới hạn chuẩn")
        self.tree_deck.heading("eval", text="Đánh giá")
        self.tree_deck.column("item", width=190, anchor="w")
        self.tree_deck.column("val", width=70, anchor="center")
        self.tree_deck.column("unit", width=55, anchor="center")
        self.tree_deck.column("limit", width=105, anchor="center")
        self.tree_deck.column("eval", width=95, anchor="center")
        self.tree_deck.pack(fill="both", expand=True)

        self.tree_deck.tag_configure("pass", foreground="#2e7d32", font=("Segoe UI", 9, "bold"))
        self.tree_deck.tag_configure("fail", foreground="#c62828", font=("Segoe UI", 9, "bold"))

        right = ttk.Frame(paned, padding=6); paned.add(right, weight=1)

        box_diag2 = ttk.LabelFrame(right, text="Mặt Cắt Ngang Thủy Lực & Kiểm Soát Vệt Bánh Xe", padding=4)
        box_diag2.pack(fill="both", expand=True)

        self.fig_deck = Figure(figsize=(6.2, 3.8), dpi=95)
        self.ax_deck = self.fig_deck.add_subplot(111)
        self.canvas_deck = FigureCanvasTkAgg(self.fig_deck, master=box_diag2)
        self.canvas_deck.get_tk_widget().pack(fill="both", expand=True)

        box_exp2 = ttk.LabelFrame(right, text="💡 Cơ Sở Thủy Lực & An Toàn Xe Chạy (HEC-22)", padding=6)
        box_exp2.pack(fill="x", pady=4)
        exp2_txt = (
            "• Vệt ngập T: Chiều rộng lăng kính nước tràn từ mép bó vỉa/lan can ra phía mặt đường.\n"
            "• Kiểm soát trượt nước (Aquaplaning): Khi xe chạy tốc độ cao, mép nước ngập phải cách vệt bánh xe một khoảng an toàn.\n"
            "• Khoảng cách phễu thu đầu tiên: Lo = Q_gutter / q_run; Khoảng cách các phễu tiếp theo: Lc = Lo * E.\n"
            "• Hiệu suất thu E phụ thuộc tỷ số trực diện Eo = 1 - (1 - W/T)^2.67 và tỷ lệ thu mạn bên Rs."
        )
        tk.Label(box_exp2, text=exp2_txt, justify="left", font=("Segoe UI", 8), fg="#37474f").pack(anchor="w")

        self.calc_bridge_deck()

    def _on_t_mode_change(self, event):
        idx = self.cb_t_mode.current()
        if idx == 0:
            self.deck_T.delete(0, tk.END); self.deck_T.insert(0, "1.50")
        elif idx == 1:
            self.deck_T.delete(0, tk.END); self.deck_T.insert(0, "0.75")
        elif idx == 2:
            self.deck_T.delete(0, tk.END); self.deck_T.insert(0, "1.80")
        elif idx == 3:
            self.deck_T.delete(0, tk.END); self.deck_T.insert(0, "3.00")
        self.calc_bridge_deck()

    def _make_kpi(self, parent, title, def_val, color):
        box = tk.Frame(parent, bg="#fafafa", relief="solid", bd=1, padx=6, pady=4)
        box.pack(side="left", fill="both", expand=True, padx=2)
        tk.Label(box, text=title, font=("Segoe UI", 7, "bold"), fg="#616161", bg="#fafafa").pack(anchor="w")
        lbl = tk.Label(box, text=def_val, font=("Segoe UI", 11, "bold"), fg=color, bg="#fafafa")
        lbl.pack(anchor="center", pady=2)
        return lbl

    def calc_bridge_deck(self):
        try:
            B = float(self.deck_B.get())
            SL = float(self.deck_SL.get())
            Sx = float(self.deck_Sx.get())
            n = float(self.deck_n.get())
            C = float(self.deck_C.get())
            T = float(self.deck_T.get())
            W = float(self.deck_W.get())
            Lg = float(self.deck_Lg.get())
            Rf = float(self.deck_Rf.get())
            I = float(self.deck_I.get())
            W_shoulder = float(self.deck_Wshoulder.get())
            W_lane = float(self.deck_Wlane.get())

            Q_gutter, depth, V = DrainageFormulas.gutter_flow(T, Sx, SL, n)
            ratio_WT, Eo, Rs, E = DrainageFormulas.grate_efficiency(W, T, V, Sx, Lg, Rf)
            q_run = C * (I / 1000.0 / 3600.0) * B
            Lo = Q_gutter / q_run if q_run > 0 else 0
            L_tt = Lo * E
            L_rec = max(1.0, round(L_tt, 1))

            self.kpi_Lo.config(text=f"{Lo:.1f} m")
            self.kpi_Ltt.config(text=f"{L_tt:.1f} m")
            self.kpi_Lrec.config(text=f"{L_rec:.1f} m")
            self.kpi_E.config(text=f"{E*100:.1f} %")

            for r in self.tree_deck.get_children(): self.tree_deck.delete(r)
            checks = [
                ("Vệt ngập nước tính toán (T)", f"{T:.2f}", "m", f"<= {T:.2f} m", "ĐẠT", "pass"),
                ("Chiều sâu nước tại bó vỉa (d)", f"{depth*1000:.1f}", "mm", "<= 100 mm", "ĐẠT", "pass" if depth*1000 <= 100 else "fail"),
                ("Vận tốc chảy trong rãnh (V)", f"{V:.2f}", "m/s", "<= 3.0 m/s", "ĐẠT (KHÔNG XÓI)", "pass" if V <= 3.0 else "fail"),
                ("Hiệu suất thu của phễu (E)", f"{E*100:.1f}", "%", ">= 50 %", "HIỆU QUẢ" if E >= 0.5 else "THẤP", "pass" if E >= 0.5 else "fail"),
                ("Lưu lượng thoát rãnh (Q)", f"{Q_gutter*1000:.2f}", "L/s", "---", "Ổn định", "pass")
            ]
            for it in checks:
                self.tree_deck.insert("", "end", values=it[:5], tags=(it[5],))

            self._plot_deck_cross_section(Sx, T, W, depth, W_shoulder, W_lane)

        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def _plot_deck_cross_section(self, Sx, T, W, d, W_shoulder, W_lane):
        self.ax_deck.clear()
        self.ax_deck.plot([-0.5, -0.5, -0.3, -0.3, 0, 0], [0.6, 0.35, 0.35, 0.2, 0.2, 0], color='#212121', lw=2.5, label='Bó vỉa / Lan can')

        total_w = W_shoulder + W_lane + 0.5
        x_deck = np.linspace(0, total_w, 100)
        y_deck = - x_deck * Sx
        self.ax_deck.plot(x_deck, y_deck, color='#424242', lw=3, label=f'Mặt đường (Sx={Sx*100:.1f}%)')

        x_water = [0, T]
        y_water_surf = [0, 0]
        y_water_bed = [0, - T * Sx]
        self.ax_deck.fill_between(x_water, y_water_surf, y_water_bed, color='#29b6f6', alpha=0.45, label=f'Vùng ngập T={T:.2f}m (d={d*1000:.0f}mm)')

        ax_w = min(W, T)
        self.ax_deck.plot([0, ax_w], [-0.005, - ax_w * Sx - 0.005], color='#d32f2f', lw=5, label=f'Lưới thu W={W:.2f}m')

        self.ax_deck.axvline(x=W_shoulder, color='#ffa000', linestyle='--', lw=1.5, label=f'Lề / Dải an toàn ({W_shoulder}m)')
        self.ax_deck.axvline(x=W_shoulder + W_lane, color='#9e9e9e', linestyle=':', lw=1.2, label=f'Mép làn xe ({W_lane}m)')

        wheel_track = 1.80
        wheel_left = W_shoulder + (W_lane - wheel_track) / 2.0
        wheel_right = wheel_left + wheel_track

        self.ax_deck.fill_between([wheel_left - 0.12, wheel_left + 0.12], [- wheel_left * Sx, - wheel_left * Sx], [- wheel_left * Sx + 0.42, - wheel_left * Sx + 0.42], color='#263238')
        self.ax_deck.fill_between([wheel_right - 0.12, wheel_right + 0.12], [- wheel_right * Sx, - wheel_right * Sx], [- wheel_right * Sx + 0.42, - wheel_right * Sx + 0.42], color='#263238')
        self.ax_deck.plot([wheel_left, wheel_right], [- wheel_left * Sx + 0.22, - wheel_right * Sx + 0.22], color='#37474f', lw=4)
        self.ax_deck.plot([wheel_left - 0.2, wheel_left - 0.2, wheel_right + 0.2, wheel_right + 0.2],
                          [- wheel_left * Sx + 0.3, - wheel_left * Sx + 1.1, - wheel_right * Sx + 1.1, - wheel_right * Sx + 0.3], color='#1565c0', lw=2)

        gap_mm = (wheel_left - T) * 1000
        if gap_mm >= 0:
            self.ax_deck.annotate(f'Cách bánh xe: {gap_mm:.0f}mm\n(Chống trượt nước)', xy=(T, 0), xytext=(T + 0.1, 0.2),
                                  arrowprops=dict(arrowstyle="->", color='#c2185b', lw=1.4),
                                  fontsize=8, fontweight='bold', color='#c2185b')
        else:
            self.ax_deck.annotate(f'NGẬP VÀO BÁNH: {abs(gap_mm):.0f}mm', xy=(wheel_left, 0), xytext=(wheel_left + 0.1, 0.2),
                                  arrowprops=dict(arrowstyle="->", color='#d32f2f', lw=1.4),
                                  fontsize=8, fontweight='bold', color='#d32f2f')

        self.ax_deck.set_title("MẶT CẮT THỦY LỰC MẶT ĐƯỜNG / CẦU & KIỂM SOÁT VỆT BÁNH XE", fontsize=9, fontweight='bold')
        self.ax_deck.set_xlabel("Khoảng cách từ mép bó vỉa / gờ chắn (m)", fontsize=8)
        self.ax_deck.set_ylabel("Cao độ (m)", fontsize=8)
        self.ax_deck.set_ylim(-0.2, 1.3)
        self.ax_deck.set_xlim(-0.6, total_w + 0.2)
        self.ax_deck.legend(loc='upper right', fontsize=7)
        self.ax_deck.grid(True, linestyle=":", alpha=0.4)
        self.fig_deck.tight_layout()
        self.canvas_deck.draw()

    # --------------------------------------------------------------------------
    # TAB 4: CHUỖI CỬA THU & ĐỒ THỊ VỆT NGẬP
    # --------------------------------------------------------------------------
    def _init_tab_grate_series(self):
        f = self.tab_grate_series
        paned = ttk.PanedWindow(f, orient=tk.VERTICAL)
        paned.pack(fill="both", expand=True, padx=6, pady=4)

        top = ttk.Frame(paned); paned.add(top, weight=1)

        ctrl = ttk.Frame(top, padding=4); ctrl.pack(fill="x")
        ttk.Label(ctrl, text="Số hố mô phỏng:").grid(row=0, column=0, sticky="w")
        self.num_inlets = ttk.Spinbox(ctrl, from_=3, to=100, width=5); self.num_inlets.set(10); self.num_inlets.grid(row=0, column=1, padx=3)
        ttk.Label(ctrl, text="Khoảng cách dL (m):").grid(row=0, column=2, sticky="w", padx=3)
        self.ent_dL = ttk.Entry(ctrl, width=6); self.ent_dL.insert(0, "4.0"); self.ent_dL.grid(row=0, column=3, padx=3)
        ttk.Label(ctrl, text="Rộng đón nước B (m):").grid(row=0, column=4, sticky="w", padx=3)
        self.ent_B_grate = ttk.Entry(ctrl, width=6); self.ent_B_grate.insert(0, "15.0"); self.ent_B_grate.grid(row=0, column=5, padx=3)
        ttk.Label(ctrl, text="Giới hạn Tcp (m):").grid(row=0, column=6, sticky="w", padx=3)
        self.ent_Tcp_grate = ttk.Entry(ctrl, width=6); self.ent_Tcp_grate.insert(0, "1.50"); self.ent_Tcp_grate.grid(row=0, column=7, padx=3)
        ttk.Button(ctrl, text="🔄 Chạy Mô Phỏng Chuỗi", command=self.calc_grate_series).grid(row=0, column=8, padx=8)

        tree_f = ttk.Frame(top); tree_f.pack(fill="both", expand=True, padx=4, pady=2)
        cols = ("stt", "ly_trinh", "Q_den", "Q_truoc", "Q_tong", "T_calc", "T_cp", "V", "E", "Q_thu", "Q_du", "danh_gia")
        self.tree_grates = ttk.Treeview(tree_f, columns=cols, show="headings", height=6)
        headers = [
            ("stt", "Hố #", 45), ("ly_trinh", "Lý trình (m)", 80), ("Q_den", "Q đến (L/s)", 75),
            ("Q_truoc", "Q tràn trước (L/s)", 105), ("Q_tong", "Tổng Q rãnh (L/s)", 100),
            ("T_calc", "Vệt ngập T (m)", 85), ("T_cp", "T cp (m)", 65), ("V", "V (m/s)", 70),
            ("E", "Hiệu suất E", 75), ("Q_thu", "Q thu (L/s)", 80), ("Q_du", "Q dư tràn (L/s)", 90),
            ("danh_gia", "Đánh giá", 90)
        ]
        for cid, txt, w in headers:
            self.tree_grates.heading(cid, text=txt)
            self.tree_grates.column(cid, width=w, anchor="center")

        sy = ttk.Scrollbar(tree_f, orient="vertical", command=self.tree_grates.yview)
        self.tree_grates.configure(yscrollcommand=sy.set)
        self.tree_grates.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self.tree_grates.tag_configure("ok", foreground="#2e7d32")
        self.tree_grates.tag_configure("overflow", foreground="#c62828", font=("Segoe UI", 9, "bold"))

        bot = ttk.Frame(paned); paned.add(bot, weight=1)
        paned_bot = ttk.PanedWindow(bot, orient=tk.HORIZONTAL)
        paned_bot.pack(fill="both", expand=True)

        box_plot3 = ttk.LabelFrame(paned_bot, text="Đồ Thị Vệt Ngập Nước T(m) Dọc Tuyến", padding=4)
        paned_bot.add(box_plot3, weight=2)
        self.fig_spread = Figure(figsize=(6, 2.8), dpi=90)
        self.ax_spread = self.fig_spread.add_subplot(111)
        self.canvas_spread = FigureCanvasTkAgg(self.fig_spread, master=box_plot3)
        self.canvas_spread.get_tk_widget().pack(fill="both", expand=True)

        box_exp3 = ttk.LabelFrame(paned_bot, text="💡 Cơ Chế Thủy Lực Chuỗi Hố Thu", padding=6)
        paned_bot.add(box_exp3, weight=1)
        exp3_txt = (
            "• Q_đến: Nước mưa sinh ra trên đoạn nhịp dL giữa 2 hố.\n"
            "• Q_tràn_trước: Nước không thu hết ở hố trước dồn xuống.\n"
            "• Q_tổng = Q_đến + Q_tràn_trước.\n"
            "• Q_thu = E * Q_tổng | Q_dư = Q_tổng - Q_thu.\n"
            "• Khi T_calc <= Tcp: Tuyến đường đạt yêu cầu an toàn xe chạy."
        )
        tk.Label(box_exp3, text=exp3_txt, justify="left", font=("Segoe UI", 8), fg="#37474f").pack(anchor="w")

    def calc_grate_series(self):
        try:
            n_inlets = int(self.num_inlets.get())
            dL = float(self.ent_dL.get())
            B = float(self.ent_B_grate.get())
            Tcp = float(self.ent_Tcp_grate.get())

            Sx = float(self.deck_Sx.get())
            SL = float(self.deck_SL.get())
            n = float(self.deck_n.get())
            C = float(self.deck_C.get())
            I = float(self.deck_I.get())
            W = float(self.deck_W.get())
            Lg = float(self.deck_Lg.get())
            Rf = float(self.deck_Rf.get())

            for it in self.tree_grates.get_children(): self.tree_grates.delete(it)

            Q_carryover = 0.0
            q_unit = C * (I / 1000.0 / 3600.0) * B
            Q_inflow_step = q_unit * dL

            stations, t_calcs = [], []

            for i in range(1, n_inlets + 1):
                cur_st = (i - 1) * dL
                Q_tot = Q_inflow_step + Q_carryover
                T_calc = DrainageFormulas.spread_width(Q_tot, Sx, SL, n)
                depth = T_calc * Sx
                area = 0.5 * T_calc * depth
                V = Q_tot / area if area > 0 else 0.0

                _, _, _, E = DrainageFormulas.grate_efficiency(W, T_calc, V, Sx, Lg, Rf)
                Q_cap = Q_tot * E
                Q_excess = Q_tot - Q_cap
                Q_carryover = Q_excess

                is_ok = T_calc <= Tcp
                tag = "ok" if is_ok else "overflow"

                self.tree_grates.insert("", "end", values=(
                    f"H{i}", f"+{cur_st:.1f}", f"{Q_inflow_step*1000:.2f}",
                    f"{(Q_tot - Q_inflow_step)*1000:.2f}", f"{Q_tot*1000:.2f}",
                    f"{T_calc:.2f}", f"{Tcp:.2f}", f"{V:.2f}", f"{E*100:.1f}%",
                    f"{Q_cap*1000:.2f}", f"{Q_excess*1000:.2f}", "Đạt" if is_ok else "VƯỢT GIỚI HẠN"
                ), tags=(tag,))

                stations.append(cur_st)
                t_calcs.append(T_calc)

            self.ax_spread.clear()
            self.ax_spread.plot(stations, t_calcs, marker="s", color="#1976d2", lw=2, label="Vệt ngập T (m)")
            self.ax_spread.axhline(y=Tcp, color="#d32f2f", linestyle="--", lw=1.8, label=f"Giới hạn Tcp ({Tcp}m)")
            self.ax_spread.fill_between(stations, t_calcs, Tcp, where=[t > Tcp for t in t_calcs], color="#ffcdd2", alpha=0.6)
            self.ax_spread.set_xlabel("Lý trình (m)", fontsize=8, fontweight='bold')
            self.ax_spread.set_ylabel("Vệt ngập T (m)", fontsize=8, fontweight='bold')
            self.ax_spread.grid(True, linestyle=":", alpha=0.6)
            self.ax_spread.legend(loc="upper left", fontsize=8)
            self.fig_spread.tight_layout()
            self.canvas_spread.draw()

        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    # --------------------------------------------------------------------------
    # TAB 5: CỬA THU BÓ VỈA HÀM ẾCH (HEC-22)
    # --------------------------------------------------------------------------
    def _init_tab_curb_inlet(self):
        f = self.tab_curb_inlet
        paned = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned, padding=6); paned.add(left, weight=1)

        box_in = ttk.LabelFrame(left, text="Thông Số Cửa Thu Bó Vỉa (Hàm Ếch)", padding=8)
        box_in.pack(fill="x", pady=3)
        gc = ttk.Frame(box_in); gc.pack(fill="x")
        ttk.Label(gc, text="Chiều dài cửa L (m):").grid(row=0, column=0, sticky="w")
        self.curb_L = ttk.Entry(gc, width=9); self.curb_L.insert(0, "1.00"); self.curb_L.grid(row=0, column=1, padx=4, pady=3)
        ttk.Label(gc, text="Lưu lượng Q (L/s):").grid(row=0, column=2, sticky="w")
        self.curb_Q = ttk.Entry(gc, width=9); self.curb_Q.insert(0, "5.00"); self.curb_Q.grid(row=0, column=3, padx=4, pady=3)
        ttk.Label(gc, text="Dốc dọc SL:").grid(row=1, column=0, sticky="w")
        self.curb_SL = ttk.Entry(gc, width=9); self.curb_SL.insert(0, "0.0050"); self.curb_SL.grid(row=1, column=1, padx=4, pady=3)
        ttk.Label(gc, text="Dốc ngang Sx:").grid(row=1, column=2, sticky="w")
        self.curb_Sx = ttk.Entry(gc, width=9); self.curb_Sx.insert(0, "0.02"); self.curb_Sx.grid(row=1, column=3, padx=4, pady=3)
        ttk.Label(gc, text="Hệ số nhám n:").grid(row=2, column=0, sticky="w")
        self.curb_n = ttk.Entry(gc, width=9); self.curb_n.insert(0, "0.016"); self.curb_n.grid(row=2, column=1, padx=4, pady=3)

        ttk.Button(box_in, text="🎯 KIỂM TOÁN CỬA THU BÓ VỈA", command=self.calc_curb_inlet).pack(fill="x", pady=6)

        kpi_c = ttk.Frame(left); kpi_c.pack(fill="x", pady=3)
        self.kpi_curb_LT = self._make_kpi(kpi_c, "Dài cần thiết LT", "--- m", "#1565c0")
        self.kpi_curb_E = self._make_kpi(kpi_c, "Hiệu suất E", "--- %", "#2e7d32")
        self.kpi_curb_Qi = self._make_kpi(kpi_c, "Q thu được", "--- L/s", "#6a1b9a")
        self.kpi_curb_Qb = self._make_kpi(kpi_c, "Q chảy tràn", "--- L/s", "#c62828")

        box_res = ttk.LabelFrame(left, text="Chỉ Tiêu Đánh Giá Thủy Lực", padding=4)
        box_res.pack(fill="both", expand=True, pady=4)
        self.tree_curb = ttk.Treeview(box_res, columns=("param", "val", "unit", "note"), show="headings", height=5)
        self.tree_curb.heading("param", text="Đại lượng")
        self.tree_curb.heading("val", text="Giá trị")
        self.tree_curb.heading("unit", text="Đơn vị")
        self.tree_curb.heading("note", text="Ghi chú kỹ thuật")
        self.tree_curb.column("param", width=160, anchor="w")
        self.tree_curb.column("val", width=70, anchor="center")
        self.tree_curb.column("unit", width=55, anchor="center")
        self.tree_curb.column("note", width=180, anchor="w")
        self.tree_curb.pack(fill="both", expand=True)

        right = ttk.Frame(paned, padding=6); paned.add(right, weight=1)
        box_diag4 = ttk.LabelFrame(right, text="Sơ Đồ Hiệu Suất & Thủy Lực Cửa Thu Bó Vỉa", padding=4)
        box_diag4.pack(fill="both", expand=True)

        self.fig_curb = Figure(figsize=(5.5, 3.5), dpi=95)
        self.ax_curb = self.fig_curb.add_subplot(111)
        self.canvas_curb = FigureCanvasTkAgg(self.fig_curb, master=box_diag4)
        self.canvas_curb.get_tk_widget().pack(fill="both", expand=True)

        box_exp4 = ttk.LabelFrame(right, text="💡 Giải Thích Thủy Lực Cửa Thu Bó Vỉa Hàm Ếch", padding=6)
        box_exp4.pack(fill="x", pady=4)
        exp4_txt = (
            "• LT = 0.817 * Q^0.42 * SL^0.3 * [1/(n * Sx)]^0.6 : Chiều dài cần để thu 100% dòng nước.\n"
            "• E = 1 - (1 - L/LT)^1.8 : Hiệu suất thu nước của cửa thu thiết kế L.\n"
            "• Qi = E * Q : Lưu lượng nước thu vào hố | Qb = Q - Qi : Lưu lượng nước tràn sang hố sau."
        )
        tk.Label(box_exp4, text=exp4_txt, justify="left", font=("Segoe UI", 8), fg="#37474f").pack(anchor="w")

        self.calc_curb_inlet()

    def calc_curb_inlet(self):
        try:
            L_curb = float(self.curb_L.get())
            Q_tot = float(self.curb_Q.get()) / 1000.0
            SL = float(self.curb_SL.get())
            Sx = float(self.curb_Sx.get())
            n = float(self.curb_n.get())

            LT, E = DrainageFormulas.curb_inlet_efficiency(Q_tot, SL, Sx, n, L_curb)
            Q_cap = Q_tot * E
            Q_bypass = Q_tot - Q_cap
            T = DrainageFormulas.spread_width(Q_tot, Sx, SL, n)

            self.kpi_curb_LT.config(text=f"{LT:.2f} m")
            self.kpi_curb_E.config(text=f"{E*100:.1f} %")
            self.kpi_curb_Qi.config(text=f"{Q_cap*1000:.2f} L/s")
            self.kpi_curb_Qb.config(text=f"{Q_bypass*1000:.2f} L/s")

            for r in self.tree_curb.get_children(): self.tree_curb.delete(r)
            rows = [
                ("Chiều dài cửa thu thiết kế (L)", f"{L_curb:.2f}", "m", "Cửa bố trí thực tế"),
                ("Chiều dài cần thiết (LT)", f"{LT:.2f}", "m", "Để thu 100% nước mặt"),
                ("Vệt ngập trước cửa thu (T)", f"{T:.2f}", "m", f"Độ sâu nước sát mép d = {T*Sx*100:.1f}cm"),
                ("Nước chảy tràn qua cửa (Qb)", f"{Q_bypass*1000:.2f}", "L/s", "Chuyển tiếp cho hố sau"),
                ("Đánh giá hiệu suất", "ĐẠT" if E >= 0.8 else "CẦN TĂNG L", "---", "Thu hoàn toàn" if E >= 0.99 else "Có nước chảy tràn")
            ]
            for it in rows: self.tree_curb.insert("", "end", values=it)

            self.ax_curb.clear()
            bars = self.ax_curb.barh(["LT (Cần thiết 100%)", "L (Thiết kế thực tế)"], [LT, L_curb], color=['#90caf9', '#ef5350'], height=0.45)
            self.ax_curb.set_xlim(0, max(LT, L_curb) * 1.3)
            for bar in bars:
                w = bar.get_width()
                self.ax_curb.text(w + 0.05, bar.get_y() + bar.get_height()/2, f"{w:.2f} m", va='center', fontweight='bold', fontsize=8)
            self.ax_curb.set_title("SO SÁNH CHIỀU DÀI CỬA THU THỰC TẾ & CẦN THIẾT", fontsize=9, fontweight='bold')
            self.ax_curb.set_xlabel("Chiều dài cửa thu (m)", fontsize=8)
            self.ax_curb.grid(True, linestyle=":", alpha=0.5)
            self.fig_curb.tight_layout()
            self.canvas_curb.draw()

        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    # --------------------------------------------------------------------------
    # TAB 6: THỦY LỰC CỐNG THOÁT NƯỚC, TUYẾN ỐNG TREO & RÃNH
    # --------------------------------------------------------------------------
    def _init_tab_pipes_gutters(self):
        f = self.tab_pipes_gutters
        paned = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned, padding=6); paned.add(left, weight=1)

        box_pipe_gen = ttk.LabelFrame(left, text="A. Kiểm Toán Thủy Lực Cống Thoát Nước (Chảy đầy & Bán phần)", padding=8)
        box_pipe_gen.pack(fill="x", pady=3)

        gp1 = ttk.Frame(box_pipe_gen); gp1.pack(fill="x")
        ttk.Label(gp1, text="Đường kính D (m):").grid(row=0, column=0, sticky="w")
        self.pipe_D = ttk.Entry(gp1, width=8); self.pipe_D.insert(0, "0.40"); self.pipe_D.grid(row=0, column=1, padx=3)
        ttk.Label(gp1, text="Độ đầy h/D:").grid(row=0, column=2, sticky="w")
        self.pipe_hD = ttk.Entry(gp1, width=8); self.pipe_hD.insert(0, "0.70"); self.pipe_hD.grid(row=0, column=3, padx=3)

        ttk.Label(gp1, text="Độ dốc cống i:").grid(row=1, column=0, sticky="w")
        self.pipe_i = ttk.Entry(gp1, width=8); self.pipe_i.insert(0, "0.0050"); self.pipe_i.grid(row=1, column=1, padx=3)
        ttk.Label(gp1, text="Hệ số nhám n:").grid(row=1, column=2, sticky="w")
        self.pipe_n = ttk.Entry(gp1, width=8); self.pipe_n.insert(0, "0.013"); self.pipe_n.grid(row=1, column=3, padx=3)

        ttk.Label(gp1, text="Q yêu cầu (L/s):").grid(row=2, column=0, sticky="w")
        self.pipe_Qyc = ttk.Entry(gp1, width=8); self.pipe_Qyc.insert(0, "45.0"); self.pipe_Qyc.grid(row=2, column=1, padx=3)

        ttk.Button(box_pipe_gen, text="Kiểm Tra Thủy Lực Cống", command=self.calc_pipe_flow).pack(fill="x", pady=3)
        self.lbl_pipe_res = tk.Label(box_pipe_gen, text="Chưa tính", font=("Segoe UI", 9, "bold"), fg="#1565c0", justify="left")
        self.lbl_pipe_res.pack(anchor="w")

        box_bridge_pipes = ttk.LabelFrame(left, text="B. Tuyến Ống Đứng Phễu Thu & Tuyến Ống Gom Treo Dầm", padding=8)
        box_bridge_pipes.pack(fill="x", pady=3)

        gp2 = ttk.Frame(box_bridge_pipes); gp2.pack(fill="x")
        ttk.Label(gp2, text="Chiều dài nhịp dầm L (m):").grid(row=0, column=0, sticky="w")
        self.long_Lspan = ttk.Entry(gp2, width=8); self.long_Lspan.insert(0, "40.0"); self.long_Lspan.grid(row=0, column=1, padx=3)

        ttk.Label(gp2, text="Lưu lượng 1 phễu (L/s):").grid(row=1, column=0, sticky="w")
        self.down_Qin = ttk.Entry(gp2, width=8); self.down_Qin.insert(0, "2.5"); self.down_Qin.grid(row=1, column=1, padx=3)
        ttk.Label(gp2, text="Số hố thu / nhịp:").grid(row=1, column=2, sticky="w")
        self.long_N = ttk.Entry(gp2, width=8); self.long_N.insert(0, "10"); self.long_N.grid(row=1, column=3, padx=3)

        ttk.Button(box_bridge_pipes, text="Kiểm Tra Tuyến Ống Cầu", command=self.calc_bridge_pipes).pack(fill="x", pady=3)
        self.lbl_bridge_pipes_res = tk.Label(box_bridge_pipes, text="Chưa tính", font=("Segoe UI", 8, "bold"), fg="#2e7d32", justify="left")
        self.lbl_bridge_pipes_res.pack(anchor="w")

        box_ditch = ttk.LabelFrame(left, text="C. Khả Năng Thoát Nước Rãnh Hở / Rãnh Mép", padding=8)
        box_ditch.pack(fill="x", pady=3)
        gdc = ttk.Frame(box_ditch); gdc.pack(fill="x")
        ttk.Label(gdc, text="Đáy rãnh b (m):").grid(row=0, column=0, sticky="w")
        self.ditch_b = ttk.Entry(gdc, width=8); self.ditch_b.insert(0, "0.30"); self.ditch_b.grid(row=0, column=1, padx=3)
        ttk.Label(gdc, text="Chiều cao H (m):").grid(row=0, column=2, sticky="w")
        self.ditch_H = ttk.Entry(gdc, width=8); self.ditch_H.insert(0, "0.40"); self.ditch_H.grid(row=0, column=3, padx=3)
        ttk.Label(gdc, text="Sâu nước h (m):").grid(row=1, column=0, sticky="w")
        self.ditch_h = ttk.Entry(gdc, width=8); self.ditch_h.insert(0, "0.25"); self.ditch_h.grid(row=1, column=1, padx=3)
        ttk.Label(gdc, text="Độ dốc i:").grid(row=1, column=2, sticky="w")
        self.ditch_i = ttk.Entry(gdc, width=8); self.ditch_i.insert(0, "0.005"); self.ditch_i.grid(row=1, column=3, padx=3)
        ttk.Button(box_ditch, text="Kiểm Tra Rãnh", command=self.calc_ditch).pack(fill="x", pady=3)
        self.lbl_ditch_res = tk.Label(box_ditch, text="Chưa tính", font=("Segoe UI", 8, "bold"), fg="#00796b")
        self.lbl_ditch_res.pack(anchor="w")

        right = ttk.Frame(paned, padding=6); paned.add(right, weight=1)
        box_diag6 = ttk.LabelFrame(right, text="Mặt Cắt Thủy Lực Cống Thoát Nước", padding=4)
        box_diag6.pack(fill="both", expand=True)

        self.fig_pipe = Figure(figsize=(5.5, 3.5), dpi=95)
        self.ax_pipe = self.fig_pipe.add_subplot(111)
        self.canvas_pipe = FigureCanvasTkAgg(self.fig_pipe, master=box_diag6)
        self.canvas_pipe.get_tk_widget().pack(fill="both", expand=True)

        box_exp6 = ttk.LabelFrame(right, text="💡 Tiêu Chuẩn Thủy Lực Cống & Tuyến Ống (TCVN 7957)", padding=6)
        box_exp6.pack(fill="x", pady=4)
        exp6_txt = (
            "• Độ đầy tính toán cống thoát nước mưa TCVN 7957: Với cống D <= 500mm, h/D khống chế <= 0.6 - 0.7.\n"
            "• Vận tốc tự làm sạch: v >= 0.7 m/s (chống bồi lắng bùn đất, cát mịn).\n"
            "• Vận tốc giới hạn không gây xói: Cống BTCT: v <= 4.0 - 5.0 m/s; Ống nhựa uPVC/HDPE: v <= 7.0 m/s.\n"
            "• Ống đứng phễu thu: Luôn chọn Dx >= 100mm để chống tắc rác và cành cây."
        )
        tk.Label(box_exp6, text=exp6_txt, justify="left", font=("Segoe UI", 8), fg="#37474f").pack(anchor="w")

        self.calc_pipe_flow()
        self.calc_bridge_pipes()
        self.calc_ditch()

    def calc_pipe_flow(self):
        try:
            D = float(self.pipe_D.get())
            h_D = float(self.pipe_hD.get())
            i = float(self.pipe_i.get())
            n = float(self.pipe_n.get())
            Qyc = float(self.pipe_Qyc.get()) / 1000.0

            h, theta, A, Pw, Rh, V, Qkn = DrainageFormulas.circular_pipe_partial(D, h_D, i, n)
            safe = Qkn >= Qyc
            v_clean = "Đạt tự làm sạch (v >= 0.7m/s)" if V >= 0.7 else "Vận tốc thấp (nguy cơ bồi lắng cặn)"

            res = (
                f">> Mực nước h = {h*1000:.1f} mm | Diện tích ướt A = {A:.4f} m2 | Bán kính TL R = {Rh:.4f} m\n"
                f">> Vận tốc dòng chảy V = {V:.2f} m/s ({v_clean})\n"
                f">> Khả năng chuyển tải Qkn = {Qkn*1000:.2f} L/s ({Qkn:.4f} m3/s) | Qyc = {Qyc*1000:.1f} L/s\n"
                f">> ĐÁNH GIÁ: {'ĐỦ KHẢ NĂNG THOÁT NƯỚC (AN TOÀN)' if safe else 'KHÔNG ĐỦ (CẦN TĂNG D HOẶC ĐỘ DỐC)'}"
            )
            self.lbl_pipe_res.config(text=res, fg="#1b5e20" if safe else "#b71c1c")

            self._plot_pipe_cross_section(D, h)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def _plot_pipe_cross_section(self, D, h):
        self.ax_pipe.clear()
        theta = np.linspace(0, 2*np.pi, 120)
        r = D / 2.0
        self.ax_pipe.plot(r * np.cos(theta), r * np.sin(theta), color='#0d47a1', lw=2.5, label=f'Thành cống D={D*1000:.0f}mm')

        y_water = -r + h
        if h < D:
            val = max(-1.0, min(1.0, y_water / r))
            phi = math.asin(val)
            phi_arr = np.linspace(-math.pi - phi, phi, 80)
            x_pts = list(r * np.cos(phi_arr))
            y_pts = list(r * np.sin(phi_arr))
            x_pts.extend([r * math.cos(phi), -r * math.cos(phi)])
            y_pts.extend([y_water, y_water])
            self.ax_pipe.fill(x_pts, y_pts, color='#81d4fa', alpha=0.55, label=f'Mực nước h={h*1000:.0f}mm')
        else:
            self.ax_pipe.fill(r * np.cos(theta), r * np.sin(theta), color='#81d4fa', alpha=0.55, label='Chảy đầy 100%')

        self.ax_pipe.set_aspect('equal')
        self.ax_pipe.set_title(f"MẶT CẮT THỦY LỰC CỐNG (D = {D*1000:.0f} mm, h/D = {h/D:.2f})", fontsize=9, fontweight='bold')
        self.ax_pipe.legend(loc="upper right", fontsize=7)
        self.ax_pipe.grid(True, linestyle=":", alpha=0.5)
        self.fig_pipe.tight_layout()
        self.canvas_pipe.draw()

    def calc_bridge_pipes(self):
        try:
            Qin = float(self.down_Qin.get()) / 1000.0
            N = int(self.long_N.get())
            d = 0.03
            x, Dx_calc, Dx_rec = DrainageFormulas.downspout_sizing(Qin, d)
            Q_tot = Qin * N
            Dv_calc, Dv_rec = DrainageFormulas.collector_pipe_sizing(Q_tot, 0.010, 0.011)

            res = (
                f">> Ống đứng phễu thu: Dx tính = {Dx_calc*1000:.1f} mm  ==>  KIẾN NGHỊ: Dx >= {Dx_rec*1000:.0f} mm\n"
                f">> Tuyến ống dọc dầm: Q_tổng = {Q_tot*1000:.2f} L/s ({N} hố) | Dv tính = {Dv_calc*1000:.1f} mm  ==>  KIẾN NGHỊ: Dv >= {Dv_rec*1000:.0f} mm"
            )
            self.lbl_bridge_pipes_res.config(text=res)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def calc_ditch(self):
        try:
            b = float(self.ditch_b.get())
            H = float(self.ditch_H.get())
            h = float(self.ditch_h.get())
            i = float(self.ditch_i.get())
            A, P_w, R, V, Qr = DrainageFormulas.channel_capacity(b, H, h, 0, 0, i, 0.012)
            self.lbl_ditch_res.config(
                text=f">> Diện tích ướt A = {A:.4f} m2 | Vận tốc V = {V:.2f} m/s | Khả năng thoát rãnh mép Qr = {Qr*1000:.2f} L/s"
            )
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    # --------------------------------------------------------------------------
    # TAB 7: THƯ VIỆN TIÊU CHUẨN, TRẠM KHÍ TƯỢNG & KHUYẾN NGHỊ
    # --------------------------------------------------------------------------
    def _init_tab_lookup(self):
        f = self.tab_lookup
        sub_nb = ttk.Notebook(f)
        sub_nb.pack(fill="both", expand=True, padx=6, pady=6)

        tab_st = ttk.Frame(sub_nb)
        tab_c = ttk.Frame(sub_nb)
        tab_n = ttk.Frame(sub_nb)
        tab_limit = ttk.Frame(sub_nb)
        tab_rec = ttk.Frame(sub_nb)

        sub_nb.add(tab_st, text=" 📍 32 Trạm Khí Tượng (TCVN 7957) ")
        sub_nb.add(tab_c, text=" 🌊 Hệ Số Dòng Chảy C ")
        sub_nb.add(tab_n, text=" 🧱 Hệ Số Nhám Manning n ")
        sub_nb.add(tab_limit, text=" 📏 Giới Hạn Vệt Ngập Tcp ")
        sub_nb.add(tab_rec, text=" 💡 Khuyến Nghị Kỹ Thuật ")

        # --- Bảng Trạm Mưa ---
        top_s = ttk.Frame(tab_st, padding=4); top_s.pack(fill="x")
        ttk.Label(top_s, text="🔍 Tìm trạm / tỉnh:").pack(side="left", padx=4)
        self.ent_search_st = ttk.Entry(top_s, width=20); self.ent_search_st.pack(side="left", padx=4)
        self.ent_search_st.bind("<KeyRelease>", self._filter_stations_table)
        ttk.Button(top_s, text="📌 Áp Dụng Trạm Đã Chọn Vào Tab 1", command=self._apply_selected_station).pack(side="right", padx=6)

        tree_s_f = ttk.Frame(tab_st); tree_s_f.pack(fill="both", expand=True, padx=4, pady=2)
        cols_s = ("name", "region", "A", "C", "b", "n")
        self.tree_stations = ttk.Treeview(tree_s_f, columns=cols_s, show="headings", height=12)
        self.tree_stations.heading("name", text="Tên Trạm Khí Tượng")
        self.tree_stations.heading("region", text="Khu Vực")
        self.tree_stations.heading("A", text="Tham số A")
        self.tree_stations.heading("C", text="Hệ số C")
        self.tree_stations.heading("b", text="Tham số b")
        self.tree_stations.heading("n", text="Số mũ n")
        self.tree_stations.column("name", width=220, anchor="w")
        self.tree_stations.column("region", width=150, anchor="w")
        self.tree_stations.column("A", width=80, anchor="center")
        self.tree_stations.column("C", width=80, anchor="center")
        self.tree_stations.column("b", width=80, anchor="center")
        self.tree_stations.column("n", width=80, anchor="center")
        sy_s = ttk.Scrollbar(tree_s_f, orient="vertical", command=self.tree_stations.yview)
        self.tree_stations.configure(yscrollcommand=sy_s.set)
        self.tree_stations.pack(side="left", fill="both", expand=True)
        sy_s.pack(side="right", fill="y")
        self._populate_stations_table(STATIONS_TABLE)

        # --- Bảng Hệ Số C ---
        top_c = ttk.Frame(tab_c, padding=4); top_c.pack(fill="x")
        ttk.Button(top_c, text="📌 Áp Dụng Hệ Số C Vào Tính Toán", command=self._apply_selected_C).pack(side="right", padx=6)
        cols_c = ("surface", "p2", "p5", "p10", "p25", "p50", "note")
        self.tree_c = ttk.Treeview(tab_c, columns=cols_c, show="headings", height=8)
        self.tree_c.heading("surface", text="Loại mặt phủ thoát nước")
        self.tree_c.heading("p2", text="P = 2 năm")
        self.tree_c.heading("p5", text="P = 5 năm")
        self.tree_c.heading("p10", text="P = 10 năm")
        self.tree_c.heading("p25", text="P = 25 năm")
        self.tree_c.heading("p50", text="P = 50 năm")
        self.tree_c.heading("note", text="Ghi chú kỹ thuật")
        self.tree_c.column("surface", width=260, anchor="w")
        for p in ["p2", "p5", "p10", "p25", "p50"]: self.tree_c.column(p, width=75, anchor="center")
        self.tree_c.column("note", width=240, anchor="w")
        self.tree_c.pack(fill="both", expand=True, padx=4, pady=4)
        for row in RUNOFF_COEFF_TABLE: self.tree_c.insert("", "end", values=row)

        # --- Bảng Manning n ---
        top_n = ttk.Frame(tab_n, padding=4); top_n.pack(fill="x")
        ttk.Button(top_n, text="📌 Áp Dụng Hệ Số n", command=self._apply_selected_n).pack(side="right", padx=6)
        cols_n = ("mat", "n_rec", "n_range", "desc")
        self.tree_n = ttk.Treeview(tab_n, columns=cols_n, show="headings", height=8)
        self.tree_n.heading("mat", text="Loại vật liệu / kết cấu")
        self.tree_n.heading("n_rec", text="n Thiết kế")
        self.tree_n.heading("n_range", text="Dải n")
        self.tree_n.heading("desc", text="Ứng dụng điển hình")
        self.tree_n.column("mat", width=280, anchor="w")
        self.tree_n.column("n_rec", width=85, anchor="center")
        self.tree_n.column("n_range", width=110, anchor="center")
        self.tree_n.column("desc", width=280, anchor="w")
        self.tree_n.pack(fill="both", expand=True, padx=4, pady=4)
        for row in MANNING_ROUGHNESS_TABLE: self.tree_n.insert("", "end", values=row)

        # --- Bảng Tcp ---
        top_l = ttk.Frame(tab_limit, padding=4); top_l.pack(fill="x")
        ttk.Button(top_l, text="📌 Áp Dụng Vệt Ngập Tcp Đã Chọn", command=self._apply_selected_Tcp).pack(side="right", padx=6)
        cols_l = ("cls", "tcp", "rule")
        self.tree_limit = ttk.Treeview(tab_limit, columns=cols_l, show="headings", height=8)
        self.tree_limit.heading("cls", text="Cấp đường / Loại công trình")
        self.tree_limit.heading("tcp", text="Giới hạn Tcp (m)")
        self.tree_limit.heading("rule", text="Quy định kỹ thuật")
        self.tree_limit.column("cls", width=280, anchor="w")
        self.tree_limit.column("tcp", width=120, anchor="center")
        self.tree_limit.column("rule", width=420, anchor="w")
        self.tree_limit.pack(fill="both", expand=True, padx=4, pady=4)
        for row in SPREAD_LIMITS_TABLE: self.tree_limit.insert("", "end", values=row)

        # --- Bảng Khuyến Nghị Kỹ Thuật ---
        cols_rec = ("seg", "slope", "width", "lc", "dx", "dv")
        tree_rec = ttk.Treeview(tab_rec, columns=cols_rec, show="headings", height=8)
        tree_rec.heading("seg", text="Điều Kiện Hình Học / Địa Hình")
        tree_rec.heading("slope", text="Độ Dốc Dọc SL")
        tree_rec.heading("width", text="Bề Rộng Tuyến Wp")
        tree_rec.heading("lc", text="Khoảng Cách Hố Lc")
        tree_rec.heading("dx", text="Ống Đứng Dx")
        tree_rec.heading("dv", text="Ống Gom Dọc Dv")
        tree_rec.column("seg", width=250, anchor="w")
        tree_rec.column("slope", width=130, anchor="center")
        tree_rec.column("width", width=120, anchor="center")
        tree_rec.column("lc", width=130, anchor="center")
        tree_rec.column("dx", width=110, anchor="center")
        tree_rec.column("dv", width=110, anchor="center")
        tree_rec.pack(fill="both", expand=True, padx=6, pady=6)
        for r in GENERAL_DESIGN_RECOMMENDATIONS: tree_rec.insert("", "end", values=r)

    def _populate_stations_table(self, data):
        for r in self.tree_stations.get_children(): self.tree_stations.delete(r)
        for st in data:
            self.tree_stations.insert("", "end", values=(st[0], st[5], st[1], st[2], st[3], st[4]))

    def _filter_stations_table(self, event):
        keyword = self.ent_search_st.get().strip().lower()
        if not keyword:
            self._populate_stations_table(STATIONS_TABLE)
        else:
            filtered = [st for st in STATIONS_TABLE if keyword in st[0].lower() or keyword in st[5].lower()]
            self._populate_stations_table(filtered)

    def _apply_selected_station(self):
        sel = self.tree_stations.selection()
        if not sel:
            messagebox.showwarning("Nhắc nhở", "Vui lòng click chọn 1 trạm khí tượng trong bảng!")
            return
        vals = self.tree_stations.item(sel[0])["values"]
        st_name = vals[0]
        self.ent_A.delete(0, tk.END); self.ent_A.insert(0, str(vals[2]))
        self.ent_C.delete(0, tk.END); self.ent_C.insert(0, str(vals[3]))
        self.ent_b.delete(0, tk.END); self.ent_b.insert(0, str(vals[4]))
        self.ent_n.delete(0, tk.END); self.ent_n.insert(0, str(vals[5]))
        self.lbl_current_station.config(text=f"Trạm mưa: {st_name}")
        self.notebook.select(self.tab_hydrology)
        self.calc_hydrology()
        messagebox.showinfo("Thành công", f"Đã nạp trạm {st_name} vào Tab 1 và cập nhật biểu đồ IDF!")

    def _apply_selected_C(self):
        sel = self.tree_c.selection()
        if not sel:
            messagebox.showwarning("Nhắc nhở", "Vui lòng chọn 1 loại mặt phủ trong bảng!")
            return
        vals = self.tree_c.item(sel[0])["values"]
        c_val = str(vals[2])
        self.deck_C.delete(0, tk.END); self.deck_C.insert(0, c_val)
        self.notebook.select(self.tab_bridge_deck)
        self.calc_bridge_deck()
        messagebox.showinfo("Đã áp dụng", f"Đã cập nhật hệ số dòng chảy C = {c_val} ({vals[0]})!")

    def _apply_selected_n(self):
        sel = self.tree_n.selection()
        if not sel:
            messagebox.showwarning("Nhắc nhở", "Vui lòng chọn 1 loại kết cấu trong bảng!")
            return
        vals = self.tree_n.item(sel[0])["values"]
        n_val = str(vals[1])
        self.deck_n.delete(0, tk.END); self.deck_n.insert(0, n_val)
        self.pipe_n.delete(0, tk.END); self.pipe_n.insert(0, n_val)
        messagebox.showinfo("Đã áp dụng", f"Đã cập nhật hệ số nhám Manning n = {n_val} ({vals[0]})!")

    def _apply_selected_Tcp(self):
        sel = self.tree_limit.selection()
        if not sel:
            messagebox.showwarning("Nhắc nhở", "Vui lòng chọn 1 cấp đường trong bảng!")
            return
        vals = self.tree_limit.item(sel[0])["values"]
        tcp_val = str(vals[1]).split(" ")[0].split("-")[0]
        self.deck_T.delete(0, tk.END); self.deck_T.insert(0, tcp_val)
        self.ent_Tcp_grate.delete(0, tk.END); self.ent_Tcp_grate.insert(0, tcp_val)
        messagebox.showinfo("Đã áp dụng", f"Đã cập nhật giới hạn vệt ngập Tcp = {tcp_val} m ({vals[0]})!")

    # --------------------------------------------------------------------------
    # QUẢN LÝ DỰ ÁN & XUẤT CSV
    # --------------------------------------------------------------------------
    def new_project(self):
        if messagebox.askyesno("Tạo Dự Án Mới", "Bạn có muốn khởi tạo một dự án mới hoàn toàn?"):
            self.project_name.set("Dự Án Thoát Nước Mới")
            self.segments_data = []
            self.recalc_all_qyc()
            messagebox.showinfo("Thông báo", "Đã khởi tạo dự án mới thành công!")

    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON File", "*.json")])
        if not path: return
        data = {
            "project_name": self.project_name.get(),
            "station": self.cb_station.get(),
            "A": self.ent_A.get(), "C": self.ent_C.get(), "b": self.ent_b.get(), "n": self.ent_n.get(),
            "P": self.ent_P.get(), "to": self.ent_to.get(), "tg": self.ent_tg.get(),
            "deck_B": self.deck_B.get(), "deck_SL": self.deck_SL.get(), "deck_Sx": self.deck_Sx.get(),
            "deck_T": self.deck_T.get(), "deck_W": self.deck_W.get(), "deck_Lg": self.deck_Lg.get(),
            "deck_Wshoulder": self.deck_Wshoulder.get(), "deck_Wlane": self.deck_Wlane.get(),
            "segments": self.segments_data
        }
        with open(path, "w", encoding="utf-8") as fp: json.dump(data, fp, ensure_ascii=False, indent=2)
        messagebox.showinfo("Thành công", "Đã lưu dự án thành công!")

    def load_project(self):
        path = filedialog.askopenfilename(filetypes=[("JSON File", "*.json")])
        if not path: return
        with open(path, "r", encoding="utf-8") as fp: data = json.load(fp)
        if "project_name" in data:
            self.project_name.set(data["project_name"])
        for key, ent in [("A", self.ent_A), ("C", self.ent_C), ("b", self.ent_b), ("n", self.ent_n),
                         ("P", self.ent_P), ("to", self.ent_to), ("tg", self.ent_tg),
                         ("deck_B", self.deck_B), ("deck_SL", self.deck_SL), ("deck_Sx", self.deck_Sx),
                         ("deck_T", self.deck_T), ("deck_W", self.deck_W), ("deck_Lg", self.deck_Lg),
                         ("deck_Wshoulder", self.deck_Wshoulder), ("deck_Wlane", self.deck_Wlane)]:
            if key in data:
                ent.delete(0, tk.END); ent.insert(0, str(data[key]))
        if "segments" in data:
            self.segments_data = data["segments"]
            self.recalc_all_qyc()
        messagebox.showinfo("Thành công", f"Đã nạp tệp dự án: {data.get('project_name', '')}!")
        self.calc_hydrology()
        self.calc_bridge_deck()

    def export_qyc_csv(self):
        items = self.tree_qyc.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Chưa có phân đoạn tuyến nào để xuất dữ liệu!")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV File", "*.csv")])
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.writer(fp)
            writer.writerow(["STT", "Hạng mục", "Từ Km", "Đến Km", "L (m)", "B (m)", "Dốc ngang", "Dốc dọc",
                             "Hệ số C", "Diện tích F (ha)", "Rộng xiên (m)", "to (phút)", "tr (phút)", "t (phút)",
                             "q (L/s.ha)", "Q bản thân (m3/s)", "Q tổng (m3/s)"])
            for it in items: writer.writerow(self.tree_qyc.item(it)["values"])
        messagebox.showinfo("Thành công", f"Đã xuất dữ liệu phân đoạn tuyến ra file:\n{path}")

    def export_grates_csv(self):
        items = self.tree_grates.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Hãy bấm 'Chạy Mô Phỏng Chuỗi' ở Tab 4 trước khi xuất file!")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV File", "*.csv")])
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.writer(fp)
            writer.writerow(["Hố thu", "Lý trình", "Q đến (L/s)", "Q tràn trước (L/s)", "Tổng Q rãnh (L/s)",
                             "Vệt ngập T (m)", "T cho phép (m)", "Vận tốc (m/s)", "Hiệu suất E", "Q thu (L/s)", "Q dư (L/s)", "Đánh giá"])
            for it in items: writer.writerow(self.tree_grates.item(it)["values"])
        messagebox.showinfo("Thành công", f"Đã xuất kết quả chuỗi hố thu ra file:\n{path}")


# ==============================================================================
# KHỞI CHẠY ỨNG DỤNG TỔNG QUÁT
# ==============================================================================
if __name__ == "__main__":
    app = DrainageApp()
    app.mainloop()