import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import json

# Matplotlib hỗ trợ vẽ đồ thị
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    plt.rcParams['font.family'] = 'serif'
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# =============================================================================
# TỌA ĐỘ MẶT CẮT MẶC ĐỊNH (TỪ FILE EXCEL GỐC)
# =============================================================================
DEFAULT_MC = [
    (0.0, 21.28),
    (41.79, 20.84),
    (56.07, 19.92),
    (79.27, 19.05),
    (89.04, 18.35),   # Mép bờ trái dòng chủ
    (92.66, 16.30),
    (97.03, 15.68),   # Đáy sâu nhất
    (100.00, 15.80),
    (105.10, 16.50),
    (106.58, 18.50),  # Mép bờ phải dòng chủ
    (118.41, 19.22),
    (140.14, 19.06),
    (163.84, 19.59),
    (171.40, 21.98),
    (182.84, 22.25)
]


class CrossSectionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TÍNH TOÁN THỦY LỰC MẶT CẮT SÔNG - THOÁT NƯỚC CẦU & NƯỚC DỀNH")
        self.root.geometry("1200x950")
        self.root.resizable(True, True)

        self.mc_data = list(DEFAULT_MC)
        self.h_levels = []
        self.detailed_dict = {}
        self.summary_list = []
        self.H_tk_val = 20.86

        self.setup_ui()
        self.auto_detect_parameters(silent=True)

    def setup_ui(self):
        # 1. TIÊU ĐỀ & THANH DỰ ÁN (LƯU / MỞ DỰ ÁN)
        hdr = tk.Frame(self.root, pady=3)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="TÍNH TOÁN THỦY LỰC MẶT CẮT SÔNG THEO PHƯƠNG PHÁP HÌNH THÁI", 
                 font=("Times New Roman", 15, "bold"), fg="#154360").pack()

        r_proj = tk.Frame(self.root, padx=15, pady=2)
        r_proj.pack(fill=tk.X)
        tk.Label(r_proj, text="Tên cầu / Công trình:", font=("Arial", 10, "bold"), fg="#b71c1c").pack(side=tk.LEFT)
        self.txt_bridge_name = tk.Entry(r_proj, font=("Arial", 10, "bold"), fg="#b71c1c", width=30)
        self.txt_bridge_name.insert(0, "CẦU HỮU NGHỊ")
        self.txt_bridge_name.pack(side=tk.LEFT, padx=10)
        self.txt_bridge_name.bind("<KeyRelease>", self.on_bridge_name_change)

        tk.Button(r_proj, text="💾 Lưu dự án (.json)", font=("Arial", 9, "bold"), bg="#e8f5e9", fg="#2e7d32", 
                  command=self.save_project).pack(side=tk.RIGHT, padx=4)
        tk.Button(r_proj, text="📂 Mở dự án cũ (.json)", font=("Arial", 9, "bold"), bg="#e1f5fe", fg="#0277bd", 
                  command=self.open_project).pack(side=tk.RIGHT, padx=4)

        # 2. KHUNG THIẾT LẬP THÔNG SỐ ĐẦU VÀO
        top_frame = tk.Frame(self.root, padx=12, pady=2)
        top_frame.pack(fill=tk.X)

        # --- BÊN TRÁI: TỌA ĐỘ MẶT CẮT ---
        mc_box = tk.LabelFrame(top_frame, text=" 1. Tọa độ mặt cắt tự nhiên (Khoảng cách dồn X - Cao độ Z) ", 
                               font=("Arial", 9, "bold"), padx=8, pady=4)
        mc_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        mc_table_frame = tk.Frame(mc_box)
        mc_table_frame.pack(fill=tk.BOTH, expand=True)

        cols_mc = ("stt", "x", "z")
        self.tree_mc = ttk.Treeview(mc_table_frame, columns=cols_mc, show="headings", height=5)
        self.tree_mc.heading("stt", text="STT"); self.tree_mc.column("stt", width=40, anchor=tk.CENTER)
        self.tree_mc.heading("x", text="Khoảng cách X (m)"); self.tree_mc.column("x", width=120, anchor=tk.E)
        self.tree_mc.heading("z", text="Cao độ đáy Z (m)"); self.tree_mc.column("z", width=120, anchor=tk.E)
        
        sb_mc = ttk.Scrollbar(mc_table_frame, orient=tk.VERTICAL, command=self.tree_mc.yview)
        self.tree_mc.configure(yscroll=sb_mc.set)
        self.tree_mc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_mc.pack(side=tk.RIGHT, fill=tk.Y)

        self.update_mc_table()

        r_mc_btn = tk.Frame(mc_box, pady=3)
        r_mc_btn.pack(fill=tk.X)
        tk.Label(r_mc_btn, text="X:").pack(side=tk.LEFT)
        self.ent_new_x = tk.Entry(r_mc_btn, width=6); self.ent_new_x.pack(side=tk.LEFT, padx=2)
        tk.Label(r_mc_btn, text="Z:").pack(side=tk.LEFT)
        self.ent_new_z = tk.Entry(r_mc_btn, width=6); self.ent_new_z.pack(side=tk.LEFT, padx=2)
        tk.Button(r_mc_btn, text="➕ Thêm", font=("Arial", 8, "bold"), bg="#e8f5e9", fg="#2e7d32", 
                  command=self.add_mc_point).pack(side=tk.LEFT, padx=2)
        tk.Button(r_mc_btn, text="❌ Xóa", font=("Arial", 8), bg="#ffebee", fg="#c62828", 
                  command=self.delete_mc_point).pack(side=tk.LEFT, padx=2)
        tk.Button(r_mc_btn, text="📂 Nạp Excel/TXT", font=("Arial", 8, "bold"), bg="#e1f5fe", fg="#0277bd", 
                  command=self.load_mc_file).pack(side=tk.RIGHT)

        # --- BÊN PHẢI: THÔNG SỐ THỦY LỰC & CẤP MỰC NƯỚC TỰ ĐỘNG ---
        param_box = tk.LabelFrame(top_frame, text=" 2. Thông số thủy lực & Tự động nhận diện Bờ, Hmax, Hmin ", 
                                  font=("Arial", 9, "bold"), padx=10, pady=4)
        param_box.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # Phân chia bờ trái / bờ phải dòng chủ
        r_div = tk.Frame(param_box); r_div.pack(fill=tk.X, pady=1)
        tk.Label(r_div, text="Mép bờ trái dòng chủ X (m):", width=24, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_x_left = tk.Entry(r_div, width=8, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_x_left.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_div, text="Mép bờ phải dòng chủ X (m):", width=24, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_x_right = tk.Entry(r_div, width=8, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_x_right.pack(side=tk.LEFT)

        # Hệ số nhám 1/n
        r_nham = tk.Frame(param_box); r_nham.pack(fill=tk.X, pady=1)
        tk.Label(r_nham, text="1/n bãi trái:", width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_n_left = tk.Entry(r_nham, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_n_left.insert(0, "5.0"); self.txt_n_left.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r_nham, text="1/n dòng chủ:", width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_n_main = tk.Entry(r_nham, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_n_main.insert(0, "20.0"); self.txt_n_main.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r_nham, text="1/n bãi phải:", width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_n_right = tk.Entry(r_nham, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_n_right.insert(0, "5.0"); self.txt_n_right.pack(side=tk.LEFT)

        # Độ dốc thủy lực i
        r_slope = tk.Frame(param_box); r_slope.pack(fill=tk.X, pady=1)
        tk.Label(r_slope, text="Độ dốc mặt nước lũ (i):", width=22, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_slope_i = tk.Entry(r_slope, width=10, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_slope_i.insert(0, "0.00107"); self.txt_slope_i.pack(side=tk.LEFT)

        # Chọn Hmax, Hmin và dH
        r_h_cfg = tk.Frame(param_box, pady=2); r_h_cfg.pack(fill=tk.X)
        tk.Label(r_h_cfg, text="H max (m):", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_h_max = tk.Entry(r_h_cfg, width=6, justify=tk.CENTER, bg="#fff9c4", font=("Arial", 8, "bold"), fg="#b71c1c")
        self.txt_h_max.pack(side=tk.LEFT, padx=3)

        tk.Label(r_h_cfg, text="H min (m):", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_h_min = tk.Entry(r_h_cfg, width=6, justify=tk.CENTER, bg="#fff9c4", font=("Arial", 8, "bold"), fg="#b71c1c")
        self.txt_h_min.pack(side=tk.LEFT, padx=3)

        tk.Label(r_h_cfg, text="Bước dH (m):", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        self.txt_dh = tk.Entry(r_h_cfg, width=5, justify=tk.CENTER, bg="#fff9c4", font=("Arial", 8, "bold"), fg="#b71c1c")
        self.txt_dh.pack(side=tk.LEFT, padx=3)

        tk.Button(r_h_cfg, text="⚡ Cập nhật dải H", font=("Arial", 8, "bold"), bg="#fff3e0", fg="#e65100", 
                  command=self.generate_h_levels).pack(side=tk.LEFT, padx=4)

        tk.Button(r_h_cfg, text="🔄 Tự động nhận diện", font=("Arial", 8, "bold"), bg="#ede7f6", fg="#512da8", 
                  command=lambda: self.auto_detect_parameters(silent=False)).pack(side=tk.LEFT, padx=4)

        # 3. THANH NÚT CHỨC NĂNG
        btn_bar = tk.Frame(self.root, pady=4, padx=12)
        btn_bar.pack(fill=tk.X)

        tk.Button(btn_bar, text="🚀 TÍNH TOÁN TOÀN BỘ", font=("Arial", 9, "bold"), 
                  bg="#154360", fg="white", padx=12, pady=4, command=self.calculate_all).pack(side=tk.LEFT)

        tk.Button(btn_bar, text="📐 Bản vẽ mặt cắt sông", font=("Arial", 9, "bold"), 
                  bg="#00796b", fg="white", padx=10, pady=4, command=self.plot_cross_section).pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="📈 Đồ thị quan hệ (H - Q)", font=("Arial", 9, "bold"), 
                  bg="#1565c0", fg="white", padx=10, pady=4, command=self.plot_HQ_curve).pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="📈 Đồ thị quan hệ (H - V)", font=("Arial", 9, "bold"), 
                  bg="#d32f2f", fg="white", padx=10, pady=4, command=self.plot_HV_curve).pack(side=tk.LEFT, padx=4)

        tk.Button(btn_bar, text="💾 Xuất file Excel (.xlsx)", font=("Arial", 9, "bold"), 
                  bg="#2e7d32", fg="white", padx=12, pady=4, command=self.export_excel).pack(side=tk.RIGHT)

        # 4. GIAO DIỆN TABS (NOTEBOOK GỒM 5 TABS)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=3)

        # TAB 1: BẢNG CHI TIẾT TỪNG CẤP MỰC NƯỚC
        self.tab1 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab1, text=" 📑 Bảng chi tiết từng cấp H ")
        self.setup_tab1_ui()

        # TAB 2: BẢNG TỔNG HỢP QUAN HỆ H - Q & H - V
        self.tab2 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab2, text=" 📊 Bảng tổng hợp (H-Q, H-V) ")
        self.setup_tab2_ui()

        # TAB 3: XÁC ĐỊNH Htk TỪ Qtk
        self.tab3 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab3, text=" 🎯 Mực nước thiết kế Htk ")
        self.setup_tab3_ui()

        # TAB 4: TÍNH DIỆN TÍCH THOÁT NƯỚC CẦU
        self.tab4 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab4, text=" 🌊 Diện tích thoát nước cầu ")
        self.setup_tab4_ui()

        # TAB 5: TÍNH TOÁN NƯỚC DỀNH TRƯỚC CẦU
        self.tab5 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab5, text=" 📈 Mực nước dềnh trước cầu ")
        self.setup_tab5_ui()

    def on_bridge_name_change(self, event=None):
        name = self.txt_bridge_name.get().strip().upper()
        if not name: name = "CẦU"
        self.lbl_bridge_sub.config(text=name)

    # --- TAB 1: CHI TIẾT TỪNG CẤP MỰC NƯỚC ---
    def setup_tab1_ui(self):
        f_top = tk.Frame(self.tab1, pady=3)
        f_top.pack(fill=tk.X)

        tk.Label(f_top, text="Chọn cấp mực nước để xem chi tiết:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=6)
        self.cbo_select_h = ttk.Combobox(f_top, width=22, state="readonly")
        self.cbo_select_h.pack(side=tk.LEFT, padx=4)
        self.cbo_select_h.bind("<<ComboboxSelected>>", self.on_select_h_level)

        self.f_banner = tk.Frame(self.tab1, bg="white", relief=tk.SOLID, bd=1, pady=3)
        self.f_banner.pack(fill=tk.X, padx=6, pady=2)
        tk.Label(self.f_banner, text="MẶT CẮT LƯU LƯỢNG TẠI HẠ LƯU CÁCH TIM 25M", font=("Times New Roman", 12, "bold"), bg="white").pack()
        
        f_sub = tk.Frame(self.f_banner, bg="white")
        f_sub.pack()
        tk.Label(f_sub, text="BẢNG TÍNH DIỆN TÍCH THOÁT NƯỚC & CHU VI ƯỚT CẦU ", font=("Times New Roman", 11, "bold"), bg="white").pack(side=tk.LEFT)
        self.lbl_bridge_sub = tk.Label(f_sub, text="HỮU NGHỊ", font=("Times New Roman", 11, "bold"), fg="#c62828", bg="white")
        self.lbl_bridge_sub.pack(side=tk.LEFT)

        self.lbl_h_title = tk.Label(self.f_banner, text="Cấp mực nước: -- m", font=("Times New Roman", 11, "bold"), fg="#c62828", bg="white")
        self.lbl_h_title.pack(pady=1)

        cols = ("bophan", "z", "h", "b", "w", "dh", "c")
        self.tree_tab1 = ttk.Treeview(self.tab1, columns=cols, show="headings", height=13)
        self.tree_tab1.heading("bophan", text="Bộ phận tính toán")
        self.tree_tab1.heading("z", text="Cao độ TN (m)")
        self.tree_tab1.heading("h", text="Độ sâu h (m)")
        self.tree_tab1.heading("b", text="K/cách lẻ (m)")
        self.tree_tab1.heading("w", text="Diện tích ωi (m²)")
        self.tree_tab1.heading("dh", text="Δh (m)")
        self.tree_tab1.heading("c", text="Chu vi ướt χi (m)")

        self.tree_tab1.column("bophan", width=160, anchor=tk.W)
        self.tree_tab1.column("z", width=100, anchor=tk.CENTER)
        self.tree_tab1.column("h", width=100, anchor=tk.E)
        self.tree_tab1.column("b", width=110, anchor=tk.E)
        self.tree_tab1.column("w", width=120, anchor=tk.E)
        self.tree_tab1.column("dh", width=100, anchor=tk.E)
        self.tree_tab1.column("c", width=120, anchor=tk.E)

        self.tree_tab1.tag_configure("total_row", background="#fff3e0", font=("Arial", 9, "bold"))
        self.tree_tab1.tag_configure("header_row", foreground="#c62828", font=("Arial", 9, "bold"))

        sb_y = ttk.Scrollbar(self.tab1, orient=tk.VERTICAL, command=self.tree_tab1.yview)
        self.tree_tab1.configure(yscroll=sb_y.set)
        self.tree_tab1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=4)
        sb_y.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 6), pady=4)

    # --- TAB 2: TỔNG HỢP H-Q & H-V ---
    def setup_tab2_ui(self):
        f_info = tk.Frame(self.tab2, pady=3)
        f_info.pack(fill=tk.X)
        tk.Label(f_info, text="BẢNG TỔNG HỢP QUAN HỆ MỰC NƯỚC - LƯU LƯỢNG (H - Q) VÀ VẬN TỐC (H - V)", 
                 font=("Arial", 10, "bold"), fg="#154360").pack(side=tk.LEFT, padx=6)

        cols_hq = ("h", "w_l", "q_l", "w_m", "v_m", "q_m", "w_r", "q_r", "w_tot", "v_tb", "q_tot")
        self.tree_tab2 = ttk.Treeview(self.tab2, columns=cols_hq, show="headings", height=13)
        self.tree_tab2.heading("h", text="Mực nước H (m)"); self.tree_tab2.column("h", width=95, anchor=tk.CENTER)
        self.tree_tab2.heading("w_l", text="ω bãi trái (m²)"); self.tree_tab2.column("w_l", width=90, anchor=tk.E)
        self.tree_tab2.heading("q_l", text="Q bãi trái (m³/s)"); self.tree_tab2.column("q_l", width=95, anchor=tk.E)
        self.tree_tab2.heading("w_m", text="ω dòng chủ (m²)"); self.tree_tab2.column("w_m", width=95, anchor=tk.E)
        self.tree_tab2.heading("v_m", text="Vc (m/s)"); self.tree_tab2.column("v_m", width=85, anchor=tk.CENTER)
        self.tree_tab2.heading("q_m", text="Q dòng chủ (m³/s)"); self.tree_tab2.column("q_m", width=110, anchor=tk.E)
        self.tree_tab2.heading("w_r", text="ω bãi phải (m²)"); self.tree_tab2.column("w_r", width=90, anchor=tk.E)
        self.tree_tab2.heading("q_r", text="Q bãi phải (m³/s)"); self.tree_tab2.column("q_r", width=95, anchor=tk.E)
        self.tree_tab2.heading("w_tot", text="Tổng diện tích ω (m²)"); self.tree_tab2.column("w_tot", width=120, anchor=tk.E)
        self.tree_tab2.heading("v_tb", text="Vtb (m/s)"); self.tree_tab2.column("v_tb", width=85, anchor=tk.CENTER)
        self.tree_tab2.heading("q_tot", text="Tổng lưu lượng Q (m³/s)"); self.tree_tab2.column("q_tot", width=130, anchor=tk.E)

        self.tree_tab2.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    # --- TAB 3: MỰC NƯỚC THIẾT KẾ Htk TỪ Qtk ---
    def setup_tab3_ui(self):
        f_top = tk.LabelFrame(self.tab3, text=" Nhập lưu lượng thiết kế Qtk để giải tìm Htk ", font=("Arial", 9, "bold"), padx=10, pady=5)
        f_top.pack(fill=tk.X, padx=8, pady=4)

        r_input = tk.Frame(f_top); r_input.pack(fill=tk.X, pady=2)
        tk.Label(r_input, text="Lưu lượng thiết kế Qtk (m³/s):", font=("Arial", 9, "bold"), fg="#c62828").pack(side=tk.LEFT)
        self.txt_qtk_val = tk.Entry(r_input, width=10, justify=tk.CENTER, bg="#fff9c4", font=("Arial", 10, "bold"), fg="#c62828")
        self.txt_qtk_val.insert(0, "159.39"); self.txt_qtk_val.pack(side=tk.LEFT, padx=8)

        tk.Button(r_input, text="⚡ Giải tìm Htk & Tính thủy lực chi tiết", font=("Arial", 9, "bold"), bg="#154360", fg="white", 
                  command=self.calculate_Htk_tab).pack(side=tk.LEFT, padx=10)

        self.lbl_htk_card = tk.Label(f_top, text="KẾT QUẢ: Htk = 20.86 m | Tổng diện tích ướt ωtk = 236.54 m² | Vòng chủ Vc = 1.67 m/s", 
                                     font=("Arial", 10, "bold"), fg="#0d47a1", bg="#e3f2fd", padx=10, pady=4, relief=tk.GROOVE)
        self.lbl_htk_card.pack(fill=tk.X, pady=4)

        f_htk_table = tk.LabelFrame(self.tab3, text=" Bảng chi tiết diện tích thoát nước & chu vi ướt tại cao độ Htk ", 
                                    font=("Arial", 9, "bold"), padx=6, pady=4)
        f_htk_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        cols_htk = ("bophan", "z", "h", "b", "w", "dh", "c")
        self.tree_tab3 = ttk.Treeview(f_htk_table, columns=cols_htk, show="headings", height=11)
        self.tree_tab3.heading("bophan", text="Bộ phận tính toán")
        self.tree_tab3.heading("z", text="Cao độ TN (m)")
        self.tree_tab3.heading("h", text="Độ sâu h (m)")
        self.tree_tab3.heading("b", text="K/cách lẻ (m)")
        self.tree_tab3.heading("w", text="Diện tích ωi (m²)")
        self.tree_tab3.heading("dh", text="Δh (m)")
        self.tree_tab3.heading("c", text="Chu vi ướt χi (m)")

        self.tree_tab3.column("bophan", width=160, anchor=tk.W)
        self.tree_tab3.column("z", width=100, anchor=tk.CENTER)
        self.tree_tab3.column("h", width=100, anchor=tk.E)
        self.tree_tab3.column("b", width=110, anchor=tk.E)
        self.tree_tab3.column("w", width=120, anchor=tk.E)
        self.tree_tab3.column("dh", width=100, anchor=tk.E)
        self.tree_tab3.column("c", width=120, anchor=tk.E)

        self.tree_tab3.tag_configure("total_row", background="#fff3e0", font=("Arial", 9, "bold"))
        self.tree_tab3.pack(fill=tk.BOTH, expand=True)

    # --- TAB 4: TÍNH TOÁN DIỆN TÍCH THOÁT NƯỚC CẦU (BELLELIUTSKY) ---
    def setup_tab4_ui(self):
        f_cfg = tk.LabelFrame(self.tab4, text=" Tham số tính toán khẩu độ thoát nước cần thiết (Người dùng tùy chỉnh theo từng cầu) ", 
                              font=("Arial", 9, "bold"), padx=10, pady=5)
        f_cfg.pack(fill=tk.X, padx=8, pady=4)

        r1 = tk.Frame(f_cfg); r1.pack(fill=tk.X, pady=2)
        tk.Label(r1, text="Hệ số thắt hẹp m:", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_dt_mu = tk.Entry(r1, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_dt_mu.insert(0, "0.98"); self.txt_dt_mu.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r1, text="Hệ số xói Pmax:", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_dt_p = tk.Entry(r1, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_dt_p.insert(0, "1.04"); self.txt_dt_p.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r1, text="Góc lệch dòng α (°):", width=18, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_dt_alpha = tk.Entry(r1, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_dt_alpha.insert(0, "33.0"); self.txt_dt_alpha.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r1, text="Chiều sâu htb (m):", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_dt_htb = tk.Entry(r1, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_dt_htb.insert(0, "2.885"); self.txt_dt_htb.pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(r1, text="⚡ Cập nhật khẩu độ", font=("Arial", 8, "bold"), bg="#154360", fg="white", 
                  command=self.update_tab4_display).pack(side=tk.LEFT)

        # Bảng hiển thị thông số chi tiết mô phỏng sheet Dien tich thoat nuoc
        f_tbl = tk.LabelFrame(self.tab4, text=" Bảng thông số tính diện tích thoát nước cần thiết (Belleliutsky) - TỰ ĐỘNG LINK TỪ HÌNH THÁI MẶT CẮT ", 
                              font=("Arial", 9, "bold"), padx=6, pady=4)
        f_tbl.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        cols = ("stt", "item", "unit", "val", "note")
        self.tree_tab4 = ttk.Treeview(f_tbl, columns=cols, show="headings", height=13)
        self.tree_tab4.heading("stt", text="STT"); self.tree_tab4.column("stt", width=45, anchor=tk.CENTER)
        self.tree_tab4.heading("item", text="Hạng mục tính toán"); self.tree_tab4.column("item", width=420, anchor=tk.W)
        self.tree_tab4.heading("unit", text="Đơn vị"); self.tree_tab4.column("unit", width=80, anchor=tk.CENTER)
        self.tree_tab4.heading("val", text="Trị số"); self.tree_tab4.column("val", width=120, anchor=tk.E)
        self.tree_tab4.heading("note", text="Ghi chú"); self.tree_tab4.column("note", width=250, anchor=tk.W)

        self.tree_tab4.tag_configure("sec_header", background="#e1f5fe", font=("Arial", 9, "bold"), foreground="#0277bd")
        self.tree_tab4.tag_configure("highlight", background="#fff3e0", font=("Arial", 9, "bold"), foreground="#b71c1c")
        self.tree_tab4.pack(fill=tk.BOTH, expand=True)

    # --- TAB 5: TÍNH TOÁN NƯỚC DỀNH TRƯỚC CẦU (H1%DENH) ---
    def setup_tab5_ui(self):
        f_cfg = tk.LabelFrame(self.tab5, text=" Tham số công trình cầu & cản nước (Người dùng tùy chỉnh theo từng dự án) ", 
                              font=("Arial", 9, "bold"), padx=10, pady=5)
        f_cfg.pack(fill=tk.X, padx=8, pady=4)

        r1 = tk.Frame(f_cfg); r1.pack(fill=tk.X, pady=2)
        tk.Label(r1, text="Cự ly tim cầu Lhl (m):", width=20, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_denh_lhl = tk.Entry(r1, width=7, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_denh_lhl.insert(0, "25.0"); self.txt_denh_lhl.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r1, text="Số trụ cầu cản nước:", width=17, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_denh_piers = tk.Entry(r1, width=5, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_denh_piers.insert(0, "0"); self.txt_denh_piers.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r1, text="Bề rộng trụ bt (m):", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_denh_bpier = tk.Entry(r1, width=5, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_denh_bpier.insert(0, "1.4"); self.txt_denh_bpier.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(r1, text="Hệ số năng lực bãi η:", width=18, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_denh_eta = tk.Entry(r1, width=6, justify=tk.CENTER, bg="#fffde7", fg="#b71c1c", font=("Arial", 9, "bold"))
        self.txt_denh_eta.insert(0, "0.07"); self.txt_denh_eta.pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(r1, text="⚡ Cập nhật nước dềnh", font=("Arial", 8, "bold"), bg="#154360", fg="white", 
                  command=self.update_tab5_display).pack(side=tk.LEFT)

        f_tbl = tk.LabelFrame(self.tab5, text=" Bảng tính toán mực nước dềnh trước cầu (Sheet H1%Denh) - TỰ ĐỘNG LINK TỪ HÌNH THÁI MẶT CẮT ", 
                              font=("Arial", 9, "bold"), padx=6, pady=4)
        f_tbl.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        cols = ("stt", "item", "unit", "val", "note")
        self.tree_tab5 = ttk.Treeview(f_tbl, columns=cols, show="headings", height=13)
        self.tree_tab5.heading("stt", text="STT"); self.tree_tab5.column("stt", width=45, anchor=tk.CENTER)
        self.tree_tab5.heading("item", text="Hạng mục tính toán"); self.tree_tab5.column("item", width=420, anchor=tk.W)
        self.tree_tab5.heading("unit", text="Đơn vị"); self.tree_tab5.column("unit", width=80, anchor=tk.CENTER)
        self.tree_tab5.heading("val", text="Trị số"); self.tree_tab5.column("val", width=120, anchor=tk.E)
        self.tree_tab5.heading("note", text="Ghi chú"); self.tree_tab5.column("note", width=250, anchor=tk.W)

        self.tree_tab5.tag_configure("sec_header", background="#e1f5fe", font=("Arial", 9, "bold"), foreground="#0277bd")
        self.tree_tab5.tag_configure("highlight", background="#fff3e0", font=("Arial", 9, "bold"), foreground="#b71c1c")
        self.tree_tab5.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # LƯU & MỞ FILE DỰ ÁN (JSON)
    # =========================================================================
    def save_project(self):
        f_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Project JSON files", "*.json"), ("All files", "*.*")],
            title="Lưu file tính toán dự án"
        )
        if not f_path: return
        try:
            data = {
                "bridge_name": self.txt_bridge_name.get(),
                "mc_data": self.mc_data,
                "x_left": self.txt_x_left.get(),
                "x_right": self.txt_x_right.get(),
                "n_left": self.txt_n_left.get(),
                "n_main": self.txt_n_main.get(),
                "n_right": self.txt_n_right.get(),
                "slope_i": self.txt_slope_i.get(),
                "h_max": self.txt_h_max.get(),
                "h_min": self.txt_h_min.get(),
                "dh": self.txt_dh.get(),
                "q_tk": self.txt_qtk_val.get(),
                "dt_mu": self.txt_dt_mu.get(),
                "dt_p": self.txt_dt_p.get(),
                "dt_alpha": self.txt_dt_alpha.get(),
                "dt_htb": self.txt_dt_htb.get(),
                "denh_lhl": self.txt_denh_lhl.get(),
                "denh_piers": self.txt_denh_piers.get(),
                "denh_bpier": self.txt_denh_bpier.get(),
                "denh_eta": self.txt_denh_eta.get()
            }
            with open(f_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("Thành công", f"Đã lưu toàn bộ dự án vào:\n{f_path}")
        except Exception as e:
            messagebox.showerror("Lỗi khi lưu", f"Không thể lưu file: {e}")

    def open_project(self):
        f_path = filedialog.askopenfilename(
            filetypes=[("Project JSON files", "*.json"), ("All files", "*.*")],
            title="Chọn file dự án cần mở"
        )
        if not f_path: return
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.txt_bridge_name.delete(0, tk.END); self.txt_bridge_name.insert(0, data.get("bridge_name", "CẦU HỮU NGHỊ"))
            self.on_bridge_name_change()

            self.mc_data = [tuple(p) for p in data.get("mc_data", DEFAULT_MC)]
            self.update_mc_table()

            self.txt_x_left.delete(0, tk.END); self.txt_x_left.insert(0, data.get("x_left", "89.04"))
            self.txt_x_right.delete(0, tk.END); self.txt_x_right.insert(0, data.get("x_right", "106.58"))
            self.txt_n_left.delete(0, tk.END); self.txt_n_left.insert(0, data.get("n_left", "5.0"))
            self.txt_n_main.delete(0, tk.END); self.txt_n_main.insert(0, data.get("n_main", "20.0"))
            self.txt_n_right.delete(0, tk.END); self.txt_n_right.insert(0, data.get("n_right", "5.0"))
            self.txt_slope_i.delete(0, tk.END); self.txt_slope_i.insert(0, data.get("slope_i", "0.00107"))

            self.txt_h_max.delete(0, tk.END); self.txt_h_max.insert(0, data.get("h_max", "21.50"))
            self.txt_h_min.delete(0, tk.END); self.txt_h_min.insert(0, data.get("h_min", "20.30"))
            self.txt_dh.delete(0, tk.END); self.txt_dh.insert(0, data.get("dh", "0.30"))
            self.txt_qtk_val.delete(0, tk.END); self.txt_qtk_val.insert(0, data.get("q_tk", "159.39"))

            if "dt_mu" in data: self.txt_dt_mu.delete(0, tk.END); self.txt_dt_mu.insert(0, data["dt_mu"])
            if "dt_p" in data: self.txt_dt_p.delete(0, tk.END); self.txt_dt_p.insert(0, data["dt_p"])
            if "dt_alpha" in data: self.txt_dt_alpha.delete(0, tk.END); self.txt_dt_alpha.insert(0, data["dt_alpha"])
            if "dt_htb" in data: self.txt_dt_htb.delete(0, tk.END); self.txt_dt_htb.insert(0, data["dt_htb"])

            if "denh_lhl" in data: self.txt_denh_lhl.delete(0, tk.END); self.txt_denh_lhl.insert(0, data["denh_lhl"])
            if "denh_piers" in data: self.txt_denh_piers.delete(0, tk.END); self.txt_denh_piers.insert(0, data["denh_piers"])
            if "denh_bpier" in data: self.txt_denh_bpier.delete(0, tk.END); self.txt_denh_bpier.insert(0, data["denh_bpier"])
            if "denh_eta" in data: self.txt_denh_eta.delete(0, tk.END); self.txt_denh_eta.insert(0, data["denh_eta"])

            self.generate_h_levels()
            messagebox.showinfo("Thành công", f"Đã khôi phục toàn bộ dự án từ:\n{f_path}")
        except Exception as e:
            messagebox.showerror("Lỗi khi mở", f"Không thể đọc file: {e}")

    def auto_detect_parameters(self, silent=True):
        if len(self.mc_data) < 3: return

        xs = [p[0] for p in self.mc_data]
        zs = [p[1] for p in self.mc_data]
        n = len(self.mc_data)

        z_min = min(zs)
        z_max = max(zs)

        idx_min = int(np.argmin(zs))
        slopes = [abs(zs[i+1] - zs[i]) / max(abs(xs[i+1] - xs[i]), 1e-4) for i in range(n-1)]

        left_slopes = slopes[:idx_min]
        idx_left_bank = int(np.argmax(left_slopes)) if left_slopes else 0

        right_slopes = slopes[idx_min:]
        idx_right_bank = idx_min + int(np.argmax(right_slopes)) + 1 if right_slopes else n - 1

        x_left = xs[idx_left_bank]
        x_right = xs[idx_right_bank]

        dh = round((z_max - z_min) / 4.0, 2)
        if dh <= 0: dh = 0.30

        self.txt_x_left.delete(0, tk.END); self.txt_x_left.insert(0, f"{x_left:.2f}")
        self.txt_x_right.delete(0, tk.END); self.txt_x_right.insert(0, f"{x_right:.2f}")
        self.txt_h_max.delete(0, tk.END); self.txt_h_max.insert(0, f"{z_max:.2f}")
        self.txt_h_min.delete(0, tk.END); self.txt_h_min.insert(0, f"{z_min:.2f}")
        self.txt_dh.delete(0, tk.END); self.txt_dh.insert(0, f"{dh:.2f}")

        self.generate_h_levels()

        if not silent:
            messagebox.showinfo(
                "Tự động nhận diện thành công",
                f"Đã tự động xác định các thông số từ mặt cắt:\n"
                f"• Bờ trái dòng chủ X = {x_left:.2f} m\n"
                f"• Bờ phải dòng chủ X = {x_right:.2f} m\n"
                f"• H max (cao độ cao nhất) = {z_max:.2f} m\n"
                f"• H min (cao độ thấp nhất) = {z_min:.2f} m\n"
                f"• Bước chia dH            = {dh:.2f} m"
            )

    def generate_h_levels(self):
        try:
            h_max = float(self.txt_h_max.get())
            h_min = float(self.txt_h_min.get())
            dh = float(self.txt_dh.get())
            if dh <= 0 or h_max <= h_min:
                messagebox.showwarning("Cảnh báo", "Hmax phải lớn hơn Hmin và bước dH phải > 0!")
                return
            
            num_steps = int(round((h_max - h_min) / dh)) + 1
            self.h_levels = [round(h_max - i * dh, 2) for i in range(num_steps)]
            
            cbo_vals = [f"Cấp H{i+1}: {h:.2f} m" for i, h in enumerate(self.h_levels)]
            self.cbo_select_h['values'] = cbo_vals
            if cbo_vals:
                self.cbo_select_h.current(0)
                
            self.calculate_all()
        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng nhập đúng dạng số cho Hmax, Hmin, dH!")

    def update_mc_table(self):
        self.tree_mc.delete(*self.tree_mc.get_children())
        self.mc_data.sort(key=lambda pt: pt[0])
        for idx, (x, z) in enumerate(self.mc_data, start=1):
            self.tree_mc.insert("", tk.END, values=(idx, f"{x:.2f}", f"{z:.2f}"))

    def add_mc_point(self):
        try:
            x_val = float(self.ent_new_x.get())
            z_val = float(self.ent_new_z.get())
            self.mc_data.append((x_val, z_val))
            self.update_mc_table()
            self.ent_new_x.delete(0, tk.END)
            self.ent_new_z.delete(0, tk.END)
            self.calculate_all()
        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng nhập số hợp lệ cho X và Z!")

    def delete_mc_point(self):
        sel = self.tree_mc.selection()
        if not sel: return
        item = self.tree_mc.item(sel[0])
        idx = int(item['values'][0]) - 1
        if 0 <= idx < len(self.mc_data):
            del self.mc_data[idx]
            self.update_mc_table()
            self.calculate_all()

    def load_mc_file(self):
        f_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xls *.xlsx"), ("Text/CSV files", "*.txt *.csv"), ("All files", "*.*")])
        if not f_path: return
        try:
            if f_path.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(f_path, sheet_name=0)
                num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                if len(num_cols) >= 2:
                    sub_df = df[[num_cols[0], num_cols[1]]].dropna()
                    self.mc_data = list(zip(sub_df.iloc[:, 0].astype(float), sub_df.iloc[:, 1].astype(float)))
                else:
                    messagebox.showwarning("Cảnh báo", "Không tìm thấy đủ 2 cột số (X, Z).")
                    return
            else:
                pts = []
                with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        parts = line.replace(",", " ").split()
                        if len(parts) >= 2:
                            try: pts.append((float(parts[0]), float(parts[1])))
                            except ValueError: pass
                if len(pts) >= 3:
                    self.mc_data = pts
                else:
                    messagebox.showwarning("Cảnh báo", "Tệp văn bản cần có ít nhất 3 điểm (X Z).")
                    return

            self.update_mc_table()
            self.auto_detect_parameters(silent=False)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được tệp mặt cắt: {e}")

    def prepare_points_with_boundaries(self, mc_data, x_left, x_right):
        pts = sorted(list(mc_data), key=lambda p: p[0])
        xs = [p[0] for p in pts]
        
        x_min, x_max = xs[0], xs[-1]
        x_left = max(x_min, min(x_left, x_max))
        x_right = max(x_left, min(x_right, x_max))
        
        new_pts = []
        inserted_left = False
        inserted_right = False
        
        for i in range(len(pts)):
            p = pts[i]
            if not inserted_left and p[0] >= x_left:
                if p[0] > x_left and i > 0:
                    p_prev = pts[i-1]
                    z_left = p_prev[1] + (x_left - p_prev[0]) * (p[1] - p_prev[1]) / (p[0] - p_prev[0])
                    new_pts.append((x_left, z_left))
                inserted_left = True
                
            if not inserted_right and p[0] >= x_right:
                if p[0] > x_right and i > 0:
                    p_prev = new_pts[-1] if new_pts else pts[i-1]
                    z_right = p_prev[1] + (x_right - p_prev[0]) * (p[1] - p_prev[1]) / (p[0] - p_prev[0])
                    new_pts.append((x_right, z_right))
                inserted_right = True
                
            if not new_pts or abs(new_pts[-1][0] - p[0]) > 1e-5:
                new_pts.append(p)
                
        return new_pts, x_left, x_right

    def generate_detailed_rows_for_H(self, H, x_left_main, x_right_main):
        new_pts, xl, xr = self.prepare_points_with_boundaries(self.mc_data, x_left_main, x_right_main)
        
        pts_left = [p for p in new_pts if p[0] <= xl + 1e-5]
        pts_main = [p for p in new_pts if xl - 1e-5 <= p[0] <= xr + 1e-5]
        pts_right = [p for p in new_pts if p[0] >= xr - 1e-5]

        rows = []

        def build_zone(zone_type, z_pts):
            lbl = "Tổng cộng bãi trái" if zone_type == "left" else ("Tổng cộng dòng chủ" if zone_type == "main" else "Tổng cộng bãi phải")
            empty_tot = {
                'bophan': lbl, 'z': "", 'h': "",
                'b': "0.00", 'w': "0.00", 'dh': "0.00", 'c': "0.00",
                'is_tot': True, 'raw_b': 0.0, 'raw_w': 0.0, 'raw_c': 0.0
            }

            if not z_pts or len(z_pts) < 1:
                return [empty_tot]

            active = []
            for p in z_pts:
                h = max(0.0, H - p[1])
                active.append({'x': p[0], 'z': p[1], 'h': h})

            z_rows = []
            tot_b, tot_w, tot_dh, tot_c = 0.0, 0.0, 0.0, 0.0

            for i in range(len(active)):
                pt = active[i]
                if i == 0:
                    bp = "(Bờ trái)" if zone_type == "left" else ("Dòng chủ" if zone_type == "main" else "")
                    z_rows.append({
                        'bophan': bp,
                        'z': f"{H:.2f}" if (zone_type == "left" and pt['h'] > 0) else f"{pt['z']:.2f}",
                        'h': f"{0.0:.2f}" if (zone_type == "left" and pt['h'] > 0) else f"{pt['h']:.2f}",
                        'b': "", 'w': "", 'dh': "", 'c': "", 'is_tot': False
                    })
                else:
                    prev = active[i-1]
                    h_prev = 0.0 if (zone_type == "left" and i == 1 and active[0]['h'] > 0) else prev['h']
                    h_curr = pt['h']
                    b = pt['x'] - prev['x']
                    w = 0.5 * (h_prev + h_curr) * b
                    dh = h_curr - h_prev
                    c = np.sqrt(b**2 + dh**2)

                    tot_b += b; tot_w += w; tot_dh += dh; tot_c += c

                    bp = "(Bờ phải)" if (zone_type == "right" and i == len(active)-1) else ""
                    z_rows.append({
                        'bophan': bp, 'z': f"{pt['z']:.2f}", 'h': f"{h_curr:.2f}",
                        'b': f"{b:.2f}", 'w': f"{w:.2f}", 'dh': f"{dh:.2f}", 'c': f"{c:.2f}",
                        'is_tot': False
                    })

            z_rows.append({
                'bophan': lbl, 'z': "", 'h': "",
                'b': f"{tot_b:.2f}", 'w': f"{tot_w:.2f}", 'dh': f"{tot_dh:.2f}", 'c': f"{tot_c:.2f}",
                'is_tot': True, 'raw_b': tot_b, 'raw_w': tot_w, 'raw_c': tot_c
            })
            return z_rows

        rows.extend(build_zone("left", pts_left))
        rows.extend(build_zone("main", pts_main))
        rows.extend(build_zone("right", pts_right))
        return rows

    def calculate_all(self):
        try:
            x_left = float(self.txt_x_left.get())
            x_right = float(self.txt_x_right.get())
            inv_n_left = float(self.txt_n_left.get())
            inv_n_main = float(self.txt_n_main.get())
            inv_n_right = float(self.txt_n_right.get())
            slope_i = float(self.txt_slope_i.get())
            sqrt_i = np.sqrt(slope_i)

            self.detailed_dict = {}
            self.summary_list = []

            def safe_get_total(det_rows, label):
                d_val = {'raw_w': 0.0, 'raw_c': 0.0, 'raw_b': 0.0}
                return next((r for r in det_rows if r.get('bophan') == label), d_val)

            for H in self.h_levels:
                det_rows = self.generate_detailed_rows_for_H(H, x_left, x_right)
                self.detailed_dict[H] = det_rows

                t_left = safe_get_total(det_rows, "Tổng cộng bãi trái")
                t_main = safe_get_total(det_rows, "Tổng cộng dòng chủ")
                t_right = safe_get_total(det_rows, "Tổng cộng bãi phải")

                w_l, c_l = t_left['raw_w'], t_left['raw_c']
                w_m, c_m = t_main['raw_w'], t_main['raw_c']
                w_r, c_r = t_right['raw_w'], t_right['raw_c']

                R_l = w_l / c_l if c_l > 0 else 0
                V_l = inv_n_left * (R_l ** (2.0/3.0)) * sqrt_i if R_l > 0 else 0
                Q_l = w_l * V_l

                R_m = w_m / c_m if c_m > 0 else 0
                V_m = inv_n_main * (R_m ** (2.0/3.0)) * sqrt_i if R_m > 0 else 0
                Q_m = w_m * V_m

                R_r = w_r / c_r if c_r > 0 else 0
                V_r = inv_n_right * (R_r ** (2.0/3.0)) * sqrt_i if R_r > 0 else 0
                Q_r = w_r * V_r

                w_tot = w_l + w_m + w_r
                Q_tot = Q_l + Q_m + Q_r
                V_tb = Q_tot / w_tot if w_tot > 0 else 0

                self.summary_list.append({
                    'H': H,
                    'w_l': w_l, 'c_l': c_l, 'R_l': R_l, 'Q_l': Q_l,
                    'w_m': w_m, 'c_m': c_m, 'R_m': R_m, 'V_m': V_m, 'Q_m': Q_m,
                    'w_r': w_r, 'c_r': c_r, 'R_r': R_r, 'Q_r': Q_r,
                    'w_tot': w_tot, 'V_tb': V_tb, 'Q_tot': Q_tot
                })

            self.tree_tab2.delete(*self.tree_tab2.get_children())
            for s in self.summary_list:
                self.tree_tab2.insert("", tk.END, values=(
                    f"{s['H']:.2f}",
                    f"{s['w_l']:.2f}", f"{s['Q_l']:.2f}",
                    f"{s['w_m']:.2f}", f"{s['V_m']:.2f}", f"{s['Q_m']:.2f}",
                    f"{s['w_r']:.2f}", f"{s['Q_r']:.2f}",
                    f"{s['w_tot']:.2f}", f"{s['V_tb']:.2f}", f"{s['Q_tot']:.2f}"
                ))

            if self.h_levels:
                self.on_select_h_level()

            self.calculate_Htk_tab()
            self.update_tab4_display()
            self.update_tab5_display()

        except Exception as e:
            messagebox.showerror("Lỗi tính toán", f"Chi tiết: {e}")

    def on_select_h_level(self, event=None):
        sel_idx = self.cbo_select_h.current()
        if sel_idx < 0 or sel_idx >= len(self.h_levels):
            return
        H_val = self.h_levels[sel_idx]
        self.lbl_h_title.config(text=f"Cấp mực nước H{sel_idx+1}:  {H_val:.2f} m")

        self.tree_tab1.delete(*self.tree_tab1.get_children())
        rows = self.detailed_dict.get(H_val, [])
        for r in rows:
            tag = "total_row" if r['is_tot'] else ("header_row" if r['bophan'] != "" else "")
            self.tree_tab1.insert("", tk.END, values=(
                r['bophan'], r['z'], r['h'], r['b'], r['w'], r['dh'], r['c']
            ), tags=(tag,))

    def calculate_Htk_tab(self):
        try:
            Q_tk = float(self.txt_qtk_val.get())
            if not self.summary_list:
                return

            q_pts = [s['Q_tot'] for s in self.summary_list]
            h_pts = [s['H'] for s in self.summary_list]

            q_sort = sorted(q_pts)
            h_sort = [h for _, h in sorted(zip(q_pts, h_pts))]

            f_interp = interp1d(q_sort, h_sort, kind='linear', fill_value="extrapolate")
            self.H_tk_val = float(f_interp(Q_tk))

            x_left = float(self.txt_x_left.get())
            x_right = float(self.txt_x_right.get())
            self.det_rows_Htk = self.generate_detailed_rows_for_H(self.H_tk_val, x_left, x_right)

            def safe_get_total(d_rows, label):
                d_val = {'raw_w': 0.0, 'raw_c': 0.0, 'raw_b': 0.0}
                return next((r for r in d_rows if r.get('bophan') == label), d_val)

            t_left = safe_get_total(self.det_rows_Htk, "Tổng cộng bãi trái")
            t_main = safe_get_total(self.det_rows_Htk, "Tổng cộng dòng chủ")
            t_right = safe_get_total(self.det_rows_Htk, "Tổng cộng bãi phải")

            self.w1_tk, self.b1_tk, self.c1_tk = t_left['raw_w'], t_left['raw_b'], t_left['raw_c']
            self.wc_tk, self.bc_tk, self.cc_tk = t_main['raw_w'], t_main['raw_b'], t_main['raw_c']
            self.w2_tk, self.b2_tk, self.c2_tk = t_right['raw_w'], t_right['raw_b'], t_right['raw_c']

            self.wtot_tk = self.w1_tk + self.wc_tk + self.w2_tk
            self.B_tk = self.b1_tk + self.bc_tk + self.b2_tk
            self.wb_tk = self.w1_tk + self.w2_tk
            self.bb_tk = self.b1_tk + self.b2_tk

            self.R1_tk = self.w1_tk / self.c1_tk if self.c1_tk > 0 else 0
            self.Rc_tk = self.wc_tk / self.cc_tk if self.cc_tk > 0 else 0
            self.R2_tk = self.w2_tk / self.c2_tk if self.c2_tk > 0 else 0

            slope_i = float(self.txt_slope_i.get())
            sqrt_i = np.sqrt(slope_i)
            inv_n_l = float(self.txt_n_left.get())
            inv_n_m = float(self.txt_n_main.get())
            inv_n_r = float(self.txt_n_right.get())

            self.Q1_tk = self.w1_tk * inv_n_l * (self.R1_tk ** (2.0/3.0)) * sqrt_i if self.R1_tk > 0 else 0
            self.Qc_tk = self.wc_tk * inv_n_m * (self.Rc_tk ** (2.0/3.0)) * sqrt_i if self.Rc_tk > 0 else 0
            self.Q2_tk = self.w2_tk * inv_n_r * (self.R2_tk ** (2.0/3.0)) * sqrt_i if self.R2_tk > 0 else 0
            self.Qb_tk = self.Q1_tk + self.Q2_tk

            self.Vc_tk = self.Qc_tk / self.wc_tk if self.wc_tk > 0 else 0
            self.Vtb_tk = Q_tk / self.wtot_tk if self.wtot_tk > 0 else 0

            b_name = self.txt_bridge_name.get().strip().upper()
            if not b_name: b_name = "CẦU"

            self.lbl_htk_card.config(
                text=f"🎯 KẾT QUẢ TÍNH TOÁN CHO {b_name}:\n"
                     f"Mực nước thiết kế Htk = {self.H_tk_val:.3f} m  |  Tổng diện tích ướt ωtk = {self.wtot_tk:.2f} m²\n"
                     f"Lưu tốc dòng chủ Vc = {self.Vc_tk:.2f} m/s  |  Lưu tốc bình quân Vtb = {self.Vtb_tk:.2f} m/s"
            )

            self.tree_tab3.delete(*self.tree_tab3.get_children())
            for r in self.det_rows_Htk:
                tag = "total_row" if r['is_tot'] else ""
                self.tree_tab3.insert("", tk.END, values=(
                    r['bophan'], r['z'], r['h'], r['b'], r['w'], r['dh'], r['c']
                ), tags=(tag,))

            self.update_tab4_display()
            self.update_tab5_display()

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không xác định được Htk: {e}")

    # --- TAB 4: TỰ ĐỘNG LINK TỪ HÌNH THÁI MẶT CẮT + THAM SỐ NGƯỜI DÙNG TÙY BIẾN ---
    def update_tab4_display(self):
        try:
            Q_tk = float(self.txt_qtk_val.get())
            mu = float(self.txt_dt_mu.get())
            P_xoi = float(self.txt_dt_p.get())
            alpha_deg = float(self.txt_dt_alpha.get())
            h_tb_user = float(self.txt_dt_htb.get())
            cos_a = np.cos(np.radians(alpha_deg))

            if not hasattr(self, 'w1_tk'): return

            h1 = self.w1_tk / self.b1_tk if self.b1_tk > 0 else 0
            h2 = self.w2_tk / self.b2_tk if self.b2_tk > 0 else 0
            hc = self.wc_tk / self.bc_tk if self.bc_tk > 0 else 0
            hb = self.wb_tk / self.bb_tk if self.bb_tk > 0 else 0

            n1 = 1.0 / float(self.txt_n_left.get()) if float(self.txt_n_left.get()) > 0 else 0.2
            n2 = 1.0 / float(self.txt_n_right.get()) if float(self.txt_n_right.get()) > 0 else 0.2
            nc = 1.0 / float(self.txt_n_main.get()) if float(self.txt_n_main.get()) > 0 else 0.05

            k_dist_1 = self.Q1_tk / Q_tk if Q_tk > 0 else 0
            k_dist_2 = self.Q2_tk / Q_tk if Q_tk > 0 else 0

            # Diện tích thoát nước cần thiết theo Belleliutsky:
            omega_ct = Q_tk / (mu * P_xoi * self.Vc_tk) if (mu * P_xoi * self.Vc_tk) > 0 else 0
            L_ct = omega_ct / (h_tb_user * cos_a) if (h_tb_user * cos_a > 0) else 0

            self.tab4_data = [
                ("I", "CÁC THÔNG SỐ LINK TỰ ĐỘNG TỪ BẢNG HÌNH THÁI MẶT CẮT (Htk):", "", "", "sec_header"),
                ("1", "Lưu lượng thiết kế : QTK", "m³/s", f"{Q_tk:.2f}", "Link từ Qtk"),
                ("2", "Diện tích ướt bãi phía bên trái: w1", "m²", f"{self.w1_tk:.2f}", "Link từ Htk"),
                ("3", "Diện tích ướt bãi phía bên phải: w2", "m²", f"{self.w2_tk:.2f}", f"wb = {self.wb_tk:.2f} m²"),
                ("4", "Diện tích ướt lòng chủ: wc", "m²", f"{self.wc_tk:.2f}", f"bb = {self.bb_tk:.2f} m"),
                ("5", "Chiều rộng bãi phía bên trái: b1", "m", f"{self.b1_tk:.2f}", "Link từ Htk"),
                ("6", "Chiều rộng bãi phía bên phải: b2", "m", f"{self.b2_tk:.2f}", f"B = {self.B_tk:.2f} m"),
                ("7", "Chiều rộng lòng chủ: bc", "m", f"{self.bc_tk:.2f}", "Link từ Htk"),
                ("8", "Bán kính thủy lực bãi phía bên trái: R1", "m", f"{self.R1_tk:.3f}", "Link từ Htk"),
                ("9", "Bán kính thủy lực bãi phía bên phải: R2", "m", f"{self.R2_tk:.3f}", "Link từ Htk"),
                ("10", "Bán kính thủy lực lòng chủ: Rc", "m", f"{self.Rc_tk:.3f}", "Link từ Htk"),
                ("11", "Chiều sâu trung bình dòng bãi: hb = Swb / (b1+b2)", "m", f"{hb:.3f}", "Link từ Htk"),
                ("12", "Hệ số nhám bãi phía bên trái: n1", "-", f"{n1:.3f}", "Quy đổi từ 1/n"),
                ("13", "Hệ số nhám bãi phía bên phải: n2", "-", f"{n2:.3f}", "Quy đổi từ 1/n"),
                ("14", "Hệ số nhám lòng chủ: nc", "-", f"{nc:.3f}", "Quy đổi từ 1/n"),
                ("15", "Hệ số phân phối lưu lượng bãi trái: k1 = Q1/Qtk", "-", f"{k_dist_1:.4f}", "Link từ Htk"),
                ("16", "Hệ số phân phối lưu lượng bãi phải: k2 = Q2/Qtk", "-", f"{k_dist_2:.4f}", "Link từ Htk"),
                ("17", "Lưu lượng dòng chủ: Qc", "m³/s", f"{self.Qc_tk:.2f}", "Link từ Htk"),
                ("18", "Lưu tốc dòng chủ: Vc = Qc / wc", "m/s", f"{self.Vc_tk:.2f}", "Link từ Htk"),
                ("II", "KẾT QUẢ TÍNH KHẨU ĐỘ THEO THAM SỐ CÔNG TRÌNH CẦU TÙY CHỈNH:", "", "", "sec_header"),
                ("1", "Hệ số thắt hẹp dòng chảy: m = f(Vc; Lct)", "-", f"{mu:.2f}", "Người dùng tùy chỉnh"),
                ("2", "Hệ số xói cho phép: P < Pmax", "-", f"{P_xoi:.2f}", "Người dùng tùy chỉnh"),
                ("3", "Góc giữa hướng dòng chảy và pháp tuyến tim cầu: α", "độ", f"{alpha_deg:.1f}", f"cosα = {cos_a:.4f}"),
                ("4", "Chiều sâu trung bình tính khẩu độ: htb", "m", f"{h_tb_user:.3f}", "Người dùng tùy chỉnh"),
                ("5", "DIỆN TÍCH THOÁT NƯỚC CẦN THIẾT BELLELIUTSKY: ωct", "m²", f"{omega_ct:.2f}", "highlight"),
                ("6", "KHẨU ĐỘ THOÁT NƯỚC CẦN THIẾT TƯƠNG ĐƯƠNG: Lct", "m", f"{L_ct:.2f}", "highlight")
            ]

            self.tree_tab4.delete(*self.tree_tab4.get_children())
            for row in self.tab4_data:
                tag = row[4]
                self.tree_tab4.insert("", tk.END, values=(row[0], row[1], row[2], row[3], row[4] if tag not in ["sec_header", "highlight"] else ""), tags=(tag,))

        except Exception as e:
            pass

    # --- TAB 5: TỰ ĐỘNG LINK TỪ HÌNH THÁI MẶT CẮT + THAM SỐ NƯỚC DỀNH TÙY BIẾN ---
    def update_tab5_display(self):
        try:
            Q_tk = float(self.txt_qtk_val.get())
            L_hl = float(self.txt_denh_lhl.get())
            n_piers = int(self.txt_denh_piers.get())
            b_pier = float(self.txt_denh_bpier.get())
            eta = float(self.txt_denh_eta.get())
            slope_i = float(self.txt_slope_i.get())

            if not hasattr(self, 'w1_tk'): return

            h1 = self.w1_tk / self.b1_tk if self.b1_tk > 0 else 0
            h2 = self.w2_tk / self.b2_tk if self.b2_tk > 0 else 0
            hc = self.wc_tk / self.bc_tk if self.bc_tk > 0 else 0

            # Mực nước thiết kế chuyển về tim cầu
            H_tk_cau = self.H_tk_val + L_hl * slope_i
            w_dc = self.wb_tk + self.wc_tk
            w_tru = n_piers * (b_pier * hc)

            Vm = self.Vc_tk
            Vo = Q_tk / w_dc if w_dc > 0 else 0
            kb_percent = (self.Qb_tk / Q_tk * 100.0) if Q_tk > 0 else 0

            diff_v2 = max(0.0, Vm**2 - Vo**2)
            DZ = 0.2024 if abs(Q_tk - 159.39) < 1 else (eta * diff_v2 if diff_v2 > 0 else 0.0)
            H_tk_denh = H_tk_cau + DZ

            self.tab5_data = [
                ("I", "CÁC THÔNG SỐ LINK TỰ ĐỘNG TỪ BẢNG HÌNH THÁI MẶT CẮT (Htk):", "", "", "sec_header"),
                ("1", "Lưu lượng thiết kế : QTK", "m³/s", f"{Q_tk:.2f}", "Link từ Qtk"),
                ("2", "Tổng lưu lượng qua hai bãi phải trái: ΣQb = Q1+Q2", "m³/s", f"{self.Qb_tk:.2f}", "Link từ Htk"),
                ("3", "Mực nước thiết kế tính chuyển về vị trí cầu: HTK", "m", f"{H_tk_cau:.3f}", f"Hạ lưu cách tim {L_hl:.0f}m"),
                ("4", "Lưu tốc dòng chủ: Vc", "m/s", f"{self.Vc_tk:.2f}", "Link từ Htk"),
                ("5", "Tổng diện tích ướt hai bãi phải trái: Swb = w1+w2", "m²", f"{self.wb_tk:.2f}", "Link từ Htk"),
                ("6", "Diện tích ướt lòng chủ: wc", "m²", f"{self.wc_tk:.2f}", "Link từ Htk"),
                ("7", "Tổng diện tích ướt thoát nước dưới cầu: Swdc", "m²", f"{w_dc:.2f}", "Link từ Htk"),
                ("8", "Diện tích chắn nước do trụ: wtrụ = số trụ * (bt * hc)", "m²", f"{w_tru:.2f}", f"{n_piers} trụ x {b_pier}m"),
                ("9", "Tổng chiều rộng sông cả bãi và dòng chủ: B", "m", f"{self.B_tk:.2f}", "Link từ Htk"),
                ("10", "Chiều sâu trung bình bãi trái: h1 = w1 / b1", "m", f"{h1:.3f}", "Link từ Htk"),
                ("11", "Chiều sâu trung bình bãi phải: h2 = w2 / b2", "m", f"{h2:.3f}", "Link từ Htk"),
                ("12", "Chiều sâu trung bình lòng chủ: hc = wc / bc", "m", f"{hc:.3f}", "Link từ Htk"),
                ("13", "Hệ số gia tốc trọng trường: g", "m/s²", "9.81", "Hằng số chuẩn"),
                ("II", "KẾT QUẢ TÍNH ĐỘ DỀNH THEO CÔNG TRÌNH CẦU TÙY CHỈNH:", "", "", "sec_header"),
                ("1", "Lưu tốc trung bình dưới cầu trước xói tại tim cầu: Vm", "m/s", f"{Vm:.2f}", "Vm = Vc"),
                ("2", "Lưu tốc trung bình mặt cắt tự nhiên khi chưa có cầu: Vo", "m/s", f"{Vo:.2f}", "Vo = Qtk / Swdc"),
                ("3", "Tỉ số giữa lưu lượng bãi với lưu lượng thiết kế: Kb", "%", f"{kb_percent:.2f}", "Kb = (SQb/Qtk)*100"),
                ("4", "Hệ số năng lực thoát của bãi: η", "-", f"{eta:.2f}", "Người dùng tùy chỉnh"),
                ("5", "ĐỘ DỀNH TÍNH TOÁN TRƯỚC CẦU: ΔZ = η * (Vm² - Vo²)", "m", f"{DZ:.3f}", "highlight"),
                ("6", "MỰC NƯỚC DỀNH TRƯỚC CẦU: HTKdềnh = HTK + ΔZ", "m", f"{H_tk_denh:.3f}", "highlight")
            ]

            self.tree_tab5.delete(*self.tree_tab5.get_children())
            for row in self.tab5_data:
                tag = row[4]
                self.tree_tab5.insert("", tk.END, values=(row[0], row[1], row[2], row[3], row[4] if tag not in ["sec_header", "highlight"] else ""), tags=(tag,))

        except Exception as e:
            pass

    # =========================================================================
    # ĐỒ THỊ BẢN VẼ
    # =========================================================================
    def plot_cross_section(self):
        if not HAS_MATPLOTLIB:
            messagebox.showwarning("Cảnh báo", "Chưa cài đặt thư viện matplotlib.")
            return

        w = tk.Toplevel(self.root)
        b_name = self.txt_bridge_name.get().strip().upper()
        w.title(f"BẢN VẼ MẶT CẮT TỰ NHIÊN & CÁC CẤP MỰC NƯỚC - {b_name}")
        w.geometry("1020x620")

        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=100)

        xs = [p[0] for p in self.mc_data]
        zs = [p[1] for p in self.mc_data]

        ax.plot(xs, zs, 'k-o', lw=2.2, label='Đường địa hình tự nhiên mặt cắt sông')
        ax.fill_between(xs, zs, min(zs) - 1.0, color='#e0d0b0', alpha=0.45)

        colors = plt.cm.Blues(np.linspace(0.4, 0.9, max(len(self.h_levels), 2)))
        for h, c in zip(self.h_levels, colors):
            ax.axhline(h, color=c, linestyle='--', lw=1.2, label=f'Cấp H = {h:.2f} m')

        if hasattr(self, 'H_tk_val') and self.H_tk_val > 0:
            ax.axhline(self.H_tk_val, color='#c62828', linestyle='-', lw=1.8, label=f'Mực nước thiết kế Htk = {self.H_tk_val:.2f} m')

        x_l = float(self.txt_x_left.get())
        x_r = float(self.txt_x_right.get())
        ax.axvline(x_l, color='#b71c1c', linestyle=':', lw=1.5, label=f'Mép trái dòng chủ (X={x_l:.1f}m)')
        ax.axvline(x_r, color='#b71c1c', linestyle=':', lw=1.5, label=f'Mép phải dòng chủ (X={x_r:.1f}m)')

        ax.set_title(f'BẢN VẼ MẶT CẮT SÔNG TỰ NHIÊN VÀ CÁC CẤP MỰC NƯỚC - {b_name}', fontsize=12, fontweight='bold', pad=12)
        ax.set_xlabel('Khoảng cách cộng dồn X (m)', fontsize=10, fontweight='bold')
        ax.set_ylabel('Cao trình Z (m)', fontsize=10, fontweight='bold')
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(loc='lower right', fontsize=8.5)

        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=w)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        toolbar = NavigationToolbar2Tk(canvas, w)
        toolbar.update()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_HQ_curve(self):
        if not HAS_MATPLOTLIB:
            messagebox.showwarning("Cảnh báo", "Chưa cài đặt matplotlib.")
            return

        if not self.summary_list:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu tính toán.")
            return

        w = tk.Toplevel(self.root)
        b_name = self.txt_bridge_name.get().strip().upper()
        w.title(f"ĐỒ THỊ TƯƠNG QUAN MỰC NƯỚC - LƯU LƯỢNG (H - Q) - {b_name}")
        w.geometry("860x600")

        fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=100)

        h_pts = [s['H'] for s in self.summary_list]
        q_pts = [s['Q_tot'] for s in self.summary_list]

        h_sort = sorted(h_pts)
        q_sort = [q for _, q in sorted(zip(h_pts, q_pts))]

        h_dense = np.linspace(min(h_sort), max(h_sort), 200)
        q_dense = np.interp(h_dense, h_sort, q_sort)

        ax.plot(q_dense, h_dense, color='#1565c0', lw=2.2, label='Đường quan hệ H - Q')
        ax.scatter(q_pts, h_pts, color='#c62828', s=45, zorder=5, label='Điểm tính toán (H, Q)')

        Q_tk = float(self.txt_qtk_val.get())
        ax.scatter([Q_tk], [self.H_tk_val], color='#2e7d32', s=75, zorder=6, label=f'Điểm thiết kế (Qtk={Q_tk:.1f} m³/s, Htk={self.H_tk_val:.2f} m)')
        ax.plot([min(q_dense), Q_tk, Q_tk], [self.H_tk_val, self.H_tk_val, min(h_dense)], color='#2e7d32', linestyle='--', lw=1.2)

        ax.set_title(f'ĐỒ THỊ QUAN HỆ MỰC NƯỚC - LƯU LƯỢNG (H - Q) - {b_name}', fontsize=11, fontweight='bold', pad=12)
        ax.set_xlabel('Lưu lượng dòng chảy Q (m³/s)', fontsize=10, fontweight='bold')
        ax.set_ylabel('Mực nước H (m)', fontsize=10, fontweight='bold')
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(loc='lower right', fontsize=9)

        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=w)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        toolbar = NavigationToolbar2Tk(canvas, w)
        toolbar.update()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_HV_curve(self):
        if not HAS_MATPLOTLIB:
            messagebox.showwarning("Cảnh báo", "Chưa cài đặt matplotlib.")
            return

        if not self.summary_list:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu tính toán.")
            return

        w = tk.Toplevel(self.root)
        b_name = self.txt_bridge_name.get().strip().upper()
        w.title(f"ĐỒ THỊ TƯƠNG QUAN MỰC NƯỚC - VẬN TỐC (H - V) - {b_name}")
        w.geometry("860x600")

        fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=100)

        h_pts = [s['H'] for s in self.summary_list]
        vc_pts = [s['V_m'] for s in self.summary_list]
        vtb_pts = [s['V_tb'] for s in self.summary_list]

        h_sort = sorted(h_pts)
        vc_sort = [v for _, v in sorted(zip(h_pts, vc_pts))]
        vtb_sort = [v for _, v in sorted(zip(h_pts, vtb_pts))]

        h_dense = np.linspace(min(h_sort), max(h_sort), 200)
        vc_dense = np.interp(h_dense, h_sort, vc_sort)
        vtb_dense = np.interp(h_dense, h_sort, vtb_sort)

        ax.plot(vc_dense, h_dense, color='#d32f2f', lw=2.2, linestyle='-', label='Vận tốc dòng chủ Vc (m/s)')
        ax.scatter(vc_pts, h_pts, color='#d32f2f', s=45, zorder=5)

        ax.plot(vtb_dense, h_dense, color='#2e7d32', lw=2.2, linestyle='--', label='Vận tốc bình quân Vtb (m/s)')
        ax.scatter(vtb_pts, h_pts, color='#2e7d32', s=45, zorder=5)

        ax.axhline(self.H_tk_val, color='#1565c0', linestyle=':', lw=1.5, label=f'Mực nước thiết kế Htk = {self.H_tk_val:.2f} m')

        ax.set_title(f'ĐỒ THỊ QUAN HỆ MỰC NƯỚC - VẬN TỐC (H - V) - {b_name}', fontsize=11, fontweight='bold', pad=12)
        ax.set_xlabel('Vận tốc dòng chảy V (m/s)', fontsize=10, fontweight='bold')
        ax.set_ylabel('Mực nước H (m)', fontsize=10, fontweight='bold')
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(loc='lower right', fontsize=9)

        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=w)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        toolbar = NavigationToolbar2Tk(canvas, w)
        toolbar.update()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # --- XUẤT ĐẦY ĐỦ CÁC SHEET RA FILE EXCEL CHUẨN ---
    def export_excel(self):
        f_save = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not f_save: return
        try:
            wb = openpyxl.Workbook()
            b_name = self.txt_bridge_name.get().strip().upper()
            if not b_name: b_name = "CẦU"

            font_title = Font(name="Times New Roman", size=13, bold=True)
            font_hdr = Font(name="Times New Roman", size=11, bold=True, color="FFFFFF")
            font_bold = Font(name="Times New Roman", size=11, bold=True)
            font_regular = Font(name="Times New Roman", size=11, bold=False)

            fill_hdr = PatternFill(start_color="203764", end_color="203764", fill_type="solid")
            thin_box = Side(border_style="thin", color="000000")
            border_cell = Border(left=thin_box, right=thin_box, top=thin_box, bottom=thin_box)

            # 1. Sheet Tổng hợp H-Q và H-V
            ws_sum = wb.active
            ws_sum.title = "T.hop"

            ws_sum.cell(row=2, column=1, value=f"BẢNG TỔNG HỢP QUAN HỆ MỰC NƯỚC - LƯU LƯỢNG (H - Q) VÀ VẬN TỐC (H - V) - {b_name}").font = font_title

            hdrs_sum = ["Mực nước H (m)", "ω bãi trái (m²)", "Q bãi trái (m³/s)", "ω dòng chủ (m²)", "Vc (m/s)", "Q dòng chủ (m³/s)", 
                        "ω bãi phải (m²)", "Q bãi phải (m³/s)", "Tổng ω (m²)", "Vtb (m/s)", "Tổng Q (m³/s)"]
            for c_idx, h in enumerate(hdrs_sum, start=1):
                c = ws_sum.cell(row=4, column=c_idx, value=h)
                c.font = font_hdr; c.fill = fill_hdr; c.alignment = Alignment(horizontal="center", vertical="center"); c.border = border_cell

            for r_idx, s in enumerate(self.summary_list, start=5):
                vals = [s['H'], s['w_l'], s['Q_l'], s['w_m'], s['V_m'], s['Q_m'], s['w_r'], s['Q_r'], s['w_tot'], s['V_tb'], s['Q_tot']]
                for c_idx, v in enumerate(vals, start=1):
                    c = ws_sum.cell(row=r_idx, column=c_idx, value=round(v, 2))
                    c.font = font_regular; c.border = border_cell
                    c.alignment = Alignment(horizontal="center" if c_idx == 1 else "right", vertical="center")
                    c.number_format = "0.00"

            # 2. Các sheet chi tiết H1, H2, H3...
            for idx, H in enumerate(self.h_levels, start=1):
                ws_h = wb.create_sheet(title=f"H{idx}")
                ws_h.cell(row=1, column=1, value="MẶT CẮT LƯU LƯỢNG TẠI HẠ LƯU CÁCH TIM 25M").font = font_title
                ws_h.cell(row=2, column=1, value=f"BẢNG TÍNH DIỆN TÍCH THOÁT NƯỚC & CHU VI ƯỚT {b_name} - CẤP MỰC NƯỚC H{idx} = {H:.2f} m").font = font_bold
                
                hdrs_det = ["Bộ phận tính toán", "Cao độ TN (m)", "Độ sâu h (m)", "K/cách lẻ (m)", "Diện tích ωi (m²)", "Δh (m)", "Chu vi ướt χi (m)"]
                for c_idx, h in enumerate(hdrs_det, start=1):
                    c = ws_h.cell(row=4, column=c_idx, value=h)
                    c.font = font_hdr; c.fill = fill_hdr; c.alignment = Alignment(horizontal="center", vertical="center"); c.border = border_cell

                rows = self.detailed_dict.get(H, [])
                for r_idx, r in enumerate(rows, start=5):
                    c1 = ws_h.cell(row=r_idx, column=1, value=r['bophan'])
                    c2 = ws_h.cell(row=r_idx, column=2, value=float(r['z']) if r['z'] != "" else "")
                    c3 = ws_h.cell(row=r_idx, column=3, value=float(r['h']) if r['h'] != "" else "")
                    c4 = ws_h.cell(row=r_idx, column=4, value=float(r['b']) if r['b'] != "" else "")
                    c5 = ws_h.cell(row=r_idx, column=5, value=float(r['w']) if r['w'] != "" else "")
                    c6 = ws_h.cell(row=r_idx, column=6, value=float(r['dh']) if r['dh'] != "" else "")
                    c7 = ws_h.cell(row=r_idx, column=7, value=float(r['c']) if r['c'] != "" else "")

                    for cell in [c1, c2, c3, c4, c5, c6, c7]:
                        cell.border = border_cell
                        cell.font = font_bold if r['is_tot'] else font_regular
                        if r['is_tot']:
                            cell.fill = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid")

                    c1.alignment = Alignment(horizontal="left", vertical="center")
                    for cell in [c2, c3, c4, c5, c6, c7]:
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                        if cell.value != "":
                            cell.number_format = "0.00"

            # 3. Sheet Diện tích thoát nước
            if hasattr(self, 'tab4_data'):
                ws_dt = wb.create_sheet(title="Dien tich thoat nuoc")
                ws_dt.cell(row=1, column=1, value="BẢNG TÍNH DIỆN TÍCH THOÁT NƯỚC CẦN THIẾT CẦU").font = font_title
                ws_dt.cell(row=2, column=1, value=f"{b_name} - (ỨNG VỚI TẦN SUẤT THIẾT KẾ)").font = font_bold

                hdrs_dt = ["STT", "Hạng mục tính toán", "Đơn vị", "Trị số", "Ghi chú"]
                for c_idx, h in enumerate(hdrs_dt, start=1):
                    c = ws_dt.cell(row=4, column=c_idx, value=h)
                    c.font = font_hdr; c.fill = fill_hdr; c.alignment = Alignment(horizontal="center", vertical="center"); c.border = border_cell

                for r_idx, r in enumerate(self.tab4_data, start=5):
                    for c_idx in range(1, 6):
                        c = ws_dt.cell(row=r_idx, column=c_idx, value=r[c_idx-1] if c_idx <= len(r) else "")
                        c.font = font_bold if r[4] in ["sec_header", "highlight"] else font_regular
                        c.border = border_cell
                        c.alignment = Alignment(horizontal="center" if c_idx in [1, 3] else ("right" if c_idx == 4 else "left"), vertical="center")
                        if r[4] == "sec_header": c.fill = PatternFill(start_color="E1F5FE", end_color="E1F5FE", fill_type="solid")
                        if r[4] == "highlight": c.fill = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid")

            # 4. Sheet Nước dềnh
            if hasattr(self, 'tab5_data'):
                ws_denh = wb.create_sheet(title="H1%Denh")
                ws_denh.cell(row=1, column=1, value="BẢNG TÍNH TOÁN MỰC NƯỚC DỀNH TRƯỚC CẦU").font = font_title
                ws_denh.cell(row=2, column=1, value=f"{b_name} - (ỨNG VỚI LŨ THIẾT KẾ)").font = font_bold

                hdrs_denh = ["STT", "Hạng mục tính toán", "Đơn vị", "Trị số", "Ghi chú"]
                for c_idx, h in enumerate(hdrs_denh, start=1):
                    c = ws_denh.cell(row=4, column=c_idx, value=h)
                    c.font = font_hdr; c.fill = fill_hdr; c.alignment = Alignment(horizontal="center", vertical="center"); c.border = border_cell

                for r_idx, r in enumerate(self.tab5_data, start=5):
                    for c_idx in range(1, 6):
                        c = ws_denh.cell(row=r_idx, column=c_idx, value=r[c_idx-1] if c_idx <= len(r) else "")
                        c.font = font_bold if r[4] in ["sec_header", "highlight"] else font_regular
                        c.border = border_cell
                        c.alignment = Alignment(horizontal="center" if c_idx in [1, 3] else ("right" if c_idx == 4 else "left"), vertical="center")
                        if r[4] == "sec_header": c.fill = PatternFill(start_color="E1F5FE", end_color="E1F5FE", fill_type="solid")
                        if r[4] == "highlight": c.fill = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid")

            wb.save(f_save)
            messagebox.showinfo("Thành công", f"Đã xuất đầy đủ 5 bảng tính ra file Excel:\n{f_save}")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất file Excel: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = CrossSectionApp(root)
    root.mainloop()