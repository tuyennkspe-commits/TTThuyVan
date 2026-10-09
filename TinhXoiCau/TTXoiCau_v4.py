# -*- coding: utf-8 -*-
"""Bridge scour calculations for granular beds and free-surface flow (HEC-18, 2012).
Report exports fill the supplied templates; hydraulic distribution uses a 1D approximation.
"""

import math
import sys
import copy
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import pandas as pd

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches

UI_FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

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
        if y1 <= 0 or d50_m <= 0:
            raise ValueError('Chiều sâu và D50 phải lớn hơn 0 để tính Vc (HEC-18, 6.1).')
        return 6.19 * y1 ** (1.0 / 6.0) * d50_m ** (1.0 / 3.0)

    @staticmethod
    def wet_segment(d1, d2, dl):
        if dl <= 0:
            return 0.0, 0.0, 0.0
        if d1 > 0 and d2 > 0:
            if abs(d2 - d1) < 1e-8 * max(d1, d2):
                ai = dl * ((d1 + d2) / 2) ** (5.0 / 3.0)
            else:
                ai = 3.0 / 8.0 * dl * (d2 ** (8.0 / 3.0) - d1 ** (8.0 / 3.0)) / (d2 - d1)
            return dl, 0.5 * (d1 + d2) * dl, ai
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
        if y1 <= 0 or v1 <= 0 or a <= 0:
            return 0.0, 0.0
        fr1 = v1 / math.sqrt(G * y1)
        ys = 2.0 * k1 * k2 * k3 * kw * (a ** 0.65) * (y1 ** 0.35) * (fr1 ** 0.43)
        if capped:
            ys = min(ys, (2.4 if fr1 <= 0.8 else 3.0) * a)
        return ys, fr1

    @staticmethod
    def kh_pier_stem(h1, a, f):
        if a <= 0 or h1 / a <= -1.0:
            return 1.0
        h1_a = h1 / a
        f_a = max(0.0, f / a)
        kh = (0.4075 - 0.0669 * f_a) - (0.4271 - 0.0778 * f_a) * h1_a \
             + (0.1615 - 0.0455 * f_a) * (h1_a ** 2) - (0.0269 - 0.012 * f_a) * (h1_a ** 3)
        return max(0.0, min(1.0, kh))

    @staticmethod
    def equivalent_width_pilecap(h2, y2, T, apc):
        if y2 <= 0 or T <= 0 or apc <= 0:
            return 0.0
        if h2 < 0:
            raise ValueError('Hình 7.7 không áp dụng cho đáy bệ dưới đáy sông; dùng Case 2.')
        y2_limit = min(y2, 3.5 * apc)
        ratio_term = T / y2_limit
        h_ratio = max(0.0, min(1.0, h2 / y2_limit))
        val_exp = math.exp(-2.705 + 0.51 * math.log(ratio_term) - 2.783 * h_ratio ** 3 + 1.751 / math.exp(h_ratio))
        return min(apc, val_exp * apc)

    @staticmethod
    def pile_group_factors(ap, S, m, n, aproj, h3, y3, skewed=False):
        if h3 <= 0 or y3 <= 0:
            return 1.0, 1.0, aproj, 0.0
        s_ap = max(1.0, S / ap) if ap > 0 else 3.0
        aproj_ap = max(1.0, aproj / ap) if ap > 0 else 5.0
        ksp = 1.0 - (4.0 / 3.0) * (1.0 - 1.0 / aproj_ap) * (1.0 - (s_ap ** (-0.6)))
        ksp = max(0.1, min(1.0, ksp))
        m = min(6, m)  # HEC-18, 7.5.5 / Figure 7.12.
        km = 1.0 if skewed else 0.9 + 0.10 * m - 0.0714 * (m - 1.0) * (2.4 - 1.1 * s_ap + 0.1 * (s_ap ** 2))
        km = max(1.0, km)
        apg_star = ksp * km * aproj
        h3_y3 = max(0.0, min(1.0, h3 / min(y3, 3.5 * apg_star)))
        khpg_term = 3.08 * h3_y3 - 5.23 * (h3_y3 ** 2) + 5.25 * (h3_y3 ** 3) - 2.10 * (h3_y3 ** 4)
        khpg = (max(0.0, khpg_term)) ** (1.0 / 0.65) if khpg_term > 0 else 0.0
        return ksp, km, apg_star, min(1.0, khpg)

    @staticmethod
    def projected_pile_width(ap, spacing, m, n, theta_deg=0.0):
        """Non-overlapping projection of the two leading rows and one column (Fig. 7.10)."""
        if ap <= 0 or spacing < ap or m < 1 or n < 1 or m != int(m) or n != int(n):
            raise ValueError('Nhóm cọc cần ap > 0, S ≥ ap và số hàng/cột nguyên dương.')
        theta = math.radians(abs(theta_deg) % 180)
        points = [(row * spacing, col * spacing) for row in range(int(m)) for col in range(int(n))
                  if row < 2 or col == (0 if math.cos(theta) >= 0 else int(n)-1)]
        intervals = sorted((x * math.sin(theta) + y * math.cos(theta)-ap/2,
                            x * math.sin(theta) + y * math.cos(theta)+ap/2) for x,y in points)
        total = 0.0
        left, right = intervals[0]
        for a, b in intervals[1:]:
            if a <= right: right = max(right, b)
            else: total += right-left; left,right=a,b
        return total + right-left

    @staticmethod
    def grain_roughness(d84_m, material='sand'):
        if d84_m <= 0:
            raise ValueError('Nhập D84 đo từ cấp phối để tính vận tốc trên bệ (HEC-18, 7.25).')
        return (3.5 if material == 'gravel' else 1.0) * d84_m

    @staticmethod
    def foundation_exposure(z_bed, z_cap_bottom, thickness, z_water, has_cap=True, has_piles=True):
        """Geometric exposure at one bed stage; pile flow starts below the cap soffit."""
        if not all(math.isfinite(v) for v in (z_bed, z_cap_bottom, thickness, z_water)):
            raise ValueError('Cao độ móng và đáy sông phải hữu hạn.')
        if has_cap and thickness <= 0:
            raise ValueError('Chiều dày bệ phải dương.')
        z_top = z_cap_bottom + thickness
        cap_wet = max(0.0, min(z_top, z_water)-max(z_cap_bottom, z_bed)) if has_cap else 0.0
        pile_wet = max(0.0, min(z_cap_bottom, z_water)-z_bed) if has_cap and has_piles else 0.0
        if z_water <= z_bed: state = 'Không ngập'
        elif not has_cap: state = 'Trụ không có bệ'
        elif pile_wet > 1e-9: state = 'Lộ bệ & cọc' if cap_wet > 1e-9 else 'Lộ cọc (bệ ngoài nước)'
        elif cap_wet > 1e-9: state = 'Lộ bệ'
        elif z_top <= z_bed+1e-9: state = 'Bệ và cọc còn chôn'
        else: state = 'Bệ ngoài nước'
        return dict(state=state, z_bed=z_bed, z_cap_top=z_top, cap_wet=cap_wet, pile_wet=pile_wet)

    @staticmethod
    def blocked_flow_from_segments(depths, widths, alpha, x_start, x_end):
        """Integrate only the selected obstructed interval of the existing 1D PPLL."""
        if len(depths)!=len(widths) or len(depths)<2 or not math.isfinite(alpha) or alpha<=0:
            raise ValueError('Chưa có bảng phân phối lưu lượng hợp lệ.')
        extent=sum(widths[1:])
        if not all(math.isfinite(v) for v in (x_start,x_end)) or not 0 <= x_start < x_end <= extent+1e-8:
            raise ValueError(f'Đoạn chắn phải có 0 ≤ X đầu < X cuối ≤ {extent:.2f} m.')
        pos=area=discharge=wet_width=0.0
        for i in range(1,len(depths)):
            length=widths[i]
            left,right=max(pos,x_start),min(pos+length,x_end)
            if length>0 and right>left:
                slope=(depths[i]-depths[i-1])/length
                d1=depths[i-1]+slope*(left-pos);d2=depths[i-1]+slope*(right-pos)
                w,a,integral=HEC18Calculations.wet_segment(d1,d2,right-left)
                wet_width+=w;area+=a;discharge+=alpha*integral
            pos+=length
        if area<=0 or wet_width<=0:
            raise ValueError('Đoạn chọn không có dòng chảy ngập; không suy ra thủy lực mố từ đoạn này.')
        return dict(Qe=discharge,Ae=area,L_prime=wet_width,ya=area/wet_width,Ve=discharge/area)

    @staticmethod
    def complex_pier(y1, v1, a, k1, k2, k3, kw, capped, ho, T, f, apc, ap, S, m, n, aproj,
                     pile_exposed=True, d50_m=0.00032, d84_m=0.0073, Lpc=None,
                     theta_deg=0.0, bed_material='sand', staggered=False, cap_k1=1.1, has_cap=True, initial_only=False):
        """HEC-18 §§7.5.3–7.5.5; initial_only freezes Case selection at the initial bed."""
        r = dict(fr1=0.0, ys_full=0.0, h1=ho+T, kh=1.0, ys_pier=0.0, y2=y1, h2=ho,
                 v2=v1, fr2=0.0, t_eff=0.0, apc_star=0.0, ys_pc=0.0, h3=ho, y3=y1,
                 v3=0.0, fr3=0.0, ksp=1.0, km=1.0, apg=0.0, khpg=0.0, ys_pg=0.0,
                 ys_total=0.0, case='DRY', note='Không có dòng chảy', cap_case=0,
                 kw_pc=1.0, k2_pc=1.0, k1_pc=k1, yf=0.0, ks=0.0, vf=0.0, frf=0.0,
                 y3_effective=y1, aproj=aproj)
        if y1 <= 0 or v1 <= 0: return r
        ys_full, fr1 = HEC18Calculations.pier_scour_csu(y1,v1,a,k1,k2,k3,kw,False)
        h1=ho+T
        r.update(fr1=fr1,ys_full=ys_full)
        ys_single=min(ys_full,(2.4 if fr1<=0.8 else 3)*a) if capped else ys_full
        if not has_cap or (h1<=1e-9 if initial_only else h1+ys_single/2<=1e-9):
            r.update(ys_pier=ys_single,ys_total=ys_single,case='BURIED' if has_cap else 'SINGLE',
                     y2=y1+ys_single/2,h2=ho+ys_single/2,
                     note='Chỉ xói thân trụ; bệ chưa tiếp xúc dòng chảy ở đáy điều chỉnh' if has_cap else 'Trụ không có bệ')
            return r
        if min(a, apc, T) <= 0: raise ValueError('Kích thước thân trụ và bệ phải dương.')
        # Only the submerged stem above the cap is relevant.
        kh=HEC18Calculations.kh_pier_stem(h1,a,f) if h1 < y1 else 0.0
        ys_pier=kh*ys_full
        if capped: ys_pier=min(ys_pier,(2.4 if fr1<=0.8 else 3)*a)
        y2=y1+ys_pier/2;h2=ho+ys_pier/2;v2=v1*y1/y2;fr2=v2/math.sqrt(G*y2)
        k2_pc=HEC18Calculations.pier_k2(theta_deg,Lpc if Lpc is not None else apc,apc)
        k1_pc=HEC18Calculations.effective_k1(cap_k1,theta_deg)
        r.update(kh=kh,ys_pier=ys_pier,y2=y2,h2=h2,v2=v2,fr2=fr2,k2_pc=k2_pc,k1_pc=k1_pc)
        if (ho<=1e-9 if initial_only else h2<=0):
            # Case 2, Eq. 7.25/7.26: flow below the footing top, no pile-group term.
            yf=min(y2,max(0.0,h1+ys_pier/2))
            ks=HEC18Calculations.grain_roughness(d84_m,bed_material) if yf > 1e-9 else 0.0
            vf=v2*math.log1p(10.93*yf/ks)/math.log1p(10.93*y2/ks) if yf > 0 else 0.0
            frf=vf/math.sqrt(G*yf) if yf>0 else 0.0
            vc2=HEC18Calculations.critical_velocity_vc(y2,d50_m)
            kw_pc=HEC18Calculations.kw_wide_pier(y2,apc,fr2,v2/vc2,d50_m)
            ys_pc,_=HEC18Calculations.pier_scour_csu(yf,vf,apc,k1_pc,k2_pc,k3,kw_pc,False)
            r.update(ys_pc=ys_pc,ys_total=ys_pier+ys_pc,cap_case=2,case='CASE2',
                     yf=yf,ks=ks,vf=vf,frf=frf,kw_pc=kw_pc,apc_star=apc,
                     t_eff=yf,note='HEC-18 Case 2: bệ trên/dưới đáy; xói nhóm cọc đã nằm trong thành phần bệ')
            return r
        # Case 1, Eq. 7.24: use cap geometry for K2 and equivalent width for Kw.
        t_eff=min(T,max(0.0,y2-h2))
        apc_star=HEC18Calculations.equivalent_width_pilecap(h2,y2,t_eff,apc)
        vc2=HEC18Calculations.critical_velocity_vc(y2,d50_m)
        kw_pc=HEC18Calculations.kw_wide_pier(y2,apc_star,fr2,v2/vc2,d50_m)
        ys_pc,_=HEC18Calculations.pier_scour_csu(y2,v2,apc_star,k1_pc,k2_pc,k3,kw_pc,False)
        y3=y1+(ys_pier+ys_pc)/2;h3=ho+(ys_pier+ys_pc)/2;v3=v1*y1/y3
        r.update(ys_pc=ys_pc,ys_total=ys_pier+ys_pc,cap_case=1,case='CASE1',
                 apc_star=apc_star,t_eff=t_eff,kw_pc=kw_pc,y3=y3,y3_effective=y3,h3=h3,v3=v3,
                 note='HEC-18 Case 1: đáy bệ lộ trong dòng chảy')
        if not pile_exposed or h3<=0 or ap<=0 or aproj<=0: return r
        ksp,km,apg,khpg=HEC18Calculations.pile_group_factors(ap,S,m,n,aproj,h3,y3,
                                                          skewed=staggered or abs(theta_deg)>1e-9)
        y3_eff=min(y3,3.5*apg);fr3=v3/math.sqrt(G*y3_eff)
        ys_pg=khpg*2*k3*apg**.65*y3_eff**.35*fr3**.43  # K1=1, K2 omitted (7.31).
        r.update(ksp=ksp,km=km,apg=apg,khpg=khpg,ys_pg=ys_pg,fr3=fr3,
                 y3_effective=y3_eff,ys_total=ys_pier+ys_pc+ys_pg)
        return r

    @staticmethod
    def contraction_scour(q, y1, v1, w1, w2, d50_m, s1, omega, q1=None, y0=None, armored=False):
        q1 = q if q1 is None else q1
        y0 = y1 if y0 is None else y0
        if min(q1, y1, w1, w2, d50_m, omega) <= 0 or q < 0 or y0 < 0 or s1 < 0:
            raise ValueError('Dữ liệu xói thu hẹp không hợp lệ: kiểm tra Q1, Q2, y1, y0, W1, W2, D50 và ω.')
        vc = HEC18Calculations.critical_velocity_vc(y1, d50_m)
        v_star = math.sqrt(max(0.0, G * y1 * s1))
        ratio_vw = v_star / omega if omega > 0 else 1.0
        k1_l, k1_desc = HEC18Tables.get_laursen_k1(ratio_vw)
        d50_cw = max(d50_m, 0.0002)  # Lower limit recommended in 6.4 and 6.7.
        dm = 1.25 * d50_cw
        y2_cw = ((0.025 * q ** 2) / ((dm ** (2.0 / 3.0)) * (w2 ** 2))) ** (3.0 / 7.0)
        y2_lb = y1 * (q / q1) ** (6.0 / 7.0) * (w1 / w2) ** k1_l
        note = 'D50 nước trong lấy tối thiểu 0,2 mm (HEC-18, 6.4).' if d50_m < 0.0002 else ''
        if v1 > vc:
            mode = "Xói nước đục"
            y2 = y2_lb
            if armored and y2_cw < y2_lb:
                y2 = y2_cw
                note = "Đáy có khả năng tạo lớp bọc: lấy min(live-bed, clear-water), HEC-18 §6.3 note 8."
        else:
            mode = "Xói nước trong"
            y2 = y2_cw
        return dict(vc=vc, v_star=v_star, ratio_vw=ratio_vw, k1=k1_l, k1_desc=k1_desc, dm=dm,
                    mode=mode, y2=y2, ysc=max(0.0, y2 - y0), note=note, y0=y0, q1=q1,
                    y2_cw=y2_cw, y2_lb=y2_lb, d50_cw=d50_cw)

    @staticmethod
    def optional_number(value):
        """Blank means unknown; accept decimal commas and common thousands separators."""
        if value is None or str(value).strip()=='': return None
        text=str(value).strip().replace(' ','').replace('\u00a0','')
        if ',' in text and '.' in text:
            text=text.replace('.','').replace(',','.') if text.rfind(',')>text.rfind('.') else text.replace(',','')
        elif ',' in text:
            if text.count(',')!=1: raise ValueError('Dùng dấu phẩy thập phân hoặc để trống thông số chưa biết.')
            text=text.replace(',','.')
        number=float(text)
        if not math.isfinite(number): raise ValueError('Thông số phải là số hữu hạn.')
        return number

    @staticmethod
    def resolve_abutment_hydraulics(qe=None, ae=None, ve=None, ya=None, length=None, blocked_width=None):
        """Solve Q=A*V; A=ya*B only with a supplied area width B, independent of L′."""
        values=dict(Qe=qe,Ae=ae,Ve=ve,ya=ya,L_prime=length)
        for key,value in values.items():
            if value is not None and (not math.isfinite(value) or value<0 or (key not in ('Qe','Ve') and value==0)):
                raise ValueError(f'{key} cần dương (Qe, Ve cho phép 0); để trống nếu chưa biết.')
        if blocked_width is not None and (not math.isfinite(blocked_width) or blocked_width<=0):
            raise ValueError('Bề rộng tính Ae phải dương; để trống nếu chưa biết.')
        for _ in range(4):
            q,a,v,d,l=(values[k] for k in ('Qe','Ae','Ve','ya','L_prime'))
            if a is None and d is not None and blocked_width is not None: values['Ae']=d*blocked_width
            elif a is None and q is not None and v is not None and v>0: values['Ae']=q/v
            a=values['Ae']
            if a is not None and a>0:
                if d is None and blocked_width is not None: values['ya']=a/blocked_width
                if q is None and v is not None: values['Qe']=a*v
                if v is None and q is not None: values['Ve']=q/a
        missing=[key for key in ('Ve','ya','L_prime') if values[key] is None]
        if missing:
            raise ValueError('Chưa đủ dữ liệu để suy '+', '.join(missing)+'. Cần ya, L′ và Ve hoặc Qe/Ae; có thể suy Ae/ya nếu biết bề rộng tính Ae.')
        q,a,v,d,l=(values[k] for k in ('Qe','Ae','Ve','ya','L_prime'))
        if (a is not None and a<=0) or d<=0 or l<=0: raise ValueError('Ae, ya, L′ phải dương cho đoạn có dòng chảy ngập.')
        if q is not None and a is not None and not math.isclose(q/a,v,rel_tol=.005,abs_tol=.005):
            raise ValueError('Qe, Ae, Ve không nhất quán: phải có Ve = Qe/Ae. Để trống đại lượng cần suy.')
        if blocked_width is not None and a is not None and not math.isclose(a/blocked_width,d,rel_tol=.005,abs_tol=.005):
            raise ValueError('Ae, ya và bề rộng tính Ae không nhất quán cho cùng đoạn dòng chảy bị chắn.')
        # Canonical values ensure conservation when redundant inputs were rounded.
        if q is not None and a is not None: values['Ve']=q/a
        if blocked_width is not None and a is not None: values['ya']=a/blocked_width
        return values

    @staticmethod
    def abutment_scour(ya, ve, l_prime, k1_abut, theta_deg=90.0):
        if ya <= 0 or l_prime <= 0 or ve <= 0:
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
        self.title("Tính toán xói cục bộ tại Cầu • HEC-18 2012")
        self.geometry(f"{min(1440, self.winfo_screenwidth())}x{min(940, self.winfo_screenheight()-70)}")
        self.minsize(1100, 720)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.configure(bg="#F3F6FA")
        self.option_add("*Font", (UI_FONT, 10))
        self.style.configure(".", font=(UI_FONT, 10), background="#F3F6FA", foreground="#24344B")
        self.style.configure("TFrame", background="#F3F6FA")
        self.style.configure("TLabelframe", padding=10, background="#F3F6FA")
        self.style.configure("TLabelframe.Label", font=(UI_FONT, 10, "bold"), foreground="#12384A")
        self.style.configure("TButton", padding=(10, 7), background="#E5EDF3", borderwidth=0)
        self.style.map("TButton", background=[("active", "#D3E3ED")])
        self.style.configure("Primary.TButton", background="#087F8C", foreground="white", font=(UI_FONT, 10, "bold"))
        self.style.map("Primary.TButton", background=[("active", "#096674")])
        self.style.configure("Treeview", background="white", fieldbackground="white", rowheight=28, borderwidth=0)
        self.style.configure("Treeview.Heading", background="#E6EEF5", font=(UI_FONT, 10, "bold"), padding=(5, 8))
        self.style.map("Treeview", background=[("selected", "#C8E9EB")], foreground=[("selected", "#12384A")])
        self.style.configure("TNotebook.Tab", padding=(10, 9))

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
            "d50": 0.32,
            "omega": 0.022,
            "y_deg": 0.50,
            "n_manning": 0.025,
            "k3_type": HEC18Tables.DEFAULT_K3,
            "k1_type": HEC18Tables.DEFAULT_PIER_K1,
            "d84": 7.3,
            "q1_up": 0.0, "y1_up": 0.0, "y0_bridge": 0.0, "bed_material": "sand", "armored": False,
            "w1_up": 0.0, "a_denh": 0.73,
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
        self.bind("<Control-o>", lambda e: self.action_open_project())
        self.bind("<Control-s>", lambda e: self.action_save_project())
        self.bind("<F5>", lambda e: self.run_full_system())
        for entry in self.t1_entries.values():
            entry.bind("<KeyRelease>", self._invalidate_results)
        for combo in (self.cb_k1, self.cb_k3, self.cb_material):
            combo.bind("<<ComboboxSelected>>", self._invalidate_results)

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
        header = tk.Frame(self, bg="#142C42")
        header.pack(fill=tk.X)
        tk.Label(header, text="TÍNH TOÁN XÓI CỤC BỘ TẠI CẦU", bg="#142C42", fg="white",
                 font=(UI_FONT, 18, "bold")).pack(anchor="w", padx=20, pady=(12, 2))
        self.lbl_title = tk.Label(header, text=f"{self.project['bridge_name']}  •  {self.project['project_name']}",
                                  bg="#142C42", fg="#BBD1E0", font=(UI_FONT, 10))
        self.lbl_title.pack(anchor="w", padx=20, pady=(0, 12))
        toolbar = ttk.Frame(self, padding=(12, 6))
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Mở dự án", command=self.action_open_project).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Lưu dự án", command=self.action_save_project).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Bệ & cọc trụ", command=self.dialog_edit_piers_detail).pack(side=tk.LEFT, padx=(14,3))
        ttk.Button(toolbar, text="Thủy lực mố", command=self.dialog_edit_abutments_detail).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Tính toán  ·  F5", style="Primary.TButton", command=self.run_full_system).pack(side=tk.RIGHT, padx=3)
        self.export_buttons = []
        for label, command in (("Xuất Word", self.action_export_word), ("Xuất Excel", self.action_export_report)):
            button = ttk.Button(toolbar, text=label, command=command, state="disabled")
            button.pack(side=tk.RIGHT, padx=3)
            self.export_buttons.append(button)
        cards = ttk.Frame(self, padding=(15, 3))
        cards.pack(fill=tk.X)
        self.metric_labels = []
        for title in ("MỰC NƯỚC THIẾT KẾ", "LƯU LƯỢNG THIẾT KẾ", "XÓI TỔNG LỚN NHẤT", "MỐ / TRỤ ĐÃ TÍNH"):
            card = tk.Frame(cards, bg="white", padx=14, pady=7)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            tk.Label(card, text=title, bg="white", fg="#60748A", font=(UI_FONT, 8)).pack(anchor="w")
            value = tk.Label(card, text="—", bg="white", fg="#142C42", font=(UI_FONT, 16, "bold"))
            value.pack(anchor="w")
            self.metric_labels.append(value)
        footer = ttk.Frame(self, padding=(16, 5))
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_text = tk.StringVar(value="Nhập dữ liệu và nhấn Tính toán")
        ttk.Label(footer, textvariable=self.status_text).pack(side=tk.LEFT)
        ttk.Button(footer, text="Xem lưu ý", command=lambda: messagebox.showinfo("Điều kiện áp dụng", "\n".join(self.calc_warnings) or "Chưa có kết quả tính toán.")).pack(side=tk.LEFT, padx=10)
        ttk.Label(footer, text="HEC-18 2012  •  Hạt rời  •  Dòng chảy mặt thoáng", foreground="#60748A").pack(side=tk.RIGHT)

    def _invalidate_results(self, event=None):
        self.scour_results.clear()
        self._report_piers.clear()
        self._report_context.clear()
        self.calc_warnings = []
        self._ppll_context = {}
        for name in ('tree_ppll', 'tree_vcau', 'tree_denh', 'tree_xoi_chung', 'tree_summary',
                     'tree_single_pier', 'tree_lobe_1', 'tree_lobe_2', 'tree_lobe_3', 'tree_lc_4', 'tree_abutment', 'tree_exposure'):
            tree = getattr(self, name, None)
            if tree is not None: tree.delete(*tree.get_children())
        if hasattr(self, 'ax_prism'):
            self.ax_prism.clear()
            self.canvas_prism.draw_idle()
        if hasattr(self, 'status_text'):
            self.status_text.set("Dữ liệu chưa tính • Nhấn F5 để cập nhật kết quả")
            for label in self.metric_labels: label.config(text="—")
            for button in self.export_buttons: button.config(state="disabled")

    def _refresh_result_summary(self):
        c = self._report_context
        values = (f"{c['htk']:.2f} m", f"{c['qtk']:,.0f} m³/s",
                  f"{max((r['y_tot'] for r in self.scour_results), default=0):.2f} m", str(len(self.scour_results)))
        for label, value in zip(self.metric_labels, values): label.config(text=value)
        for button in self.export_buttons: button.config(state="normal")
        self.status_text.set(f"Đã tính • {len(self.calc_warnings)} lưu ý điều kiện áp dụng" if self.calc_warnings else "Đã tính • Kết quả sẵn sàng xuất báo cáo")

    def _validate_calculation_inputs(self, hydraulics_only=False):
        vals = {k: float(e.get()) for k, e in self.t1_entries.items()}
        if any(not math.isfinite(v) for v in vals.values()):
            raise ValueError('Các thông số phải là số hữu hạn.')
        for key in ('qtk', 'd50', 'omega', 'n_manning', 'a_denh'):
            if vals[key] <= 0: raise ValueError(f'{key} phải lớn hơn 0.')
        for key in ('s1', 'y_deg', 'd84', 'w1_up', 'q1_up', 'y1_up', 'y0_bridge'):
            if vals[key] < 0: raise ValueError(f'{key} không được âm.')
        if abs(vals['skew']) >= 90:
            raise ValueError('Góc xiên cần nằm trong khoảng (-90°, 90°).')
        self.project['bed_material'] = 'gravel' if self.cb_material.get().startswith('Sỏi') else 'sand'
        self.sync_all_details()
        cs = self.project['cross_section']
        if len(cs) < 2: raise ValueError('Mặt cắt cần ít nhất hai điểm.')
        names = [str(r[1]).strip() for r in cs if str(r[1]).strip()]
        if len(set(names)) != len(names): raise ValueError('Tên mố/trụ không được trùng nhau.')
        if vals['d84'] > 0 and vals['d84'] < vals['d50']:
            raise ValueError('D84 không thể nhỏ hơn D50 trong cùng cấp phối.')
        for row in cs:
            if row[1] and not is_abut_name(row[1]) and (float(row[5]) <= 0 or float(row[6]) <= 0):
                raise ValueError(f'{row[1]}: bề rộng và chiều dài trụ phải dương.')
            if any(not math.isfinite(float(row[i])) for i in (2,3,5,6)) or float(row[3]) < 0:
                raise ValueError('Cao độ, khoảng cách và kích thước mặt cắt không hợp lệ.')
        if hydraulics_only: return
        for d in self.project['piers_detail']:
            keys=['apier','Lpier']
            if d.get('has_cap',True): keys += ['apc','Lpc','T']
            if d.get('has_cap',True) and d.get('has_piles',True): keys += ['ap','S','m','n']
            for key in keys:
                value = float(d[key])
                if not math.isfinite(value) or value <= 0: raise ValueError(f"{d['name']}: {key} phải dương và hữu hạn.")
            if d.get('has_cap',True) and d.get('has_piles',True) and (float(d['S']) < float(d['ap']) or any(float(d[k]) != int(float(d[k])) for k in ('m','n'))):
                raise ValueError(f"{d['name']}: S ≥ ap; m, n phải là số nguyên dương.")
            if not all(math.isfinite(float(d[k])) for k in ('f','z_day_be')) or float(d['f']) < 0:
                raise ValueError(f"{d['name']}: kiểm tra cao độ bệ và khoảng cách f.")
            if d.get('manual_aproj') and (not math.isfinite(float(d['aproj'])) or float(d['aproj']) <= 0):
                raise ValueError(f"{d['name']}: hình chiếu nhóm cọc phải dương.")
        for d in self.project['abutments_detail']:
            if not d.get('hydraulics_confirmed', True):
                raise ValueError(f"{d['name']}: nhập và lưu ya, L′ cùng Ve hoặc Qe/Ae trước khi tính.")
            HEC18Calculations.resolve_abutment_hydraulics(qe=d.get('Qe'),ae=d.get('Ae'),ve=d.get('Ve'),ya=d.get('ya'),length=d.get('L_prime'),blocked_width=d.get('blocked_width'))
            if not math.isfinite(float(d['theta'])) or not 10 <= float(d['theta']) <= 170:
                raise ValueError(f"{d['name']}: góc mố từ 10° đến 170°.")

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

        self.nb.add(self.tab1, text="1. Mặt cắt")
        self.nb.add(self.tab2, text="2. H–Q / H–V")
        self.nb.add(self.tab3, text="3. Lưu lượng")
        self.nb.add(self.tab4, text="4. Choán dòng")
        self.nb.add(self.tab5, text="5. Nước dềnh")
        self.nb.add(self.tab6, text="6. Xói thu hẹp")
        self.nb.add(self.tab7, text="7. Xói cục bộ")
        self.nb.add(self.tab8, text="8. Tổng hợp")

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

        left_host = ttk.Frame(pane, width=470)
        pane.add(left_host, weight=1)
        input_canvas = tk.Canvas(left_host, width=470, background="#F3F6FA", highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_host, orient=tk.VERTICAL, command=input_canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        input_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        input_canvas.configure(yscrollcommand=scrollbar.set)
        f_left = ttk.LabelFrame(input_canvas, text="Thông số thủy lực & lòng dẫn")
        input_canvas.create_window((0,0), window=f_left, anchor="nw")
        f_left.bind("<Configure>", lambda e: input_canvas.configure(scrollregion=input_canvas.bbox("all")))

        inputs = [
            ("Mực nước lũ thiết kế Htk (m):", "htk"),
            ("Lưu lượng lũ thiết kế Qtk (m3/s):", "qtk"),
            ("Góc xiên tim cầu với dòng chảy (°):", "skew"),
            ("Độ dốc thủy lực lòng sông S1 (m/m):", "s1"),
            ("Đường kính hạt trung vị D50 (mm):", "d50"),
            ("Đường kính hạt D84 đo từ cấp phối (mm):", "d84"),
            ("Vận tốc lắng chìm hạt w (m/s):", "omega"),
            ("Hạ thấp lòng dẫn dài hạn y_deg (m):", "y_deg"),
            ("Hệ số nhám Manning nc lòng sông:", "n_manning"),
            ("Bề rộng W1 thượng lưu (m) [0 = mặt cắt]:", "w1_up"),
            ("Q1 lòng chủ thượng lưu (m³/s) [0 = Qtk]:", "q1_up"),
            ("y1 thượng lưu (m) [0 = mặt cắt]:", "y1_up"),
            ("y0 tại cầu (m) [0 = mặt cắt]:", "y0_bridge"),
            ("Hệ số hình thái a (ước tính nước dềnh):", "a_denh"),
        ]

        for r, (txt, k) in enumerate(inputs):
            ttk.Label(f_left, text=txt, font=(UI_FONT, 9)).grid(row=r, column=0, sticky=tk.W, padx=8, pady=4)
            e = ttk.Entry(f_left, width=11)
            e.insert(0, str(self.project[k]))
            e.grid(row=r, column=1, sticky=tk.W, padx=8, pady=4)
            self.t1_entries[k] = e

        ttk.Label(f_left, text="Tình trạng đáy sông K3:").grid(row=len(inputs), column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_k3 = ttk.Combobox(f_left, values=list(HEC18Tables.PIER_K3.keys()), state="readonly", width=22)
        self.cb_k3.set(self.project["k3_type"])
        self.cb_k3.grid(row=len(inputs)+1, column=0, columnspan=2, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(f_left, text="Dạng mũi trụ mặc định K1:").grid(row=len(inputs)+2, column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_k1 = ttk.Combobox(f_left, values=list(HEC18Tables.PIER_K1.keys()), state="readonly", width=22)
        self.cb_k1.set(self.project["k1_type"])
        self.cb_k1.grid(row=len(inputs)+3, column=0, columnspan=2, sticky=tk.EW, padx=8, pady=4)

        ttk.Label(f_left, text="Vật liệu đáy (tính Ks):").grid(row=len(inputs)+4, column=0, sticky=tk.W, padx=8, pady=4)
        self.cb_material = ttk.Combobox(f_left, values=("Cát (Ks = D84)", "Sỏi / cuội (Ks = 3,5 D84)"), state="readonly", width=22)
        self.cb_material.set("Cát (Ks = D84)")
        self.cb_material.grid(row=len(inputs)+5, column=0, columnspan=2, sticky=tk.EW, padx=8, pady=4)
        self.armored_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_left, text="Đáy có khả năng tạo lớp bọc (HEC-18 §6.3)", variable=self.armored_var, command=self._invalidate_results).grid(row=len(inputs)+6, column=0, columnspan=2, sticky=tk.W, padx=8, pady=4)
        f_btn = ttk.Frame(f_left)
        f_btn.grid(row=len(inputs)+7, column=0, columnspan=2, pady=10, padx=8, sticky=tk.EW)

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

        ttk.Button(f_fast, text="Thêm Điểm", command=self.add_point_tab1).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=2, pady=5)
        ttk.Button(f_fast, text="Sửa Điểm", command=self.edit_selected_point_tab1).grid(row=1, column=4, columnspan=3, sticky=tk.EW, padx=2, pady=5)
        ttk.Button(f_fast, text="Xóa Điểm", command=self.del_point_tab1).grid(row=1, column=7, columnspan=3, sticky=tk.EW, padx=2, pady=5)

        cols = ("STT", "Tên Mố/Trụ", "Cao Độ CĐTN (m)", "L chéo (m)", "L ngang (m)", "Độ sâu h (m)", "Phân Loại", "Kích thước a (m)", "Dài L / L' (m)")
        self.tree_tab1 = ttk.Treeview(f_right, columns=cols, show="headings", height=18)
        for c, label in zip(cols, ("STT", "Mố / trụ", "CĐTN (m)", "L chéo (m)", "L ngang (m)", "Sâu h (m)", "Loại điểm", "a (m)", "L (m)")):
            self.tree_tab1.heading(c, text=label)
            self.tree_tab1.column(c, anchor=tk.CENTER, width=45 if c==cols[0] else 180 if c==cols[1] else 100)

        s_x = ttk.Scrollbar(f_right, orient=tk.HORIZONTAL, command=self.tree_tab1.xview)
        s_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_tab1.configure(xscrollcommand=s_x.set)
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
                        "Qe": 0.0, "hydraulics_confirmed": False,
                        "Ae": 0.0,
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
        dlg.geometry(f"1180x{min(800,self.winfo_screenheight()-80)}")
        dlg.minsize(1050, 600)
        dlg.grab_set()

        pane = ttk.PanedWindow(dlg, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left_host=ttk.Frame(pane)
        pane.add(left_host,weight=3)
        f_act=ttk.Frame(left_host)
        f_act.pack(side=tk.BOTTOM,fill=tk.X,padx=4,pady=6)
        left_canvas=tk.Canvas(left_host,highlightthickness=0,bg='#F3F6FA')
        left_scroll=ttk.Scrollbar(left_host,orient=tk.VERTICAL,command=left_canvas.yview)
        left_scroll.pack(side=tk.RIGHT,fill=tk.Y)
        left_canvas.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        f_left=ttk.Frame(left_canvas)
        left_window=left_canvas.create_window((0,0),window=f_left,anchor='nw')
        f_left.bind('<Configure>',lambda event:left_canvas.configure(scrollregion=left_canvas.bbox('all')))
        left_canvas.bind('<Configure>',lambda event:left_canvas.itemconfigure(left_window,width=event.width))

        lbl_guide = tk.Label(
            f_left,
            text="CHỌN MỐ CẦU TRÊN BẢNG, NHẬP CÁC THÔNG SỐ VÀ BẤM 'LƯU MỐ ĐANG CHỌN'",
            font=(UI_FONT, 9, "bold"),
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
                qe = d.get("Qe")
                ae = d.get("Ae")
                ve = qe / ae if qe is not None and ae is not None and ae > 0 else (d.get("Ve") or 0.0)
                fr = ve / math.sqrt(G * ya) if ya > 0 else 0.0
                k1_val = HEC18Tables.ABUT_K1.get(d.get("k1_type", HEC18Tables.DEFAULT_ABUT_K1), (1.0,))[0]
                th = float(d.get("theta", 90.0))
                k2 = (th / 90.0) ** 0.13
                tree_ab.insert("", tk.END, values=(
                    d["name"], f"{d['cdtn']:.2f}", f"{ya:.2f}", ("—" if qe is None else f"{qe:.2f}"), ("—" if ae is None else f"{ae:.2f}"),
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
        ttk.Label(f_form, textvariable=ab_vars["name"], font=(UI_FONT, 10, "bold"), foreground="red").grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_form, text="Cao độ tự nhiên CĐTN (m):").grid(row=0, column=2, sticky=tk.W, padx=6, pady=4)
        ttk.Label(f_form, textvariable=ab_vars["cdtn"], font=(UI_FONT, 9, "bold")).grid(row=0, column=3, sticky=tk.W, padx=6, pady=4)

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

        width_input=tk.StringVar(value='')
        ve_input=tk.StringVar(value='')
        hydraulic_hint=tk.StringVar(value='Nhập ya, L′ và Ve hoặc Qe/Ae; để trống thông số chưa biết, hoặc lấy từ PPLL.')
        ttk.Label(f_form,text='Ve biết trước (m/s), tùy chọn:').grid(row=5,column=0,sticky=tk.W,padx=6,pady=4)
        ttk.Entry(f_form,textvariable=ve_input,width=12).grid(row=5,column=1,sticky=tk.W,padx=6,pady=4)
        ttk.Label(f_form,text='Bề rộng tính Ae (m), tùy chọn:').grid(row=6,column=0,sticky=tk.W,padx=6,pady=4)
        ttk.Entry(f_form,textvariable=width_input,width=12).grid(row=6,column=1,sticky=tk.W,padx=6,pady=4)
        ttk.Label(f_form,text='Bề rộng này không mặc định bằng L′.',wraplength=250).grid(row=6,column=2,columnspan=2,sticky=tk.W)
        ttk.Label(f_form,textvariable=hydraulic_hint,wraplength=650,foreground='#60748A').grid(row=7,column=0,columnspan=4,sticky=tk.W,padx=6,pady=4)
        def read_hydraulics():
            number=HEC18Calculations.optional_number
            return HEC18Calculations.resolve_abutment_hydraulics(qe=number(ab_vars['Qe'].get()),ae=number(ab_vars['Ae'].get()),
                ve=number(ve_input.get()),ya=number(ab_vars['ya'].get()),length=number(ab_vars['L_prime'].get()),blocked_width=number(width_input.get()))

        f_res_calc = ttk.LabelFrame(f_form, text="Thông Số Thủy Lực Suy Ra Tự Động")
        f_res_calc.grid(row=8, column=0, columnspan=4, sticky=tk.EW, padx=6, pady=6)

        ttk.Label(f_res_calc, text="Vận tốc Ve = Qe/Ae:").grid(row=0, column=0, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["ve_disp"], font=(UI_FONT, 9, "bold"), foreground="blue").grid(row=0, column=1, padx=6, pady=2)

        ttk.Label(f_res_calc, text="Hệ số Froude Fr1:").grid(row=0, column=2, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["fr_disp"], font=(UI_FONT, 9, "bold"), foreground="blue").grid(row=0, column=3, padx=6, pady=2)

        ttk.Label(f_res_calc, text="Hệ số góc K2:").grid(row=0, column=4, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["k2_disp"], font=(UI_FONT, 9, "bold"), foreground="blue").grid(row=0, column=5, padx=6, pady=2)

        ttk.Label(f_res_calc, text="Chiều sâu xói ys dự kiến:").grid(row=1, column=0, padx=6, pady=2)
        ttk.Label(f_res_calc, textvariable=ab_vars["ys_preview"], font=(UI_FONT, 10, "bold"), foreground="red").grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=6, pady=2)

        def recompute_preview(*args):
            try:
                solved=read_hydraulics()
                ya,qe,ae,lp=(solved[k] for k in ('ya','Qe','Ae','L_prime'))
                th = HEC18Calculations.optional_number(ab_vars["theta"].get())
                if th is None or not 10<=th<=170: raise ValueError("Góc mố cần trong khoảng 10°–170°.")
                k1_val = HEC18Tables.ABUT_K1.get(ab_vars["k1_type"].get(), (1.0,))[0]

                ve = solved["Ve"]
                hydraulic_hint.set(f"Đã đủ dữ liệu • Qe={'—' if qe is None else format(qe,'.4g')} m³/s • Ae={'—' if ae is None else format(ae,'.4g')} m² • ya={ya:.4g} m • L′={lp:.4g} m")
                fr = ve / math.sqrt(G * ya) if ya > 0 else 0.0
                k2 = (th / 90.0) ** 0.13
                res = HEC18Calculations.abutment_scour(ya, ve, lp, k1_val, th)

                ab_vars["ve_disp"].set(f"{ve:.2f} m/s")
                ab_vars["fr_disp"].set(f"{fr:.3f}")
                ab_vars["k2_disp"].set(f"{k2:.3f}")
                ab_vars["ys_preview"].set(f"{res['ys']:.2f} m ({res['method']})")
            except Exception as exc:
                hydraulic_hint.set(str(exc))
                ab_vars["ve_disp"].set("...")
                ab_vars["fr_disp"].set("...")
                ab_vars["k2_disp"].set("...")
                ab_vars["ys_preview"].set("...")

        width_input.trace_add("write",recompute_preview)
        ve_input.trace_add("write",recompute_preview)
        for k in ["ya", "Qe", "Ae", "L_prime", "theta", "k1_type"]:
            ab_vars[k].trace_add("write", recompute_preview)

        range_start_var=tk.StringVar()
        range_end_var=tk.StringVar()
        pending_ppll={}

        def on_select_ab(event):
            sel = tree_ab.selection()
            if not sel:
                return
            v = tree_ab.item(sel[0], "values")
            name = v[0]
            ab_obj = next((d for d in self.project["abutments_detail"] if d["name"] == name), None)
            if ab_obj:
                ve_input.set(str(ab_obj.get("Ve") or "") if ab_obj.get("Qe") is None or ab_obj.get("Ae") is None else "")
                width_input.set(str(ab_obj.get("blocked_width", "")))
                ab_vars["name"].set(ab_obj["name"])
                ab_vars["cdtn"].set(f"{ab_obj['cdtn']:.2f}")
                ab_vars["ya"].set(str(ab_obj.get("ya", 1.0)) if ab_obj.get("hydraulics_confirmed",True) else "")
                ab_vars["Qe"].set(("" if ab_obj.get("Qe") is None else str(ab_obj["Qe"])) if ab_obj.get("hydraulics_confirmed",True) else "")
                ab_vars["Ae"].set(("" if ab_obj.get("Ae") is None else str(ab_obj["Ae"])) if ab_obj.get("hydraulics_confirmed",True) else "")
                ab_vars["L_prime"].set(str(ab_obj.get("L_prime", 1.70)) if ab_obj.get("hydraulics_confirmed",True) else "")
                ab_vars["k1_type"].set(ab_obj.get("k1_type", HEC18Tables.DEFAULT_ABUT_K1))
                ab_vars["theta"].set(str(ab_obj.get("theta", 90.0)))
                interval=ab_obj.get('ppll_range', ('',''))
                range_start_var.set(str(interval[0]));range_end_var.set(str(interval[1]))
                recompute_preview()

        tree_ab.bind("<<TreeviewSelect>>", on_select_ab)

        children = tree_ab.get_children()
        if children:
            tree_ab.selection_set(children[0])
            on_select_ab(None)

        range_box = ttk.LabelFrame(f_left,text='Ước tính từ PPLL — chọn đúng đoạn dòng chảy bị nền đường chắn')
        range_box.pack(fill=tk.X,padx=5,pady=5)
        ttk.Label(range_box,text='X đầu (m):').grid(row=0,column=0,padx=3)
        x_start=ttk.Entry(range_box,width=10,textvariable=range_start_var);x_start.grid(row=0,column=1,padx=3)
        ttk.Label(range_box,text='X cuối (m):').grid(row=0,column=2,padx=3)
        x_end=ttk.Entry(range_box,width=10,textvariable=range_end_var);x_end.grid(row=0,column=3,padx=3)
        ttk.Label(range_box,text='X ngang cộng dồn, gốc tại điểm đầu mặt cắt. Không tự lấy đoạn M1–M2.\nPPLL 1D trên mặt cắt nhập là ước tính; cần kiểm tra tính đại diện cho thượng lưu.',wraplength=620).grid(row=1,column=0,columnspan=5,sticky=tk.W,padx=3,pady=4)
        def take_ppll():
            try:
                if not ab_vars['name'].get(): raise ValueError('Chọn mố trước khi lấy thông số.')
                self.run_full_system(hydraulics_only=True)
                c=getattr(self,'_ppll_context',{})
                if not c: return
                start,end=float(x_start.get()),float(x_end.get())
                values=HEC18Calculations.blocked_flow_from_segments(c['depths'],c['widths'],c['alpha'],start,end)
                ve_input.set('')
                width_input.set(format(values['L_prime'],'.9g'))
                for key in ('Qe','Ae','ya','L_prime'): ab_vars[key].set(format(values[key],'.9g'))
                pending_ppll.clear()
                pending_ppll.update(name=ab_vars['name'].get(),interval=[start,end],values=values)
                recompute_preview()
                messagebox.showinfo('Đã lấy thông số',f"Đoạn X={start:.2f}–{end:.2f} m.\nQe={values['Qe']:.3f} m³/s; Ae={values['Ae']:.3f} m²; ya={values['ya']:.3f} m; L′={values['L_prime']:.3f} m.\nKiểm tra đoạn chắn và bấm Lưu mố đang chọn.")
            except Exception as exc:
                messagebox.showerror('Không lấy được thủy lực mố',str(exc))
        ttk.Button(range_box,text='Tính PPLL & lấy thông số',command=take_ppll).grid(row=0,column=4,padx=5)

        def save_current_ab():
            name = ab_vars["name"].get()
            if not name:
                messagebox.showwarning("Cảnh báo", "Vui lòng chọn một mố từ danh sách trước!")
                return
            for d in self.project["abutments_detail"]:
                if d["name"] == name:
                    try:
                        solved=read_hydraulics()
                        theta=HEC18Calculations.optional_number(ab_vars['theta'].get())
                        if theta is None or not 10<=theta<=170: raise ValueError('Góc mố cần trong khoảng 10°–170°.')
                        d.update({k:solved[k] for k in ('ya','Qe','Ae','Ve','L_prime')})
                        d['theta']=theta
                        width=HEC18Calculations.optional_number(width_input.get())
                        if width is None: d.pop('blocked_width',None)
                        else: d['blocked_width']=width
                        for key in ('ya','Qe','Ae','L_prime'): ab_vars[key].set('' if solved[key] is None else format(solved[key],'.9g'))
                        d["k1_type"] = ab_vars["k1_type"].get()
                        d["hydraulics_confirmed"] = True
                        if pending_ppll.get('name')==name and all(d[k] is not None and math.isclose(d[k],pending_ppll['values'][k],rel_tol=1e-8) for k in ('Qe','Ae','ya','L_prime')):
                            d['ppll_range']=pending_ppll['interval']
                            d['hydraulic_source']='PPLL 1D — ước tính theo đoạn chắn đã chọn'
                        else:
                            d.pop('ppll_range',None)
                            d['hydraulic_source']='Nhập thủ công'
                        self._invalidate_results()
                        refresh_table()
                        messagebox.showinfo("Thành công", f"Đã lưu thành công thông số thủy lực cho {name}!")
                    except Exception as e:
                        messagebox.showerror("Lỗi", f"Không tính được thủy lực mố: {e}")
                    break

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
            font=(UI_FONT, 9, "bold"),
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
                loai = HEC18Calculations.foundation_exposure(d["cdtn"],z_cur,d["T"],float(self.t1_entries["htk"].get()),d.get("has_cap",True),d.get("has_piles",True))["state"]
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

        has_cap_var = tk.BooleanVar(value=True)
        has_piles_var = tk.BooleanVar(value=True)
        z_top_display=tk.StringVar(value="—")
        cap_shape = tk.StringVar(value="Mũi vuông (Square nose)")
        manual_aproj = tk.BooleanVar(value=False)
        ent_vars = {
            "name": tk.StringVar(), "cdtn": tk.StringVar(), "loai_tru": tk.StringVar(),
            "apier": tk.StringVar(), "Lpier": tk.StringVar(),
            "apc": tk.StringVar(), "Lpc": tk.StringVar(), "T": tk.StringVar(),
            "z_day_be": tk.StringVar(), "ho_display": tk.StringVar(), "f": tk.StringVar(),
            "ap": tk.StringVar(), "S": tk.StringVar(), "m": tk.StringVar(), "n": tk.StringVar(), "aproj": tk.StringVar()
        }

        ttk.Label(f_sub1, text="Tên trụ:").grid(row=0, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Label(f_sub1, textvariable=ent_vars["name"], font=(UI_FONT, 9, "bold"), foreground="blue").grid(row=0, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub1, text="Cao độ CĐTN:").grid(row=1, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Label(f_sub1, textvariable=ent_vars["cdtn"]).grid(row=1, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub1, text="Trạng thái ban đầu:", font=(UI_FONT, 8, "bold"), foreground="#C62828").grid(row=2, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Label(f_sub1,textvariable=ent_vars['loai_tru'],wraplength=160).grid(row=2,column=1,padx=3,pady=2)
        ttk.Checkbutton(f_sub1,text='Có bệ móng',variable=has_cap_var).grid(row=5,column=0,columnspan=2,sticky=tk.W)
        ttk.Checkbutton(f_sub1,text='Có nhóm cọc dưới bệ',variable=has_piles_var).grid(row=6,column=0,columnspan=2,sticky=tk.W)

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

        ttk.Label(f_sub2, text="Cao độ đáy bệ Z_đáy (m):", font=(UI_FONT, 9, "bold"), foreground="#B71C1C").grid(row=3, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["z_day_be"], width=8).grid(row=3, column=1, padx=3, pady=2)

        ttk.Label(f_sub2, text="ho = Zđáy - CĐTN:").grid(row=4, column=0, sticky=tk.W, padx=3, pady=2)
        lbl_ho_show = tk.Label(f_sub2, textvariable=ent_vars["ho_display"], font=(UI_FONT, 9, "bold"), fg="#D32F2F")
        lbl_ho_show.grid(row=4, column=1, sticky=tk.W, padx=3, pady=2)

        ttk.Label(f_sub2, text="Gờ bệ trước mũi f (m):").grid(row=5, column=0, sticky=tk.W, padx=3, pady=2)
        ttk.Entry(f_sub2, textvariable=ent_vars["f"], width=8).grid(row=5, column=1, padx=3, pady=2)

        def on_z_day_change(*args):
            try:
                z_d = float(ent_vars["z_day_be"].get())
                z_tn = float(ent_vars["cdtn"].get())
                ho_calc = z_d - z_tn
                z_top_display.set(f"{z_d+float(ent_vars['T'].get()):.2f} m")
                ent_vars["ho_display"].set(f"{ho_calc:.2f} m")
                exposure=HEC18Calculations.foundation_exposure(z_tn,z_d,float(ent_vars['T'].get()),float(self.t1_entries['htk'].get()),has_cap_var.get(),has_piles_var.get())
                ent_vars['loai_tru'].set(exposure['state'])
            except Exception:
                ent_vars["ho_display"].set("...")
                ent_vars["loai_tru"].set("Chưa đủ cao độ")
                z_top_display.set("—")

        for key in ('z_day_be','T','cdtn'):
            ent_vars[key].trace_add('write',on_z_day_change)
        has_cap_var.trace_add('write',on_z_day_change)
        has_piles_var.trace_add('write',on_z_day_change)

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
                manual_aproj.set(detail.get("manual_aproj", False))
                cap_shape.set(detail.get("cap_shape", "Mũi vuông (Square nose)"))
                has_cap_var.set(detail.get("has_cap",True))
                has_piles_var.set(detail.get("has_piles",True))

        tree_p.bind("<<TreeviewSelect>>", on_select_pier)

        children = tree_p.get_children()
        if children:
            tree_p.selection_set(children[0])
            on_select_pier(None)

        ttk.Checkbutton(f_sub3, text="Nhập aproj riêng (bố trí đặc biệt)", variable=manual_aproj).grid(row=5, column=0, columnspan=2, sticky=tk.W)

        ttk.Label(f_sub2, text="Dạng mũi bệ K1:").grid(row=6, column=0, sticky=tk.W)
        ttk.Combobox(f_sub2, textvariable=cap_shape, values=list(HEC18Tables.PIER_K1), state="readonly", width=18).grid(row=6, column=1)

        ttk.Label(f_sub2,text="CĐ đỉnh bệ (đáy + T):").grid(row=7,column=0,sticky=tk.W)
        ttk.Label(f_sub2,textvariable=z_top_display).grid(row=7,column=1,sticky=tk.W)

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
                        d["has_cap"] = has_cap_var.get()
                        d["has_piles"] = has_piles_var.get()
                        d['loai_tru']=HEC18Calculations.foundation_exposure(z_tn,z_d,d['T'],float(self.t1_entries['htk'].get()),d['has_cap'],d['has_piles'])['state']

                        d["f"] = float(ent_vars["f"].get())
                        d["ap"] = float(ent_vars["ap"].get())
                        d["S"] = float(ent_vars["S"].get())
                        d["m"] = int(ent_vars["m"].get())
                        d["n"] = int(ent_vars["n"].get())
                        d["aproj"] = float(ent_vars["aproj"].get())
                        d["cap_shape"] = cap_shape.get()
                        d["manual_aproj"] = manual_aproj.get()
                        self._invalidate_results()

                        for r in self.project["cross_section"]:
                            if str(r[1]).strip() == name:
                                r[5] = ap_val
                                r[6] = lp_val
                                break

                        refresh_dlg_table()
                        self._refresh_tab1_table()
                        messagebox.showinfo("Thành công", f"Đã lưu trụ {name}:\n- Trạng thái ban đầu: {d['loai_tru']}\n- CĐ đáy bệ = {z_d:.2f} m\n- ho = {d['ho']:.2f} m")
                    except Exception as e:
                        messagebox.showerror("Lỗi", f"Vui lòng nhập đúng định dạng số! Chi tiết: {e}")
                    break

        def apply_all_piers():
            if not messagebox.askyesno("Xác nhận", "Áp dụng kích thước Bệ và Cọc này cho TẤT CẢ các TRỤ?"):
                return
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
                    
                    d['has_cap']=has_cap_var.get()
                    d['has_piles']=has_piles_var.get()
                    d['loai_tru']=HEC18Calculations.foundation_exposure(float(d['cdtn']),z_d,d['T'],float(self.t1_entries['htk'].get()),d['has_cap'],d['has_piles'])['state']

                    d["f"] = float(ent_vars["f"].get())
                    d["ap"] = float(ent_vars["ap"].get())
                    d["S"] = float(ent_vars["S"].get())
                    d["m"] = int(ent_vars["m"].get())
                    d["n"] = int(ent_vars["n"].get())
                    d["aproj"] = float(ent_vars["aproj"].get())
                    d["cap_shape"] = cap_shape.get()
                    d["manual_aproj"] = manual_aproj.get()
                    self._invalidate_results()

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

        txt_p_guide = tk.Text(f_right_side, height=20, bg="#FFFFFF", font=(UI_FONT, 9), padx=6, pady=4)
        txt_p_guide.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        p_guide_text = """CHỌN THÀNH PHẦN THEO CAO ĐỘ BAN ĐẦU

So sánh với CĐTN:
• Đỉnh bệ ≤ CĐTN: bệ/cọc còn chôn, chỉ tính thân trụ.
• Đáy bệ ≤ CĐTN < đỉnh bệ: lộ bệ; tính thân + bệ (Case 2), không cộng cọc.
• CĐTN < đáy bệ: tính bệ (Case 1) và cọc nếu cấu tạo có cọc đang ngập.

Đỉnh bệ = đáy bệ + T.
Chỉ bộ phận tiếp xúc dòng chảy dưới mực nước tham gia tính.
Nếu bệ nằm ngoài nước nhưng cọc vẫn ngập, chỉ phần cọc ngập tham gia.
Loại móng giữ cố định theo cao độ ban đầu, không chuyển loại sau xói.

Công thức thành phần HEC vẫn có các biến trung gian y2, V2, h2, y3, V3; những biến này không dùng để đổi loại móng ban đầu trong chế độ này.

Mô tả đúng cấu tạo bằng Có bệ móng / Có nhóm cọc dưới bệ. Chỉ bỏ chọn Có bệ móng khi thực tế không có bệ.

Cọc lộ là đoạn ngoài bệ, phía dưới mặt dưới bệ; cao độ mũi cọc dùng kiểm tra an toàn móng, không quyết định đoạn cọc tiếp xúc dòng chảy.

Nhóm cọc: m hàng dọc dòng, n cột ngang dòng. aproj tự tính cho lưới đều; nhập riêng cho bố trí đặc biệt.
Ks: D84 cho cát; 3,5 D84 cho sỏi/cuội.
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

        self.lbl_htk_res = ttk.Label(f_top, text="Mực nước thiết kế Htk = ...", font=(UI_FONT, 10, "bold"), foreground="#B71C1C")
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

        self.lbl_ppll_htk = ttk.Label(f_info, text="Mực nước tính toán Htk: ... m", font=(UI_FONT, 9, "bold"), foreground="#0D47A1")
        self.lbl_ppll_htk.grid(row=0, column=0, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_qtk = ttk.Label(f_info, text="Lưu lượng thiết kế Qtk: ... m3/s", font=(UI_FONT, 9, "bold"), foreground="#B71C1C")
        self.lbl_ppll_qtk.grid(row=0, column=1, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_qsum = ttk.Label(f_info, text="Tổng Q phân phối ΣQi: ... m3/s", font=(UI_FONT, 9, "bold"), foreground="#2E7D32")
        self.lbl_ppll_qsum.grid(row=0, column=2, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_alpha = ttk.Label(f_info, text="Hệ số phân bố α: ...", font=(UI_FONT, 9))
        self.lbl_ppll_alpha.grid(row=1, column=0, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_wsum = ttk.Label(f_info, text="Tổng diện tích ướt Σω: ... m2", font=(UI_FONT, 9))
        self.lbl_ppll_wsum.grid(row=1, column=1, padx=12, pady=4, sticky=tk.W)

        self.lbl_ppll_vbq = ttk.Label(f_info, text="Vận tốc bình quân Vbq: ... m/s", font=(UI_FONT, 9))
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
        self.nb_scour.add(self.subtab_single_pier, text="7.1 Chỉ xói thân trụ")

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
        self.nb_scour.add(self.subtab_lobe, text="7.2 Case 2: XCB Lộ Bệ")

        f_lobe_1 = ttk.LabelFrame(self.subtab_lobe, text="1, Xói cục bộ do thân trụ gây ra (yspier)")
        f_lobe_1.pack(fill=tk.X, padx=6, pady=2)
        cols_lobe_1 = ("No.", "CĐTN", "y1", "V1", "Fr1", "a", "K1", "θ", "L", "K2", "K3", "f", "ho", "T", "h1", "Khpier", "D50", "Vc", "V/Vc", "Kw", "yspier")
        self.tree_lobe_1 = ttk.Treeview(f_lobe_1, columns=cols_lobe_1, show="headings", height=4)
        for c in cols_lobe_1:
            self.tree_lobe_1.heading(c, text=c)
            self.tree_lobe_1.column(c, anchor=tk.CENTER, width=62)
        scroll_y = ttk.Scrollbar(f_lobe_1, orient=tk.VERTICAL, command=self.tree_lobe_1.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x = ttk.Scrollbar(f_lobe_1, orient=tk.HORIZONTAL, command=self.tree_lobe_1.xview)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_lobe_1.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree_lobe_1.pack(fill=tk.X, padx=3, pady=2)

        f_lobe_2 = ttk.LabelFrame(self.subtab_lobe, text="2, Xói cục bộ do bệ trụ (ysfooting)")
        f_lobe_2.pack(fill=tk.X, padx=6, pady=2)
        cols_lobe_2 = ("No.", "CĐTN", "y1", "V1", "yspier", "y2", "h2", "h1", "yf", "V2", "Ks", "Vf", "af", "Frf", "Kw", "ysfooting")
        self.tree_lobe_2 = ttk.Treeview(f_lobe_2, columns=cols_lobe_2, show="headings", height=4)
        for c in cols_lobe_2:
            self.tree_lobe_2.heading(c, text=c)
            self.tree_lobe_2.column(c, anchor=tk.CENTER, width=68)
        scroll_y = ttk.Scrollbar(f_lobe_2, orient=tk.VERTICAL, command=self.tree_lobe_2.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x = ttk.Scrollbar(f_lobe_2, orient=tk.HORIZONTAL, command=self.tree_lobe_2.xview)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_lobe_2.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree_lobe_2.pack(fill=tk.X, padx=3, pady=2)

        f_lobe_3 = ttk.LabelFrame(self.subtab_lobe, text="3, Kết quả phân tích xói cục bộ tại trụ (ys = yspier + ysfooting)")
        f_lobe_3.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        cols_lobe_3 = ("STT", "Tên Trụ", "CĐTN (m)", "CĐ đáy bệ (m)", "ho (m)", "Xói thân ys,pier (m)", "Xói bệ ys,footing (m)", "Tổng chiều sâu xói ys (m)", "Cao độ đáy xói (m)")
        self.tree_lobe_3 = ttk.Treeview(f_lobe_3, columns=cols_lobe_3, show="headings", height=4)
        for c in cols_lobe_3:
            self.tree_lobe_3.heading(c, text=c)
            self.tree_lobe_3.column(c, anchor=tk.CENTER, width=115)
        scroll_y = ttk.Scrollbar(f_lobe_3, orient=tk.VERTICAL, command=self.tree_lobe_3.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x = ttk.Scrollbar(f_lobe_3, orient=tk.HORIZONTAL, command=self.tree_lobe_3.xview)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_lobe_3.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree_lobe_3.pack(fill=tk.BOTH, expand=True, padx=3, pady=2)

        # 7.3: TRỤ LỘ BỆ & CỌC
        self.subtab_lococ = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_lococ, text="7.3 Case 1: XCB Lộ Cọc")

        f_lc_4 = ttk.LabelFrame(self.subtab_lococ, text="Xói bệ trên đáy sông (Case 1); nhóm cọc nếu có")
        f_lc_4.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        cols_lc_4 = ("STT", "Tên Trụ", "CĐTN (m)", "CĐ đáy bệ (m)", "ho (m)", "yspier (m)", "yspc (m)", "yspg (m)", "Tổng xói ys (m)", "Cao độ sau xói (m)", "Ghi chú phân loại")
        self.tree_lc_4 = ttk.Treeview(f_lc_4, columns=cols_lc_4, show="headings", height=12)
        for c in cols_lc_4:
            self.tree_lc_4.heading(c, text=c)
            self.tree_lc_4.column(c, anchor=tk.CENTER, width=105)
        self.tree_lc_4.pack(fill=tk.BOTH, expand=True, padx=3, pady=2)

        # 7.4: XÓI CỤC BỘ MỐ CẦU
        self.subtab_abutment = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_abutment, text="7.4 Mố cầu")

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

        self.subtab_exposure = ttk.Frame(self.nb_scour)
        self.nb_scour.add(self.subtab_exposure,text="7.5 Cao độ ban đầu")
        ttk.Label(self.subtab_exposure,text="Chọn thành phần xói theo CĐTN, cao độ đáy/đỉnh bệ và phần cọc tiếp xúc dòng chảy ban đầu.\nLoại móng được giữ cố định; không chuyển loại theo cao độ đáy sau xói.",padding=10).pack(anchor='w')
        cols=('Trụ','CĐTN','Đáy bệ','Đỉnh bệ','Mực nước','Trạng thái ban đầu','Bệ ngập (m)','Cọc lộ ngập (m)','Thành phần tính','HEC')
        self.tree_exposure=ttk.Treeview(self.subtab_exposure,columns=cols,show='headings',height=12)
        for c in cols:
            self.tree_exposure.heading(c,text=c)
            self.tree_exposure.column(c,width=175 if c in ('Trạng thái ban đầu','Thành phần tính') else 135,anchor=tk.CENTER)
        sx=ttk.Scrollbar(self.subtab_exposure,orient=tk.HORIZONTAL,command=self.tree_exposure.xview)
        sx.pack(side=tk.BOTTOM,fill=tk.X)
        sy=ttk.Scrollbar(self.subtab_exposure,orient=tk.VERTICAL,command=self.tree_exposure.yview)
        sy.pack(side=tk.RIGHT,fill=tk.Y)
        self.tree_exposure.configure(xscrollcommand=sx.set,yscrollcommand=sy.set)
        self.tree_exposure.pack(fill=tk.BOTH,expand=True,padx=6,pady=6)

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
        short_heads = ("Mố / trụ", "Vị trí X (m)", "CĐTN (m)", "Đáy bệ (m)", "h0 (m)", "Dài hạn (m)", "Thu hẹp (m)", "Cục bộ (m)", "Tổng xói (m)", "Đáy xói (m)")
        for c, label in zip(cols, short_heads):
            self.tree_summary.heading(c, text=label)
            self.tree_summary.column(c, anchor=tk.CENTER, width=110)
        summary_scroll = ttk.Scrollbar(f_table, orient=tk.VERTICAL, command=self.tree_summary.yview)
        summary_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_summary.configure(yscrollcommand=summary_scroll.set)
        self.tree_summary.pack(fill=tk.X, padx=4, pady=4)

        f_plot = ttk.LabelFrame(self.tab8, text="Đồ Thị Mặt Cắt Thoát Nước & Hố Xói Dưới Cầu (Scour Prism)")
        f_plot.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.fig_prism = Figure(figsize=(10, 3.8), dpi=100, layout="constrained")
        self.ax_prism = self.fig_prism.add_subplot(1, 1, 1)
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
        self.ax_prism.set_facecolor("#FAFCFE")
        self.ax_prism.grid(True, color="#DCE5EE", linewidth=0.7)
        for spine in ('top', 'right'): self.ax_prism.spines[spine].set_visible(False)
        self.ax_prism.legend(loc="lower right", fontsize=8)
        self.canvas_prism.draw()

    # =========================================================================
    # THỰC THI TÍNH TOÁN TOÀN BỘ (RUN FULL SYSTEM - ĐÃ SỬA CHUẨN XÁC VCAU)
    # =========================================================================
    def run_full_system(self, hydraulics_only=False):
        cs = self.project["cross_section"]
        if not cs:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập dữ liệu mặt cắt sông!")
            return

        try:
            self._invalidate_results()
            warnings = ['Thủy lực đến trụ dùng phân phối mặt cắt 1D và bảo toàn lưu lượng; cần đối chiếu mô hình thủy lực công trình.',
                        'Nước dềnh là ước tính theo công thức trong mẫu, không thuộc phần công thức xói HEC-18 đã kiểm chứng.']
            if self.project.get('is_demo'): warnings.append('Đang dùng bộ dữ liệu minh họa; thay bằng số liệu công trình trước khi thiết kế.')
            self._validate_calculation_inputs(hydraulics_only=hydraulics_only)
            self.sync_all_details()

            htk = float(self.t1_entries["htk"].get())
            qtk = float(self.t1_entries["qtk"].get())
            skew = float(self.t1_entries["skew"].get())
            s1 = float(self.t1_entries["s1"].get())
            d50_mm = float(self.t1_entries["d50"].get())
            d50_m = d50_mm / 1000.0
            d84_mm = float(self.t1_entries["d84"].get())
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

            sum_A = sum(Ai_vals)
            sum_w = sum(w_vals)
            if sum_A <= 0 or sum_w <= 0: raise ValueError('Mặt cắt không có diện tích ngập dương.')
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

            W1 = sum(wet_w)
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

            self._ppll_context = dict(depths=depth, widths=dl_vals, alpha=alpha_v,
                                       htk=htk,qtk=qtk,extent=sum(dl_vals[1:]))
            if hydraulics_only:
                self.nb.select(self.tab3)
                self.status_text.set('Đã tính PPLL • Chưa tính xói / chưa có báo cáo kết quả')
                return

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
                # Hình chiếu mặt bằng B|cosθ| + L|sinθ|; nhóm cọc dùng hợp các hình chiếu.
                b_proj_than = a_tru * abs(cos_sk) + L_tru * abs(sin_sk)
                b_proj_be = apc * abs(cos_sk) + Lpc * abs(sin_sk)
                b_proj_coc = (aproj if detail and detail.get('manual_aproj',False) else HEC18Calculations.projected_pile_width(ap_coc,S_coc,m_hang,n_cot,skew)) if not detail or (detail.get('has_cap',True) and detail.get('has_piles',True)) else 0.0

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

                if detail and not detail.get('has_cap',True):
                    w_coc = w_be = 0.0
                    w_than = b_proj_than * hi
                if detail and not detail.get("has_piles",True): w_coc=0.0
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

            W2 = W1 - sum_b_choan
            if W2 <= 0 or sum_w <= sum_w_choan:
                raise ValueError('Choán dòng lớn hơn mặt cắt ngập: kiểm tra góc và kích thước móng.')
            W1_up = w1_up_in if w1_up_in > 0 else W1
            w_eff_bridge = sum_w - sum_w_choan
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
            a_factor = float(self.t1_entries["a_denh"].get())
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
            q1_up = float(self.t1_entries['q1_up'].get()) or qtk
            y1_up = float(self.t1_entries['y1_up'].get()) or y1_mean
            y0_bridge = float(self.t1_entries['y0_bridge'].get()) or y1_mean
            v_up = q1_up / (W1_up * y1_up)
            cr = HEC18Calculations.contraction_scour(qtk,y1_up,v_up,W1_up,W2,d50_m,s1,omega,
                                                    q1=q1_up,y0=y0_bridge,armored=self.armored_var.get())
            if cr['note']: warnings.append(cr['note'])
            Vc = cr["vc"]
            ysc = cr["ysc"]
            bed_z = htk - y1_up

            self.tree_xoi_chung.insert("", tk.END, values=(
                "Lòng sông", f"{bed_z:.2f}", f"{y1_up:.2f}", f"{d50_mm:.3f}", f"{Vc:.3f}",
                f"{v_up:.2f}", f"{(Vc/v_up):.3f}", cr["mode"], f"{s1:.5e}",
                f"{cr['v_star']:.4f}", f"{omega:.3f}", f"{cr['ratio_vw']:.3f}", f"{cr['k1']}", f"{q1_up:.2f}", f"{W1_up:.2f}",
                f"{qtk:.2f}", f"{W2:.2f}", f"{cr['dm']*1000:.3f}", f"{cr['y2']:.2f}", f"{htk-y0_bridge:.2f}", f"{y0_bridge:.2f}",
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
                        Qe = ab_cfg.get("Qe")
                        Ae = ab_cfg.get("Ae")
                        l_prime = float(ab_cfg.get("L_prime", 1.70))
                        k1_type_name = ab_cfg.get("k1_type", HEC18Tables.DEFAULT_ABUT_K1)
                        k1_abut = HEC18Tables.ABUT_K1.get(k1_type_name, (1.00,))[0]
                        th = float(ab_cfg.get("theta", 90.0))
                    else:
                        ya, Qe, Ae, l_prime, k1_abut, th = max(0.1, htk - cdtn), 24.39, 8.19, 1.70, 1.00, 90.0

                    if ab_cfg is None: raise ValueError(f"{p_name}: chưa cấu hình thủy lực mố.")
                    ve = HEC18Calculations.resolve_abutment_hydraulics(qe=Qe,ae=Ae,ve=ab_cfg.get('Ve'),ya=ya,length=l_prime,blocked_width=ab_cfg.get('blocked_width'))['Ve']
                    ab_res = HEC18Calculations.abutment_scour(ya, ve, l_prime, k1_abut, th)
                    ys_abut = ab_res["ys"]
                    cd_sau_xoi_ab = cdtn - (gen_lower + ys_abut)

                    hd_short = "Tường đứng" if k1_abut == 1.0 else ("Tường cánh" if k1_abut == 0.82 else "Mái taluy")
                    self.tree_abutment.insert("", tk.END, values=(
                        p_name, f"{cdtn:.2f}", f"{ya:.2f}", ("—" if Qe is None else f"{Qe:.2f}"), ("—" if Ae is None else f"{Ae:.2f}"),
                        f"{ve:.2f}", f"{ab_res['fr']:.3f}", hd_short, f"{k1_abut:.2f}",
                        f"{th:.1f}", f"{ab_res['k2']:.3f}", f"{l_prime:.2f}", f"{ys_abut:.2f}", f"{cd_sau_xoi_ab:.2f}", ab_res["method"]
                    ))

                    ys_final_chosen = ys_abut
                    z_be_disp, ho_disp = "-", "-"
                    v1, y1 = ve, ya

                # B. TÍNH CHO TRỤ CẦU
                else:
                    y1 = p['hi']
                    v1 = p['Vloc']  # Approach hydraulics at the initial natural bed.
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
                    ho = ho0  # Select participating foundation components at the initial bed.

                    z_be_disp = f"{z_be:.2f}"
                    ho_disp = f"{ho0:.2f}"

                    # 7.1 Trụ đơn
                    if y1 > 0 and v1 > 0:
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
                    if detail and (not detail.get('has_cap',True) or not detail.get('has_piles',True)):
                        aproj=0.0
                    elif not detail or not detail.get('manual_aproj', False):
                        aproj = HEC18Calculations.projected_pile_width(ap,S_coc,m_hang,n_cot,skew)
                    cp = HEC18Calculations.complex_pier(y1,v1,a,k1_eff,k2,k3_val,kw_single,capped,
                        ho,T_be,f_dist,apc,ap,S_coc,m_hang,n_cot,aproj,
                        pile_exposed=detail.get("has_piles",True) if detail else True,d50_m=d50_m,d84_m=d84_m,
                        Lpc=detail.get('Lpc',13.32) if detail else 13.32,
                        theta_deg=skew,bed_material=self.project.get('bed_material','sand'),
                        cap_k1=HEC18Tables.PIER_K1.get(detail.get('cap_shape', 'Mũi vuông (Square nose)') if detail else 'Mũi vuông (Square nose)', (1.1,))[0],
                        has_cap=detail.get('has_cap',True) if detail else True,initial_only=True)
                    has_cap = detail.get('has_cap',True) if detail else True
                    has_piles = detail.get('has_piles',True) if detail else True
                    if not has_cap: z_be_disp=ho_disp='-'
                    initial = HEC18Calculations.foundation_exposure(cdtn,z_be,T_be,htk,has_cap,has_piles)
                    loai_tru = ('Trụ đơn đặc' if cp['cap_case']==0 else 'Lộ bệ & cọc' if cp['cap_case']==1 else 'Lộ bệ')
                    participating=[]
                    stem_wet=max(0.0,htk-max(cdtn,z_be+T_be)) if has_cap else max(0.0,htk-cdtn)
                    if stem_wet>1e-9: participating.append('Thân trụ')
                    if initial['cap_wet']>1e-9: participating.append('Bệ')
                    if initial['pile_wet']>1e-9: participating.append('Cọc')
                    components=' + '.join(participating) if y1>0 and v1>0 else 'Không có dòng chảy'

                    self.tree_exposure.insert('',tk.END,values=(p_name,f'{cdtn:.2f}',f'{z_be:.2f}' if has_cap else '—',
                        f'{z_be+T_be:.2f}' if has_cap else '—',f'{htk:.2f}',initial['state'],
                        f'{initial["cap_wet"]:.2f}',f'{initial["pile_wet"]:.2f}',components,
                        '—' if cp['cap_case']==0 else f'Case {cp["cap_case"]}'))
                    if cp['cap_case'] and (f_dist/a > 1.5 or cp['h1']/a > 2):
                        warnings.append(f'{p_name}: tỷ số hình học vượt phạm vi đồ thị K_hpier Hình 7.6; cần đánh giá riêng.')
                    if loai_tru == 'Trụ đơn đặc':
                        self.tree_single_pier.insert("", tk.END, values=(
                            f"{stt_p}. {p_name}", f"{cdtn:.2f}", f"{y1:.2f}", f"{v1:.2f}", f"{fr1:.3f}",
                            f"{a:.2f}", k1_short, f"{k1_eff:.2f}", f"{skew:.1f}", f"{L:.2f}",
                            f"{k2:.3f}", k3_name.split(" (")[0], f"{k3_val:.2f}", f"{d50_mm:.3f}", f"{vc_tru:.2f}",
                            f"{ratio_v_vc:.2f}", f"{kw_single:.3f}", f"{ys_pier_single:.2f}", f"{cd_single:.2f}", note_single
                        ))

                    ks_val = cp['ks']
                    yspier_lobe, h1 = cp['ys_pier'], cp['h1']
                    yf_lb, y2_lb, h2_lb, v2_lb = cp['yf'],cp['y2'],cp['h2'],cp['v2']
                    ysfooting_lb, vf_lb, fr2_lb, kw_lb = cp['ys_pc'],cp['vf'],cp['frf'],cp['kw_pc']

                    # Lưu các giá trị chưa làm tròn cho báo cáo, không tính lại khi xuất.
                    self._report_piers.append(dict(
                        name=p_name, stt=stt_p, cdtn=cdtn, kind=loai_tru,has_cap=has_cap,has_piles=has_piles,
                        y1=y1, v1=v1, fr1=fr1, a=a, shape=k1_short,
                        k1=k1_eff, theta=skew, L=L, k2=k2, bed=k3_name.split(" (")[0],
                        k3=k3_val, d50=d50_mm, vc=vc_tru, ratio=ratio_v_vc,
                        kw=kw_single, single=ys_pier_single, z_single=cd_single,
                        f=f_dist, ho=ho, ho0=ho0, T=T_be, apc=apc, z_be=z_be,
                        Lpc=(detail.get('Lpc', 13.32) if detail else 13.32),
                        ap=ap, S=S_coc, m=m_hang, n=n_cot, aproj=aproj,
                        initial_exposure=initial,exposure_basis="initial",
                        cp=copy.deepcopy(cp), cap_shape=(detail.get('cap_shape', 'Mũi vuông (Square nose)') if detail else 'Mũi vuông (Square nose)').split(" (")[0], yf=yf_lb, ks=ks_val, vf=vf_lb,
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

            self._report_context = dict(htk=htk, qtk=qtk, y_deg=y_deg, q1_up=q1_up, y1_up=y1_up, y0_bridge=y0_bridge,
                                        bed_material=self.project.get("bed_material","sand"),
                                        skew=skew, s1=s1, d50=d50_mm, d84=d84_mm, omega=omega,
                                        k1_type=k1_pier_name, k3_type=k3_name,
                                        W1=W1, W1_up=W1_up, W2=W2, area=sum_w,
                                        area_bridge=w_eff_bridge, alpha=alpha_v,
                                        ai_vals=copy.deepcopy(Ai_vals), wet_w=copy.deepcopy(wet_w),
                                        vh_data=copy.deepcopy(self.vh_data),
                                        n_manning=self.t1_entries['n_manning'].get(),
                                        project_name=self.project.get("project_name", ""),
                                        bridge_name=self.project.get("bridge_name", ""))

            self.calc_warnings = warnings
            self._refresh_result_summary()
            self.nb.select(self.tab8)
            if warnings:
                messagebox.showwarning('Kết quả và điều kiện áp dụng', '\n'.join(warnings))
            else:
                messagebox.showinfo('Hoàn tất', f'Đã tính xói cho {self.project["bridge_name"]}.')

        except Exception as e:
            self._invalidate_results()
            messagebox.showerror("Lỗi thực thi", f"Quá trình tính toán gặp sự cố: {e}")

    # =========================================================================
    # DỮ LIỆU MẪU & CÁC THAO TÁC FILE
    # =========================================================================
    def _load_sample_data(self):
        # Dữ liệu minh họa để thử giao diện, không thay thế hồ sơ thiết kế.
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
        self.project['is_demo'] = True
        self.sync_all_details()
        for d in self.project['abutments_detail']:
            d.update(Qe=24.39 if '1' in d['name'] else 55.64,Ae=8.19 if '1' in d['name'] else 6.80,hydraulics_confirmed=True)
            d['L_prime']=d['Ae']/d['ya']  # Consistent demonstration inputs for the same blocked stream tube.
        # Kích thước bệ và cọc của bộ dữ liệu minh họa.
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
        self._invalidate_results()
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
            self._invalidate_results()
            self.project["is_demo"] = False
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
        self.project["bed_material"] = "gravel" if self.cb_material.get().startswith("Sỏi") else "sand"
        self.project["armored"] = self.armored_var.get()
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
            self._invalidate_results()
            self.project = {**copy.deepcopy(self._project_defaults), **data}
            self.lbl_title.config(text=f"DỰ ÁN: {self.project.get('project_name','').upper()} | CÔNG TRÌNH: {self.project.get('bridge_name','').upper()}")
            for k in self.t1_entries:
                if k in self.project:
                    self.t1_entries[k].delete(0, tk.END)
                    self.t1_entries[k].insert(0, str(self.project[k]))
            self.cb_material.set("Sỏi / cuội (Ks = 3,5 D84)" if self.project.get("bed_material")=="gravel" else "Cát (Ks = D84)")
            self.armored_var.set(self.project.get("armored", False))
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
            ent = ttk.Entry(dlg, width=22)
            ent.insert(0, str(self.project[key]))
            ent.grid(row=r, column=1, sticky=tk.W, padx=15, pady=8)
            dlg_entries[key] = ent

        def save():
            self._invalidate_results()
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
            row['ratiof'] = row['ratio2']  # Case 2 Kw uses approach V2 and y2 (§7.5.4).
            row['y2_af'] = row['y2'] / p['apc'] if p['apc'] > 0 else 0.0
            row['kw_pc'] = p['cp']['kw_pc']
            row['k2_pg'] = 1.0  # Nhóm cọc dùng K2 = 1 trong bộ tính hiện tại.
            row['y3max'] = 3.5 * row['apg']
            row['y3'] = p['cp']['y3_effective'] if p['cp']['cap_case']==1 else row['y3']
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
            'd50|D₅₀|mm|3|input', 'vc2|V_c|m/s|3|output', 'ratiof|V₂/V_c||2|output',
            'kw_lb|K_w||3|output', 'k1_foot|K₁||2|output', 'k2|K₂||2|output',
            'k3|K₃||2|output', 'footing|y_sfooting|m|2|output', 'note|Ghi chú||0|text']
        for row in records:
            row['k1_foot'] = row['k1_pc']
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
            'a_f: bề rộng bệ; K_s: D84 cho cát; 3,5D84 cho sỏi/cuội (HEC-18, 7.25).',
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
            ('FOOT-KS', 'Độ nhám được sử dụng trong bộ tính', r'$K_s=D_{84}\ (sand);\ K_s=3.5D_{84}\ (gravel)$'),
            ('FOOT-VF', 'Vận tốc dưới đỉnh bệ', r'$V_f=V_2\frac{\ln(10.93y_f/K_s+1)}{\ln(10.93y_2/K_s+1)}$'),
            ('FOOT-FRF', 'Froude tại đỉnh bệ', r'$Fr_f=V_f/\sqrt{g y_f}$'),
            ('FOOT-TOTAL', 'Tổng xói trụ lộ bệ', r'$y_s=y_{spier}+y_{sfooting}$')], common_defs + [
            'z_be: cao độ đáy bệ; z_tn: cao độ đáy sông tự nhiên; h₀,initial tính trước hạ thấp dài hạn và xói thu hẹp (m).',
            'h₀ dùng trong tính xói phức hợp đã cộng y_deg và y_sc; bảng kiểm tra bên dưới xuất cả h₀,initial và h₀.',
            'y₂: chiều sâu hiệu chỉnh cho bệ; h₂: cao độ đáy bệ so với đáy sau xói thân; h₁: cao độ đỉnh bệ (m).',
            'V₂: vận tốc hiệu chỉnh; V_f: vận tốc dưới đỉnh bệ (m/s); Fr₂ và Fr_f là hai hệ số khác nhau.',
            'D₈₄: đường kính hạt mà 84% hạt nhỏ hơn (mm); D₈₄ hiệu dụng = 2D₅₀ nếu đầu vào D₈₄ ≤ 0.',
            'Ks lấy từ D84 đo ở vật liệu đáy: cát D84; sỏi/cuội 3,5D84.',
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
            ('d50', 'D₅₀ — đường kính hạt', 'mm', ''), ('d84', 'D₈₄ — đường kính hạt hiệu dụng', 'mm', 'Giá trị đo từ cấp phối'),
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

    def _load_template_exporter(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).with_name('report_template_export.py')
        spec = importlib.util.spec_from_file_location('ttxoi_template_export', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def export_excel_report(self, file_path):
        self._load_template_exporter().export_excel(self, file_path)

    def export_word_report(self, file_path):
        self._load_template_exporter().export_word(self, file_path)

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
