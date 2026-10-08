# -*- coding: utf-8 -*-
"""
PHẦN MỀM TÍNH TOÁN THỦY LỰC CÔNG TRÌNH THOÁT NƯỚC MƯA
Tiêu chuẩn áp dụng: TCVN 7957:2023
Tích hợp: Bộ Bảng Tra Cứu Tiêu Chuẩn & Chú Thích Rõ Nguồn Gốc Từng Thông Số
Chạy trực tiếp trên Windows (GUI Tkinter/TTK)
"""

import math
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ==============================================================================
# 1. CƠ SỞ DỮ LIỆU ĐẦY ĐỦ TỪ TCVN 7957:2023 (FILE EXCEL GỐC)
# ==============================================================================

# Bảng A.1: 49 Trạm đo mưa / Thành phố
STATIONS_DATA = {
    "Hồ Chí Minh": {"A": 7290.0, "C": 0.59, "b": 32.0, "n": 0.88},
    "Hà Nội": {"A": 5890.0, "C": 0.65, "b": 20.0, "n": 0.84},
    "Đà Nẵng": {"A": 2170.0, "C": 0.52, "b": 10.0, "n": 0.65},
    "Hải Phòng": {"A": 5950.0, "C": 0.55, "b": 21.0, "n": 0.82},
    "Bảo Lộc": {"A": 8130.0, "C": 0.58, "b": 30.0, "n": 0.85},
    "Bình Dương": {"A": 7923.0, "C": 0.53, "b": 30.0, "n": 0.87},
    "Bắc Cạn": {"A": 8150.0, "C": 0.53, "b": 27.0, "n": 0.87},
    "Bắc Giang": {"A": 7650.0, "C": 0.55, "b": 28.0, "n": 0.85},
    "Bắc Quang": {"A": 8860.0, "C": 0.57, "b": 29.0, "n": 0.82},
    "Ba Xuyên": {"A": 9430.0, "C": 0.55, "b": 30.0, "n": 0.90},
    "Buôn Mê Thuột": {"A": 8920.0, "C": 0.58, "b": 28.0, "n": 0.89},
    "Cà Mau": {"A": 9210.0, "C": 0.48, "b": 25.0, "n": 0.92},
    "Cửa Tùng": {"A": 2340.0, "C": 0.49, "b": 14.0, "n": 0.62},
    "Đô Lương": {"A": 3540.0, "C": 0.55, "b": 19.0, "n": 0.70},
    "Hà Giang": {"A": 4640.0, "C": 0.42, "b": 22.0, "n": 0.79},
    "Hà Nam": {"A": 4850.0, "C": 0.51, "b": 19.0, "n": 0.80},
    "Hải Dương": {"A": 4260.0, "C": 0.42, "b": 18.0, "n": 0.78},
    "Hòn Gai": {"A": 4720.0, "C": 0.42, "b": 20.0, "n": 0.78},
    "Hưng Yên": {"A": 4760.0, "C": 0.59, "b": 20.0, "n": 0.79},
    "Hoà Bình": {"A": 5500.0, "C": 0.45, "b": 19.0, "n": 0.82},
    "Huế": {"A": 2610.0, "C": 0.55, "b": 12.0, "n": 0.55},
    "Lào Cai": {"A": 6210.0, "C": 0.58, "b": 22.0, "n": 0.84},
    "Lai Châu": {"A": 4200.0, "C": 0.50, "b": 16.0, "n": 0.80},
    "Liên Khương": {"A": 9230.0, "C": 0.52, "b": 29.0, "n": 0.92},
    "Móng Cái": {"A": 4860.0, "C": 0.46, "b": 20.0, "n": 0.79},
    "Nam Định": {"A": 4320.0, "C": 0.55, "b": 19.0, "n": 0.79},
    "Nha Trang": {"A": 1810.0, "C": 0.55, "b": 12.0, "n": 0.65},
    "Ninh Bình": {"A": 4930.0, "C": 0.48, "b": 19.0, "n": 0.80},
    "Phan Thiết": {"A": 7070.0, "C": 0.55, "b": 25.0, "n": 0.92},
    "Plây Cu": {"A": 8820.0, "C": 0.49, "b": 29.0, "n": 0.92},
    "Quảng Ngãi": {"A": 2590.0, "C": 0.58, "b": 16.0, "n": 0.67},
    "Quảng Trị": {"A": 2230.0, "C": 0.48, "b": 15.0, "n": 0.62},
    "Quy Nhơn": {"A": 2610.0, "C": 0.55, "b": 14.0, "n": 0.68},
    "Sơn La": {"A": 4120.0, "C": 0.42, "b": 20.0, "n": 0.80},
    "Sơn Tây": {"A": 5210.0, "C": 0.62, "b": 19.0, "n": 0.82},
    "Sa Pa": {"A": 3720.0, "C": 0.50, "b": 10.0, "n": 0.56},
    "Tây Hiếu": {"A": 3360.0, "C": 0.54, "b": 19.0, "n": 0.69},
    "Tam Đảo": {"A": 5460.0, "C": 0.55, "b": 20.0, "n": 0.81},
    "Thái Bình": {"A": 5220.0, "C": 0.45, "b": 19.0, "n": 0.81},
    "Thái Nguyên": {"A": 7710.0, "C": 0.52, "b": 28.0, "n": 0.85},
    "Thanh Hoá": {"A": 3640.0, "C": 0.53, "b": 19.0, "n": 0.72},
    "Trà Vinh": {"A": 9150.0, "C": 0.53, "b": 28.0, "n": 0.97},
    "Tuy Hoà": {"A": 2820.0, "C": 0.48, "b": 15.0, "n": 0.72},
    "Tuyên Quang": {"A": 8670.0, "C": 0.55, "b": 30.0, "n": 0.87},
    "Vân Lý": {"A": 4560.0, "C": 0.52, "b": 21.0, "n": 0.79},
    "Vinh": {"A": 3430.0, "C": 0.55, "b": 20.0, "n": 0.69},
    "Việt Trì": {"A": 5830.0, "C": 0.55, "b": 18.0, "n": 0.85},
    "Vĩnh Yên": {"A": 5670.0, "C": 0.53, "b": 21.0, "n": 0.80},
    "Yên Bái": {"A": 7500.0, "C": 0.54, "b": 29.0, "n": 0.85},
}

# Bảng 3: Hệ số dòng chảy Psi theo P
PSI_TABLE = {
    "Mặt đường atphan": {2: 0.73, 5: 0.77, 10: 0.81, 25: 0.86, 50: 0.90},
    "Mái nhà, mặt phủ bêtông": {2: 0.75, 5: 0.80, 10: 0.81, 25: 0.88, 50: 0.92},
    "Mặt cỏ, vườn, công viên - Độ dốc nhỏ 1-2%": {2: 0.32, 5: 0.34, 10: 0.37, 25: 0.40, 50: 0.44},
    "Mặt cỏ, vườn, công viên - Độ dốc TB 2-7%": {2: 0.37, 5: 0.40, 10: 0.43, 25: 0.46, 50: 0.49},
    "Mặt cỏ, vườn, công viên - Độ dốc lớn >7%": {2: 0.40, 5: 0.43, 10: 0.45, 25: 0.49, 50: 0.52},
}

# Bảng 5: Hệ số mặt phủ Z
Z_TABLE = {
    "Mái nhà mặt đường nhựa": 0.240,
    "Mặt đường lát đá": 0.224,
    "Mặt đường cấp phối": 0.145,
    "Mặt đường ghép đá": 0.125,
    "Mặt đường đất": 0.084,
    "Công viên, đất trồng cây (á sét)": 0.038,
    "Công viên, đất cây xanh (á cát)": 0.020,
    "Bãi cỏ": 0.015,
}

# Bảng 1.1: Hệ số nhám bề mặt đường n
N_SURFACE_TABLE = {
    "BTXM": 0.010,
    "Bê tông nhẵn": 0.014,
    "Bê tông thô": 0.016,
    "Đá dăm": 0.025,
    "Đá cuội sỏi đổ": 0.025,
}

# Bảng 1.1: Hệ số nhám thành cống mương n1
N_CONDUIT_TABLE = {
    "Xi măng mài nhắn, gỗ bào nhắn": 0.010,
    "Gỗ bào, gang phủ": 0.012,
    "Bê tông nhẵn": 0.014,
    "Bê tông thô": 0.016,
    "Kênh đất trong điều kiện giữ gìn tốt": 0.023,
    "Kênh đất trong điều kiện giữ gìn trung bình": 0.027,
    "Đá hộc xây vữa": 0.0225,
    "Đá dăm xếp": 0.025,
    "Đá cuội sỏi đổ": 0.025,
    "Sông suối tự nhiên": 0.030,
}

LOOKUP_DATABASE = {
    "Bảng A.1 - Hằng số khí hậu (49 Trạm mưa)": {
        "type": "A1",
        "columns": ["TT", "Tên thành phố / Trạm", "A", "C", "b", "n"],
        "widths": [50, 180, 80, 80, 80, 80],
        "aligns": ["center", "w", "e", "e", "e", "e"],
        "rows": [
            [str(i + 1), k, f"{v['A']:.0f}", f"{v['C']:.2f}", f"{v['b']:.0f}", f"{v['n']:.2f}"]
            for i, (k, v) in enumerate(STATIONS_DATA.items())
        ],
        "note": "Công thức cường độ mưa: q = [A*(1 + C*lgP)*K] / [(t + b)^n] (L/s.ha). Chọn trạm rồi nhấn 'Áp dụng'."
    },
    "Bảng 1 & 2 - Chu kỳ lặp lại mưa P (Đô thị & KCN)": {
        "type": "P_TABLE",
        "columns": ["Loại công trình / Tính chất", "Đặc biệt & Loại I", "Loại II, III & IV", "Loại V / Giá trị P"],
        "widths": [240, 130, 130, 130],
        "aligns": ["w", "center", "center", "center"],
        "rows": [
            ["Sông thoát nước", "≥ 20", "≥ 10", "≥ 10"],
            ["Kênh, mương", "10 ÷ 20", "5 ÷ 10", "2 ÷ 5"],
            ["Cống chính", "5 ÷ 10", "2 ÷ 5", "1 ÷ 2"],
            ["Cống nhánh", "1 ÷ 2", "0.5 ÷ 1", "0.33 ÷ 0.5"],
            ["KCN có công nghệ bình thường", "-", "-", "5 - 10"],
            ["KCN có cơ sở đặc biệt", "-", "-", "10 - 20"]
        ],
        "note": "Xác định chu kỳ lặp P (năm) theo phân cấp đô thị hoặc yêu cầu của khu công nghiệp."
    },
    "Bảng 3 - Hệ số dòng chảy Psi (ψ)": {
        "type": "PSI",
        "columns": ["Tính chất bề mặt thoát nước", "P = 2 năm", "P = 5 năm", "P = 10 năm", "P = 25 năm", "P = 50 năm"],
        "widths": [280, 80, 80, 80, 80, 80],
        "aligns": ["w", "e", "e", "e", "e", "e"],
        "rows": [
            [surf, f"{p_dict[2]:.2f}", f"{p_dict[5]:.2f}", f"{p_dict[10]:.2f}", f"{p_dict[25]:.2f}", f"{p_dict[50]:.2f}"]
            for surf, p_dict in PSI_TABLE.items()
        ],
        "note": "Hệ số dòng chảy bề mặt. Khi lưu vực gồm nhiều loại bề mặt, tính Psi trung bình theo diện tích."
    },
    "Bảng 4 - Hệ số phân bổ mưa Beta (β)": {
        "type": "BETA",
        "columns": ["Diện tích lưu vực F (ha)", "Hệ số Beta (β)"],
        "widths": [200, 150],
        "aligns": ["w", "center"],
        "rows": [
            ["F < 500 ha", "1.00"],
            ["F = 500 ha", "0.95"],
            ["F = 1000 ha", "0.90"],
            ["F = 2000 ha", "0.85"],
            ["F = 4000 ha", "0.80"],
            ["F = 6000 ha", "0.70"],
            ["F = 8000 ha", "0.60"],
            ["F = 10000 ha", "0.55"]
        ],
        "note": "Hệ số giảm cường độ khi vùng mưa rào không bao phủ kín toàn bộ diện tích lưu vực lớn."
    },
    "Bảng 5 - Hệ số mặt phủ Z": {
        "type": "Z_COEF",
        "columns": ["Loại mặt phủ", "Hệ số Z"],
        "widths": [240, 120],
        "aligns": ["w", "e"],
        "rows": [
            [k, f"{v:.3f}"] for k, v in Z_TABLE.items()
        ],
        "note": "Dùng trong công thức tính thời gian nước chảy trên bề mặt sườn t0."
    },
    "Bảng 1.1 - Hệ số nhám n & n1 (Mặt đường & Cống)": {
        "type": "ROUGHNESS",
        "columns": ["Vật liệu / Mặt phủ", "Phạm vi áp dụng", "Hệ số nhám (n)"],
        "widths": [240, 160, 120],
        "aligns": ["w", "w", "center"],
        "rows": [
            ["BTXM", "Mặt đường phố (n)", "0.010"],
            ["Bê tông nhẵn", "Mặt đường phố (n)", "0.014"],
            ["Bê tông thô", "Mặt đường phố (n)", "0.016"],
            ["Đá dăm", "Mặt đường phố (n)", "0.025"],
            ["Đá cuội sỏi đổ", "Mặt đường phố (n)", "0.025"],
            ["Xi măng mài nhẵn, gỗ bào", "Thành cống, mương (n1)", "0.010"],
            ["Gỗ bào, gang phủ", "Thành cống, mương (n1)", "0.012"],
            ["Bê tông nhẵn", "Thành cống, mương (n1)", "0.014"],
            ["Bê tông thô", "Thành cống, mương (n1)", "0.016"],
            ["Kênh đất giữ gìn tốt", "Kênh đất (n1)", "0.023"],
            ["Kênh đất giữ gìn TB", "Kênh đất (n1)", "0.027"],
            ["Đá hộc xây vữa", "Mương đá (n1)", "0.0225"],
            ["Đá dăm xếp", "Mương xếp đá (n1)", "0.025"],
            ["Sông suối tự nhiên", "Lòng sông tự nhiên (n1)", "0.030"]
        ],
        "note": "Nguồn tham khảo: Giáo trình Thủy lực công trình - NXB Xây dựng."
    },
    "Bảng A.2 & Bảng 9 - Hệ số mưa rào, hệ số m & Manning": {
        "type": "MISC",
        "columns": ["Hạng mục công trình", "Giá trị quy chuẩn", "Ghi chú kỹ thuật"],
        "widths": [220, 150, 260],
        "aligns": ["w", "center", "w"],
        "rows": [
            ["Lưu vực F = 300 ha", "n_rào = 0.96", "Hệ số phân bố mưa rào Bảng A.2"],
            ["Lưu vực F = 500 ha", "n_rào = 0.94", "Bảng A.2"],
            ["Lưu vực F = 1000 ha", "n_rào = 0.91", "Bảng A.2"],
            ["Lưu vực F = 2000 ha", "n_rào = 0.87", "Bảng A.2"],
            ["Lưu vực F = 3000 ha", "n_rào = 0.83", "Bảng A.2"],
            ["Lưu vực F = 4000 ha", "n_rào = 0.80", "Bảng A.2"],
            ["Cống ngầm", "m = 2.0", "Hệ số giảm vận tốc t = t1 + m*t2"],
            ["Mương, máng", "m = 1.2", "Hệ số m trong dòng chảy hở"],
            ["Rãnh đường", "m = 1.2", "Hệ số m rãnh đường phố"],
            ["Cống BTCT (Bảng 9)", "Manning n = 0.013", "Mạng lưới cống bê tông thoát nước"],
            ["Cống ống nhựa uPVC/HDPE", "Manning n = 0.011 - 0.0115", "Ống thành trơn nhẵn"]
        ],
        "note": "Hệ số mưa rào áp dụng khi diện tích lưu vực F > 300 ha."
    }
}

# ==============================================================================
# 2. LỚP XỬ LÝ TÍNH TOÁN THỦY LỰC
# ==============================================================================
class DrainageCalculator:
    @staticmethod
    def calculate_all(inputs):
        A = float(inputs["A"])
        C = float(inputs["C"])
        b = float(inputs["b"])
        n_clim = float(inputs["n_clim"])
        P = float(inputs["P"])
        K_climate = float(inputs["K_climate"])

        Lx = float(inputs["Lx"])
        L_surf = float(inputs["L_surf"])
        Ftt = Lx * L_surf / 10000.0

        n_surf = float(inputs["n_surf"])
        Z = float(inputs["Z"])
        i_surf = float(inputs["i_surf"])
        I_rain = float(inputs["I_rain"])

        t0 = 1.5 * (n_surf**0.6) * (L_surf**0.6) / ((Z**0.3) * (i_surf**0.3) * (I_rain**0.3))

        conduit_shape = inputs["conduit_shape"]
        i_conduit = float(inputs["i_conduit"])
        n1 = float(inputs["n1"])

        if conduit_shape == "Cống hình chữ nhật":
            B = float(inputs["B"])
            H = float(inputs["H"])
            h_water = H * 0.75 if H < 0.9 else H - 0.2
            omega = B * h_water
            chi = B + 2.0 * h_water
            dim_str = f"B={B:.2f} m, H={H:.2f} m (h={h_water:.3f} m)"
        else:
            D = float(inputs["D"])
            omega = math.pi * (D / 2.0)**2
            chi = math.pi * D
            dim_str = f"D={D:.2f} m"

        R = omega / chi if chi > 0 else 0.0

        # Công thức Pavlovskii tính hệ số Chezy C
        y_pavlov = 2.5 * math.sqrt(n1) - 0.13 - 0.75 * math.sqrt(R) * (math.sqrt(n1) - 0.01)
        C_chezy = (R**y_pavlov) / n1 if n1 > 0 else 0.0
        V_conduit = C_chezy * math.sqrt(R * i_conduit)

        tr = 0.021 * Lx / V_conduit if V_conduit > 0 else 0.0
        t1 = t0 + tr
        m_coef = float(inputs["m_coef"])
        t2 = float(inputs.get("t2", 0.0))
        t_total = t1 + m_coef * t2

        q = A * (1.0 + C * math.log10(P)) * K_climate / ((t_total + b)**n_clim)
        q_mm = q / 166.667

        if Ftt < 500:
            beta = 1.0
        elif Ftt < 1000:
            beta = 0.95
        elif Ftt < 2000:
            beta = 0.90
        elif Ftt < 4000:
            beta = 0.85
        elif Ftt < 6000:
            beta = 0.80
        elif Ftt < 8000:
            beta = 0.70
        elif Ftt < 10000:
            beta = 0.60
        else:
            beta = 0.55

        psi = float(inputs["psi"])
        m_rain = 1.0 if Ftt < 300 else (1.0 / (1.0 + 0.001 * (Ftt**(2.0/3.0))))

        Q_ls = q * Ftt * beta * psi * m_rain
        Q_m3s = Q_ls / 1000.0

        omega_req = Q_m3s / V_conduit if V_conduit > 0 else 999.0
        is_safe = omega >= omega_req

        return {
            "Ftt": Ftt,
            "t0": t0,
            "tr": tr,
            "t1": t1,
            "t_total": t_total,
            "q": q,
            "q_mm": q_mm,
            "beta": beta,
            "psi": psi,
            "m_rain": m_rain,
            "Q_ls": Q_ls,
            "Q_m3s": Q_m3s,
            "omega": omega,
            "chi": chi,
            "R": R,
            "y_pavlov": y_pavlov,
            "C_chezy": C_chezy,
            "V_conduit": V_conduit,
            "omega_req": omega_req,
            "is_safe": is_safe,
            "dim_str": dim_str,
        }

# ==============================================================================
# 3. GIAO DIỆN PHẦN MỀM CHÍNH (WINDOWS DESKTOP)
# ==============================================================================
class DrainageApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phần Mềm Tính Toán Thoát Nước Mưa & Tra Cứu TCVN 7957:2023")
        self.geometry("1280x820")
        self.minsize(1100, 720)

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("vista")
        except Exception:
            pass

        self.last_results = None
        self.current_filtered_rows = []
        self.create_widgets()
        self.on_city_change()
        self.on_conduit_type_change()
        self.calculate()
        self.load_table_view()

    def create_widgets(self):
        header_frame = tk.Frame(self, bg="#1E3A8A", height=58)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        lbl_title = tk.Label(
            header_frame,
            text="TÍNH TOÁN THỦY LỰC THOÁT NƯỚC MƯA THEO TIÊU CHUẨN TCVN 7957:2023",
            font=("Segoe UI", 13, "bold"),
            fg="white",
            bg="#1E3A8A",
            pady=8
        )
        lbl_title.pack()

        main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ---------------- KHUNG NHẬP LIỆU BÊN TRÁI ----------------
        left_container = ttk.Frame(main_paned)
        main_paned.add(left_container, weight=1)

        canvas = tk.Canvas(left_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Khung chú giải màu sắc nguồn gốc dữ liệu
        legend_frame = tk.Frame(self.scrollable_frame, bg="#EFF6FF", bd=1, relief=tk.SOLID, padx=6, pady=4)
        legend_frame.pack(fill=tk.X, padx=4, pady=(2, 4))
        lbl_lg = tk.Label(
            legend_frame,
            text="🔵 [Tra Bảng X]: Nạp tự động từ tiêu chuẩn  |  🟠 [Nhập tay]: Khảo sát / Thiết kế",
            font=("Segoe UI", 8, "bold"),
            bg="#EFF6FF",
            fg="#1E40AF"
        )
        lbl_lg.pack(anchor="w")

        # --- Nhóm 1: Dự án & Trạm mưa ---
        grp_project = ttk.LabelFrame(self.scrollable_frame, text=" 1. Dự Án & Hằng Số Khí Tượng ", padding=8)
        grp_project.pack(fill=tk.X, pady=3, padx=4)

        # Trạm mưa
        ttk.Label(grp_project, text="Trạm mưa:").grid(row=0, column=0, sticky="w", pady=2)
        self.cbo_city = ttk.Combobox(grp_project, values=list(STATIONS_DATA.keys()), state="readonly", width=16)
        self.cbo_city.set("Hồ Chí Minh")
        self.cbo_city.grid(row=0, column=1, sticky="ew", pady=2)
        self.cbo_city.bind("<<ComboboxSelected>>", lambda e: self.on_city_change())
        lbl_tag_city = tk.Label(grp_project, text="[Tra Bảng A.1]", font=("Segoe UI", 8, "bold"), fg="#2563EB")
        lbl_tag_city.grid(row=0, column=2, sticky="w", padx=4)

        # Chu kỳ P
        ttk.Label(grp_project, text="Chu kỳ P (năm):").grid(row=1, column=0, sticky="w", pady=2)
        self.cbo_P = ttk.Combobox(grp_project, values=["2", "5", "10", "25", "50"], width=16, state="readonly")
        self.cbo_P.set("10")
        self.cbo_P.grid(row=1, column=1, sticky="ew", pady=2)
        self.cbo_P.bind("<<ComboboxSelected>>", lambda e: self.on_psi_update())
        lbl_tag_p = tk.Label(grp_project, text="[Tra Bảng 1 & 2]", font=("Segoe UI", 8, "bold"), fg="#2563EB")
        lbl_tag_p.grid(row=1, column=2, sticky="w", padx=4)

        # Hằng số A, C, b, n
        ttk.Label(grp_project, text="Hằng số (A,C,b,n):").grid(row=2, column=0, sticky="w", pady=2)
        param_frame = ttk.Frame(grp_project)
        param_frame.grid(row=2, column=1, sticky="ew", pady=2)
        self.ent_A = ttk.Entry(param_frame, width=6)
        self.ent_A.pack(side=tk.LEFT, padx=1)
        self.ent_C = ttk.Entry(param_frame, width=4)
        self.ent_C.pack(side=tk.LEFT, padx=1)
        self.ent_b = ttk.Entry(param_frame, width=4)
        self.ent_b.pack(side=tk.LEFT, padx=1)
        self.ent_n = ttk.Entry(param_frame, width=4)
        self.ent_n.pack(side=tk.LEFT, padx=1)
        lbl_tag_par = tk.Label(grp_project, text="[Tự động từ Bảng A.1]", font=("Segoe UI", 8), fg="#059669")
        lbl_tag_par.grid(row=2, column=2, sticky="w", padx=4)

        # Hệ số K
        ttk.Label(grp_project, text="Hệ số BĐKH (K):").grid(row=3, column=0, sticky="w", pady=2)
        self.ent_K = ttk.Entry(grp_project, width=16)
        self.ent_K.insert(0, "1.0")
        self.ent_K.grid(row=3, column=1, sticky="w", pady=2)
        lbl_tag_k = tk.Label(grp_project, text="[Nhập tay: K ≥ 1.0]", font=("Segoe UI", 8, "bold"), fg="#EA580C")
        lbl_tag_k.grid(row=3, column=2, sticky="w", padx=4)

        # --- Nhóm 2: Lưu vực & Chảy mặt ---
        grp_surface = ttk.LabelFrame(self.scrollable_frame, text=" 2. Lưu Vực & Dòng Chảy Mặt ", padding=8)
        grp_surface.pack(fill=tk.X, pady=3, padx=4)

        # Lx
        ttk.Label(grp_surface, text="Dài cống Lx (m):").grid(row=0, column=0, sticky="w", pady=2)
        self.ent_Lx = ttk.Entry(grp_surface, width=16)
        self.ent_Lx.insert(0, "44.07")
        self.ent_Lx.grid(row=0, column=1, sticky="w", pady=2)
        lbl_tag_lx = tk.Label(grp_surface, text="[Nhập tay: từ bình đồ]", font=("Segoe UI", 8, "bold"), fg="#EA580C")
        lbl_tag_lx.grid(row=0, column=2, sticky="w", padx=4)

        # L
        ttk.Label(grp_surface, text="Rộng thu nước L (m):").grid(row=1, column=0, sticky="w", pady=2)
        self.ent_Lsurf = ttk.Entry(grp_surface, width=16)
        self.ent_Lsurf.insert(0, "16.25")
        self.ent_Lsurf.grid(row=1, column=1, sticky="w", pady=2)
        lbl_tag_l = tk.Label(grp_surface, text="[Nhập tay: khảo sát]", font=("Segoe UI", 8, "bold"), fg="#EA580C")
        lbl_tag_l.grid(row=1, column=2, sticky="w", padx=4)

        # Mặt phủ Psi
        ttk.Label(grp_surface, text="Mặt phủ (Ψ):").grid(row=2, column=0, sticky="w", pady=2)
        self.cbo_flow_surf = ttk.Combobox(grp_surface, values=list(PSI_TABLE.keys()), state="readonly", width=16)
        self.cbo_flow_surf.set("Mặt đường atphan")
        self.cbo_flow_surf.grid(row=2, column=1, sticky="ew", pady=2)
        self.cbo_flow_surf.bind("<<ComboboxSelected>>", lambda e: self.on_psi_update())
        lbl_tag_psi_tbl = tk.Label(grp_surface, text="[Tra Bảng 3]", font=("Segoe UI", 8, "bold"), fg="#2563EB")
        lbl_tag_psi_tbl.grid(row=2, column=2, sticky="w", padx=4)

        # Hệ số Psi
        ttk.Label(grp_surface, text="Hệ số dòng chảy Ψ:").grid(row=3, column=0, sticky="w", pady=2)
        self.ent_psi = ttk.Entry(grp_surface, width=16)
        self.ent_psi.insert(0, "0.81")
        self.ent_psi.grid(row=3, column=1, sticky="w", pady=2)
        lbl_tag_psi = tk.Label(grp_surface, text="[Tự động từ Bảng 3]", font=("Segoe UI", 8), fg="#059669")
        lbl_tag_psi.grid(row=3, column=2, sticky="w", padx=4)

        # Mặt phủ Z
        ttk.Label(grp_surface, text="Mặt phủ (Z):").grid(row=4, column=0, sticky="w", pady=2)
        self.cbo_cover = ttk.Combobox(grp_surface, values=list(Z_TABLE.keys()), state="readonly", width=16)
        self.cbo_cover.set("Mái nhà mặt đường nhựa")
        self.cbo_cover.grid(row=4, column=1, sticky="ew", pady=2)
        lbl_tag_z = tk.Label(grp_surface, text="[Tra Bảng 5]", font=("Segoe UI", 8, "bold"), fg="#2563EB")
        lbl_tag_z.grid(row=4, column=2, sticky="w", padx=4)

        # Nhám mặt đường n
        ttk.Label(grp_surface, text="Nhám mặt đường (n):").grid(row=5, column=0, sticky="w", pady=2)
        self.cbo_nsurf = ttk.Combobox(grp_surface, values=list(N_SURFACE_TABLE.keys()), state="readonly", width=16)
        self.cbo_nsurf.set("Bê tông nhẵn")
        self.cbo_nsurf.grid(row=5, column=1, sticky="ew", pady=2)
        lbl_tag_n = tk.Label(grp_surface, text="[Tra Bảng 1.1]", font=("Segoe UI", 8, "bold"), fg="#2563EB")
        lbl_tag_n.grid(row=5, column=2, sticky="w", padx=4)

        # Độ dốc mặt sườn i
        ttk.Label(grp_surface, text="Độ dốc mặt sườn i:").grid(row=6, column=0, sticky="w", pady=2)
        self.ent_isurf = ttk.Entry(grp_surface, width=16)
        self.ent_isurf.insert(0, "0.02")
        self.ent_isurf.grid(row=6, column=1, sticky="w", pady=2)
        lbl_tag_isurf = tk.Label(grp_surface, text="[Nhập tay: đo thực tế]", font=("Segoe UI", 8, "bold"), fg="#EA580C")
        lbl_tag_isurf.grid(row=6, column=2, sticky="w", padx=4)

        # --- Nhóm 3: Thông số cống & Thủy lực ---
        grp_conduit = ttk.LabelFrame(self.scrollable_frame, text=" 3. Tuyến Cống & Thủy Lực Lòng Dẫn ", padding=8)
        grp_conduit.pack(fill=tk.X, pady=3, padx=4)

        # Hình dạng cống
        ttk.Label(grp_conduit, text="Hình dạng cống:").grid(row=0, column=0, sticky="w", pady=2)
        self.cbo_shape = ttk.Combobox(grp_conduit, values=["Cống hình chữ nhật", "Cống hình tròn"], state="readonly", width=16)
        self.cbo_shape.set("Cống hình chữ nhật")
        self.cbo_shape.grid(row=0, column=1, sticky="ew", pady=2)
        self.cbo_shape.bind("<<ComboboxSelected>>", lambda e: self.on_conduit_type_change())
        lbl_tag_shape = tk.Label(grp_conduit, text="[Thiết kế chọn]", font=("Segoe UI", 8, "bold"), fg="#7C3AED")
        lbl_tag_shape.grid(row=0, column=2, sticky="w", padx=4)

        # Loại công trình (m)
        ttk.Label(grp_conduit, text="Loại công trình (m):").grid(row=1, column=0, sticky="w", pady=2)
        self.cbo_struct = ttk.Combobox(grp_conduit, values=["Mương, máng (m=1.2)", "Cống ngầm (m=2.0)"], state="readonly", width=16)
        self.cbo_struct.set("Mương, máng (m=1.2)")
        self.cbo_struct.grid(row=1, column=1, sticky="ew", pady=2)
        lbl_tag_m = tk.Label(grp_conduit, text="[Tra Bảng m]", font=("Segoe UI", 8, "bold"), fg="#2563EB")
        lbl_tag_m.grid(row=1, column=2, sticky="w", padx=4)

        # Kích thước 1
        self.lbl_dim1 = ttk.Label(grp_conduit, text="Bề rộng B (m):")
        self.lbl_dim1.grid(row=2, column=0, sticky="w", pady=2)
        self.ent_dim1 = ttk.Entry(grp_conduit, width=16)
        self.ent_dim1.insert(0, "0.25")
        self.ent_dim1.grid(row=2, column=1, sticky="w", pady=2)
        self.lbl_tag_dim1 = tk.Label(grp_conduit, text="[Thiết kế chọn]", font=("Segoe UI", 8, "bold"), fg="#7C3AED")
        self.lbl_tag_dim1.grid(row=2, column=2, sticky="w", padx=4)

        # Kích thước 2
        self.lbl_dim2 = ttk.Label(grp_conduit, text="Chiều cao H (m):")
        self.lbl_dim2.grid(row=3, column=0, sticky="w", pady=2)
        self.ent_dim2 = ttk.Entry(grp_conduit, width=16)
        self.ent_dim2.insert(0, "0.10")
        self.ent_dim2.grid(row=3, column=1, sticky="w", pady=2)
        self.lbl_tag_dim2 = tk.Label(grp_conduit, text="[Thiết kế chọn]", font=("Segoe UI", 8, "bold"), fg="#7C3AED")
        self.lbl_tag_dim2.grid(row=3, column=2, sticky="w", padx=4)

        # Nhám thành cống n1
        ttk.Label(grp_conduit, text="Vật liệu cống (n1):").grid(row=4, column=0, sticky="w", pady=2)
        self.cbo_nconduit = ttk.Combobox(grp_conduit, values=list(N_CONDUIT_TABLE.keys()), state="readonly", width=16)
        self.cbo_nconduit.set("Bê tông nhẵn")
        self.cbo_nconduit.grid(row=4, column=1, sticky="ew", pady=2)
        lbl_tag_n1 = tk.Label(grp_conduit, text="[Tra Bảng 1.1 / 9]", font=("Segoe UI", 8, "bold"), fg="#2563EB")
        lbl_tag_n1.grid(row=4, column=2, sticky="w", padx=4)

        # Độ dốc cống i
        ttk.Label(grp_conduit, text="Độ dốc cống i:").grid(row=5, column=0, sticky="w", pady=2)
        self.ent_iconduit = ttk.Entry(grp_conduit, width=16)
        self.ent_iconduit.insert(0, "0.03")
        self.ent_iconduit.grid(row=5, column=1, sticky="w", pady=2)
        lbl_tag_iconduit = tk.Label(grp_conduit, text="[Thiết kế: theo trắc dọc]", font=("Segoe UI", 8, "bold"), fg="#7C3AED")
        lbl_tag_iconduit.grid(row=5, column=2, sticky="w", padx=4)

        # Khung nút bấm
        btn_frame = ttk.Frame(self.scrollable_frame)
        btn_frame.pack(fill=tk.X, pady=8, padx=4)

        btn_calc = tk.Button(
            btn_frame,
            text="▶ TÍNH TOÁN THỦY LỰC",
            command=self.calculate,
            bg="#059669",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief=tk.RAISED,
            padx=10,
            pady=5
        )
        btn_calc.pack(side=tk.LEFT, padx=3)

        btn_view_tab = tk.Button(
            btn_frame,
            text="📖 Mở Bảng Tra Cứu",
            command=self.switch_to_lookup_tab,
            bg="#2563EB",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=5
        )
        btn_view_tab.pack(side=tk.LEFT, padx=3)

        btn_reset = tk.Button(
            btn_frame,
            text="↺ Mặc định",
            command=self.reset_default,
            bg="#6B7280",
            fg="white",
            font=("Segoe UI", 9),
            padx=6,
            pady=5
        )
        btn_reset.pack(side=tk.LEFT, padx=3)

        # ---------------- KHUNG NOTEBOOK BÊN PHẢI (2 TABS) ----------------
        right_container = ttk.Frame(main_paned)
        main_paned.add(right_container, weight=2)

        self.notebook = ttk.Notebook(right_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # === TAB 1: THUYẾT MINH & KẾT QUẢ ===
        tab_result = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab_result, text=" 📊 Thuyết Minh & Nguồn Gốc Thông Số ")

        verdict_frame = tk.Frame(tab_result, bg="#F3F4F6", bd=1, relief=tk.SOLID, padx=10, pady=8)
        verdict_frame.pack(fill=tk.X, pady=(0, 6))

        self.lbl_verdict = tk.Label(
            verdict_frame,
            text="KẾT QUẢ: ĐANG TÍNH...",
            font=("Segoe UI", 12, "bold"),
            fg="#059669",
            bg="#F3F4F6"
        )
        self.lbl_verdict.pack(anchor="w")

        self.lbl_summary = tk.Label(
            verdict_frame,
            text="Lưu lượng Q: -- | Vận tốc V: -- | Tiết diện: --",
            font=("Segoe UI", 9),
            bg="#F3F4F6"
        )
        self.lbl_summary.pack(anchor="w", pady=(3, 0))

        grp_report = ttk.LabelFrame(tab_result, text=" Thuyết Minh Chi Tiết Có Chú Thích Nguồn Gốc Số Liệu ", padding=4)
        grp_report.pack(fill=tk.BOTH, expand=True)

        self.txt_report = tk.Text(grp_report, font=("Consolas", 10), wrap="none", padx=8, pady=8)
        txt_scroll_y = ttk.Scrollbar(grp_report, orient="vertical", command=self.txt_report.yview)
        txt_scroll_x = ttk.Scrollbar(grp_report, orient="horizontal", command=self.txt_report.xview)
        self.txt_report.configure(yscrollcommand=txt_scroll_y.set, xscrollcommand=txt_scroll_x.set)

        self.txt_report.grid(row=0, column=0, sticky="nsew")
        txt_scroll_y.grid(row=0, column=1, sticky="ns")
        txt_scroll_x.grid(row=1, column=0, sticky="ew")
        grp_report.rowconfigure(0, weight=1)
        grp_report.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(tab_result)
        toolbar.pack(fill=tk.X, pady=6)

        btn_export_excel = tk.Button(
            toolbar,
            text="📊 Xuất Excel Kèm Cột Nguồn Gốc (.xlsx)",
            command=self.export_excel,
            bg="#107C41",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4
        )
        btn_export_excel.pack(side=tk.LEFT, padx=3)

        btn_export_txt = tk.Button(
            toolbar,
            text="📄 Xuất Thuyết Minh (.txt)",
            command=self.export_txt,
            bg="#374151",
            fg="white",
            font=("Segoe UI", 9),
            padx=8,
            pady=4
        )
        btn_export_txt.pack(side=tk.LEFT, padx=3)

        btn_copy = tk.Button(
            toolbar,
            text="📋 Sao Chép Kết Quả",
            command=self.copy_to_clipboard,
            font=("Segoe UI", 9),
            padx=8,
            pady=4
        )
        btn_copy.pack(side=tk.LEFT, padx=3)

        # === TAB 2: TRA CỨU CÁC BẢNG TIÊU CHUẨN ===
        tab_lookup = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab_lookup, text=" 📚 Tra Cứu Bảng Tiêu Chuẩn TCVN 7957:2023 ")

        top_lookup_bar = ttk.Frame(tab_lookup)
        top_lookup_bar.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(top_lookup_bar, text="Chọn bảng tra:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.cbo_table_select = ttk.Combobox(
            top_lookup_bar,
            values=list(LOOKUP_DATABASE.keys()),
            state="readonly",
            width=42,
            font=("Segoe UI", 9)
        )
        self.cbo_table_select.set(list(LOOKUP_DATABASE.keys())[0])
        self.cbo_table_select.pack(side=tk.LEFT, padx=(0, 10))
        self.cbo_table_select.bind("<<ComboboxSelected>>", lambda e: self.load_table_view())

        ttk.Label(top_lookup_bar, text="🔍 Tìm kiếm:").pack(side=tk.LEFT, padx=(5, 3))
        self.ent_search = ttk.Entry(top_lookup_bar, width=18)
        self.ent_search.pack(side=tk.LEFT, padx=(0, 8))
        self.ent_search.bind("<KeyRelease>", lambda e: self.filter_table_view())

        btn_apply_table = tk.Button(
            top_lookup_bar,
            text="⚡ Áp dụng vào tính toán",
            command=self.apply_selected_row,
            bg="#D97706",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3
        )
        btn_apply_table.pack(side=tk.RIGHT, padx=3)

        tree_frame = ttk.Frame(tab_lookup)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, selectmode="browse")
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.tag_configure("oddrow", background="#F9FAFB")
        self.tree.tag_configure("evenrow", background="#FFFFFF")

        self.lbl_table_note = tk.Label(
            tab_lookup,
            text="",
            font=("Segoe UI", 9, "italic"),
            fg="#4B5563",
            anchor="w",
            justify=tk.LEFT,
            pady=4
        )
        self.lbl_table_note.pack(fill=tk.X)

    def switch_to_lookup_tab(self):
        self.notebook.select(1)

    def load_table_view(self):
        table_name = self.cbo_table_select.get()
        if table_name not in LOOKUP_DATABASE:
            return
        tbl_info = LOOKUP_DATABASE[table_name]

        self.tree.delete(*self.tree.get_children())
        cols = tbl_info["columns"]
        self.tree["columns"] = cols
        self.tree["show"] = "headings"

        for idx, col_name in enumerate(cols):
            w = tbl_info["widths"][idx] if idx < len(tbl_info["widths"]) else 120
            align = tbl_info["aligns"][idx] if idx < len(tbl_info["aligns"]) else "center"
            anchor = tk.CENTER if align == "center" else (tk.W if align == "w" else tk.E)
            self.tree.heading(col_name, text=col_name, anchor=anchor)
            self.tree.column(col_name, width=w, minwidth=60, anchor=anchor)

        self.ent_search.delete(0, tk.END)
        self.current_filtered_rows = tbl_info["rows"]
        self.render_table_rows(self.current_filtered_rows)
        self.lbl_table_note.config(text=f"📌 Ghi chú: {tbl_info['note']}")

    def render_table_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for idx, r in enumerate(rows):
            tag = "evenrow" if idx % 2 == 0 else "oddrow"
            self.tree.insert("", tk.END, values=r, tags=(tag,))

    def filter_table_view(self):
        keyword = self.ent_search.get().strip().lower()
        table_name = self.cbo_table_select.get()
        all_rows = LOOKUP_DATABASE[table_name]["rows"]

        if not keyword:
            self.render_table_rows(all_rows)
            return

        filtered = [
            r for r in all_rows if any(keyword in str(cell).lower() for cell in r)
        ]
        self.render_table_rows(filtered)

    def apply_selected_row(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Hướng dẫn", "Vui lòng bấm chọn một dòng trong bảng trước khi nhấn 'Áp dụng'!")
            return

        row_vals = self.tree.item(selected[0], "values")
        tbl_name = self.cbo_table_select.get()
        tbl_type = LOOKUP_DATABASE[tbl_name]["type"]

        if tbl_type == "A1":
            city_name = row_vals[1]
            if city_name in STATIONS_DATA:
                self.cbo_city.set(city_name)
                self.on_city_change()
                self.calculate()
                messagebox.showinfo("Thành công", f"Đã áp dụng trạm đo mưa: {city_name} (A={row_vals[2]}, C={row_vals[3]}, b={row_vals[4]}, n={row_vals[5]})")

        elif tbl_type == "PSI":
            surf_name = row_vals[0]
            if surf_name in PSI_TABLE:
                self.cbo_flow_surf.set(surf_name)
                self.on_psi_update()
                self.calculate()
                messagebox.showinfo("Thành công", f"Đã áp dụng loại mặt phủ: {surf_name}")

        elif tbl_type == "Z_COEF":
            cover_name = row_vals[0]
            if cover_name in Z_TABLE:
                self.cbo_cover.set(cover_name)
                self.calculate()
                messagebox.showinfo("Thành công", f"Đã áp dụng mặt phủ Z: {cover_name} (Z = {row_vals[1]})")

        elif tbl_type == "ROUGHNESS":
            mat_name = row_vals[0]
            app_type = row_vals[1]
            if "Mặt đường" in app_type and mat_name in N_SURFACE_TABLE:
                self.cbo_nsurf.set(mat_name)
                self.calculate()
                messagebox.showinfo("Thành công", f"Đã áp dụng nhám mặt đường: {mat_name}")
            elif "Thành cống" in app_type and mat_name in N_CONDUIT_TABLE:
                self.cbo_nconduit.set(mat_name)
                self.calculate()
                messagebox.showinfo("Thành công", f"Đã áp dụng nhám thành cống mương: {mat_name}")
            else:
                messagebox.showinfo("Thông báo", f"Đã xem giá trị: {mat_name} = {row_vals[2]}")

        else:
            messagebox.showinfo("Thông báo", f"Giá trị lựa chọn: {row_vals[0]} - {row_vals[1]}")

    def on_city_change(self):
        city = self.cbo_city.get()
        if city in STATIONS_DATA:
            data = STATIONS_DATA[city]
            self.ent_A.delete(0, tk.END)
            self.ent_A.insert(0, str(data["A"]))
            self.ent_C.delete(0, tk.END)
            self.ent_C.insert(0, str(data["C"]))
            self.ent_b.delete(0, tk.END)
            self.ent_b.insert(0, str(data["b"]))
            self.ent_n.delete(0, tk.END)
            self.ent_n.insert(0, str(data["n"]))

    def on_psi_update(self):
        surf = self.cbo_flow_surf.get()
        try:
            P_val = int(self.cbo_P.get())
        except ValueError:
            P_val = 10
        if surf in PSI_TABLE and P_val in PSI_TABLE[surf]:
            psi_val = PSI_TABLE[surf][P_val]
            self.ent_psi.delete(0, tk.END)
            self.ent_psi.insert(0, f"{psi_val:.2f}")

    def on_conduit_type_change(self):
        shape = self.cbo_shape.get()
        if shape == "Cống hình chữ nhật":
            self.lbl_dim1.config(text="Bề rộng B (m):")
            self.lbl_dim2.grid(row=3, column=0, sticky="w", pady=2)
            self.ent_dim2.grid(row=3, column=1, sticky="w", pady=2)
            self.lbl_tag_dim2.grid(row=3, column=2, sticky="w", padx=4)
            self.ent_dim1.delete(0, tk.END)
            self.ent_dim1.insert(0, "0.25")
            self.ent_dim2.delete(0, tk.END)
            self.ent_dim2.insert(0, "0.10")
            self.ent_iconduit.delete(0, tk.END)
            self.ent_iconduit.insert(0, "0.03")
        else:
            self.lbl_dim1.config(text="Đường kính D (m):")
            self.lbl_dim2.grid_remove()
            self.ent_dim2.grid_remove()
            self.lbl_tag_dim2.grid_remove()
            self.ent_dim1.delete(0, tk.END)
            self.ent_dim1.insert(0, "0.60")
            self.ent_iconduit.delete(0, tk.END)
            self.ent_iconduit.insert(0, "0.002")

    def reset_default(self):
        self.cbo_city.set("Hồ Chí Minh")
        self.on_city_change()
        self.cbo_P.set("10")
        self.on_psi_update()
        self.ent_Lx.delete(0, tk.END)
        self.ent_Lx.insert(0, "44.07")
        self.ent_Lsurf.delete(0, tk.END)
        self.ent_Lsurf.insert(0, "16.25")
        self.cbo_shape.set("Cống hình chữ nhật")
        self.on_conduit_type_change()
        self.calculate()

    def calculate(self):
        try:
            inputs = {
                "city": self.cbo_city.get(),
                "A": float(self.ent_A.get()),
                "C": float(self.ent_C.get()),
                "b": float(self.ent_b.get()),
                "n_clim": float(self.ent_n.get()),
                "P": float(self.cbo_P.get()),
                "K_climate": float(self.ent_K.get()),
                "Lx": float(self.ent_Lx.get()),
                "L_surf": float(self.ent_Lsurf.get()),
                "psi": float(self.ent_psi.get()),
                "Z": Z_TABLE.get(self.cbo_cover.get(), 0.24),
                "n_surf": N_SURFACE_TABLE.get(self.cbo_nsurf.get(), 0.014),
                "i_surf": float(self.ent_isurf.get()),
                "I_rain": 2.5,
                "conduit_shape": self.cbo_shape.get(),
                "m_coef": 2.0 if "Cống ngầm" in self.cbo_struct.get() else 1.2,
                "n1": N_CONDUIT_TABLE.get(self.cbo_nconduit.get(), 0.014),
                "i_conduit": float(self.ent_iconduit.get()),
                "t2": 0.0,
            }

            if inputs["conduit_shape"] == "Cống hình chữ nhật":
                inputs["B"] = float(self.ent_dim1.get())
                inputs["H"] = float(self.ent_dim2.get())
            else:
                inputs["D"] = float(self.ent_dim1.get())

            res = DrainageCalculator.calculate_all(inputs)
            self.last_results = (inputs, res)

            if res["is_safe"]:
                self.lbl_verdict.config(
                    text=f"✓ ĐẢM BẢO KHẢ NĂNG THOÁT NƯỚC  (ω = {res['omega']:.4f} m²  ≥  [ω] = {res['omega_req']:.4f} m²)",
                    fg="#059669"
                )
            else:
                self.lbl_verdict.config(
                    text=f"✗ KHÔNG ĐẢM BẢO - CẦN TĂNG TIẾT DIỆN (ω = {res['omega']:.4f} m²  <  [ω] = {res['omega_req']:.4f} m²)",
                    fg="#DC2626"
                )

            self.lbl_summary.config(
                text=f"Lưu lượng Q: {res['Q_ls']:.2f} L/s ({res['Q_m3s']:.4f} m³/s) | "
                     f"Vận tốc V: {res['V_conduit']:.2f} m/s | Cường độ q: {res['q']:.1f} L/s.ha"
            )

            self.generate_report_text(inputs, res)

        except Exception as e:
            err_msg = "Vui lòng kiểm tra lại thông số nhập vào:\n" + str(e)
            messagebox.showerror("Lỗi số liệu", err_msg)

    def generate_report_text(self, inp, r):
        shape_txt = inp["conduit_shape"]
        t = []
        t.append("=" * 86)
        t.append("      TÍNH TOÁN THỦY LỰC CÔNG TRÌNH THOÁT NƯỚC MƯA THEO TCVN 7957:2023")
        t.append("         (KÈM BẢNG CHÚ THÍCH NGUỒN GỐC XÁC ĐỊNH CHO TỪNG THÔNG SỐ)")
        t.append("=" * 86)
        t.append("1. CÁC SỐ LIỆU ĐIỀU TRA ĐO ĐẠC & KHẢO SÁT:")
        t.append(f" - Địa điểm công trình        : {inp['city']:<18} --> [Nguồn: Tra Bảng A.1]")
        t.append(f" - Chu kỳ lặp lại P           : {inp['P']:.0f} năm{'':<14} --> [Nguồn: Tra Bảng 1 & 2 - Cấp đô thị/KCN]")
        t.append(f" - Hệ số BĐKH K               : {inp['K_climate']:.2f}{'':<16} --> [Nguồn: Nhập tay - Kịch bản BĐKH vùng]")
        t.append(f" - Chiều dài đoạn tuyến Lx     : {inp['Lx']:.2f} m{'':<15} --> [Nguồn: Nhập tay - Đo từ bình đồ thoát nước]")
        t.append(f" - Chiều dài dòng chảy mặt L  : {inp['L_surf']:.2f} m{'':<15} --> [Nguồn: Nhập tay - Phạm vi thu nước sườn]")
        t.append(f" - Diện tích lưu vực Ftt       : {r['Ftt']:.6f} ha{'':<11} --> [Nguồn: Tự động tính Ftt = Lx * L / 10000]")
        t.append("")
        t.append("2. THÔNG SỐ KHÍ TƯỢNG VÀ DÒNG CHẢY MẶT (t0):")
        t.append(f" - Hằng số trạm mưa A, C, b, n: A={inp['A']}, C={inp['C']}, b={inp['b']}, n={inp['n_clim']} --> [Nguồn: Tự động tra từ Bảng A.1]")
        t.append(f" - Hệ số mặt phủ Z            : {inp['Z']:.3f}{'':<15} --> [Nguồn: Tra Bảng 5 - Theo loại mặt phủ]")
        t.append(f" - Hệ số nhám mặt đường n     : {inp['n_surf']:.3f}{'':<15} --> [Nguồn: Tra Bảng 1.1 - Vật liệu phủ đường]")
        t.append(f" - Độ dốc mặt sườn i          : {inp['i_surf']:.3f}{'':<15} --> [Nguồn: Nhập tay - Đo từ cao độ tự nhiên]")
        t.append(f" - Cường độ mưa giả định I    : 2.50 mm/phút (150/60) --> [Nguồn: Quy định tính t0 trong TCVN]")
        t.append(f" -> Thời gian chảy mặt t0     : {r['t0']:.4f} phút{'':<13} --> [Nguồn: Công thức kinh nghiệm TCVN]")
        t.append("")
        t.append("3. THỦY LỰC KẾT CẤU CỐNG VÀ THỜI GIAN CHẢY TRONG RÃNH / MƯƠNG (tr):")
        t.append(f" - Dạng kết cấu cống          : {shape_txt:<18} --> [Nguồn: Kỹ sư thiết kế lựa chọn]")
        t.append(f" - Kích thước lựa chọn        : {r['dim_str']:<18} --> [Nguồn: Kỹ sư thiết kế chọn giả định]")
        t.append(f" - Loại công trình (hệ số m)  : {inp['m_coef']:.1f}{'':<17} --> [Nguồn: Tra Bảng m - Mương:1.2, Cống:2.0]")
        t.append(f" - Độ dốc đặt cống i          : {inp['i_conduit']:.4f}{'':<14} --> [Nguồn: Kỹ sư thiết kế theo trắc dọc]")
        t.append(f" - Hệ số nhám cống n1         : {inp['n1']:.3f}{'':<15} --> [Nguồn: Tra Bảng 1.1 & 9 - Vật liệu cống]")
        t.append(f" - Bán kính thủy lực R        : {r['R']:.4f} m{'':<15} --> [Nguồn: R = omega / chi]")
        t.append(f" - Hệ số Pavlovskii y         : {r['y_pavlov']:.4f}{'':<14} --> [Nguồn: Công thức Pavlovskii N.N.]")
        t.append(f" - Hệ số Chezy C              : {r['C_chezy']:.4f}{'':<14} --> [Nguồn: C = R^y / n1]")
        t.append(f" -> Vận tốc dòng chảy V       : {r['V_conduit']:.4f} m/s{'':<13} --> [Nguồn: V = C * sqrt(R * i)]")
        t.append(f" -> Thời gian chảy rãnh tr    : {r['tr']:.4f} phút{'':<13} --> [Nguồn: tr = 0.021 * Lx / V]")
        t.append(f" -> Tổng thời gian mưa t      : {r['t_total']:.4f} phút{'':<13} --> [Nguồn: t = t0 + tr + m*t2]")
        t.append("")
        t.append("4. LƯU LƯỢNG MƯA TÍNH TOÁN (Q):")
        t.append(f" - Cường độ mưa tính toán q   : {r['q']:.2f} L/(s.ha) [{r['q_mm']:.3f} mm/p] --> [Nguồn: Công thức cường độ giới hạn]")
        t.append(f" - Hệ số dòng chảy Psi        : {r['psi']:.2f}{'':<16} --> [Nguồn: Tra Bảng 3 theo chu kỳ P]")
        t.append(f" - Hệ số phân bố mưa Beta     : {r['beta']:.2f}{'':<16} --> [Nguồn: Tra Bảng 4 theo Ftt < 500ha]")
        t.append(f" - Hệ số phân bố mưa rào m    : {r['m_rain']:.2f}{'':<16} --> [Nguồn: Tra Bảng A.2 do Ftt < 300ha]")
        t.append(f" -> Lưu lượng tính toán Q     : {r['Q_ls']:.2f} L/s ({r['Q_m3s']:.6f} m3/s) --> [Nguồn: Q = q * F * beta * psi * m]")
        t.append("")
        t.append("5. KIỂM TRA ĐIỀU KIỆN THỦY LỰC & QUY CHUẨN:")
        t.append(f" - Diện tích ướt thiết kế     : omega = {r['omega']:.4f} m2")
        t.append(f" - Diện tích mặt cắt yêu cầu  : [omega] = {r['omega_req']:.4f} m2  ([omega] = Q / V)")
        status_txt = "ĐẢM BẢO KHẢ NĂNG THOÁT NƯỚC" if r['is_safe'] else "KHÔNG ĐẢM BẢO - CẦN TĂNG KÍCH THƯỚC HOẶC ĐỘ DỐC"
        t.append(f" - So sánh: omega ({r['omega']:.4f} m2) {'≥' if r['is_safe'] else '<'} [omega] ({r['omega_req']:.4f} m2) -> {status_txt}")
        if r['V_conduit'] < 0.7:
            t.append(" - Cảnh báo: Vận tốc V < 0.7 m/s (dễ xảy ra bồi lắng bùn cặn).")
        elif r['V_conduit'] > 4.0:
            t.append(" - Cảnh báo: Vận tốc V > 4.0 m/s (nguy cơ gây xói lở thành cống bê tông).")
        else:
            t.append(" - Vận tốc dòng chảy đạt điều kiện tự làm sạch và an toàn: 0.7 <= V <= 4.0 m/s.")
        t.append("=" * 86)

        full_content = "\n".join(t)
        self.txt_report.delete("1.0", tk.END)
        self.txt_report.insert(tk.END, full_content)

    def copy_to_clipboard(self):
        text = self.txt_report.get("1.0", tk.END)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Thành công", "Đã sao chép thuyết minh vào Clipboard!")

    def export_txt(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All Files", "*.*")],
            title="Lưu file Thuyết minh tính toán"
        )
        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.txt_report.get("1.0", tk.END))
            messagebox.showinfo("Thành công", f"Đã lưu thuyết minh thành công tại:\n{filename}")

    def export_excel(self):
        if not self.last_results:
            messagebox.showwarning("Thông báo", "Vui lòng bấm 'Tính toán' trước khi xuất file!")
            return

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            msg = "Chưa cài thư viện openpyxl. Mở CMD gõ: pip install openpyxl\nHiện bạn vẫn có thể xuất ra file Text (.txt) đầy đủ!"
            messagebox.showwarning("Thiếu thư viện", msg)
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx")],
            title="Lưu kết quả tính toán thủy lực Excel"
        )
        if not filename:
            return

        inp, r = self.last_results
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "ThuyetMinhThoatNuoc"

        ws.merge_cells("A1:E1")
        ws["A1"] = "BẢNG TÍNH TOÁN THỦY LỰC CÔNG TRÌNH THOÁT NƯỚC MƯA (TCVN 7957:2023)"
        ws["A1"].font = Font(name="Segoe UI", size=13, bold=True, color="1E3A8A")
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells("A2:E2")
        ws["A2"] = "Kèm bảng chú thích nguồn gốc xác định thông số (Tra bảng tiêu chuẩn / Khảo sát thiết kế)"
        ws["A2"].font = Font(name="Segoe UI", size=10, italic=True)
        ws["A2"].alignment = Alignment(horizontal="center")

        headers_cols = ["STT", "Tên thông số kỹ thuật", "Giá trị tính toán", "Đơn vị", "Nguồn gốc xác định thông số"]
        for col_i, h_name in enumerate(headers_cols, 1):
            cell = ws.cell(row=4, column=col_i, value=h_name)
            cell.font = Font(name="Segoe UI", bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")

        records = [
            ("Địa điểm công trình / Trạm mưa", inp["city"], "-", "Tra Bảng A.1 (49 Trạm mưa TCVN)"),
            ("Chu kỳ lặp lại trận mưa P", inp["P"], "năm", "Tra Bảng 1 & 2 (Theo cấp đô thị/KCN)"),
            ("Hệ số biến đổi khí hậu K", inp["K_climate"], "-", "Nhập tay: Kịch bản BĐKH địa phương (≥1.0)"),
            ("Chiều dài đoạn tuyến cống Lx", inp["Lx"], "m", "Nhập tay: Đo từ bình đồ thoát nước"),
            ("Chiều rộng thu nước bề mặt L", inp["L_surf"], "m", "Nhập tay: Khảo sát phạm vi lưu vực"),
            ("Diện tích lưu vực tính toán Ftt", round(r["Ftt"], 6), "ha", "Tự động tính: Ftt = Lx * L / 10000"),
            ("Hằng số khí hậu A", inp["A"], "-", "Tự động tra từ Bảng A.1"),
            ("Hằng số khí hậu C", inp["C"], "-", "Tự động tra từ Bảng A.1"),
            ("Hằng số khí hậu b", inp["b"], "-", "Tự động tra từ Bảng A.1"),
            ("Hằng số khí hậu n", inp["n_clim"], "-", "Tự động tra từ Bảng A.1"),
            ("Hệ số mặt phủ Z", inp["Z"], "-", "Tra Bảng 5 (Theo loại mặt phủ)"),
            ("Hệ số nhám mặt đường n", inp["n_surf"], "-", "Tra Bảng 1.1 (Theo vật liệu làm đường)"),
            ("Độ dốc bề mặt sườn dốc i", inp["i_surf"], "-", "Nhập tay: Đo cao độ địa hình tự nhiên"),
            ("Thời gian nước chảy mặt t0", round(r["t0"], 4), "phút", "Tính theo công thức kinh nghiệm TCVN"),
            ("Vận tốc dòng chảy trong cống V", round(r["V_conduit"], 4), "m/s", "Tính theo công thức Pavlovskii / Chezy"),
            ("Thời gian nước chảy trong rãnh tr", round(r["tr"], 4), "phút", "Tính theo công thức: tr = 0.021 * Lx / V"),
            ("Hệ số giảm vận tốc m", inp["m_coef"], "-", "Tra Bảng m (Mương: 1.2, Cống ngầm: 2.0)"),
            ("Tổng thời gian mưa tính toán t", round(r["t_total"], 4), "phút", "Tính theo công thức: t = t0 + tr + m*t2"),
            ("Cường độ mưa tính toán q", round(r["q"], 2), "L/(s.ha)", "Phương pháp cường độ giới hạn"),
            ("Hệ số dòng chảy Psi (Ψ)", inp["psi"], "-", "Tra Bảng 3 (Phụ thuộc P và mặt phủ)"),
            ("Hệ số phân bổ mưa Beta (β)", r["beta"], "-", "Tra Bảng 4 (Phụ thuộc diện tích Ftt)"),
            ("Hệ số phân bố mưa rào m", r["m_rain"], "-", "Tra Bảng A.2 (Xét khi Ftt > 300ha)"),
            ("Lưu lượng tính toán Q (L/s)", round(r["Q_ls"], 2), "L/s", "Q = q * Ftt * β * Ψ * m_rào"),
            ("Lưu lượng tính toán Q (m3/s)", round(r["Q_m3s"], 6), "m³/s", "Q (m³/s) = Q (L/s) / 1000"),
            ("Loại cống / mương thiết kế", inp["conduit_shape"], "-", "Kỹ sư thiết kế lựa chọn"),
            ("Kích thước công trình lựa chọn", r["dim_str"], "-", "Kỹ sư thiết kế chọn giả định"),
            ("Độ dốc đáy cống thiết kế i", inp["i_conduit"], "-", "Kỹ sư thiết kế chọn theo trắc dọc"),
            ("Hệ số nhám thành cống n1", inp["n1"], "-", "Tra Bảng 1.1 & Bảng 9 (Vật liệu thành)"),
            ("Diện tích ướt cống lựa chọn ω", round(r["omega"], 4), "m²", "Diện tích cống thiết kế giả định"),
            ("Diện tích mặt cắt yêu cầu [ω]", round(r["omega_req"], 4), "m²", "Tính toán: [ω] = Q / V"),
            ("KẾT LUẬN KIỂM TRA THỦY LỰC", "ĐẢM BẢO" if r["is_safe"] else "CẦN THỬ LẠI", "-", "So sánh điều kiện: ω ≥ [ω]")
        ]

        thin_border = Border(
            left=Side(style='thin', color='D1D5DB'),
            right=Side(style='thin', color='D1D5DB'),
            top=Side(style='thin', color='D1D5DB'),
            bottom=Side(style='thin', color='D1D5DB')
        )

        for row_idx, (p_name, p_val, p_unit, p_src) in enumerate(records, 5):
            ws.cell(row=row_idx, column=1, value=row_idx - 4).alignment = Alignment(horizontal="center")
            ws.cell(row=row_idx, column=2, value=p_name).font = Font(name="Segoe UI", bold=("KẾT LUẬN" in p_name))
            val_cell = ws.cell(row=row_idx, column=3, value=p_val)
            val_cell.alignment = Alignment(horizontal="right")
            val_cell.font = Font(name="Segoe UI", bold=("KẾT LUẬN" in p_name))
            ws.cell(row=row_idx, column=4, value=p_unit).alignment = Alignment(horizontal="center")
            src_cell = ws.cell(row=row_idx, column=5, value=p_src)

            if "KẾT LUẬN" in p_name:
                color = "C6F6D5" if r["is_safe"] else "FED7D7"
                val_cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            elif "Tra Bảng" in p_src or "Tự động tra" in p_src:
                src_cell.font = Font(name="Segoe UI", color="1E40AF", italic=True)
            elif "Nhập tay" in p_src or "Kỹ sư" in p_src:
                src_cell.font = Font(name="Segoe UI", color="C2410C", bold=True)

            for col in range(1, 6):
                ws.cell(row=row_idx, column=col).border = thin_border

        ws.column_dimensions['A'].width = 6
        ws.column_dimensions['B'].width = 36
        ws.column_dimensions['C'].width = 18
        ws.column_dimensions['D'].width = 10
        ws.column_dimensions['E'].width = 42

        wb.save(filename)
        messagebox.showinfo("Thành công", f"Đã xuất file Excel thành công tại:\n{filename}")


if __name__ == "__main__":
    app = DrainageApp()
    app.mainloop()