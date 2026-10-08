# -*- coding: utf-8 -*-
"""
PHẦN MỀM TÍNH TOÁN XÓI MỐ TRỤ CẦU ĐA DỰ ÁN THEO TIÊU CHUẨN HEC-18 (FHWA) - MASTER PRO
- Cập nhật Tab 3 chính thức cho Phân phối lưu lượng (PPLL) kèm hiển thị Htk, Qtk.
- Đánh số lại tuần tự Tab 1 -> Tab 8 và các subtab tương ứng.
- Tối ưu bộ nhớ, triệt tiêu rò rỉ RAM với Figure OOP.
- v2: rà soát & sửa công thức theo HEC-18 (K3, K1/K2, Kw, Froehlich mố, trụ phức hợp, vận tốc cục bộ, ...).
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


G = 9.81  # gia tốc trọng trường (m/s2)


def is_abut_name(name):
    """Mố cầu: tên bắt đầu bằng chữ M (M1, M2, Mố trái...). Trụ: T1, T2..."""
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
    # Chỉ các dạng này mới được áp giới hạn ys <= 2.4a / 3.0a (HEC-18 Eq. 7.2)
    ROUND_NOSE = {"Mũi tròn (Round nose)", "Trụ tròn (Circular cylinder)",
                  "Nhóm cọc tròn (Group of cylinders)"}
    DEFAULT_K1 = "Mũi vuông (Square nose)"

    # HEC-18 Table 7.3: chiều cao cồn cát nhỏ 0.6-3 m, trung bình 3-9 m, lớn >= 9 m
    PIER_K3 = {
        "Nước trong / Đáy phẳng / Sóng cát nghịch": (1.1, "K3=1.1: xói nước trong, đáy phẳng, sóng cát nghịch"),
        "Cồn cát nhỏ (0.6 <= H < 3 m)": (1.1, "K3=1.1: cồn cát nhỏ"),
        "Cồn cát trung bình (3 <= H < 9 m)": (1.2, "K3=1.1~1.2 (lấy 1.2, thiên về an toàn)"),
        "Cồn cát lớn (H >= 9 m)": (1.3, "K3=1.3: cồn cát lớn"),
    }
    DEFAULT_K3 = "Nước trong / Đáy phẳng / Sóng cát nghịch"
    # Ánh xạ tên cũ trong file *.json đã lưu (bảng K3 cũ sai ngưỡng chiều cao cồn cát)
    LEGACY_K3 = {
        "Đôn cát nhỏ / Xói nước trong": "Nước trong / Đáy phẳng / Sóng cát nghịch",
        "Đáy phẳng / Sóng cát nghịch": "Nước trong / Đáy phẳng / Sóng cát nghịch",
        "Cồn cát nhỏ (Dunes H < 0.6m)": "Nước trong / Đáy phẳng / Sóng cát nghịch",
        "Cồn cát trung bình (0.6m <= H < 3m)": "Cồn cát nhỏ (0.6 <= H < 3 m)",
        "Cồn cát lớn (Dunes H >= 3m)": "Cồn cát trung bình (3 <= H < 9 m)",
    }

    # HEC-18 Table 8.1 (Froehlich): hệ số hình dạng mố K1
    ABUT_K1 = {
        "Tường đứng (Vertical wall)": (1.00, "K1=1.00"),
        "Tường đứng có tường cánh (Wing walls)": (0.82, "K1=0.82"),
        "Taluy thoải (Spill-through)": (0.55, "K1=0.55"),
    }
    DEFAULT_ABUT = "Tường đứng có tường cánh (Wing walls)"

    @staticmethod
    def get_laursen_k1(ratio_vstar_w):
        if ratio_vstar_w < 0.50:
            return 0.59, "V*/w < 0.50: Bùn cát vận chuyển sát đáy (Contact load)"
        elif ratio_vstar_w <= 2.0:
            return 0.64, "0.50 <= V*/w <= 2.0: Bùn cát lơ lửng một phần"
        else:
            return 0.69, "V*/w > 2.0: Bùn cát chủ yếu lơ lửng (Suspended load)"


# =============================================================================
# 2. TOÁN HỌC & CÔNG THỨC HEC-18 (hàm thuần, không phụ thuộc giao diện)
# =============================================================================
class HEC18Calculations:
    @staticmethod
    def fall_velocity_rubey(d_m, nu=1.0e-6, s=2.65):
        """Vận tốc lắng chìm w (m/s) theo Rubey - dùng để kiểm tra chéo giá trị w nhập tay."""
        d = max(d_m, 1e-6)
        t = 36.0 * nu ** 2 / (G * d ** 3 * (s - 1.0))
        f = math.sqrt(2.0 / 3.0 + t) - math.sqrt(t)
        return f * math.sqrt((s - 1.0) * G * d)

    @staticmethod
    def critical_velocity_vc(y1, d50_m):
        """HEC-18 Eq. 6.1 (SI): Vc = 6.19 y^(1/6) D50^(1/3)"""
        y_val = max(0.01, y1)
        d_val = max(0.00001, d50_m)
        return 6.19 * (y_val ** (1.0 / 6.0)) * (d_val ** (1.0 / 3.0))

    @staticmethod
    def wet_segment(d1, d2, dl):
        """Đoạn mặt cắt giữa 2 điểm có độ sâu ĐẠI SỐ d1, d2 (âm = khô).
        Trả về (bề rộng ướt, diện tích ướt, tích phân h^(5/3)dx).
        Đoạn ngập hoàn toàn: dùng trung bình h^(5/3) như bảng tính gốc.
        Đoạn ngập một phần: cắt tại mép nước (bảng cũ lấy nguyên dl -> thừa bề rộng & diện tích)."""
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
        """HEC-18: góc tấn công > 5° thì K2 chi phối, K1 lấy bằng 1.0 cho mọi dạng mũi."""
        return 1.0 if abs(theta_deg) > 5.0 else k1

    @staticmethod
    def pier_k2(theta_deg, L, a):
        """HEC-18 Eq. 7.4, L/a không lấy quá 12."""
        if abs(theta_deg) < 1e-9 or a <= 0:
            return 1.0
        rad = math.radians(abs(theta_deg))
        l_a = min(12.0, max(0.0, L) / a)
        return min(5.0, (math.cos(rad) + l_a * math.sin(rad)) ** 0.65)

    @staticmethod
    def kw_wide_pier(y, a, fr, v_over_vc, d50_m):
        """Hệ số trụ rộng nước nông (Johnson & Torrico), điều kiện y/a<0.8, a>50*D50, Fr<1. Kw<=1."""
        if a <= 0 or y <= 0 or fr <= 0 or fr >= 1.0 or (y / a) >= 0.8 or a <= 50.0 * d50_m:
            return 1.0
        if v_over_vc < 1.0:
            kw = 2.58 * ((y / a) ** 0.34) * (fr ** 0.65)
        else:
            kw = 1.0 * ((y / a) ** 0.13) * (fr ** 0.25)
        return min(1.0, kw)

    @staticmethod
    def pier_scour_csu(y1, v1, a, k1, k2, k3, kw=1.0, capped=False):
        """HEC-18 Eq. 7.1. capped=True (mũi tròn, dòng thẳng góc): ys <= 2.4a (Fr<=0.8) hoặc 3.0a."""
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
        """Thân trụ + bệ + nhóm cọc (cộng dồn 3 thành phần).
        ho: cao bệ (đáy bệ) so với ĐÁY ĐÃ HẠ (sau hạ thấp dài hạn + xói co hẹp), dương = bệ nằm trên đáy."""
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
        t_eff = T + min(0.0, h2)                       # bề dày bệ thực sự lộ ra khỏi đáy
        apc_star = HEC18Calculations.equivalent_width_pilecap(max(0.0, h2), y2, t_eff, apc)
        ys_pc = 2.0 * k1 * k2 * k3 * (apc_star ** 0.65) * (y2 ** 0.35) * (fr2 ** 0.43)

        h3 = ho + 0.5 * ys_pier + 0.5 * ys_pc          # chiều cao nhóm cọc lộ sau khi xói thân + bệ
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
        """HEC-18 Ch.6. Live-bed (Laursen, Eq. 6.2) hoặc clear-water (Eq. 6.4), Q2/Q1 = 1."""
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
            if d50_m >= 0.02 and y2_cw < y2_lb:      # vật liệu thô: lấy giá trị nhỏ hơn
                y2 = y2_cw
                note = "D50>=20mm: lấy min(live-bed, clear-water)"
        else:
            mode = "Xói nước trong"
            y2 = y2_cw
        return dict(vc=vc, v_star=v_star, ratio_vw=ratio_vw, k1=k1_l, k1_desc=k1_desc, dm=dm,
                    mode=mode, y2=y2, ysc=max(0.0, y2 - y1), note=note)

    # -------------------------------- MỐ CẦU -------------------------------
    @staticmethod
    def abutment_scour(ya, ve, l_prime, k1_abut, skew_deg):
        """HEC-18 Ch.8. Froehlich: ys = ya*(2.27 K1 K2 (L'/ya)^0.43 Fr^0.61 + 1)  (ys là chiều sâu xói,
        số +1 đã nằm trong công thức). L'/ya > 25 -> HIRE: ys = 4 ya Fr^0.33 (K1/0.55) K2."""
        if ya <= 0.05:
            return dict(fr=0.0, k2=1.0, theta=90.0, ys=0.0, method="-")
        fr = max(0.0, ve) / math.sqrt(G * ya)
        theta = 90.0 + abs(skew_deg)          # mái taluy hướng lên thượng lưu: thiên về an toàn
        k2 = (theta / 90.0) ** 0.13
        ratio = l_prime / ya
        if ratio > 25.0:
            ys = 4.0 * ya * (fr ** 0.33) * (k1_abut / 0.55) * k2
            method = "HIRE"
        else:
            ys = ya * (2.27 * k1_abut * k2 * (ratio ** 0.43) * (fr ** 0.61) + 1.0)
            method = "Froehlich"
        return dict(fr=fr, k2=k2, theta=theta, ys=max(0.0, ys), method=method)


# =============================================================================
# 3. GIAO DIỆN PHẦN MỀM CHÍNH (GUI)
# =============================================================================
class MainScourApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEC-18 BRIDGE SCOUR SYSTEM PRO - PHẦN MỀM TÍNH TOÁN XÓI CẦU ĐA DỰ ÁN")
        self.geometry("1420x930")
        self.minsize(1200, 780)

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
            "k1_type": HEC18Tables.DEFAULT_K1,
            "abut_type": HEC18Tables.DEFAULT_ABUT,
            "d84": 0.0,
            "w1_up": 0.0,
            "cross_section": [],
            "piers_detail": []
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
        menu_cfg.add_command(label="Cấu Hình Kích Thước Bệ & Cọc (Sơ đồ CAD)...", command=self.dialog_edit_piers_detail)
        menubar.add_cascade(label="Cấu Hình Móng Bệ", menu=menu_cfg)

        menu_calc = tk.Menu(menubar, tearoff=0)
        menu_calc.add_command(label="Tính Đường Quan Hệ H-Q / H-V", command=self.calc_hq_curve)
        menu_calc.add_command(label="Chạy Tính Toàn Bộ Hệ Thống Xói (HEC-18)", command=self.run_full_system)
        menubar.add_cascade(label="Thực Thi Tính Toán", menu=menu_calc)

        self.config(menu=menubar)

    def action_new_project(self):
        if messagebox.askyesno("Tạo mới", "Tạo dự án mới? Dữ liệu hiện tại chưa lưu sẽ mất."):
            self.project["project_name"] = "Dự Án Mới"
            self.project["bridge_name"] = "Cầu Mới"
            self.project["cross_section"] = []
            self.project["piers_detail"] = []
            self._refresh_tab1_table()
            self.lbl_title.config(text="DỰ ÁN: CẦU MỚI | CÔNG TRÌNH: CẦU MỚI")

    def action_save_project(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            title="Lưu file cấu hình dự án cầu"
        )
        if not file_path:
            return
        for k in self.t1_entries:
            try:
                self.project[k] = float(self.t1_entries[k].get())
            except Exception:
                pass
        self.project["k3_type"] = self.cb_k3.get()
        self.project["k1_type"] = self.cb_k1.get()
        self.project["abut_type"] = self.cb_ab.get()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.project, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Thành công", f"Đã lưu file dự án tại:\n{file_path}")

    def action_open_project(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")],
            title="Mở hồ sơ dự án cầu (*.json)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.project = {**copy.deepcopy(self._project_defaults), **data}
            self.project["k3_type"] = HEC18Tables.LEGACY_K3.get(self.project["k3_type"], self.project["k3_type"])
            self.lbl_title.config(
                text=f"DỰ ÁN: {self.project.get('project_name','').upper()} | CÔNG TRÌNH: {self.project.get('bridge_name','').upper()}"
            )
            for k in self.t1_entries:
                if k in self.project:
                    self.t1_entries[k].delete(0, tk.END)
                    self.t1_entries[k].insert(0, str(self.project[k]))
            self.cb_k3.set(self.project["k3_type"])
            self.cb_k1.set(self.project["k1_type"])
            self.cb_ab.set(self.project["abut_type"])
            self.sync_piers_detail()
            self._refresh_tab1_table()
            messagebox.showinfo("Thành công", f"Đã mở dự án cầu: {self.project.get('bridge_name')}!")
        except Exception as e:
            messagebox.showerror("Lỗi mở file", f"Không đọc được file: {e}")

    def action_import_excel(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Excel Files", "*.xlsx *.xls")],
            title="Chọn file Excel mặt cắt sông"
        )
        if not file_path:
            return

        try:
            df = pd.read_excel(file_path)
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            str_cols = df.select_dtypes(include=['object']).columns.tolist()

            if len(num_cols) < 2:
                messagebox.showerror("Lỗi", "File Excel phải có ít nhất 2 cột số (Khoảng cách và Cao độ)!")
                return

            col1 = num_cols[0]
            col2 = num_cols[1]
            c1_name = str(col1).lower()
            c2_name = str(col2).lower()
            c1_vals = df[col1].dropna().values
            c2_vals = df[col2].dropna().values

            is_c1_elev = any(v < 0 for v in c1_vals) or any(w in c1_name for w in ['cao', 'z', 'elev', 'cd', 'đáy'])
            is_c2_elev = any(v < 0 for v in c2_vals) or any(w in c2_name for w in ['cao', 'z', 'elev', 'cd', 'đáy'])
            c1_inc = all(c1_vals[i] <= c1_vals[i+1] for i in range(len(c1_vals)-1)) if len(c1_vals) > 1 else False
            c2_inc = all(c2_vals[i] <= c2_vals[i+1] for i in range(len(c2_vals)-1)) if len(c2_vals) > 1 else False

            if (c1_inc and not is_c1_elev) or is_c2_elev:
                x_col, z_col, x_is_cum = col1, col2, c1_inc
            elif (c2_inc and not is_c2_elev) or is_c1_elev:
                x_col, z_col, x_is_cum = col2, col1, c2_inc
            else:
                if max(c1_vals) > max(c2_vals):
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
                    if idx == 0:
                        l_cheo = 0.0
                        prev_x = raw_x
                    else:
                        l_cheo = max(0.0, raw_x - prev_x)
                        prev_x = raw_x
                else:
                    l_cheo = max(0.0, raw_x)

                p_type = "Điểm tự nhiên" if not name else ("Mố cầu" if is_abut_name(name) else "Trụ đơn")
                a = 2.0 if p_type == "Trụ đơn" else 0.0
                L = 1.5 if p_type == "Trụ đơn" else 0.0
                k1 = 1.0 if is_abut_name(name) else 1.1

                self.project["cross_section"].append([stt, name, z_val, l_cheo, p_type, a, L, k1])

            self.sync_piers_detail()
            self._refresh_tab1_table()
            messagebox.showinfo("Thành công", f"Đã nạp {len(self.project['cross_section'])} điểm mặt cắt từ Excel!\n- Cột Khoảng Cách: {x_col}\n- Cột Cao Độ: {z_col}")
        except Exception as e:
            messagebox.showerror("Lỗi đọc Excel", f"Không thể đọc file: {e}")

    def action_export_excel(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            title="Lưu dữ liệu mặt cắt ra Excel"
        )
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
        dlg.geometry("540x360")
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
            self.lbl_title.config(
                text=f"DỰ ÁN: {self.project['project_name'].upper()} | CÔNG TRÌNH: {self.project['bridge_name'].upper()}"
            )
            dlg.destroy()
            messagebox.showinfo("Thành công", f"Đã lưu thông tin dự án cầu: {self.project['bridge_name']}!")

        ttk.Button(dlg, text="Lưu Cấu Hình", command=save).grid(row=len(fields), column=0, columnspan=2, pady=16)

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

        btn_cad = tk.Button(
            f_top,
            text="📐 Cấu Hình Bệ & Cọc (CAD)",
            bg="#E3F2FD",
            fg="#0D47A1",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            relief=tk.GROOVE,
            cursor="hand2",
            command=self.dialog_edit_piers_detail
        )
        btn_cad.pack(side=tk.RIGHT, padx=6, pady=6)

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

        f_left = ttk.LabelFrame(pane, text="Thông Số Thủy Lực Thiết Kế Cầu")
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
            ("Bề rộng lòng chủ thượng lưu W1 (m) [0 = theo mặt cắt]:", "w1_up"),
        ]

        for r, (txt, k) in enumerate(inputs):
            ttk.Label(f_left, text=txt).grid(row=r, column=0, sticky=tk.W, padx=8, pady=4)
            e = ttk.Entry(f_left, width=15)
            e.insert(0, str(self.project[k]))
            e.grid(row=r, column=1, sticky=tk.W, padx=8, pady=4)
            self.t1_entries[k] = e

        ttk.Label(f_left, text="Tình trạng đáy sông K3:").grid(row=len(inputs), column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_k3 = ttk.Combobox(f_left, values=list(HEC18Tables.PIER_K3.keys()), state="readonly", width=36)
        self.cb_k3.set(self.project["k3_type"])
        self.cb_k3.grid(row=len(inputs), column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Label(f_left, text="Dạng mũi trụ K1:").grid(row=len(inputs)+1, column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_k1 = ttk.Combobox(f_left, values=list(HEC18Tables.PIER_K1.keys()), state="readonly", width=36)
        self.cb_k1.set(self.project["k1_type"])
        self.cb_k1.grid(row=len(inputs)+1, column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Label(f_left, text="Dạng mố K1 (Froehlich):").grid(row=len(inputs)+2, column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_ab = ttk.Combobox(f_left, values=list(HEC18Tables.ABUT_K1.keys()), state="readonly", width=36)
        self.cb_ab.set(self.project["abut_type"])
        self.cb_ab.grid(row=len(inputs)+2, column=1, sticky=tk.W, padx=8, pady=4)

        f_btn = ttk.Frame(f_left)
        f_btn.grid(row=len(inputs)+3, column=0, columnspan=2, pady=10, padx=8, sticky=tk.EW)

        ttk.Button(f_btn, text=">>> CHẠY TÍNH TOÁN TOÀN BỘ <<<", command=self.run_full_system).pack(fill=tk.X, pady=3)
        ttk.Button(f_btn, text="CẤU HÌNH CHI TIẾT BỆ & CỌC (CAD)...", command=self.dialog_edit_piers_detail).pack(fill=tk.X, pady=3)
        ttk.Button(f_btn, text="Nhập Mặt Cắt Từ File Excel...", command=self.action_import_excel).pack(fill=tk.X, pady=3)
        ttk.Button(f_btn, text="ĐẢO CỘT (CĐTN <-> Khoảng Cách)", command=self.swap_columns_manual).pack(fill=tk.X, pady=3)

        f_right = ttk.LabelFrame(pane, text="Bảng Tọa Độ Mặt Cắt Sông & Bố Trí Mố Trụ (Sheet hinh thai)")
        pane.add(f_right, weight=3)

        f_fast = ttk.Frame(f_right)
        f_fast.pack(fill=tk.X, padx=5, pady=4)

        ttk.Label(f_fast, text="Tên mố/trụ:").grid(row=0, column=0, padx=2)
        self.eq_name = ttk.Entry(f_fast, width=8)
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

        cols = ("STT", "Tên Mố/Trụ", "Cao Độ CĐTN (m)", "L chéo (m)", "L ngang (m)", "Độ sâu h (m)", "Phân Loại", "Bề rộng a (m)", "Dài L (m)")
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
            self.sync_piers_detail()
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
            self.sync_piers_detail()
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
        self.sync_piers_detail()
        self._refresh_tab1_table()

    def sync_piers_detail(self):
        existing_map = {d["name"]: d for d in self.project.get("piers_detail", [])}
        synced = []
        for r in self.project.get("cross_section", []):
            name = str(r[1]).strip()
            if name:
                cdtn = float(r[2])
                a_val = float(r[5]) if float(r[5]) > 0 else 2.0
                L_val = float(r[6]) if float(r[6]) > 0 else 1.5
                is_abutment = is_abut_name(name)

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
                    synced.append(d)
                else:
                    default_z_be = cdtn - 1.40
                    d = {
                        "name": name,
                        "cdtn": cdtn,
                        "z_be": default_z_be,
                        "z_day_be": default_z_be,
                        "ho": -1.40,
                        "apier": 0.0 if is_abutment else a_val,
                        "Lpier": 0.0 if is_abutment else L_val,
                        "apc": 6.0 if is_abutment else max(6.0, a_val * 3.0),
                        "Lpc": 13.32,
                        "T": 2.0 if not is_abutment else 1.5,
                        "f": 1.85,
                        "ap": 1.20,
                        "S": 4.20,
                        "m": 2,
                        "n": 3,
                        "aproj": 3.60
                    }
                    synced.append(d)
        self.project["piers_detail"] = synced

    def dialog_edit_piers_detail(self):
        self.sync_piers_detail()

        dlg = tk.Toplevel(self)
        dlg.title("Cấu Hình Chi Tiết Kích Thước Bệ Đài & Nhóm Cọc (Nhập Cao Độ Đáy Bệ)")
        dlg.geometry("1300x750")
        dlg.minsize(1150, 680)
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

        ttk.Label(f_sub1, text="Tên mố/trụ:").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
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

        ttk.Label(f_sub2, text="ho tự tính = Zđáy-CĐTN:").grid(row=4, column=0, sticky=tk.W, padx=3, pady=2)
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

        f_right_side = ttk.LabelFrame(pane, text="Sơ Đồ Minh Họa & Hướng Dẫn Tra Cứu Thông Số Từ File CAD")
        pane.add(f_right_side, weight=2)

        fig_cad = Figure(figsize=(5.0, 3.4), dpi=100)
        fig_cad.patch.set_facecolor('#F8F9FA')
        ax_elev = fig_cad.add_subplot(2, 1, 1)
        ax_plan = fig_cad.add_subplot(2, 1, 2)
        fig_cad.tight_layout(pad=2.0)

        canvas_cad = FigureCanvasTkAgg(fig_cad, master=f_right_side)
        canvas_cad.get_tk_widget().pack(fill=tk.X, padx=4, pady=2)

        txt_guide = tk.Text(f_right_side, height=12, bg="#FFFFFF", font=("Segoe UI", 9), padx=6, pady=4)
        txt_guide.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        guide_content = """❖ HƯỚNG DẪN ĐỐI CHIẾU THÔNG SỐ VỚI BẢN VẼ AUTOCAD:
1. THÂN TRỤ (Pier Stem):
   • a: Bề rộng thân trụ (m) - Đo trên bản vẽ Mặt cắt ngang cầu vuông góc hướng dòng.
   • L: Chiều dài thân trụ (m) - Đo trên bản vẽ Mặt bằng trụ dọc theo hướng dòng chảy.
2. MÓNG BỆ ĐÀI CỌC (Footing):
   • apc: Bề rộng bệ đài (m) - Bề rộng bệ theo phương vuông góc hướng dòng.
   • Lpc: Chiều dài bệ đài (m) - Chiều dài bệ theo phương dọc dòng chảy.
   • T: Chiều dày bệ móng (m) - Chiều cao từ đáy đài đến đỉnh đài.
   • Cao độ đáy bệ Z_đáy (m): Nhập trực tiếp cao độ đáy đài từ CAD.
     Phần mềm tự tính: ho = Z_đáy - CĐTN (khoảng cách so đáy sông).
     > ho <= 0: Đáy đài chôn sâu dưới đáy sông -> CỌC KHÔNG BỘC LỘ (yspg = 0.00 m).
     > ho > 0: Đáy đài nằm lơ lửng trên đáy sông -> LỘ CỌC TRONG DÒNG CHẢY (yspg > 0).
   • f: Gờ bệ trước mũi trụ (m) - Đo từ mép mũi thân trụ ra mép ngoài cùng của bệ đài.
3. NHÓM CỌC (Pile Group):
   • ap: Bề rộng / đường kính cọc (m) - Đường kính cọc D.
   • S: Cự ly tim cọc (m) - Khoảng cách giữa 2 tim cọc liền kề.
   • m: Số hàng cọc theo chiều dọc dòng chảy.
   • n: Số cột cọc theo chiều ngang tim cầu.
   • aproj: Tổng bề rộng hình chiếu cọc (m) - Thường aproj = n * ap.
"""
        txt_guide.insert(tk.END, guide_content)
        txt_guide.config(state=tk.DISABLED)

        def draw_cad_preview():
            ax_elev.clear()
            ax_elev.set_title("MẶT ĐỨNG TRỤ & MÓNG (Bản vẽ Trắc dọc/đứng CAD)", fontsize=8, fontweight="bold", color="#0D47A1")
            ax_elev.axhline(0, color="#795548", linestyle="-", linewidth=2)
            ax_elev.text(0.1, -0.22, "Đáy sông (CĐTN)", color="#795548", fontsize=7, fontweight="bold")
            ax_elev.axhline(3.3, color="#1E88E5", linestyle="--", linewidth=1.2)
            ax_elev.text(0.1, 3.45, "Mực nước Htk", color="#1E88E5", fontsize=7, fontweight="bold")

            ax_elev.add_patch(patches.Rectangle((1.5, 1.2), 1.0, 2.5, facecolor="#90A4AE", edgecolor="#37474F", linewidth=1.2))
            ax_elev.text(2.0, 2.3, "Thân trụ (a x L)", ha="center", fontsize=7, fontweight="bold")
            ax_elev.annotate("", xy=(1.5, 3.9), xytext=(2.5, 3.9), arrowprops=dict(arrowstyle="<->", color="red"))
            ax_elev.text(2.0, 4.05, "a (Bề rộng)", ha="center", fontsize=7, color="red")

            ax_elev.add_patch(patches.Rectangle((0.8, 0.4), 2.4, 0.8, facecolor="#B0BEC5", edgecolor="#37474F", linewidth=1.2))
            ax_elev.text(2.0, 0.75, "Bệ đài (apc x Lpc)", ha="center", fontsize=7, fontweight="bold")
            ax_elev.annotate("", xy=(3.3, 0.4), xytext=(3.3, 1.2), arrowprops=dict(arrowstyle="<->", color="blue"))
            ax_elev.text(3.4, 0.75, "T (Chiều cao bệ)", va="center", fontsize=7, color="blue")
            ax_elev.annotate("", xy=(3.3, 0.0), xytext=(3.3, 0.4), arrowprops=dict(arrowstyle="<->", color="purple"))
            ax_elev.text(3.4, 0.18, "ho = Zđáy-CĐTN", va="center", fontsize=7, color="purple")
            ax_elev.annotate("", xy=(0.8, 1.3), xytext=(1.5, 1.3), arrowprops=dict(arrowstyle="<->", color="green"))
            ax_elev.text(1.15, 1.45, "f (Gờ)", ha="center", fontsize=7, color="green")

            for px in [1.0, 1.6, 2.3, 2.9]:
                ax_elev.add_patch(patches.Rectangle((px - 0.08, -1.3), 0.16, 1.7, facecolor="#CFD8DC", edgecolor="#455A64", linewidth=1.0))
            ax_elev.text(2.0, -0.65, "Nhóm cọc", ha="center", fontsize=7, fontweight="bold")
            ax_elev.annotate("", xy=(0.92, -1.45), xytext=(1.08, -1.45), arrowprops=dict(arrowstyle="<->", color="red"))
            ax_elev.text(1.0, -1.75, "ap", ha="center", fontsize=7, color="red")
            ax_elev.set_xlim(0, 4.6)
            ax_elev.set_ylim(-1.9, 4.5)
            ax_elev.axis("off")

            ax_plan.clear()
            ax_plan.set_title("MẶT BẰNG BỐ TRÍ CỌC & BỆ (Bản vẽ Mặt bằng móng CAD)", fontsize=8, fontweight="bold", color="#0D47A1")
            ax_plan.add_patch(patches.Rectangle((0.5, 0.4), 2.8, 1.8, facecolor="#ECEFF1", edgecolor="#37474F", linewidth=1.2, linestyle="--"))
            ax_plan.text(1.9, 0.2, "Bề rộng bệ apc", ha="center", fontsize=7, color="blue", fontweight="bold")
            ax_plan.text(0.3, 1.3, "Lpc", va="center", rotation=90, fontsize=7, color="blue", fontweight="bold")

            ax_plan.add_patch(patches.Rectangle((1.2, 0.7), 1.4, 1.2, facecolor="#CFD8DC", edgecolor="#37474F", linewidth=1.0))
            ax_plan.text(1.9, 1.3, "Thân (a x L)", ha="center", fontsize=7)

            for r in range(3):
                for c in range(4):
                    cx = 0.8 + c * 0.7
                    cy = 0.6 + r * 0.7
                    ax_plan.add_patch(patches.Circle((cx, cy), 0.09, facecolor="#78909C", edgecolor="#263238", linewidth=0.8))

            ax_plan.annotate("", xy=(0.8, 2.3), xytext=(1.5, 2.3), arrowprops=dict(arrowstyle="<->", color="magenta"))
            ax_plan.text(1.15, 2.45, "S (Cự ly cọc)", ha="center", fontsize=7, color="magenta")
            ax_plan.annotate("Dòng chảy ->", xy=(0.5, 2.6), xytext=(2.2, 2.6),
                             arrowprops=dict(facecolor='red', edgecolor='red', width=1.5, headwidth=5))
            ax_plan.text(0.5, 2.8, "m: số hàng dọc dòng; n: số cột ngang tim", fontsize=7, color="#C62828")
            ax_plan.set_xlim(0, 3.8)
            ax_plan.set_ylim(0, 3.1)
            ax_plan.axis("off")

            canvas_cad.draw()

        draw_cad_preview()

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
            if not messagebox.askyesno("Xác nhận", "Bạn có muốn áp dụng kích thước Bệ và Nhóm Cọc này cho TẤT CẢ các trụ không?"):
                return
            for d in self.project["piers_detail"]:
                if not is_abut_name(d["name"]):
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
        ttk.Button(f_acts, text="ÁP DỤNG CHO TẤT CẢ CÁC TRỤ", command=apply_all_piers).pack(side=tk.LEFT, padx=4)
        ttk.Button(f_acts, text="Đóng Cửa Sổ", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

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
    # TAB 3: PHÂN PHỐI LƯU LƯỢNG & TỐC ĐỘ DÒNG CHẢY Htk (Sheet PPLL / Htk)
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
    # TAB 4: CHOÁN DÒNG VCAU
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
    # TAB 5: NƯỚC DỀNH (SHEET denh)
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
    # TAB 6: XÓI CO HẸP (SHEET xoi chung)
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
    # TAB 7: TÍNH CÁC LOẠI XÓI CỤC BỘ MỐ & TRỤ (CHI TIẾT 4 BẢNG THEO HEC-18)
    # =========================================================================
    def _init_tab7(self):
        f_ctrl = ttk.Frame(self.tab7)
        f_ctrl.pack(fill=tk.X, padx=10, pady=4)

        btn_recalc = ttk.Button(f_ctrl, text=">>> TÍNH TOÁN & CẬP NHẬT TẤT CẢ CÁC BẢNG XÓI CỤC BỘ <<<", command=self.run_full_system)
        btn_recalc.pack(side=tk.LEFT, padx=5)

        self.nb_scour = ttk.Notebook(self.tab7)
        self.nb_scour.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # ---------------- 7.1: TRỤ ĐƠN ĐẶC (Xoi cuc tru) ----------------
        self.subtab_single_pier = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_single_pier, text=" 7.1 Trụ Đơn Đặc (xoi cuc tru) ")

        f_fml_71 = ttk.LabelFrame(self.subtab_single_pier, text="Công Thức Xói Cục Bộ Trụ Đơn Theo CSU (HEC-18 Eq 7.1)")
        f_fml_71.pack(fill=tk.X, padx=6, pady=3)
        txt_71 = (
            "• Chiều sâu xói cục bộ:  yspier = 2.0 * K1 * K2 * K3 * Kw * a^0.65 * y1^0.35 * Fr1^0.43   (m)\n"
            "  Trong đó: Fr1 = V1 / (g * y1)^0.5 | K2 = [cos(θ) + (L/a)*sin(θ)]^0.65 | Kw: Hiệu chỉnh trụ rộng khi y1/a < 0.8\n"
            "  Khống chế cực đại (chỉ mũi tròn, dòng thẳng góc θ<=5°): yspier <= 2.4*a (Fr1<=0.8) hoặc 3.0*a (Fr1>0.8)\n"
            "  θ > 5°: K1 = 1.0 | L/a <= 12 | Kw: y1/a<0.8 (V/Vc<1: 2.58(y/a)^0.34 Fr^0.65 ; V/Vc>=1: (y/a)^0.13 Fr^0.25), Kw<=1"
        )
        tk.Label(f_fml_71, text=txt_71, justify=tk.LEFT, font=("Consolas", 9), fg="#0D47A1", bg="#F4F6F9").pack(fill=tk.X, padx=4, pady=3)

        cols_single = (
            "No. Trụ", "CĐTN (m)", "y1 (m)", "V1 (m/s)", "Fr1", "a (m)", "H.D. trụ", "K1", "θ (°)", "L (m)",
            "K2", "Đáy sông", "K3", "D50 (mm)", "Vc (m/s)", "V/Vc", "Kw", "yspier (m)", "CĐ sau xói (m)", "Ghi chú"
        )
        self.tree_single_pier = ttk.Treeview(self.subtab_single_pier, columns=cols_single, show="headings", height=12)
        for c in cols_single:
            self.tree_single_pier.heading(c, text=c)
            self.tree_single_pier.column(c, anchor=tk.CENTER, width=78)

        s_single_x = ttk.Scrollbar(self.subtab_single_pier, orient=tk.HORIZONTAL, command=self.tree_single_pier.xview)
        self.tree_single_pier.configure(xscrollcommand=s_single_x.set)
        self.tree_single_pier.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)
        s_single_x.pack(side=tk.BOTTOM, fill=tk.X, padx=4)

        # ---------------- 7.2: TRỤ LỘ BỆ (XCB-Lo Be) ----------------
        self.subtab_lobe = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_lobe, text=" 7.2 Trụ Lộ Bệ (XCB-Lo Be) ")

        f_fml_72 = ttk.LabelFrame(self.subtab_lobe, text="Công Thức Phân Tích Trụ Có Bệ Lộ Dòng Chảy (HEC-18 Sec 7.5.4)")
        f_fml_72.pack(fill=tk.X, padx=6, pady=2)
        txt_72 = (
            "• Tổng xói cục bộ:  ys = yspier + ysfooting\n"
            "• Xói thân trụ:  yspier = Khpier * [2.0 * K1 * K2 * K3 * Kw * apier^0.65 * y1^0.35 * Fr1^0.43]\n"
            "• Xói bệ đài:  ysfooting = 2.0 * K1 * K2 * K3 * Kw * af^0.65 * yf^0.35 * Frf^0.43\n"
            "  Với: y2 = y1 + yspier/2;  V2 = V1*(y1/y2);  yf = h1 + yspier/2;  Vf = V2 * ln(10.93*yf/Ks + 1) / ln(10.93*y2/Ks + 1)\n"
            "  (*) Khi ho <= 0 (đáy bệ ngàm đất): Case 2 HEC-18 -> Cọc ngàm trong đất KHÔNG tính xói cọc!"
        )
        tk.Label(f_fml_72, text=txt_72, justify=tk.LEFT, font=("Consolas", 8), fg="#0D47A1", bg="#F4F6F9").pack(fill=tk.X, padx=4, pady=2)

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
        cols_lobe_3 = ("STT", "Tên Trụ", "CĐTN (m)", "CĐ đáy bệ (m)", "ho (m)", "Chiều sâu xói thân ys,pier (m)", "Chiều sâu xói bệ ys,footing (m)", "Tổng chiều sâu xói ys (m)", "Cao độ đáy xói (m)")
        self.tree_lobe_3 = ttk.Treeview(f_lobe_3, columns=cols_lobe_3, show="headings", height=4)
        for c in cols_lobe_3:
            self.tree_lobe_3.heading(c, text=c)
            self.tree_lobe_3.column(c, anchor=tk.CENTER, width=115)
        self.tree_lobe_3.pack(fill=tk.BOTH, expand=True, padx=3, pady=2)

        # ---------------- 7.3: TRỤ LỘ BỆ & CỌC (XBC-lo coc) ----------------
        self.subtab_lococ = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_lococ, text=" 7.3 Trụ Lộ Bệ & Cọc (XBC-lo coc) ")

        f_fml_73 = ttk.LabelFrame(self.subtab_lococ, text="Công Thức Phân Tích Trụ Có Bệ & Nhóm Cọc Lộ Dòng (HEC-18 Sec 7.5.5)")
        f_fml_73.pack(fill=tk.X, padx=6, pady=2)
        txt_73 = (
            "• Tổng xói cục bộ:  ys = yspier + yspc + yspg\n"
            "  (*) QUY TẮC BỘC LỘ CỌC CHUẨN HEC-18 (Mục 7.5.4):\n"
            "      - ho tính so với ĐÁY ĐÃ HẠ: ho = (z_đáy_bệ - CĐTN) + y_deg + y_sc\n"
            "      - h1 = ho + T <= 0: xói như trụ đơn | h3 = ho + 0.5*yspier + 0.5*yspc <= 0: yspg = 0 | h3 > 0: có xói cọc"
        )
        tk.Label(f_fml_73, text=txt_73, justify=tk.LEFT, font=("Consolas", 8), fg="#0D47A1", bg="#F4F6F9").pack(fill=tk.X, padx=4, pady=2)

        f_lc_4 = ttk.LabelFrame(self.subtab_lococ, text="Bảng Tổng Hợp Xói Cục Bộ Trụ Lộ Bệ & Cọc (Khống chế ho <= 0 -> yspg = 0)")
        f_lc_4.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        cols_lc_4 = ("STT", "Tên Trụ", "CĐTN (m)", "CĐ đáy bệ (m)", "ho (m)", "yspier (m)", "yspc (m)", "yspg (m)", "Tổng xói ys (m)", "Cao độ sau xói (m)", "Ghi chú phân loại")
        self.tree_lc_4 = ttk.Treeview(f_lc_4, columns=cols_lc_4, show="headings", height=10)
        for c in cols_lc_4:
            self.tree_lc_4.heading(c, text=c)
            self.tree_lc_4.column(c, anchor=tk.CENTER, width=105)
        self.tree_lc_4.pack(fill=tk.BOTH, expand=True, padx=3, pady=2)

        # ---------------- 7.4: XÓI CỤC BỘ MỐ CẦU (Froehlich) ----------------
        self.subtab_abutment = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_abutment, text=" 7.4 Xói Cục Bộ Mố (Froehlich / HIRE) ")

        f_fml_74 = ttk.LabelFrame(self.subtab_abutment, text="Công Thức Xói Cục Bộ Mố Cầu Theo Froehlich (HEC-18 Chapter 8)")
        f_fml_74.pack(fill=tk.X, padx=6, pady=3)
        txt_74 = (
            "• Phương trình Froehlich:  ys / ya = 2.27 * K1 * K2 * (L' / ya)^0.43 * Fr^0.61 + 1\n"
            "  Trong đó: ya: Độ sâu nước trung bình bãi tràn (m) | L': Chiều dài mố/nền đắp cản dòng (m)\n"
            "  Fr = Ve / (g * ya)^0.5  với Ve = Qe / Ae | K1: Hình dạng mố (0.55 taluy, 0.82 tường cánh, 1.0 đứng) | K2 = (θ/90)^0.13 (θ=90°+skew, thiên về an toàn)\n"
            "  L'/ya > 25: dùng HIRE  ys = 4*ya*Fr^0.33*(K1/0.55)*K2 | L' nhập ở cột 'Dài L' của dòng mố"
        )
        tk.Label(f_fml_74, text=txt_74, justify=tk.LEFT, font=("Consolas", 9), fg="#0D47A1", bg="#F4F6F9").pack(fill=tk.X, padx=4, pady=3)

        cols_abut = ("STT", "Tên Mố", "CĐTN (m)", "Độ sâu ya (m)", "Qe chặn (m3/s)", "Ae chặn (m2)", "Ve (m/s)", "Fr", "Chiều dài L' (m)", "Hình dạng", "K1", "θ (°)", "K2", "ys_abut (m)", "Cao độ sau xói (m)")
        self.tree_abutment = ttk.Treeview(self.subtab_abutment, columns=cols_abut, show="headings", height=12)
        for c in cols_abut:
            self.tree_abutment.heading(c, text=c)
            self.tree_abutment.column(c, anchor=tk.CENTER, width=88)

        s_abut_x = ttk.Scrollbar(self.subtab_abutment, orient=tk.HORIZONTAL, command=self.tree_abutment.xview)
        self.tree_abutment.configure(xscrollcommand=s_abut_x.set)
        self.tree_abutment.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)
        s_abut_x.pack(side=tk.BOTTOM, fill=tk.X, padx=4)

    # =========================================================================
    # TAB 8: TỔNG HỢP & BÁO CÁO SCOUR PRISM
    # =========================================================================
    def _init_tab8(self):
        f_table = ttk.LabelFrame(self.tab8, text="Bảng Tổng Hợp Chiều Sâu Xói & Cao Độ Đáy Xói Thiết Kế Móng")
        f_table.pack(fill=tk.X, padx=8, pady=4)

        cols = (
            "Mố/Trụ", "Vị trí X (m)", "CĐTN (m)", "CĐ đáy bệ", "ho (m)", "Hạ thấp dài hạn y_deg (m)",
            "Xói co hẹp y_sc (m)", "Xói cục bộ ys (m)", "Tổng xói Y_total (m)", "Cao độ đáy sau xói (m)"
        )
        self.tree_summary = ttk.Treeview(f_table, columns=cols, show="headings", height=5)
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

    def action_export_report(self):
        if not self.scour_results:
            messagebox.showwarning("Cảnh báo", "Vui lòng tính toán trước khi xuất báo cáo!")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
            title="Lưu báo cáo tính toán xói cầu"
        )
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
            "BẢNG TỔNG HỢP CHIỀU SÂU XÓI TẠI CÁC MỐ VÀ TRỤ CẦU:",
            f"{'Mố/Trụ':<10} {'X (m)':<10} {'CĐTN(m)':<10} {'y_deg(m)':<10} {'y_sc(m)':<10} {'ys(m)':<10} {'Y_tot(m)':<10} {'CĐ đáy xói(m)':<14}",
            "-------------------------------------------------------------------------------------------------------"
        ]
        for r in self.scour_results:
            lines.append(
                f"{r['name']:<10} {r['x']:<10.1f} {r['cdtn']:<10.2f} {r['y_deg']:<10.2f} "
                f"{r['ysc']:<10.2f} {r['ys_local']:<10.2f} {r['y_tot']:<10.2f} {r['z_scour']:<14.2f}"
            )
        lines.append("=======================================================================================================")
        if self.calc_warnings:
            lines.append("CẢNH BÁO / LƯU Ý KHI TÍNH TOÁN:")
            for w in self.calc_warnings:
                lines.append(f"  - {w}")
            lines.append("=======================================================================================================")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Thành công", f"Đã xuất báo cáo kỹ thuật tại:\n{file_path}")

    def _load_sample_data(self):
        self.project["cross_section"] = [
            [1, "M1 (Bờ trái)", 1.51, 0.0, "Mố cầu", 0.0, 0.0, 1.0],
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
            [19, "M2 (Bờ phải)", 1.51, 6.71, "Mố cầu", 0.0, 0.0, 1.0]
        ]
        self.sync_piers_detail()
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

    def run_full_system(self):
        cs = self.project["cross_section"]
        if not cs:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập dữ liệu mặt cắt sông!")
            return

        try:
            warnings = []
            for d in self.project.get("piers_detail", []):
                z_val = d.get("z_day_be", d.get("z_be", d["cdtn"] - 1.40))
                d["z_be"] = z_val
                d["z_day_be"] = z_val
                d["ho"] = round(z_val - d["cdtn"], 3)

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
            if d50_m <= 0 or s1 <= 0 or qtk <= 0:
                messagebox.showerror("Lỗi dữ liệu", "Qtk, S1 và D50 phải lớn hơn 0!")
                return

            k3_name = self.cb_k3.get()
            k3_val, _ = HEC18Tables.PIER_K3.get(k3_name, HEC18Tables.PIER_K3[HEC18Tables.DEFAULT_K3])
            k1_name = self.cb_k1.get()
            k1_shape, _ = HEC18Tables.PIER_K1.get(k1_name, HEC18Tables.PIER_K1[HEC18Tables.DEFAULT_K1])
            round_nose = k1_name in HEC18Tables.ROUND_NOSE
            k1_abut, _ = HEC18Tables.ABUT_K1.get(self.cb_ab.get(), HEC18Tables.ABUT_K1[HEC18Tables.DEFAULT_ABUT])

            if d50_mm < 0.2:
                warnings.append(f"D50 = {d50_mm:.3f} mm < 0.2 mm: các công thức Vc, Laursen, CSU của HEC-18 chỉ áp dụng "
                                f"cho đất rời (cát, sỏi). Với bùn/sét/đất dính phải dùng phương pháp riêng cho đất dính.")
            w_ref = HEC18Calculations.fall_velocity_rubey(d50_m)
            if omega > 0 and (omega > 3.0 * w_ref or omega < w_ref / 3.0):
                warnings.append(f"Vận tốc lắng chìm w nhập = {omega:.4f} m/s lệch nhiều so với w tính theo D50 "
                                f"(Rubey ≈ {w_ref:.4f} m/s). Kiểm tra lại D50 hoặc w vì w quyết định hệ số K1 của Laursen.")

            rad_sk = math.radians(skew)
            cos_sk = math.cos(rad_sk)
            sin_sk = math.sin(rad_sk)
            theta_attack = abs(skew)

            self.vh_data.clear()
            n_pts = len(cs)
            depth = [htk - float(r[2]) for r in cs]                    # độ sâu đại số (âm = khô)
            h_vals = [max(0.0, d) for d in depth]
            dl_vals = [max(0.0, float(r[3]) * cos_sk) for r in cs]

            if max(h_vals) <= 0.0:
                messagebox.showerror("Lỗi dữ liệu", "Độ sâu nước ngập tại toàn bộ các điểm đều bằng 0 m. Hãy kiểm tra lại Htk hoặc bấm Đảo Cột!")
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
            # Vận tốc CỤC BỘ tại điểm: q = alpha*h^(5/3) -> V = alpha*h^(2/3)  (HEC-18 cần V, y ngay thượng lưu trụ)
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

            # ---------------- Tab 4: Choán dòng ----------------
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
            if w1_up_in <= 0:
                warnings.append("Chưa nhập bề rộng lòng chủ thượng lưu W1: đang lấy W1 = bề rộng ướt của mặt cắt cầu, "
                                "nên xói co hẹp chỉ phản ánh chiều rộng trụ. Nếu sông thượng lưu rộng hơn khẩu độ cầu, "
                                "hãy nhập W1 thực (HEC-18: W1 = bề rộng đáy lòng chủ thượng lưu).")

            summary_vcau_txt = (
                f"- TỔNG BỀ RỘNG ƯỚT HOẠT ĐỘNG TẠI MẶT CẮT CẦU W1: {W1:.2f} m | DIỆN TÍCH ƯỚT TỰ NHIÊN: {sum_w:.2f} m2\n"
                f"- TỔNG BỀ RỘNG TRỤ CẢN DÒNG sum(b)        : {sum_b_choan:.2f} m | TỔNG DIỆN TÍCH CHOÁN: {sum_w_choan:.2f} m2\n"
                f"- BỀ RỘNG THOÁT LŨ SAU THU HẸP W2          : {W2:.2f} m (= W1 - sum(b))\n"
                f"- BỀ RỘNG LÒNG CHỦ THƯỢNG LƯU DÙNG CHO LAURSEN W1_up: {W1_up:.2f} m\n"
                f"- HỆ SỐ PHÂN BỐ LƯU TỐC alpha_v           : {alpha_v:.6f} | LƯU TỐC BÌNH QUÂN V_bq = {V_mean:.2f} m/s"
            )
            self.txt_vcau_summary.delete("1.0", tk.END)
            self.txt_vcau_summary.insert(tk.END, summary_vcau_txt)

            # ---------------- Tab 5: Nước dềnh (giữ nguyên công thức bảng tính gốc, ngoài phạm vi HEC-18) ----------------
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
            ratio_q_qcau = qtk / Qcau0

            self.tree_denh.insert("", tk.END, values=(
                "1.0", f"{v0:.2f}", f"{Lngap:.2f}", f"{Fr:.5f}", f"{s1:.5e}",
                f"{Fr_i0:.2f}", f"{Qcau0:.2f}", f"{Vcau0:.2f}", f"{ratio_q_qcau:.2f}",
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

            # ---------------- Tab 7: Xói cục bộ ----------------
            self.scour_results.clear()
            self.tree_summary.delete(*self.tree_summary.get_children())
            self.tree_single_pier.delete(*self.tree_single_pier.get_children())
            self.tree_lobe_1.delete(*self.tree_lobe_1.get_children())
            self.tree_lobe_2.delete(*self.tree_lobe_2.get_children())
            self.tree_lobe_3.delete(*self.tree_lobe_3.get_children())
            self.tree_lc_4.delete(*self.tree_lc_4.get_children())
            self.tree_abutment.delete(*self.tree_abutment.get_children())

            gen_lower = y_deg + ysc            # đáy hạ chung (dài hạn + co hẹp) trước khi tính xói cục bộ
            plot_x = []
            plot_scour_z = []
            stt_p = 1
            stt_ab = 1
            k1_short = k1_name.split(" (")[0].lower()

            for idx_p, p in enumerate(self.vh_data):
                if not p["name"]:
                    continue

                p_name = p["name"]
                px = p["L_cum"]
                cdtn = p["z"]
                y1 = p["hi"]
                a = p["a"]
                L = p["L"]

                if is_abut_name(p_name):
                    # Mố: dùng đoạn mặt cắt kề mố (mố đầu tiên chưa có đoạn "kết thúc tại điểm" nên lấy đoạn kế tiếp)
                    j = idx_p if idx_p > 0 else min(1, n_pts - 1)
                    Qe, Ae = Qi_vals[j], w_vals[j]
                    ya = (Ae / wet_w[j]) if wet_w[j] > 0 else y1
                    ve = (Qe / Ae) if Ae > 0 else 0.0
                    l_prime = L
                    if l_prime <= 0:
                        l_prime = 12.0
                        warnings.append(f"Mố {p_name}: chưa nhập chiều dài mố/nền đắp cản dòng L' (cột 'Dài L'). "
                                        f"Tạm lấy L' = 12 m. Kết quả xói mố phụ thuộc mạnh vào L'.")
                    ab = HEC18Calculations.abutment_scour(ya, ve, l_prime, k1_abut, skew)
                    ys_abut = ab["ys"]
                    if ab["method"] == "HIRE":
                        warnings.append(f"Mố {p_name}: L'/ya = {l_prime/max(ya,1e-6):.1f} > 25 -> dùng HIRE thay cho Froehlich (HEC-18).")

                    cd_sau_xoi_ab = cdtn - (y_deg + ysc + ys_abut)
                    self.tree_abutment.insert("", tk.END, values=(
                        stt_ab, p_name, f"{cdtn:.2f}", f"{ya:.2f}", f"{Qe:.2f}", f"{Ae:.2f}",
                        f"{ve:.2f}", f"{ab['fr']:.3f}", f"{l_prime:.1f}", f"{self.cb_ab.get().split(' (')[0]} [{ab['method']}]",
                        f"{k1_abut:.2f}", f"{ab['theta']:.1f}", f"{ab['k2']:.3f}",
                        f"{ys_abut:.2f}", f"{cd_sau_xoi_ab:.2f}"
                    ))
                    stt_ab += 1
                    ys_final_chosen = ys_abut
                    z_be_disp, ho_disp = "-", "-"
                    v1 = ve
                    y1 = ya
                else:
                    v1 = p["Vloc"]
                    k1_eff = HEC18Calculations.effective_k1(k1_shape, theta_attack)
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
                    aproj = max(ap, n_cot * ap)                    # tổng bề rộng hình chiếu cọc không chồng lấn
                    ho = ho0 + gen_lower                           # cao bệ so với đáy ĐÃ HẠ (dài hạn + co hẹp)

                    z_be_disp = f"{z_be:.2f}"
                    ho_disp = f"{ho0:.2f}"

                    # 7.1 trụ đơn
                    if y1 > 0.05 and v1 > 0:
                        vc_tru = HEC18Calculations.critical_velocity_vc(y1, d50_m)
                        ratio_v_vc = v1 / max(0.01, vc_tru)
                        fr1 = v1 / math.sqrt(G * y1)
                        kw_single = HEC18Calculations.kw_wide_pier(y1, a, fr1, ratio_v_vc, d50_m)
                        ys_pier_single, fr1 = HEC18Calculations.pier_scour_csu(y1, v1, a, k1_eff, k2, k3_val, kw_single, capped)
                    else:
                        vc_tru, ratio_v_vc, kw_single, ys_pier_single, fr1 = 0.0, 0.0, 1.0, 0.0, 0.0

                    note_single = "θ>5°: K1=1.0" if theta_attack > 5.0 else ("giới hạn 2.4a/3.0a" if capped else "")
                    cd_single = cdtn - (y_deg + ysc + ys_pier_single)
                    self.tree_single_pier.insert("", tk.END, values=(
                        f"{stt_p}. {p_name}", f"{cdtn:.2f}", f"{y1:.2f}", f"{v1:.2f}", f"{fr1:.3f}",
                        f"{a:.2f}", k1_short, f"{k1_eff:.2f}", f"{skew:.1f}", f"{L:.2f}",
                        f"{k2:.3f}", k3_name.split(" (")[0], f"{k3_val:.2f}", f"{d50_mm:.3f}", f"{vc_tru:.2f}",
                        f"{ratio_v_vc:.2f}", f"{kw_single:.3f}", f"{ys_pier_single:.2f}", f"{cd_single:.2f}", note_single
                    ))

                    # Thân trụ + bệ + cọc (HEC-18 trụ phức hợp)
                    cp = HEC18Calculations.complex_pier(y1, v1, a, k1_eff, k2, k3_val, kw_single, capped,
                                                        ho, T_be, f_dist, apc, ap, S_coc, m_hang, n_cot, aproj)

                    # 7.2 (phương pháp bệ lộ của bảng tính gốc: Vf theo phân bố log, ks = 2*D84)
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
                    cd_lobe = cdtn - (y_deg + ysc + ys_total_lobe)
                    self.tree_lobe_3.insert("", tk.END, values=(
                        stt_p, p_name, f"{cdtn:.2f}", f"{z_be:.2f}", f"{ho0:.2f}",
                        f"{yspier_lobe:.2f}", f"{ysfooting_lb:.2f}", f"{ys_total_lobe:.2f}", f"{cd_lobe:.2f}"
                    ))

                    # 7.3 (kết quả CHÍNH: thân + bệ + cọc theo HEC-18 5th)
                    ys_final_chosen = cp["ys_total"]
                    cd_lococ = cdtn - (y_deg + ysc + ys_final_chosen)
                    self.tree_lc_4.insert("", tk.END, values=(
                        stt_p, p_name, f"{cdtn:.2f}", f"{z_be:.2f}", f"{ho0:.2f}",
                        f"{cp['ys_pier']:.2f}", f"{cp['ys_pc']:.2f}", f"{cp['ys_pg']:.2f}",
                        f"{ys_final_chosen:.2f}", f"{cd_lococ:.2f}", cp["note"]
                    ))
                    stt_p += 1

                y_tot = y_deg + ysc + ys_final_chosen
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

            # ---------------- Tab 8: Vẽ biểu đồ ----------------
            all_x = [pt["L_cum"] for pt in self.vh_data]
            all_z = [pt["z"] for pt in self.vh_data]
            self._render_scour_prism_plot(all_x, all_z, htk, y_deg, ysc, plot_x, plot_scour_z)

            self.calc_warnings = list(dict.fromkeys(warnings))
            self.nb.select(self.tab8)
            if self.calc_warnings:
                messagebox.showwarning(
                    "Hoàn thành - có cảnh báo",
                    f"Đã tính xong xói cầu {self.project['bridge_name']}.\n\nCẢNH BÁO CẦN XEM LẠI:\n- " + "\n- ".join(self.calc_warnings)
                )
            else:
                messagebox.showinfo("Thành công", f"Đã hoàn thành toàn bộ hệ thống tính toán xói cầu cho {self.project['bridge_name']}!")

        except Exception as e:
            messagebox.showerror("Lỗi thực thi", f"Quá trình tính toán gặp sự cố: {e}")


# =============================================================================
# KHỞI CHẠY CHƯƠNG TRÌNH
# =============================================================================
if __name__ == "__main__":
    app = MainScourApplication()
    app.mainloop()