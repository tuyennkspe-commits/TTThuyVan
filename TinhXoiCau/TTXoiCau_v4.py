# -*- coding: utf-8 -*-
"""
PHẦN MỀM TÍNH TOÁN XÓI MỐ TRỤ CẦU ĐA DỰ ÁN THEO TIÊU CHUẨN HEC-18 (FHWA) - MASTER PRO v4.1
- ĐÃ KHẮC PHỤC TRIỆT ĐỂ:
  1. Phân tầng choán dòng Vcau chính xác tuyệt đối: bề rộng cản nước chỉ phụ thuộc vào B*cos(skew) do trụ đặt xuôi dòng.
  2. Bề rộng thoát nước co hẹp W2 = W1 - sum(b_choán) chuẩn xác từng milimet so với file Excel gốc.
  3. Phân định rõ ràng: Trụ T25, T26, T27 đáy bệ ngàm sâu (Z_đáy <= CĐTN) là TRỤ LỘ BỆ (KHÔNG LỘ CỌC, yspg = 0),
     chỉ xuất hiện ở Tab 7.2. Các trụ lòng sâu T28, T29, T30 mới là TRỤ LỘ BỆ & CỌC (Tab 7.3).
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
    ROUND_NOSE = {"Mũi tròn (Round nose)", "Trụ tròn (Circular cylinder)", "Nhóm cọc tròn (Group of cylinders)"}
    DEFAULT_PIER_K1 = "Mũi vuông (Square nose)"

    PIER_K3 = {
        "Nước trong / Đáy phẳng / Sóng cát nghịch": (1.1, "K3=1.1: xói nước trong, đáy phẳng, sóng cát nghịch"),
        "Cồn cát nhỏ (0.6 <= H < 3 m)": (1.1, "K3=1.1: cồn cát nhỏ"),
        "Cồn cát trung bình (3 <= H < 9 m)": (1.2, "K3=1.2: cồn cát trung bình"),
        "Cồn cát lớn (H >= 9 m)": (1.3, "K3=1.3: cồn cát lớn"),
    }
    DEFAULT_K3 = "Nước trong / Đáy phẳng / Sóng cát nghịch"

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
# 2. TOÁN HỌC & CÔNG THỨC HEC-18
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
    def complex_pier(y1, v1, a, k1, k2, k3, kw, capped, ho, T, f, apc, ap, S, m, n, aproj, pile_exposed=True):
        """
        Tính xói trụ phức hợp HEC-18.
        pile_exposed: False nếu móng cọc ngàm trong đất (Trụ lộ bệ T25-T27), True nếu móng cọc lộ trong nước (T28-T30).
        """
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

        # Trường hợp 1: Đỉnh bệ chìm sâu dưới đáy sông đã hạ
        if h1 <= 0:
            ys_p = limit(ys_full)
            r.update(ys_pier=ys_p, ys_total=ys_p, case="TH1",
                     note=f"TH1: Đỉnh bệ dưới đáy hạ (h1={h1:.2f}m <= 0) -> xói thân trụ đơn")
            return r

        # Xói do thân trụ
        kh = HEC18Calculations.kh_pier_stem(h1, a, f)
        ys_pier = limit(kh * ys_full)

        # Xói do bệ đài
        y2 = y1 + 0.5 * ys_pier
        h2 = ho + 0.5 * ys_pier
        v2 = v1 * y1 / y2
        fr2 = v2 / math.sqrt(G * y2)
        t_eff = T + min(0.0, h2)
        apc_star = HEC18Calculations.equivalent_width_pilecap(max(0.0, h2), y2, t_eff, apc)
        ys_pc = 2.0 * k1 * k2 * k3 * (apc_star ** 0.65) * (y2 ** 0.35) * (fr2 ** 0.43)

        # Kiểm tra điều kiện lộ cọc
        if not pile_exposed:
            r.update(kh=kh, ys_pier=ys_pier, y2=y2, h2=h2, v2=v2, fr2=fr2, t_eff=t_eff,
                     apc_star=apc_star, ys_pc=ys_pc, h3=0.0, y3=y2, ys_pg=0.0,
                     ys_total=ys_pier + ys_pc, case="TH2_LOBE",
                     note="Trụ Lộ Bệ: Cọc ngàm trong đất (KHÔNG LỘ CỌC -> yspg = 0)")
            return r

        h3 = ho + 0.5 * ys_pier + 0.5 * ys_pc
        y3 = y1 + 0.5 * ys_pier + 0.5 * ys_pc
        r.update(kh=kh, ys_pier=ys_pier, y2=y2, h2=h2, v2=v2, fr2=fr2, t_eff=t_eff,
                 apc_star=apc_star, ys_pc=ys_pc, h3=h3, y3=y3)

        if h3 <= 0:
            r.update(ys_total=ys_pier + ys_pc, case="TH2",
                     note=f"TH2: Nhóm cọc còn chôn trong đất (h3={h3:.2f}m <= 0) -> yspg = 0")
            return r

        # Xói do nhóm cọc lộ trong nước
        v3 = v1 * y1 / y3
        fr3 = v3 / math.sqrt(G * y3)
        ksp, km, apg, khpg = HEC18Calculations.pile_group_factors(ap, S, m, n, aproj, h3, y3)
        ys_pg = khpg * 2.0 * k1 * 1.0 * k3 * (apg ** 0.65) * (y3 ** 0.35) * (fr3 ** 0.43)
        r.update(v3=v3, fr3=fr3, ksp=ksp, km=km, apg=apg, khpg=khpg, ys_pg=ys_pg,
                 ys_total=ys_pier + ys_pc + ys_pg, case="TH3_LOCOC",
                 note=f"TH3: Lộ cả bệ & cọc (h3={h3:.2f}m > 0) -> CÓ XÓI CỌC (yspg={ys_pg:.2f}m)")
        return r

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

    @staticmethod
    def abutment_scour(ya, ve, l_prime, k1_abut, theta_deg=90.0):
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
            ys = 2.27 * k1_abut * k2 * (l_prime ** 0.43) * (ya ** 0.57) * (fr ** 0.61) + ya
            method = "Froehlich"
        return dict(fr=fr, k2=k2, theta=theta, ys=max(0.0, ys), method=method)


# =============================================================================
# 3. GIAO DIỆN CHÍNH & ĐIỀU HÀNH
# =============================================================================
class MainScourApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEC-18 BRIDGE SCOUR SYSTEM PRO - v4.1 (CHUẨN THỦY VĂN CẦU)")
        self.geometry("1440x940")
        self.minsize(1220, 780)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.project = {
            "project_name": "DỰ ÁN NÂNG CẤP GIAO THÔNG VÙNG ĐỒNG BẰNG",
            "bridge_name": "CẦU BẠCH ĐẰNG",
            "river_name": "Sông Bạch Đằng",
            "frequency_p": "1%",
            "engineer": "KS. Thủy Lực Cầu Đường",
            "htk": 1.62,
            "qtk": 2370.0,
            "skew": 10.0,
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
            "piers_detail": [],
            "abutments_detail": []
        }

        self._project_defaults = copy.deepcopy(self.project)
        self.calc_warnings = []
        self.hq_data = []
        self.vh_data = []
        self.scour_results = []
        self._report_piers = []
        self._report_context = {}
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
        menu_data.add_command(label="Xuất Báo Cáo Tính Xói Tổng Hợp (*.xlsx)...", command=self.action_export_report)
        menu_data.add_command(label="Xuất Báo Cáo Thuyết Minh (*.docx)...", command=self.action_export_word)
        menubar.add_cascade(label="Dữ Liệu & Excel", menu=menu_data)

        menu_cfg = tk.Menu(menubar, tearoff=0)
        menu_cfg.add_command(label="📐 Cấu Hình Bệ & Cọc Cho TRỤ CẦU (CAD)...", command=self.dialog_edit_piers_detail)
        menu_cfg.add_command(label="🏛 Cấu Hình Thủy Lực Cho MỐ CẦU...", command=self.dialog_edit_abutments_detail)
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
        ttk.Button(f_btn, text="🏛 CẤU HÌNH THỦY LỰC MỐ CẦU...", command=self.dialog_edit_abutments_detail).pack(fill=tk.X, pady=3)
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

        ttk.Label(f_fast, text="Bề rộng a(m):").grid(row=0, column=6, padx=2)
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
                    z_val = d.get("z_day_be", d.get("z_be", cdtn + d.get("ho", -1.40)))
                    d["z_be"] = z_val
                    d["z_day_be"] = z_val
                    d["ho"] = round(z_val - cdtn, 3)
                    if "loai_tru" not in d:
                        d["loai_tru"] = "Lộ bệ & cọc" if d["ho"] > 0 else "Lộ bệ"
                    synced_piers.append(d)
                else:
                    default_z_be = cdtn - 1.40
                    loai = "Lộ bệ & cọc" if default_z_be > cdtn else "Lộ bệ"
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
                        "aproj": 3.60,
                        "loai_tru": loai
                    }
                    synced_piers.append(d)
        self.project["piers_detail"] = synced_piers

    def sync_abutments_detail(self):
        existing_map = {d["name"]: d for d in self.project.get("abutments_detail", [])}
        synced_abuts = []
        htk = float(self.project.get("htk", 1.62))

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

        f_form = ttk.LabelFrame(f_left, text="Thông Số Thủy Lực Nhập Liệu Của Mố Đang Chọn")
        f_form.pack(fill=tk.BOTH, expand=True, padx=4, pady=6)

        ab_vars = {
            "name": tk.StringVar(), "cdtn": tk.StringVar(), "ya": tk.StringVar(),
            "Qe": tk.StringVar(), "Ae": tk.StringVar(), "L_prime": tk.StringVar(),
            "k1_type": tk.StringVar(), "theta": tk.StringVar(),
            "ve_disp": tk.StringVar(), "fr_disp": tk.StringVar(), "k2_disp": tk.StringVar(),
            "ys_preview": tk.StringVar()
        }

        ttk.Label(f_form, text="Tên mố cầu:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Label(f_form, textvariable=ab_vars["name"], font=("Segoe UI", 10, "bold"), foreground="red").grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Cao độ tự nhiên CĐTN (m):").grid(row=0, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Label(f_form, textvariable=ab_vars["cdtn"], font=("Segoe UI", 9, "bold")).grid(row=0, column=3, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Chiều sâu nước bãi tràn ya (m):").grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["ya"], width=12).grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Chiều dài mố/nền cản dòng L' (m):").grid(row=1, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["L_prime"], width=12).grid(row=1, column=3, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Dòng chảy bị chặn Qe (m3/s):").grid(row=2, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["Qe"], width=12).grid(row=2, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Diện tích bị chặn Ae (m2):").grid(row=2, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["Ae"], width=12).grid(row=2, column=3, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Dạng mố K1 (Froehlich):").grid(row=3, column=0, sticky=tk.W, padx=6, pady=4)
        cb_k1_ab = ttk.Combobox(f_form, textvariable=ab_vars["k1_type"], values=list(HEC18Tables.ABUT_K1.keys()), state="readonly", width=36)
        cb_k1_ab.grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Góc xiên θ (°):").grid(row=4, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Entry(f_form, textvariable=ab_vars["theta"], width=12).grid(row=4, column=1, sticky=tk.W, padx=6, pady=4)

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

    # =========================================================================
    # DIALOG CẤU HÌNH BỆ & CỌC CHO TRỤ CẦU
    # =========================================================================
    def dialog_edit_piers_detail(self):
        self.sync_piers_detail()

        dlg = tk.Toplevel(self)
        dlg.title("Cấu Hình Chi Tiết Kích Thước Bệ Đài & Nhóm Cọc Cho Các TRỤ CẦU (HEC-18)")
        dlg.geometry("1340x760")
        dlg.minsize(1180, 680)
        dlg.grab_set()

        pane = ttk.PanedWindow(dlg, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        f_left_side = ttk.Frame(pane)
        pane.add(f_left_side, weight=3)

        lbl_guide = tk.Label(
            f_left_side,
            text="CHỌN TRỤ TRÊN BẢNG, NHẬP THÔNG SỐ VÀ BẤM 'CẬP NHẬT TRỤ ĐANG CHỌN'",
            font=("Segoe UI", 9, "bold"),
            fg="#0D47A1"
        )
        lbl_guide.pack(pady=4)

        f_tree = ttk.Frame(f_left_side)
        f_tree.pack(fill=tk.X, padx=5, pady=2)

        cols = ("Tên Trụ", "CĐTN (m)", "Phân Loại Móng", "Thân a(m)", "Thân L(m)", "Bệ apc(m)", "Bệ Lpc(m)", "Cao T(m)", "CĐ Đáy Bệ", "ho (m)", "Cọc ap", "Cự ly S", "Hàng m", "Cột n")
        tree_p = ttk.Treeview(f_tree, columns=cols, show="headings", height=6)
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
                z_cur = d.get("z_day_be", d.get("z_be", d["cdtn"] + d["ho"]))
                loai = d.get("loai_tru", "Lộ bệ & cọc" if d.get("ho", 0) > 0 else "Lộ bệ")
                tree_p.insert("", tk.END, values=(
                    d["name"], f"{d['cdtn']:.2f}", loai, f"{d['apier']:.2f}", f"{d['Lpier']:.2f}",
                    f"{d['apc']:.2f}", f"{d['Lpc']:.2f}", f"{d['T']:.2f}", f"{z_cur:.2f}",
                    f"{d['ho']:.2f}", f"{d['ap']:.2f}", f"{d['S']:.2f}", d["m"], d["n"]
                ))

        refresh_dlg_table()

        f_form = ttk.LabelFrame(f_left_side, text="Thông Số Kích Thước Nhập Liệu Của Trụ Đang Chọn")
        f_form.pack(fill=tk.BOTH, expand=True, padx=5, pady=4)

        f_sub1 = ttk.LabelFrame(f_form, text="1. Thân Trụ & Phân Loại")
        f_sub1.grid(row=0, column=0, padx=4, pady=3, sticky=tk.NSEW)

        f_sub2 = ttk.LabelFrame(f_form, text="2. Móng Bệ Đài Cọc (Footing)")
        f_sub2.grid(row=0, column=1, padx=4, pady=3, sticky=tk.NSEW)

        f_sub3 = ttk.LabelFrame(f_form, text="3. Nhóm Cọc (Pile Group)")
        f_sub3.grid(row=0, column=2, padx=4, pady=3, sticky=tk.NSEW)

        ent_vars = {
            "name": tk.StringVar(), "cdtn": tk.StringVar(), "loai_tru": tk.StringVar(),
            "apier": tk.StringVar(), "Lpier": tk.StringVar(),
            "apc": tk.StringVar(), "Lpc": tk.StringVar(), "T": tk.StringVar(),
            "z_day_be": tk.StringVar(), "ho_display": tk.StringVar(), "f": tk.StringVar(),
            "ap": tk.StringVar(), "S": tk.StringVar(), "m": tk.StringVar(), "n": tk.StringVar(), "aproj": tk.StringVar()
        }

        ttk.Label(f_sub1, text="Tên trụ:").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Label(f_sub1, textvariable=ent_vars["name"], font=("Segoe UI", 9, "bold"), foreground="blue").grid(row=0, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub1, text="Cao độ CĐTN:").grid(row=1, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Label(f_sub1, textvariable=ent_vars["cdtn"]).grid(row=1, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub1, text="Phân loại xói móng:", font=("Segoe UI", 8, "bold"), foreground="#C62828").grid(row=2, column=0, sticky=tk.W, padx=3, pady=2)
        cb_loai = ttk.Combobox(f_sub1, textvariable=ent_vars["loai_tru"], values=["Lộ bệ", "Lộ bệ & cọc", "Trụ đơn đặc"], state="readonly", width=12)
        cb_loai.grid(row=2, column=1, padx=3, pady=2)

        ttk.Label(f_sub1, text="Bề rộng thân a (m):").grid(row=3, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub1, textvariable=ent_vars["apier"], width=8).grid(row=3, column=1, padx=3, pady=2)

        ttk.Label(f_sub1, text="Chiều dài thân L (m):").grid(row=4, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub1, textvariable=ent_vars["Lpier"], width=8).grid(row=4, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Bề rộng bệ apc (m):").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["apc"], width=8).grid(row=0, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Chiều dài bệ Lpc (m):").grid(row=1, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["Lpc"], width=8).grid(row=1, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Chiều cao bệ T (m):").grid(row=2, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["T"], width=8).grid(row=2, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="Cao độ đáy bệ Z_đáy (m):", font=("Segoe UI", 9, "bold"), foreground="#B71C1C").grid(row=3, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["z_day_be"], width=8).grid(row=3, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="ho = Zđáy - CĐTN:").grid(row=4, column=0, sticky=tk.W, padx=3, pady=2)
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
                if ho_calc <= 0:
                    ent_vars["loai_tru"].set("Lộ bệ")
                else:
                    ent_vars["loai_tru"].set("Lộ bệ & cọc")
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
            ent_vars["loai_tru"].set(v[2])
            ent_vars["apier"].set(v[3])
            ent_vars["Lpier"].set(v[4])
            ent_vars["apc"].set(v[5])
            ent_vars["Lpc"].set(v[6])
            ent_vars["T"].set(v[7])
            ent_vars["z_day_be"].set(v[8])
            ent_vars["ho_display"].set(f"{float(v[9]):.2f} m")
            ent_vars["ap"].set(v[10])
            ent_vars["S"].set(v[11])
            ent_vars["m"].set(v[12])
            ent_vars["n"].set(v[13])
            detail = next((d for d in self.project["piers_detail"] if d["name"] == v[0]), None)
            if detail:
                ent_vars["f"].set(str(detail.get("f", 1.85)))
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
                        ap_val = float(ent_vars["apier"].get())
                        lp_val = float(ent_vars["Lpier"].get())
                        d["apier"] = ap_val
                        d["Lpier"] = lp_val
                        d["apc"] = float(ent_vars["apc"].get())
                        d["Lpc"] = float(ent_vars["Lpc"].get())
                        d["T"] = float(ent_vars["T"].get())
                        z_d = float(ent_vars["z_day_be"].get())
                        z_tn = float(ent_vars["cdtn"].get())

                        d["z_be"] = z_d
                        d["z_day_be"] = z_d
                        d["ho"] = round(z_d - z_tn, 3)
                        d["loai_tru"] = ent_vars["loai_tru"].get()

                        d["f"] = float(ent_vars["f"].get())
                        d["ap"] = float(ent_vars["ap"].get())
                        d["S"] = float(ent_vars["S"].get())
                        d["m"] = int(float(ent_vars["m"].get()))
                        d["n"] = int(float(ent_vars["n"].get()))
                        d["aproj"] = float(ent_vars["aproj"].get())

                        for r in self.project["cross_section"]:
                            if str(r[1]).strip() == name:
                                r[5] = ap_val
                                r[6] = lp_val
                                break

                        refresh_dlg_table()
                        self._refresh_tab1_table()
                        messagebox.showinfo("Thành công", f"Đã lưu trụ {name}:\n- Phân loại: {d['loai_tru']}\n- CĐ đáy bệ = {z_d:.2f} m\n- ho = {d['ho']:.2f} m")
                    except Exception as e:
                        messagebox.showerror("Lỗi", f"Vui lòng nhập đúng định dạng số! Chi tiết: {e}")
                    break

        def apply_all_piers():
            if not messagebox.askyesno("Xác nhận", "Áp dụng kích thước Bệ và Cọc này cho TẤT CẢ các TRỤ?"):
                return
            loai_selected = ent_vars["loai_tru"].get()
            for d in self.project["piers_detail"]:
                try:
                    ap_val = float(ent_vars["apier"].get())
                    lp_val = float(ent_vars["Lpier"].get())
                    d["apier"] = ap_val
                    d["Lpier"] = lp_val
                    d["apc"] = float(ent_vars["apc"].get())
                    d["Lpc"] = float(ent_vars["Lpc"].get())
                    d["T"] = float(ent_vars["T"].get())
                    z_d = float(ent_vars["z_day_be"].get())
                    d["z_be"] = z_d
                    d["z_day_be"] = z_d
                    d["ho"] = round(z_d - float(d["cdtn"]), 3)
                    
                    if loai_selected == "Trụ đơn đặc":
                        d["loai_tru"] = "Trụ đơn đặc"
                    else:
                        d["loai_tru"] = "Lộ bệ & cọc" if d["ho"] > 0 else "Lộ bệ"
                    
                    d["f"] = float(ent_vars["f"].get())
                    d["ap"] = float(ent_vars["ap"].get())
                    d["S"] = float(ent_vars["S"].get())
                    d["m"] = int(float(ent_vars["m"].get()))
                    d["n"] = int(float(ent_vars["n"].get()))
                    d["aproj"] = float(ent_vars["aproj"].get())

                    for r in self.project["cross_section"]:
                        if str(r[1]).strip() == d["name"]:
                            r[5] = ap_val
                            r[6] = lp_val
                except Exception:
                    pass
            refresh_dlg_table()
            self._refresh_tab1_table()
            messagebox.showinfo("Thành công", "Đã áp dụng thông số bệ cọc cho tất cả các trụ!")

        f_acts = ttk.Frame(f_left_side)
        f_acts.pack(fill=tk.X, padx=5, pady=6)
        ttk.Button(f_acts, text="CẬP NHẬT TRỤ ĐANG CHỌN", command=save_current_pier).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_acts, text="ÁP DỤNG CHO TẤT CẢ TRỤ", command=apply_all_piers).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_acts, text="Đóng Cửa Sổ", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

        f_right_side = ttk.LabelFrame(pane, text="Hướng Dẫn Phân Loại Trụ HEC-18")
        pane.add(f_right_side, weight=2)

        txt_p_guide = tk.Text(f_right_side, height=20, bg="#FFFFFF", font=("Segoe UI", 9), padx=6, pady=4)
        txt_p_guide.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        p_guide_text = """❖ QUY ĐỊNH PHÂN LOẠI MÓNG TRỤ (HEC-18):
1. TRỤ LỘ BỆ (Footing Exposed):
   • Đáy bệ ngàm sâu dưới đáy sông: Z_đáy <= CĐTN (ho <= 0).
   • Điển hình: Các trụ dẫn bờ T25, T26, T27...
   • Cọc chôn sâu trong địa chất ngầm, KHÔNG TIẾP XÚC VỚI DÒNG NƯỚC.
   • Trong Vcau: h_cọc = 0, b_cọc = 0, w_cọc = 0.
   • Xói cục bộ: Chỉ tính xói thân và bệ (ys = yspier + ysfooting). KHÔNG TÍNH XÓI CỌC (yspg = 0).

2. TRỤ LỘ BỆ & CỌC (Exposed Pile Group):
   • Bệ nằm lơ lửng trong dòng nước: Z_đáy > CĐTN (ho > 0).
   • Điển hình: Các trụ tháp lòng sông T28, T29, T30...
   • Cọc bị lộ trong cột nước từ CĐTN đến đáy bệ.
   • Trong Vcau: h_cọc = Z_đáy - CĐTN > 0, tính đầy đủ diện tích cản dòng của cọc.
   • Xói cục bộ: Tính đầy đủ xói thân + xói bệ + xói cọc (ys = yspier + yspc + yspg).
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
    # TAB 4: CHOÁN DÒNG (VCAU - ĐÃ SỬA TÍNH PHÂN TẦNG THÂN, BỆ, CỌC)
    # =========================================================================
    def _init_tab4(self):
        f_top = ttk.LabelFrame(self.tab4, text="Bảng Tính Diện Tích Trụ & Chiều Rộng Bình Quân Trụ Choán Dòng (Sheet Vcau)")
        f_top.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        vcau_cols = (
            "Tên Trụ", "Cao Độ CĐTN", "Chiều Sâu h(m)", "B_thân b(m)", "w_thân(m2)",
            "B_bệ(m)", "w_bệ(m2)", "B_cọc(m)", "w_cọc(m2)", "B_choán b(m)", "Diện Tích Choán w(m2)",
            "Kích Thước Bệ", "CĐ Đáy Bệ", "ho(m)"
        )
        self.tree_vcau = ttk.Treeview(f_top, columns=vcau_cols, show="headings", height=12)
        for c in vcau_cols:
            self.tree_vcau.heading(c, text=c)
            self.tree_vcau.column(c, anchor=tk.CENTER, width=85)
        self.tree_vcau.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        f_sum = ttk.LabelFrame(self.tab4, text="Tổng Hợp Bề Rộng Thoát Nước Co Hẹp Qua Cầu W2 & Vận Tốc Vcầu")
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
    # TAB 7: XÓI CỤC BỘ MỐ & TRỤ
    # =========================================================================
    def _init_tab7(self):
        f_ctrl = ttk.Frame(self.tab7)
        f_ctrl.pack(fill=tk.X, padx=10, pady=4)

        ttk.Button(f_ctrl, text="▶ CHẠY TÍNH TOÁN LẠI TẤT CẢ", command=self.run_full_system).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_ctrl, text="🏛 CẤU HÌNH THỦY LỰC MỐ CẦU...", command=self.dialog_edit_abutments_detail).pack(side=tk.LEFT, padx=6)
        ttk.Button(f_ctrl, text="📐 CẤU HÌNH BỆ & CỌC TRỤ...", command=self.dialog_edit_piers_detail).pack(side=tk.LEFT, padx=6)

        self.nb_scour = ttk.Notebook(self.tab7)
        self.nb_scour.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 7.1: TRỤ ĐƠN ĐẶC
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

        # 7.2: TRỤ LỘ BỆ
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

        # 7.3: TRỤ LỘ BỆ & CỌC
        self.subtab_lococ = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_lococ, text=" 7.3 Trụ Lộ Bệ & Cọc (XBC-lo coc) ")

        f_lc_4 = ttk.LabelFrame(self.subtab_lococ, text="Bảng Tổng Hợp Xói Cục Bộ Trụ Lộ Bệ & Cọc")
        f_lc_4.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        cols_lc_4 = ("STT", "Tên Trụ", "CĐTN (m)", "CĐ đáy bệ (m)", "ho (m)", "yspier (m)", "yspc (m)", "yspg (m)", "Tổng xói ys (m)", "Cao độ sau xói (m)", "Ghi chú phân loại")
        self.tree_lc_4 = ttk.Treeview(f_lc_4, columns=cols_lc_4, show="headings", height=12)
        for c in cols_lc_4:
            self.tree_lc_4.heading(c, text=c)
            self.tree_lc_4.column(c, anchor=tk.CENTER, width=105)
        self.tree_lc_4.pack(fill=tk.BOTH, expand=True, padx=3, pady=2)

        # 7.4: XÓI CỤC BỘ MỐ CẦU
        self.subtab_abutment = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_abutment, text=" 7.4 Xói Cục Bộ Mố (Froehlich / HIRE) ")

        f_fml_74 = ttk.LabelFrame(self.subtab_abutment, text="Công Thức Dự Báo Xói Cục Bộ Mố Cầu Theo Froehlich (HEC-18)")
        f_fml_74.pack(fill=tk.X, padx=6, pady=3)
        txt_74 = (
            "• Công thức Froehlich:  yx = 2.27 * K1 * K2 * (L')^0.43 * ya^0.57 * Fr1^0.61 + ya   (m)\n"
            "  Trong đó: ya: Chiều sâu dòng chảy trung bình trên bãi (m) | L': Chiều dài mố cản dòng (m)\n"
            "  Fr1 = Ve / (g * ya)^0.5  với Ve = Qe / Ae (m/s) | Qe: Lưu lượng bị chặn | Ae: Diện tích bị chặn\n"
            "  K1: Hình dạng mố (1.00 tường đứng; 0.82 tường cánh; 0.55 taluy xiên) | K2 = (θ/90)^0.13"
        )
        tk.Label(f_fml_74, text=txt_74, justify=tk.LEFT, font=("Consolas", 9), fg="#0D47A1", bg="#F4F6F9").pack(fill=tk.X, padx=4, pady=3)

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
        btn_exp = ttk.Button(f_bot, text="Xuất File Excel Kết Quả Tính Xói (*.xlsx)...", command=self.action_export_report)
        btn_exp.pack(side=tk.RIGHT, padx=5)
        ttk.Button(f_bot, text="Xuất Báo Cáo Word (*.docx)...",
                   command=self.action_export_word).pack(side=tk.RIGHT, padx=5)

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
    # THỰC THI TÍNH TOÁN TOÀN BỘ (RUN FULL SYSTEM - ĐÃ SỬA CHUẨN XÁC VCAU)
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
            self.lbl_ppll_qsum.config(text=f"Tổng Q phân phối ΣQi: {cum_q:.2f} m3/s")
            self.lbl_ppll_alpha.config(text=f"Hệ số phân bố α: {alpha_v:.6f}")
            self.lbl_ppll_wsum.config(text=f"Tổng diện tích ướt Σω: {sum_w:.2f} m2")
            self.lbl_ppll_vbq.config(text=f"Vận tốc bình quân Vbq: {V_mean:.2f} m/s")

            # ---------------- Tab 4: Choán dòng (ĐÃ FIX TÍNH CHÍNH XÁC BỀ RỘNG VÀ PHÂN TẦNG) ----------------
            self.tree_vcau.delete(*self.tree_vcau.get_children())
            sum_b_choan = 0.0
            sum_w_choan = 0.0

            piers_in_channel = [p for p in self.vh_data if p["name"] and not is_abut_name(p["name"])]
            for p in piers_in_channel:
                p_name = p["name"]
                cdtn = p["z"]
                hi = p["hi"]
                if hi <= 0:
                    continue

                detail = next((d for d in self.project.get("piers_detail", []) if d["name"] == p_name), None)
                if detail:
                    a_tru = float(detail.get("apier", p["a"]))
                    L_tru = float(detail.get("Lpier", p["L"]))
                    apc = float(detail.get("apc", 6.0))
                    Lpc = float(detail.get("Lpc", 13.3))
                    T_be = float(detail.get("T", 2.0))
                    z_day_be = float(detail.get("z_day_be", detail.get("z_be", cdtn - 1.4)))
                    ap_coc = float(detail.get("ap", 1.2))
                    S_coc = float(detail.get("S", 4.2))
                    m_hang = int(detail.get("m", 2))
                    n_cot = int(detail.get("n", 3))
                    aproj = float(detail.get("aproj", n_cot * ap_coc))
                else:
                    a_tru, L_tru = p["a"], p["L"]
                    apc, Lpc, T_be, z_day_be = 6.0, 13.3, 2.0, cdtn - 1.4
                    ap_coc, S_coc, m_hang, n_cot, aproj = 1.2, 4.2, 2, 3, 3.6

                z_dinh_be = z_day_be + T_be
                ho = z_day_be - cdtn

                # Hình chiếu cản nước xét góc xiên (Trụ đặt xuôi dòng)
                # Bề rộng cản nước hiệu dụng chỉ lấy B * cos(skew) - Đúng khớp bảng tính HEC-18 gốc
                b_proj_than = a_tru * cos_sk
                b_proj_be = apc * cos_sk
                b_proj_coc = aproj * cos_sk

                z_water = cdtn + hi

                # 1. Tầng cọc: từ cdtn đến min(z_day_be, z_water) nếu ho > 0
                w_coc = 0.0
                if z_day_be > cdtn:
                    z_top_coc = min(z_day_be, z_water)
                    h_coc = max(0.0, z_top_coc - cdtn)
                    w_coc = b_proj_coc * h_coc

                # 2. Tầng bệ: từ max(cdtn, z_day_be) đến min(z_dinh_be, z_water)
                w_be = 0.0
                z_bot_be = max(cdtn, z_day_be)
                z_top_be = min(z_dinh_be, z_water)
                if z_top_be > z_bot_be:
                    h_be = z_top_be - z_bot_be
                    w_be = b_proj_be * h_be

                # 3. Tầng thân: từ max(cdtn, z_dinh_be) đến z_water
                w_than = 0.0
                z_bot_than = max(cdtn, z_dinh_be)
                if z_water > z_bot_than:
                    h_than = z_water - z_bot_than
                    w_than = b_proj_than * h_than

                w_choan = w_coc + w_be + w_than
                b_proj = w_choan / hi if hi > 0 else 0.0

                sum_b_choan += b_proj
                sum_w_choan += w_choan

                be_str = f"{apc:.1f}x{Lpc:.1f}"
                z_be_str = f"{z_day_be:.2f}"
                ho_str = f"{ho:.2f}"

                self.tree_vcau.insert("", tk.END, values=(
                    p_name, f"{cdtn:.2f}", f"{hi:.2f}",
                    f"{b_proj_than:.2f}", f"{w_than:.2f}",
                    f"{b_proj_be:.2f}", f"{w_be:.2f}",
                    f"{b_proj_coc:.2f}", f"{w_coc:.2f}",
                    f"{b_proj:.2f}", f"{w_choan:.2f}",
                    be_str, z_be_str, ho_str
                ))

            W2 = max(1.0, W1 - sum_b_choan)
            W1_up = w1_up_in if w1_up_in > 0 else W1
            w_eff_bridge = max(0.1, sum_w - sum_w_choan)
            Vcau = qtk / w_eff_bridge

            summary_vcau_txt = (
                f"- TỔNG BỀ RỘNG ƯỚT TỰ NHIÊN W1: {W1:.2f} m | DIỆN TÍCH ƯỚT TỰ NHIÊN: {sum_w:.2f} m2\n"
                f"- TỔNG BỀ RỘNG CẢN DÒNG sum(b): {sum_b_choan:.2f} m | TỔNG DIỆN TÍCH CHOÁN DÒNG: {sum_w_choan:.2f} m2\n"
                f"- BỀ RỘNG THOÁT NƯỚC CO HẸP W2: {W2:.2f} m | DIỆN TÍCH THOÁT LŨ DƯỚI CẦU: {w_eff_bridge:.2f} m2\n"
                f"- VẬN TỐC TỰ NHIÊN V_bq = {V_mean:.2f} m/s | VẬN TỐC DƯỚI CẦU THU HẸP V_cầu = {Vcau:.2f} m/s"
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

            # ---------------- Tab 7: Xói cục bộ mố & trụ ----------------
            self.scour_results.clear()
            self._report_piers.clear()
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

                # A. TÍNH CHO MỐ CẦU
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
                        ya, Qe, Ae, l_prime, k1_abut, th = max(0.1, htk - cdtn), 24.39, 8.19, 1.70, 1.00, 90.0

                    ve = Qe / Ae if Ae > 0 else 0.0
                    ab_res = HEC18Calculations.abutment_scour(ya, ve, l_prime, k1_abut, th)
                    ys_abut = ab_res["ys"]
                    cd_sau_xoi_ab = cdtn - (gen_lower + ys_abut)

                    hd_short = "Tường đứng" if k1_abut == 1.0 else ("Tường cánh" if k1_abut == 0.82 else "Mái taluy")
                    self.tree_abutment.insert("", tk.END, values=(
                        p_name, f"{cdtn:.2f}", f"{ya:.2f}", f"{Qe:.2f}", f"{Ae:.2f}",
                        f"{ve:.2f}", f"{ab_res['fr']:.3f}", hd_short, f"{k1_abut:.2f}",
                        f"{th:.1f}", f"{ab_res['k2']:.3f}", f"{l_prime:.2f}", f"{ys_abut:.2f}", f"{cd_sau_xoi_ab:.2f}", ab_res["method"]
                    ))

                    ys_final_chosen = ys_abut
                    z_be_disp, ho_disp = "-", "-"
                    v1, y1 = ve, ya

                # B. TÍNH CHO TRỤ CẦU
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
                        loai_tru = detail.get("loai_tru", "Lộ bệ & cọc" if ho0 > 0 else "Lộ bệ")
                    else:
                        z_be, ho0, T_be, f_dist, apc, ap, S_coc, m_hang, n_cot = cdtn - 1.40, -1.40, 2.0, 1.85, 6.0, 1.20, 4.20, 2, 3
                        loai_tru = "Lộ bệ & cọc" if ho0 > 0 else "Lộ bệ"

                    aproj = detail.get("aproj", n_cot * ap) if detail else n_cot * ap
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

                    # Ép điều kiện pile_exposed=False đối với các Trụ "Lộ bệ" để huỷ hoàn toàn yspg
                    is_pile_exposed = (loai_tru == "Lộ bệ & cọc")

                    # 7.2 & 7.3 Trụ phức hợp
                    cp = HEC18Calculations.complex_pier(y1, v1, a, k1_eff, k2, k3_val, kw_single, capped,
                                                        ho, T_be, f_dist, apc, ap, S_coc, m_hang, n_cot, aproj, pile_exposed=is_pile_exposed)

                    ks_val = max(2.0 * d84_m, 1e-4)
                    yspier_lobe = cp["ys_pier"]
                    h1 = cp["h1"]
                    yf_lb = h1 + yspier_lobe * 0.5
                    y2_lb = cp["y2"]
                    h2_lb = cp["h2"]
                    v2_lb = cp["v2"]

                    # Tính xói cục bộ phần bệ (Footing) theo công thức vận tốc cắt
                    if h1 <= 0 or y1 <= 0.05 or v1 <= 0:
                        ysfooting_lb, vf_lb, fr2_lb, kw_lb = 0.0, 0.0, 0.0, 1.0
                    else:
                        vf_lb = v2_lb * (math.log(10.93 * yf_lb / ks_val + 1.0) / math.log(10.93 * y2_lb / ks_val + 1.0))
                        fr2_lb = v2_lb / math.sqrt(G * y2_lb)
                        frf_lb = vf_lb / math.sqrt(G * yf_lb)
                        vc2 = HEC18Calculations.critical_velocity_vc(y2_lb, d50_m)
                        kw_lb = HEC18Calculations.kw_wide_pier(y2_lb, apc, frf_lb, vf_lb / max(0.01, vc2), d50_m)
                        ysfooting_lb = 2.0 * 1.0 * k2 * k3_val * kw_lb * (apc ** 0.65) * (yf_lb ** 0.35) * (frf_lb ** 0.43)

                    # Lưu các giá trị chưa làm tròn cho báo cáo, không tính lại khi xuất.
                    self._report_piers.append(dict(
                        name=p_name, stt=stt_p, cdtn=cdtn, kind=loai_tru,
                        y1=y1, v1=v1, fr1=fr1, a=a, shape=k1_short,
                        k1=k1_eff, theta=skew, L=L, k2=k2, bed=k3_name.split(" (")[0],
                        k3=k3_val, d50=d50_mm, vc=vc_tru, ratio=ratio_v_vc,
                        kw=kw_single, single=ys_pier_single, z_single=cd_single,
                        f=f_dist, ho=ho, ho0=ho0, T=T_be, apc=apc, z_be=z_be,
                        Lpc=(detail.get('Lpc', 13.32) if detail else 13.32),
                        ap=ap, S=S_coc, m=m_hang, n=n_cot, aproj=aproj,
                        cp=copy.deepcopy(cp), yf=yf_lb, ks=ks_val, vf=vf_lb,
                        frf=(vf_lb / math.sqrt(G * yf_lb) if yf_lb > 0 else 0.0),
                        kw_lb=kw_lb, footing=ysfooting_lb, note=note_single))

                    # Đưa vào đúng Tab phân loại để không bị lẫn lộn giữa Trụ lộ bệ và Trụ lộ cọc
                    if loai_tru == "Lộ bệ":
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
                    elif loai_tru == "Lộ bệ & cọc":
                        cd_lococ = cdtn - (gen_lower + cp["ys_total"])
                        self.tree_lc_4.insert("", tk.END, values=(
                            stt_p, p_name, f"{cdtn:.2f}", f"{z_be:.2f}", f"{ho0:.2f}",
                            f"{cp['ys_pier']:.2f}", f"{cp['ys_pc']:.2f}", f"{cp['ys_pg']:.2f}",
                            f"{cp['ys_total']:.2f}", f"{cd_lococ:.2f}", cp["note"]
                        ))

                    if loai_tru == "Trụ đơn đặc":
                        ys_final_chosen = ys_pier_single
                    elif loai_tru == "Lộ bệ":
                        ys_final_chosen = yspier_lobe + ysfooting_lb
                    else:
                        ys_final_chosen = cp["ys_total"]

                    stt_p += 1

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

            all_x = [pt["L_cum"] for pt in self.vh_data]
            all_z = [pt["z"] for pt in self.vh_data]
            self._render_scour_prism_plot(all_x, all_z, htk, y_deg, ysc, plot_x, plot_scour_z)

            self._report_context = dict(htk=htk, qtk=qtk, y_deg=y_deg,
                                        skew=skew, s1=s1, d50=d50_mm, d84=d84_mm, omega=omega,
                                        k1_type=k1_pier_name, k3_type=k3_name,
                                        W1=W1, W1_up=W1_up, W2=W2, area=sum_w,
                                        area_bridge=w_eff_bridge, alpha=alpha_v,
                                        ai_vals=copy.deepcopy(Ai_vals), wet_w=copy.deepcopy(wet_w),
                                        vh_data=copy.deepcopy(self.vh_data),
                                        n_manning=self.t1_entries['n_manning'].get(),
                                        project_name=self.project.get("project_name", ""),
                                        bridge_name=self.project.get("bridge_name", ""))

            self.nb.select(self.tab4)
            messagebox.showinfo("Thành công", f"Đã tính toán choán dòng & xói cầu chính xác cho {self.project['bridge_name']}!")

        except Exception as e:
            messagebox.showerror("Lỗi thực thi", f"Quá trình tính toán gặp sự cố: {e}")

    # =========================================================================
    # DỮ LIỆU MẪU & CÁC THAO TÁC FILE
    # =========================================================================
    def _load_sample_data(self):
        # Dữ liệu chuẩn Cầu Bạch Đằng
        self.project["cross_section"] = [
            [1, "M1 (Bờ Hải Phòng)", 0.50, 0.0, "Mố cầu", 0.0, 1.70, 1.0],
            [2, "", 0.20, 35.0, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [3, "T25", 0.04, 50.0, "Trụ đơn", 2.0, 1.5, 1.1],
            [4, "T26", -0.94, 65.0, "Trụ đơn", 2.0, 1.5, 1.1],
            [5, "T27", -1.84, 75.0, "Trụ đơn", 2.0, 1.5, 1.1],
            [6, "T28", -5.06, 120.0, "Trụ đơn", 2.0, 1.5, 1.1],
            [7, "T29", -8.33, 140.0, "Trụ đơn", 2.0, 1.5, 1.1],
            [8, "T30", -1.66, 130.0, "Trụ đơn", 2.0, 1.5, 1.1],
            [9, "", -0.50, 80.0, "Điểm tự nhiên", 0.0, 0.0, 1.0],
            [10, "M2 (Bờ Quảng Ninh)", 0.60, 69.44, "Mố cầu", 0.0, 1.70, 1.0]
        ]
        self.sync_all_details()
        # Áp đặt kích thước bệ & cọc đúng chuẩn CAD Cầu Bạch Đằng
        for d in self.project["piers_detail"]:
            if d["name"] in ["T25", "T26", "T27"]:
                d["apc"], d["Lpc"], d["T"], d["z_day_be"] = 12.0, 20.5, 3.0, -2.50
                d["ap"], d["S"], d["m"], d["n"], d["aproj"] = 1.2, 4.2, 2, 3, 3.6
            elif d["name"] in ["T28", "T29", "T30"]:
                d["apc"], d["Lpc"], d["T"], d["z_day_be"] = 20.0, 72.0, 5.4, 1.00
                d["ap"], d["S"], d["m"], d["n"], d["aproj"] = 2.0, 7.75, 4, 8, 15.3
            d["ho"] = round(d["z_day_be"] - d["cdtn"], 3)
            d["z_be"] = d["z_day_be"]

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

    # =========================================================================
    # HÀM BỔ TRỢ: TẠO ẢNH CÔNG THỨC TOÁN HỌC CHUẨN EQUATION (LATEX)
    # =========================================================================
    def _create_equation_img(self, latex_str, fontsize=10, dpi=160):
        """Biên dịch công thức toán học LaTeX thành ảnh Equation trong suốt chuẩn tỷ lệ"""
        try:
            import tempfile
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            
            fig = Figure(figsize=(8, 2), dpi=dpi)
            fig.patch.set_alpha(0.0)
            canvas = FigureCanvasAgg(fig)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off')
            t = ax.text(0.5, 0.5, latex_str, fontsize=fontsize, ha='center', va='center', color='black')
            canvas.draw()
            
            renderer = canvas.get_renderer()
            bbox = t.get_window_extent(renderer=renderer)
            w_in = max(0.5, (bbox.width + 12) / dpi)
            h_in = max(0.25, (bbox.height + 8) / dpi)
            
            fig_tight = Figure(figsize=(w_in, h_in), dpi=dpi)
            fig_tight.patch.set_alpha(0.0)
            canvas_tight = FigureCanvasAgg(fig_tight)
            ax_t = fig_tight.add_axes([0, 0, 1, 1])
            ax_t.axis('off')
            ax_t.text(0.5, 0.5, latex_str, fontsize=fontsize, ha='center', va='center', color='black')
            canvas_tight.draw()
            
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp_path = tmp.name
            tmp.close()
            fig_tight.savefig(tmp_path, format='png', transparent=True, dpi=dpi, bbox_inches='tight', pad_inches=0.02)
            return tmp_path, w_in, h_in
        except Exception:
            return None, 0, 0

    # =========================================================================
    # BÁO CÁO WORD / EXCEL: CÙNG DỮ LIỆU, CÙNG CẤU TRÚC BẢNG THEO MẪU
    # =========================================================================
    def _report_sections(self):
        """Dữ liệu xuất độc lập định dạng; giữ nguyên kết quả của bộ tính HEC-18."""
        import re

        def columns(spec):
            result = []
            for entry in spec:
                key, label, unit, digits, role = entry.split('|')
                result.append(dict(key=key, label=label, unit=unit,
                                   digits=int(digits), role=role))
            return result

        def table(title, spec, rows, groups=()):
            return dict(title=title, columns=columns(spec), rows=rows, groups=groups)

        def tree_table(title, tree):
            spec = []
            for i, key in enumerate(tree['columns']):
                label = tree.heading(key, 'text')
                match = re.search(r'\s*\(([^()]*)\)\s*$', label)
                unit = match.group(1) if match else ''
                label = label[:match.start()] if match else label
                is_text = any(word in label for word in ('Tên', 'No.', 'STT', 'Ghi chú', 'H.D.', 'Kích Thước'))
                role = 'text' if is_text else 'output'
                digits = 6 if label in ('io', 'Fr') else 3
                spec.append(f'{i}|{label}|{unit}|{digits}|{role}')
            rows = [dict(zip((str(i) for i in range(len(spec))), tree.item(item, 'values')))
                    for item in tree.get_children()]
            return table(title, spec, rows)

        records = []
        for p in self._report_piers:
            row = {**p, **p['cp']}
            row['note'] = p['note']
            row['case_note'] = p['cp']['note']
            row['vc2'] = HEC18Calculations.critical_velocity_vc(row['y2'], p['d50'] / 1000.0)
            row['ratio2'] = row['v2'] / row['vc2'] if row['vc2'] > 0 else 0.0
            row['ratiof'] = p['vf'] / row['vc2'] if row['vc2'] > 0 else 0.0
            row['y2_af'] = row['y2'] / p['apc'] if p['apc'] > 0 else 0.0
            row['kw_pc'] = 1.0  # Thành phần bệ của complex_pier không nhân Kw.
            row['k2_pg'] = 1.0  # Nhóm cọc dùng K2 = 1 trong bộ tính hiện tại.
            row['y3max'] = 3.5 * row['apg']
            row['ys_lb'] = p['cp']['ys_pier'] + p['footing']
            records.append(row)

        stem_spec = [
            'name|No. Trụ||0|text', 'cdtn|∇tn|m|2|input', 'y1|y₁|m|2|input',
            'v1|V₁|m/s|2|input', 'fr1|Fr₁||3|output', 'a|a_pier|m|2|input',
            'shape|H. D. trụ||0|text', 'k1|K₁||2|output', 'theta|θ|°|1|input',
            'L|L|m|2|input', 'k2|K₂||2|output', 'bed|Đáy sông là||0|text',
            'k3|K₃||2|output', 'f|f|m|2|input', 'ho|h₀|m|2|input',
            'T|T|m|2|input', 'h1|h₁|m|2|output', 'kh|K_hpier||3|output',
            'd50|D₅₀|mm|3|input', 'vc|V_c|m/s|3|output', 'ratio|V₁/V_c||2|output',
            'kw|K_w||3|output', 'ys_pier|y_spier|m|2|output', 'note|Ghi chú||0|text']
        stem_groups = [('Xác định K₁', 'shape', 'k1'), ('Xác định K₂', 'theta', 'k2'),
                       ('Xác định K₃', 'bed', 'k3'), ('Xác định K_hpier', 'f', 'kh')]
        cap_spec = [
            'name|No. Trụ||0|text', 'cdtn|∇tn|m|2|input', 'y1|y₁|m|2|input',
            'v1|V₁|m/s|2|input', 'ys_pier|y_spier|m|2|output', 'y2|y₂|m|2|output',
            'h2|h₂|m|2|output', 'T|T|m|2|input', 'apc|a_pc|m|2|input',
            'v2|V₂|m/s|2|output', 'apc_star|a_pc*|m|3|output', 'fr2|Fr₂||3|output',
            'd50|D₅₀|mm|3|input', 'vc2|V_c|m/s|3|output', 'ratio2|V₂/V_c||2|output',
            'kw_pc|K_w||2|output', 'shape|H. D. trụ||0|text', 'k1|K₁||2|output',
            'theta|θ|°|1|input', 'L|L|m|2|input', 'k2|K₂||2|output',
            'k3|K₃||2|output', 'ys_pc|y_spc|m|2|output']
        pile_spec = [
            'name|No. Trụ||0|text', 'cdtn|∇tn|m|2|input', 'y1|y₁|m|2|input',
            'v1|V₁|m/s|2|input', 'ys_pier|y_spier|m|2|output', 'y3|y₃|m|2|output',
            'h3|h₃|m|2|output', 'ap|a_p|m|2|input', 'S|S|m|2|input',
            'm|m||0|input', 'n|n||0|input', 'aproj|a_proj|m|2|input',
            'km|K_m||3|output', 'ksp|K_sp||3|output', 'apg|a_pg*|m|3|output',
            'y3max|y₃,max = 3,5a_pg*|m|2|output', 'khpg|K_hpg||3|output',
            'v3|V₃|m/s|2|output', 'shape|H. D. trụ||0|text', 'k1|K₁||2|output',
            'k2_pg|K₂||2|output', 'k3|K₃||2|output', 'ys_pg|y_spg|m|2|output',
            'note|Ghi chú||0|text']
        footing_spec = [
            'name|No. Trụ||0|text', 'cdtn|∇tn|m|2|input', 'y1|y₁|m|2|input',
            'v1|V₁|m/s|2|input', 'ys_pier|y_spier|m|2|output', 'y2|y₂|m|2|output',
            'h2|h₂|m|2|output', 'h1|h₁|m|2|output', 'yf|y_f|m|2|output',
            'v2|V₂|m/s|2|output', 'ks|K_s|m|4|input', 'vf|V_f|m/s|2|output',
            'apc|a_f|m|2|input', 'y2_af|y₂/a_f||3|output', 'frf|Fr_f||3|output',
            'd50|D₅₀|mm|3|input', 'vc2|V_c|m/s|3|output', 'ratiof|V_f/V_c||2|output',
            'kw_lb|K_w||3|output', 'k1_foot|K₁||2|output', 'k2|K₂||2|output',
            'k3|K₃||2|output', 'footing|y_sfooting|m|2|output', 'note|Ghi chú||0|text']
        for row in records:
            row['k1_foot'] = 1.0  # Hệ số thực tế của công thức ysfooting_lb.
        lc = [r for r in records if r['kind'] == 'Lộ bệ & cọc']
        lb = [r for r in records if r['kind'] == 'Lộ bệ']
        single = [r for r in records if r['kind'] == 'Trụ đơn đặc']
        sum_spec = ['stt|STT||0|text', 'name|Tên trụ||0|text', 'cdtn|∇tn|m|2|input',
                    'ys_pier|y_spier|m|2|output', 'ys_pc|y_spc|m|2|output',
                    'ys_pg|y_spg|m|2|output', 'ys_total|y_s|m|2|output', 'case_note|Ghi chú||0|text']
        lb_sum_spec = ['stt|STT||0|text', 'name|Tên trụ||0|text', 'cdtn|∇tn|m|2|input',
                       'ys_pier|Xói do thân trụ y_spier|m|2|output',
                       'footing|Xói do bệ trụ y_sfooting|m|2|output',
                       'ys_lb|Tổng xói cục bộ y_s|m|2|output', 'note|Ghi chú||0|text']
        # Bảng trụ đơn chỉ chứa trụ được chọn là Trụ đơn đặc, không lặp trụ phức hợp.
        single_spec = stem_spec[:13] + stem_spec[18:22] + [
            'single|y_spier|m|2|output', 'z_single|∇sau xói|m|2|output', 'note|Ghi chú||0|text']

        xc_spec = [
            '0|No.||0|text', '1|∇tr.b thượng lưu|m|2|input', '2|y₁|m|2|input',
            '3|D₅₀|mm|3|input', '4|V_c|m/s|3|output', '5|V|m/s|2|output',
            '6|V_c/V||3|output', '7|Thuộc loại||0|text', '8|S₁|m/m|6|input',
            '9|V*|m/s|4|output', '10|ω|m/s|3|input', '11|V*/ω||3|output',
            '12|k₁||2|output', '13|Q₁|m³/s|2|input', '14|W₁|m|2|input',
            '15|Q₂|m³/s|2|input', '16|W₂|m|2|input', '17|D_m|mm|3|output',
            '18|y₂|m|2|output', '19|∇tr.b thu hẹp|m|2|input', '20|y₀|m|2|input',
            '21|Δy_xch|m|3|output', '22|Ghi chú||0|text']
        xc_rows = [dict(zip(map(str, range(23)), self.tree_xoi_chung.item(i, 'values')))
                   for i in self.tree_xoi_chung.get_children()]
        summary_rows = []
        abutments = sorted([r for r in self.scour_results if is_abut_name(r['name'])],
                           key=lambda r: r['x'])
        for r in self.scour_results:
            out = dict(r, left='', main='', right='', note='')
            key = 'main'
            if abutments and r is abutments[0]:
                key = 'left'
            elif abutments and r is abutments[-1]:
                key = 'right'
            out[key] = r['ysc']
            summary_rows.append(out)
        summary_spec = ['name|Tên mố/trụ||0|text', 'cdtn|Cao độ tự nhiên|m|2|input',
                        'left|Bãi trái|m|2|output', 'main|Lòng chính|m|2|output',
                        'right|Bãi phải|m|2|output']
        if any(r['y_deg'] != 0 for r in self.scour_results):
            summary_spec.append('y_deg|Hạ thấp dài hạn|m|2|output')
        summary_spec += ['ys_local|Xói cục bộ|m|2|output', 'y_tot|Tổng chiều sâu xói|m|2|output',
                         'z_scour|Cao độ sau xói|m|2|output']

        eq_stem = r'$y_{spier}=K_{hpier}\,[2.0 K_1 K_2 K_3 K_w a_{pier}^{0.65} y_1^{0.35} Fr_1^{0.43}]$'
        eq_kh = (r'$K_{hpier}=(0.4075-0.0669 f/a_{pier})'
                 r'-(0.4271-0.0778 f/a_{pier})(h_1/a_{pier})'
                 r'+(0.1615-0.0455 f/a_{pier})(h_1/a_{pier})^2'
                 r'-(0.0269-0.012 f/a_{pier})(h_1/a_{pier})^3$')
        base_defs = [
            'y₁: chiều sâu dòng chảy trước khi tính xói (m); V₁: vận tốc dòng chảy đến trụ (m/s).',
            'K₁: hệ số hình dạng mũi trụ; K₂: hệ số góc chéo θ; K₃: hệ số tình trạng đáy sông.',
            'K_w: hệ số xét chiều sâu và bề rộng trụ; a_pier: bề rộng thân trụ (m).',
            'Fr₁ = V₁/√(g y₁); g = 9,81 m/s²; D₅₀: đường kính hạt bùn cát (mm).',
            'V_c = 6,19 y₁^(1/6) D₅₀^(1/3), trong công thức D₅₀ đổi sang m.',
            'f: khoảng cách từ mũi bệ đến thân trụ; T: chiều cao bệ (m).',
            'h₀: cao độ đáy bệ trừ cao độ đáy sau hạ thấp dài hạn và xói thu hẹp (m).',
            'h₁ = h₀ + T; y₂ = y₁ + y_spier/2; h₂ = h₀ + y_spier/2 (m).',
            'V₂ = V₁(y₁/y₂); a_pc: bề rộng bệ; a_pc*: bề rộng tương đương của bệ (m).',
            'K_hpier được giới hạn trong [0; 1]; khi đỉnh bệ dưới đáy, dùng kết quả trụ đơn.']
        lc_defs = base_defs + [
            'y_s = y_spier + y_spc + y_spg: tổng chiều sâu xói cục bộ (m).',
            'y₃ = y₁ + y_spier/2 + y_spc/2; h₃ = h₀ + y_spier/2 + y_spc/2 (m).',
            'V₃ = V₁(y₁/y₃); a_p: đường kính cọc; S: khoảng cách giữa các cọc (m).',
            'm: số hàng cọc theo dòng chảy; n: số cột cọc theo tim cầu.',
            'a_proj: bề rộng chiếu nhóm cọc; a_pg* = K_sp K_m a_proj (m).',
            'K_sp: hệ số khoảng cách cọc; K_m: hệ số số hàng cọc.',
            'K_hpg: hệ số chiều sâu xói nhóm cọc; y₃,max = 3,5a_pg* chỉ là giá trị tham khảo.',
            'Thành phần bệ phức hợp dùng K_w = 1; thành phần nhóm cọc dùng K₂ = 1 theo bộ tính.']
        lb_defs = base_defs + [
            'y_s = y_spier + y_sfooting; cọc ngàm trong đất nên không có thành phần y_spg.',
            'y_f = h₁ + y_spier/2: khoảng cách từ đáy sau xói thân đến đỉnh bệ (m).',
            'V_f: vận tốc dưới đỉnh bệ; Fr_f = V_f/√(g y_f).',
            'a_f: bề rộng bệ; K_s: độ nhám dùng trong bộ tính (= max(2D₈₄; 0,0001 m)).',
            'Thành phần xói bệ dùng K₁ = 1; V_c của bảng bệ được tính theo y₂.']
        xc_defs = [
            'Δy_xch = y₂ − y₀: chiều sâu xói thu hẹp; y₀: chiều sâu hiện tại trước xói (m).',
            'y₁: chiều sâu trung bình thượng lưu; y₂: chiều sâu sau xói tại mặt cắt thu hẹp (m).',
            'V_c < V: xói nước đục; V_c ≥ V: xói nước trong.',
            'Q₁, Q₂: lưu lượng thượng lưu và tại mặt cắt thu hẹp (m³/s).',
            'W₁, W₂: bề rộng thượng lưu và bề rộng thu hẹp sau khi trừ trụ (m).',
            'k₁ = f(V*/ω): số mũ vận chuyển bùn cát; V* = √(g y₁ S₁).',
            'S₁: độ dốc đường năng lượng; ω: vận tốc lắng hạt D₅₀ (m/s).',
            'D_m = 1,25 D₅₀; bảng dùng mm, công thức xói nước trong dùng m.',
            'V_c: vận tốc tới hạn hạt đáy (m/s); V: vận tốc trung bình dòng chảy (m/s).']
        sections = [
            dict(sheet='Vcau', title='TÍNH DIỆN TÍCH TRỤ VÀ CHIỀU RỘNG BÌNH QUÂN TRỤ',
                 formulas=[], definitions=self.txt_vcau_summary.get('1.0', 'end-1c').splitlines(),
                 tables=[tree_table('', self.tree_vcau)]),
            dict(sheet='Nuoc denh', title='TÍNH TOÁN NƯỚC DỀNH VÀ KHOẢNG CÁCH DỀNH LỚN NHẤT PHÍA THƯỢNG LƯU CẦU',
                 formulas=[r'$\Delta h_{dmax}=K\frac{V_c^2-V_{c0}^2}{2g}$',
                           r'$K=1+(V_0/V_{c0})^2 a/\sqrt{Fr/i_0},\quad Fr=V_0^2/(gL_{ngap})$'],
                 definitions=['V₀, V_c0, V_c: vận tốc tự nhiên, trước và sau thu hẹp (m/s).',
                              'L_ngập: bề rộng ngập; i₀: độ dốc; a: hệ số hình thái; g = 9,81 m/s².'],
                 tables=[tree_table('', self.tree_denh)]),
            dict(sheet='PPLL', title='PHÂN PHỐI TỐC ĐỘ DÒNG CHẢY LŨ THIẾT KẾ QUA MẶT CẮT TIM CẦU',
                 formulas=[], definitions=[], tables=[tree_table('', self.tree_ppll)]),
            dict(sheet='Xói chung', title='TÍNH XÓI THU HẸP TRUNG BÌNH DƯỚI CẦU',
                 formulas=[r'$\Delta y_{xch}=y_2-y_0$',
                           r'$y_2=y_1(Q_2/Q_1)^{6/7}(W_1/W_2)^{k_1}\quad (V_c<V)$',
                           r'$y_2=[0.025 Q_2^2/(D_m^{2/3} W_2^2)]^{3/7}\quad (V_c\geq V)$'],
                 definitions=xc_defs,
                 tables=[table('', xc_spec, xc_rows,
                               [('Tìm số mũ k₁', '8', '12'),
                                ('Lưu lượng, bề rộng mặt cắt thượng lưu và thu hẹp', '13', '16')])]),
            dict(sheet='XCB-lo coc', title='TÍNH XÓI CỤC BỘ TRỤ CẦU (TRƯỜNG HỢP CÓ BỆ TRỤ, NHÓM CỌC LỘ TRONG DÒNG CHẢY)',
                 formulas=[r'$y_s=y_{spier}+y_{spc}+y_{spg}$', eq_stem,
                           r'$y_{spc}=2.0 K_1 K_2 K_3 K_w (a_{pc}^{*})^{0.65} y_2^{0.35} Fr_2^{0.43}$',
                           r'$y_{spg}=K_{hpg}[2.0 K_1 K_2 K_3 (a_{pg}^{*})^{0.65} y_3^{0.35} (V_3/\sqrt{gy_3})^{0.43}]$',
                           eq_kh,
                           r'$K_{hpg}=[3.08r-5.23r^2+5.25r^3-2.10r^4]^{1/0.65},\quad r=h_3/y_3$'],
                 definitions=lc_defs, tables=[
                     table('1. Xói cục bộ do thân trụ gây ra', stem_spec, lc, stem_groups),
                     table('2. Xói cục bộ do bệ trụ', cap_spec, lc,
                           [('Xác định K₁', 'shape', 'k1'), ('Xác định K₂', 'theta', 'k2')]),
                     table('3. Xói cục bộ do nhóm cọc', pile_spec, lc,
                           [('Xác định K₁', 'shape', 'k1')]),
                     table('4. Kết quả phân tích xói cục bộ tại trụ', sum_spec, lc)]),
            dict(sheet='XCB-lo be', title='TÍNH XÓI CỤC BỘ TRỤ CẦU (TRƯỜNG HỢP CÓ BỆ TRỤ LỘ TRONG DÒNG CHẢY)',
                 formulas=[r'$y_s=y_{spier}+y_{sfooting}$', eq_stem,
                           r'$y_{sfooting}=2.0 K_1 K_2 K_3 K_w a_f^{0.65} y_f^{0.35} Fr_f^{0.43}$',
                           r'$V_f/V_2=\frac{\ln(10.93y_f/K_s+1)}{\ln(10.93y_2/K_s+1)}$', eq_kh],
                 definitions=lb_defs, tables=[
                     table('1. Xói cục bộ do thân trụ gây ra', stem_spec, lb, stem_groups),
                     table('2. Xói cục bộ do bệ trụ', footing_spec, lb),
                     table('3. Kết quả phân tích xói cục bộ tại trụ', lb_sum_spec, lb)]),
            dict(sheet='Xoi cuc tru', title='TÍNH XÓI CỤC BỘ TRỤ CẦU',
                 formulas=[r'$y_{spier}=2.0 K_1 K_2 K_3 K_w a^{0.65} y_1^{0.35} Fr_1^{0.43}$'],
                 definitions=base_defs[:5], tables=[table('', single_spec, single, stem_groups[:3])]),
            dict(sheet='Xoi mo', title='TÍNH XÓI CỤC BỘ MỐ CẦU', formulas=[], definitions=[],
                 tables=[tree_table('', self.tree_abutment)]),
            dict(sheet='Tong hop', title='TỔNG HỢP XÓI DƯỚI CẦU', formulas=[],
                 definitions=['Tổng xói = hạ thấp dài hạn + xói thu hẹp + xói cục bộ; cao độ sau xói = cao độ tự nhiên − tổng xói.',
                              'Xói thu hẹp lấy từ kết quả hiện tại; bộ tính chưa tách riêng thủy lực từng bãi.',
                              'Mố ở vị trí X nhỏ nhất/lớn nhất được xếp bãi trái/phải; các trụ xếp lòng chính.'],
                 tables=[table('', summary_spec, summary_rows,
                               [('Độ sâu xói thu hẹp (m)', 'left', 'right')])])]
        return self._complete_report_sections(sections)

    def _complete_report_sections(self, sections):
        """Bổ sung đầy đủ căn cứ tính, bảng tra và số liệu kiểm tra cho hai định dạng."""
        by_sheet = {s['sheet']: s for s in sections}
        context = self._report_context

        def make_table(title, fields, rows, groups=()):
            cols = []
            for key, label, unit, digits, role in fields:
                cols.append(dict(key=key, label=label, unit=unit, digits=digits, role=role))
            return dict(title=title, columns=cols, rows=rows, groups=groups)

        def detail(sheet, equations, definitions):
            by_sheet[sheet]['detail'] = dict(sheet=sheet + '-detail',
                formulas=[e[2] for e in equations],
                formula_labels=[f'{e[0]} — {e[1]}' for e in equations],
                definitions=definitions)

        # Mã công thức xuất thành chữ bên cạnh ảnh: dễ tìm và kiểm tra nội dung.
        common = [
            ('HEC-FR', 'Hệ số Froude', r'$Fr=V/\sqrt{g y}$'),
            ('HEC-VC', 'Vận tốc tới hạn hạt đáy (D₅₀ dùng m)', r'$V_c=6.19y^{1/6}D_{50}^{1/3}$'),
            ('HEC-K2', 'Hệ số góc chéo và tỷ số chiều dài/rộng hữu hiệu',
             r'$\lambda=\min(12,\max(0,L)/a),\quad K_2=\min[5,(\cos|\theta|+\lambda\sin|\theta|)^{0.65}]$'),
            ('HEC-KW-CW', 'K_w khi V/V_c < 1', r'$K_w=\min[1,2.58(y/a)^{0.34}Fr^{0.65}]$'),
            ('HEC-KW-LB', 'K_w khi V/V_c ≥ 1', r'$K_w=\min[1,(y/a)^{0.13}Fr^{0.25}]$'),
            ('HEC-LIMIT', 'Giới hạn xói trụ mũi tròn khi được áp dụng',
             r'$y_{s,lim}=2.4a\ (Fr\leq0.8),\qquad y_{s,lim}=3a\ (Fr>0.8)$')]
        common_defs = [
            'K₁: tra theo hình dạng mũi trụ ở bảng tra cuối phần trụ đơn; nếu |θ| > 5° thì K₁ hữu hiệu = 1,0.',
            'K₂: hệ số góc chéo; L: chiều dài thân trụ theo dòng chảy (m); a: bề rộng thân trụ (m); θ tính bằng độ.',
            'K₃: hệ số tình trạng đáy sông, xem bảng tra K₃; g = 9,81 m/s².',
            'K_w chỉ hiệu chỉnh khi a > 50D₅₀, 0 < Fr < 1 và y/a < 0,8; các trường hợp khác K_w = 1.',
            'D₅₀ trong công thức là m = D₅₀(mm)/1000; bộ tính vận tốc tới hạn dùng y ≥ 0,01 m và D₅₀ ≥ 0,00001 m.',
            'Giới hạn 2,4a/3a chỉ áp dụng với mũi tròn và |θ| ≤ 5°; chiều sâu nước ≤ 0,05 m hoặc V ≤ 0 cho xói bằng 0.']
        complex_relations = [
            ('CP-H0', 'Đáy bệ so với đáy ban đầu và đáy sau xói chung',
             r'$h_{0,initial}=z_{be}-z_{tn},\quad h_0=h_{0,initial}+y_{deg}+y_{sc},\quad h_1=h_0+T$'),
            ('CP-Y2', 'Chiều sâu và cao độ sau xói thân',
             r'$y_2=y_1+y_{spier}/2,\quad h_2=h_0+y_{spier}/2$'),
            ('CP-V2', 'Vận tốc và Froude hiệu chỉnh tại bệ',
             r'$V_2=V_1y_1/y_2,\quad Fr_2=V_2/\sqrt{g y_2}$')]
        detail('Xoi cuc tru', common, common_defs)
        detail('XCB-lo be', common + complex_relations + [
            ('FOOT-YF', 'Chiều sâu dòng chảy dưới đỉnh bệ', r'$y_f=h_1+y_{spier}/2$'),
            ('FOOT-KS', 'Độ nhám được sử dụng trong bộ tính', r'$K_s=\max(2D_{84},0.0001)$'),
            ('FOOT-VF', 'Vận tốc dưới đỉnh bệ', r'$V_f=V_2\frac{\ln(10.93y_f/K_s+1)}{\ln(10.93y_2/K_s+1)}$'),
            ('FOOT-FRF', 'Froude tại đỉnh bệ', r'$Fr_f=V_f/\sqrt{g y_f}$'),
            ('FOOT-TOTAL', 'Tổng xói trụ lộ bệ', r'$y_s=y_{spier}+y_{sfooting}$')], common_defs + [
            'z_be: cao độ đáy bệ; z_tn: cao độ đáy sông tự nhiên; h₀,initial tính trước hạ thấp dài hạn và xói thu hẹp (m).',
            'h₀ dùng trong tính xói phức hợp đã cộng y_deg và y_sc; bảng kiểm tra bên dưới xuất cả h₀,initial và h₀.',
            'y₂: chiều sâu hiệu chỉnh cho bệ; h₂: cao độ đáy bệ so với đáy sau xói thân; h₁: cao độ đỉnh bệ (m).',
            'V₂: vận tốc hiệu chỉnh; V_f: vận tốc dưới đỉnh bệ (m/s); Fr₂ và Fr_f là hai hệ số khác nhau.',
            'D₈₄: đường kính hạt mà 84% hạt nhỏ hơn (mm); D₈₄ hiệu dụng = 2D₅₀ nếu đầu vào D₈₄ ≤ 0.',
            'Mẫu ghi K_s = D₈₄, nhưng bộ tính hiện tại dùng K_s = max(2D₈₄; 0,0001 m); báo cáo ghi giá trị thực tế.',
            'K₁ của thành phần bệ hiện được dùng bằng 1,0; K₂/K₃ lấy cùng bộ hệ số của thân trụ.',
            'Nếu đỉnh bệ h₁ ≤ 0 hoặc trụ khô, thành phần xói bệ bằng 0.',
            'a_f: bề rộng bệ (m); y₂/a_f: tỷ số chiều sâu/rộng; V_c của phần bệ được tính tại y₂.'])
        detail('XCB-lo coc', common + complex_relations + [
            ('CAP-TEFF', 'Chiều cao bệ tham gia dòng chảy', r'$T_{eff}=T+\min(0,h_2)$'),
            ('CAP-RATIOS', 'Các tỷ số xác định bề rộng bệ tương đương',
             r'$\bar y_2=\min(y_2,3.5a_{pc}),\quad t=\max(0.001,T_{eff}/\bar y_2),\quad u=\max[0,\min(1,h_2/\bar y_2)]$'),
            ('CAP-WIDTH', 'Bề rộng bệ tương đương theo bộ tính',
             r'$a_{pc}^{*}=a_{pc}\exp[-2.705+0.51\ln(t)-2.783u^3+1.751\exp(-u)]$'),
            ('PILE-Y3', 'Chiều sâu và cao độ sau xói bệ',
             r'$y_3=y_1+y_{spier}/2+y_{spc}/2,\quad h_3=h_0+y_{spier}/2+y_{spc}/2$'),
            ('PILE-V3', 'Vận tốc và Froude hiệu chỉnh tại nhóm cọc',
             r'$V_3=V_1y_1/y_3,\quad Fr_3=V_3/\sqrt{g y_3}$'),
            ('PILE-RATIOS', 'Tỷ số khoảng cách và bề rộng chiếu',
             r'$s=\max(1,S/a_p),\qquad A=\max(1,a_{proj}/a_p)$'),
            ('PILE-KSP', 'Hệ số khoảng cách giữa các cọc',
             r'$K_{sp}=1-\frac{4}{3}(1-1/A)(1-s^{-0.6})$'),
            ('PILE-KM', 'Hệ số số hàng cọc',
             r'$K_m=0.9+0.10m-0.0714(m-1)(2.4-1.1s+0.1s^2)$'),
            ('PILE-WIDTH', 'Bề rộng nhóm cọc tương đương', r'$a_{pg}^{*}=K_{sp}K_m a_{proj}$'),
            ('PILE-KHPG', 'Hệ số chiều sâu nhóm cọc và giới hạn áp dụng',
             r'$r=\max[0,\min(1,h_3/y_3)],\quad K_{hpg}=\min[1,\max(0,3.08r-5.23r^2+5.25r^3-2.10r^4)^{1/0.65}]$'),
            ('PILE-TOTAL', 'Tổng thành phần xói phức hợp', r'$y_s=y_{spier}+y_{spc}+y_{spg}$')], common_defs + [
            'a_pc: bề rộng bệ; a_pc*: bề rộng bệ tương đương; T_eff: chiều cao hữu hiệu của bệ (m).',
            'Bề rộng a_pc* được giới hạn trong [0,01a_pc; a_pc]; nếu h₂ ≤ 0 hoặc T_eff ≤ 0 thì bộ tính trả a_pc* = a_pc.',
            'y₂ và y₃: chiều sâu hiệu chỉnh sau xói thân và sau xói bệ (m).',
            'h₁, h₂, h₃: chiều cao đỉnh bệ, đáy bệ và nhóm cọc so với đáy đang xét (m).',
            'V₂ và V₃: vận tốc hiệu chỉnh ở bệ và nhóm cọc; Fr₂/Fr₃: hệ số Froude tương ứng.',
            'a_p: đường kính cọc; S: khoảng cách cọc; m: số hàng theo dòng chảy; n: số cột theo tim cầu.',
            'a_proj: bề rộng chiếu nhóm cọc nhập vào (m), mặc định n a_p nếu không khai báo.',
            'K_sp giới hạn [0,1; 1]; K_m không nhỏ hơn 1; K_hpg không lớn hơn 1.',
            'K₂ của thành phần nhóm cọc và K_w của thành phần bệ phức hợp được dùng bằng 1 trong bộ tính.',
            'K_hpier trong bộ tính có dấu trừ trước 0,0669 f/a_pier, khác dấu cộng trong ảnh mẫu; báo cáo giữ đúng bộ tính.',
            'Nếu h₃ ≤ 0 hoặc cọc ngàm trong đất thì y_spg = 0; khi h₁ ≤ 0 thì dùng kết quả trụ đơn.',
            'y₃,max = 3,5a_pg* là giá trị tham khảo trong mẫu, không phải giới hạn y₃ của bộ tính nhóm cọc hiện tại.'])
        detail('Xói chung', [
            ('XC-VC', 'Vận tốc tới hạn để phân loại xói', r'$V_c=6.19y_1^{1/6}D_{50}^{1/3}$'),
            ('XC-VSTAR', 'Vận tốc ma sát', r'$V_* =\sqrt{g y_1 S_1}$'),
            ('XC-DM', 'Đường kính hạt không bị cuốn đi', r'$D_m=1.25D_{50}$'),
            ('XC-RATIO', 'Tỷ số xác định số mũ Laursen', r'$R=V_*/\omega$'),
            ('XC-DEPTH', 'Chiều sâu bình quân và vận tốc tự nhiên', r'$y_1=\Omega/W_1,\quad V=Q/\Omega$'),
            ('XC-NONNEG', 'Không lấy chiều sâu xói âm', r'$y_{sc}=\max(0,y_2-y_0)$')], [
            'Bảng tra số mũ Laursen: R < 0,50 → k₁ = 0,59; 0,50 ≤ R ≤ 2 → k₁ = 0,64; R > 2 → k₁ = 0,69.',
            'Q₁ = Q₂ = Qtk trong mô hình hiện tại, nên tỷ số Q₂/Q₁ bằng 1.',
            'Nếu D₅₀ ≥ 20 mm và y₂ nước trong nhỏ hơn y₂ nước đục, bộ tính lấy giá trị nhỏ hơn và ghi chú điều kiện.',
            'Ω: diện tích mặt cắt ướt tự nhiên (m²); y₀ lấy bằng chiều sâu bình quân hiện tại trong mô hình.',
            'ω là vận tốc lắng nhập vào; bộ tính xói thu hẹp không tự thay ω bằng công thức Rubey.'])
        detail('Nuoc denh', [
            ('DENH-X0', 'Khoảng cách nước dềnh xa nhất', r'$x_0=aL_{ngap}\sqrt{Fr/i_0}$'),
            ('DENH-V', 'Vận tốc trước và sau thu hẹp', r'$V_0=Q/\Omega,\quad V_{cau}=Q/(\Omega-\Omega_{choan})$'),
            ('DENH-NONNEG', 'Giới hạn độ dềnh', r'$\Delta h_{dmax}=\max[0,K(V_{cau}^2-V_{cau0}^2)/(2g)]$')], [
            'Δh_dmax: trị số dềnh lớn nhất phía thượng lưu cầu (m); x₀: khoảng cách dềnh xa nhất (m).',
            'V₀: vận tốc trung bình trên toàn mặt cắt tự nhiên; V_cau0: vận tốc mặt cắt trước thu hẹp (m/s).',
            'V_cau: vận tốc sau khi trừ diện tích choán dòng; Q_cau0: lưu lượng trước thu hẹp (m³/s).',
            'L_ngập: bề rộng ngập; i₀ = S₁: độ dốc mặt nước; Fr = V₀²/(g L_ngập), khác Fr của trụ.',
            'Fr/i₀: thành phần không thứ nguyên; a = 0,73 là hệ số hình thái đang dùng; K: hệ số nước dềnh.',
            'Mô hình hiện lấy Q_cau0 = Qtk và V_cau0 = V₀; Fr/i₀ được giới hạn không nhỏ hơn 0,0001.'])
        detail('PPLL', [
            ('PPLL-H', 'Chiều sâu và khoảng cách chiếu lên mặt cắt', r'$h_i=\max(0,H_{tt}-z_i),\quad \Delta l_i=\Delta l_{input,i}\cos\theta$'),
            ('PPLL-WET', 'Đoạn ngập cả hai đầu', r'$\omega_i=(h_{i-1}+h_i)\Delta l_i/2,\quad A_{pp,i}=(h_{i-1}^{5/3}+h_i^{5/3})\Delta l_i/2$'),
            ('PPLL-PART', 'Đoạn chỉ ngập một đầu', r'$b_i=\Delta l_i d_m/(d_m-d_n),\quad \omega_i=d_m b_i/2,\quad A_{pp,i}=3d_m^{5/3}b_i/8$'),
            ('PPLL-ALPHA', 'Hệ số phân phối vận tốc', r'$\alpha=Q_{tk}/\sum A_{pp,i}$'),
            ('PPLL-Q', 'Lưu lượng đoạn và lưu lượng đơn vị', r'$Q_i=\alpha A_{pp,i},\quad q_i=Q_i/\Delta l_i$'),
            ('PPLL-V', 'Vận tốc bình quân đoạn và vận tốc đến trụ', r'$V_i=Q_i/\omega_i,\quad V_{loc,i}=\alpha h_i^{2/3}$'),
            ('PPLL-NODE', 'Giá trị A_i tại nút trong bảng mẫu', r'$A_{node,i}=h_i^{5/3}\Delta l_i$'),
            ('PPLL-CHECK', 'Kiểm tra bảo toàn lưu lượng', r'$\sum Q_i=Q_{tk}$')], [
            'z_i: cao độ đáy sông (m); Δl_input,i: khoảng cách gốc; Δl_i: khoảng cách đã chiếu theo góc chéo θ (m).',
            'ω_i: diện tích ướt của đoạn (m²); Σω_i cũng có đơn vị m², không phải m.',
            'A_pp,i: hệ số diện tích tích phân dùng để phân phối Q; A_node,i: giá trị tại nút hiển thị trong mẫu.',
            'Bảng xuất có cả A_node,i và A_pp,i để giải thích đúng Q_i, không dùng A_node thay A_pp.',
            'V_loc,i: vận tốc tại nút được dùng cho tính xói trụ; V_i: vận tốc bình quân đoạn.',
            'd_m và d_n: độ sâu có dấu lớn nhất/nhỏ nhất khi chỉ một đầu đoạn ngập; đoạn khô cho ω_i = A_pp,i = 0.',
            'Hệ số Manning được dùng ở tính đường H–Q; phân phối lưu lượng hiện dùng α = Qtk/ΣA_pp,i.'])
        detail('Vcau', [
            ('VCAU-B', 'Bề rộng chiếu thân, bệ và nhóm cọc', r'$b_{than}=a\cos\theta,\quad b_{be}=a_{pc}\cos\theta,\quad b_{coc}=a_{proj}\cos\theta$'),
            ('VCAU-AREA', 'Diện tích choán dòng theo từng tầng ngập', r'$\omega_{choan}=b_{than}h_{than}+b_{be}h_{be}+b_{coc}h_{coc}$'),
            ('VCAU-WIDTH', 'Bề rộng choán dòng bình quân', r'$b_{choan}=\omega_{choan}/h$'),
            ('VCAU-W2', 'Bề rộng và diện tích thoát nước hữu hiệu', r'$W_2=\max(1,W_1-\sum b_{choan}),\quad \Omega_{eff}=\max(0.1,\Omega-\sum\omega_{choan})$'),
            ('VCAU-V', 'Vận tốc dòng chảy dưới cầu', r'$V_{cau}=Q_{tk}/\Omega_{eff}$')], [
            'h_than = max(0, z_water − max(z_tn, z_be + T)); h_be = max(0, min(z_be + T, z_water) − max(z_tn, z_be)).',
            'h_coc = max(0, min(z_be, z_water) − z_tn) khi z_be > z_tn; z_water = z_tn + h.',
            'a, L: bề rộng và chiều dài thân; a_pc, L_pc: bề rộng và chiều dài bệ; T: chiều cao bệ (m).',
            'a_p: đường kính cọc; S: khoảng cách cọc; m/n: số hàng/cột; a_proj: bề rộng chiếu nhóm cọc (m).',
            'z_be: cao độ đáy bệ; h₀,initial = z_be − z_tn; chỉ các tầng thực sự ngập mới tham gia choán dòng.'])
        detail('Xoi mo', [
            ('ABUT-VE', 'Vận tốc và Froude khu vực bị mố chặn', r'$V_e=Q_e/A_e,\quad Fr=V_e/\sqrt{g y_a}$'),
            ('ABUT-K2', 'Hệ số góc mố', r'$K_2=(\theta/90)^{0.13}$'),
            ('ABUT-FROEHLICH', 'Công thức Froehlich khi L′/y_a ≤ 25', r'$y_s=2.27K_1K_2(L^{\prime})^{0.43}y_a^{0.57}Fr^{0.61}+y_a$'),
            ('ABUT-HIRE', 'Công thức HIRE khi L′/y_a > 25', r'$y_s=4y_a Fr^{0.33}(K_1/0.55)K_2$')], [
            'y_a: chiều sâu bình quân khu vực mố cản dòng (m); L′: chiều dài mố cản dòng (m).',
            'Q_e: lưu lượng bị chặn (m³/s); A_e: diện tích bị chặn (m²); V_e: vận tốc (m/s).',
            'K₁ = 1,00 cho tường đứng; 0,82 cho tường đứng có cánh; 0,55 cho mố taluy xiên.',
            'θ: góc dòng chảy với mố; bộ tính giới hạn θ trong [10°; 170°]; K₂ = (θ/90)^0,13.',
            'Cột Ghi chú chỉ rõ Froehlich hay HIRE; nếu y_a ≤ 0,05 m hoặc L′ ≤ 0 thì xói bằng 0.'])
        detail('Tong hop', [
            ('SUM-Y', 'Tổng chiều sâu xói', r'$Y_{total}=y_{deg}+y_{sc}+y_{s,local}$'),
            ('SUM-Z', 'Cao độ đáy sau xói', r'$z_{scour}=z_{tn}-Y_{total}$')], [
            'y_deg: hạ thấp đáy dài hạn; y_sc: xói thu hẹp; y_s,local: xói cục bộ theo loại mố/trụ được chọn (m).',
            'Trụ đơn dùng y_spier; trụ lộ bệ dùng y_spier + y_sfooting; trụ lộ cọc dùng y_spier + y_spc + y_spg.',
            'Xói chung của mô hình hiện tại dùng một giá trị bình quân; ba cột bãi trái/lòng chính/bãi phải là vị trí trình bày.',
            'Giá trị tổng hợp lấy trước làm tròn, nên có thể lệch 0,01 m so với cộng các số đã làm tròn trên bảng.'])

        input_rows = []
        for key, label, unit, note in [
            ('htk', 'Htt — mực nước tính toán', 'm', ''), ('qtk', 'Qtk — lưu lượng thiết kế', 'm³/s', ''),
            ('skew', 'θ — góc chéo dòng chảy', '°', ''), ('s1', 'S₁ — độ dốc', 'm/m', ''),
            ('d50', 'D₅₀ — đường kính hạt', 'mm', ''), ('d84', 'D₈₄ — đường kính hạt hiệu dụng', 'mm', 'Đã xét mặc định 2D₅₀ nếu đầu vào ≤ 0'),
            ('omega', 'ω — vận tốc lắng', 'm/s', 'Giá trị nhập, không tự tính lại'),
            ('n_manning', 'n — hệ số Manning', '', 'Dùng cho đường H–Q'),
            ('y_deg', 'y_deg — hạ thấp dài hạn', 'm', ''), ('W1_up', 'W₁ — bề rộng thượng lưu hiệu dụng', 'm', ''),
            ('W2', 'W₂ — bề rộng thu hẹp', 'm', ''), ('area', 'Ω — diện tích ướt tự nhiên', 'm²', ''),
            ('area_bridge', 'Ω_eff — diện tích thoát nước qua cầu', 'm²', ''),
            ('k1_type', 'Hình dạng mũi trụ', '', ''), ('k3_type', 'Tình trạng đáy sông', '', '')]:
            input_rows.append(dict(parameter=label, value=context.get(key, ''), unit=unit, note=note))
        by_sheet['Vcau']['tables'].insert(0, make_table('Thông số đầu vào và thủy lực dùng trong lần tính', [
            ('parameter','Thông số','',0,'text'), ('value','Giá trị','',6,'input'),
            ('unit','Đơn vị','',0,'text'), ('note','Ghi chú','',0,'text')], input_rows))
        geometry = [dict(p, kind=p['kind']) for p in self._report_piers]
        by_sheet['Vcau']['tables'].insert(1, make_table('Kích thước thân trụ, bệ và móng cọc', [
            ('name','Tên trụ','',0,'text'), ('cdtn','∇tn','m',2,'input'),
            ('a','a_pier','m',2,'input'), ('L','L_pier','m',2,'input'),
            ('apc','a_pc','m',2,'input'), ('Lpc','L_pc','m',2,'input'), ('T','T','m',2,'input'),
            ('z_be','Cao độ đáy bệ','m',2,'input'), ('ho0','h₀,initial','m',2,'output'),
            ('ap','a_p','m',2,'input'), ('S','S','m',2,'input'), ('m','m','',0,'input'),
            ('n','n','',0,'input'), ('aproj','a_proj','m',2,'input'), ('f','f','m',2,'input'),
            ('theta','θ','°',1,'input'), ('kind','Loại trụ','',0,'text')], geometry,
            [('Thân trụ','a','L'), ('Bệ trụ','apc','ho0'), ('Móng cọc','ap','aproj')]))

        # Không để bảng PPLL mô tả sai Ai tích phân và đơn vị Σωi.
        ppll = by_sheet['PPLL']['tables'][0]
        ppll['columns'][6]['label'], ppll['columns'][6]['unit'] = 'Σω_i', 'm²'
        ppll['columns'][8]['label'], ppll['columns'][8]['unit'] = 'A_node,i', 'm⁸/³'
        ppll['columns'] += [dict(key='ai_actual',label='A_pp,i',unit='m⁸/³',digits=6,role='output'),
                            dict(key='vloc',label='V_loc đến trụ',unit='m/s',digits=3,role='output')]
        for i, row in enumerate(ppll['rows']):
            row['ai_actual'] = context.get('ai_vals', [])[i] if i < len(context.get('ai_vals', [])) else ''
            vh = context.get('vh_data', [])
            row['vloc'] = vh[i]['Vloc'] if i < len(vh) else ''
        lookups = [('Hình dạng mũi trụ — K₁', HEC18Tables.PIER_K1),
                   ('Tình trạng đáy sông — K₃', HEC18Tables.PIER_K3)]
        for title, mapping in lookups:
            by_sheet['Xoi cuc tru']['tables'].append(make_table(title, [
                ('condition','Trường hợp','',0,'text'), ('factor','Hệ số','',2,'output'),
                ('note','Căn cứ / ghi chú','',0,'text')],
                [dict(condition=k,factor=v[0],note=v[1]) for k,v in mapping.items()]))
        by_sheet['Xói chung']['tables'].append(make_table('Bảng tra số mũ Laursen k₁', [
            ('condition','V*/ω','',0,'text'), ('factor','k₁','',2,'output'), ('note','Dạng vận chuyển','',0,'text')],
            [dict(condition='R < 0,50',factor=0.59,note='Vận chuyển sát đáy'),
             dict(condition='0,50 ≤ R ≤ 2,00',factor=0.64,note='Lơ lửng một phần'),
             dict(condition='R > 2,00',factor=0.69,note='Chủ yếu lơ lửng')]))
        # Xuất cả cao độ gốc và các tỷ số trung gian, tránh bỏ những yếu tố tra hệ số.
        for sheet, kind in [('XCB-lo coc','Lộ bệ & cọc'), ('XCB-lo be','Lộ bệ')]:
            checks = []
            for p in self._report_piers:
                if p['kind'] != kind:
                    continue
                cp = p['cp']
                checks.append(dict(p, h1=cp['h1'], y2=cp['y2'], h2=cp['h2'],
                    f_a=p['f']/p['a'] if p['a']>0 else 0,
                    h1_a=cp['h1']/p['a'] if p['a']>0 else 0,
                    h2_y2=cp['h2']/cp['y2'] if cp['y2']>0 else 0,
                    T_y2=cp['t_eff']/cp['y2'] if cp['y2']>0 else 0,
                    fr2=cp['fr2'], fr3=cp['fr3'], teff=cp['t_eff'],
                    s_ap=p['S']/p['ap'] if p['ap']>0 else 0,
                    A_ap=p['aproj']/p['ap'] if p['ap']>0 else 0,
                    h3_y3=cp['h3']/cp['y3'] if cp['y3']>0 else 0))
            fields = [('name','Tên trụ','',0,'text'), ('z_be','Cao độ đáy bệ','m',2,'input'),
                ('ho0','h₀,initial','m',2,'output'), ('ho','h₀ sau xói chung','m',2,'output'),
                ('f_a','f/a_pier','',3,'output'), ('h1_a','h₁/a_pier','',3,'output'),
                ('h2_y2','h₂/y₂','',3,'output'), ('T_y2','T_eff/y₂','',3,'output'),
                ('teff','T_eff','m',2,'output'), ('fr2','Fr₂','',3,'output')]
            if sheet == 'XCB-lo coc':
                fields += [('s_ap','S/a_p','',3,'output'), ('A_ap','a_proj/a_p','',3,'output'),
                           ('h3_y3','h₃/y₃','',3,'output'), ('fr3','Fr₃','',3,'output')]
            by_sheet[sheet]['tables'].append(make_table('Thông số trung gian kiểm tra hệ số và cao độ', fields, checks))
        return sections

    def _template_report_sections(self):
        """Bảng chính theo mẫu; căn cứ bổ sung đặt ở phụ lục riêng.

        Không dùng số liệu hay công thức lưu sẵn trong tệp mẫu của công trình khác.
        Hai định dạng dùng cùng thứ tự bảng và cùng kết quả tính hiện hành.
        """
        import copy
        sections = copy.deepcopy(self._report_sections())
        context = self._report_context
        # Trang "hinh thai" trong mẫu Excel: xuất lại hình học phần mặt cắt
        # thực sự ngập nước, sử dụng dữ liệu đã chụp tại lần tính gần nhất.
        vh = context.get('vh_data', [])
        wet = context.get('wet_w', [])
        cos_sk = math.cos(math.radians(context.get('skew', 0)))
        geometry_rows = []
        for i, point in enumerate(vh):
            width = wet[i] if i < len(wet) else 0.0
            area = point['wi']
            dz = point['hi'] - vh[i - 1]['hi'] if i else 0.0
            perimeter = math.hypot(width, dz) if width > 0 else 0.0
            geometry_rows.append(dict(name=point['name'] or f'ĐIỂM {i+1}',
                z=point['z'], h=point['hi'], havg=area / width if width > 0 else 0.0,
                lcheo=point['dl'] / cos_sk if cos_sk > 1e-9 else '',
                skew=context.get('skew', 0), lngang=point['dl'],
                area=area, perimeter=perimeter, note=''))
        geometry_rows.append(dict(name='Tổng', lngang=sum(p['dl'] for p in vh),
            area=sum(p['wi'] for p in vh),
            perimeter=sum(r['perimeter'] for r in geometry_rows)))
        geometry_columns = [dict(key=k, label=label, unit=unit, digits=2,
            role='text' if k in ('name', 'note') else 'output') for k, label, unit in [
            ('name','Bộ phận',''), ('z','CĐTN','m'), ('h','Chiều sâu','m'),
            ('havg','Chiều sâu bình quân','m'), ('lcheo','L chéo','m'),
            ('skew','Góc chéo','°'), ('lngang','L ngang','m'),
            ('area','Diện tích','m²'), ('perimeter','Chu vi ướt','m'), ('note','Ghi chú','')]]
        sections.insert(2, dict(sheet='Hinh thai',
            title='TÍNH DIỆN TÍCH THOÁT NƯỚC VÀ CHU VI ƯỚT TẠI TIM CẦU (ĐIỀU KIỆN TỰ NHIÊN)',
            formulas=[], definitions=['Diện tích và chiều rộng ngập lấy từ các đoạn mặt cắt của lần tính hiện tại; đoạn khô không tính vào chu vi ướt.'],
            tables=[dict(title='', columns=geometry_columns, rows=geometry_rows, groups=())]))
        appendices = []
        main_counts = {'Vcau': 1, 'Xói chung': 1, 'XCB-lo coc': 4,
                       'XCB-lo be': 3, 'Xoi cuc tru': 1}
        for section in sections:
            tables = section['tables']
            if section['sheet'] == 'Vcau':
                primary, extra = tables[2:], tables[:2]
            else:
                count = main_counts.get(section['sheet'], len(tables))
                primary, extra = tables[:count], tables[count:]
            section['tables'] = primary
            if section['sheet'] == 'Xoi cuc tru':
                section['formulas'].append(r'$Fr_1=V_1/\sqrt{g y_1}$')
            detail = section.pop('detail', None)
            if detail or extra:
                appendix = dict(sheet='PL-' + section['sheet'],
                                title='PHỤ LỤC — ' + section['title'],
                                formulas=detail['formulas'] if detail else [],
                                formula_labels=detail.get('formula_labels', []) if detail else [],
                                definitions=detail['definitions'] if detail else [],
                                tables=extra, appendix=True)
                appendices.append(appendix)
            # Nước dềnh và hình học: mẫu đặt giải thích sau bảng kết quả.
            section['explain_after'] = section['sheet'] in ('Vcau', 'Nuoc denh', 'Hinh thai', 'Xói chung', 'Tong hop')
        return sections + appendices

    @staticmethod
    def _report_value(value, column):
        """Giữ tên trụ và ghi chú dạng chữ; chỉ đổi cột số, kể cả ký hiệu khoa học."""
        if value is None or value == '':
            return ''
        if column['role'] == 'text':
            return str(value)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not math.isfinite(number):
            raise ValueError(f"Giá trị không hữu hạn ở cột {column['label']}")
        return number

    @staticmethod
    def _report_column_weights(columns):
        weights = []
        for c in columns:
            if c['key'] in ('parameter', 'condition'):
                weights.append(3.5)
            elif c['key'] == 'value':
                weights.append(2.5)
            elif c['key'] in ('unit', 'factor'):
                weights.append(0.7)
            elif c['key'] in ('note', 'case_note') or c['label'] == 'Ghi chú':
                weights.append(2.2)
            elif c['key'] in ('shape', 'bed') or 'Thuộc loại' in c['label']:
                weights.append(1.8)
            elif c['role'] == 'text':
                weights.append(1.4)
            else:
                weights.append(1.0)
        return weights

    def export_excel_report(self, file_path):
        """Xuất không mở hộp thoại, dùng được cho kiểm thử và tác vụ tự động."""
        import os
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.drawing.image import Image

        sections = self._template_report_sections()
        context = self._report_context or self.project
        wb = Workbook()
        wb.remove(wb.active)
        side = Side(style='thin', color='000000')
        border = Border(left=side, right=side, top=side, bottom=side)
        temp_images = []

        def font(size=10, bold=False, color='000000', italic=False):
            return Font(name='Times New Roman', size=size, bold=bold, color=color, italic=italic)

        def line(ws, row, text, end, size=10, bold=False, italic=False):
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=end)
            cell = ws.cell(row, 1, text)
            cell.font = font(size, bold, italic=italic)
            cell.alignment = Alignment(vertical='center', wrap_text=True)
            ws.row_dimensions[row].height = max(20, 16 * math.ceil(len(text) / max(40, end * 9)))

        def explanations(ws, row, section, count):
            for equation_index, equation in enumerate(section['formulas']):
                labels = section.get('formula_labels', [])
                if equation_index < len(labels):
                    line(ws, row, labels[equation_index], count, 10, True)
                    row += 1
                path, width, height = self._create_equation_img(equation, fontsize=11)
                if not path:
                    raise ValueError(f'Không tạo được ảnh công thức: {equation}')
                temp_images.append(path)
                image = Image(path)
                scale = min(1.0, 1100 / max(1, image.width))
                image.width *= scale
                image.height *= scale
                ws.add_image(image, f'A{row}')
                # Mỗi công thức có vùng riêng; giữ tỷ lệ, không kéo méo ảnh.
                slots = max(2, math.ceil(image.height / 24) + 1)
                for r in range(row, row + slots):
                    ws.row_dimensions[r].height = 18
                row += slots
            if section['definitions']:
                line(ws, row, 'Trong đó:', count, 10, True, True)
                row += 1
                half = max(1, count // 2)
                definitions = section['definitions']
                split = math.ceil(len(definitions) / 2)
                for i in range(split):
                    texts = [definitions[i], definitions[i + split] if i + split < len(definitions) else '']
                    for start, end, text in [(1, half, texts[0]), (half + 1, count, texts[1])]:
                        ws.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)
                        cell = ws.cell(row, start, text)
                        cell.font = font()
                        cell.alignment = Alignment(vertical='center', wrap_text=True)
                    ws.row_dimensions[row].height = 32 if max(map(len, texts)) > 80 else 24
                    row += 1
                row += 2
            return row

        try:
            for section in sections:
                ws = wb.create_sheet(section['sheet'])
                count = max((len(t['columns']) for t in section['tables']), default=16)
                line(ws, 1, section['title'], count, 13, True)
                line(ws, 2, '(Theo Hướng dẫn thủy lực công trình HEC No.18, 2012)', count, 11, True, True)
                line(ws, 3, f"{context.get('bridge_name', '')} — Htt = {context.get('htk', '')} m; Qtk = {context.get('qtk', '')} m³/s", count, 11, True)
                row = 5
                if not section.get('explain_after'):
                    row = explanations(ws, row, section, count)
                for data in section['tables']:
                    cols = data['columns']
                    n = len(cols)
                    # Bảng ngắn vẫn dùng đủ bề rộng trang, không ép bảng đầu vào
                    # vào bốn cột hẹp của bảng trụ ở cùng worksheet.
                    weights = self._report_column_weights(cols)
                    extra = count - n
                    shares = [extra * w / sum(weights) for w in weights]
                    spans = [1 + int(v) for v in shares]
                    remaining = count - sum(spans)
                    for i in sorted(range(n), key=lambda i: shares[i] - int(shares[i]), reverse=True)[:remaining]:
                        spans[i] += 1
                    positions, next_col = [], 1
                    for span in spans:
                        positions.append((next_col, next_col + span - 1))
                        next_col += span
                    if data['title']:
                        line(ws, row, data['title'], count, 11, True, True)
                        row += 1
                    header = row
                    for r in range(header, header + 3):
                        ws.row_dimensions[r].height = 26
                        for c in range(1, count + 1):
                            cell = ws.cell(r, c)
                            cell.border = border
                            cell.font = font(10, True)
                            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                    keys = [c['key'] for c in cols]
                    grouped = set()
                    for title, start, end in data['groups']:
                        first, last = keys.index(start), keys.index(end)
                        a, b = positions[first][0], positions[last][1]
                        ws.merge_cells(start_row=header, start_column=a, end_row=header, end_column=b)
                        ws.cell(header, a, title)
                        grouped.update(range(first, last + 1))
                    for c, column in enumerate(cols, 1):
                        a, b = positions[c - 1]
                        if c - 1 in grouped:
                            ws.merge_cells(start_row=header + 1, start_column=a, end_row=header + 1, end_column=b)
                            ws.cell(header + 1, a, column['label'])
                        else:
                            ws.merge_cells(start_row=header, start_column=a, end_row=header + 1, end_column=b)
                            ws.cell(header, a, column['label'])
                        ws.merge_cells(start_row=header + 2, start_column=a, end_row=header + 2, end_column=b)
                        ws.cell(header + 2, a, f"({column['unit']})" if column['unit'] else '')
                        if column['key'] in ('d50', '3', '10') and column['label'] in ('D₅₀', 'ω'):
                            for r in range(header, header + 3):
                                ws.cell(r, a).fill = PatternFill('solid', fgColor='FFFF99')
                    row += 3
                    for values in data['rows']:
                        row_height = 25
                        for c, column in enumerate(cols, 1):
                            value = self._report_value(values.get(column['key'], ''), column)
                            a, b = positions[c - 1]
                            for physical in range(a, b + 1):
                                ws.cell(row, physical).border = border
                            ws.merge_cells(start_row=row, start_column=a, end_row=row, end_column=b)
                            cell = ws.cell(row, a, value)
                            if isinstance(value, str):
                                cell.data_type = 's'  # Ghi chú bắt đầu bằng '=' vẫn là văn bản.
                            color = 'C00000' if column['role'] == 'input' else ('17365D' if column['role'] == 'output' else '000000')
                            cell.font = font(10, color=color)
                            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                            cell.border = border
                            if isinstance(value, (int, float)):
                                cell.number_format = '0' if column['digits'] == 0 else '0.' + '0' * column['digits']
                            if section['sheet'] == 'Xói chung':
                                cell.fill = PatternFill('solid', fgColor='CCFFFF')
                            if isinstance(value, str):
                                row_height = max(row_height, 6 + 14 * math.ceil(len(value) / max(6, 9 * (b - a + 1))))
                        ws.row_dimensions[row].height = row_height
                        row += 1
                    if not data['rows']:
                        line(ws, row, 'Không có mố/trụ thuộc trường hợp này trong kết quả tính toán.', count, 10, italic=True)
                        row += 1
                    row += 2
                if section.get('explain_after'):
                    row = explanations(ws, row, section, count)
                if section.get('detail'):
                    from openpyxl.worksheet.pagebreak import Break
                    ws.row_breaks.append(Break(id=row - 1))
                    line(ws, row, 'CÔNG THỨC XÁC ĐỊNH THÔNG SỐ, HỆ SỐ VÀ ĐIỀU KIỆN ÁP DỤNG', count, 11, True)
                    row = explanations(ws, row + 1, section['detail'], count)
                widest = max(section['tables'], key=lambda t: len(t['columns']), default=None)
                weights = self._report_column_weights(widest['columns']) if widest else [1] * count
                for c, weight in enumerate(weights, 1):
                    # Tỷ lệ cột số/chữ theo mẫu .xls, tránh thu nhỏ quá mức
                    # bảng rộng khi in vừa một trang ngang.
                    ws.column_dimensions[get_column_letter(c)].width = (9 * weight if section.get('appendix')
                                                                       else 6 * weight)
                ws.freeze_panes = 'C4'
                ws.print_title_rows = '1:3'
                ws.sheet_properties.pageSetUpPr.fitToPage = True
                ws.page_setup.orientation = 'landscape'
                ws.page_setup.paperSize = ws.PAPERSIZE_A3 if count > 18 else ws.PAPERSIZE_A4
                # Chỉ vừa chiều ngang; nhiều bảng/công thức được phép sang
                # trang tiếp theo, tránh chữ quá nhỏ vì ép cả báo cáo vào 1 trang.
                ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
                ws.page_margins.left = ws.page_margins.right = 0.25
                ws.print_options.horizontalCentered = True
                ws.print_area = f'A1:{get_column_letter(count)}{row - 1}'
                ws.oddFooter.center.text = 'Trang &P / &N'
            wb.save(file_path)
        finally:
            for path in temp_images:
                if os.path.exists(path):
                    os.remove(path)

    def export_word_report(self, file_path):
        import os
        from docx import Document
        from docx.shared import Pt, Cm, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.section import WD_ORIENT, WD_SECTION_START
        from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        doc = Document()
        normal = doc.styles['Normal']
        normal.font.name, normal.font.size = 'Times New Roman', Pt(10)
        normal.paragraph_format.space_after = Pt(3)
        context = self._report_context or self.project
        temp_images = []

        def element(tag, attrs):
            item = OxmlElement(tag)
            for key, value in attrs.items():
                item.set(qn(key), str(value))
            return item

        def paragraph(text, bold=False, size=10, center=False):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(text)
            run.bold, run.font.size = bold, Pt(size)
            run.font.name = 'Times New Roman'
            if bold:
                p.paragraph_format.keep_with_next = True
            return p

        def set_cell(cell, text, bold=False, color='000000', size=8):
            cell.text = text
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.space_before = Pt(0)
                for run in p.runs:
                    run.font.name, run.font.size, run.bold = 'Times New Roman', Pt(size), bold
                    run.font.color.rgb = RGBColor.from_string(color)

        def explanations(section_data, usable_cm):
            equations = section_data['formulas']
            paired = 4 if section_data['sheet'] in ('XCB-lo coc', 'XCB-lo be') else 0
            for i in range(0, len(equations)):
                if i < paired and i % 2:
                    continue
                if i < paired:
                    formula_table = doc.add_table(rows=1, cols=2)
                    formula_table.autofit = False
                    for col in formula_table.columns:
                        col.width = Cm(usable_cm / 2)
                    targets = [(formula_table.cell(0, j).paragraphs[0], equations[i + j], usable_cm / 2, i + j)
                               for j in range(2)]
                else:
                    targets = [(doc.add_paragraph(), equations[i], usable_cm, i)]
                for p, equation, available, equation_index in targets:
                    path, width, height = self._create_equation_img(equation, fontsize=11)
                    if not path:
                        raise ValueError(f'Không tạo được ảnh công thức: {equation}')
                    temp_images.append(path)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    labels = section_data.get('formula_labels', [])
                    if equation_index < len(labels):
                        run = p.add_run(labels[equation_index] + '\n')
                        run.bold, run.font.size = True, Pt(10)
                    p.add_run().add_picture(path, width=Inches(min(width, available / 2.54)))
            if section_data['definitions']:
                paragraph('Trong đó:', True)
                definitions = section_data['definitions']
                half = math.ceil(len(definitions) / 2)
                tbl = doc.add_table(rows=half, cols=2)
                tbl.autofit = False
                for c in tbl.columns:
                    c.width = Cm(usable_cm / 2)
                for i in range(half):
                    for j in range(2):
                        k = i + j * half
                        cell = tbl.cell(i, j)
                        cell.width = Cm(usable_cm / 2)
                        if k < len(definitions):
                            set_cell(cell, definitions[k], size=9)
                            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
                doc.add_paragraph()

        try:
            for index, section_data in enumerate(self._template_report_sections()):
                section = doc.sections[0] if index == 0 else doc.add_section(WD_SECTION_START.NEW_PAGE)
                count = max((len(t['columns']) for t in section_data['tables']), default=16)
                section.orientation = WD_ORIENT.LANDSCAPE
                # Mẫu Word dùng A4 ngang, kể cả bảng thân trụ/bệ/nhóm cọc.
                section.page_width = Cm(29.7)
                section.page_height = Cm(21)
                section.left_margin = section.right_margin = Cm(1.2)
                section.top_margin = section.bottom_margin = Cm(1.2)
                usable_cm = section.page_width.cm - section.left_margin.cm - section.right_margin.cm
                paragraph(section_data['title'], True, 13, True)
                p = paragraph('(Theo Hướng dẫn thủy lực công trình HEC No.18, 2012)', True, 10, True)
                p.runs[0].italic = True
                paragraph(f"{context.get('bridge_name', '')} — Htt = {context.get('htk', '')} m; Qtk = {context.get('qtk', '')} m³/s", True, 10, True)
                if not section_data.get('explain_after'):
                    explanations(section_data, usable_cm)
                for table_index, data in enumerate(section_data['tables']):
                    if data['title']:
                        paragraph(data['title'], True, 11)
                    cols, rows = data['columns'], data['rows']
                    tbl = doc.add_table(rows=3 + len(rows), cols=len(cols))
                    tbl.style = 'Table Grid'
                    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                    tbl.autofit = False
                    weights = self._report_column_weights(cols)
                    widths = [usable_cm * w / sum(weights) for w in weights]
                    for c, width in zip(tbl.columns, widths):
                        c.width = Cm(width)
                    for row in tbl.rows:
                        row._tr.get_or_add_trPr().append(element('w:cantSplit', {}))
                        for cell, width in zip(row.cells, widths):
                            cell.width = Cm(width)
                            margins = element('w:tcMar', {})
                            for side in ('top', 'left', 'bottom', 'right'):
                                margins.append(element(f'w:{side}', {'w:w': 25, 'w:type': 'dxa'}))
                            cell._tc.get_or_add_tcPr().append(margins)
                    for row in tbl.rows[:3]:
                        row._tr.get_or_add_trPr().append(element('w:tblHeader', {}))
                    keys = [c['key'] for c in cols]
                    grouped = set()
                    for title, start, end in data['groups']:
                        a, b = keys.index(start), keys.index(end)
                        cell = tbl.cell(0, a).merge(tbl.cell(0, b))
                        set_cell(cell, title, True)
                        grouped.update(range(a, b + 1))
                    for i, column in enumerate(cols):
                        cell = tbl.cell(1, i) if i in grouped else tbl.cell(0, i).merge(tbl.cell(1, i))
                        set_cell(cell, column['label'], True)
                        set_cell(tbl.cell(2, i), f"({column['unit']})" if column['unit'] else '', True)
                        if column['label'] in ('D₅₀', 'ω'):
                            for r in range(3):
                                tbl.cell(r, i)._tc.get_or_add_tcPr().append(element('w:shd', {'w:fill': 'FFFF99'}))
                    for r, values in enumerate(rows, 3):
                        for c, column in enumerate(cols):
                            value = self._report_value(values.get(column['key'], ''), column)
                            text = f"{value:.{column['digits']}f}" if isinstance(value, (int, float)) else str(value)
                            color = 'C00000' if column['role'] == 'input' else ('17365D' if column['role'] == 'output' else '000000')
                            cell = tbl.cell(r, c)
                            set_cell(cell, text, color=color, size=8)
                            if section_data['sheet'] == 'Xói chung':
                                cell._tc.get_or_add_tcPr().append(element('w:shd', {'w:fill': 'CCFFFF'}))
                    if not rows:
                        paragraph('Không có mố/trụ thuộc trường hợp này trong kết quả tính toán.')
                    if table_index + 1 < len(section_data['tables']):
                        doc.add_paragraph()
                if section_data.get('explain_after'):
                    explanations(section_data, usable_cm)
                if section_data.get('detail'):
                    doc.add_page_break()
                    paragraph('CÔNG THỨC XÁC ĐỊNH THÔNG SỐ, HỆ SỐ VÀ ĐIỀU KIỆN ÁP DỤNG', True, 11)
                    explanations(section_data['detail'], usable_cm)
            doc.save(file_path)
        finally:
            for path in temp_images:
                if os.path.exists(path):
                    os.remove(path)

    def action_export_report(self):
        if not self.scour_results:
            messagebox.showwarning('Cảnh báo', 'Vui lòng chạy tính toán trước khi xuất báo cáo!')
            return
        path = filedialog.asksaveasfilename(defaultextension='.xlsx',
                    filetypes=[('Excel Workbook', '*.xlsx')], title='Lưu báo cáo tính xói cầu')
        if not path:
            return
        try:
            self.export_excel_report(path)
            messagebox.showinfo('Thành công', f'Đã xuất báo cáo Excel theo mẫu:\n{path}')
        except Exception as exc:
            messagebox.showerror('Lỗi', f'Xuất Excel thất bại:\n{exc}')

    def action_export_word(self):
        if not self.scour_results:
            messagebox.showwarning('Cảnh báo', 'Vui lòng chạy tính toán trước khi xuất báo cáo!')
            return
        path = filedialog.asksaveasfilename(defaultextension='.docx',
                    filetypes=[('Word Document', '*.docx')], title='Lưu báo cáo tính xói cầu')
        if not path:
            return
        try:
            self.export_word_report(path)
            messagebox.showinfo('Thành công', f'Đã xuất báo cáo Word theo mẫu:\n{path}')
        except Exception as exc:
            messagebox.showerror('Lỗi', f'Xuất Word thất bại:\n{exc}')

# =============================================================================
# KHỞI CHẠY CHƯƠNG TRÌNH
# =============================================================================
if __name__ == "__main__":
    app = MainScourApplication()
    app.mainloop()
