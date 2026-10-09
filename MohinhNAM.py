"""
PHẦN MỀM THỦY VĂN NAM DESKTOP - CHẠY TRỰC TIẾP TRÊN MÁY TÍNH
NAM khái niệm: không tuyết/tưới; điều tiết tuyến tính CK_12 cố định.
Không khẳng định tương đương bộ giải MIKE NAM của DHI.
Cài đặt: python -m pip install numpy pandas scipy matplotlib
P/PET tổng mm mỗi bước; Q trung bình bước m³/s. Hiệu chỉnh cần kiểm định độc lập.
"""

import os
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure
import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

# ==============================================================================
# 1. THUẬT TOÁN MÔ HÌNH BỂ CHỨA NAM VÀ ĐÁNH GIÁ CHỈ SỐ NASH
# ==============================================================================

PARAM_KEYS = [
    "U_max",
    "L_max",
    "CQOF",
    "CK_12",
    "TOF",
    "TIF",
    "TG",
    "CK_IF",
    "CK_BF",
]

PARAM_BOUNDS = [
    (5.0, 35.0),  # U_max (mm): Dung tích trữ tầng mặt
    (40.0, 350.0),  # L_max (mm): Dung tích trữ tầng rễ
    (0.05, 0.95),  # CQOF (-): Hệ số dòng tràn bề mặt
    (2.0, 48.0),  # CK_12 (h): Thời gian điều tiết dòng tràn
    (0.0, 0.7),  # TOF (-): Ngưỡng ẩm sinh dòng tràn
    (0.0, 0.7),  # TIF (-): Ngưỡng ẩm sinh dòng sát mặt
    (0.0, 0.7),  # TG (-): Ngưỡng ẩm thấm xuống ngầm
    (10.0, 300.0),  # CK_IF (h): Thời gian điều tiết dòng sát mặt
    (200.0, 3000.0),  # CK_BF (h): Thời gian điều tiết dòng ngầm
]


def finite_number(value, name, positive=False):
    try:
        value=float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name}: cần nhập số.') from None
    if not np.isfinite(value) or (positive and value<=0):
        raise ValueError(f'{name}: cần số hữu hạn'+(' lớn hơn 0.' if positive else '.'))
    return value


def validate_data(df, dt_hours):
    """P và PET là tổng mm trong mỗi bước, không phải mm/giờ."""
    df=df.copy()
    if len(df)<2:
        raise ValueError('Chuỗi cần ít nhất 2 bước thời gian.')
    for col in ['Mua_mm', 'BocHoi_mm']:
        if col not in df:
            raise ValueError(f'Thiếu cột {col}.')
        df[col]=pd.to_numeric(df[col],errors='raise')
        if not np.all(np.isfinite(df[col])) or np.any(df[col]<0):
            raise ValueError(f'{col}: không được âm, thiếu hoặc vô hạn; không tự điền mưa thiếu bằng 0.')
    if 'Q_ThucDo_m3s' not in df:
        df['Q_ThucDo_m3s']=np.nan
    df['Q_ThucDo_m3s']=pd.to_numeric(df['Q_ThucDo_m3s'],errors='raise')
    q=df['Q_ThucDo_m3s'].to_numpy()
    if np.any(np.isinf(q)) or np.any(q[np.isfinite(q)]<0):
        raise ValueError('Lưu lượng thực đo không được âm hoặc vô hạn; có thể để trống.')
    if 'ThoiGian' in df:
        times=pd.to_datetime(df['ThoiGian'],errors='raise')
        if times.isna().any() or not np.allclose(np.diff(times.astype('int64'))/3.6e12,dt_hours,rtol=0,atol=1e-6):
            raise ValueError('ThoiGian phải tăng đều đúng bước tính; không chấp nhận ngày thiếu/trùng.')
    return df


def route_linear(storage, inflow, dt, k):
    """Bể tuyến tính: trữ lượng mm, inflow mm/giờ, out tổng mm trong dt."""
    e=np.exp(-dt/k)
    new=storage*e+inflow*k*(-np.expm1(-dt/k))
    out=storage+inflow*dt-new
    return max(new,0.), max(out,0.)


def route_cascade(storage, inflow, dt, k):
    """Nghiệm chính xác hai bể tuyến tính nối tiếp, đầu vào đều trong dt."""
    s1,s2=storage
    e=np.exp(-dt/k);one=-np.expm1(-dt/k)
    a=s1*e+inflow*k*one
    b=s2*e+s1*(dt/k)*e+inflow*(k*one-dt*e)
    out=s1+s2+inflow*dt-a-b
    return (max(a,0.),max(b,0.)),max(out,0.)


def run_nam(params, area_km2, rain, pet, dt_hours, initial=None, max_substep_hours=1.):
    """NAM khái niệm không tuyết/tưới; CK_12 tuyến tính cố định.

    Không tuyên bố tương đương bộ giải MIKE NAM. P/PET là mm mỗi bước;
    Q là lưu lượng TRUNG BÌNH bước. Điều tiết bảo toàn thể tích với hai bể
    nối tiếp cho dòng tràn/sát mặt và một bể dòng ngầm. Chia bước nội bộ
    ≤1 giờ; không nội suy trận mưa chưa quan trắc trong bước lớn.
    """
    p={k:finite_number(params[k],k) for k in PARAM_KEYS}
    for k in ['U_max','L_max','CK_12','CK_IF','CK_BF']:
        if p[k]<=0:raise ValueError(f'{k} phải lớn hơn 0.')
    if not 0<=p['CQOF']<=1 or any(not 0<=p[k]<1 for k in ['TOF','TIF','TG']):
        raise ValueError('CQOF thuộc [0;1]; TOF, TIF, TG thuộc [0;1).')
    area=finite_number(area_km2,'Diện tích',True);dt=finite_number(dt_hours,'Bước tính',True)
    sub=finite_number(max_substep_hours,'Bước nội bộ',True)
    rain=np.asarray(rain,dtype=float);pet=np.asarray(pet,dtype=float)
    if rain.ndim!=1 or pet.shape!=rain.shape or not len(rain) or not np.all(np.isfinite(rain)) or not np.all(np.isfinite(pet)) or np.any(rain<0) or np.any(pet<0):
        raise ValueError('Mưa/PET phải là hai chuỗi một chiều cùng độ dài, hữu hạn và không âm.')
    init={'U_fraction':.2,'L_fraction':.5,'Q_base_m3s':0.}
    if initial:init.update(initial)
    init={k:finite_number(v,k) for k,v in init.items()}
    if any(not 0<=init[k]<=1 for k in ['U_fraction','L_fraction']) or init['Q_base_m3s']<0:
        raise ValueError('Độ đầy ban đầu thuộc [0;1]; dòng ngầm ban đầu không âm.')
    U=init['U_fraction']*p['U_max'];L=init['L_fraction']*p['L_max']
    surf=(0.,0.);inter=(0.,0.)
    base=init['Q_base_m3s']*3.6/area*p['CK_BF']
    initial_storage=U+L+base
    n=len(rain);components=np.zeros((n,3));evap=np.zeros(n);stores=np.zeros(n);residual=np.zeros(n)
    steps=int(np.ceil(dt/sub));h=dt/steps
    for t in range(n):
        before=U+L+sum(surf)+sum(inter)+base
        for _ in range(steps):
            U+=rain[t]/steps
            eu=min(U,pet[t]/steps);U-=eu
            el=min(L,(pet[t]/steps-eu)*L/p['L_max']);L-=el
            evap[t]+=eu+el
            excess=max(U-p['U_max'],0.);U-=excess
            moisture=L/p['L_max']
            threshold=lambda x:max((moisture-x)/(1-x),0.)
            of=p['CQOF']*threshold(p['TOF'])*excess
            # CK_IF sinh dòng sát mặt: U/CK_IF nhân hệ số ngưỡng ẩm.
            # Tích phân suy giảm U để không rút quá lượng nước có trong bể.
            inf_flow=U*(-np.expm1(-threshold(p['TIF'])*h/p['CK_IF']));U-=inf_flow
            infiltration=excess-of;recharge=infiltration*threshold(p['TG'])
            L+=infiltration-recharge
            # Bể rễ đầy: phần thấm vượt sức chứa bổ cập ngầm, không mất nước.
            spill=max(L-p['L_max'],0.);L-=spill;recharge+=spill
            surf,qo=route_cascade(surf,of/h,h,p['CK_12'])
            inter,qi=route_cascade(inter,inf_flow/h,h,p['CK_12'])
            base,qb=route_linear(base,recharge/h,h,p['CK_BF'])
            components[t]+=np.array([qo,qi,qb])
        stores[t]=U+L+sum(surf)+sum(inter)+base
        residual[t]=before+rain[t]-evap[t]-components[t].sum()-stores[t]
    conv=area/(3.6*dt)
    return dict(Q_sim=components.sum(axis=1)*conv,Q_surf=components[:,0]*conv,
                Q_inter=components[:,1]*conv,Q_base=components[:,2]*conv,
                Evap_actual_mm=evap,Storage_mm=stores,Balance_error_mm=residual,
                Initial_storage_mm=initial_storage,Initial_state=init,
                Final_state=dict(U_mm=U,L_mm=L,surface_mm=surf,interflow_mm=inter,base_mm=base))


def compute_nse(obs,sim):
    obs=np.asarray(obs,dtype=float);sim=np.asarray(sim,dtype=float)
    if obs.shape!=sim.shape:raise ValueError('Hai chuỗi đánh giá phải cùng kích thước.')
    # Thiếu quan trắc được bỏ; mô phỏng không hữu hạn tại điểm đo là lỗi.
    valid=np.isfinite(obs)
    if np.any(~np.isfinite(sim[valid])):return np.nan
    o,s=obs[valid],sim[valid]
    denominator=np.sum((o-o.mean())**2) if len(o)>=2 else 0.
    return float(1-np.sum((o-s)**2)/denominator) if denominator>0 else np.nan


def compute_metrics(obs,sim):
    obs=np.asarray(obs,dtype=float);sim=np.asarray(sim,dtype=float)
    valid=np.isfinite(obs)&np.isfinite(sim);o=obs[valid];s=sim[valid]
    # PBIAS theo quy ước tổng (đo - mô phỏng)/tổng đo: dương = thiếu nước.
    return dict(nse=compute_nse(obs,sim),pbias=100*np.sum(o-s)/np.sum(o) if len(o) and np.sum(o)>0 else np.nan,
                observed_peak=float(o.max()) if len(o) else np.nan,
                simulated_peak=float(s.max()) if len(s) else np.nan,n=int(len(o)))


# ==============================================================================
# 2. GIAO DIỆN PHẦN MỀM MÁY TÍNH (TKINTER DESKTOP APP)
# ==============================================================================


class NAMDesktopApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(
            "Phần mềm Thủy văn NAM - Tự động Hiệu chỉnh Thông số (Nash-Sutcliffe)"
        )
        self.root.geometry("1280x900")
        self.root.minsize(1050, 850)

        # Dữ liệu nội bộ
        self.df_data = None
        self.best_params = {
            "U_max": 15.0,
            "L_max": 100.0,
            "CQOF": 0.50,
            "CK_12": 15.0,
            "TOF": 0.20,
            "TIF": 0.20,
            "TG": 0.30,
            "CK_IF": 50.0,
            "CK_BF": 1000.0,
        }
        self.current_sim = None

        self._setup_style()
        self._build_ui()
        self._busy=False;self._worker_queue=queue.Queue();self._result_signature=None
        self._update_parameter_display()
        self.root.after(300,self._watch)

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=4)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))

    def _build_ui(self):
        # Khung chính chia 2 cột: Trái (Điều khiển & Tham số), Phải (Đồ thị)
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- KHUNG BÊN TRÁI: ĐIỀU KHIỂN ---
        left_outer=ttk.Frame(main_paned,width=390)
        main_paned.add(left_outer,weight=0)
        controls=tk.Canvas(left_outer,width=390,highlightthickness=0)
        scroll=ttk.Scrollbar(left_outer,orient='vertical',command=controls.yview)
        controls.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');controls.pack(side='left',fill='both',expand=True)
        left_frame=ttk.Frame(controls,padding=10)
        item=controls.create_window((0,0),window=left_frame,anchor='nw')
        left_frame.bind('<Configure>',lambda event:controls.configure(scrollregion=controls.bbox('all')))
        controls.bind('<Configure>',lambda event:controls.itemconfigure(item,width=event.width))

        # 1. Thông tin lưu vực
        lbl_sec1 = ttk.Label(
            left_frame, text="1. Thông số Lưu vực", style="Header.TLabel"
        )
        lbl_sec1.pack(anchor="w", pady=(0, 5))

        f_basin = ttk.Frame(left_frame)
        f_basin.pack(fill=tk.X, pady=2)

        ttk.Label(f_basin, text="Diện tích F (km²):").grid(
            row=0, column=0, sticky="w", padx=3, pady=3
        )
        self.ent_area = ttk.Entry(f_basin, width=10)
        self.ent_area.insert(0, "150.0")
        self.ent_area.grid(row=0, column=1, sticky="w", padx=3, pady=3)

        ttk.Label(f_basin, text="Bước tính Δt (giờ):").grid(
            row=1, column=0, sticky="w", padx=3, pady=3
        )
        self.ent_dt = ttk.Entry(f_basin, width=10)
        self.ent_dt.insert(0, "1.0")
        self.ent_dt.grid(row=1, column=1, sticky="w", padx=3, pady=3)

        self.setting_entries=[self.ent_area,self.ent_dt]
        for row,(attr,label,default) in enumerate([
            ('ent_warm','Khởi động (giờ):','0'),('ent_split','Hiệu chỉnh (% chuỗi sau khởi động):','70'),
            ('ent_u','Độ đầy bể mặt đầu (0–1):','0.2'),('ent_l','Độ đầy bể rễ đầu (0–1):','0.5'),
            ('ent_base','Dòng ngầm ban đầu (m³/s):','0')],2):
            ttk.Label(f_basin,text=label).grid(row=row,column=0,sticky='w',padx=3,pady=2)
            entry=ttk.Entry(f_basin,width=10);entry.insert(0,default);entry.grid(row=row,column=1,padx=3)
            setattr(self,attr,entry);self.setting_entries.append(entry)
        ttk.Label(left_frame,text='NAM khái niệm: CK_12 cố định; không tuyết/tưới.\nMưa/PET: tổng mm mỗi bước. Q thực đo có thể để trống.\nCSV: Mua_mm; BocHoi_mm; Q_ThucDo_m3s (tùy chọn).\nThoiGian tùy chọn để kiểm tra bước giờ.',wraplength=350).pack(anchor='w',pady=4)
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # 2. Nạp dữ liệu
        lbl_sec2 = ttk.Label(
            left_frame, text="2. Mưa, bốc hơi và lưu lượng", style="Header.TLabel"
        )
        lbl_sec2.pack(anchor="w", pady=(0, 5))

        f_data_btn = ttk.Frame(left_frame)
        f_data_btn.pack(fill=tk.X, pady=2)

        btn_load_csv = ttk.Button(
            f_data_btn, text="📂 Nạp file CSV", command=self._on_load_csv
        )
        btn_load_csv.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        btn_sample = ttk.Button(
            f_data_btn, text="Dữ liệu giả lập", command=self._load_synthetic_data
        )
        btn_sample.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.lbl_data_status = ttk.Label(
            left_frame, text="Chưa nạp dữ liệu", foreground="gray"
        )
        self.lbl_data_status.pack(anchor="w", pady=4)

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # 3. Tự động dò thông số (Auto-Calibrate)
        lbl_sec3 = ttk.Label(
            left_frame,
            text="3. Hiệu chỉnh theo Nash–Sutcliffe",
            style="Header.TLabel",
        )
        lbl_sec3.pack(anchor="w", pady=(0, 5))

        f_iter = ttk.Frame(left_frame)
        f_iter.pack(fill=tk.X, pady=2)
        ttk.Label(f_iter, text="Số thế hệ tối ưu:").pack(side=tk.LEFT)
        self.ent_maxiter = ttk.Entry(f_iter, width=6)
        self.ent_maxiter.insert(0, "20")
        self.ent_maxiter.pack(side=tk.LEFT, padx=6)
        runs_row=ttk.Frame(left_frame);runs_row.pack(fill=tk.X,pady=2)
        ttk.Label(runs_row,text='Số lần chạy hiệu chỉnh:').pack(side=tk.LEFT)
        self.ent_runs=ttk.Entry(runs_row,width=6);self.ent_runs.insert(0,'3');self.ent_runs.pack(side=tk.LEFT,padx=6)
        ttk.Label(left_frame,text='Mỗi lần tự tìm thông số; giữ NSE cao nhất.\nSố thế hệ × số lần chạy quyết định thời gian tìm kiếm.',wraplength=350).pack(anchor='w')


        self.btn_calibrate = ttk.Button(
            left_frame,
            text="🚀 BẮT ĐẦU DÒ THÔNG SỐ (MAX NSE)",
            style="Accent.TButton",
            command=self._start_calibration_thread,
        )
        self.btn_calibrate.pack(fill=tk.X, pady=6)

        self.progress_bar = ttk.Progressbar(left_frame, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, pady=2)

        self.lbl_calib_status = ttk.Label(
            left_frame, text="Sẵn sàng", foreground="#007ACC", wraplength=350
        )
        self.lbl_calib_status.pack(anchor="w", pady=2)

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # 4. Hiển thị thông số mô hình
        lbl_sec4 = ttk.Label(
            left_frame, text="4. Tham số NAM hiện tại", style="Header.TLabel"
        )
        lbl_sec4.pack(anchor="w", pady=(0, 5))

        self.param_labels = {}
        f_params = ttk.Frame(left_frame)
        f_params.pack(fill=tk.X)

        for i, key in enumerate(PARAM_KEYS):
            row = i // 2
            col = (i % 2) * 2
            ttk.Label(f_params, text=f"{key}:", font=("Segoe UI", 8)).grid(
                row=row, column=col, sticky="w", padx=2, pady=1
            )
            lbl_v = ttk.Label(
                f_params,
                text="--",
                font=("Segoe UI", 8, "bold"),
                foreground="#333",
            )
            lbl_v.grid(row=row, column=col + 1, sticky="w", padx=2, pady=1)
            self.param_labels[key] = lbl_v

        ttk.Button(left_frame,text='Chỉnh thông số mô hình',command=self._edit_parameters).pack(fill=tk.X,pady=2)
        ttk.Button(left_frame,text='Chạy mô phỏng',command=self._run_manual).pack(fill=tk.X,pady=2)

        # 5. Xuất kết quả
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )
        btn_export = ttk.Button(
            left_frame,
            text="💾 Xuất kết quả ra file CSV",
            command=self._export_csv,
        )
        btn_export.pack(fill=tk.X, pady=4)

        # --- KHUNG BÊN PHẢI: ĐỒ THỊ MATPLOTLIB ---
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)

        # Thanh hiển thị chỉ số thống kê (NSE, Qmax, PBIAS)
        metrics_bar = ttk.Frame(right_frame, padding=5)
        metrics_bar.pack(fill=tk.X)

        self.lbl_metric_nse = ttk.Label(
            metrics_bar,
            text="Hệ số NASH (NSE): --",
            font=("Segoe UI", 9, "bold"),
            foreground="#D9534F",
        )
        self.lbl_metric_nse.pack(anchor="w", padx=5)

        self.lbl_metric_peak = ttk.Label(
            metrics_bar,
            text="Đỉnh Qmax (Đo / Mô phỏng): --",
            font=("Segoe UI", 10),
        )
        self.lbl_metric_peak.pack(anchor="w", padx=5)

        self.lbl_metric_pbias = ttk.Label(
            metrics_bar, text="Sai số thể tích (PBIAS): --", font=("Segoe UI", 10)
        )
        self.lbl_metric_pbias.pack(anchor="w", padx=5)

        # Nhúng Matplotlib Canvas
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax_rain = self.fig.add_subplot(2, 1, 1)
        self.ax_flow = self.fig.add_subplot(2, 1, 2, sharex=self.ax_rain)
        self.fig.subplots_adjust(hspace=0.15)

        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, right_frame)
        toolbar.update()
        toolbar.pack(fill=tk.X)

    # ==========================================================================
    # CÁC HÀM XỬ LÝ SỰ KIỆN VÀ DỮ LIỆU
    # ==========================================================================

    def _load_synthetic_data(self):
        """Sinh chuỗi mưa rào mẫu và lưu lượng thực đo giả lập 72 giờ."""
        n_hours = 72
        rain = np.zeros(n_hours)
        # Vũ biểu mưa rào cường độ lớn từ giờ thứ 8 đến 23
        rain[8:24] = [
            4,
            12,
            25,
            46,
            58,
            38,
            22,
            14,
            8,
            4,
            2,
            1,
            0.5,
            0.5,
            0.2,
            0.1,
        ]
        pet = np.full(n_hours, 0.2)

        # Tạo chuỗi lưu lượng giả định có nhiễu thực tế
        target_p = {
            "U_max": 18.0,
            "L_max": 120.0,
            "CQOF": 0.65,
            "CK_12": 10.0,
            "TOF": 0.2,
            "TIF": 0.15,
            "TG": 0.25,
            "CK_IF": 40.0,
            "CK_BF": 800.0,
        }
        res_true = run_nam(target_p, 150.0, rain, pet, 1.0)["Q_sim"]
        rng=np.random.default_rng(42)
        q_obs=np.maximum(0,res_true+rng.normal(0,res_true*.08,n_hours))
        self.ent_area.delete(0,'end');self.ent_area.insert(0,'150')
        self.ent_dt.delete(0,'end');self.ent_dt.insert(0,'1')

        self.df_data = pd.DataFrame(
            {"Mua_mm": rain, "BocHoi_mm": pet, "Q_ThucDo_m3s": q_obs}
        )
        self.lbl_data_status.config(
            text="DỮ LIỆU GIẢ LẬP (72 giờ), không phải quan trắc", foreground="green"
        )
        self._update_parameter_display()
        self._recompute_and_plot()

    def _update_parameter_display(self):
        for k, v in self.best_params.items():
            if k in self.param_labels:
                self.param_labels[k].config(text=f"{v:.2f}")

    def _settings(self):
        area=finite_number(self.ent_area.get(),'Diện tích',True)
        dt=finite_number(self.ent_dt.get(),'Bước tính',True)
        warm=finite_number(self.ent_warm.get(),'Khởi động')
        split=finite_number(self.ent_split.get(),'Tỷ lệ hiệu chỉnh')
        initial=dict(U_fraction=finite_number(self.ent_u.get(),'Độ đầy bể mặt'),L_fraction=finite_number(self.ent_l.get(),'Độ đầy bể rễ'),Q_base_m3s=finite_number(self.ent_base.get(),'Dòng ngầm đầu'))
        if warm<0 or not 0<split<=100 or any(not 0<=initial[k]<=1 for k in ['U_fraction','L_fraction']) or initial['Q_base_m3s']<0:
            raise ValueError('Khởi động ≥0 giờ; hiệu chỉnh trong (0;100]%; độ đầy trong [0;1]; dòng ngầm ≥0.')
        return area,dt,int(np.ceil(warm/dt)),split/100,initial

    def _signature(self):
        return tuple(e.get() for e in self.setting_entries)+(self.ent_maxiter.get(),self.ent_runs.get())+tuple(self.best_params.items())+(id(self.df_data),)

    def _watch(self):
        if self.current_sim is not None and self._result_signature!=self._signature():
            self.current_sim=None
            self.lbl_calib_status.config(text='Đầu vào đã đổi: chạy mô phỏng lại trước khi xuất.')
            self.ax_flow.clear();self.canvas.draw()
            for label in [self.lbl_metric_nse,self.lbl_metric_peak,self.lbl_metric_pbias]:label.config(text='Cần tính lại')
        self.root.after(300,self._watch)

    def _run_manual(self):
        self._recompute_and_plot()

    def _edit_parameters(self):
        window=tk.Toplevel(self.root);window.title('Thông số mô hình và đơn vị')
        entries={}
        descriptions=['Dung tích mặt (mm)','Dung tích rễ (mm)','Hệ số dòng tràn (0–1)',
                      'Điều tiết tràn/sát mặt (giờ)','Ngưỡng dòng tràn (0–<1)',
                      'Ngưỡng sát mặt (0–<1)','Ngưỡng bổ cập ngầm (0–<1)',
                      'Sinh dòng sát mặt (giờ)','Điều tiết ngầm (giờ)']
        for i,(key,desc) in enumerate(zip(PARAM_KEYS,descriptions)):
            ttk.Label(window,text=key+' — '+desc).grid(row=i,column=0,sticky='w',padx=8,pady=3)
            e=ttk.Entry(window);e.insert(0,str(self.best_params[key]));e.grid(row=i,column=1,padx=8);entries[key]=e
        def save():
            try:
                params={k:finite_number(e.get(),k) for k,e in entries.items()}
                run_nam(params,1.,[0.],[0.],1.)
                self.best_params=params;self._update_parameter_display();window.destroy();self._recompute_and_plot()
            except Exception as exc:messagebox.showerror('Thông số',str(exc),parent=window)
        ttk.Button(window,text='Áp dụng và mô phỏng',command=save).grid(row=9,column=0,columnspan=2,pady=8)
        window.transient(self.root);window.grab_set()

    def _on_load_csv(self):
        path=filedialog.askopenfilename(title='Mưa/PET tổng mm mỗi bước; Q thực đo tùy chọn',filetypes=[('CSV','*.csv')])
        if not path:return
        try:
            _,dt,_,_,_=self._settings()
            df=validate_data(pd.read_csv(path,sep=None,engine='python',encoding='utf-8-sig'),dt)
            self.df_data=df;self.current_sim=None
            self.lbl_data_status.config(text=f'{os.path.basename(path)}: {len(df)} bước',foreground='blue')
            self._recompute_and_plot()
        except Exception as exc:messagebox.showerror('Nạp dữ liệu',str(exc))

    def _start_calibration_thread(self):
        if self._busy:return
        if self.df_data is None:
            messagebox.showwarning('Dữ liệu','Nạp mưa và bốc hơi trước khi hiệu chỉnh.');return
        try:
            area,dt,warm,split,initial=self._settings()
            df=validate_data(self.df_data,dt)
            maxiter=int(self.ent_maxiter.get())
            runs=int(self.ent_runs.get())
            if maxiter<=0 or runs<=0:raise ValueError('Số thế hệ và số lần chạy phải là số nguyên dương.')
            end=warm+int((len(df)-warm)*split)
            obs=df['Q_ThucDo_m3s'].to_numpy()[warm:end]
            if np.count_nonzero(np.isfinite(obs))<3 or not np.isfinite(compute_nse(obs,np.zeros(len(obs)))):
                raise ValueError('Sau khởi động, phần hiệu chỉnh cần ≥3 Q thực đo và phương sai khác 0.')
            snapshot=(self._signature(),df.copy(deep=True),area,dt,warm,end,initial,maxiter,self.best_params.copy(),runs)
        except Exception as exc:messagebox.showerror('Hiệu chỉnh',str(exc));return
        self._busy=True;self.btn_calibrate.config(state=tk.DISABLED);self.progress_bar.start(10)
        self.lbl_calib_status.config(text='Đang hiệu chỉnh; dữ liệu đầu vào đã được chụp riêng.',foreground='#D9534F')
        threading.Thread(target=self._run_optimization_worker,args=(snapshot,),daemon=True).start()
        self.root.after(100,self._poll_worker)

    def _run_optimization_worker(self,snapshot):
        try:
            signature,df,area,dt,warm,end,initial,maxiter=snapshot[:8]
            current=snapshot[8] if len(snapshot)>8 else dict(zip(PARAM_KEYS,[15,100,.5,15,.2,.2,.3,50,1000]))
            runs=snapshot[9] if len(snapshot)>9 else 1
            rain=df['Mua_mm'].to_numpy();pet=df['BocHoi_mm'].to_numpy();obs=df['Q_ThucDo_m3s'].to_numpy()
            def score(params):
                sim=run_nam(params,area,rain[:end],pet[:end],dt,initial)['Q_sim']
                nse=compute_nse(obs[warm:end],sim[warm:end])
                if not np.isfinite(nse):raise ValueError('NSE không xác định; kiểm tra chuỗi thực đo và giai đoạn đánh giá.')
                return nse
            best_params=current.copy();best_nse=score(best_params)
            def objective(x):
                nonlocal best_params,best_nse
                params=dict(zip(PARAM_KEYS,x));nse=score(params)
                if nse>best_nse:best_nse=nse;best_params=params.copy()
                return 1-nse
            converged=0
            for run in range(runs):
                generation=0
                self._worker_queue.put(('progress',f'Lần {run+1}/{runs}: NSE tốt nhất = {best_nse:.4f}'))
                def callback(xk,convergence):
                    nonlocal generation
                    generation+=1
                    self._worker_queue.put(('progress',f'Lần {run+1}/{runs}, thế hệ {generation}/{maxiter}: NSE tốt nhất = {best_nse:.4f}'))
                candidate=np.array([best_params[k] for k in PARAM_KEYS])
                candidate=np.clip(candidate,np.array(PARAM_BOUNDS)[:,0],np.array(PARAM_BOUNDS)[:,1])
                result=differential_evolution(objective,bounds=PARAM_BOUNDS,maxiter=maxiter,popsize=10,tol=.005,
                    seed=42+run,polish=False,x0=candidate,callback=callback)
                converged+=int(result.success)
            # Không bao giờ thay bộ hiện tại bằng bộ có NSE thấp hơn.
            self._worker_queue.put(('done',signature,best_params,float(best_nse),converged==runs,
                f'Đã chạy {runs} lần; {converged} lần đạt điều kiện hội tụ, {runs-converged} lần hết giới hạn thế hệ.'))
        except Exception as exc:self._worker_queue.put(('error',str(exc)))

    def _poll_worker(self):
        try:
            result=self._worker_queue.get_nowait()
            while result[0]=='progress':
                try:result=self._worker_queue.get_nowait()
                except queue.Empty:break
        except queue.Empty:self.root.after(100,self._poll_worker);return
        if result[0]=='progress':
            self.lbl_calib_status.config(text=result[1]);self.root.after(100,self._poll_worker);return
        self._busy=False;self.progress_bar.stop();self.btn_calibrate.config(state=tk.NORMAL)
        if result[0]=='error':
            self.lbl_calib_status.config(text='Hiệu chỉnh thất bại.')
            messagebox.showerror('Hiệu chỉnh',result[1]);return
        _,signature,params,nse,success,reason=result
        if signature!=self._signature():
            self.lbl_calib_status.config(text='Đầu vào đã thay đổi: bỏ kết quả hiệu chỉnh cũ.');return
        self.best_params=params;self._update_parameter_display();self._recompute_and_plot()
        self.lbl_calib_status.config(text=f'NSE hiệu chỉnh = {nse:.3f}; '+reason,foreground='green' if success else '#b05b00')

    def _recompute_and_plot(self):
        if self.df_data is None:return
        self.current_sim=None
        try:
            area,dt,warm,split,initial=self._settings()
            df=validate_data(self.df_data,dt)
            if warm>=len(df):raise ValueError('Thời gian khởi động phải ngắn hơn chuỗi dữ liệu.')
            rain=df['Mua_mm'].to_numpy();pet=df['BocHoi_mm'].to_numpy();q_obs=df['Q_ThucDo_m3s'].to_numpy()
            res=run_nam(self.best_params,area,rain,pet,dt,initial)
        except Exception as exc:messagebox.showerror('Mô phỏng',str(exc));return
        self.current_sim=res;self._result_signature=self._signature()
        self._run_settings=dict(area=area,dt=dt,warm=warm,split=split,initial=initial,params=self.best_params.copy())
        q_sim=res['Q_sim'];end=warm+int((len(df)-warm)*split)
        train=compute_metrics(q_obs[warm:end],q_sim[warm:end]);validation=compute_metrics(q_obs[end:],q_sim[end:])
        metric=compute_metrics(q_obs[warm:],q_sim[warm:])
        fmt=lambda v:f'{v:.3f}' if np.isfinite(v) else 'không xác định'
        self.lbl_metric_nse.config(text=f'NSE hiệu chỉnh: {fmt(train["nse"])} | kiểm định: {fmt(validation["nse"])}')
        self.lbl_metric_peak.config(text=f'Đỉnh Q đo/mô phỏng: {fmt(metric["observed_peak"])}/{fmt(metric["simulated_peak"])} m³/s')
        self.lbl_metric_pbias.config(text=f'PBIAS (đo−mô phỏng): {fmt(metric["pbias"])}%')
        self.lbl_calib_status.config(text=f'Sai số cân bằng lớn nhất: {np.max(np.abs(res["Balance_error_mm"])):.2e} mm; loại {warm} bước khởi động.')
        self.ax_rain.clear();self.ax_flow.clear()
        time=np.arange(len(rain))*dt
        self.ax_rain.bar(time,rain,width=dt*.8,color='#1f77b4',label='Mưa tổng mỗi bước (mm)')
        self.ax_rain.set_ylabel('Mưa (mm)');self.ax_rain.set_ylim(max(10.,rain.max()*1.3),0);self.ax_rain.legend(fontsize=8)
        self.ax_rain.set_title('MƯA – DÒNG CHẢY NAM KHÁI NIỆM (KHÔNG TUYẾT; ĐIỀU TIẾT TUYẾN TÍNH)',fontsize=10)
        self.ax_flow.plot(time,q_obs,'k--',label='Lưu lượng thực đo')
        self.ax_flow.plot(time,q_sim,'r-',label='Lưu lượng mô phỏng trung bình bước')
        self.ax_flow.stackplot(time,res['Q_base'],res['Q_inter'],res['Q_surf'],labels=['Dòng ngầm','Dòng sát mặt','Dòng tràn'],alpha=.25)
        if warm:self.ax_flow.axvspan(0,warm*dt,color='gray',alpha=.2,label='Khởi động (không đánh giá)')
        if end<len(df):self.ax_flow.axvline(end*dt,color='navy',linestyle=':',label='Bắt đầu kiểm định')
        self.ax_flow.set(xlabel='Thời gian (giờ)',ylabel='Lưu lượng (m³/s)',xlim=(0,max(dt,time[-1])))
        self.ax_flow.set_ylim(bottom=0);self.ax_flow.grid(alpha=.3);self.ax_flow.legend(fontsize=8)
        self.fig.tight_layout();self.canvas.draw()

    def _export_csv(self):
        if self.df_data is None:return
        # Tính lại từ đầu vào hiện tại, tránh xuất kết quả cũ với bước giờ mới.
        self._recompute_and_plot()
        if self.current_sim is None:return
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        try:
            out=self.df_data.copy();res=self.current_sim;settings=self._run_settings;dt=settings['dt']
            out['Gio']=np.arange(len(out))*dt
            for column,key in [('Q_MoPhong_m3s','Q_sim'),('Q_TranMat_m3s','Q_surf'),('Q_SatMat_m3s','Q_inter'),('Q_Ngam_m3s','Q_base'),('BocHoiThuc_mm','Evap_actual_mm'),('TruLuong_mm','Storage_mm'),('SaiSoCanBang_mm','Balance_error_mm')]:out[column]=res[key]
            end=settings['warm']+int((len(out)-settings['warm'])*settings['split'])
            out['GiaiDoan']=['Khoi_dong' if i<settings['warm'] else 'Hieu_chinh' if i<end else 'Kiem_dinh' for i in range(len(out))]
            out['DienTich_km2']=settings['area'];out['BuocGio']=dt
            out['TruLuongDau_mm']=res['Initial_storage_mm']
            for key,value in settings['params'].items():out[key]=value
            for key,value in settings['initial'].items():out['BanDau_'+key]=value
            out.to_csv(path,index=False,encoding='utf-8-sig')
            messagebox.showinfo('Xuất kết quả','Đã xuất lưu lượng, cân bằng nước, giai đoạn đánh giá và thông số.')
        except Exception as exc:messagebox.showerror('Xuất kết quả',str(exc))


# ==============================================================================
# ĐIỂM BẮT ĐẦU CHƯƠNG TRÌNH
# ==============================================================================
if __name__ == "__main__":
    app_root = tk.Tk()
    app = NAMDesktopApp(app_root)
    app_root.mainloop()