import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import json
import numpy as np
import pandas as pd
from scipy.stats import norm, skew, pearson3

# Thư viện xuất định dạng Excel nâng cao
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Cấu hình Matplotlib hỗ trợ vẽ đồ thị chuẩn giấy xác suất thủy văn
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# =============================================================================
# CƠ SỞ DỮ LIỆU ĐẦY ĐỦ 8 BẢNG TRA CHUẨN SOKOLOVSKY
# =============================================================================

# 1. Bảng 2-10: Tra alpha và Ho theo phân vùng lưu vực
BANG_2_10 = {
    1: {"name": "Lưu vực sông Nậm Rốn và thượng nguồn sông Mã", "alpha": 0.65, "Ho": 20},
    2: {"name": "Lưu vực sông Đà, sông Thao", "alpha": 0.81, "Ho": 22},
    3: {"name": "Các Lưu vực thượng nguồn sông Lô, sông Chảy", "alpha": 0.82, "Ho": 20},
    4: {"name": "Sông Gâm, hạ Lưu sông Lô, sông Phó Đáy", "alpha": 0.66, "Ho": 26},
    5: {"name": "Lưu vực sông Cầu, sông Thương, sông Trung, sông Bằng Giang", "alpha": 0.77, "Ho": 22},
    6: {"name": "Lưu vực sông Kỳ Cùng, sông Lục Nam", "alpha": 0.86, "Ho": 19},
    7: {"name": "Lưu vực các sông Quảng Ninh", "alpha": 0.89, "Ho": 15},
    8: {"name": "Lưu vực các sông từ sông Chu - sông Hương", "alpha": 0.92, "Ho": 21},
    9: {"name": "Lưu vực các sông từ Thu Bồn - sông Cái", "alpha": 0.86, "Ho": 16},
    10: {"name": "Lưu vực các sông Sê San và sông Srêpốk", "alpha": 0.76, "Ho": 21},
    11: {"name": "Lưu vực các sông Đồng Nai, sông Bé", "alpha": 0.64, "Ho": 25}
}

# 2. Bảng C.13: Tra hệ số hình dạng lũ f
BANG_C13 = {
    "I": {"name": "Các lưu vực sông nhỏ tỉnh Quảng Ninh", "f_range": "1.2 - 1.5", "f_def": 1.35},
    "II": {"name": "Lưu vực sông Thái Bình", "f_range": "0.6 - 0.8", "f_def": 0.70},
    "III": {"name": "Lưu vực sông Bằng Giang - Kỳ Cùng, sông Gâm", "f_range": "0.6 - 0.8", "f_def": 0.70},
    "IV": {"name": "Lưu vực sông Lô - Chảy", "f_range": "0.7 - 0.9", "f_def": 0.80},
    "V": {"name": "Lưu vực sông Thao, sông Đà", "f_range": "0.7 - 0.9", "f_def": 0.80},
    "VI": {"name": "Thượng nguồn sông Mã, thượng nguồn sông Mê Kông", "f_range": "0.6 - 0.7", "f_def": 0.65},
    "VII": {"name": "Trung & hạ lưu sông Mã + Lưu vực sông Cả", "f_range": "0.6 - 0.8", "f_def": 0.70},
    "VIII": {"name": "Các lưu vực sông nhỏ tỉnh Quảng Bình", "f_range": "0.8 - 1.2", "f_def": 1.00},
    "IX": {"name": "Từ Quảng Trị đến Quảng Ngãi", "f_range": "0.5 - 0.7", "f_def": 0.60},
    "X": {"name": "Khu vực Bắc Tây Nguyên", "f_range": "1.3 - 1.5", "f_def": 1.40},
    "XI": {"name": "Từ Bình Định đến Bình Thuận & Nam Tây Nguyên", "f_range": "0.5 - 0.9", "f_def": 0.70},
    "XII": {"name": "Lưu vực sông Đồng Nai + ĐBSCL", "f_range": "0.5 - 0.7", "f_def": 0.60}
}

# 3. Tọa độ đường cong mưa rào psi(T) của 18 vùng mưa Việt Nam
TIME_STEPS = [10, 15, 20, 30, 45, 60, 90, 120, 240, 480, 540, 720, 1080, 1440]
RAINFALL_CURVE_COORDS = {
    1: [0.180, 0.220, 0.260, 0.340, 0.430, 0.490, 0.610, 0.660, 0.800, 0.940, 0.950, 0.960, 0.980, 1.070],
    2: [0.130, 0.180, 0.220, 0.250, 0.330, 0.350, 0.400, 0.440, 0.580, 0.770, 0.790, 0.880, 0.900, 1.090],
    3: [0.070, 0.090, 0.120, 0.140, 0.200, 0.220, 0.270, 0.300, 0.440, 0.630, 0.680, 0.780, 0.830, 1.070],
    4: [0.150, 0.210, 0.240, 0.320, 0.380, 0.470, 0.550, 0.600, 0.920, 0.820, 0.830, 0.880, 0.930, 1.060],
    5: [0.101, 0.120, 0.150, 0.226, 0.300, 0.378, 0.460, 0.537, 0.700, 0.924, 0.935, 0.952, 0.985, 1.055],
    6: [0.120, 0.140, 0.180, 0.260, 0.300, 0.380, 0.470, 0.590, 0.780, 0.920, 0.950, 0.990, 1.030, 1.200],
    7: [0.098, 0.110, 0.176, 0.214, 0.240, 0.322, 0.419, 0.508, 0.682, 0.857, 0.890, 0.912, 0.950, 1.110],
    8: [0.125, 0.160, 0.200, 0.268, 0.320, 0.408, 0.504, 0.594, 0.734, 0.890, 0.920, 0.994, 1.040, 1.160],
    9: [0.100, 0.120, 0.150, 0.220, 0.250, 0.320, 0.390, 0.460, 0.590, 0.810, 0.830, 0.890, 0.930, 1.050],
    10: [0.080, 0.110, 0.130, 0.190, 0.230, 0.300, 0.380, 0.460, 0.640, 0.820, 0.835, 0.900, 0.965, 1.160],
    11: [0.060, 0.080, 0.102, 0.130, 0.170, 0.187, 0.260, 0.305, 0.415, 0.617, 0.670, 0.827, 0.935, 1.040],
    12: [0.078, 0.102, 0.118, 0.115, 0.205, 0.240, 0.303, 0.335, 0.500, 0.660, 0.710, 0.825, 1.060, 1.095],
    13: [0.098, 0.280, 0.145, 0.795, 0.245, 0.302, 0.380, 0.440, 0.630, 0.770, 0.830, 0.870, 0.970, 1.090],
    14: [0.160, 0.232, 0.295, 0.360, 0.420, 0.590, 0.665, 0.680, 0.790, 0.890, 0.960, 0.940, 0.965, 1.005],
    15: [0.255, 0.310, 0.463, 0.510, 0.540, 0.570, 0.610, 0.690, 0.766, 0.820, 0.840, 0.905, 0.960, 1.020],
    16: [0.230, 0.320, 0.417, 0.530, 0.700, 0.780, 0.830, 0.850, 0.870, 0.950, 0.965, 0.980, 0.990, 1.030],
    17: [0.205, 0.220, 0.250, 0.330, 0.380, 0.480, 0.580, 0.660, 0.730, 0.890, 0.910, 1.035, 1.045, 1.050],
    18: [0.190, 0.285, 0.330, 0.430, 0.520, 0.610, 0.715, 0.935, 0.780, 0.880, 0.900, 0.980, 1.030, 1.150]
}

# 4. Bảng tra hệ số km theo vùng khí hậu
BANG_KM = {
    "Đông Bắc": 0.55,
    "Tây Bắc": 0.60,
    "Bắc Trung Bộ": 0.55,
    "Nam Trung Bộ": 0.60,
    "Tây Nguyên": 0.70,
    "Nam Bộ": 0.80
}

# 5. Bảng tra vận tốc lớn nhất trên sườn dốc Vmax
BANG_VMAX = {
    "Đồng bằng rất bằng phẳng": 0.5,
    "Đồng bằng": 1.0,
    "Trung du thấp": 1.5,
    "Đồi núi thấp": 2.0,
    "Núi trung bình": 2.5,
    "Núi cao, dốc lớn": 3.0,
    "Núi rất dốc": 4.0
}

# 6. Bảng tra hệ số truyền lũ lòng sông kv (22TCN 220)
BANG_KV = {
    "Sông quanh co nhiều, lòng dẫn kém phát triển": 0.50,
    "Phát triển trung bình": 0.55,
    "Phát triển khá": 0.60,
    "Phát triển tốt": 0.65,
    "Phát triển rất tốt, lòng dẫn rõ ràng": 0.70
}

# 7. Bảng hệ số nhám lòng sông thiên nhiên
BANG_NHAM_SONG = [
    (1, "Sông bờ nhẵn nhụi, dòng thẳng không trở ngại, nước chảy dễ dàng", 40.0, 0.025, 1.20),
    (2, "Sông vùng đồng bằng luôn có nước, lòng sông và nước chảy đặc biệt tốt", 30.0, 0.035, 2.00),
    (3, "Sông đồng bằng nước tương đối sạch, đáy có bãi nổi, hố xói, đá lác đác", 25.0, 0.040, 2.75),
    (4, "Sông quanh co, có nhiều trở ngại cục bộ, cây cỏ mọc hoặc đá tròn to", 20.0, 0.050, 3.75),
    (5, "Sông cực kỳ trở ngại, khúc khuỷu, bãi sông không phẳng, nhiều đá cuội to", 15.0, 0.060, 5.50),
    (6, "Sông có bãi, cây cỏ mọc đặc biệt rậm rạp, nước chảy chậm, có vực sâu", 12.5, 0.080, 7.00),
    (7, "Sông miền núi có nhiều đá lớn, nước chảy sinh bọt tung toé, khúc khuỷu", 12.5, 0.080, 7.00),
    (8, "Sông miền núi có thác, lòng sông khúc khuỷu, đá to, nước chảy réo vang", 10.0, 0.100, 9.00),
    (9, "Sông núi cây cối rậm rạp, nhiều chỗ nước ứ đọng, khúc chết sâu rộng", 7.5, 0.133, 12.00),
    (10, "Sông có bùn đá trôi, bãi sông cây lớn mọc rậm rạp dày đặc", 5.0, 0.200, 20.00)
]

# 8. Bảng 3: Ranh giới phân vùng mưa rào Việt Nam
BANG_PHAN_VUNG_MUA = {
    1: "Lưu vực thượng nguồn sông Mã, sông Chu, sông Cả",
    2: "Vùng thượng nguồn sông Đà từ biên giới đến Nghĩa Lộ",
    3: "Tâm mưa Hoàng Liên Sơn hữu ngạn sông Thao, từ biên giới đến Ngòi Hút",
    4: "Vùng lưu vực sông Kỳ Cùng, sông Bằng Giang, thượng nguồn sông Hồng",
    5: "Lưu vực sông Gâm, tả ngạn sông Lô",
    6: "Thung lũng sông Thao, sông Chảy, hạ lưu sông Lô - Gâm",
    7: "Các lưu vực bắt nguồn từ dãy Yên Tử đổ ra biển",
    8: "Vùng ven biển từ Hải Phòng đến Thanh Hóa",
    9: "Các lưu vực phần trung du sông Mã, sông Chu ra đến biển",
    10: "Vùng ven biển từ Thanh Hóa đến Đồng Hới",
    11: "Vùng ven biển từ Đồng Hới đến Đà Nẵng",
    12: "Vùng ven biển từ Đà Nẵng đến Quảng Ngãi",
    13: "Vùng ven biển từ Quảng Ngãi đến Phan Rang",
    14: "Các lưu vực sông phía bắc Tây Nguyên",
    15: "Các lưu vực sông phía nam Tây Nguyên",
    16: "Các lưu vực sông từ Ban Mê Thuột tới Bảo Lộc",
    17: "Vùng ven biển từ Phan Rang đến Vũng Tàu",
    18: "Vùng đồng bằng Nam Bộ"
}


# =============================================================================
# GIAO DIỆN PHẦN MỀM CHÍNH
# =============================================================================
class SokolovskyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TÍNH TOÁN LŨ LỚN THEO PHƯƠNG PHÁP XÔ-KÔ-LÔP-SKY (F > 100 km²)")
        self.root.geometry("1100x950")
        self.root.resizable(True, True)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.mean_x = 107.2
        self.rain_raw_vals = None
        self.popup_windows = []

        self.setup_ui()

    def on_close(self):
        try:
            for w in self.popup_windows:
                if w and w.winfo_exists(): w.destroy()
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        finally:
            os._exit(0)

    def setup_ui(self):
        # THANH THỰC ĐƠN
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="💾 Lưu dự án (Save)", command=self.save_project)
        file_menu.add_command(label="📂 Mở dự án cũ (Open)", command=self.open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Thoát", command=self.on_close)
        menubar.add_cascade(label="Tệp (File)", menu=file_menu)

        tbl_menu = tk.Menu(menubar, tearoff=0)
        tbl_menu.add_command(label="1. Bảng 2-10 (Tra α, Ho)", command=self.show_b210_window)
        tbl_menu.add_command(label="2. Bảng C.13 (Hệ số f)", command=self.show_c13_window)
        tbl_menu.add_command(label="3. Bảng Tọa độ đường cong mưa ψ(T)", command=self.show_curve_window)
        tbl_menu.add_command(label="4. Bảng Hệ số nhám sông (1/n, N, γ)", command=self.show_nham_window)
        tbl_menu.add_command(label="5. Bảng tra hệ số km", command=self.show_km_window)
        tbl_menu.add_command(label="6. Bảng tra vận tốc Vmax", command=self.show_vmax_window)
        tbl_menu.add_command(label="7. Bảng tra hệ số truyền lũ kv (22TCN 220)", command=self.show_kv_window)
        tbl_menu.add_command(label="8. Bảng 3: Phân vùng mưa rào I-XVIII", command=self.show_vungmua_window)
        menubar.add_cascade(label="Tra cứu 8 Bảng chuẩn", menu=tbl_menu)
        self.root.config(menu=menubar)

        # TIÊU ĐỀ
        hdr = tk.Frame(self.root, pady=4)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="TÍNH TOÁN ĐỈNH LŨ THIẾT KẾ THEO PHƯƠNG PHÁP XÔ-KÔ-LÔP-SKY (F > 100 km²)", 
                 font=("Times New Roman", 15, "bold"), fg="#154360").pack()

        r_proj = tk.Frame(self.root, padx=15, pady=2)
        r_proj.pack(fill=tk.X)
        tk.Label(r_proj, text="Tên công trình / Vị trí tính:", font=("Arial", 9, "bold"), fg="#b71c1c").pack(side=tk.LEFT)
        self.txt_project = tk.Entry(r_proj, font=("Arial", 10, "bold"), fg="#b71c1c", width=34)
        self.txt_project.insert(0, "Cầu Phú Kiểng")
        self.txt_project.pack(side=tk.LEFT, padx=10)

        # Thanh nút bấm mở nhanh các bảng tra
        btn_bar = tk.Frame(self.root, padx=15, pady=2)
        btn_bar.pack(fill=tk.X)
        tk.Label(btn_bar, text="Mở xem bảng tra:", font=("Arial", 8, "italic")).pack(side=tk.LEFT)
        tk.Button(btn_bar, text="📑 Bảng 2-10 (α, Ho)", font=("Arial", 8, "bold"), bg="#e8f5e9", fg="#2e7d32", command=self.show_b210_window).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_bar, text="📑 Bảng C.13 (Hệ số f)", font=("Arial", 8, "bold"), bg="#e1f5fe", fg="#0277bd", command=self.show_c13_window).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_bar, text="📑 Đường cong mưa ψ(T)", font=("Arial", 8, "bold"), bg="#f3e5f5", fg="#6a1b9a", command=self.show_curve_window).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_bar, text="📑 Bảng tra kv (22TCN 220)", font=("Arial", 8, "bold"), bg="#fff3e0", fg="#e65100", command=self.show_kv_window).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_bar, text="📑 Bảng 3: Ranh giới vùng mưa", font=("Arial", 8, "bold"), bg="#ede7f6", fg="#4a148c", command=self.show_vungmua_window).pack(side=tk.LEFT, padx=3)

        # =========================================================================
        # MỤC I: THÔNG SỐ ĐẦU VÀO LƯU VỰC VÀ THỦY VĂN
        # =========================================================================
        p_fr = tk.LabelFrame(self.root, text=" I. THÔNG SỐ ĐẦU VÀO LƯU VỰC VÀ THỦY VĂN ", font=("Arial", 9, "bold"), padx=10, pady=4)
        p_fr.pack(fill=tk.X, padx=15, pady=2)

        r_note = tk.Frame(p_fr)
        r_note.pack(fill=tk.X, pady=1)
        tk.Label(r_note, text="Quy ước màu:", font=("Arial", 8, "italic")).pack(side=tk.LEFT)
        tk.Label(r_note, text="  Màu vàng nhạt: Nhập tay  ", font=("Arial", 8, "bold"), bg="#fffde7", fg="#b71c1c", relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=6)
        tk.Label(r_note, text="  Màu xanh nhạt: Tra bảng / Tính tự động  ", font=("Arial", 8, "bold"), bg="#e1f5fe", fg="#0277bd", relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=6)

        # Hàng 1: Flv, Ls, kt (Nhập tay)
        r1 = tk.Frame(p_fr); r1.pack(fill=tk.X, pady=2)
        tk.Label(r1, text="Diện tích lưu vực Flv (km²):", width=22, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_Flv = tk.Entry(r1, width=10, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold")); self.txt_Flv.insert(0, "1855"); self.txt_Flv.pack(side=tk.LEFT, padx=(0, 15))
        
        tk.Label(r1, text="Chiều dài sông chính Ls (km):", width=24, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_Ls = tk.Entry(r1, width=10, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold")); self.txt_Ls.insert(0, "78.98"); self.txt_Ls.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r1, text="H/S thời gian mưa kt:", width=18, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_kt = tk.Entry(r1, width=8, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold")); self.txt_kt.insert(0, "1.0"); self.txt_kt.pack(side=tk.LEFT)

        # Hàng 2: Hệ số dòng chảy α và Ho (tra Bảng 2-10)
        r2 = tk.Frame(p_fr); r2.pack(fill=tk.X, pady=2)
        tk.Label(r2, text="Hệ số α & Ho (tra Bảng 2-10):", width=24, anchor=tk.W, fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(r2, text="Chọn vùng:").pack(side=tk.LEFT)
        self.cbo_b210 = ttk.Combobox(r2, width=12, state="readonly", values=[f"Vùng {i}" for i in range(1, 12)])
        self.cbo_b210.set("Vùng 11"); self.cbo_b210.pack(side=tk.LEFT, padx=(2, 10))
        self.cbo_b210.bind("<<ComboboxSelected>>", self.on_select_b210)

        tk.Label(r2, text="Kết quả tra α:", fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_alpha = tk.Entry(r2, width=8, bg="#e1f5fe", fg="#0277bd", font=("Arial", 9, "bold")); self.txt_alpha.insert(0, "0.86"); self.txt_alpha.pack(side=tk.LEFT, padx=(2, 10))

        tk.Label(r2, text="Ho (mm):", fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_Ho = tk.Entry(r2, width=8, bg="#e1f5fe", fg="#0277bd", font=("Arial", 9, "bold")); self.txt_Ho.insert(0, "16"); self.txt_Ho.pack(side=tk.LEFT)

        # Hàng 3: Hệ số hình dạng lũ f (tra Bảng C.13)
        r3 = tk.Frame(p_fr); r3.pack(fill=tk.X, pady=2)
        tk.Label(r3, text="Hệ số hình dạng lũ f (tra Bảng C.13):", width=28, anchor=tk.W, fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(r3, text="Chọn vùng:").pack(side=tk.LEFT)
        self.cbo_c13 = ttk.Combobox(r3, width=12, state="readonly", values=[f"Vùng {k}" for k in BANG_C13.keys()])
        self.cbo_c13.set("Vùng II"); self.cbo_c13.pack(side=tk.LEFT, padx=(2, 10))
        self.cbo_c13.bind("<<ComboboxSelected>>", self.on_select_c13)

        tk.Label(r3, text="Kết quả tra f:", fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_f = tk.Entry(r3, width=8, bg="#e1f5fe", fg="#0277bd", font=("Arial", 9, "bold")); self.txt_f.insert(0, "0.7"); self.txt_f.pack(side=tk.LEFT)

        # Hàng 4: Vận tốc sườn dốc Vmax (tra Bảng Vmax)
        r4 = tk.Frame(p_fr); r4.pack(fill=tk.X, pady=2)
        tk.Label(r4, text="Vận tốc sườn dốc Vmax (tra Bảng Vmax):", width=32, anchor=tk.W, fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(r4, text="Chọn địa hình:").pack(side=tk.LEFT)
        self.cbo_vmax = ttk.Combobox(r4, width=22, state="readonly", values=list(BANG_VMAX.keys()))
        self.cbo_vmax.set("Đồi núi thấp"); self.cbo_vmax.pack(side=tk.LEFT, padx=(2, 10))
        self.cbo_vmax.bind("<<ComboboxSelected>>", self.on_select_vmax)

        tk.Label(r4, text="Kết quả tra Vmax (m/s):", fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_Vmax = tk.Entry(r4, width=8, bg="#e1f5fe", fg="#0277bd", font=("Arial", 9, "bold")); self.txt_Vmax.insert(0, "2.0"); self.txt_Vmax.pack(side=tk.LEFT)

        # Hàng 5: Hệ số truyền lũ lòng sông kv (tra Bảng 22TCN 220)
        r5 = tk.Frame(p_fr); r5.pack(fill=tk.X, pady=2)
        tk.Label(r5, text="H/S truyền lũ kv (tra Bảng 22TCN 220):", width=32, anchor=tk.W, fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(r5, text="Chọn đặc điểm sông:").pack(side=tk.LEFT)
        self.cbo_kv = ttk.Combobox(r5, width=26, state="readonly", values=list(BANG_KV.keys()))
        self.cbo_kv.set("Phát triển tốt"); self.cbo_kv.pack(side=tk.LEFT, padx=(2, 10))
        self.cbo_kv.bind("<<ComboboxSelected>>", self.on_select_kv)

        tk.Label(r5, text="Kết quả tra kv:", fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_kv = tk.Entry(r5, width=8, bg="#e1f5fe", fg="#0277bd", font=("Arial", 9, "bold")); self.txt_kv.insert(0, "0.65"); self.txt_kv.pack(side=tk.LEFT)

        # Hàng 6: Hệ số km (tra Bảng vùng khí hậu)
        r6 = tk.Frame(p_fr); r6.pack(fill=tk.X, pady=2)
        tk.Label(r6, text="Hệ số thời gian km (tra Bảng khí hậu):", width=32, anchor=tk.W, fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(r6, text="Chọn vùng khí hậu:").pack(side=tk.LEFT)
        self.cbo_km = ttk.Combobox(r6, width=18, state="readonly", values=list(BANG_KM.keys()))
        self.cbo_km.set("Đông Bắc"); self.cbo_km.pack(side=tk.LEFT, padx=(2, 10))
        self.cbo_km.bind("<<ComboboxSelected>>", self.on_select_km)

        tk.Label(r6, text="Kết quả tra km:", fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_km = tk.Entry(r6, width=8, bg="#e1f5fe", fg="#0277bd", font=("Arial", 9, "bold")); self.txt_km.insert(0, "0.565"); self.txt_km.pack(side=tk.LEFT)

        # Hàng 7: Phân vùng mưa rào kèm hiển thị ranh giới
        r7 = tk.Frame(p_fr); r7.pack(fill=tk.X, pady=2)
        tk.Label(r7, text="Phân vùng mưa rào (tra Bảng 3 & ψ(T)):", width=32, anchor=tk.W, fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(r7, text="Chọn vùng:").pack(side=tk.LEFT)
        self.cbo_vung = ttk.Combobox(r7, width=12, state="readonly", values=[f"Vùng {i}" for i in range(1, 19)])
        self.cbo_vung.set("Vùng 13"); self.cbo_vung.pack(side=tk.LEFT, padx=(2, 10))
        self.cbo_vung.bind("<<ComboboxSelected>>", self.on_select_vungmua)

        self.lbl_ranhgioi = tk.Label(r7, text="Ranh giới: Vùng ven biển từ Quảng Ngãi đến Phan Rang", fg="#b71c1c", font=("Arial", 8, "italic"))
        self.lbl_ranhgioi.pack(side=tk.LEFT, padx=5)

        # Hàng 8: Hệ số triết giảm ao hồ, đầm lầy δ
        r8 = tk.Frame(p_fr); r8.pack(fill=tk.X, pady=2)
        tk.Label(r8, text="Triết giảm ao hồ, rừng δ (tính theo fa, fl, fr):", width=34, anchor=tk.W, fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(r8, text="fa:").pack(side=tk.LEFT)
        self.txt_fa = tk.Entry(r8, width=5, bg="#fffde7", fg="#b71c1c"); self.txt_fa.insert(0, "0.1"); self.txt_fa.pack(side=tk.LEFT, padx=2)
        tk.Label(r8, text="fl:").pack(side=tk.LEFT)
        self.txt_fl = tk.Entry(r8, width=5, bg="#fffde7", fg="#b71c1c"); self.txt_fl.insert(0, "0.1"); self.txt_fl.pack(side=tk.LEFT, padx=2)
        tk.Label(r8, text="fr:").pack(side=tk.LEFT)
        self.txt_fr = tk.Entry(r8, width=5, bg="#fffde7", fg="#b71c1c"); self.txt_fr.insert(0, "6.9"); self.txt_fr.pack(side=tk.LEFT, padx=2)
        tk.Button(r8, text="⚡ Tính δ", font=("Arial", 7, "bold"), bg="#e1f5fe", fg="#0277bd", command=self.recalculate_delta).pack(side=tk.LEFT, padx=4)

        tk.Label(r8, text="Kết quả tính δ:", fg="#0277bd", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.txt_delta = tk.Entry(r8, width=9, bg="#e1f5fe", fg="#0277bd", font=("Arial", 9, "bold")); self.txt_delta.insert(0, "0.9005"); self.txt_delta.pack(side=tk.LEFT)

        # =========================================================================
        # PHẦN THỐNG KÊ MƯA, TẦN SUẤT LÝ LUẬN & ĐỒ THỊ
        # =========================================================================
        stat_fr = tk.LabelFrame(self.root, text=" THỐNG KÊ MƯA PEARSON III & TẦN SUẤT LÝ LUẬN ", font=("Arial", 9, "bold"), fg="#b71c1c", padx=10, pady=4)
        stat_fr.pack(fill=tk.X, padx=15, pady=2)

        r_st1 = tk.Frame(stat_fr); r_st1.pack(fill=tk.X, pady=2)
        tk.Button(r_st1, text="📁 Nhập tệp trạm mưa (.txt)", font=("Arial", 9, "bold"), bg="#e8f5e9", fg="#2e7d32", command=self.load_rain_txt_file).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r_st1, text="Cv:").pack(side=tk.LEFT, padx=2)
        self.txt_cv = tk.Entry(r_st1, width=6, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold")); self.txt_cv.insert(0, "0.24"); self.txt_cv.pack(side=tk.LEFT, padx=2)
        tk.Label(r_st1, text="Cs:").pack(side=tk.LEFT, padx=2)
        self.txt_cs = tk.Entry(r_st1, width=6, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold")); self.txt_cs.insert(0, "0.72"); self.txt_cs.pack(side=tk.LEFT, padx=2)
        tk.Button(r_st1, text="⚡ Cập nhật H24p", font=("Arial", 8, "bold"), bg="#fff3e0", fg="#e65100", command=self.recalculate_hp_from_cv_cs).pack(side=tk.LEFT, padx=6)

        tk.Button(r_st1, text="📋 Bảng tần suất lý luận", font=("Arial", 8, "bold"), bg="#e1f5fe", fg="#0277bd", command=self.show_freq_table_window).pack(side=tk.RIGHT, padx=4)
        tk.Button(r_st1, text="📈 Vẽ đường tần suất (Chuẩn giấy xác suất)", font=("Arial", 8, "bold"), bg="#fce4ec", fg="#c2185b", command=self.plot_frequency_curve).pack(side=tk.RIGHT, padx=4)

        r_rain = tk.Frame(stat_fr); r_rain.pack(fill=tk.X, pady=3)
        self.rain_entries = {}
        self.cc_entries = {}
        
        rain_defaults = [("P=1%", "398.77"), ("P=1.5%", "373.86"), ("P=4%", "314.74"), ("P=5%", "298.64"), ("P=10%", "253.87"), ("P=50%", "137.68")]
        for p_label, val in rain_defaults:
            box = tk.Frame(r_rain, bd=1, relief=tk.GROOVE, padx=2, pady=2)
            box.pack(side=tk.LEFT, expand=True, padx=2)
            tk.Label(box, text=p_label, font=("Arial", 8, "bold"), fg="#154360").pack()
            
            tk.Label(box, text="H24p gốc:", font=("Arial", 7)).pack()
            ent = tk.Entry(box, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 8, "bold"))
            ent.insert(0, val)
            ent.pack()
            self.rain_entries[p_label] = ent
            
            tk.Label(box, text="Hệ số BĐKH:", font=("Arial", 7), fg="#b71c1c").pack()
            ent_cc = tk.Entry(box, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c")
            ent_cc.insert(0, "1.135")
            ent_cc.pack()
            self.cc_entries[p_label] = ent_cc

        # =========================================================================
        # PHẦN II: KẾT QUẢ TÍNH TOÁN HIỆN TRẠNG
        # =========================================================================
        res_fr2 = tk.LabelFrame(self.root, text=" II. KẾT QUẢ TÍNH TOÁN HIỆN TRẠNG ", font=("Arial", 9, "bold"), fg="#0277bd", padx=10, pady=3)
        res_fr2.pack(fill=tk.BOTH, expand=True, padx=15, pady=2)

        cols2 = ("p", "h24", "psi", "htp", "h_trieu", "qmax")
        self.tree2 = ttk.Treeview(res_fr2, columns=cols2, show="headings", height=4)
        self.tree2.heading("p", text="Tần suất P (%)")
        self.tree2.heading("h24", text="H24p (mm)")
        self.tree2.heading("psi", text="Tung độ ψ(T)")
        self.tree2.heading("htp", text="Htp (mm)")
        self.tree2.heading("h_trieu", text="H'tp triết giảm (mm)")
        self.tree2.heading("qmax", text="Qmax,p (m³/s)")

        self.tree2.column("p", width=100, anchor=tk.CENTER)
        self.tree2.column("h24", width=120, anchor=tk.E)
        self.tree2.column("psi", width=110, anchor=tk.CENTER)
        self.tree2.column("htp", width=120, anchor=tk.E)
        self.tree2.column("h_trieu", width=140, anchor=tk.E)
        self.tree2.column("qmax", width=160, anchor=tk.E)
        self.tree2.pack(fill=tk.BOTH, expand=True, pady=1)

        # =========================================================================
        # PHẦN III: KẾT QUẢ TÍNH TOÁN XÉT ĐẾN BIẾN ĐỔI KHÍ HẬU (BĐKH)
        # =========================================================================
        res_fr3 = tk.LabelFrame(self.root, text=" III. KẾT QUẢ TÍNH TOÁN XÉT ĐẾN BIẾN ĐỔI KHÍ HẬU (BĐKH) ", font=("Arial", 9, "bold"), fg="#2e7d32", padx=10, pady=3)
        res_fr3.pack(fill=tk.BOTH, expand=True, padx=15, pady=2)

        cols3 = ("p", "h24_goc", "cc", "h24_bdkh", "psi", "htp", "h_trieu", "qmax")
        self.tree3 = ttk.Treeview(res_fr3, columns=cols3, show="headings", height=4)
        self.tree3.heading("p", text="Tần suất P (%)")
        self.tree3.heading("h24_goc", text="H24p gốc (mm)")
        self.tree3.heading("cc", text="Hệ số BĐKH")
        self.tree3.heading("h24_bdkh", text="H24p BĐKH (mm)")
        self.tree3.heading("psi", text="ψ(T)")
        self.tree3.heading("htp", text="Htp (mm)")
        self.tree3.heading("h_trieu", text="H'tp triết giảm (mm)")
        self.tree3.heading("qmax", text="Qmax,p (m³/s)")

        self.tree3.column("p", width=85, anchor=tk.CENTER)
        self.tree3.column("h24_goc", width=95, anchor=tk.E)
        self.tree3.column("cc", width=80, anchor=tk.CENTER)
        self.tree3.column("h24_bdkh", width=105, anchor=tk.E)
        self.tree3.column("psi", width=80, anchor=tk.CENTER)
        self.tree3.column("htp", width=95, anchor=tk.E)
        self.tree3.column("h_trieu", width=115, anchor=tk.E)
        self.tree3.column("qmax", width=130, anchor=tk.E)
        self.tree3.pack(fill=tk.BOTH, expand=True, pady=1)

        # CÁC NÚT THAO TÁC CHÍNH
        btn_fr = tk.Frame(self.root, pady=6)
        btn_fr.pack(fill=tk.X, padx=15)

        tk.Button(btn_fr, text="🚀 TÍNH TOÁN LŨ SOKOLOVSKY", font=("Arial", 10, "bold"), bg="#154360", fg="white", padx=15, pady=4, command=self.calculate_all).pack(side=tk.LEFT)
        tk.Button(btn_fr, text="📋 Sao chép kết quả", font=("Arial", 9, "bold"), bg="#27ae60", fg="white", padx=10, pady=4, command=self.copy_table).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_fr, text="💾 Xuất file Excel (.xlsx)", font=("Arial", 9, "bold"), bg="#2980b9", fg="white", padx=10, pady=4, command=self.export_excel).pack(side=tk.RIGHT)

        self.calculate_all()

    # --- SỰ KIỆN TỰ ĐỘNG TRA BẢNG VÀ HIỂN THỊ KẾT QUẢ ---
    def on_select_b210(self, event=None):
        sel = self.cbo_b210.get()
        try:
            v_id = int(sel.replace("Vùng ", ""))
            if v_id in BANG_2_10:
                self.txt_alpha.delete(0, tk.END)
                self.txt_alpha.insert(0, str(BANG_2_10[v_id]["alpha"]))
                self.txt_Ho.delete(0, tk.END)
                self.txt_Ho.insert(0, str(BANG_2_10[v_id]["Ho"]))
                self.calculate_all()
        except Exception:
            pass

    def on_select_c13(self, event=None):
        sel = self.cbo_c13.get().replace("Vùng ", "")
        if sel in BANG_C13:
            self.txt_f.delete(0, tk.END)
            self.txt_f.insert(0, str(BANG_C13[sel]["f_def"]))
            self.calculate_all()

    def on_select_vmax(self, event=None):
        sel = self.cbo_vmax.get()
        if sel in BANG_VMAX:
            self.txt_Vmax.delete(0, tk.END)
            self.txt_Vmax.insert(0, str(BANG_VMAX[sel]))
            self.calculate_all()

    def on_select_kv(self, event=None):
        sel = self.cbo_kv.get()
        if sel in BANG_KV:
            self.txt_kv.delete(0, tk.END)
            self.txt_kv.insert(0, str(BANG_KV[sel]))
            self.calculate_all()

    def on_select_km(self, event=None):
        sel = self.cbo_km.get()
        if sel in BANG_KM:
            self.txt_km.delete(0, tk.END)
            self.txt_km.insert(0, str(BANG_KM[sel]))
            self.calculate_all()

    def on_select_vungmua(self, event=None):
        sel = self.cbo_vung.get()
        try:
            v_id = int(sel.replace("Vùng ", ""))
            if v_id in BANG_PHAN_VUNG_MUA:
                self.lbl_ranhgioi.config(text=f"Ranh giới: {BANG_PHAN_VUNG_MUA[v_id]}")
                self.calculate_all()
        except Exception:
            pass

    def recalculate_delta(self):
        try:
            fa = float(self.txt_fa.get())
            fl = float(self.txt_fl.get())
            fr = float(self.txt_fr.get())
            delta = 1.0 - 0.6 * np.log10(1.0 + fa + 0.2 * fl + 0.05 * fr)
            self.txt_delta.delete(0, tk.END)
            self.txt_delta.insert(0, f"{delta:.4f}")
            self.calculate_all()
        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng nhập đúng dạng số cho fa, fl, fr!")

    # --- CỬA SỔ HIỂN THỊ CÁC BẢNG TRA CHUYÊN NGÀNH ---
    def show_b210_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG 2-10: TRA HỆ SỐ DÒNG CHẢY α VÀ LỚP NƯỚC TỔN THẤT Ho")
        w.geometry("820x450")
        self.popup_windows.append(w)
        tk.Label(w, text="BẢNG 2-10: BẢNG TRA HỆ SỐ α VÀ Ho THEO PHÂN VÙNG LƯU VỰC", font=("Times New Roman", 13, "bold"), fg="#154360").pack(pady=8)
        cols = ("vung", "diadanh", "alpha", "ho")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=12)
        tree.heading("vung", text="Phân vùng"); tree.column("vung", width=80, anchor=tk.CENTER)
        tree.heading("diadanh", text="Lưu vực sông / Địa danh"); tree.column("diadanh", width=480, anchor=tk.W)
        tree.heading("alpha", text="Hệ số α"); tree.column("alpha", width=100, anchor=tk.CENTER)
        tree.heading("ho", text="Ho (mm)"); tree.column("ho", width=100, anchor=tk.CENTER)
        for k, v in BANG_2_10.items():
            tree.insert("", tk.END, values=(k, v["name"], v["alpha"], v["Ho"]))
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

    def show_c13_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG C.13: HỆ SỐ HÌNH DẠNG LŨ f CHO CÁC PHÂN VÙNG")
        w.geometry("780x440")
        self.popup_windows.append(w)
        tk.Label(w, text="BẢNG C.13: HỆ SỐ HÌNH DẠNG LŨ  f  CHO CÁC PHÂN VÙNG", font=("Times New Roman", 13, "bold"), fg="#0277bd").pack(pady=8)
        cols = ("vung", "diadanh", "frange")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=13)
        tree.heading("vung", text="Phân vùng"); tree.column("vung", width=80, anchor=tk.CENTER)
        tree.heading("diadanh", text="Lưu vực sông / Địa danh"); tree.column("diadanh", width=520, anchor=tk.W)
        tree.heading("frange", text="Khoảng hệ số f"); tree.column("frange", width=130, anchor=tk.CENTER)
        for k, v in BANG_C13.items():
            tree.insert("", tk.END, values=(k, v["name"], v["f_range"]))
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

    def show_curve_window(self):
        w = tk.Toplevel(self.root)
        w.title("TỌA ĐỘ ĐƯỜNG CONG MƯA RÀO ψ(T) CỦA CÁC PHÂN VÙNG (I - XVIII)")
        w.geometry("980x480")
        self.popup_windows.append(w)
        tk.Label(w, text="TỌA ĐỘ ĐƯỜNG CONG MƯA RÀO ψ(T) THEO THỜI ĐOẠN TÍNH TOÁN", font=("Times New Roman", 13, "bold"), fg="#6a1b9a").pack(pady=8)
        cols = ["vung"] + [f"t_{t}" for t in TIME_STEPS]
        tree = ttk.Treeview(w, columns=cols, show="headings", height=19)
        tree.heading("vung", text="Vùng"); tree.column("vung", width=55, anchor=tk.CENTER)
        for t in TIME_STEPS:
            tree.heading(f"t_{t}", text=f"{t}'"); tree.column(f"t_{t}", width=60, anchor=tk.CENTER)
        for r_id in range(1, 19):
            vals = [f"Vùng {r_id}"] + [f"{x:.3f}" for x in RAINFALL_CURVE_COORDS[r_id]]
            tree.insert("", tk.END, values=vals)
        sb_x = ttk.Scrollbar(w, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(xscroll=sb_x.set)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        sb_x.pack(side=tk.BOTTOM, fill=tk.X)

    def show_nham_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG HỆ SỐ NHÁM LÒNG SÔNG THIÊN NHIÊN")
        w.geometry("920x420")
        self.popup_windows.append(w)
        tk.Label(w, text="BẢNG HỆ SỐ NHÁM CỦA SÔNG THIÊN NHIÊN (1/n, N, γ)", font=("Times New Roman", 13, "bold"), fg="#e65100").pack(pady=8)
        cols = ("tt", "mota", "inv_n", "N", "gamma")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=11)
        tree.heading("tt", text="TT"); tree.column("tt", width=40, anchor=tk.CENTER)
        tree.heading("mota", text="Đặc điểm lòng sông thiên nhiên"); tree.column("mota", width=620, anchor=tk.W)
        tree.heading("inv_n", text="1/n"); tree.column("inv_n", width=70, anchor=tk.CENTER)
        tree.heading("N", text="N"); tree.column("N", width=70, anchor=tk.CENTER)
        tree.heading("gamma", text="γ"); tree.column("gamma", width=70, anchor=tk.CENTER)
        for row in BANG_NHAM_SONG:
            tree.insert("", tk.END, values=row)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def show_km_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG TRA HỆ SỐ km THEO VÙNG KHÍ HẬU")
        w.geometry("640x350")
        self.popup_windows.append(w)
        tk.Label(w, text="BẢNG TRA HỆ SỐ km THEO VÙNG KHÍ HẬU", font=("Times New Roman", 13, "bold"), fg="#4a148c").pack(pady=8)
        cols = ("vung", "km")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=7)
        tree.heading("vung", text="Vùng khí hậu"); tree.column("vung", width=380, anchor=tk.W)
        tree.heading("km", text="Hệ số km"); tree.column("km", width=150, anchor=tk.CENTER)
        for k, v in BANG_KM.items(): tree.insert("", tk.END, values=(k, v))
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

    def show_vmax_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG TRA VẬN TỐC LỚN NHẤT TRÊN SƯỜN DỐC Vmax")
        w.geometry("680x380")
        self.popup_windows.append(w)
        tk.Label(w, text="BẢNG TRA VẬN TỐC LỚN NHẤT SƯỜN DỐC Vmax (m/s)", font=("Times New Roman", 13, "bold"), fg="#0277bd").pack(pady=8)
        cols = ("dh", "vm")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=8)
        tree.heading("dh", text="Đặc điểm địa hình lưu vực"); tree.column("dh", width=420, anchor=tk.W)
        tree.heading("vm", text="Vmax (m/s)"); tree.column("vm", width=150, anchor=tk.CENTER)
        for k, v in BANG_VMAX.items(): tree.insert("", tk.END, values=(k, v))
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

    def show_kv_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG TRA HỆ SỐ TRUYỀN LŨ LÒNG SÔNG kv (22TCN 220)")
        w.geometry("740x360")
        self.popup_windows.append(w)
        tk.Label(w, text="BẢNG TRA HỆ SỐ TRUYỀN LŨ LÒNG SÔNG kv (THEO 22TCN 220)", font=("Times New Roman", 13, "bold"), fg="#b71c1c").pack(pady=8)
        cols = ("dd", "kv")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=6)
        tree.heading("dd", text="Đặc điểm hệ thống sông & lòng dẫn"); tree.column("dd", width=500, anchor=tk.W)
        tree.heading("kv", text="Hệ số kv"); tree.column("kv", width=140, anchor=tk.CENTER)
        for k, v in BANG_KV.items(): tree.insert("", tk.END, values=(k, v))
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

    def show_vungmua_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG 3: RANH GIỚI PHÂN VÙNG MƯA RÀO VIỆT NAM (I - XVIII)")
        w.geometry("860x480")
        self.popup_windows.append(w)
        tk.Label(w, text="BẢNG 3: BẢNG PHÂN VÙNG MƯA RÀO VIỆT NAM KÈM RANH GIỚI CHI TIẾT", font=("Times New Roman", 13, "bold"), fg="#154360").pack(pady=8)
        cols = ("vung", "mota")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=19)
        tree.heading("vung", text="Phân vùng"); tree.column("vung", width=90, anchor=tk.CENTER)
        tree.heading("mota", text="Ranh giới phân vùng mưa rào"); tree.column("mota", width=700, anchor=tk.W)
        for k, v in BANG_PHAN_VUNG_MUA.items():
            tree.insert("", tk.END, values=(f"Vùng {k}", v))
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    # --- TÍNH TOÁN PEARSON III VÀ BẢNG TẦN SUẤT LÝ LUẬN ---
    def get_kp(self, p_percent, cv, cs):
        u = norm.ppf(1.0 - p_percent / 100.0)
        if abs(cs) < 0.01:
            return 1.0 + cv * u
        kp = 1.0 + cv * (u + (u**2 - 1.0) * cs / 6.0 + (u**3 - 3.0*u) * (cs**2) / 27.0)
        return max(kp, 0.0)

    def recalculate_hp_from_cv_cs(self):
        try:
            cv = float(self.txt_cv.get())
            cs = float(self.txt_cs.get())
            p_vals = [1.0, 1.5, 4.0, 5.0, 10.0, 50.0]
            
            new_hp = []
            for p in p_vals:
                kp = self.get_kp(p, cv, cs)
                new_hp.append(self.mean_x * kp)

            keys = list(self.rain_entries.keys())
            for k_label, hp_val in zip(keys, new_hp):
                if k_label in self.rain_entries:
                    self.rain_entries[k_label].delete(0, tk.END)
                    self.rain_entries[k_label].insert(0, f"{hp_val:.2f}")

            messagebox.showinfo("Thành công", f"Đã cập nhật lượng mưa gốc H24p theo phân phối Pearson III!")
            self.calculate_all()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Lỗi tính toán: {e}")

    def load_rain_txt_file(self):
        f_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not f_path: return
        try:
            with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            vals = []
            for l in lines:
                parts = l.replace(",", " ").split()
                if len(parts) >= 2:
                    try: vals.append(float(parts[1]))
                    except ValueError: pass
                elif len(parts) == 1:
                    try: vals.append(float(parts[0]))
                    except ValueError: pass

            if len(vals) < 3:
                messagebox.showwarning("Cảnh báo", "Chuỗi số liệu mưa phải có ít nhất 3 năm.")
                return

            self.rain_raw_vals = np.array(vals)
            self.mean_x = float(np.mean(self.rain_raw_vals))
            std_x = float(np.std(self.rain_raw_vals, ddof=1))
            cv_calc = std_x / self.mean_x
            
            cs_calc = float(skew(self.rain_raw_vals, bias=False))
            if cs_calc < 0.1: cs_calc = 3.0 * cv_calc

            self.txt_cv.delete(0, tk.END); self.txt_cv.insert(0, f"{cv_calc:.2f}")
            self.txt_cs.delete(0, tk.END); self.txt_cs.insert(0, f"{cs_calc:.2f}")

            messagebox.showinfo("Thành công", f"Đã nạp {len(vals)} năm từ file trạm mưa.\nX_tb = {self.mean_x:.2f} mm | Cv = {cv_calc:.2f} | Cs = {cs_calc:.2f}")
            self.recalculate_hp_from_cv_cs()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được tệp TXT: {e}")

    def show_freq_table_window(self):
        w = tk.Toplevel(self.root)
        w.title("BẢNG KẾT QUẢ TẦN SUẤT LÝ LUẬN MƯA NGÀY (PEARSON III)")
        w.geometry("800x580")
        self.popup_windows.append(w)

        tk.Label(w, text="BẢNG TẦN SUẤT LÝ LUẬN LƯỢNG MƯA NGÀY H24p (PEARSON III)", font=("Times New Roman", 13, "bold"), fg="#154360").pack(pady=8)
        
        try:
            cv = float(self.txt_cv.get())
            cs = float(self.txt_cs.get())
        except ValueError:
            cv, cs = 0.24, 0.72

        p_list = [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 25.0, 30.0, 50.0, 75.0, 80.0, 90.0, 95.0, 99.0, 99.9, 99.99]
        
        cols = ("p", "kp", "hp")
        tree = ttk.Treeview(w, columns=cols, show="headings", height=16)
        tree.heading("p", text="Tần suất P (%)"); tree.column("p", width=160, anchor=tk.CENTER)
        tree.heading("kp", text="Hệ số mô-đun Kp"); tree.column("kp", width=180, anchor=tk.CENTER)
        tree.heading("hp", text="Lượng mưa H24p (mm)"); tree.column("hp", width=220, anchor=tk.E)

        table_records = []
        for p in p_list:
            kp = self.get_kp(p, cv, cs)
            hp = self.mean_x * kp
            tree.insert("", tk.END, values=(f"{p} %", f"{kp:.4f}", f"{hp:.2f}"))
            table_records.append({"Tần suất P (%)": p, "Hệ số Kp": round(kp, 4), "Lượng mưa H24p (mm)": round(hp, 2)})

        tree.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        def export_table():
            f_s = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
            if not f_s: return
            pd.DataFrame(table_records).to_excel(f_s, index=False)
            messagebox.showinfo("Thành công", f"Đã xuất file:\n{f_s}")

        tk.Button(w, text="💾 Xuất bảng tần suất ra Excel", font=("Arial", 9, "bold"), bg="#27ae60", fg="white", padx=10, pady=4, command=export_table).pack(pady=8)

    # --- VẼ ĐƯỜNG TẦN SUẤT CHUẨN GIẤY XÁC SUẤT GAUSS (NHƯ ẢNH MẪU) ---
    def plot_frequency_curve(self):
        if not HAS_MATPLOTLIB:
            messagebox.showwarning("Cảnh báo", "Môi trường hiện tại chưa cài đặt matplotlib để vẽ biểu đồ.")
            return

        w = tk.Toplevel(self.root)
        w.title("BẢN VẼ ĐƯỜNG TẦN SUẤT LƯỢNG MƯA 1 NGÀY LỚN NHẤT NĂM (PEARSON III)")
        w.geometry("1100x750")
        self.popup_windows.append(w)

        try:
            cv = float(self.txt_cv.get())
            cs = float(self.txt_cs.get())
        except ValueError:
            cv, cs = 0.24, 0.72

        proj_name = self.txt_project.get()

        fig, ax = plt.subplots(figsize=(11.5, 7.2), dpi=100)

        def p_to_x(p):
            return norm.ppf(p / 100.0)

        p_ticks = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 85.0, 90.0, 95.0, 99.0, 99.9, 99.95, 99.99]
        tick_labels = ['001', '005', '01', '05', '10', '5', '10', '15', '20', '30', '40', '50', '60', '70', '80', '85', '90', '95', '99', '999', '9995', '9999']
        x_ticks = [p_to_x(p) for p in p_ticks]

        x_min = p_to_x(0.008)
        x_max = p_to_x(99.992)
        ax.set_xlim(x_min, x_max)

        p_dense = np.linspace(0.01, 99.99, 500)
        x_dense = [p_to_x(p) for p in p_dense]
        phi_dense = np.array([pearson3.ppf(1.0 - p/100.0, skew=cs) for p in p_dense])
        kp_dense = 1.0 + cv * phi_dense
        hp_dense = self.mean_x * kp_dense

        ax.plot(x_dense, hp_dense, color='black', lw=1.8, zorder=4)

        ax.set_xticks(x_ticks)
        ax.set_xticklabels(tick_labels, fontsize=8.5, family='sans-serif')

        for xt in x_ticks:
            ax.axvline(xt, color='#888888', lw=0.6, alpha=0.7)

        minor_p = [0.02, 0.03, 0.04, 0.2, 0.3, 0.4, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19, 
                   22, 24, 26, 28, 32, 34, 36, 38, 42, 44, 46, 48, 52, 54, 56, 58, 62, 64, 66, 68, 72, 
                   74, 76, 78, 82, 84, 86, 88, 91, 92, 93, 94, 96, 97, 98, 99.2, 99.4, 99.6, 99.8]
        for mp in minor_p:
            ax.axvline(p_to_x(mp), color='#e8e8e8', lw=0.4, alpha=0.6)

        ax.grid(True, axis='y', color='#888888', lw=0.6, alpha=0.7)

        n_obs = 30
        if self.rain_raw_vals is not None and len(self.rain_raw_vals) > 0:
            sorted_vals = np.sort(self.rain_raw_vals)[::-1]
            n_obs = len(sorted_vals)
            m_pts = np.arange(1, n_obs + 1)
            p_emp = (m_pts - 0.25) / (n_obs + 0.5) * 100.0
            x_emp = [p_to_x(p) for p in p_emp]
            ax.scatter(x_emp, sorted_vals, color='black', s=14, zorder=10)

        ax.text(0.01, 1.02, "H (mm)", transform=ax.transAxes, fontsize=9.5, fontweight='bold', va='bottom', ha='left')

        title_banner = f"ĐƯỜNG TẦN SUẤT LƯỢNG MƯA 1 NGÀY LỚN NHẤT NĂM TRẠM {proj_name.upper()}"
        ax.text(0.65, 0.94, title_banner, transform=ax.transAxes, fontsize=10, fontweight='bold', ha='center',
                bbox=dict(boxstyle='square,pad=0.5', facecolor='white', edgecolor='black', lw=1.2))

        info_block = f"X̄ = {self.mean_x:.2f} mm          N = {n_obs}\nCv = {cv:.2f}\nCs = {cs:.2f}\nPHƯƠNG PHÁP THÍCH HỢP - PEARSON III"
        ax.text(0.65, 0.79, info_block, transform=ax.transAxes, fontsize=8.5, ha='center',
                bbox=dict(boxstyle='square,pad=0.5', facecolor='white', edgecolor='black', lw=1.0))

        # Khung chữ ký chuẩn kỹ thuật như ảnh mẫu
        sig_data = [
            ["", "", "", "2026"],
            ["Người vẽ", "Nguyễn Kim Tuyên", "Người kiểm tra", ""]
        ]
        sig_tbl = ax.table(cellText=sig_data, colWidths=[0.12, 0.22, 0.16, 0.10], cellLoc='center', loc='bottom right', bbox=[0.40, 0.0, 0.60, 0.12])
        sig_tbl.auto_set_font_size(False)
        sig_tbl.set_fontsize(8.5)
        for key, cell in sig_tbl.get_celld().items():
            cell.set_edgecolor('black')
            cell.set_facecolor('white')
            cell.set_linewidth(1.0)

        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=w)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        toolbar = NavigationToolbar2Tk(canvas, w)
        toolbar.update()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # --- TÍNH TOÁN LŨ SOKOLOVSKY CHO PHẦN II VÀ PHẦN III ---
    def calculate_all(self):
        try:
            Flv = float(self.txt_Flv.get())
            Ls = float(self.txt_Ls.get())
            Ho = float(self.txt_Ho.get())
            Vmax = float(self.txt_Vmax.get())
            kv = float(self.txt_kv.get())
            kt = float(self.txt_kt.get())
            km = float(self.txt_km.get())
            alpha = float(self.txt_alpha.get())
            f_shape = float(self.txt_f.get())
            delta = float(self.txt_delta.get())
            
            sel_vung = self.cbo_vung.get()
            try:
                vung = int(sel_vung.replace("Vùng ", ""))
            except Exception:
                vung = 13

            v_tb = kv * Vmax
            ts = Ls / (v_tb * 3.6) if v_tb > 0 else 16.88
            tl = ts

            T = ts * km * kt

            curve_vals = RAINFALL_CURVE_COORDS.get(vung, RAINFALL_CURVE_COORDS[13])
            psi = float(np.interp(T * 60.0, TIME_STEPS, curve_vals))

            self.tree2.delete(*self.tree2.get_children())
            self.tree3.delete(*self.tree3.get_children())
            self.results_ii = []
            self.results_iii = []

            for p_label, ent in self.rain_entries.items():
                h24_goc = float(ent.get())
                cc_val = float(self.cc_entries[p_label].get())
                h24_bdkh = h24_goc * cc_val

                # --- PHẦN II: KẾT QUẢ TÍNH TOÁN HIỆN TRẠNG ---
                htp_ii = h24_goc * psi
                h_trieu_ii = htp_ii / (1.0 + 0.001 * (Flv ** 0.8))
                qmax_ii = (0.278 * alpha * max(h_trieu_ii - Ho, 0.0) * f_shape * Flv * delta) / tl if tl > 0 else 0.0

                self.tree2.insert("", tk.END, values=(
                    p_label, f"{h24_goc:.2f}", f"{psi:.4f}", f"{htp_ii:.2f}", f"{h_trieu_ii:.2f}", f"{qmax_ii:.2f}"
                ))
                self.results_ii.append({
                    "Tần suất P": p_label, "H24p (mm)": round(h24_goc, 2),
                    "Tung độ ψ(T)": round(psi, 4), "Htp (mm)": round(htp_ii, 2),
                    "H'tp triết giảm (mm)": round(h_trieu_ii, 2), "Qmax,p (m³/s)": round(qmax_ii, 2)
                })

                # --- PHẦN III: KẾT QUẢ TÍNH TOÁN XÉT ĐẾN BIẾN ĐỔI KHÍ HẬU (BĐKH) ---
                htp_iii = h24_bdkh * psi
                h_trieu_iii = htp_iii / (1.0 + 0.001 * (Flv ** 0.8))
                qmax_iii = (0.278 * alpha * max(h_trieu_iii - Ho, 0.0) * f_shape * Flv * delta) / tl if tl > 0 else 0.0

                self.tree3.insert("", tk.END, values=(
                    p_label, f"{h24_goc:.2f}", f"{cc_val:.2f}", f"{h24_bdkh:.2f}",
                    f"{psi:.4f}", f"{htp_iii:.2f}", f"{h_trieu_iii:.2f}", f"{qmax_iii:.2f}"
                ))
                self.results_iii.append({
                    "Tần suất P": p_label, "H24p gốc (mm)": round(h24_goc, 2),
                    "Hệ số BĐKH": round(cc_val, 3), "H24p tính (mm)": round(h24_bdkh, 2),
                    "Tung độ ψ(T)": round(psi, 4), "Htp (mm)": round(htp_iii, 2),
                    "H'tp triết giảm (mm)": round(h_trieu_iii, 2), "Qmax,p (m³/s)": round(qmax_iii, 2)
                })

        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng kiểm tra lại các ô số liệu nhập vào!")

    # --- LƯU & MỞ FILE DỰ ÁN ---
    def save_project(self):
        f_path = filedialog.asksaveasfilename(defaultextension=".soko", filetypes=[("Sokolovsky files", "*.soko"), ("JSON files", "*.json")])
        if not f_path: return
        try:
            data = {
                "project_name": self.txt_project.get(),
                "Flv": self.txt_Flv.get(), "Ls": self.txt_Ls.get(), "Ho": self.txt_Ho.get(),
                "Vmax": self.txt_Vmax.get(), "kv": self.txt_kv.get(), "kt": self.txt_kt.get(), "km": self.txt_km.get(),
                "alpha": self.txt_alpha.get(), "f": self.txt_f.get(), "delta": self.txt_delta.get(),
                "vung": self.cbo_vung.get(), "b210": self.cbo_b210.get(), "c13": self.cbo_c13.get(),
                "vmax_sel": self.cbo_vmax.get(), "kv_sel": self.cbo_kv.get(), "km_sel": self.cbo_km.get(),
                "cv": self.txt_cv.get(), "cs": self.txt_cs.get(), "mean_x": self.mean_x,
                "fa": self.txt_fa.get(), "fl": self.txt_fl.get(), "fr": self.txt_fr.get(),
                "rain_data": {p: self.rain_entries[p].get() for p in self.rain_entries},
                "cc_data": {p: self.cc_entries[p].get() for p in self.cc_entries}
            }
            with open(f_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("Thành công", f"Đã lưu tệp dự án tại:\n{f_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu file: {e}")

    def open_project(self):
        f_path = filedialog.askopenfilename(filetypes=[("Project files", "*.soko *.json"), ("All files", "*.*")])
        if not f_path: return
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.txt_project.delete(0, tk.END); self.txt_project.insert(0, data.get("project_name", ""))
            self.txt_Flv.delete(0, tk.END); self.txt_Flv.insert(0, data.get("Flv", "1855"))
            self.txt_Ls.delete(0, tk.END); self.txt_Ls.insert(0, data.get("Ls", "78.98"))
            self.txt_Ho.delete(0, tk.END); self.txt_Ho.insert(0, data.get("Ho", "16"))
            self.txt_Vmax.delete(0, tk.END); self.txt_Vmax.insert(0, data.get("Vmax", "2.0"))
            self.txt_kv.delete(0, tk.END); self.txt_kv.insert(0, data.get("kv", "0.65"))
            self.txt_kt.delete(0, tk.END); self.txt_kt.insert(0, data.get("kt", "1.0"))
            if "km" in data: self.txt_km.delete(0, tk.END); self.txt_km.insert(0, data["km"])
            self.txt_alpha.delete(0, tk.END); self.txt_alpha.insert(0, data.get("alpha", "0.86"))
            self.txt_f.delete(0, tk.END); self.txt_f.insert(0, data.get("f", "0.7"))
            self.txt_delta.delete(0, tk.END); self.txt_delta.insert(0, data.get("delta", "0.9005"))
            self.cbo_vung.set(data.get("vung", "Vùng 13"))
            self.on_select_vungmua()
            if "b210" in data: self.cbo_b210.set(data["b210"])
            if "c13" in data: self.cbo_c13.set(data["c13"])
            if "vmax_sel" in data: self.cbo_vmax.set(data["vmax_sel"])
            if "kv_sel" in data: self.cbo_kv.set(data["kv_sel"])
            if "km_sel" in data: self.cbo_km.set(data["km_sel"])
            self.txt_cv.delete(0, tk.END); self.txt_cv.insert(0, data.get("cv", "0.24"))
            self.txt_cs.delete(0, tk.END); self.txt_cs.insert(0, data.get("cs", "0.72"))
            self.mean_x = data.get("mean_x", 107.2)
            if "fa" in data: self.txt_fa.delete(0, tk.END); self.txt_fa.insert(0, data["fa"])
            if "fl" in data: self.txt_fl.delete(0, tk.END); self.txt_fl.insert(0, data["fl"])
            if "fr" in data: self.txt_fr.delete(0, tk.END); self.txt_fr.insert(0, data["fr"])

            for p, val in data.get("rain_data", {}).items():
                if p in self.rain_entries:
                    self.rain_entries[p].delete(0, tk.END); self.rain_entries[p].insert(0, val)
            for p, val in data.get("cc_data", {}).items():
                if p in self.cc_entries:
                    self.cc_entries[p].delete(0, tk.END); self.cc_entries[p].insert(0, val)

            self.calculate_all()
            messagebox.showinfo("Thành công", "Đã nạp dự án thành công!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không mở được tệp: {e}")

    def copy_table(self):
        if not hasattr(self, 'results_ii'): return
        out = "=== II. KẾT QUẢ TÍNH TOÁN HIỆN TRẠNG ===\n"
        out += "Tan suat P\tH24p (mm)\tPsi(T)\tHtp (mm)\tH'tp triet giam\tQmax,p (m3/s)\n"
        for r in self.results_ii:
            out += f"{r['Tần suất P']}\t{r['H24p (mm)']}\t{r['Tung độ ψ(T)']}\t{r['Htp (mm)']}\t{r['H\'tp triết giảm (mm)']}\t{r['Qmax,p (m³/s)']}\n"
        
        out += "\n=== III. KẾT QUẢ TÍNH TOÁN XÉT ĐẾN BIẾN ĐỔI KHÍ HẬU (BĐKH) ===\n"
        out += "Tan suat P\tH24p goc\tHe so BDKH\tH24p tinh\tPsi(T)\tHtp (mm)\tH'tp triet giam\tQmax,p (m3/s)\n"
        for r in self.results_iii:
            out += f"{r['Tần suất P']}\t{r['H24p gốc (mm)']}\t{r['Hệ số BĐKH']}\t{r['H24p tính (mm)']}\t{r['Tung độ ψ(T)']}\t{r['Htp (mm)']}\t{r['H\'tp triết giảm (mm)']}\t{r['Qmax,p (m³/s)']}\n"
        
        self.root.clipboard_clear(); self.root.clipboard_append(out)
        messagebox.showinfo("Thành công", "Đã sao chép toàn bộ kết quả vào Clipboard!")

    # =========================================================================
    # XUẤT FILE EXCEL ĐỊNH DẠNG CHUẨN XÁC 100% NHƯ HÌNH ẢNH MẪU
    # =========================================================================
    def build_excel_sheet(self, ws, title_sec2, p_labels, h24_list, psi, htp_list, h_trieu_list, qmax_list, inputs):
        font_family = "Times New Roman"
        font_title = Font(name=font_family, size=12, bold=True)
        font_regular = Font(name=font_family, size=11, bold=False)
        font_italic = Font(name=font_family, size=11, italic=True)
        font_bold = Font(name=font_family, size=11, bold=True)
        font_hdr = Font(name=font_family, size=11, bold=True, color="FFFFFF")

        fill_hdr = PatternFill(start_color="203764", end_color="203764", fill_type="solid")
        thin_box = Side(border_style="thin", color="000000")
        border_cell = Border(left=thin_box, right=thin_box, top=thin_box, bottom=thin_box)

        align_left = Alignment(horizontal="left", vertical="center")
        align_center = Alignment(horizontal="center", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        # Row 2: Tiêu đề Mục I
        ws.cell(row=2, column=1, value="I. THÔNG SỐ ĐẦU VÀO LƯU VỰC VÀ THỦY VĂN").font = font_title

        # Bảng 1: Thông số hình thái lưu vực (Rows 3 đến 16)
        table1_data = [
            ("Diện tích lưu vực", "Flv", inputs["Flv"], "km²"),
            ("Chiều dài sông chính", "Ls", inputs["Ls"], "km"),
            ("Lớp nước tổn thất ban đầu", "Ho", inputs["Ho"], "mm"),
            ("Vận tốc bình quân lớn nhất tại cửa ra", "Vmax", inputs["Vmax"], "m/s"),
            ("H/S vận tốc truyền lũ tb lòng sông", "kv", inputs["kv"], ""),
            ("H/S thời gian mưa rào", "kt", inputs["kt"], ""),
            ("Hệ số dòng chảy lũ", "α", inputs["alpha"], ""),
            ("Hệ số hình dạng lũ", "f", inputs["f"], ""),
            ("Hệ số triết giảm hồ ao, đầm lầy", "δ", inputs["delta"], ""),
            ("Thời gian tập trung nước trong sông", "ts", inputs["ts"], "giờ"),
            ("Thời gian lũ lên", "tl", inputs["tl"], "giờ"),
            ("Thời gian mưa tính toán", "T", inputs["T"], "giờ"),
            ("Phân khu mưa rào", "R", inputs["R"], ""),
            ("Lưu lượng dòng chảy ngầm", "Qng", inputs["Qng"], "m³/s")
        ]

        for idx, (param, sym, val, unit) in enumerate(table1_data, start=3):
            c1 = ws.cell(row=idx, column=1, value=param)
            c2 = ws.cell(row=idx, column=2, value=sym)
            c3 = ws.cell(row=idx, column=3, value=val)
            c4 = ws.cell(row=idx, column=4, value=unit)

            for c in [c1, c2, c3, c4]:
                c.border = border_cell

            c1.font = font_regular; c1.alignment = align_left
            c2.font = font_italic; c2.alignment = align_center
            c3.font = font_bold; c3.alignment = align_center
            c4.font = font_regular; c4.alignment = align_left

            if isinstance(val, (int, float)):
                if val >= 1000:
                    c3.number_format = "#,##0"
                elif isinstance(val, float):
                    c3.number_format = "0.00" if (round(val, 2) != int(val)) else "0"

        # Row 18: Tiêu đề Mục II
        row_sec2 = 18
        num_cols = len(p_labels)
        c_sec2 = ws.cell(row=row_sec2, column=1, value=title_sec2)
        c_sec2.font = font_title
        c_sec2.alignment = align_center
        ws.merge_cells(start_row=row_sec2, start_column=1, end_row=row_sec2, end_column=2 + num_cols)

        # Row 19: Tiêu đề các cột Bảng II (Nền xanh đậm, chữ trắng)
        headers = ["Thông số tính toán", "Ký hiệu (Đơn vị)"] + [p.replace("P=", "") for p in p_labels]
        for c_idx, h_text in enumerate(headers, start=1):
            c = ws.cell(row=19, column=c_idx, value=h_text)
            c.font = font_hdr
            c.fill = fill_hdr
            c.alignment = align_center
            c.border = border_cell

        # Rows 20 đến 25: Số liệu tính toán
        p_percent_vals = []
        for p in p_labels:
            p_clean = p.replace("P=", "").replace("%", "")
            try:
                p_val = float(p_clean)
                p_percent_vals.append(f"{p_val:.1f}%")
            except Exception:
                p_percent_vals.append(p)

        rows_data = [
            ("Tần suất thiết kế", "P (%)", p_percent_vals, align_center, "@", False),
            ("Lượng mưa ngày thiết kế", "H24p (mm)", [round(x, 1) for x in h24_list], align_right, "0.0", False),
            ("Tung độ đường cong lũ tích mưa", "ψ(T)", [round(psi, 3)] * num_cols, align_right, "0.000", False),
            ("Lượng mưa lũ thiết kế", "Htp (mm)", [round(x, 1) for x in htp_list], align_right, "0.0", False),
            ("Lượng mưa lũ thiết kế triết giảm", "H'tp (mm)", [round(x, 1) for x in h_trieu_list], align_right, "0.0", False),
            ("Lưu lượng đỉnh lũ thiết kế", "Qmax,p (m³/s)", [round(x) for x in qmax_list], align_right, "#,##0", True)
        ]

        for r_offset, (p_name, sym, vals, align_val, num_fmt, is_bold) in enumerate(rows_data, start=20):
            c1 = ws.cell(row=r_offset, column=1, value=p_name)
            c2 = ws.cell(row=r_offset, column=2, value=sym)
            c1.font = font_bold if is_bold else font_regular
            c1.alignment = align_left
            c1.border = border_cell

            c2.font = font_bold if is_bold else font_regular
            c2.alignment = align_center
            c2.border = border_cell

            for c_idx, val in enumerate(vals, start=3):
                c = ws.cell(row=r_offset, column=c_idx, value=val)
                c.font = font_bold if is_bold else font_regular
                c.alignment = align_val
                c.border = border_cell
                c.number_format = num_fmt

        # Thiết lập độ rộng cột cho vừa vặn chuẩn in ấn
        ws.column_dimensions['A'].width = 38
        ws.column_dimensions['B'].width = 18
        for col_i in range(3, 3 + num_cols + 2):
            col_letter = get_column_letter(col_i)
            ws.column_dimensions[col_letter].width = 12

        # Bật hiển thị lưới ô Excel
        ws.views.sheetView[0].showGridLines = True

    def export_excel(self):
        proj = self.txt_project.get()
        f_save = filedialog.asksaveasfilename(
            initialfile=f"Sokolovsky_{proj.replace(' ', '_')}.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")]
        )
        if not f_save: return

        try:
            Flv = float(self.txt_Flv.get())
            Ls = float(self.txt_Ls.get())
            Ho = float(self.txt_Ho.get())
            Vmax = float(self.txt_Vmax.get())
            kv = float(self.txt_kv.get())
            kt = float(self.txt_kt.get())
            km = float(self.txt_km.get())
            alpha = float(self.txt_alpha.get())
            f_shape = float(self.txt_f.get())
            delta = float(self.txt_delta.get())

            sel_vung = self.cbo_vung.get()
            try:
                vung = int(sel_vung.replace("Vùng ", ""))
            except Exception:
                vung = 13

            v_tb = kv * Vmax
            ts = Ls / (v_tb * 3.6) if v_tb > 0 else 16.88
            tl = ts
            T = ts * km * kt

            curve_vals = RAINFALL_CURVE_COORDS.get(vung, RAINFALL_CURVE_COORDS[13])
            psi = float(np.interp(T * 60.0, TIME_STEPS, curve_vals))

            inputs = {
                "Flv": Flv, "Ls": Ls, "Ho": Ho, "Vmax": Vmax, "kv": kv, "kt": kt,
                "alpha": alpha, "f": f_shape, "delta": delta,
                "ts": round(ts, 2), "tl": round(tl, 2), "T": round(T, 2),
                "R": vung, "Qng": 0
            }

            p_labels = list(self.rain_entries.keys())
            h24_ii = [float(self.rain_entries[p].get()) for p in p_labels]
            htp_ii = [x * psi for x in h24_ii]
            h_trieu_ii = [x / (1.0 + 0.001 * (Flv ** 0.8)) for x in htp_ii]
            qmax_ii = [(0.278 * alpha * max(h - Ho, 0.0) * f_shape * Flv * delta) / tl for h in h_trieu_ii]

            h24_iii = [h * float(self.cc_entries[p].get()) for h, p in zip(h24_ii, p_labels)]
            htp_iii = [x * psi for x in h24_iii]
            h_trieu_iii = [x / (1.0 + 0.001 * (Flv ** 0.8)) for x in htp_iii]
            qmax_iii = [(0.278 * alpha * max(h - Ho, 0.0) * f_shape * Flv * delta) / tl for h in h_trieu_iii]

            wb = openpyxl.Workbook()
            ws1 = wb.active
            ws1.title = "Hiện trạng"
            self.build_excel_sheet(ws1, "II. KẾT QUẢ TÍNH TOÁN THEO TẦN SUẤT THIẾT KẾ P (%)", p_labels, h24_ii, psi, htp_ii, h_trieu_ii, qmax_ii, inputs)

            ws2 = wb.create_sheet(title="Xét BĐKH")
            self.build_excel_sheet(ws2, "III. KẾT QUẢ TÍNH TOÁN THEO TẦN SUẤT THIẾT KẾ P (%)", p_labels, h24_iii, psi, htp_iii, h_trieu_iii, qmax_iii, inputs)

            wb.save(f_save)
            messagebox.showinfo("Thành công", f"Đã xuất file Excel chuẩn định dạng tại:\n{f_save}")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất file Excel: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SokolovskyApp(root)
    root.mainloop()