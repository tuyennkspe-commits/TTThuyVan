# -*- coding: utf-8 -*-
"""
PHẦN MỀM TÍNH TOÁN XÓI MỐ TRỤ CẦU ĐA DỰ ÁN THEO TIÊU CHUẨN HEC-18 (FHWA) - MASTER PRO v3
- Tách biệt hoàn toàn cơ chế nhập liệu & tính toán MỐ CẦU (Froehlich / HIRE) và TRỤ CẦU (CSU / Trụ phức hợp).
- Bổ sung cửa sổ cấu hình chuyên biệt cho Mố: ya, Qe, Ae, Ve, Fr, L', K1 (riêng từng mố), theta, K2.
- Đồng bộ bảng kết quả Tab 7.4 theo chuẩn biểu mẫu tính xói mố HEC-18.
- Tối ưu bộ nhớ, giao diện trực quan kèm sơ đồ CAD minh họa.
"""

import math
import copy
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import pandas as pd

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches

G = 9.81  # Gia tốc trọng trường (m/s2)


def is_abut_name(name):
    """Mố cầu: tên bắt đầu bằng chữ M (M1, M2, Mố trái, Mố phải...). Trụ: T1, T2..."""
    return str(name).strip().upper().startswith("M")


# =============================================================================
# 1. BẢNG TRA CỨU HỆ SỐ THEO HEC-18 (FHWA)
# =============================================================================
class HEC18Tables:
    PIER_K1 = {
        "Mũi tròn (Round nose)": (1.0, "K1=1.0: Dạng mũi cong tròn elip"),
        "Mũi vuông (Square nose)": (1.1, "K1=1.1: Mũi phẳng vuông góc dòng chảy"),
        "Mũi nhọn (Sharp nose 90°)": (0.9, "K1=0.9: Mũi nhọn góc vát 90 độ"),
        "Trụ tròn (Circular cylinder)": (1.0, "K1=1.0: Cột trụ tròn độc lập"),
        "Nhóm cọc tròn (Group of cylinders)": (1.0, "K1=1.0: Nhóm cọc tròn lộ trong nước")
    }
    ROUND_NOSE = {"Mũi tròn (Round nose)", "Trụ tròn (Circular cylinder)",
                  "Nhóm cọc tròn (Group of cylinders)"}
    DEFAULT_PIER_K1 = "Mũi vuông (Square nose)"

    PIER_K3 = {
        "Nước trong / Đáy phẳng / Sóng cát nghịch": (1.1, "K3=1.1: xói nước trong, đáy phẳng, sóng cát nghịch"),
        "Cồn cát nhỏ (0.6 <= H < 3 m)": (1.1, "K3=1.1: cồn cát nhỏ"),
        "Cồn cát trung bình (3 <= H < 9 m)": (1.2, "K3=1.2: cồn cát trung bình"),
        "Cồn cát lớn (H >= 9 m)": (1.3, "K3=1.3: cồn cát lớn"),
    }
    DEFAULT_K3 = "Nước trong / Đáy phẳng / Sóng cát nghịch"
    LEGACY_K3 = {
        "Đôn cát nhỏ / Xói nước trong": "Nước trong / Đáy phẳng / Sóng cát nghịch",
        "Đáy phẳng / Sóng cát nghịch": "Nước trong / Đáy phẳng / Sóng cát nghịch",
        "Cồn cát nhỏ (Dunes H < 0.6m)": "Nước trong / Đáy phẳng / Sóng cát nghịch",
        "Cồn cát trung bình (0.6m <= H < 3m)": "Cồn cát nhỏ (0.6 <= H < 3 m)",
        "Cồn cát lớn (Dunes H >= 3m)": "Cồn cát trung bình (3 <= H < 9 m)",
    }

    # HEC-18 Bảng 8.1 & Hình 4-11: Hệ số hình dạng mố K1 (Froehlich)
    ABUT_K1 = {
        "Mố có tường thẳng đứng (K1=1.00)": (1.00, "K1=1.00: Mố thành đứng, không có tường cánh loe"),
        "Mố tường thẳng đứng có tường cánh loe đón nước (K1=0.82)": (0.82, "K1=0.82: Có tường cánh xiên loe hướng đón dòng"),
        "Mố xiên / taluy thoải (K1=0.55)": (0.55, "K1=0.55: Mái taluy đất/đá đắp thoải (Spill-through)")
    }
    DEFAULT_ABUT_K1 = "Mố có tường thẳng đứng (K1=1.00)"

    @staticmethod
    def get_laursen_k1(ratio_vstar_w):
        if ratio_vstar_w < 0.50:
            return 0.59, "V*/w < 0.50: Bùn cát vận chuyển sát đáy (Contact load)"
        elif ratio_vstar_w <= 2.0:
            return 0.64, "0.50 <= V*/w <= 2.0: Bùn cát lơ lửng một phần"
        else:
            return 0.69, "V*/w > 2.0: Bùn cát chủ yếu lơ lửng (Suspended load)"


# =============================================================================
# 2. TOÁN HỌC & CÔNG THỨC HEC-18 (THUẦN TÚY THỦY LỰC)
# =============================================================================
class HEC18Calculations:
    @staticmethod
    def fall_velocity_rubey(d_m, nu=1.0e-6, s=2.65):
        d = max(d_m, 1e-6)
        t = 36.0 * nu ** 2 / (G * d ** 3 * (s - 1.0))
        f = math.sqrt(2.0 / 3.0 + t) - math.sqrt(t)
        return f * math.sqrt((s - 1.0) * G * d)

    @staticmethod
    def critical_velocity_vc(y1, d50_m):
        y_val = max(0.01, y1)
        d_val = max(0.00001, d50_m)
        return 6.19 * (y_val ** (1.0 / 6.0)) * (d_val ** (1.0 / 3.0))

    @staticmethod
    def wet_segment(d1, d2, dl):
        if dl <= 0:
            return 0.0, 0.0, 0.0
        if d1 > 0 and d2 > 0:
            return dl, 0.5 * (d1 + d2) * dl, 0.5 * (d1 ** (5.0 / 3.0) + d2 ** (5.0 / 3.0)) * dl
        if d1 > 0 or d2 > 0:
            dm, dn = max(d1, d2), min(d1, d2)
            w = dl * dm / (dm - dn)
            return w, 0.5 * dm * w, (dm ** (5.0 / 3.0)) * w * 3.0 / 8.0
        return 0.0, 0.0, 0.0

    # ----------------------------- TRỤ ĐƠN ---------------------------------
    @staticmethod
    def effective_k1(k1, theta_deg):
        return 1.0 if abs(theta_deg) > 5.0 else k1

    @staticmethod
    def pier_k2(theta_deg, L, a):
        if abs(theta_deg) < 1e-9 or a <= 0:
            return 1.0
        rad = math.radians(abs(theta_deg))
        l_a = min(12.0, max(0.0, L) / a)
        return min(5.0, (math.cos(rad) + l_a * math.sin(rad)) ** 0.65)

    @staticmethod
    def kw_wide_pier(y, a, fr, v_over_vc, d50_m):
        if a <= 0 or y <= 0 or fr <= 0 or fr >= 1.0 or (y / a) >= 0.8 or a <= 50.0 * d50_m:
            return 1.0
        if v_over_vc < 1.0:
            kw = 2.58 * ((y / a) ** 0.34) * (fr ** 0.65)
        else:
            kw = 1.0 * ((y / a) ** 0.13) * (fr ** 0.25)
        return min(1.0, kw)

    @staticmethod
    def pier_scour_csu(y1, v1, a, k1, k2, k3, kw=1.0, capped=False):
        if y1 <= 0.05 or v1 <= 0 or a <= 0:
            return 0.0, 0.0
        fr1 = v1 / math.sqrt(G * y1)
        ys = 2.0 * k1 * k2 * k3 * kw * (a ** 0.65) * (y1 ** 0.35) * (fr1 ** 0.43)
        if capped:
            ys = min(ys, (2.4 if fr1 <= 0.8 else 3.0) * a)
        return ys, fr1

    # --------------------------- TRỤ PHỨC HỢP ------------------------------
    @staticmethod
    def kh_pier_stem(h1, a, f):
        if a <= 0 or h1 <= 0:
            return 1.0
        h1_a = max(0.0, h1 / a)
        f_a = max(0.0, f / a)
        kh = (0.4075 - 0.0669 * f_a) - (0.4271 - 0.0778 * f_a) * h1_a \
             + (0.1615 - 0.0455 * f_a) * (h1_a ** 2) - (0.0269 - 0.012 * f_a) * (h1_a ** 3)
        return max(0.0, min(1.0, kh))

    @staticmethod
    def equivalent_width_pilecap(h2, y2, T, apc):
        if y2 <= 0.05 or T <= 0 or apc <= 0 or h2 <= 0:
            return apc
        y2_limit = min(y2, 3.5 * apc)
        try:
            ratio_term = max(0.001, T / y2_limit)
            h_ratio = max(0.0, min(1.0, h2 / y2_limit))
            val_exp = math.exp(-2.705 + 0.51 * math.log(ratio_term) - 2.783 * (h_ratio ** 3) + 1.751 / math.exp(h_ratio))
            return max(0.01 * apc, min(apc, val_exp * apc))
        except Exception:
            return apc

    @staticmethod
    def pile_group_factors(ap, S, m, n, aproj, h3, y3):
        if h3 <= 0 or y3 <= 0:
            return 1.0, 1.0, aproj, 0.0
        s_ap = max(1.0, S / ap) if ap > 0 else 3.0
        aproj_ap = max(1.0, aproj / ap) if ap > 0 else 5.0
        ksp = 1.0 - (4.0 / 3.0) * (1.0 - 1.0 / aproj_ap) * (1.0 - (s_ap ** (-0.6)))
        ksp = max(0.1, min(1.0, ksp))
        km = 0.9 + 0.10 * m - 0.0714 * (m - 1.0) * (2.4 - 1.1 * s_ap + 0.1 * (s_ap ** 2))
        km = max(1.0, km)
        apg_star = ksp * km * aproj
        h3_y3 = max(0.0, min(1.0, h3 / y3))
        khpg_term = 3.08 * h3_y3 - 5.23 * (h3_y3 ** 2) + 5.25 * (h3_y3 ** 3) - 2.10 * (h3_y3 ** 4)
        khpg = (max(0.0, khpg_term)) ** (1.0 / 0.65) if khpg_term > 0 else 0.0
        return ksp, km, apg_star, min(1.0, khpg)

    @staticmethod
    def complex_pier(y1, v1, a, k1, k2, k3, kw, capped, ho, T, f, apc, ap, S, m, n, aproj):
        r = dict(fr1=0.0, ys_full=0.0, h1=ho + T, kh=1.0, ys_pier=0.0, y2=y1, h2=ho, v2=v1, fr2=0.0,
                 t_eff=T, apc_star=apc, ys_pc=0.0, h3=ho, y3=y1, v3=v1, fr3=0.0, ksp=1.0, km=1.0,
                 apg=0.0, khpg=0.0, ys_pg=0.0, ys_total=0.0, case="TH0",
                 note="Trụ khô / không có dòng chảy -> ys = 0")
        if y1 <= 0.05 or v1 <= 0:
            return r
        fr1 = v1 / math.sqrt(G * y1)
        ys_full = 2.0 * k1 * k2 * k3 * kw * (a ** 0.65) * (y1 ** 0.35) * (fr1 ** 0.43)
        lim = (2.4 if fr1 <= 0.8 else 3.0) * a

        def limit(x):
            return min(x, lim) if capped else x

        h1 = ho + T
        r.update(fr1=fr1, ys_full=ys_full, h1=h1)
        if h1 <= 0:
            ys_p = limit(ys_full)
            r.update(ys_pier=ys_p, ys_total=ys_p, case="TH1",
                     note=f"TH1: đỉnh bệ dưới đáy đã hạ (h1={h1:.2f}m <= 0) -> xói như trụ đơn bề rộng a")
            return r

        kh = HEC18Calculations.kh_pier_stem(h1, a, f)
        ys_pier = limit(kh * ys_full)
        y2 = y1 + 0.5 * ys_pier
        h2 = ho + 0.5 * ys_pier
        v2 = v1 * y1 / y2
        fr2 = v2 / math.sqrt(G * y2)
        t_eff = T + min(0.0, h2)
        apc_star = HEC18Calculations.equivalent_width_pilecap(max(0.0, h2), y2, t_eff, apc)
        ys_pc = 2.0 * k1 * k2 * k3 * (apc_star ** 0.65) * (y2 ** 0.35) * (fr2 ** 0.43)

        h3 = ho + 0.5 * ys_pier + 0.5 * ys_pc
        y3 = y1 + 0.5 * ys_pier + 0.5 * ys_pc
        r.update(kh=kh, ys_pier=ys_pier, y2=y2, h2=h2, v2=v2, fr2=fr2, t_eff=t_eff,
                 apc_star=apc_star, ys_pc=ys_pc, h3=h3, y3=y3)
        if h3 <= 0:
            r.update(ys_total=ys_pier + ys_pc, case="TH2",
                     note=f"TH2: nhóm cọc còn chôn trong đất (h3={h3:.2f}m <= 0) -> yspg = 0")
            return r

        v3 = v1 * y1 / y3
        fr3 = v3 / math.sqrt(G * y3)
        ksp, km, apg, khpg = HEC18Calculations.pile_group_factors(ap, S, m, n, aproj, h3, y3)
        ys_pg = khpg * 2.0 * k1 * 1.0 * k3 * (apg ** 0.65) * (y3 ** 0.35) * (fr3 ** 0.43)
        r.update(v3=v3, fr3=fr3, ksp=ksp, km=km, apg=apg, khpg=khpg, ys_pg=ys_pg,
                 ys_total=ys_pier + ys_pc + ys_pg, case="TH3",
                 note=f"TH3: lộ cả bệ & cọc (h3={h3:.2f}m > 0) -> CÓ XÓI CỌC")
        return r

    # ------------------------------ XÓI CO HẸP -----------------------------
    @staticmethod
    def contraction_scour(q, y1, v1, w1, w2, d50_m, s1, omega):
        w1 = max(w1, 1e-6)
        w2 = max(w2, 1e-6)
        vc = HEC18Calculations.critical_velocity_vc(y1, d50_m)
        v_star = math.sqrt(max(0.0, G * y1 * s1))
        ratio_vw = v_star / omega if omega > 0 else 1.0
        k1_l, k1_desc = HEC18Tables.get_laursen_k1(ratio_vw)
        dm = 1.25 * d50_m
        y2_cw = ((0.025 * q ** 2) / ((dm ** (2.0 / 3.0)) * (w2 ** 2))) ** (3.0 / 7.0)
        y2_lb = y1 * (w1 / w2) ** k1_l
        note = ""
        if v1 > vc:
            mode = "Xói nước đục"
            y2 = y2_lb
            if d50_m >= 0.02 and y2_cw < y2_lb:
                y2 = y2_cw
                note = "D50>=20mm: lấy min(live-bed, clear-water)"
        else:
            mode = "Xói nước trong"
            y2 = y2_cw
        return dict(vc=vc, v_star=v_star, ratio_vw=ratio_vw, k1=k1_l, k1_desc=k1_desc, dm=dm,
                    mode=mode, y2=y2, ysc=max(0.0, y2 - y1), note=note)

    # --------------------------- MỐ CẦU (FROEHLICH & HIRE) -----------------
    @staticmethod
    def abutment_scour(ya, ve, l_prime, k1_abut, theta_deg=90.0):
        """
        HEC-18 (2012) Chapter 8 & Biểu mẫu xói mố cầu:
        yx = 2.27 * K1 * K2 * (L')^0.43 * ya^0.57 * Fr1^0.61 + ya
        Khi L'/ya > 25: áp dụng HIRE: ys = 4 * ya * Fr^0.33 * (K1/0.55) * K2
        """
        if ya <= 0.05 or l_prime <= 0:
            return dict(fr=0.0, k2=1.0, theta=theta_deg, ys=0.0, method="-")

        fr = max(0.0, ve) / math.sqrt(G * ya)
        theta = max(10.0, min(170.0, theta_deg))
        k2 = (theta / 90.0) ** 0.13
        ratio = l_prime / ya

        if ratio > 25.0:
            ys = 4.0 * ya * (fr ** 0.33) * (k1_abut / 0.55) * k2
            method = "HIRE (L'/ya > 25)"
        else:
            # Phương trình Froehlich chuẩn HEC-18
            ys = 2.27 * k1_abut * k2 * (l_prime ** 0.43) * (ya ** 0.57) * (fr ** 0.61) + ya
            method = "Froehlich"
        return dict(fr=fr, k2=k2, theta=theta, ys=max(0.0, ys), method=method)


# =============================================================================
# 3. GIAO DIỆN CHÍNH & ĐIỀU HÀNH HỆ THỐNG
# =============================================================================
class MainScourApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEC-18 BRIDGE SCOUR SYSTEM PRO - v3.0 (PHẦN MỀM TÍNH TOÁN XÓI MỐ & TRỤ)")
        self.geometry("1440x940")
        self.minsize(1220, 780)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.project = {
            "project_name": "Dự án Nâng cấp Giao thông Vùng Đồng Bằng",
            "bridge_name": "Cầu Phú Kiểng",
            "river_name": "Sông Phú Kiểng",
            "frequency_p": "1%",
            "engineer": "KS. Thủy Lực Cầu Đường",
            "htk": 3.81,
            "qtk": 3902.0,
            "skew": 0.0,
            "s1": 0.000005,
            "d50": 0.025,
            "omega": 0.022,
            "y_deg": 0.50,
            "n_manning": 0.025,
            "k3_type": HEC18Tables.DEFAULT_K3,
            "k1_type": HEC18Tables.DEFAULT_PIER_K1,
            "d84": 0.0,
            "w1_up": 0.0,
            "cross_section": [],
            "piers_detail": [],       # Chỉ lưu TRỤ (T1, T2...)
            "abutments_detail": []     # Chỉ lưu MỐ (M1, M2...)
        }

        self._project_defaults = copy.deepcopy(self.project)
        self.calc_warnings = []
        self.hq_data = []
        self.vh_data = []
        self.scour_results = []
        self.t1_entries = {}

        self._build_menu()
        self._build_header_banner()
        self._build_tabs()
        self._load_sample_data()

    def _build_menu(self):
        menubar = tk.Menu(self)

        menu_proj = tk.Menu(menubar, tearoff=0)
        menu_proj.add_command(label="Tạo Dự Án Mới", command=self.action_new_project)
        menu_proj.add_command(label="Mở File Dự Án (*.json)...", command=self.action_open_project)
        menu_proj.add_command(label="Lưu Hồ Sơ Dự Án (*.json)...", command=self.action_save_project)
        menu_proj.add_separator()
        menu_proj.add_command(label="Thay Đổi Tên Cầu & Dự Án...", command=self.dialog_edit_metadata)
        menu_proj.add_separator()
        menu_proj.add_command(label="Thoát Phần Mềm", command=self.destroy)
        menubar.add_cascade(label="Hồ Sơ Dự Án", menu=menu_proj)

        menu_data = tk.Menu(menubar, tearoff=0)
        menu_data.add_command(label="Nhập Mặt Cắt Từ File Excel...", command=self.action_import_excel)
        menu_data.add_command(label="Xuất Dữ Liệu Mặt Cắt Ra Excel...", command=self.action_export_excel)
        menu_data.add_command(label="Đảo Cột (CĐTN <-> Khoảng Cách)", command=self.swap_columns_manual)
        menu_data.add_separator()
        menu_data.add_command(label="Xuất Báo Cáo Thuyết Minh (*.txt)...", command=self.action_export_report)
        menubar.add_cascade(label="Dữ Liệu & Excel", menu=menu_data)

        menu_cfg = tk.Menu(menubar, tearoff=0)
        menu_cfg.add_command(label="📐 Cấu Hình Bệ & Cọc Cho TRỤ CẦU...", command=self.dialog_edit_piers_detail)
        menu_cfg.add_command(label="🏛 Cấu Hình Thủy Lực Cho MỐ CẦU (Froehlich)...", command=self.dialog_edit_abutments_detail)
        menubar.add_cascade(label="Cấu Hình Móng & Mố Trụ", menu=menu_cfg)

        menu_calc = tk.Menu(menubar, tearoff=0)
        menu_calc.add_command(label="Tính Đường Quan Hệ H-Q / H-V", command=self.calc_hq_curve)
        menu_calc.add_command(label="Chạy Tính Toàn Bộ Hệ Thống Xói (HEC-18)", command=self.run_full_system)
        menubar.add_cascade(label="Thực Thi Tính Toán", menu=menu_calc)

        self.config(menu=menubar)

    def _build_header_banner(self):
        f_top = tk.Frame(self, bg="#0E4D92", height=48)
        f_top.pack(fill=tk.X, side=tk.TOP)

        self.lbl_title = tk.Label(
            f_top,
            text=f"DỰ ÁN: {self.project['project_name'].upper()} | CÔNG TRÌNH: {self.project['bridge_name'].upper()}",
            font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF",
            bg="#0E4D92"
        )
        self.lbl_title.pack(side=tk.LEFT, padx=16, pady=8)

        btn_run = tk.Button(
            f_top,
            text="▶ CHẠY TÍNH TOÁN TOÀN BỘ (HEC-18)",
            bg="#FFB300",
            fg="#000000",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            relief=tk.RAISED,
            cursor="hand2",
            command=self.run_full_system
        )
        btn_run.pack(side=tk.RIGHT, padx=12, pady=6)

        btn_abut = tk.Button(
            f_top,
            text="🏛 Cấu Hình MỐ CẦU",
            bg="#FFE082",
            fg="#BF360C",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            relief=tk.GROOVE,
            cursor="hand2",
            command=self.dialog_edit_abutments_detail
        )
        btn_abut.pack(side=tk.RIGHT, padx=6, pady=6)

        btn_pier = tk.Button(
            f_top,
            text="📐 Cấu Hình BỆ & CỌC TRỤ",
            bg="#E3F2FD",
            fg="#0D47A1",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            relief=tk.GROOVE,
            cursor="hand2",
            command=self.dialog_edit_piers_detail
        )
        btn_pier.pack(side=tk.RIGHT, padx=6, pady=6)

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        self.tab1 = ttk.Frame(self.nb)
        self.tab2 = ttk.Frame(self.nb)
        self.tab3 = ttk.Frame(self.nb)
        self.tab4 = ttk.Frame(self.nb)
        self.tab5 = ttk.Frame(self.nb)
        self.tab6 = ttk.Frame(self.nb)
        self.tab7 = ttk.Frame(self.nb)
        self.tab8 = ttk.Frame(self.nb)

        self.nb.add(self.tab1, text="1. Mặt Cắt & Bố Trí Mố Trụ")
        self.nb.add(self.tab2, text="2. Quan Hệ H-Q / H-V & Htk")
        self.nb.add(self.tab3, text="3. Phân Phối Lưu Lượng (PPLL)")
        self.nb.add(self.tab4, text="4. Choán Dòng (Vcau)")
        self.nb.add(self.tab5, text="5. Nước Dềnh (Denh)")
        self.nb.add(self.tab6, text="6. Xói Co Hẹp (Xoi chung)")
        self.nb.add(self.tab7, text="7. Xói Cục Bộ Mố Trụ (HEC-18)")
        self.nb.add(self.tab8, text="8. Tổng Hợp & Đồ Thị Scour Prism")

        self._init_tab1()
        self._init_tab2()
        self._init_tab3()
        self._init_tab4()
        self._init_tab5()
        self._init_tab6()
        self._init_tab7()
        self._init_tab8()

    # =========================================================================
    # TAB 1: MẶT CẮT & THÔNG SỐ CẦU
    # =========================================================================
    def _init_tab1(self):
        pane = ttk.PanedWindow(self.tab1, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        f_left = ttk.LabelFrame(pane, text="Thông Số Thủy Lực & Lòng Sông")
        pane.add(f_left, weight=1)

        inputs = [
            ("Mực nước lũ thiết kế Htk (m):", "htk"),
            ("Lưu lượng lũ thiết kế Qtk (m3/s):", "qtk"),
            ("Góc xiên tim cầu với dòng chảy (°):", "skew"),
            ("Độ dốc thủy lực lòng sông S1 (m/m):", "s1"),
            ("Đường kính hạt trung vị D50 (mm):", "d50"),
            ("Đường kính hạt D84 (mm) [0 = 2×D50]:", "d84"),
            ("Vận tốc lắng chìm hạt w (m/s):", "omega"),
            ("Hạ thấp lòng dẫn dài hạn y_deg (m):", "y_deg"),
            ("Hệ số nhám Manning nc lòng sông:", "n_manning"),
            ("Bề rộng lòng chủ thượng lưu W1 (m) [0 = tự tính]:", "w1_up"),
        ]

        for r, (txt, k) in enumerate(inputs):
            ttk.Label(f_left, text=txt).grid(row=r, column=0, sticky=tk.W, padx=8, pady=4)
            e = ttk.Entry(f_left, width=15)
            e.insert(0, str(self.project[k]))
            e.grid(row=r, column=1, sticky=tk.W, padx=8, pady=4)
            self.t1_entries[k] = e

        ttk.Label(f_left, text="Tình trạng đáy sông K3:").grid(row=len(inputs), column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_k3 = ttk.Combobox(f_left, values=list(HEC18Tables.PIER_K3.keys()), state="readonly", width=35)
        self.cb_k3.set(self.project["k3_type"])
        self.cb_k3.grid(row=len(inputs), column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Label(f_left, text="Dạng mũi trụ mặc định K1:").grid(row=len(inputs)+1, column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_k1 = ttk.Combobox(f_left, values=list(HEC18Tables.PIER_K1.keys()), state="readonly", width=35)
        self.cb_k1.set(self.project["k1_type"])
        self.cb_k1.grid(row=len(inputs)+1, column=1, sticky=tk.W, padx=8, pady=4)

        f_btn = ttk.Frame(f_left)
        f_btn.grid(row=len(inputs)+2, column=0, columnspan=2, pady=10, padx=8, sticky=tk.EW)

        ttk.Button(f_btn, text="▶ CHẠY TÍNH TOÁN TOÀN BỘ", command=self.run_full_system).pack(fill=tk.X, pady=3)
        ttk.Button(f_btn, text="🏛 CẤU HÌNH THỦY LỰC MỐ CẦU (Froehlich)...", command=self.dialog_edit_abutments_detail).pack(fill=tk.X, pady=3)
        ttk.Button(f_btn, text="📐 CẤU HÌNH BỆ & CỌC TRỤ (CAD)...", command=self.dialog_edit_piers_detail).pack(fill=tk.X, pady=3)
        ttk.Button(f_btn, text="Nhập Mặt Cắt Từ File Excel...", command=self.action_import_excel).pack(fill=tk.X, pady=3)
        ttk.Button(f_btn, text="ĐẢO CỘT (CĐTN <-> Khoảng Cách)", command=self.swap_columns_manual).pack(fill=tk.X, pady=3)

        f_right = ttk.LabelFrame(pane, text="Bảng Tọa Độ Mặt Cắt Sông & Bố Trí Mố Trụ (Sheet hinh thai)")
        pane.add(f_right, weight=3)

        f_fast = ttk.Frame(f_right)
        f_fast.pack(fill=tk.X, padx=5, pady=4)

        ttk.Label(f_fast, text="Tên mố/trụ:").grid(row=0, column=0, padx=2)
        self.eq_name = ttk.Entry(f_fast, width=9)
        self.eq_name.grid(row=0, column=1, padx=2)

        ttk.Label(f_fast, text="CĐTN(m):").grid(row=0, column=2, padx=2)
        self.eq_z = ttk.Entry(f_fast, width=7)
        self.eq_z.grid(row=0, column=3, padx=2)

        ttk.Label(f_fast, text="L chéo(m):").grid(row=0, column=4, padx=2)
        self.eq_l = ttk.Entry(f_fast, width=7)
        self.eq_l.grid(row=0, column=5, padx=2)

        ttk.Label(f_fast, text="Bề rộng a/L'(m):").grid(row=0, column=6, padx=2)
        self.eq_a = ttk.Entry(f_fast, width=6)
        self.eq_a.insert(0, "2.0")
        self.eq_a.grid(row=0, column=7, padx=2)

        ttk.Label(f_fast, text="Dài L(m):").grid(row=0, column=8, padx=2)
        self.eq_len = ttk.Entry(f_fast, width=6)
        self.eq_len.insert(0, "1.5")
        self.eq_len.grid(row=0, column=9, padx=2)

        ttk.Button(f_fast, text="Thêm Điểm", command=self.add_point_tab1).grid(row=0, column=10, padx=2)
        ttk.Button(f_fast, text="Sửa Điểm", command=self.edit_selected_point_tab1).grid(row=0, column=11, padx=2)
        ttk.Button(f_fast, text="Xóa Điểm", command=self.del_point_tab1).grid(row=0, column=12, padx=2)

        cols = ("STT", "Tên Mố/Trụ", "Cao Độ CĐTN (m)", "L chéo (m)", "L ngang (m)", "Độ sâu h (m)", "Phân Loại", "Kích thước a (m)", "Dài L / L' (m)")
        self.tree_tab1 = ttk.Treeview(f_right, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree_tab1.heading(c, text=c)
            self.tree_tab1.column(c, anchor=tk.CENTER, width=95)

        s_y = ttk.Scrollbar(f_right, orient=tk.VERTICAL, command=self.tree_tab1.yview)
        self.tree_tab1.configure(yscrollcommand=s_y.set)
        self.tree_tab1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        s_y.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        self.tree_tab1.bind("<<TreeviewSelect>>", self._on_tab1_select_row)

    def _on_tab1_select_row(self, event):
        sel = self.tree_tab1.selection()
        if not sel:
            return
        vals = self.tree_tab1.item(sel[0], "values")
        if vals:
            self.eq_name.delete(0, tk.END)
            self.eq_name.insert(0, vals[1])
            self.eq_z.delete(0, tk.END)
            self.eq_z.insert(0, vals[2])
            self.eq_l.delete(0, tk.END)
            self.eq_l.insert(0, vals[3])
            self.eq_a.delete(0, tk.END)
            self.eq_a.insert(0, vals[7])
            self.eq_len.delete(0, tk.END)
            self.eq_len.insert(0, vals[8])

    def edit_selected_point_tab1(self):
        sel = self.tree_tab1.selection()
        if not sel:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn dòng cần sửa trên bảng!")
            return
        try:
            idx = self.tree_tab1.index(sel[0])
            name = self.eq_name.get().strip()
            z = float(self.eq_z.get())
            l = float(self.eq_l.get())
            a = float(self.eq_a.get())
            len_p = float(self.eq_len.get())
            p_type = "Điểm tự nhiên" if not name else ("Mố cầu" if is_abut_name(name) else "Trụ đơn")
            k1 = 1.0 if is_abut_name(name) else 1.1

            self.project["cross_section"][idx] = [idx + 1, name, z, l, p_type, a, len_p, k1]
            self.sync_all_details()
            self._refresh_tab1_table()
            messagebox.showinfo("Thành công", f"Đã cập nhật điểm STT {idx + 1} ({name})!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Vui lòng nhập đúng số liệu! Chi tiết: {e}")

    def add_point_tab1(self):
        try:
            name = self.eq_name.get().strip()
            z = float(self.eq_z.get())
            l = float(self.eq_l.get())
            a = float(self.eq_a.get())
            len_p = float(self.eq_len.get())
            p_type = "Điểm tự nhiên" if not name else ("Mố cầu" if is_abut_name(name) else "Trụ đơn")
            k1 = 1.0 if is_abut_name(name) else 1.1
            stt = len(self.project["cross_section"]) + 1
            self.project["cross_section"].append([stt, name, z, l, p_type, a, len_p, k1])
            self.sync_all_details()
            self._refresh_tab1_table()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Vui lòng nhập đúng số liệu điểm! Chi tiết: {e}")

    def del_point_tab1(self):
        sel = self.tree_tab1.selection()
        if not sel:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn dòng cần xóa!")
            return
        idx = self.tree_tab1.index(sel[0])
        del self.project["cross_section"][idx]
        for i, r in enumerate(self.project["cross_section"], start=1):
            r[0] = i
        self.sync_all_details()
        self._refresh_tab1_table()

    # =========================================================================
    # ĐỒNG BỘ THÔNG SỐ: TÁCH RIÊNG TRỤ VÀ MỐ
    # =========================================================================
    def sync_all_details(self):
        self.sync_piers_detail()
        self.sync_abutments_detail()

    def sync_piers_detail(self):
        """Đồng bộ danh sách TRỤ CẦU (loại bỏ hoàn toàn các Mố)"""
        existing_map = {d["name"]: d for d in self.project.get("piers_detail", [])}
        synced_piers = []

        for r in self.project.get("cross_section", []):
            name = str(r[1]).strip()
            if name and not is_abut_name(name):
                cdtn = float(r[2])
                a_val = float(r[5]) if float(r[5]) > 0 else 2.0
                L_val = float(r[6]) if float(r[6]) > 0 else 1.5

                if name in existing_map:
                    d = existing_map[name]
                    d["cdtn"] = cdtn
                    if a_val > 0:
                        d["apier"] = a_val
                    if L_val > 0:
                        d["Lpier"] = L_val
                    z_val = d.get("z_be", d.get("z_day_be", cdtn + d.get("ho", -1.40)))
                    d["z_be"] = z_val
                    d["z_day_be"] = z_val
                    d["ho"] = round(z_val - cdtn, 3)
                    synced_piers.append(d)
                else:
                    default_z_be = cdtn - 1.40
                    d = {
                        "name": name,
                        "cdtn": cdtn,
                        "z_be": default_z_be,
                        "z_day_be": default_z_be,
                        "ho": -1.40,
                        "apier": a_val,
                        "Lpier": L_val,
                        "apc": max(6.0, a_val * 3.0),
                        "Lpc": 13.32,
                        "T": 2.0,
                        "f": 1.85,
                        "ap": 1.20,
                        "S": 4.20,
                        "m": 2,
                        "n": 3,
                        "aproj": 3.60
                    }
                    synced_piers.append(d)
        self.project["piers_detail"] = synced_piers

    def sync_abutments_detail(self):
        """Đồng bộ danh sách MỐ CẦU với các thông số thủy lực chuyên biệt"""
        existing_map = {d["name"]: d for d in self.project.get("abutments_detail", [])}
        synced_abuts = []
        htk = float(self.project.get("htk", 3.81))

        for r in self.project.get("cross_section", []):
            name = str(r[1]).strip()
            if name and is_abut_name(name):
                cdtn = float(r[2])
                l_prime_val = float(r[6]) if float(r[6]) > 0 else (float(r[5]) if float(r[5]) > 0 else 1.70)
                ya_default = max(0.1, round(htk - cdtn, 2))

                if name in existing_map:
                    d = existing_map[name]
                    d["cdtn"] = cdtn
                    if "L_prime" not in d or d["L_prime"] <= 0:
                        d["L_prime"] = l_prime_val
                    if "ya" not in d or d["ya"] <= 0:
                        d["ya"] = ya_default
                    synced_abuts.append(d)
                else:
                    d = {
                        "name": name,
                        "cdtn": cdtn,
                        "ya": ya_default,
                        "Qe": 24.39 if "1" in name else 55.64,
                        "Ae": 8.19 if "1" in name else 6.80,
                        "L_prime": l_prime_val,
                        "k1_type": HEC18Tables.DEFAULT_ABUT_K1,
                        "theta": 90.0,
                        "note": "Nhập từ hồ sơ thủy lực bãi tràn"
                    }
                    synced_abuts.append(d)
        self.project["abutments_detail"] = synced_abuts

    # =========================================================================
    # DIALOG CẤU HÌNH THỦY LỰC MỐ CẦU (FROEHLICH & HIRE)
    # =========================================================================
    def dialog_edit_abutments_detail(self):
        self.sync_abutments_detail()

        dlg = tk.Toplevel(self)
        dlg.title("Cấu Hình Thông Số Thủy Lực Mố Cầu (Froehlich / HIRE - HEC-18 Chapter 8)")
        dlg.geometry("1180x680")
        dlg.minsize(1050, 600)
        dlg.grab_set()

        pane = ttk.PanedWindow(dlg, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        f_left = ttk.Frame(pane)
        pane.add(f_left, weight=3)

        lbl_guide = tk.Label(
            f_left,
            text="CHỌN MỐ CẦU TRÊN BẢNG, NHẬP CÁC THÔNG SỐ VÀ BẤM 'LƯU MỐ ĐANG CHỌN'",
            font=("Segoe UI", 9, "bold"),
            fg="#BF360C"
        )
        lbl_guide.pack(pady=4)

        f_tbl = ttk.Frame(f_left)
        f_tbl.pack(fill=tk.X, padx=4, pady=2)

        cols = ("Tên Mố", "CĐTN (m)", "ya (m)", "Qe (m3/s)", "Ae (m2)", "Ve (m/s)", "Fr1", "L' (m)", "Dạng mố K1", "θ (°)", "K2")
        tree_ab = ttk.Treeview(f_tbl, columns=cols, show="headings", height=5)
        for c in cols:
            tree_ab.heading(c, text=c)
            tree_ab.column(c, anchor=tk.CENTER, width=70)
        tree_ab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        s_y = ttk.Scrollbar(f_tbl, orient=tk.VERTICAL, command=tree_ab.yview)
        tree_ab.configure(yscrollcommand=s_y.set)
        s_y.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_table():
            tree_ab.delete(*tree_ab.get_children())
            for d in self.project.get("abutments_detail", []):
                ya = float(d.get("ya", 1.0))
                qe = float(d.get("Qe", 0.0))
                ae = float(d.get("Ae", 1.0))
                ve = qe / ae if ae > 0 else 0.0
                fr = ve / math.sqrt(G * ya) if ya > 0 else 0.0
                k1_val = HEC18Tables.ABUT_K1.get(d.get("k1_type", HEC18Tables.DEFAULT_ABUT_K1), (1.0,))[0]
                th = float(d.get("theta", 90.0))
                k2 = (th / 90.0) ** 0.13
                tree_ab.insert("", tk.END, values=(
                    d["name"], f"{d['cdtn']:.2f}", f"{ya:.2f}", f"{qe:.2f}", f"{ae:.2f}",
                    f"{ve:.2f}", f"{fr:.3f}", f"{d['L_prime']:.2f}", f"{k1_val:.2f}", f"{th:.1f}", f"{k2:.3f}"
                ))

        refresh_table()

        # FORM NHẬP LIỆU CHO MỐ
        f_form = ttk.LabelFrame(f_left, text="Thông Số Thủy Lực Nhập Liệu Của Mố Đang Chọn")
        f_form.pack(fill=tk.BOTH, expand=True, padx=4, pady=6)

        ab_vars = {
            "name": tk.StringVar(), "cdtn": tk.StringVar(), "ya": tk.StringVar(),
            "Qe": tk.StringVar(), "Ae": tk.StringVar(), "L_prime": tk.StringVar(),
            "k1_type": tk.StringVar(), "theta": tk.StringVar(),
            "ve_disp": tk.StringVar(), "fr_disp": tk.StringVar(), "k2_disp": tk.StringVar(),
            "ys_preview": tk.StringVar()
        }

        # Dòng 0: Tên & CĐTN
        ttk.Label(f_form, text="Tên mố cầu:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Label(f_form, textvariable=ab_vars["name"], font=("Segoe UI", 10, "bold"), foreground="red").grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Cao độ tự nhiên CĐTN (m):").grid(row=0, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Label(f_form, textvariable=ab_vars["cdtn"], font=("Segoe UI", 9, "bold")).grid(row=0, column=3, sticky=tk.W, padx=6, pady=4)

        # Dòng 1: ya và L'
        ttk.Label(f_form, text="Chiều sâu nước bãi tràn ya (m):").grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["ya"], width=12).grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Chiều dài mố/nền cản dòng L' (m):").grid(row=1, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["L_prime"], width=12).grid(row=1, column=3, sticky=tk.W, padx=6, pady=4)

        # Dòng 2: Qe và Ae
        ttk.Label(f_form, text="Dòng chảy bị chặn Qe (m3/s):").grid(row=2, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["Qe"], width=12).grid(row=2, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Diện tích bị chặn Ae (m2):").grid(row=2, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["Ae"], width=12).grid(row=2, column=3, sticky=tk.W, padx=6, pady=4)

        # Dòng 3: Dạng mố K1 và Góc xiên theta
        ttk.Label(f_form, text="Dạng mố K1 (Froehlich):").grid(row=3, column=0, sticky=tk.W, padx=6, pady=4)
        cb_k1_ab = ttk.Combobox(f_form, textvariable=ab_vars["k1_type"], values=list(HEC18Tables.ABUT_K1.keys()), state="readonly", width=36)
        cb_k1_ab.grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Góc xiên θ (°):").grid(row=4, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["theta"], width=12).grid(row=4, column=1, sticky=tk.W, padx=6, pady=4)

        # Dòng 4: Kết quả nội bộ tự tính
        f_res_calc = ttk.LabelFrame(f_form, text="Thông Số Thủy Lực Suy Ra Tự Động")
        f_res_calc.grid(row=5, column=0, columnspan=4, sticky=tk.EW, padx=6, pady=6)

        ttk.Label(f_res_calc, text="Vận tốc Ve = Qe/Ae:").grid(row=0, column=0, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["ve_disp"], font=("Segoe UI", 9, "bold"), foreground="blue").grid(row=0, column=1, padx=6, pady=2)

        ttk.Label(f_res_calc, text="Hệ số Froude Fr1:").grid(row=0, column=2, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["fr_disp"], font=("Segoe UI", 9, "bold"), foreground="blue").grid(row=0, column=3, padx=6, pady=2)

        ttk.Label(f_res_calc, text="Hệ số góc K2:").grid(row=0, column=4, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["k2_disp"], font=("Segoe UI", 9, "bold"), foreground="blue").grid(row=0, column=5, padx=6, pady=2)

        ttk.Label(f_res_calc, text="Chiều sâu xói ys dự kiến:").grid(row=1, column=0, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["ys_preview"], font=("Segoe UI", 10, "bold"), foreground="red").grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=6, pady=2)

        def recompute_preview(*args):
            try:
                ya = float(ab_vars["ya"].get())
                qe = float(ab_vars["Qe"].get())
                ae = float(ab_vars["Ae"].get())
                lp = float(ab_vars["L_prime"].get())
                th = float(ab_vars["theta"].get())
                k1_val = HEC18Tables.ABUT_K1.get(ab_vars["k1_type"].get(), (1.0,))[0]

                ve = qe / ae if ae > 0 else 0.0
                fr = ve / math.sqrt(G * ya) if ya > 0 else 0.0
                k2 = (th / 90.0) ** 0.13
                res = HEC18Calculations.abutment_scour(ya, ve, lp, k1_val, th)

                ab_vars["ve_disp"].set(f"{ve:.2f} m/s")
                ab_vars["fr_disp"].set(f"{fr:.3f}")
                ab_vars["k2_disp"].set(f"{k2:.3f}")
                ab_vars["ys_preview"].set(f"{res['ys']:.2f} m ({res['method']})")
            except Exception:
                ab_vars["ve_disp"].set("...")
                ab_vars["fr_disp"].set("...")
                ab_vars["k2_disp"].set("...")
                ab_vars["ys_preview"].set("...")

        for k in ["ya", "Qe", "Ae", "L_prime", "theta", "k1_type"]:
            ab_vars[k].trace_add("write", recompute_preview)

        def on_select_ab(event):
            sel = tree_ab.selection()
            if not sel:
                return
            v = tree_ab.item(sel[0], "values")
            name = v[0]
            ab_obj = next((d for d in self.project["abutments_detail"] if d["name"] == name), None)
            if ab_obj:
                ab_vars["name"].set(ab_obj["name"])
                ab_vars["cdtn"].set(f"{ab_obj['cdtn']:.2f}")
                ab_vars["ya"].set(str(ab_obj.get("ya", 1.0)))
                ab_vars["Qe"].set(str(ab_obj.get("Qe", 20.0)))
                ab_vars["Ae"].set(str(ab_obj.get("Ae", 8.0)))
                ab_vars["L_prime"].set(str(ab_obj.get("L_prime", 1.70)))
                ab_vars["k1_type"].set(ab_obj.get("k1_type", HEC18Tables.DEFAULT_ABUT_K1))
                ab_vars["theta"].set(str(ab_obj.get("theta", 90.0)))
                recompute_preview()

        tree_ab.bind("<<TreeviewSelect>>", on_select_ab)

        children = tree_ab.get_children()
        if children:
            tree_ab.selection_set(children[0])
            on_select_ab(None)

        def save_current_ab():
            name = ab_vars["name"].get()
            if not name:
                messagebox.showwarning("Cảnh báo", "Vui lòng chọn một mố từ danh sách trước!")
                return
            for d in self.project["abutments_detail"]:
                if d["name"] == name:
                    try:
                        d["ya"] = float(ab_vars["ya"].get())
                        d["Qe"] = float(ab_vars["Qe"].get())
                        d["Ae"] = float(ab_vars["Ae"].get())
                        d["L_prime"] = float(ab_vars["L_prime"].get())
                        d["theta"] = float(ab_vars["theta"].get())
                        d["k1_type"] = ab_vars["k1_type"].get()
                        refresh_table()
                        messagebox.showinfo("Thành công", f"Đã lưu thành công thông số thủy lực cho {name}!")
                    except Exception as e:
                        messagebox.showerror("Lỗi", f"Vui lòng nhập đúng định dạng số! Chi tiết: {e}")
                    break

        f_act = ttk.Frame(f_left)
        f_act.pack(fill=tk.X, padx=4, pady=6)
        ttk.Button(f_act, text="💾 LƯU THÔNG SỐ MỐ ĐANG CHỌN", command=save_current_ab).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_act, text="Đóng Cửa Sổ", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

        # PHẦN HƯỚNG DẪN & SƠ ĐỒ HÌNH HỌC HEC-18
        f_right = ttk.LabelFrame(pane, text="Sơ Đồ Minh Họa Mố Bãi Tràn (HEC-18)")
        pane.add(f_right, weight=2)

        fig_ab = Figure(figsize=(4.5, 3.2), dpi=100)
        fig_ab.patch.set_facecolor('#F8F9FA')
        ax = fig_ab.add_subplot(1, 1, 1)

        ax.plot([0, 2, 4, 8], [2.8, 1.0, 0.0, 0.0], color="#795548", linewidth=2.5)
        ax.fill_between([0, 2, 4, 8], [-1, -1, -1, -1], [2.8, 1.0, 0.0, 0.0], color="#D7CCC8", alpha=0.5)
        ax.axhline(2.5, color="#0288D1", linestyle="--", linewidth=1.5)
        ax.text(5.5, 2.6, "Mực nước Htk", color="#0288D1", fontsize=8, fontweight="bold")

        ax.add_patch(patches.Rectangle((0, 2.5), 2.2, 1.2, facecolor="#78909C", edgecolor="#37474F"))
        ax.text(1.1, 3.1, "Nền đường đầu cầu", ha="center", fontsize=7, color="white", fontweight="bold")

        ax.add_patch(patches.Rectangle((2.2, 1.2), 0.8, 2.5, facecolor="#B0BEC5", edgecolor="#263238", linewidth=1.2))
        ax.text(2.6, 2.4, "Mố", ha="center", fontsize=8, fontweight="bold")

        ax.annotate("", xy=(0, 3.8), xytext=(2.6, 3.8), arrowprops=dict(arrowstyle="<->", color="red", lw=1.2))
        ax.text(1.3, 3.95, "L' (Chiều dài cản dòng)", ha="center", color="red", fontsize=8, fontweight="bold")

        ax.annotate("", xy=(2.6, 1.0), xytext=(2.6, 2.5), arrowprops=dict(arrowstyle="<->", color="blue", lw=1.2))
        ax.text(2.8, 1.75, "ya", color="blue", fontsize=8, fontweight="bold")

        ax.annotate("Dòng chảy bãi tràn Qe, Ae ->", xy=(1.5, 1.8), xytext=(0.2, 1.8),
                    arrowprops=dict(facecolor="orange", edgecolor="orange", width=2, headwidth=6))

        ax.set_xlim(-0.2, 7.5)
        ax.set_ylim(-0.5, 4.4)
        ax.axis("off")

        canvas_ab = FigureCanvasTkAgg(fig_ab, master=f_right)
        canvas_ab.get_tk_widget().pack(fill=tk.X, padx=4, pady=4)
        canvas_ab.draw()

        txt_ab_doc = tk.Text(f_right, height=10, bg="#FFFFFF", font=("Segoe UI", 9), padx=6, pady=4)
        txt_ab_doc.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        doc_content = """❖ HƯỚNG DẪN NHẬP SỐ LIỆU MỐ THEO HEC-18 (Froehlich):
1. ya (m): Chiều sâu nước trung bình trên bãi tràn trước mố. Mặc định lấy Htk - CĐTN.
2. L' (m): Chiều dài phần mố và nền đường nhô ra cản trở dòng chảy bãi tràn.
3. Qe (m3/s): Phần lưu lượng bãi tràn bị mố và đường đầu cầu chặn lại.
4. Ae (m2): Diện tích mặt cắt ướt thượng lưu của dòng chảy bị chặn.
5. Ve = Qe / Ae: Vận tốc trung bình qua vùng bị chặn.
6. K1: Hệ số dạng mố (1.00 mố thẳng đứng, 0.82 tường cánh, 0.55 mái taluy xiên).
7. θ: Góc của nền đắp với dòng chảy (K2 = (θ/90)^0.13).
"""
        txt_ab_doc.insert(tk.END, doc_content)
        txt_ab_doc.config(state=tk.DISABLED)

    # =========================================================================
    # DIALOG CẤU HÌNH BỆ & CỌC CHO TRỤ CẦU (KHÔNG CHỨA MỐ)
    # =========================================================================
    def dialog_edit_piers_detail(self):
        self.sync_piers_detail()

        dlg = tk.Toplevel(self)
        dlg.title("Cấu Hình Chi Tiết Kích Thước Bệ Đài & Nhóm Cọc Cho Các TRỤ CẦU (HEC-18)")
        dlg.geometry("1300x750")
        dlg.minsize(1150, 680)
        dlg.grab_set()

        pane = ttk.PanedWindow(dlg, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        f_left_side = ttk.Frame(pane)
        pane.add(f_left_side, weight=3)

        lbl_guide = tk.Label(
            f_left_side,
            text="CHỌN TRỤ TRÊN BẢNG, NHẬP THÔNG SỐ VÀ BẤM 'CẬP NHẬT TRỤ ĐANG CHỌN' (BẢNG NÀY CHỈ DÀNH CHO TRỤ CẦU)",
            font=("Segoe UI", 9, "bold"),
            fg="#0D47A1"
        )
        lbl_guide.pack(pady=4)

        f_tree = ttk.Frame(f_left_side)
        f_tree.pack(fill=tk.X, padx=5, pady=2)

        cols = ("Tên Trụ", "CĐTN (m)", "Thân a(m)", "Thân L(m)", "Bệ apc(m)", "Bệ Lpc(m)", "Cao T(m)", "CĐ Đáy Bệ", "ho (m)", "Gờ f(m)", "Cọc ap", "Cự ly S", "Hàng m", "Cột n")
        tree_p = ttk.Treeview(f_tree, columns=cols, show="headings", height=5)
        for c in cols:
            tree_p.heading(c, text=c)
            tree_p.column(c, anchor=tk.CENTER, width=54)

        s_y = ttk.Scrollbar(f_tree, orient=tk.VERTICAL, command=tree_p.yview)
        tree_p.configure(yscrollcommand=s_y.set)
        tree_p.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        s_y.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_dlg_table():
            tree_p.delete(*tree_p.get_children())
            for d in self.project.get("piers_detail", []):
                z_cur = d.get("z_be", d.get("z_day_be", d["cdtn"] + d["ho"]))
                tree_p.insert("", tk.END, values=(
                    d["name"], f"{d['cdtn']:.2f}", f"{d['apier']:.2f}", f"{d['Lpier']:.2f}",
                    f"{d['apc']:.2f}", f"{d['Lpc']:.2f}", f"{d['T']:.2f}", f"{z_cur:.2f}",
                    f"{d['ho']:.2f}", f"{d['f']:.2f}", f"{d['ap']:.2f}", f"{d['S']:.2f}", d["m"], d["n"]
                ))

        refresh_dlg_table()

        f_form = ttk.LabelFrame(f_left_side, text="Thông Số Kích Thước Nhập Liệu Của Trụ Đang Chọn")
        f_form.pack(fill=tk.BOTH, expand=True, padx=5, pady=4)

        f_sub1 = ttk.LabelFrame(f_form, text="1. Thân Trụ (Pier Stem)")
        f_sub1.grid(row=0, column=0, padx=4, pady=3, sticky=tk.NSEW)

        f_sub2 = ttk.LabelFrame(f_form, text="2. Móng Bệ Đài Cọc (Footing)")
        f_sub2.grid(row=0, column=1, padx=4, pady=3, sticky=tk.NSEW)

        f_sub3 = ttk.LabelFrame(f_form, text="3. Nhóm Cọc (Pile Group)")
        f_sub3.grid(row=0, column=2, padx=4, pady=3, sticky=tk.NSEW)

        ent_vars = {
            "name": tk.StringVar(), "cdtn": tk.StringVar(),
            "apier": tk.StringVar(), "Lpier": tk.StringVar(),
            "apc": tk.StringVar(), "Lpc": tk.StringVar(), "T": tk.StringVar(),
            "z_day_be": tk.StringVar(), "ho_display": tk.StringVar(), "f": tk.StringVar(),
            "ap": tk.StringVar(), "S": tk.StringVar(), "m": tk.StringVar(), "n": tk.StringVar(), "aproj": tk.StringVar()
        }

        ttk.Label(f_sub1, text="Tên trụ:").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Label(f_sub1, textvariable=ent_vars["name"], font=("Segoe UI", 9, "bold"), foreground="blue").grid(row=0, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub1, text="Cao độ CĐTN:").grid(row=1, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Label(f_sub1, textvariable=ent_vars["cdtn"]).grid(row=1, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub1, text="Bề rộng thân a (m):").grid(row=2, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub1, textvariable=ent_vars["apier"], width=8).grid(row=2, column=1, padx=3, pady=2)

        ttk.Label(f_sub1, text="Chiều dài thân L (m):").grid(row=3, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub1, textvariable=ent_vars["Lpier"], width=8).grid(row=3, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Bề rộng bệ apc (m):").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["apc"], width=8).grid(row=0, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Chiều dài bệ Lpc (m):").grid(row=1, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["Lpc"], width=8).grid(row=1, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Chiều cao bệ T (m):").grid(row=2, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["T"], width=8).grid(row=2, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Cao độ đáy bệ Z_đáy (m):", font=("Segoe UI", 9, "bold"), foreground="#B71C1C").grid(row=3, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["z_day_be"], width=8).grid(row=3, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="ho = Zđáy-CĐTN:").grid(row=4, column=0, sticky=tk.W, padx=3, pady=2)
        lbl_ho_show = tk.Label(f_sub2, textvariable=ent_vars["ho_display"], font=("Segoe UI", 9, "bold"), fg="#D32F2F")
        lbl_ho_show.grid(row=4, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub2, text="Gờ bệ trước mũi f (m):").grid(row=5, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["f"], width=8).grid(row=5, column=1, padx=3, pady=2)

        def on_z_day_change(*args):
            try:
                z_d = float(ent_vars["z_day_be"].get())
                z_tn = float(ent_vars["cdtn"].get())
                ho_calc = z_d - z_tn
                ent_vars["ho_display"].set(f"{ho_calc:.2f} m")
            except Exception:
                ent_vars["ho_display"].set("...")

        ent_vars["z_day_be"].trace_add("write", on_z_day_change)

        ttk.Label(f_sub3, text="Bề rộng cọc ap (m):").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub3, textvariable=ent_vars["ap"], width=8).grid(row=0, column=1, padx=3, pady=2)

        ttk.Label(f_sub3, text="Cự ly cọc S (m):").grid(row=1, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub3, textvariable=ent_vars["S"], width=8).grid(row=1, column=1, padx=3, pady=2)

        ttk.Label(f_sub3, text="Số hàng cọc m (dọc dòng):").grid(row=2, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub3, textvariable=ent_vars["m"], width=8).grid(row=2, column=1, padx=3, pady=2)

        ttk.Label(f_sub3, text="Số cột cọc n (ngang tim):").grid(row=3, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub3, textvariable=ent_vars["n"], width=8).grid(row=3, column=1, padx=3, pady=2)

        ttk.Label(f_sub3, text="Hình chiếu aproj (m):").grid(row=4, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub3, textvariable=ent_vars["aproj"], width=8).grid(row=4, column=1, padx=3, pady=2)

        def on_select_pier(event):
            sel = tree_p.selection()
            if not sel:
                return
            v = tree_p.item(sel[0], "values")
            ent_vars["name"].set(v[0])
            ent_vars["cdtn"].set(v[1])
            ent_vars["apier"].set(v[2])
            ent_vars["Lpier"].set(v[3])
            ent_vars["apc"].set(v[4])
            ent_vars["Lpc"].set(v[5])
            ent_vars["T"].set(v[6])
            ent_vars["z_day_be"].set(v[7])
            ent_vars["ho_display"].set(f"{float(v[8]):.2f} m")
            ent_vars["f"].set(v[9])
            ent_vars["ap"].set(v[10])
            ent_vars["S"].set(v[11])
            ent_vars["m"].set(v[12])
            ent_vars["n"].set(v[13])
            detail = next((d for d in self.project["piers_detail"] if d["name"] == v[0]), None)
            if detail:
                ent_vars["aproj"].set(str(detail.get("aproj", 3.60)))

        tree_p.bind("<<TreeviewSelect>>", on_select_pier)

        children = tree_p.get_children()
        if children:
            tree_p.selection_set(children[0])
            on_select_pier(None)

        def save_current_pier():
            name = ent_vars["name"].get()
            if not name:
                messagebox.showwarning("Cảnh báo", "Vui lòng chọn một trụ từ bảng trước!")
                return
            for d in self.project["piers_detail"]:
                if d["name"] == name:
                    try:
                        d["apier"] = float(ent_vars["apier"].get())
                        d["Lpier"] = float(ent_vars["Lpier"].get())
                        d["apc"] = float(ent_vars["apc"].get())
                        d["Lpc"] = float(ent_vars["Lpc"].get())
                        d["T"] = float(ent_vars["T"].get())
                        z_d = float(ent_vars["z_day_be"].get())
                        z_tn = float(ent_vars["cdtn"].get())

                        d["z_be"] = z_d
                        d["z_day_be"] = z_d
                        d["ho"] = round(z_d - z_tn, 3)

                        d["f"] = float(ent_vars["f"].get())
                        d["ap"] = float(ent_vars["ap"].get())
                        d["S"] = float(ent_vars["S"].get())
                        d["m"] = int(float(ent_vars["m"].get()))
                        d["n"] = int(float(ent_vars["n"].get()))
                        d["aproj"] = float(ent_vars["aproj"].get())
                        refresh_dlg_table()
                        messagebox.showinfo("Thành công", f"Đã lưu trụ {name}:\n- CĐ đáy bệ = {z_d:.2f} m\n- ho = {d['ho']:.2f} m")
                    except Exception as e:
                        messagebox.showerror("Lỗi", f"Vui lòng nhập đúng định dạng số! Chi tiết: {e}")
                    break

        def apply_all_piers():
            if not messagebox.askyesno("Xác nhận", "Bạn có muốn áp dụng kích thước Bệ và Nhóm Cọc này cho TẤT CẢ các TRỤ không?"):
                return
            for d in self.project["piers_detail"]:
                try:
                    d["apier"] = float(ent_vars["apier"].get())
                    d["Lpier"] = float(ent_vars["Lpier"].get())
                    d["apc"] = float(ent_vars["apc"].get())
                    d["Lpc"] = float(ent_vars["Lpc"].get())
                    d["T"] = float(ent_vars["T"].get())
                    z_d = float(ent_vars["z_day_be"].get())
                    d["z_be"] = z_d
                    d["z_day_be"] = z_d
                    d["ho"] = round(z_d - float(d["cdtn"]), 3)
                    d["f"] = float(ent_vars["f"].get())
                    d["ap"] = float(ent_vars["ap"].get())
                    d["S"] = float(ent_vars["S"].get())
                    d["m"] = int(float(ent_vars["m"].get()))
                    d["n"] = int(float(ent_vars["n"].get()))
                    d["aproj"] = float(ent_vars["aproj"].get())
                except Exception:
                    pass
            refresh_dlg_table()
            messagebox.showinfo("Thành công", "Đã áp dụng thông số bệ cọc cho tất cả các trụ!")

        f_acts = ttk.Frame(f_left_side)
        f_acts.pack(fill=tk.X, padx=5, pady=6)
        ttk.Button(f_acts, text="CẬP NHẬT TRỤ ĐANG CHỌN", command=save_current_pier).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_acts, text="ÁP DỤNG CHO TẤT CẢ TRỤ", command=apply_all_piers).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_acts, text="Đóng Cửa Sổ", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

        # Cột chỉ dẫn CAD bên phải
        f_right_side = ttk.LabelFrame(pane, text="Hướng Dẫn Thông Số Trụ CAD")
        pane.add(f_right_side, weight=2)

        txt_p_guide = tk.Text(f_right_side, height=20, bg="#FFFFFF", font=("Segoe UI", 9), padx=6, pady=4)
        txt_p_guide.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        p_guide_text = """❖ QUY ĐỊNH KÍCH THƯỚC TRỤ & MÓNG CỌC:
1. THÂN TRỤ (Pier Stem):
   • a: Bề rộng thân trụ (m) - vuông góc dòng chảy.
   • L: Chiều dài thân trụ (m) - dọc theo dòng chảy.
2. BỆ ĐÀI CỌC (Footing):
   • apc: Bề rộng bệ đài (m) - vuông góc dòng chảy.
   • Lpc: Chiều dài bệ đài (m) - dọc theo dòng chảy.
   • T: Chiều dày bệ đài (m).
   • Cao độ đáy bệ Z_đáy (m): Phần mềm tự tính khoảng cách ho = Zđáy - CĐTN.
     - ho <= 0: Đáy bệ ngàm dưới đáy sông -> Cọc ngàm trong đất (yspg = 0).
     - ho > 0: Bệ nằm lơ lửng trong nước -> Tính xói nhóm cọc (yspg > 0).
3. NHÓM CỌC (Pile Group):
   • ap: Đường kính cọc D.
   • S: Cự ly khoảng cách giữa các cọc.
   • m: Số hàng cọc dọc dòng chảy.
   • n: Số cột cọc ngang tim cầu.
"""
        txt_p_guide.insert(tk.END, p_guide_text)
        txt_p_guide.config(state=tk.DISABLED)

    # =========================================================================
    # TAB 2: QUAN HỆ H-Q, H-V & NỘI SUY HTK
    # =========================================================================
    def _init_tab2(self):
        f_top = ttk.Frame(self.tab2)
        f_top.pack(fill=tk.X, padx=10, pady=6)

        ttk.Label(f_top, text="Dải mực nước quét H (m): từ").pack(side=tk.LEFT, padx=4)
        self.e_h_min = ttk.Entry(f_top, width=6)
        self.e_h_min.insert(0, "-2.0")
        self.e_h_min.pack(side=tk.LEFT, padx=2)

        ttk.Label(f_top, text="đến").pack(side=tk.LEFT, padx=4)
        self.e_h_max = ttk.Entry(f_top, width=6)
        self.e_h_max.insert(0, "6.0")
        self.e_h_max.pack(side=tk.LEFT, padx=2)

        ttk.Label(f_top, text="Bước dH:").pack(side=tk.LEFT, padx=4)
        self.e_h_step = ttk.Entry(f_top, width=5)
        self.e_h_step.insert(0, "0.5")
        self.e_h_step.pack(side=tk.LEFT, padx=2)

        btn_calc_curve = ttk.Button(f_top, text="Tính & Vẽ Đường Quan Hệ H-Q, H-V", command=self.calc_hq_curve)
        btn_calc_curve.pack(side=tk.LEFT, padx=15)

        self.lbl_htk_res = ttk.Label(f_top, text="Mực nước thiết kế Htk = ...", font=("Segoe UI", 10, "bold"), foreground="#B71C1C")
        self.lbl_htk_res.pack(side=tk.LEFT, padx=10)

        pane = ttk.PanedWindow(self.tab2, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        f_tbl = ttk.LabelFrame(pane, text="Bảng Tính Thủy Lực Theo Các Cấp Mực Nước H")
        pane.add(f_tbl, weight=1)

        cols = ("H (m)", "Diện tích w(m2)", "Chu vi chi(m)", "Bán kính R(m)", "Môđun K", "Q (m3/s)", "V_bq (m/s)")
        self.tree_hq = ttk.Treeview(f_tbl, columns=cols, show="headings", height=14)
        for c in cols:
            self.tree_hq.heading(c, text=c)
            self.tree_hq.column(c, anchor=tk.CENTER, width=85)
        self.tree_hq.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        f_plot = ttk.LabelFrame(pane, text="Đồ Thị Quan Hệ H - Q và H - V")
        pane.add(f_plot, weight=2)

        self.fig_hq = Figure(figsize=(7, 3.8), dpi=100)
        self.ax_q = self.fig_hq.add_subplot(1, 2, 1)
        self.ax_v = self.fig_hq.add_subplot(1, 2, 2)
        self.fig_hq.tight_layout()
        self.canvas_hq = FigureCanvasTkAgg(self.fig_hq, master=f_plot)
        self.canvas_hq.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def calc_hq_curve(self):
        cs = self.project["cross_section"]
        if not cs:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu mặt cắt sông!")
            return

        try:
            h_min = float(self.e_h_min.get())
            h_max = float(self.e_h_max.get())
            h_step = float(self.e_h_step.get())
            qtk = float(self.t1_entries["qtk"].get())
            s1 = float(self.t1_entries["s1"].get())
            n_manning = float(self.t1_entries["n_manning"].get())
            skew = float(self.t1_entries["skew"].get())
            cos_sk = math.cos(math.radians(skew))

            h_stages = np.arange(h_min, h_max + 0.001, h_step)
            self.hq_data.clear()
            self.tree_hq.delete(*self.tree_hq.get_children())

            q_list = []
            v_list = []
            h_valid = []
            sqrt_s1 = math.sqrt(max(0.0, s1))
            inv_n = 1.0 / n_manning

            for h_stage in h_stages:
                w_tot = 0.0
                chi_tot = 0.0
                for i in range(1, len(cs)):
                    z1, z2 = float(cs[i-1][2]), float(cs[i][2])
                    dl = max(0.001, float(cs[i][3]) * cos_sk)
                    y1_raw = h_stage - z1
                    y2_raw = h_stage - z2

                    if y1_raw > 0 and y2_raw > 0:
                        seg_w = (y1_raw + y2_raw) * 0.5 * dl
                        seg_chi = math.hypot(dl, z2 - z1)
                    elif y1_raw > 0 and y2_raw <= 0:
                        r_eff = y1_raw / max(0.0001, y1_raw - y2_raw)
                        w_eff = dl * r_eff
                        seg_w = y1_raw * w_eff * 0.5
                        seg_chi = math.hypot(w_eff, y1_raw)
                    elif y1_raw <= 0 and y2_raw > 0:
                        r_eff = y2_raw / max(0.0001, y2_raw - y1_raw)
                        w_eff = dl * r_eff
                        seg_w = y2_raw * w_eff * 0.5
                        seg_chi = math.hypot(w_eff, y2_raw)
                    else:
                        seg_w, seg_chi = 0.0, 0.0

                    w_tot += seg_w
                    chi_tot += seg_chi

                if w_tot > 0 and chi_tot > 0:
                    R = w_tot / chi_tot
                    K_mod = inv_n * w_tot * (R ** (2.0 / 3.0))
                    Q_calc = K_mod * sqrt_s1
                    V_calc = Q_calc / w_tot
                else:
                    R, K_mod, Q_calc, V_calc = 0, 0, 0, 0

                self.hq_data.append((h_stage, w_tot, chi_tot, R, K_mod, Q_calc, V_calc))
                self.tree_hq.insert("", tk.END, values=(
                    f"{h_stage:.2f}", f"{w_tot:.2f}", f"{chi_tot:.2f}", f"{R:.2f}",
                    f"{K_mod:.1f}", f"{Q_calc:.2f}", f"{V_calc:.2f}"
                ))

                if Q_calc > 0:
                    q_list.append(Q_calc)
                    v_list.append(V_calc)
                    h_valid.append(h_stage)

            if q_list and qtk >= min(q_list) and qtk <= max(q_list):
                htk_interp = float(np.interp(qtk, q_list, h_valid))
                self.lbl_htk_res.config(text=f"Mực nước lũ Htk nội suy = {htk_interp:.2f} m")
                self.t1_entries["htk"].delete(0, tk.END)
                self.t1_entries["htk"].insert(0, f"{htk_interp:.2f}")
            else:
                self.lbl_htk_res.config(text="Qtk nằm ngoài dải H quét, giữ nguyên Htk nhập.")

            self.ax_q.clear()
            self.ax_v.clear()

            self.ax_q.plot(q_list, h_valid, color="#1976D2", linewidth=2, marker="o", markersize=3)
            self.ax_q.set_title("Đường Quan Hệ H - Q", fontsize=9, fontweight="bold")
            self.ax_q.set_xlabel("Lưu lượng Q (m3/s)", fontsize=8)
            self.ax_q.set_ylabel("Mực nước H (m)", fontsize=8)
            self.ax_q.grid(True, linestyle="--", alpha=0.5)

            self.ax_v.plot(v_list, h_valid, color="#388E3C", linewidth=2, marker="s", markersize=3)
            self.ax_v.set_title("Đường Quan Hệ H - V", fontsize=9, fontweight="bold")
            self.ax_v.set_xlabel("Vận tốc V_bq (m/s)", fontsize=8)
            self.ax_v.set_ylabel("Mực nước H (m)", fontsize=8)
            self.ax_v.grid(True, linestyle="--", alpha=0.5)

            self.canvas_hq.draw()

        except Exception as e:
            messagebox.showerror("Lỗi", f"Quá trình tính đường quan hệ H-Q bị lỗi: {e}")

    # =========================================================================
    # TAB 3: PHÂN PHỐI LƯU LƯỢNG (PPLL)
    # =========================================================================
    def _init_tab3(self):
        f_info = ttk.LabelFrame(self.tab3, text="Thông Số Thủy Lực Thiết Kế Cần Phân Phối (Mặt cắt Htk)")
        f_info.pack(fill=tk.X, padx=8, pady=4)

        self.lbl_ppll_htk = ttk.Label(f_info, text="Mực nước tính toán Htk: ... m", font=("Segoe UI", 9, "bold"), foreground="#0D47A1")
        self.lbl_ppll_htk.grid(row=0, column=0, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_qtk = ttk.Label(f_info, text="Lưu lượng thiết kế Qtk: ... m3/s", font=("Segoe UI", 9, "bold"), foreground="#B71C1C")
        self.lbl_ppll_qtk.grid(row=0, column=1, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_qsum = ttk.Label(f_info, text="Tổng Q phân phối ΣQi: ... m3/s", font=("Segoe UI", 9, "bold"), foreground="#2E7D32")
        self.lbl_ppll_qsum.grid(row=0, column=2, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_alpha = ttk.Label(f_info, text="Hệ số phân bố α: ...", font=("Segoe UI", 9))
        self.lbl_ppll_alpha.grid(row=1, column=0, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_wsum = ttk.Label(f_info, text="Tổng diện tích ướt Σω: ... m2", font=("Segoe UI", 9))
        self.lbl_ppll_wsum.grid(row=1, column=1, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_vbq = ttk.Label(f_info, text="Vận tốc bình quân Vbq: ... m/s", font=("Segoe UI", 9))
        self.lbl_ppll_vbq.grid(row=1, column=2, padx=12, pady=4, sticky=tk.W)

        f_tbl = ttk.LabelFrame(self.tab3, text="Bảng Phân Phối Lưu Lượng & Tốc Độ Dòng Chảy Thiết Kế Qua Mặt Cắt Tim Cầu (Sheet PPLL / Htk)")
        f_tbl.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        ppll_cols = (
            "Tên trụ / BP", "▼Đáy sông (m)", "hi (m)", "Δli (m)",
            "ΣΔli (m)", "ωi (m2)", "Σωi (m)", "h^5/3 (m5/3)", "Ai", "α tốc độ",
            "qi (m3/sm)", "Qi (m3/s)", "ΣQi (m3/s)", "Vbq th.tr (m/s)"
        )
        self.tree_ppll = ttk.Treeview(f_tbl, columns=ppll_cols, show="headings", height=16)
        for c in ppll_cols:
            self.tree_ppll.heading(c, text=c)
            self.tree_ppll.column(c, anchor=tk.CENTER, width=88)

        s_ppll_y = ttk.Scrollbar(f_tbl, orient=tk.VERTICAL, command=self.tree_ppll.yview)
        self.tree_ppll.configure(yscrollcommand=s_ppll_y.set)
        self.tree_ppll.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        s_ppll_y.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

    # =========================================================================
    # TAB 4: CHOÁN DÒNG (VCAU - CHỈ TÍNH CÁC TRỤ CẢN DÒNG)
    # =========================================================================
    def _init_tab4(self):
        f_top = ttk.LabelFrame(self.tab4, text="Bảng Tính Diện Tích Trụ & Chiều Rộng Bình Quân Trụ Choán Dòng (Sheet Vcau)")
        f_top.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        vcau_cols = (
            "Tên Trụ", "Cao Độ CĐTN", "Bề Rộng Thân a(m)", "Chiều Dài L(m)", 
            "Góc Xiên (°)", "B_choán b(m)", "Chiều Sâu h(m)", "Diện Tích Choán w(m2)",
            "Kích Thước Bệ (BxL)", "CĐ Đáy Bệ Z_be(m)", "ho(m)", "Cọc (ap, S, m, n)"
        )
        self.tree_vcau = ttk.Treeview(f_top, columns=vcau_cols, show="headings", height=12)
        for c in vcau_cols:
            self.tree_vcau.heading(c, text=c)
            self.tree_vcau.column(c, anchor=tk.CENTER, width=100)
        self.tree_vcau.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        f_sum = ttk.LabelFrame(self.tab4, text="Tổng Hợp Bề Rộng Thoát Nước Co Hẹp Qua Cầu W2")
        f_sum.pack(fill=tk.X, padx=8, pady=6)

        self.txt_vcau_summary = tk.Text(f_sum, height=6, bg="#F9F9F9", font=("Consolas", 10))
        self.txt_vcau_summary.pack(fill=tk.X, padx=6, pady=4)

    # =========================================================================
    # TAB 5: NƯỚC DỀNH
    # =========================================================================
    def _init_tab5(self):
        f_fml = ttk.LabelFrame(self.tab5, text="Công Thức Tính Toán Nước Dềnh Thượng Lưu (Sheet denh)")
        f_fml.pack(fill=tk.X, padx=8, pady=4)

        fml_text = (
            "• Độ dềnh lớn nhất:  Δhdmax = K * (Vcầu² - Vcầu0²) / (2g)\n"
            "• Hệ số nước dềnh:  K = 1 + (Vo / Vcầu0)² * a / (Fr / io)^0.5   với   Fr = Vo² / (g * Lngập)\n"
            "• Khoảng cách dềnh xa nhất lên thượng lưu:  xo = a * Lngập * (Fr / io)^0.5\n"
            "  Trong đó: Vo: Vận tốc bình quân tự nhiên | Lngập: Chiều rộng ngập nước | io: Độ dốc dọc S1 | Vcầu: Vận tốc qua cầu thu hẹp | a: Hệ số hình thái"
        )
        lbl_fml = tk.Label(f_fml, text=fml_text, justify=tk.LEFT, font=("Consolas", 9), fg="#0D47A1", bg="#F4F6F9")
        lbl_fml.pack(fill=tk.X, padx=6, pady=4)

        f_top = ttk.LabelFrame(self.tab5, text="Bảng Kết Quả Tính Toán Nước Dềnh Dưới Cầu")
        f_top.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        denh_cols = (
            "STT", "Vo (m/s)", "Lngập (m)", "Fr", "io", "Fr / io",
            "Qcầu 0 (m3/s)", "Vcầu 0 (m/s)", "QTK / Qcầu0", "a", "K", "Vcầu (m/s)", "Δhdmax (m)", "xo (m)", "Ghi chú"
        )
        self.tree_denh = ttk.Treeview(f_top, columns=denh_cols, show="headings", height=8)
        for c in denh_cols:
            self.tree_denh.heading(c, text=c)
            self.tree_denh.column(c, anchor=tk.CENTER, width=88)

        s_denh_x = ttk.Scrollbar(f_top, orient=tk.HORIZONTAL, command=self.tree_denh.xview)
        self.tree_denh.configure(xscrollcommand=s_denh_x.set)
        self.tree_denh.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)
        s_denh_x.pack(side=tk.BOTTOM, fill=tk.X, padx=4)

    # =========================================================================
    # TAB 6: XÓI CO HẸP
    # =========================================================================
    def _init_tab6(self):
        f_fml = ttk.LabelFrame(self.tab6, text="Công Thức Tính Toán Xói Thu Hẹp Dưới Cầu (HEC-18 Chapter 6 / Sheet xoi chung)")
        f_fml.pack(fill=tk.X, padx=8, pady=4)

        fml_text = (
            "• Vận tốc tới hạn di chuyển hạt bùn cát:  Vc = 6.19 * y1^(1/6) * D50^(1/3)  (m/s)\n"
            "• Khi Vc < V (Xói nước đục - Live-bed):  y2 = y1 * [Q2 / Q1]^(6/7) * [W1 / W2]^k1   với   k1 = f(V* / w),  V* = (g * y1 * S1)^0.5\n"
            "• Khi Vc >= V (Xói nước trong - Clear-water):  y2 = [0.025 * Q2² / (Dm^(2/3) * W2²)]^(3/7)   với   Dm = 1.25 * D50\n"
            "• Chiều sâu xói co hẹp bình quân:  Dyxch = y2 - yo   (yo: Độ sâu hiện tại trước xói)"
        )
        lbl_fml = tk.Label(f_fml, text=fml_text, justify=tk.LEFT, font=("Consolas", 9), fg="#0D47A1", bg="#F4F6F9")
        lbl_fml.pack(fill=tk.X, padx=6, pady=4)

        f_top = ttk.LabelFrame(self.tab6, text="Bảng Tính Toán Xói Thu Hẹp Trung Bình Dưới Cầu")
        f_top.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        xoi_cols = (
            "No.", "Đtr.b ở m/c thượng lưu", "y1 (m)", "D50 (mm)", "Vc (m/s)",
            "V (m/s)", "Vc / V", "Thuộc loại", "S1 (m/m)", "V* (m/s)",
            "w (m/s)", "V* / w", "K1", "Q1 (m3/s)", "W1 (m)", "Q2 (m3/s)",
            "W2 (m)", "Dm (mm)", "y2 (m)", "Đtr.b ở m/c thu hẹp", "yo (m)", "Dyxch (m)", "Ghi chú"
        )
        self.tree_xoi_chung = ttk.Treeview(f_top, columns=xoi_cols, show="headings", height=10)
        for c in xoi_cols:
            self.tree_xoi_chung.heading(c, text=c)
            self.tree_xoi_chung.column(c, anchor=tk.CENTER, width=90)

        s_x = ttk.Scrollbar(f_top, orient=tk.HORIZONTAL, command=self.tree_xoi_chung.xview)
        self.tree_xoi_chung.configure(xscrollcommand=s_x.set)
        self.tree_xoi_chung.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
        s_x.pack(side=tk.BOTTOM, fill=tk.X, padx=4)

    # =========================================================================
    # TAB 7: XÓI CỤC BỘ MỐ & TRỤ (TÁCH BIỆT 7.1~7.3 VỚI 7.4 MỐ)
    # =========================================================================
    def _init_tab7(self):
        f_ctrl = ttk.Frame(self.tab7)
        f_ctrl.pack(fill=tk.X, padx=10, pady=4)

        ttk.Button(f_ctrl, text="▶ CHẠY TÍNH TOÁN LẠI TẤT CẢ", command=self.run_full_system).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_ctrl, text="🏛 CẤU HÌNH THỦY LỰC MỐ CẦU...", command=self.dialog_edit_abutments_detail).pack(side=tk.LEFT, padx=6)
        ttk.Button(f_ctrl, text="📐 CẤU HÌNH BỆ & CỌC TRỤ...", command=self.dialog_edit_piers_detail).pack(side=tk.LEFT, padx=6)

        self.nb_scour = ttk.Notebook(self.tab7)
        self.nb_scour.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # ---------------- 7.1: TRỤ ĐƠN ĐẶC ----------------
        self.subtab_single_pier = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_single_pier, text=" 7.1 Trụ Đơn Đặc (xoi cuc tru) ")

        cols_single = (
            "No. Trụ", "CĐTN (m)", "y1 (m)", "V1 (m/s)", "Fr1", "a (m)", "H.D. trụ", "K1", "θ (°)", "L (m)",
            "K2", "Đáy sông", "K3", "D50 (mm)", "Vc (m/s)", "V/Vc", "Kw", "yspier (m)", "CĐ sau xói (m)", "Ghi chú"
        )
        self.tree_single_pier = ttk.Treeview(self.subtab_single_pier, columns=cols_single, show="headings", height=14)
        for c in cols_single:
            self.tree_single_pier.heading(c, text=c)
            self.tree_single_pier.column(c, anchor=tk.CENTER, width=78)

        s_single_x = ttk.Scrollbar(self.subtab_single_pier, orient=tk.HORIZONTAL, command=self.tree_single_pier.xview)
        self.tree_single_pier.configure(xscrollcommand=s_single_x.set)
        self.tree_single_pier.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)
        s_single_x.pack(side=tk.BOTTOM, fill=tk.X, padx=4)

        # ---------------- 7.2: TRỤ LỘ BỆ ----------------
        self.subtab_lobe = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_lobe, text=" 7.2 Trụ Lộ Bệ (XCB-Lo Be) ")

        f_lobe_1 = ttk.LabelFrame(self.subtab_lobe, text="1, Xói cục bộ do thân trụ gây ra (yspier)")
        f_lobe_1.pack(fill=tk.X, padx=6, pady=2)
        cols_lobe_1 = ("No.", "CĐTN", "y1", "V1", "Fr1", "a", "K1", "θ", "L", "K2", "K3", "f", "ho", "T", "h1", "Khpier", "D50", "Vc", "V/Vc", "Kw", "yspier")
        self.tree_lobe_1 = ttk.Treeview(f_lobe_1, columns=cols_lobe_1, show="headings", height=4)
        for c in cols_lobe_1:
            self.tree_lobe_1.heading(c, text=c)
            self.tree_lobe_1.column(c, anchor=tk.CENTER, width=62)
        self.tree_lobe_1.pack(fill=tk.X, padx=3, pady=2)

        f_lobe_2 = ttk.LabelFrame(self.subtab_lobe, text="2, Xói cục bộ do bệ trụ (ysfooting)")
        f_lobe_2.pack(fill=tk.X, padx=6, pady=2)
        cols_lobe_2 = ("No.", "CĐTN", "y1", "V1", "yspier", "y2", "h2", "h1", "yf", "V2", "Ks", "Vf", "af", "Fr2", "Kw", "ysfooting")
        self.tree_lobe_2 = ttk.Treeview(f_lobe_2, columns=cols_lobe_2, show="headings", height=4)
        for c in cols_lobe_2:
            self.tree_lobe_2.heading(c, text=c)
            self.tree_lobe_2.column(c, anchor=tk.CENTER, width=68)
        self.tree_lobe_2.pack(fill=tk.X, padx=3, pady=2)

        f_lobe_3 = ttk.LabelFrame(self.subtab_lobe, text="3, Kết quả phân tích xói cục bộ tại trụ (ys = yspier + ysfooting)")
        f_lobe_3.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        cols_lobe_3 = ("STT", "Tên Trụ", "CĐTN (m)", "CĐ đáy bệ (m)", "ho (m)", "Xói thân ys,pier (m)", "Xói bệ ys,footing (m)", "Tổng chiều sâu xói ys (m)", "Cao độ đáy xói (m)")
        self.tree_lobe_3 = ttk.Treeview(f_lobe_3, columns=cols_lobe_3, show="headings", height=4)
        for c in cols_lobe_3:
            self.tree_lobe_3.heading(c, text=c)
            self.tree_lobe_3.column(c, anchor=tk.CENTER, width=115)
        self.tree_lobe_3.pack(fill=tk.BOTH, expand=True, padx=3, pady=2)

        # ---------------- 7.3: TRỤ LỘ BỆ & CỌC ----------------
        self.subtab_lococ = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_lococ, text=" 7.3 Trụ Lộ Bệ & Cọc (XBC-lo coc) ")

        f_lc_4 = ttk.LabelFrame(self.subtab_lococ, text="Bảng Tổng Hợp Xói Cục Bộ Trụ Lộ Bệ & Cọc (Khống chế ho <= 0 -> yspg = 0)")
        f_lc_4.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        cols_lc_4 = ("STT", "Tên Trụ", "CĐTN (m)", "CĐ đáy bệ (m)", "ho (m)", "yspier (m)", "yspc (m)", "yspg (m)", "Tổng xói ys (m)", "Cao độ sau xói (m)", "Ghi chú phân loại")
        self.tree_lc_4 = ttk.Treeview(f_lc_4, columns=cols_lc_4, show="headings", height=12)
        for c in cols_lc_4:
            self.tree_lc_4.heading(c, text=c)
            self.tree_lc_4.column(c, anchor=tk.CENTER, width=105)
        self.tree_lc_4.pack(fill=tk.BOTH, expand=True, padx=3, pady=2)

        # ---------------- 7.4: XÓI CỤC BỘ MỐ CẦU (FROEHLICH - CHUẨN BIỂU MẪU) ----------------
        self.subtab_abutment = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_abutment, text=" 7.4 Xói Cục Bộ Mố (Froehlich / HIRE) ")

        f_fml_74 = ttk.LabelFrame(self.subtab_abutment, text="Công Thức Dự Báo Xói Cục Bộ Mố Cầu Theo Froehlich (HEC-18 / Tiêu Chuẩn Thiết Kế)")
        f_fml_74.pack(fill=tk.X, padx=6, pady=3)
        txt_74 = (
            "• Công thức Froehlich:  yx = 2.27 * K1 * K2 * (L')^0.43 * ya^0.57 * Fr1^0.61 + ya   (m)\n"
            "  Trong đó: ya: Chiều sâu dòng chảy trung bình trên bãi (m) | L': Chiều dài mố/nền đắp nhô ra cản dòng (m)\n"
            "  Fr1 = Ve / (g * ya)^0.5  với Ve = Qe / Ae (m/s) | Qe: Lưu lượng bị chặn | Ae: Diện tích bị chặn\n"
            "  K1: Hình dạng mố (1.00 tường đứng; 0.82 tường cánh; 0.55 taluy xiên) | K2 = (θ/90)^0.13 với θ là góc xiên"
        )
        tk.Label(f_fml_74, text=txt_74, justify=tk.LEFT, font=("Consolas", 9), fg="#0D47A1", bg="#F4F6F9").pack(fill=tk.X, padx=4, pady=3)

        f_ab_act = ttk.Frame(self.subtab_abutment)
        f_ab_act.pack(fill=tk.X, padx=6, pady=2)
        ttk.Button(f_ab_act, text="⚙ CẤU HÌNH & NHẬP SỐ LIỆU THỦY LỰC MỐ (Qe, Ae, L', K1)...", command=self.dialog_edit_abutments_detail).pack(side=tk.LEFT, padx=2)

        cols_abut = (
            "No. Mố", "CĐTN (m)", "ya (m)", "Qe (m3/s)", "Ae (m2)", "Ve (m/s)", "Fr1",
            "H.D. mố", "K1", "θ (°)", "K2", "L' (m)", "yx (m)", "CĐ sau xói (m)", "Ghi chú"
        )
        self.tree_abutment = ttk.Treeview(self.subtab_abutment, columns=cols_abut, show="headings", height=12)
        for c in cols_abut:
            self.tree_abutment.heading(c, text=c)
            self.tree_abutment.column(c, anchor=tk.CENTER, width=80)

        s_abut_x = ttk.Scrollbar(self.subtab_abutment, orient=tk.HORIZONTAL, command=self.tree_abutment.xview)
        self.tree_abutment.configure(xscrollcommand=s_abut_x.set)
        self.tree_abutment.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)
        s_abut_x.pack(side=tk.BOTTOM, fill=tk.X, padx=4)

    # =========================================================================
    # TAB 8: TỔNG HỢP & SCOUR PRISM
    # =========================================================================
    def _init_tab8(self):
        f_table = ttk.LabelFrame(self.tab8, text="Bảng Tổng Hợp Chiều Sâu Xói & Cao Độ Đáy Xói Thiết Kế Móng")
        f_table.pack(fill=tk.X, padx=8, pady=4)

        cols = (
            "Mố/Trụ", "Vị trí X (m)", "CĐTN (m)", "CĐ đáy bệ", "ho (m)", "Hạ thấp dài hạn y_deg (m)",
            "Xói co hẹp y_sc (m)", "Xói cục bộ ys (m)", "Tổng xói Y_total (m)", "Cao độ đáy sau xói (m)"
        )
        self.tree_summary = ttk.Treeview(f_table, columns=cols, show="headings", height=6)
        for c in cols:
            self.tree_summary.heading(c, text=c)
            self.tree_summary.column(c, anchor=tk.CENTER, width=110)
        self.tree_summary.pack(fill=tk.X, padx=4, pady=4)

        f_plot = ttk.LabelFrame(self.tab8, text="Đồ Thị Mặt Cắt Thoát Nước & Hố Xói Dưới Cầu (Scour Prism)")
        f_plot.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.fig_prism = Figure(figsize=(10, 3.8), dpi=100)
        self.ax_prism = self.fig_prism.add_subplot(1, 1, 1)
        self.fig_prism.tight_layout()
        self.canvas_prism = FigureCanvasTkAgg(self.fig_prism, master=f_plot)
        self.canvas_prism.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        f_bot = ttk.Frame(self.tab8)
        f_bot.pack(fill=tk.X, padx=8, pady=4)
        btn_exp = ttk.Button(f_bot, text="Xuất File Báo Cáo Thuyết Minh Kỹ Thuật (*.txt)...", command=self.action_export_report)
        btn_exp.pack(side=tk.RIGHT, padx=5)

    def _render_scour_prism_plot(self, x_pts, z_pts, htk, y_deg, ysc, piers_x, scour_z):
        self.ax_prism.clear()
        self.ax_prism.axhline(htk, color="#0288D1", linestyle="--", linewidth=1.5, label=f"Mực nước lũ Htk = {htk:.2f}m")
        self.ax_prism.plot(x_pts, z_pts, color="#5D4037", linewidth=2.0, marker="o", markersize=3, label="Đáy sông tự nhiên (CĐTN)")

        z_gen = [z - (y_deg + ysc) for z in z_pts]
        self.ax_prism.plot(x_pts, z_gen, color="#FF8F00", linestyle=":", linewidth=1.5, label="Đáy sau xói co hẹp + dài hạn")

        for px, sz in zip(piers_x, scour_z):
            self.ax_prism.plot([px, px], [sz, htk + 1.2], color="#263238", linewidth=3.5)
            w_hole = max(2.0, (htk - sz) * 0.4)
            self.ax_prism.plot([px - w_hole, px, px + w_hole], [sz + (htk-sz)*0.15, sz, sz + (htk-sz)*0.15], color="red", linestyle="--")
            self.ax_prism.scatter(px, sz, color="red", s=70, zorder=5)
            self.ax_prism.text(px, sz - 0.7, f"Z={sz:.2f}m", ha="center", fontsize=8, color="red", fontweight="bold")

        title_str = f"MẶT CẮT THOÁT NƯỚC & ĐƯỜNG ĐÁY XÓI DƯỚI CẦU - DỰ ÁN: {self.project['bridge_name'].upper()}"
        self.ax_prism.set_title(title_str, fontsize=10, fontweight="bold")
        self.ax_prism.set_xlabel("Khoảng cách ngang dòng sông X (m)", fontsize=9)
        self.ax_prism.set_ylabel("Cao độ Z (m)", fontsize=9)
        self.ax_prism.grid(True, linestyle="--", alpha=0.5)
        self.ax_prism.legend(loc="lower right", fontsize=8)
        self.canvas_prism.draw()

    # =========================================================================
    # THỰC THI TÍNH TOÁN TOÀN BỘ (RUN FULL SYSTEM)
    # =========================================================================
    def run_full_system(self):
        cs = self.project["cross_section"]
        if not cs:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập dữ liệu mặt cắt sông!")
            return

        try:
            warnings = []
            self.sync_all_details()

            htk = float(self.t1_entries["htk"].get())
            qtk = float(self.t1_entries["qtk"].get())
            skew = float(self.t1_entries["skew"].get())
            s1 = float(self.t1_entries["s1"].get())
            d50_mm = float(self.t1_entries["d50"].get())
            d50_m = d50_mm / 1000.0
            d84_mm = float(self.t1_entries["d84"].get())
            if d84_mm <= 0:
                d84_mm = 2.0 * d50_mm
            d84_m = d84_mm / 1000.0
            w1_up_in = float(self.t1_entries["w1_up"].get())
            omega = float(self.t1_entries["omega"].get())
            y_deg = float(self.t1_entries["y_deg"].get())

            k3_name = self.cb_k3.get()
            k3_val, _ = HEC18Tables.PIER_K3.get(k3_name, HEC18Tables.PIER_K3[HEC18Tables.DEFAULT_K3])
            k1_pier_name = self.cb_k1.get()
            k1_pier_shape, _ = HEC18Tables.PIER_K1.get(k1_pier_name, HEC18Tables.PIER_K1[HEC18Tables.DEFAULT_PIER_K1])
            round_nose = k1_pier_name in HEC18Tables.ROUND_NOSE

            rad_sk = math.radians(skew)
            cos_sk = math.cos(rad_sk)
            sin_sk = math.sin(rad_sk)
            theta_attack = abs(skew)

            self.vh_data.clear()
            n_pts = len(cs)
            depth = [htk - float(r[2]) for r in cs]
            h_vals = [max(0.0, d) for d in depth]
            dl_vals = [max(0.0, float(r[3]) * cos_sk) for r in cs]

            if max(h_vals) <= 0.0:
                messagebox.showerror("Lỗi dữ liệu", "Độ sâu nước ngập tại toàn bộ các điểm đều <= 0 m!")
                return

            L_cum = [0.0]
            for i in range(1, n_pts):
                L_cum.append(L_cum[-1] + dl_vals[i])

            w_vals = [0.0]
            Ai_vals = [0.0]
            wet_w = [0.0]
            for i in range(1, n_pts):
                ww, wi, Ai = HEC18Calculations.wet_segment(depth[i - 1], depth[i], dl_vals[i])
                wet_w.append(ww)
                w_vals.append(wi)
                Ai_vals.append(Ai)

            sum_A = max(1e-6, sum(Ai_vals))
            sum_w = max(0.1, sum(w_vals))
            alpha_v = qtk / sum_A
            V_mean = qtk / sum_w

            Qi_vals = [0.0] + [alpha_v * Ai_vals[i] for i in range(1, n_pts)]
            Vi_vals = [0.0]
            for i in range(1, n_pts):
                Vi_vals.append(Qi_vals[i] / w_vals[i] if w_vals[i] > 0 else 0.0)
            Vloc_vals = [alpha_v * (h ** (2.0 / 3.0)) if h > 0 else 0.0 for h in h_vals]

            for i in range(n_pts):
                r = cs[i]
                self.vh_data.append({
                    "stt": r[0], "name": r[1], "z": float(r[2]), "hi": h_vals[i],
                    "dl": dl_vals[i], "L_cum": L_cum[i], "wi": w_vals[i],
                    "Qi": Qi_vals[i], "Vi": Vi_vals[i], "Vloc": Vloc_vals[i], "type": r[4],
                    "a": float(r[5]), "L": float(r[6]), "k1": float(r[7])
                })

            W1 = max(1.0, sum(wet_w))
            y1_mean = sum_w / W1

            # ---------------- Tab 3 (PPLL) ----------------
            self.tree_ppll.delete(*self.tree_ppll.get_children())
            cum_dl = cum_w = cum_q = 0.0
            for i, p in enumerate(self.vh_data):
                cum_dl += p["dl"]
                cum_w += p["wi"]
                cum_q += p["Qi"]
                h_53 = (p["hi"] ** (5.0 / 3.0)) if p["hi"] > 0 else 0.0
                ai_val = h_53 * p["dl"]
                qi_val = p["Qi"] / max(0.001, p["dl"]) if p["dl"] > 0 else 0.0
                self.tree_ppll.insert("", tk.END, values=(
                    p["name"] if p["name"] else f"ĐIỂM {i+1}",
                    f"{p['z']:.2f}", f"{p['hi']:.2f}", f"{p['dl']:.2f}",
                    f"{cum_dl:.2f}", f"{p['wi']:.2f}", f"{cum_w:.2f}", f"{h_53:.2f}",
                    f"{ai_val:.2f}", f"{alpha_v:.2f}", f"{qi_val:.2f}",
                    f"{p['Qi']:.2f}", f"{cum_q:.2f}", f"{p['Vi']:.2f}"
                ))

            self.lbl_ppll_htk.config(text=f"Mực nước tính toán Htk: {htk:.2f} m")
            self.lbl_ppll_qtk.config(text=f"Lưu lượng thiết kế Qtk: {qtk:.2f} m3/s")
            self.lbl_ppll_qsum.config(text=f"Tổng Q phân phối ΣQi: {cum_q:.2f} m3/s (Khớp {(cum_q/max(0.001, qtk))*100:.1f}%)")
            self.lbl_ppll_alpha.config(text=f"Hệ số phân bố α: {alpha_v:.6f}")
            self.lbl_ppll_wsum.config(text=f"Tổng diện tích ướt Σω: {sum_w:.2f} m2")
            self.lbl_ppll_vbq.config(text=f"Vận tốc bình quân Vbq: {V_mean:.2f} m/s")

            # ---------------- Tab 4: Choán dòng (Chỉ trụ) ----------------
            self.tree_vcau.delete(*self.tree_vcau.get_children())
            sum_b_choan = 0.0
            sum_w_choan = 0.0

            piers_in_channel = [p for p in self.vh_data if p["name"] and not is_abut_name(p["name"])]
            for p in piers_in_channel:
                a_tru = p["a"]
                L_tru = p["L"]
                b_proj = a_tru * cos_sk + L_tru * abs(sin_sk)
                w_choan = b_proj * p["hi"]
                sum_b_choan += b_proj if p["hi"] > 0 else 0.0
                sum_w_choan += w_choan

                detail = next((d for d in self.project.get("piers_detail", []) if d["name"] == p["name"]), None)
                if detail:
                    be_str = f"{detail['apc']}x{detail['Lpc']}"
                    z_be_str = f"{detail['z_be']:.2f}"
                    ho_str = f"{detail['ho']:.2f}"
                    coc_str = f"d={detail['ap']}, S={detail['S']}, {detail['m']}x{detail['n']}"
                else:
                    be_str = "6.0x13.3"
                    z_be_str = f"{p['z'] - 1.40:.2f}"
                    ho_str = "-1.40"
                    coc_str = "d=1.2, S=4.2"

                self.tree_vcau.insert("", tk.END, values=(
                    p["name"], f"{p['z']:.2f}", f"{a_tru:.2f}", f"{L_tru:.2f}",
                    f"{skew:.1f}", f"{b_proj:.2f}", f"{p['hi']:.2f}", f"{w_choan:.2f}",
                    be_str, z_be_str, ho_str, coc_str
                ))

            W2 = max(1.0, W1 - sum_b_choan)
            W1_up = w1_up_in if w1_up_in > 0 else W1

            summary_vcau_txt = (
                f"- TỔNG BỀ RỘNG ƯỚT HOẠT ĐỘNG W1: {W1:.2f} m | DIỆN TÍCH ƯỚT: {sum_w:.2f} m2\n"
                f"- TỔNG BỀ RỘNG TRỤ CẢN DÒNG sum(b): {sum_b_choan:.2f} m | TỔNG DIỆN TÍCH CHOÁN: {sum_w_choan:.2f} m2\n"
                f"- BỀ RỘNG THOÁT LŨ SAU THU HẸP W2 : {W2:.2f} m (= W1 - sum(b))\n"
                f"- BỀ RỘNG LÒNG CHỦ THƯỢNG LƯU W1_up: {W1_up:.2f} m | V_bq = {V_mean:.2f} m/s"
            )
            self.txt_vcau_summary.delete("1.0", tk.END)
            self.txt_vcau_summary.insert(tk.END, summary_vcau_txt)

            # ---------------- Tab 5: Nước dềnh ----------------
            self.tree_denh.delete(*self.tree_denh.get_children())
            v0 = V_mean
            Lngap = max(1.0, W1)
            Fr = (v0 ** 2) / (G * Lngap)
            Fr_i0 = max(0.0001, Fr / max(1e-7, s1))
            Qcau0 = qtk
            Vcau0 = V_mean
            a_factor = 0.73
            w_eff_bridge = max(0.1, sum_w - sum_w_choan)
            Vcau = qtk / w_eff_bridge
            K_denh = 1.0 + ((v0 / max(0.01, Vcau0)) ** 2) * a_factor / math.sqrt(max(0.0001, Fr_i0))
            dhdmax = max(0.0, K_denh * (Vcau ** 2 - Vcau0 ** 2) / (2.0 * G))
            x0 = a_factor * Lngap * math.sqrt(max(0.0001, Fr_i0))

            self.tree_denh.insert("", tk.END, values=(
                "1.0", f"{v0:.2f}", f"{Lngap:.2f}", f"{Fr:.5f}", f"{s1:.5e}",
                f"{Fr_i0:.2f}", f"{Qcau0:.2f}", f"{Vcau0:.2f}", f"{(qtk/Qcau0):.2f}",
                f"{a_factor:.2f}", f"{K_denh:.3f}", f"{Vcau:.2f}", f"{dhdmax:.3f}", f"{x0:.1f}", ""
            ))

            # ---------------- Tab 6: Xói co hẹp ----------------
            self.tree_xoi_chung.delete(*self.tree_xoi_chung.get_children())
            cr = HEC18Calculations.contraction_scour(qtk, y1_mean, V_mean, W1_up, W2, d50_m, s1, omega)
            Vc = cr["vc"]
            ysc = cr["ysc"]
            bed_z = htk - y1_mean

            self.tree_xoi_chung.insert("", tk.END, values=(
                "Lòng sông", f"{bed_z:.2f}", f"{y1_mean:.2f}", f"{d50_mm:.3f}", f"{Vc:.3f}",
                f"{V_mean:.2f}", f"{(Vc/max(0.01, V_mean)):.3f}", cr["mode"], f"{s1:.5e}",
                f"{cr['v_star']:.4f}", f"{omega:.3f}", f"{cr['ratio_vw']:.3f}", f"{cr['k1']}", f"{qtk:.2f}", f"{W1_up:.2f}",
                f"{qtk:.2f}", f"{W2:.2f}", f"{cr['dm']*1000:.3f}", f"{cr['y2']:.2f}", f"{bed_z:.2f}", f"{y1_mean:.2f}",
                f"{ysc:.3f}", cr["note"]
            ))

            # ---------------- Tab 7: Xói cục bộ (Tách Mố vs Trụ) ----------------
            self.scour_results.clear()
            self.tree_summary.delete(*self.tree_summary.get_children())
            self.tree_single_pier.delete(*self.tree_single_pier.get_children())
            self.tree_lobe_1.delete(*self.tree_lobe_1.get_children())
            self.tree_lobe_2.delete(*self.tree_lobe_2.get_children())
            self.tree_lobe_3.delete(*self.tree_lobe_3.get_children())
            self.tree_lc_4.delete(*self.tree_lc_4.get_children())
            self.tree_abutment.delete(*self.tree_abutment.get_children())

            gen_lower = y_deg + ysc
            plot_x = []
            plot_scour_z = []
            stt_p = 1

            for idx_p, p in enumerate(self.vh_data):
                if not p["name"]:
                    continue

                p_name = p["name"]
                px = p["L_cum"]
                cdtn = p["z"]
                y1 = p["hi"]
                a = p["a"]
                L = p["L"]

                # ==================== A. TÍNH CHO MỐ CẦU ====================
                if is_abut_name(p_name):
                    ab_cfg = next((d for d in self.project.get("abutments_detail", []) if d["name"] == p_name), None)
                    if ab_cfg:
                        ya = float(ab_cfg.get("ya", max(0.1, htk - cdtn)))
                        Qe = float(ab_cfg.get("Qe", 24.39))
                        Ae = float(ab_cfg.get("Ae", 8.19))
                        l_prime = float(ab_cfg.get("L_prime", 1.70))
                        k1_type_name = ab_cfg.get("k1_type", HEC18Tables.DEFAULT_ABUT_K1)
                        k1_abut = HEC18Tables.ABUT_K1.get(k1_type_name, (1.00,))[0]
                        th = float(ab_cfg.get("theta", 90.0))
                    else:
                        ya = max(0.1, htk - cdtn)
                        Qe = 24.39
                        Ae = 8.19
                        l_prime = 1.70
                        k1_abut = 1.00
                        k1_type_name = HEC18Tables.DEFAULT_ABUT_K1
                        th = 90.0

                    ve = Qe / Ae if Ae > 0 else 0.0
                    ab_res = HEC18Calculations.abutment_scour(ya, ve, l_prime, k1_abut, th)
                    ys_abut = ab_res["ys"]
                    cd_sau_xoi_ab = cdtn - (gen_lower + ys_abut)

                    # Ghi vào Tab 7.4 (Chuẩn biểu mẫu HEC-18)
                    hd_short = "Tường đứng" if k1_abut == 1.0 else ("Tường cánh" if k1_abut == 0.82 else "Mái taluy")
                    self.tree_abutment.insert("", tk.END, values=(
                        p_name, f"{cdtn:.2f}", f"{ya:.2f}", f"{Qe:.2f}", f"{Ae:.2f}",
                        f"{ve:.2f}", f"{ab_res['fr']:.3f}", hd_short, f"{k1_abut:.2f}",
                        f"{th:.1f}", f"{ab_res['k2']:.3f}", f"{l_prime:.2f}", f"{ys_abut:.2f}", f"{cd_sau_xoi_ab:.2f}", ab_res["method"]
                    ))

                    ys_final_chosen = ys_abut
                    z_be_disp, ho_disp = "-", "-"
                    v1 = ve
                    y1 = ya

                # ==================== B. TÍNH CHO TRỤ CẦU ====================
                else:
                    v1 = p["Vloc"]
                    k1_eff = HEC18Calculations.effective_k1(k1_pier_shape, theta_attack)
                    k2 = HEC18Calculations.pier_k2(skew, L, a)
                    capped = round_nose and theta_attack <= 5.0

                    detail = next((d for d in self.project.get("piers_detail", []) if d["name"] == p_name), None)
                    if detail:
                        z_be = detail.get("z_day_be", detail.get("z_be", cdtn + detail.get("ho", -1.40)))
                        ho0 = round(z_be - cdtn, 3)
                        detail["ho"] = ho0
                        detail["z_be"] = z_be
                        detail["z_day_be"] = z_be
                        T_be = detail["T"]
                        f_dist = detail["f"]
                        apc = detail["apc"]
                        ap = detail["ap"]
                        S_coc = detail["S"]
                        m_hang = detail["m"]
                        n_cot = detail["n"]
                    else:
                        z_be = cdtn - 1.40
                        ho0 = -1.40
                        T_be = 2.0
                        f_dist = 1.85
                        apc = 6.0
                        ap = 1.20
                        S_coc = 4.20
                        m_hang = 2
                        n_cot = 3

                    aproj = max(ap, n_cot * ap)
                    ho = ho0 + gen_lower

                    z_be_disp = f"{z_be:.2f}"
                    ho_disp = f"{ho0:.2f}"

                    # 7.1 Trụ đơn
                    if y1 > 0.05 and v1 > 0:
                        vc_tru = HEC18Calculations.critical_velocity_vc(y1, d50_m)
                        ratio_v_vc = v1 / max(0.01, vc_tru)
                        fr1 = v1 / math.sqrt(G * y1)
                        kw_single = HEC18Calculations.kw_wide_pier(y1, a, fr1, ratio_v_vc, d50_m)
                        ys_pier_single, fr1 = HEC18Calculations.pier_scour_csu(y1, v1, a, k1_eff, k2, k3_val, kw_single, capped)
                    else:
                        vc_tru, ratio_v_vc, kw_single, ys_pier_single, fr1 = 0.0, 0.0, 1.0, 0.0, 0.0

                    note_single = "θ>5°: K1=1.0" if theta_attack > 5.0 else ("giới hạn 2.4a/3.0a" if capped else "")
                    cd_single = cdtn - (gen_lower + ys_pier_single)
                    k1_short = k1_pier_name.split(" (")[0]
                    self.tree_single_pier.insert("", tk.END, values=(
                        f"{stt_p}. {p_name}", f"{cdtn:.2f}", f"{y1:.2f}", f"{v1:.2f}", f"{fr1:.3f}",
                        f"{a:.2f}", k1_short, f"{k1_eff:.2f}", f"{skew:.1f}", f"{L:.2f}",
                        f"{k2:.3f}", k3_name.split(" (")[0], f"{k3_val:.2f}", f"{d50_mm:.3f}", f"{vc_tru:.2f}",
                        f"{ratio_v_vc:.2f}", f"{kw_single:.3f}", f"{ys_pier_single:.2f}", f"{cd_single:.2f}", note_single
                    ))

                    # 7.2 & 7.3 Trụ phức hợp (thân + bệ + cọc)
                    cp = HEC18Calculations.complex_pier(y1, v1, a, k1_eff, k2, k3_val, kw_single, capped,
                                                        ho, T_be, f_dist, apc, ap, S_coc, m_hang, n_cot, aproj)

                    ks_val = max(2.0 * d84_m, 1e-4)
                    yspier_lobe = cp["ys_pier"]
                    h1 = cp["h1"]
                    yf_lb = h1 + yspier_lobe * 0.5
                    y2_lb = cp["y2"]
                    h2_lb = cp["h2"]
                    v2_lb = cp["v2"]

                    if h1 <= 0 or y1 <= 0.05 or v1 <= 0:
                        ysfooting_lb, vf_lb, fr2_lb, kw_lb = 0.0, 0.0, 0.0, 1.0
                    else:
                        vf_lb = v2_lb * (math.log(10.93 * yf_lb / ks_val + 1.0) / math.log(10.93 * y2_lb / ks_val + 1.0))
                        fr2_lb = v2_lb / math.sqrt(G * y2_lb)
                        frf_lb = vf_lb / math.sqrt(G * yf_lb)
                        vc2 = HEC18Calculations.critical_velocity_vc(y2_lb, d50_m)
                        kw_lb = HEC18Calculations.kw_wide_pier(y2_lb, apc, frf_lb, vf_lb / max(0.01, vc2), d50_m)
                        ysfooting_lb = 2.0 * 1.0 * k2 * k3_val * kw_lb * (apc ** 0.65) * (yf_lb ** 0.35) * (frf_lb ** 0.43)

                    self.tree_lobe_1.insert("", tk.END, values=(
                        stt_p, f"{cdtn:.2f}", f"{y1:.2f}", f"{v1:.2f}", f"{cp['fr1']:.3f}", f"{a:.2f}",
                        f"{k1_eff:.2f}", f"{skew:.0f}", f"{L:.0f}", f"{k2:.2f}", f"{k3_val:.2f}",
                        f"{f_dist:.2f}", f"{ho:.2f}", f"{T_be:.2f}", f"{h1:.2f}", f"{cp['kh']:.2f}",
                        f"{d50_mm:.3f}", f"{vc_tru:.2f}", f"{ratio_v_vc:.2f}", f"{kw_single:.3f}", f"{yspier_lobe:.2f}"
                    ))
                    self.tree_lobe_2.insert("", tk.END, values=(
                        stt_p, f"{cdtn:.2f}", f"{y1:.2f}", f"{v1:.2f}", f"{yspier_lobe:.2f}",
                        f"{y2_lb:.2f}", f"{h2_lb:.2f}", f"{h1:.2f}", f"{yf_lb:.2f}", f"{v2_lb:.2f}",
                        f"{ks_val:.4f}", f"{vf_lb:.2f}", f"{apc:.2f}", f"{fr2_lb:.2f}", f"{kw_lb:.2f}", f"{ysfooting_lb:.2f}"
                    ))
                    ys_total_lobe = yspier_lobe + ysfooting_lb
                    cd_lobe = cdtn - (gen_lower + ys_total_lobe)
                    self.tree_lobe_3.insert("", tk.END, values=(
                        stt_p, p_name, f"{cdtn:.2f}", f"{z_be:.2f}", f"{ho0:.2f}",
                        f"{yspier_lobe:.2f}", f"{ysfooting_lb:.2f}", f"{ys_total_lobe:.2f}", f"{cd_lobe:.2f}"
                    ))

                    ys_final_chosen = cp["ys_total"]
                    cd_lococ = cdtn - (gen_lower + ys_final_chosen)
                    self.tree_lc_4.insert("", tk.END, values=(
                        stt_p, p_name, f"{cdtn:.2f}", f"{z_be:.2f}", f"{ho0:.2f}",
                        f"{cp['ys_pier']:.2f}", f"{cp['ys_pc']:.2f}", f"{cp['ys_pg']:.2f}",
                        f"{ys_final_chosen:.2f}", f"{cd_lococ:.2f}", cp["note"]
                    ))
                    stt_p += 1

                # TỔNG HỢP XÓI TẠI MỐ/TRỤ
                y_tot = gen_lower + ys_final_chosen
                z_scour = cdtn - y_tot

                self.tree_summary.insert("", tk.END, values=(
                    p_name, f"{px:.1f}", f"{cdtn:.2f}", z_be_disp, ho_disp, f"{y_deg:.2f}",
                    f"{ysc:.2f}", f"{ys_final_chosen:.2f}", f"{y_tot:.2f}", f"{z_scour:.2f}"
                ))

                self.scour_results.append({
                    "name": p_name, "x": px, "cdtn": cdtn, "z_be": z_be_disp, "ho": ho_disp,
                    "y1": y1, "v1": v1, "y_deg": y_deg, "ysc": ysc, "ys_local": ys_final_chosen,
                    "y_tot": y_tot, "z_scour": z_scour
                })

                plot_x.append(px)
                plot_scour_z.append(z_scour)

            # ---------------- Tab 8: Vẽ Scour Prism ----------------
            all_x = [pt["L_cum"] for pt in self.vh_data]
            all_z = [pt["z"] for pt in self.vh_data]
            self._render_scour_prism_plot(all_x, all_z, htk, y_deg, ysc, plot_x, plot_scour_z)

            self.calc_warnings = list(dict.fromkeys(warnings))
            self.nb.select(self.tab8)
            messagebox.showinfo("Thành công", f"Đã hoàn thành toàn bộ hệ thống tính toán xói cầu cho {self.project['bridge_name']}!")

        except Exception as e:
            messagebox.showerror("Lỗi thực thi", f"Quá trình tính toán gặp sự cố: {e}")

    # =========================================================================
    # DỮ LIỆU MẪU & CÁC THAO TÁC FILE
    # =========================================================================
    def _load_sample_data(self):
        self.project["cross_section"] = [
            [1, "M1 (Bờ trái)", -1.01, 0.0, "Mố cầu", 0.0, 1.70, 1.0],
            [2, "", 0.52, 14.01, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [3, "", 0.24, 50.00, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [4, "", -0.83, 23.49, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [5, "T1", -2.59, 21.74, "Trụ đơn", 2.0, 1.5, 1.1],
            [6, "", -1.43, 21.73, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [7, "", -2.01, 33.04, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [8, "T2", -2.10, 50.00, "Trụ đơn", 2.0, 1.5, 1.1],
            [9, "", -2.02, 37.61, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [10, "", -3.34, 35.15, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [11, "", -3.83, 49.98, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [12, "T3", -4.09, 12.71, "Trụ đơn", 2.0, 1.5, 1.1],
            [13, "", -3.63, 40.76, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [14, "T4", -2.89, 42.37, "Trụ đơn", 2.0, 1.5, 1.1],
            [15, "", -2.85, 31.42, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [16, "T5", -2.81, 28.91, "Trụ đơn", 2.0, 1.5, 1.1],
            [17, "", -1.13, 36.91, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [18, "", 0.44, 19.00, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [19, "M2 (Bờ phải)", -0.19, 6.71, "Mố cầu", 0.0, 1.70, 1.0]
        ]
        self.sync_all_details()
        self._refresh_tab1_table()

    def _refresh_tab1_table(self):
        self.tree_tab1.delete(*self.tree_tab1.get_children())
        htk = float(self.t1_entries["htk"].get()) if hasattr(self, 't1_entries') and "htk" in self.t1_entries else self.project["htk"]
        skew = float(self.t1_entries["skew"].get()) if hasattr(self, 't1_entries') and "skew" in self.t1_entries else self.project["skew"]
        cos_sk = math.cos(math.radians(skew))

        for row in self.project["cross_section"]:
            cdtn = float(row[2])
            l_cheo = float(row[3])
            l_ngang = l_cheo * cos_sk
            h = max(0.0, htk - cdtn)
            display_row = (row[0], row[1], f"{cdtn:.2f}", f"{l_cheo:.2f}", f"{l_ngang:.2f}", f"{h:.2f}", row[4], f"{float(row[5]):.2f}", f"{float(row[6]):.2f}")
            self.tree_tab1.insert("", tk.END, values=display_row)

    def action_new_project(self):
        if messagebox.askyesno("Tạo mới", "Tạo dự án mới? Dữ liệu hiện tại chưa lưu sẽ mất."):
            self.project["project_name"] = "Dự Án Mới"
            self.project["bridge_name"] = "Cầu Mới"
            self.project["cross_section"] = []
            self.project["piers_detail"] = []
            self.project["abutments_detail"] = []
            self._refresh_tab1_table()
            self.lbl_title.config(text="DỰ ÁN: CẦU MỚI | CÔNG TRÌNH: CẦU MỚI")

    def action_save_project(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if not file_path:
            return
        for k in self.t1_entries:
            try:
                self.project[k] = float(self.t1_entries[k].get())
            except Exception:
                pass
        self.project["k3_type"] = self.cb_k3.get()
        self.project["k1_type"] = self.cb_k1.get()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.project, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Thành công", f"Đã lưu file dự án tại:\n{file_path}")

    def action_open_project(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.project = {**copy.deepcopy(self._project_defaults), **data}
            self.lbl_title.config(text=f"DỰ ÁN: {self.project.get('project_name','').upper()} | CÔNG TRÌNH: {self.project.get('bridge_name','').upper()}")
            for k in self.t1_entries:
                if k in self.project:
                    self.t1_entries[k].delete(0, tk.END)
                    self.t1_entries[k].insert(0, str(self.project[k]))
            self.cb_k3.set(self.project.get("k3_type", HEC18Tables.DEFAULT_K3))
            self.cb_k1.set(self.project.get("k1_type", HEC18Tables.DEFAULT_PIER_K1))
            self.sync_all_details()
            self._refresh_tab1_table()
            messagebox.showinfo("Thành công", f"Đã mở dự án cầu: {self.project.get('bridge_name')}!")
        except Exception as e:
            messagebox.showerror("Lỗi mở file", f"Không đọc được file: {e}")

    def action_import_excel(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel Files", "*.xlsx *.xls")])
        if not file_path:
            return
        try:
            df = pd.read_excel(file_path)
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            str_cols = df.select_dtypes(include=['object']).columns.tolist()
            if len(num_cols) < 2:
                messagebox.showerror("Lỗi", "File Excel phải có ít nhất 2 cột số!")
                return

            col1, col2 = num_cols[0], num_cols[1]
            c1_vals, c2_vals = df[col1].dropna().values, df[col2].dropna().values
            is_c1_elev = any(v < 0 for v in c1_vals)
            is_c2_elev = any(v < 0 for v in c2_vals)
            c1_inc = all(c1_vals[i] <= c1_vals[i+1] for i in range(len(c1_vals)-1)) if len(c1_vals) > 1 else False
            c2_inc = all(c2_vals[i] <= c2_vals[i+1] for i in range(len(c2_vals)-1)) if len(c2_vals) > 1 else False

            if (c1_inc and not is_c1_elev) or is_c2_elev:
                x_col, z_col, x_is_cum = col1, col2, c1_inc
            else:
                x_col, z_col, x_is_cum = col2, col1, c2_inc

            name_col = str_cols[0] if str_cols else None
            self.project["cross_section"].clear()
            prev_x = 0.0

            for idx, r in df.iterrows():
                stt = idx + 1
                name = str(r[name_col]).strip() if name_col and pd.notna(r[name_col]) else ""
                if name.lower() in ["nan", "none"]:
                    name = ""
                raw_x = float(r[x_col])
                z_val = float(r[z_col])
                if x_is_cum:
                    l_cheo = 0.0 if idx == 0 else max(0.0, raw_x - prev_x)
                    prev_x = raw_x
                else:
                    l_cheo = max(0.0, raw_x)

                p_type = "Điểm tự nhiên" if not name else ("Mố cầu" if is_abut_name(name) else "Trụ đơn")
                a = 2.0 if p_type == "Trụ đơn" else 0.0
                L = 1.5 if p_type == "Trụ đơn" else (1.70 if p_type == "Mố cầu" else 0.0)
                k1 = 1.0 if is_abut_name(name) else 1.1
                self.project["cross_section"].append([stt, name, z_val, l_cheo, p_type, a, L, k1])

            self.sync_all_details()
            self._refresh_tab1_table()
            messagebox.showinfo("Thành công", f"Đã nạp {len(self.project['cross_section'])} điểm mặt cắt từ Excel!")
        except Exception as e:
            messagebox.showerror("Lỗi đọc Excel", f"Không thể đọc file: {e}")

    def action_export_excel(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")])
        if not file_path:
            return
        cols = ["STT", "TenMoTru", "CaoDoCDTN", "L_cheo", "PhanLoai", "BeRong_a", "ChieuDai_L", "HeSoK1"]
        df = pd.DataFrame(self.project["cross_section"], columns=cols)
        df.to_excel(file_path, index=False)
        messagebox.showinfo("Thành công", f"Đã xuất ra Excel:\n{file_path}")

    def swap_columns_manual(self):
        cs = self.project["cross_section"]
        if not cs:
            return
        for r in cs:
            z_old = r[2]
            l_old = r[3]
            r[2] = l_old
            r[3] = abs(z_old)
        self._refresh_tab1_table()
        messagebox.showinfo("Thành công", "Đã hoán đổi cột Cao độ CĐTN và Khoảng cách L chuẩn xác!")

    def dialog_edit_metadata(self):
        dlg = tk.Toplevel(self)
        dlg.title("Cấu Hình Dự Án & Thông Tin Công Trình Cầu")
        dlg.geometry("520x340")
        dlg.grab_set()

        fields = [
            ("Tên Dự Án:", "project_name"),
            ("Tên Cầu (Công trình):", "bridge_name"),
            ("Tên Sông / Tuyến Đường:", "river_name"),
            ("Tần Suất Thiết Kế Lũ P%:", "frequency_p"),
            ("Kỹ Sư Thiết Kế Thủy Lực:", "engineer"),
        ]
        dlg_entries = {}
        for r, (lbl, key) in enumerate(fields):
            ttk.Label(dlg, text=lbl).grid(row=r, column=0, sticky=tk.W, padx=15, pady=8)
            ent = ttk.Entry(dlg, width=35)
            ent.insert(0, str(self.project[key]))
            ent.grid(row=r, column=1, sticky=tk.W, padx=15, pady=8)
            dlg_entries[key] = ent

        def save():
            for k, e in dlg_entries.items():
                self.project[k] = e.get().strip()
            self.lbl_title.config(text=f"DỰ ÁN: {self.project['project_name'].upper()} | CÔNG TRÌNH: {self.project['bridge_name'].upper()}")
            dlg.destroy()

        ttk.Button(dlg, text="Lưu Cấu Hình", command=save).grid(row=len(fields), column=0, columnspan=2, pady=16)

    def action_export_report(self):
        if not self.scour_results:
            messagebox.showwarning("Cảnh báo", "Vui lòng tính toán trước khi xuất báo cáo!")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text file", "*.txt")])
        if not file_path:
            return

        lines = [
            "=======================================================================================================",
            "                      BÁO CÁO THUYẾT MINH TÍNH TOÁN XÓI CẦU THEO TIÊU CHUẨN HEC-18                     ",
            "=======================================================================================================",
            f"DỰ ÁN               : {self.project['project_name']}",
            f"CÔNG TRÌNH CẦU      : {self.project['bridge_name']}",
            f"SÔNG / TUYẾN        : {self.project['river_name']}",
            f"TẦN SUẤT THIẾT KẾ   : P = {self.project['frequency_p']}",
            f"KỸ SƯ THỰC HIỆN     : {self.project['engineer']}",
            "-------------------------------------------------------------------------------------------------------",
            f"{'Mố/Trụ':<10} {'X (m)':<10} {'CĐTN(m)':<10} {'y_deg(m)':<10} {'y_sc(m)':<10} {'ys(m)':<10} {'Y_tot(m)':<10} {'CĐ đáy xói(m)':<14}",
            "-------------------------------------------------------------------------------------------------------"
        ]
        for r in self.scour_results:
            lines.append(
                f"{r['name']:<10} {r['x']:<10.1f} {r['cdtn']:<10.2f} {r['y_deg']:<10.2f} "
                f"{r['ysc']:<10.2f} {r['ys_local']:<10.2f} {r['y_tot']:<10.2f} {r['z_scour']:<14.2f}"
            )
        lines.append("=======================================================================================================")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Thành công", f"Đã xuất báo cáo kỹ thuật tại:\n{file_path}")


# =============================================================================
# KHỞI CHẠY CHƯƠNG TRÌNH
# =============================================================================
if __name__ == "__main__":
    app = MainScourApplication()
    app.mainloop()