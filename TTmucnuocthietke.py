import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import pandas as pd

# Matplotlib nhúng vào giao diện Tkinter
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


class HydrologyBridgeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Phần Mềm Thủy Văn - Thủy Lực Công Trình Cầu (Đa Dự Án)")
        self.geometry("1180x820")
        self.minsize(980, 700)

        # Style giao diện
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("Treeview.Heading", font=("Arial", 9, "bold"))
        self.style.configure("Treeview", font=("Arial", 9), rowheight=24)

        # Biến lưu trữ hệ số hồi quy tương quan
        self.reg_a = None
        self.reg_b = None
        self.reg_r2 = None

        self.setup_ui()

    def setup_ui(self):
        # Tiêu đề trên cùng
        top_bar = tk.Frame(self, bg="#0d3b66", height=45)
        top_bar.pack(fill="x")
        lbl_title = tk.Label(
            top_bar, 
            text="HỆ THỐNG TÍNH TOÁN THỦY VĂN & MỰC NƯỚC THIẾT KẾ CẦU ĐƯỜNG", 
            fg="#ffffff", bg="#0d3b66", font=("Arial", 13, "bold"), pady=8
        )
        lbl_title.pack()

        # Notebook tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_survey = ttk.Frame(self.notebook)
        self.tab_corr = ttk.Frame(self.notebook)
        self.tab_slope = ttk.Frame(self.notebook)
        self.tab_report = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_survey, text=" 1. Điều Tra Vết Lũ & Gia Số (ΔHp) ")
        self.notebook.add(self.tab_corr, text=" 2. Tương Quan Thực Đo & Hồi Quy (a, b) ")
        self.notebook.add(self.tab_slope, text=" 3. Phân Tích Độ Dốc Thủy Lực (I) ")
        self.notebook.add(self.tab_report, text=" 4. Bảng Tổng Hợp & Xuất Báo Cáo ")

        self.build_tab_survey()
        self.build_tab_correlation()
        self.build_tab_slope()
        self.build_tab_report()

    # =========================================================================
    # TAB 1: ĐIỀU TRA VẾT LŨ LỚN & PHƯƠNG PHÁP GIA SỐ MỰC NƯỚC (ΔHp)
    # =========================================================================
    def build_tab_survey(self):
        paned = ttk.PanedWindow(self.tab_survey, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        # Cột trái: Nhập số liệu điều tra vết lũ
        frame_left = ttk.LabelFrame(paned, text="Số liệu vết lũ điều tra các năm tại các vị trí/cụm", padding=8)
        paned.add(frame_left, weight=4)

        f_input_survey = ttk.Frame(frame_left)
        f_input_survey.pack(fill="x", pady=4)

        ttk.Label(f_input_survey, text="Năm:").grid(row=0, column=0, padx=2, sticky="w")
        self.ent_surv_year = ttk.Entry(f_input_survey, width=8)
        self.ent_surv_year.insert(0, "2020")
        self.ent_surv_year.grid(row=0, column=1, padx=4)

        ttk.Label(f_input_survey, text="Vị trí/Cụm:").grid(row=0, column=2, padx=2, sticky="w")
        self.ent_surv_loc = ttk.Entry(f_input_survey, width=12)
        self.ent_surv_loc.insert(0, "Cụm 2 (Tim Cầu)")
        self.ent_surv_loc.grid(row=0, column=3, padx=4)

        ttk.Label(f_input_survey, text="H vết lũ (m):").grid(row=0, column=4, padx=2, sticky="w")
        self.ent_surv_h = ttk.Entry(f_input_survey, width=9)
        self.ent_surv_h.insert(0, "3.10")
        self.ent_surv_h.grid(row=0, column=5, padx=4)

        btn_add_surv = ttk.Button(f_input_survey, text="+ Thêm Vết Lũ", command=self.add_survey_point)
        btn_add_surv.grid(row=0, column=6, padx=6)

        btn_del_surv = ttk.Button(f_input_survey, text="Xóa Dòng Chọn", command=self.del_survey_point)
        btn_del_surv.grid(row=0, column=7, padx=2)

        # Bảng vết lũ
        self.tree_survey = ttk.Treeview(frame_left, columns=("year", "loc", "h", "status"), show="headings", height=8)
        self.tree_survey.heading("year", text="Năm lũ")
        self.tree_survey.heading("loc", text="Vị trí / Cụm quan sát")
        self.tree_survey.heading("h", text="Cao độ H điều tra (m)")
        self.tree_survey.heading("status", text="Vai trò chọn tính")
        self.tree_survey.column("year", width=70, anchor="center")
        self.tree_survey.column("loc", width=160, anchor="w")
        self.tree_survey.column("h", width=120, anchor="center")
        self.tree_survey.column("status", width=110, anchor="center")
        self.tree_survey.pack(fill="both", expand=True, pady=5)

        btn_pick_base = ttk.Button(frame_left, text="★ Chọn Dòng Này Làm Mực Nước Lũ Mốc Tại Cầu (Hmax.cầu)", command=self.set_base_flood)
        btn_pick_base.pack(pady=4)

        # Mực nước trạm TV mốc
        f_base_tv = ttk.Frame(frame_left)
        f_base_tv.pack(fill="x", pady=6)
        ttk.Label(f_base_tv, text="H lũ mốc tại Trạm TV tương ứng (m):").pack(side="left")
        self.ent_base_tv = ttk.Entry(f_base_tv, width=10)
        self.ent_base_tv.insert(0, "13.42")
        self.ent_base_tv.pack(side="left", padx=6)

        self.lbl_selected_base = ttk.Label(frame_left, text="Mốc tại Cầu hiện chọn: Hmax = 3.10 m (Cụm 2)", font=("Arial", 9, "bold"), foreground="#0066cc")
        self.lbl_selected_base.pack(pady=2)

        # Cột phải: Bảng tần suất trạm TV và tính toán ΔHp
        frame_right = ttk.LabelFrame(paned, text="Tính toán mực nước thiết kế theo Gia số ΔHp", padding=8)
        paned.add(frame_right, weight=5)

        # Bảng nhập tần suất
        f_freq_in = ttk.Frame(frame_right)
        f_freq_in.pack(fill="x", pady=4)
        ttk.Label(f_freq_in, text="Tần suất:").grid(row=0, column=0, padx=2)
        self.ent_freq_name = ttk.Entry(f_freq_in, width=8)
        self.ent_freq_name.insert(0, "H1%")
        self.ent_freq_name.grid(row=0, column=1, padx=4)

        ttk.Label(f_freq_in, text="H trạm TV (m):").grid(row=0, column=2, padx=2)
        self.ent_freq_val = ttk.Entry(f_freq_in, width=9)
        self.ent_freq_val.insert(0, "13.68")
        self.ent_freq_val.grid(row=0, column=3, padx=4)

        ttk.Label(f_freq_in, text="+ BĐKH (m):").grid(row=0, column=4, padx=2)
        self.ent_freq_bdkh = ttk.Entry(f_freq_in, width=7)
        self.ent_freq_bdkh.insert(0, "0.43")
        self.ent_freq_bdkh.grid(row=0, column=5, padx=4)

        btn_add_freq = ttk.Button(f_freq_in, text="+ Thêm TS", command=self.add_freq_point)
        btn_add_freq.grid(row=0, column=6, padx=4)

        btn_del_freq = ttk.Button(f_freq_in, text="Xóa TS", command=self.del_freq_point)
        btn_del_freq.grid(row=0, column=7, padx=2)

        self.tree_freq = ttk.Treeview(frame_right, columns=("freq", "htv", "bdkh", "dh", "hcau", "hbdkh"), show="headings", height=8)
        self.tree_freq.heading("freq", text="Tần suất")
        self.tree_freq.heading("htv", text="H trạm TV (m)")
        self.tree_freq.heading("bdkh", text="Mức BĐKH")
        self.tree_freq.heading("dh", text="ΔHp (m)")
        self.tree_freq.heading("hcau", text="H cầu TK (m)")
        self.tree_freq.heading("hbdkh", text="H cầu + BĐKH (m)")
        for c in ("freq", "htv", "bdkh", "dh", "hcau", "hbdkh"):
            self.tree_freq.column(c, width=85, anchor="center")
        self.tree_freq.pack(fill="both", expand=True, pady=6)

        btn_run_m1 = ttk.Button(frame_right, text="▶ Tính Mực Nước Cầu Theo Gia Số (PP1)", command=self.calc_increment_method)
        btn_run_m1.pack(pady=4)

        self.init_default_survey_data()

    def init_default_survey_data(self):
        # Dữ liệu mẫu ban đầu
        defaults = [
            ("2020", "Cụm 1 (Thượng lưu)", "3.15", ""),
            ("2020", "Cụm 2 (Tim cầu)", "3.10", "Chọn làm mốc"),
            ("2020", "Cụm 3 (Hạ lưu)", "3.04", ""),
            ("2021", "Cụm 2 (Tim cầu)", "2.65", ""),
            ("2022", "Cụm 2 (Tim cầu)", "2.40", "")
        ]
        for row in defaults:
            self.tree_survey.insert("", "end", values=row)

        default_freqs = [
            ("H1%", "13.68", "0.43"),
            ("H1.5%", "13.45", "0.00"),
            ("H4%", "13.39", "0.20"),
            ("H5%", "13.20", "0.00"),
            ("H10%", "12.80", "0.00")
        ]
        for f, h, b in default_freqs:
            self.tree_freq.insert("", "end", values=(f, h, b, "", "", ""))

    def add_survey_point(self):
        y = self.ent_surv_year.get().strip()
        loc = self.ent_surv_loc.get().strip()
        h = self.ent_surv_h.get().strip()
        if not y or not loc or not h:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập đầy đủ Năm, Vị trí và Mực nước!")
            return
        self.tree_survey.insert("", "end", values=(y, loc, h, ""))

    def del_survey_point(self):
        sel = self.tree_survey.selection()
        for item in sel:
            self.tree_survey.delete(item)

    def set_base_flood(self):
        sel = self.tree_survey.selection()
        if not sel:
            messagebox.showinfo("Chọn dòng", "Hãy chọn một dòng vết lũ trong bảng để làm mốc!")
            return
        # Xóa đánh dấu cũ
        for item in self.tree_survey.get_children():
            vals = list(self.tree_survey.item(item, "values"))
            vals[3] = ""
            self.tree_survey.item(item, values=vals)

        item = sel[0]
        vals = list(self.tree_survey.item(item, "values"))
        vals[3] = "Chọn làm mốc"
        self.tree_survey.item(item, values=vals)
        self.lbl_selected_base.config(text=f"Mốc tại Cầu hiện chọn: Hmax = {vals[2]} m ({vals[1]} - Năm {vals[0]})")

    def add_freq_point(self):
        f = self.ent_freq_name.get().strip()
        h = self.ent_freq_val.get().strip()
        b = self.ent_freq_bdkh.get().strip()
        if not f or not h:
            return
        self.tree_freq.insert("", "end", values=(f, h, b if b else "0.00", "", "", ""))

    def del_freq_point(self):
        for item in self.tree_freq.selection():
            self.tree_freq.delete(item)

    def calc_increment_method(self):
        try:
            # Tìm mốc cầu
            base_bridge_h = None
            for item in self.tree_survey.get_children():
                vals = self.tree_survey.item(item, "values")
                if vals[3] == "Chọn làm mốc":
                    base_bridge_h = float(vals[2])
                    break
            if base_bridge_h is None:
                messagebox.showwarning("Chưa chọn mốc", "Vui lòng chọn 1 dòng vết lũ làm mốc tính toán tại Cầu!")
                return

            base_tv_h = float(self.ent_base_tv.get())

            # Tính chuyển dịch cho từng tần suất
            for item in self.tree_freq.get_children():
                vals = list(self.tree_freq.item(item, "values"))
                h_tv = float(vals[1])
                bdkh = float(vals[2]) if vals[2] else 0.0

                dh = h_tv - base_tv_h
                h_cau = base_bridge_h + dh
                h_cau_bdkh = h_cau + bdkh if bdkh > 0 else h_cau

                vals[3] = f"{dh:+.3f}"
                vals[4] = f"{h_cau:.3f}"
                vals[5] = f"{h_cau_bdkh:.3f}" if bdkh > 0 else "-"
                self.tree_freq.item(item, values=vals)

            messagebox.showinfo("Thành công", "Đã tính toán xong mực nước theo phương pháp gia số!")
        except Exception as e:
            messagebox.showerror("Lỗi tính toán", str(e))

    # =========================================================================
    # TAB 2: TƯƠNG QUAN THỰC ĐO & TỰ ĐỘNG TÌM HỆ SỐ HỒI QUY (a, b) + ĐỒ THỊ
    # =========================================================================
    def build_tab_correlation(self):
        paned = ttk.PanedWindow(self.tab_corr, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        # Bên trái: Nhập điểm thực đo
        frame_data = ttk.LabelFrame(paned, text="Chuỗi điểm đo đồng thời (H_trạm TV - H_cầu)", padding=8)
        paned.add(frame_data, weight=4)

        f_input_corr = ttk.Frame(frame_data)
        f_input_corr.pack(fill="x", pady=4)

        ttk.Label(f_input_corr, text="H Trạm TV (X):").grid(row=0, column=0, padx=2)
        self.ent_corr_x = ttk.Entry(f_input_corr, width=10)
        self.ent_corr_x.grid(row=0, column=1, padx=4)

        ttk.Label(f_input_corr, text="H Cầu/CT (Y):").grid(row=0, column=2, padx=2)
        self.ent_corr_y = ttk.Entry(f_input_corr, width=10)
        self.ent_corr_y.grid(row=0, column=3, padx=4)

        btn_add_pt = ttk.Button(f_input_corr, text="+ Thêm Điểm", command=self.add_corr_point)
        btn_add_pt.grid(row=0, column=4, padx=4)

        btn_del_pt = ttk.Button(f_input_corr, text="Xóa Điểm", command=self.del_corr_point)
        btn_del_pt.grid(row=0, column=5, padx=2)

        self.tree_corr = ttk.Treeview(frame_data, columns=("idx", "x", "y"), show="headings", height=9)
        self.tree_corr.heading("idx", text="STT")
        self.tree_corr.heading("x", text="H Trạm TV (m)")
        self.tree_corr.heading("y", text="H Cầu thực đo (m)")
        self.tree_corr.column("idx", width=50, anchor="center")
        self.tree_corr.column("x", width=140, anchor="center")
        self.tree_corr.column("y", width=140, anchor="center")
        self.tree_corr.pack(fill="both", expand=True, pady=5)

        # Nút tính tương quan và nhập nhanh từ file
        f_actions = ttk.Frame(frame_data)
        f_actions.pack(fill="x", pady=4)
        btn_calc_fit = ttk.Button(f_actions, text="▶ Tính Hồi Quy & Vẽ Biểu Đồ", command=self.fit_correlation)
        btn_calc_fit.pack(side="left", padx=4)

        btn_import_pts = ttk.Button(f_actions, text="Nhập Cặp Điểm Từ Excel/CSV", command=self.import_corr_data)
        btn_import_pts.pack(side="left", padx=4)

        # Khung kết quả hồi quy
        f_reg_res = ttk.LabelFrame(frame_data, text="Phương trình tương quan xác định được", padding=8)
        f_reg_res.pack(fill="x", pady=6)

        self.lbl_eqn = ttk.Label(f_reg_res, text="Phương trình: H_cầu = a · H_trạm + b", font=("Arial", 10, "bold"), foreground="#990000")
        self.lbl_eqn.pack(anchor="w", pady=2)

        self.lbl_stat = ttk.Label(f_reg_res, text="Hệ số: a = ... | b = ... | R² = ... | R = ...", font=("Arial", 9))
        self.lbl_stat.pack(anchor="w", pady=2)

        btn_apply_corr = ttk.Button(f_reg_res, text="Áp Dụng Phương Trình Này Để Tính Thiết Kế", command=self.apply_corr_to_design)
        btn_apply_corr.pack(anchor="w", pady=4)

        # Khung tính mực nước kiệt & thông thuyền
        f_low_water = ttk.LabelFrame(frame_data, text="Tính mực nước kiệt & thông thuyền theo quan trắc trạm TV", padding=8)
        f_low_water.pack(fill="x", pady=6)

        ttk.Label(f_low_water, text="H kiệt trạm TV (30 năm) (m):").grid(row=0, column=0, sticky="w", pady=2)
        self.ent_hmin_station = ttk.Entry(f_low_water, width=8)
        self.ent_hmin_station.insert(0, "1.20")
        self.ent_hmin_station.grid(row=0, column=1, padx=4)

        self.lbl_hmin_res = ttk.Label(f_low_water, text="-> H kiệt tại Cầu: ...", font=("Arial", 9, "bold"))
        self.lbl_hmin_res.grid(row=0, column=2, padx=8)

        ttk.Label(f_low_water, text="H 98% giờ trạm TV (m):").grid(row=1, column=0, sticky="w", pady=2)
        self.ent_h98_station = ttk.Entry(f_low_water, width=8)
        self.ent_h98_station.insert(0, "1.85")
        self.ent_h98_station.grid(row=1, column=1, padx=4)

        self.lbl_h98_res = ttk.Label(f_low_water, text="-> H thông thuyền tại Cầu: ...", font=("Arial", 9, "bold"))
        self.lbl_h98_res.grid(row=1, column=2, padx=8)

        # Bên phải: Đồ thị Matplotlib nhúng trực tiếp
        frame_plot = ttk.LabelFrame(paned, text="Đồ thị hồi quy tương quan thực nghiệm", padding=6)
        paned.add(frame_plot, weight=6)

        self.fig = Figure(figsize=(5.5, 4.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Đường Tương Quan H_cầu = f(H_trạm)", fontsize=10, fontweight="bold")
        self.ax.set_xlabel("Mực nước Trạm Thủy Văn (m)")
        self.ax.set_ylabel("Mực nước tại Cầu (m)")
        self.ax.grid(True, linestyle="--", alpha=0.6)

        self.canvas = FigureCanvasTkAgg(self.fig, master=frame_plot)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, frame_plot)
        toolbar.update()
        toolbar.pack(fill="x")

        self.init_default_corr_data()

    def init_default_corr_data(self):
        # Dữ liệu thực nghiệm mẫu
        pts = [
            (10.50, 1.15),
            (11.20, 1.62),
            (12.00, 2.14),
            (12.80, 2.68),
            (13.34, 3.05),
            (13.42, 3.10)
        ]
        for i, (x, y) in enumerate(pts, start=1):
            self.tree_corr.insert("", "end", values=(i, f"{x:.2f}", f"{y:.2f}"))

    def add_corr_point(self):
        x = self.ent_corr_x.get().strip()
        y = self.ent_corr_y.get().strip()
        if not x or not y:
            return
        idx = len(self.tree_corr.get_children()) + 1
        self.tree_corr.insert("", "end", values=(idx, x, y))

    def del_corr_point(self):
        for item in self.tree_corr.selection():
            self.tree_corr.delete(item)

    def fit_correlation(self):
        pts_x = []
        pts_y = []
        for item in self.tree_corr.get_children():
            vals = self.tree_corr.item(item, "values")
            try:
                pts_x.append(float(vals[1]))
                pts_y.append(float(vals[2]))
            except ValueError:
                continue

        if len(pts_x) < 2:
            messagebox.showwarning("Thiếu dữ liệu", "Cần ít nhất 2 cặp điểm thực đo để lập hồi quy!")
            return

        x = np.array(pts_x)
        y = np.array(pts_y)

        # Tính hồi quy tuyến tính y = a*x + b
        A = np.vstack([x, np.ones(len(x))]).T
        a, b = np.linalg.lstsq(A, y, rcond=None)[0]

        # Đánh giá R2 và R
        y_pred = a * x + b
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 1.0
        r_corr = np.corrcoef(x, y)[0, 1] if len(x) > 1 else 1.0

        self.reg_a = a
        self.reg_b = b
        self.reg_r2 = r2

        sign = "+" if b >= 0 else "-"
        self.lbl_eqn.config(text=f"Phương trình: H_cầu = {a:.4f} · H_trạm {sign} {abs(b):.4f}")
        self.lbl_stat.config(text=f"a = {a:.4f} | b = {b:.4f} | R² = {r2:.4f} | R = {r_corr:.4f} (Tương quan chặt)")

        # Tính mực nước kiệt & thông thuyền
        try:
            if self.ent_hmin_station.get():
                hmin_st = float(self.ent_hmin_station.get())
                hmin_bridge = a * hmin_st + b
                self.lbl_hmin_res.config(text=f"-> H kiệt tại Cầu: {hmin_bridge:.3f} m")
            if self.ent_h98_station.get():
                h98_st = float(self.ent_h98_station.get())
                h98_bridge = a * h98_st + b
                self.lbl_h98_res.config(text=f"-> H thông thuyền tại Cầu: {h98_bridge:.3f} m")
        except Exception:
            pass

        # Vẽ lại đồ thị
        self.ax.clear()
        self.ax.scatter(x, y, color="#e63946", s=45, label="Điểm thực đo đồng thời", zorder=3)

        x_line = np.linspace(min(x) * 0.95, max(x) * 1.05, 100)
        y_line = a * x_line + b
        self.ax.plot(x_line, y_line, color="#1d3557", linewidth=2, label=f"y = {a:.3f}x {sign} {abs(b):.3f}")

        self.ax.set_title(f"Tương Quan Tuyến Tính (R² = {r2:.4f})", fontsize=10, fontweight="bold")
        self.ax.set_xlabel("Mực nước Trạm Thủy Văn (m)")
        self.ax.set_ylabel("Mực nước tại Cầu (m)")
        self.ax.legend(loc="upper left", fontsize=9)
        self.ax.grid(True, linestyle="--", alpha=0.6)
        self.canvas.draw()

    def apply_corr_to_design(self):
        if self.reg_a is None or self.reg_b is None:
            messagebox.showinfo("Chưa tính", "Vui lòng bấm 'Tính Hồi Quy & Vẽ Biểu Đồ' trước!")
            return
        # Chuyển kết quả sang Tab 4
        self.load_summary_table()
        self.notebook.select(self.tab_report)
        messagebox.showinfo("Đã áp dụng", "Hệ số tương quan đã được áp dụng vào bảng so sánh thiết kế ở Tab 4!")

    def import_corr_data(self):
        file_path = filedialog.askopenfilename(filetypes=[("Data Files", "*.xlsx *.csv")])
        if not file_path:
            return
        try:
            if file_path.endswith(".xlsx"):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path)

            cols = df.columns
            if len(cols) < 2:
                messagebox.showerror("Lỗi file", "File cần ít nhất 2 cột dữ liệu (X và Y)!")
                return

            for item in self.tree_corr.get_children():
                self.tree_corr.delete(item)

            for i, row in df.iterrows():
                self.tree_corr.insert("", "end", values=(i+1, f"{float(row[0]):.3f}", f"{float(row[1]):.3f}"))
            messagebox.showinfo("Thành công", f"Đã nhập {len(df)} dòng dữ liệu từ file!")
        except Exception as e:
            messagebox.showerror("Lỗi đọc file", str(e))

    # =========================================================================
    # TAB 3: MÔ HÌNH THỦY LỰC - PHÂN TÍCH ĐỘ DỐC DỌC TUYẾN SÔNG (I)
    # =========================================================================
    def build_tab_slope(self):
        paned = ttk.PanedWindow(self.tab_slope, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        frame_left = ttk.LabelFrame(paned, text="Danh sách các cọc / mặt cắt quan trắc dọc sông", padding=8)
        paned.add(frame_left, weight=5)

        f_in = ttk.Frame(frame_left)
        f_in.pack(fill="x", pady=4)

        ttk.Label(f_in, text="Mặt cắt:").grid(row=0, column=0, padx=2)
        self.ent_cs_name = ttk.Entry(f_in, width=12)
        self.ent_cs_name.insert(0, "Cọc mới")
        self.ent_cs_name.grid(row=0, column=1, padx=4)

        ttk.Label(f_in, text="Lý trình (m):").grid(row=0, column=2, padx=2)
        self.ent_cs_dist = ttk.Entry(f_in, width=9)
        self.ent_cs_dist.insert(0, "2000")
        self.ent_cs_dist.grid(row=0, column=3, padx=4)

        ttk.Label(f_in, text="H vết lũ (m):").grid(row=0, column=4, padx=2)
        self.ent_cs_h = ttk.Entry(f_in, width=9)
        self.ent_cs_h.insert(0, "8.50")
        self.ent_cs_h.grid(row=0, column=5, padx=4)

        btn_add_cs = ttk.Button(f_in, text="+ Thêm", command=self.add_slope_point)
        btn_add_cs.grid(row=0, column=6, padx=4)

        btn_del_cs = ttk.Button(f_in, text="Xóa", command=self.del_slope_point)
        btn_del_cs.grid(row=0, column=7, padx=2)

        self.tree_slope = ttk.Treeview(frame_left, columns=("name", "dist", "h", "slope"), show="headings", height=10)
        self.tree_slope.heading("name", text="Mặt cắt / Vị trí")
        self.tree_slope.heading("dist", text="Lý trình/Khoảng cách (m)")
        self.tree_slope.heading("h", text="Cao độ H (m)")
        self.tree_slope.heading("slope", text="Độ dốc I tới cọc sau (‰)")
        self.tree_slope.column("name", width=140, anchor="w")
        self.tree_slope.column("dist", width=120, anchor="center")
        self.tree_slope.column("h", width=90, anchor="center")
        self.tree_slope.column("slope", width=120, anchor="center")
        self.tree_slope.pack(fill="both", expand=True, pady=6)

        btn_calc_slope = ttk.Button(frame_left, text="▶ Phân Tích Độ Dốc & Vẽ Trắc Dọc Lũ", command=self.calc_hydraulic_slopes)
        btn_calc_slope.pack(pady=4)

        # Bên phải: Đồ thị trắc dọc mặt nước
        frame_plot_slope = ttk.LabelFrame(paned, text="Trắc dọc đường mặt nước lũ", padding=6)
        paned.add(frame_plot_slope, weight=5)

        self.fig_slope = Figure(figsize=(5, 4), dpi=100)
        self.ax_slope = self.fig_slope.add_subplot(111)
        self.ax_slope.set_title("Trắc Dọc Mực Nước Lũ Dọc Sông", fontsize=10, fontweight="bold")
        self.ax_slope.set_xlabel("Khoảng cách dồn (m)")
        self.ax_slope.set_ylabel("Cao trình mực nước (m)")
        self.ax_slope.grid(True, linestyle="--", alpha=0.6)

        self.canvas_slope = FigureCanvasTkAgg(self.fig_slope, master=frame_plot_slope)
        self.canvas_slope.draw()
        self.canvas_slope.get_tk_widget().pack(fill="both", expand=True)

        self.init_default_slope_data()

    def init_default_slope_data(self):
        # Dữ liệu trích từ file gốc
        mc_data = [
            ("Trạm TV Đồng Trăng", "0", "13.34"),
            ("Thượng lưu cầu", "3820", "5.80"),
            ("Tim Cầu Nghiên Cứu", "5000", "3.10"),
            ("Hạ lưu cầu", "5370", "2.75")
        ]
        for row in mc_data:
            self.tree_slope.insert("", "end", values=(row[0], row[1], row[2], ""))

    def add_slope_point(self):
        name = self.ent_cs_name.get().strip()
        dist = self.ent_cs_dist.get().strip()
        h = self.ent_cs_h.get().strip()
        if not name or not dist or not h:
            return
        self.tree_slope.insert("", "end", values=(name, dist, h, ""))

    def del_slope_point(self):
        for item in self.tree_slope.selection():
            self.tree_slope.delete(item)

    def calc_hydraulic_slopes(self):
        rows = []
        for item in self.tree_slope.get_children():
            v = self.tree_slope.item(item, "values")
            rows.append({"item": item, "name": v[0], "dist": float(v[1]), "h": float(v[2])})

        if len(rows) < 2:
            messagebox.showwarning("Cảnh báo", "Cần ít nhất 2 mặt cắt để tính độ dốc!")
            return

        # Sắp xếp theo lý trình
        rows.sort(key=lambda x: x["dist"])

        # Tính độ dốc từng đoạn I = (H1 - H2) / (X2 - X1)
        for i in range(len(rows) - 1):
            dx = rows[i+1]["dist"] - rows[i]["dist"]
            dh = rows[i]["h"] - rows[i+1]["h"]
            slope_promille = (dh / dx * 1000) if dx > 0 else 0.0

            item = rows[i]["item"]
            old_v = list(self.tree_slope.item(item, "values"))
            old_v[3] = f"{slope_promille:.3f}"
            self.tree_slope.item(item, values=old_v)

        last_item = rows[-1]["item"]
        last_v = list(self.tree_slope.item(last_item, "values"))
        last_v[3] = "-"
        self.tree_slope.item(last_item, values=last_v)

        # Vẽ trắc dọc
        x_pts = [r["dist"] for r in rows]
        y_pts = [r["h"] for r in rows]
        names = [r["name"] for r in rows]

        self.ax_slope.clear()
        self.ax_slope.plot(x_pts, y_pts, marker="o", color="#2a9d8f", linewidth=2.2, label="Đường mặt nước lũ")
        for x, y, name in zip(x_pts, y_pts, names):
            self.ax_slope.annotate(f"{name}\n({y:.2f}m)", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)

        self.ax_slope.set_title("Trắc Dọc Mực Nước Lũ", fontsize=10, fontweight="bold")
        self.ax_slope.set_xlabel("Khoảng cách dọc sông L (m)")
        self.ax_slope.set_ylabel("Cao độ mực nước (m)")
        self.ax_slope.grid(True, linestyle="--", alpha=0.6)
        self.ax_slope.legend()
        self.canvas_slope.draw()

    # =========================================================================
    # TAB 4: BẢNG TỔNG HỢP SO SÁNH & XUẤT BÁO CÁO EXCEL ĐA NĂNG
    # =========================================================================
    def build_tab_report(self):
        f_top = ttk.Frame(self.tab_report, padding=10)
        f_top.pack(fill="x")

        btn_load = ttk.Button(f_top, text="🔄 Cập Nhật / Tổng Hợp Kết Quả Các PP", command=self.load_summary_table)
        btn_load.pack(side="left", padx=5)

        btn_export = ttk.Button(f_top, text="💾 Xuất Toàn Bộ Báo Cáo Ra File Excel (.xlsx)", command=self.export_excel_complete)
        btn_export.pack(side="left", padx=10)

        # Bảng so sánh
        self.tree_summary = ttk.Treeview(self.tab_report, columns=("freq", "htv", "m1_cau", "m1_bdkh", "m2_cau", "diff"), show="headings", height=12)
        self.tree_summary.heading("freq", text="Tần suất P%")
        self.tree_summary.heading("htv", text="H Trạm TV (m)")
        self.tree_summary.heading("m1_cau", text="PP1: Gia số ΔHp (m)")
        self.tree_summary.heading("m1_bdkh", text="PP1: Xét BĐKH (m)")
        self.tree_summary.heading("m2_cau", text="PP2: Hồi quy (m)")
        self.tree_summary.heading("diff", text="Chênh lệch PP1 - PP2 (m)")

        for c in ("freq", "htv", "m1_cau", "m1_bdkh", "m2_cau", "diff"):
            self.tree_summary.column(c, width=150, anchor="center")
        self.tree_summary.pack(fill="both", expand=True, padx=10, pady=8)

        # Thông tin kết luận
        self.txt_summary = tk.Text(self.tab_report, height=6, font=("Arial", 10), bg="#fcfcfc")
        self.txt_summary.pack(fill="x", padx=10, pady=6)
        self.txt_summary.insert("1.0", "HƯỚNG DẪN ĐÁNH GIÁ CHỌN MỰC NƯỚC THIẾT KẾ CẦU:\n"
                                       "- Nếu tương quan chặt chẽ (R² > 0.85): Khuyến nghị ưu tiên PP2 (Hồi quy tương quan) vì phản ánh quy luật thủy lực liên tục.\n"
                                       "- Nếu chuỗi thực đo đồng thời ít (< 3 trận lũ): Ưu tiên PP1 (Gia số vết lũ lịch sử) để đảm bảo an toàn chịu lũ.\n"
                                       "- Luôn đối chứng cao độ giữa 2 phương pháp trước khi quyết định cao độ đáy dầm và khổ tĩnh không cầu.")
        self.txt_summary.config(state="disabled")

    def load_summary_table(self):
        for item in self.tree_summary.get_children():
            self.tree_summary.delete(item)

        for item in self.tree_freq.get_children():
            vals = self.tree_freq.item(item, "values")
            freq = vals[0]
            try:
                h_tv = float(vals[1])
            except ValueError:
                continue

            h_m1 = vals[4] if len(vals) > 4 and vals[4] else "-"
            h_m1_bdkh = vals[5] if len(vals) > 5 and vals[5] else "-"

            if self.reg_a is not None and self.reg_b is not None:
                h_m2_val = self.reg_a * h_tv + self.reg_b
                h_m2_str = f"{h_m2_val:.3f}"
            else:
                h_m2_str = "-"

            # Tính chênh lệch
            if h_m1 != "-" and h_m2_str != "-":
                diff = f"{float(h_m1) - float(h_m2_str):+.3f}"
            else:
                diff = "-"

            self.tree_summary.insert("", "end", values=(freq, f"{h_tv:.3f}", h_m1, h_m1_bdkh, h_m2_str, diff))

    def export_excel_complete(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")]
        )
        if not file_path:
            return

        try:
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                # Sheet 1: Điều tra vết lũ
                surv_list = []
                for item in self.tree_survey.get_children():
                    surv_list.append(self.tree_survey.item(item, "values"))
                pd.DataFrame(surv_list, columns=["Năm", "Vị trí", "H điều tra (m)", "Mốc"]).to_excel(writer, sheet_name="Vet_Lu_Dieu_Tra", index=False)

                # Sheet 2: Tính PP1 (Gia số)
                freq_list = []
                for item in self.tree_freq.get_children():
                    freq_list.append(self.tree_freq.item(item, "values"))
                pd.DataFrame(freq_list, columns=["Tần suất", "H trạm TV", "Mức BĐKH", "ΔHp", "H cầu", "H cầu + BĐKH"]).to_excel(writer, sheet_name="PP1_Gia_So", index=False)

                # Sheet 3: Thực đo & hồi quy PP2
                corr_list = []
                for item in self.tree_corr.get_children():
                    corr_list.append(self.tree_corr.item(item, "values"))
                df_corr = pd.DataFrame(corr_list, columns=["STT", "H Trạm TV", "H Cầu"])
                if self.reg_a is not None:
                    df_corr["Hệ số a"] = self.reg_a
                    df_corr["Hệ số b"] = self.reg_b
                    df_corr["R2"] = self.reg_r2
                df_corr.to_excel(writer, sheet_name="PP2_Tuong_Quan", index=False)

                # Sheet 4: Độ dốc I
                slope_list = []
                for item in self.tree_slope.get_children():
                    slope_list.append(self.tree_slope.item(item, "values"))
                pd.DataFrame(slope_list, columns=["Mặt cắt", "Lý trình (m)", "Cao độ H (m)", "Độ dốc I (‰)"]).to_excel(writer, sheet_name="PP3_Do_Doc_Thuy_Luc", index=False)

                # Sheet 5: Tổng hợp so sánh
                summary_list = []
                for item in self.tree_summary.get_children():
                    summary_list.append(self.tree_summary.item(item, "values"))
                pd.DataFrame(summary_list, columns=["Tần suất", "H trạm TV", "PP1: Gia số", "PP1: Có BĐKH", "PP2: Hồi quy", "Chênh lệch"]).to_excel(writer, sheet_name="Tong_Hop_So_Sanh", index=False)

            messagebox.showinfo("Thành công", f"Báo cáo toàn diện dự án đã được xuất tại:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất file", str(e))


if __name__ == "__main__":
    app = HydrologyBridgeApp()
    app.mainloop()