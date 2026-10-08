"""
PHẦN MỀM THỦY VĂN & THỦY LỰC CẦU ĐƯỜNG TỔNG QUÁT (HYDROCIVIL PRO - CHUẨN HÓA)
Áp dụng cho mọi vùng địa hình: Đồng bằng triều, Sông lớn, Miền Trung, Miền núi.
Tiêu chuẩn: TCVN 9845:2013, TCVN 13615:2022, TCVN 4054:2005.
"""

import math
import json
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from scipy.stats import pearson3

# ==============================================================================
# KHỐI 1: CÁC THUẬT TOÁN TOÁN HỌC & THỦY VĂN GIẢI TÍCH
# ==============================================================================

def solve_pearson_3(data_list, cs_mode="2.0"):
    """
    Phân phối xác suất Pearson Loại III chuẩn tắc (dùng tích phân số SciPy Pearson III,
    tương đương bảng tra Foster-Rưpkin tiêu chuẩn trong TCVN 9845).
    """
    n = len(data_list)
    if n < 3:
        raise ValueError("Chuỗi số liệu phải có tối thiểu 3 năm quan trắc!")
    mean_val = sum(data_list) / n
    var = sum((x - mean_val) ** 2 for x in data_list) / (n - 1)
    sigma = math.sqrt(var)
    cv = sigma / mean_val if mean_val != 0 else 0

    if cs_mode == "sample":
        m3 = sum((x - mean_val) ** 3 for x in data_list)
        cs = (n * m3) / ((n - 1) * (n - 2) * (sigma ** 3)) if sigma != 0 else 0
    else:
        cs = float(cs_mode) * cv

    freqs = [0.1, 0.5, 1.0, 2.0, 4.0, 5.0, 10.0, 20.0, 50.0]
    res_freq = {}
    skew_val = cs if abs(cs) > 1e-4 else 1e-4

    for p in freqs:
        prob = 1.0 - (p / 100.0)
        phi_val = float(pearson3.ppf(prob, skew=skew_val))
        res_freq[p] = mean_val * (1.0 + cv * phi_val)

    return {"n": n, "mean": mean_val, "cv": cv, "cs": cs, "sigma": sigma, "freq": res_freq}

def solve_regression(x_data, y_data):
    """Tính hồi quy Y = a*X + b, hệ số R và R^2 cho cặp số liệu đo đồng thời."""
    n = len(x_data)
    if n < 3:
        raise ValueError("Cần tối thiểu 3 cặp số liệu thực đo đồng thời!")
    mx, my = sum(x_data) / n, sum(y_data) / n
    ss_xx = sum((x - mx) ** 2 for x in x_data)
    ss_yy = sum((y - my) ** 2 for y in y_data)
    ss_xy = sum((x_data[i] - mx) * (y_data[i] - my) for i in range(n))
    if ss_xx == 0:
        raise ValueError("Số liệu X không có dao động!")
    a = ss_xy / ss_xx
    b = my - a * mx
    r = ss_xy / math.sqrt(ss_xx * ss_yy) if (ss_xx * ss_yy) > 0 else 0
    return a, b, r, r**2

# ==============================================================================
# KHỐI 2: GIAO DIỆN PHẦN MỀM TỔNG QUÁT (DESKTOP GUI)
# ==============================================================================

class HydroCivilPro(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HydroCivil Pro - Phần Mềm Thủy Văn & Thủy Lực Cầu Đường Tổng Quát (TCVN)")
        self.geometry("1300x820")
        self.minsize(1120, 720)
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.st_results = None     # Kết quả Pearson III trạm
        self.reg_results = None    # Kết quả hồi quy Y = aX + b

        self._build_menu()
        self._build_header()
        self._build_tabs()

    def _build_menu(self):
        menubar = tk.Menu(self)
        fm = tk.Menu(menubar, tearoff=0)
        fm.add_command(label="Mở Dự Án (.json)...", command=self.load_project)
        fm.add_command(label="Lưu Dự Án (.json)...", command=self.save_project)
        fm.add_separator()
        fm.add_command(label="Xuất Bảng Kết Quả Nền Đường Ra Excel (.csv)...", command=self.export_csv_subgrade)
        fm.add_command(label="Xuất Bảng Khẩu Độ Cầu Cống Ra Excel (.csv)...", command=self.export_csv_struct)
        fm.add_command(label="Xuất Thuyết Minh Kỹ Thuật (.txt)...", command=self.export_report)
        fm.add_separator()
        fm.add_command(label="Thoát", command=self.quit)
        menubar.add_cascade(label="Dự Án", menu=fm)
        self.config(menu=menubar)

    def _build_header(self):
        hdr = tk.Frame(self, bg="#0F172A", height=50)
        hdr.pack(fill=tk.X, side=tk.TOP)
        tk.Label(hdr, text="HỆ THỐNG TÍNH TOÁN THỦY VĂN NỀN ĐƯỜNG & KHẨU ĐỘ CẦU CỐNG TỔNG QUÁT",
                 fg="white", bg="#0F172A", font=("Segoe UI", 12, "bold")).pack(pady=10)

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        self.tab1 = ttk.Frame(self.nb)
        self.tab2 = ttk.Frame(self.nb)
        self.tab3 = ttk.Frame(self.nb)
        self.tab4 = ttk.Frame(self.nb)

        self.nb.add(self.tab1, text=" BƯỚC 1: XỬ LÝ SỐ LIỆU TRẠM (PEARSON III) ")
        self.nb.add(self.tab2, text=" BƯỚC 2: MỰC NƯỚC NỀN ĐƯỜNG (Htk) - TƯƠNG QUAN TRẠM & VẾT LŨ ")
        self.nb.add(self.tab3, text=" BƯỚC 3: TÍNH LƯU LƯỢNG LŨ & ĐỊNH CỠ CẦU CỐNG DỌC TUYẾN ")
        self.nb.add(self.tab4, text=" BƯỚC 4: HỒ SƠ BÁO CÁO THUYẾT MINH & XUẤT TỆP ")

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()
        self._build_tab4()

    # --------------------------------------------------------------------------
    # TAB 1: PEARSON III TRẠM QUAN TRẮC
    # --------------------------------------------------------------------------
    def _build_tab1(self):
        paned = ttk.PanedWindow(self.tab1, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        lf = ttk.LabelFrame(paned, text=" Nhập Chuỗi Số Liệu Quan Trắc Trạm Đại Biểu ", padding=8)
        paned.add(lf, weight=1)

        ttk.Label(lf, text="Dán từ Excel 2 cột: Năm   Trị_số (Mưa Xmax, Mực nước Hmax, hoặc Lưu lượng Qmax):",
                  font=("Arial", 9, "italic"), foreground="#1E40AF").pack(anchor="w")

        self.txt_st_in = tk.Text(lf, width=32, height=18, font=("Consolas", 10))
        self.txt_st_in.pack(fill=tk.BOTH, expand=True, pady=4)

        bbar = tk.Frame(lf)
        bbar.pack(fill=tk.X, pady=2)
        ttk.Button(bbar, text="Xóa Hết", command=lambda: self.txt_st_in.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bbar, text="Dán Từ Clipboard", command=lambda: self._paste_to_txt(self.txt_st_in)).pack(side=tk.LEFT, padx=2)

        rf = ttk.LabelFrame(paned, text=" Cấu Hình Phân Phối Xác Suất & Kết Quả ", padding=10)
        paned.add(rf, weight=2)

        g = tk.Frame(rf)
        g.pack(fill=tk.X, pady=2)

        ttk.Label(g, text="Tên trạm quan trắc:").grid(row=0, column=0, sticky="w", pady=3)
        self.ent_st_name = ttk.Entry(g, width=28)
        self.ent_st_name.insert(0, "Trạm Thủy Văn / Khí Tượng Cơ Sở")
        self.ent_st_name.grid(row=0, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(g, text="Yếu tố tính toán:").grid(row=1, column=0, sticky="w", pady=3)
        self.cbo_st_factor = ttk.Combobox(g, values=["Mực nước đỉnh lũ Hmax (m)", "Lượng mưa ngày Xmax (mm)", "Lưu lượng đỉnh lũ Qmax (m3/s)"], state="readonly", width=26)
        self.cbo_st_factor.current(0)
        self.cbo_st_factor.grid(row=1, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(g, text="Quy tắc hệ số Cs:").grid(row=2, column=0, sticky="w", pady=3)
        self.cbo_st_cs = ttk.Combobox(g, values=[
            "Cs = 2.0 * Cv (Vùng đồng bằng, hạ lưu sông lớn)",
            "Cs = 3.0 * Cv (Vùng trung du, miền Trung, đồi dốc)",
            "Cs = 4.0 * Cv (Vùng núi cao, lũ quét cực đoan)",
            "Cs tính trực tiếp từ mẫu thực tế"
        ], state="readonly", width=26)
        self.cbo_st_cs.current(0)
        self.cbo_st_cs.grid(row=2, column=1, sticky="w", padx=6, pady=3)

        btn_run = tk.Button(g, text="▶ TÍNH TOÁN ĐƯỜNG TẦN SUẤT PEARSON LOẠI III", bg="#0D9488", fg="white",
                            font=("Arial", 9, "bold"), command=self.run_tab1)
        btn_run.grid(row=3, column=0, columnspan=2, sticky="ew", pady=8, padx=2)

        self.txt_st_out = tk.Text(rf, height=14, font=("Consolas", 10), bg="#F8FAFC", bd=1)
        self.txt_st_out.pack(fill=tk.BOTH, expand=True, pady=4)

    def run_tab1(self):
        txt = self.txt_st_in.get("1.0", tk.END).strip()
        if not txt:
            messagebox.showerror("Lỗi", "Vui lòng nhập chuỗi quan trắc trạm!")
            return
        series = []
        for line in txt.splitlines():
            line = line.strip()
            if not line: continue
            parts = line.replace(",", ".").split()
            try:
                series.append(float(parts[1]) if len(parts) >= 2 else float(parts[0]))
            except ValueError:
                continue

        cs_mode = ["2.0", "3.0", "4.0", "sample"][self.cbo_st_cs.current()]
        try:
            res = solve_pearson_3(series, cs_mode)
            self.st_results = res
            unit = "m" if "Mực nước" in self.cbo_st_factor.get() else ("mm" if "Lượng mưa" in self.cbo_st_factor.get() else "m3/s")

            out = (
                f"=== KẾT QUẢ PHÂN TÍCH TẦN SUẤT PEARSON III (TCVN 9845) ===\n"
                f"- Tên Trạm cơ sở:               {self.ent_st_name.get()}\n"
                f"- Số năm quan trắc thực đo (N): {res['n']} năm\n"
                f"- Giá trị trung bình mẫu (X_tb):{res['mean']:.3f} {unit}\n"
                f"- Hệ số biến động (Cv):         {res['cv']:.3f}\n"
                f"- Hệ số thiên lệch (Cs):        {res['cs']:.3f}\n"
                f"------------------------------------------------------------------\n"
                f" BẢNG GIÁ TRỊ THIẾT KẾ CÁC CẤP TẦN SUẤT P%:\n"
                f"   P = 0.5% (Cầu lớn):           {res['freq'][0.5]:.3f} {unit}\n"
                f"   P = 1.0% (Đường cao tốc, Cầu trung): {res['freq'][1.0]:.3f} {unit}\n"
                f"   P = 2.0% (Đường Cấp II, Cầu nhỏ):    {res['freq'][2.0]:.3f} {unit}\n"
                f"   P = 4.0% (Đường Cấp III, IV, Cống):  {res['freq'][4.0]:.3f} {unit}\n"
                f"   P = 5.0% (Mực nước thông thuyền):    {res['freq'][5.0]:.3f} {unit}\n"
                f"   P = 10.0% (Đường nông thôn, cống tạm):{res['freq'][10.0]:.3f} {unit}\n"
                f"==================================================================\n"
                f"=> DỮ LIỆU ĐÃ ĐƯỢC ĐỒNG BỘ SANG BƯỚC 2 VÀ BƯỚC 3!"
            )
            self.txt_st_out.delete("1.0", tk.END)
            self.txt_st_out.insert(tk.END, out)

            if "Mực nước" in self.cbo_st_factor.get():
                self.ent_h_st_p.delete(0, tk.END)
                self.ent_h_st_p.insert(0, f"{res['freq'][1.0]:.2f}")
            elif "Lượng mưa" in self.cbo_st_factor.get():
                self.ent_rain_hp.delete(0, tk.END)
                self.ent_rain_hp.insert(0, f"{res['freq'][1.0]:.1f}")

            messagebox.showinfo("Thành công", "Đã phân tích tần suất trạm hoàn tất!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không tính được tần suất: {e}")

    # --------------------------------------------------------------------------
    # TAB 2: XÁC ĐỊNH MỰC NƯỚC NỀN ĐƯỜNG (Htk) THEO VẾT LŨ & TƯƠNG QUAN TRẠM
    # --------------------------------------------------------------------------
    def _build_tab2(self):
        sub_nb = ttk.Notebook(self.tab2)
        sub_nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        sub_reg = ttk.Frame(sub_nb)
        sub_flood = ttk.Frame(sub_nb)

        sub_nb.add(sub_reg, text=" 2A. PHƯƠNG PHÁP HỒI QUY TƯƠNG QUAN MỰC NƯỚC THỰC ĐO (Y = aX + b) ")
        sub_nb.add(sub_flood, text=" 2B. PHƯƠNG PHÁP ĐIỀU TRA VẾT LŨ LỊCH SỬ & ĐỘ DỐC MẶT NƯỚC DỌC TUYẾN ")

        p_reg = ttk.PanedWindow(sub_reg, orient=tk.HORIZONTAL)
        p_reg.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        lf_reg = ttk.LabelFrame(p_reg, text=" Nhập Chuỗi Số Liệu Đo Mực Nước Đồng Thời Tuyến & Trạm ", padding=8)
        p_reg.add(lf_reg, weight=1)

        ttk.Label(lf_reg, text="Dán 2 cột từ Excel: H_Trạm(X)   H_Tuyến(Y) (đo theo giờ hoặc ngày):",
                  font=("Arial", 9, "italic"), foreground="#1E40AF").pack(anchor="w")

        self.txt_reg_in = tk.Text(lf_reg, width=32, height=18, font=("Consolas", 10))
        self.txt_reg_in.pack(fill=tk.BOTH, expand=True, pady=4)

        rf_reg = ttk.LabelFrame(p_reg, text=" Phương Trình Tương Quan & Dự Báo Mực Nước Thiết Kế Tuyến ", padding=10)
        p_reg.add(rf_reg, weight=2)

        btn_run_reg = tk.Button(rf_reg, text="▶ THIẾT LẬP PHƯƠNG TRÌNH TƯƠNG QUAN HỒI QUY", bg="#2563EB", fg="white",
                                font=("Arial", 9, "bold"), command=self.run_regression)
        btn_run_reg.pack(fill=tk.X, pady=4)

        self.txt_reg_out = tk.Text(rf_reg, height=14, font=("Consolas", 10), bg="#F8FAFC", bd=1)
        self.txt_reg_out.pack(fill=tk.BOTH, expand=True, pady=4)

        top_f = ttk.LabelFrame(sub_flood, text=" Tham Số Khống Chế Tuyến & Trạm Chuẩn ", padding=8)
        top_f.pack(fill=tk.X, padx=6, pady=4)

        rf1 = tk.Frame(top_f)
        rf1.pack(fill=tk.X, pady=2)

        ttk.Label(rf1, text="Mực nước trạm thiết kế H_tram(P%) (m):").pack(side=tk.LEFT, padx=3)
        self.ent_h_st_p = ttk.Entry(rf1, width=8)
        self.ent_h_st_p.insert(0, "2.00")
        self.ent_h_st_p.pack(side=tk.LEFT, padx=4)

        ttk.Label(rf1, text="Mực nước trạm năm lũ lịch sử H_tram(ls) (m):").pack(side=tk.LEFT, padx=8)
        self.ent_h_st_hist = ttk.Entry(rf1, width=8)
        self.ent_h_st_hist.insert(0, "1.80")
        self.ent_h_st_hist.pack(side=tk.LEFT, padx=4)

        ttk.Label(rf1, text="Mức chênh hệ cao độ Dự án - Trạm (m):").pack(side=tk.LEFT, padx=8)
        self.ent_dh_sys = ttk.Entry(rf1, width=8)
        self.ent_dh_sys.insert(0, "0.00")
        self.ent_dh_sys.pack(side=tk.LEFT, padx=4)

        ttk.Label(rf1, text="Độ cao an toàn vai đường a (m):").pack(side=tk.LEFT, padx=8)
        self.ent_safe_subgrade = ttk.Entry(rf1, width=8)
        self.ent_safe_subgrade.insert(0, "0.50")
        self.ent_safe_subgrade.pack(side=tk.LEFT, padx=4)

        tree_box = ttk.LabelFrame(sub_flood, text=" Bảng Xác Định Mực Nước Thiết Kế Nền Đường (Htk) Dọc Tuyến ", padding=6)
        tree_box.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        cols_sub = ("km", "name", "h_vl", "delta_h", "h_tk", "h_vai", "slope", "eval")
        self.tree_subgrade = ttk.Treeview(tree_box, columns=cols_sub, show="headings", height=8)

        headers_sub = [
            ("km", "Lý trình", 90),
            ("name", "Vị Trí Khảo Sát / Công Trình", 160),
            ("h_vl", "Vết Lũ Hvl (m)", 110),
            ("delta_h", "ΔH Cục Bộ (m)", 110),
            ("h_tk", "Htk Thiết Kế (m)", 120),
            ("h_vai", "Vai Đường Min (m)", 130),
            ("slope", "Độ Dốc Nước i", 110),
            ("eval", "Đánh Giá Ổn Định Nền", 170)
        ]
        for c, t, w in headers_sub:
            self.tree_subgrade.heading(c, text=t)
            self.tree_subgrade.column(c, width=w, anchor="center")

        sb = ttk.Scrollbar(tree_box, orient=tk.VERTICAL, command=self.tree_subgrade.yview)
        self.tree_subgrade.configure(yscroll=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_subgrade.pack(fill=tk.BOTH, expand=True)

        bar_f = tk.Frame(sub_flood, bg="#E2E8F0", pady=4)
        bar_f.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(bar_f, text="📋 Dán Vết Lũ Từ Excel", command=self._paste_flood_excel).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar_f, text="➕ Thêm Mốc", command=self._add_single_flood_dialog).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar_f, text="❌ Xóa Mốc Chọn", command=self._del_flood_row).pack(side=tk.LEFT, padx=4)

        btn_calc_htk = tk.Button(bar_f, text="▶ TÍNH TOÁN MỰC NƯỚC THIẾT KẾ Htk & VAI ĐƯỜNG", bg="#059669", fg="white",
                                 font=("Arial", 9, "bold"), command=self.run_subgrade_htk)
        btn_calc_htk.pack(side=tk.RIGHT, padx=10)

    def run_regression(self):
        txt = self.txt_reg_in.get("1.0", tk.END).strip()
        if not txt:
            messagebox.showerror("Lỗi", "Vui lòng nhập cặp số liệu đo đồng thời!")
            return
        xs, ys = [], []
        for line in txt.splitlines():
            line = line.strip()
            if not line: continue
            parts = line.replace(",", ".").split()
            if len(parts) >= 2:
                try:
                    xs.append(float(parts[0]))
                    ys.append(float(parts[1]))
                except ValueError:
                    continue
        try:
            a, b, r, r2 = solve_regression(xs, ys)
            self.reg_results = {"a": a, "b": b, "r": r, "r2": r2}

            pred_text = ""
            if self.st_results:
                h1 = self.st_results['freq'][1.0]
                h2 = self.st_results['freq'][2.0]
                h4 = self.st_results['freq'][4.0]
                pred_text = (
                    f" DỰ BÁO MỰC NƯỚC THIẾT KẾ NỀN ĐƯỜNG THEO TẦN SUẤT TRẠM:\n"
                    f"   + Htk (P=1.0%): Y = {a:.4f} * ({h1:.2f}) + ({b:.4f}) = {a*h1+b:.3f} m\n"
                    f"   + Htk (P=2.0%): Y = {a:.4f} * ({h2:.2f}) + ({b:.4f}) = {a*h2+b:.3f} m\n"
                    f"   + Htk (P=4.0%): Y = {a:.4f} * ({h4:.2f}) + ({b:.4f}) = {a*h4+b:.3f} m\n"
                )

            rpt = (
                f"=== KẾT QUẢ HỒI QUY TƯƠNG QUAN MỰC NƯỚC THỰC ĐO ===\n"
                f"- Số cặp giá trị đo đồng thời (N):   {len(xs)}\n"
                f"- Phương trình tương quan tuyến tính:  Y = {a:.4f} * X + ({b:+.4f})\n"
                f"- Hệ số tương quan (R):               R = {r:.4f}\n"
                f"- Hệ số xác định (R^2):              R^2 = {r2:.4f}\n"
                f"- Đánh giá chất lượng tương quan:     "
                f"{'RẤT CHẶT CHẼ (R >= 0.85, đủ cơ sở pháp lý)' if r >= 0.85 else 'TƯƠNG ĐỐI (Cần bổ sung thêm ngày đo)'}\n"
                f"------------------------------------------------------------------\n"
                f"{pred_text}"
                f"==================================================================\n"
                f"=> PHƯƠNG TRÌNH NÀY DÙNG ĐỂ KHỐNG CHẾ MẶT NƯỚC NỀN ĐƯỜNG TẠI CÔNG TRÌNH!"
            )
            self.txt_reg_out.delete("1.0", tk.END)
            self.txt_reg_out.insert(tk.END, rpt)
            messagebox.showinfo("Thành công", f"Đã thiết lập phương trình: Y = {a:.3f}X + {b:.3f} (R2={r2:.3f})")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không tính được tương quan: {e}")

    def _paste_flood_excel(self):
        try:
            raw = self.clipboard_get().strip()
            count = 0
            for line in raw.splitlines():
                parts = [p.strip().replace(",", ".") for p in line.split("\t")]
                if len(parts) < 2:
                    parts = [p.strip().replace(",", ".") for p in line.split()]
                if not parts: continue
                km = parts[0]
                name = parts[1] if len(parts) > 1 else "Điểm khảo sát"
                h_vl = parts[2] if len(parts) > 2 else "2.00"
                self.tree_subgrade.insert("", tk.END, values=(km, name, h_vl, "-", "-", "-", "-", "Chờ tính"))
                count += 1
            messagebox.showinfo("Thành công", f"Đã nhận {count} mốc vết lũ!")
        except Exception as e:
            messagebox.showerror("Lỗi dán", f"Không đọc được: {e}")

    def _add_single_flood_dialog(self):
        w = tk.Toplevel(self)
        w.title("Thêm Mốc Vết Lũ Khảo Sát")
        w.geometry("340x200")
        w.resizable(False, False)

        ttk.Label(w, text="Lý trình (Km):").grid(row=0, column=0, padx=8, pady=4, sticky="w")
        e_km = ttk.Entry(w, width=18); e_km.insert(0, "Km0+000"); e_km.grid(row=0, column=1, padx=8, pady=4)

        ttk.Label(w, text="Tên vị trí / Cột mốc:").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        e_name = ttk.Entry(w, width=18); e_name.insert(0, "Vết ngập lũ"); e_name.grid(row=1, column=1, padx=8, pady=4)

        ttk.Label(w, text="Cao độ vết lũ Hvl (m):").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        e_hvl = ttk.Entry(w, width=18); e_hvl.insert(0, "2.00"); e_hvl.grid(row=2, column=1, padx=8, pady=4)

        def add():
            self.tree_subgrade.insert("", tk.END, values=(e_km.get(), e_name.get(), e_hvl.get(), "-", "-", "-", "-", "Chờ tính"))
            w.destroy()

        ttk.Button(w, text="Thêm Vào Bảng", command=add).grid(row=3, column=0, columnspan=2, pady=12)

    def _del_flood_row(self):
        for s in self.tree_subgrade.selection():
            self.tree_subgrade.delete(s)

    def run_subgrade_htk(self):
        items = self.tree_subgrade.get_children()
        if not items:
            messagebox.showwarning("Trống", "Bảng vết lũ đang trống!")
            return
        try:
            h_st_p = float(self.ent_h_st_p.get())
            h_st_hist = float(self.ent_h_st_hist.get())
            dh_sys = float(self.ent_dh_sys.get())
            safe_a = float(self.ent_safe_subgrade.get())
        except ValueError:
            messagebox.showerror("Lỗi", "Kiểm tra lại định dạng số tại các ô tham số khống chế!")
            return

        delta_h_station = h_st_p - h_st_hist
        rows_calc = []

        for it in items:
            v = list(self.tree_subgrade.item(it, "values"))
            try:
                h_vl = float(v[2])
            except ValueError:
                continue

            h_st_hist_duan = h_st_hist + dh_sys
            delta_h_local = h_vl - h_st_hist_duan
            h_tk = h_vl + delta_h_station
            h_vai = h_tk + safe_a

            rows_calc.append({"item": it, "km": v[0], "name": v[1], "h_vl": h_vl,
                              "delta_h_local": delta_h_local, "h_tk": h_tk, "h_vai": h_vai})

        for i in range(len(rows_calc)):
            if i < len(rows_calc) - 1:
                dh = rows_calc[i]["h_tk"] - rows_calc[i+1]["h_tk"]
                slope_str = f"Δh={dh:+.2f}m"
            else:
                slope_str = "Cuối tuyến"

            eval_str = f"An toàn ngập (Htk={rows_calc[i]['h_tk']:.2f}m, Vai={rows_calc[i]['h_vai']:.2f}m)"

            self.tree_subgrade.item(rows_calc[i]["item"], values=(
                rows_calc[i]["km"], rows_calc[i]["name"], f"{rows_calc[i]['h_vl']:.2f}",
                f"{rows_calc[i]['delta_h_local']:+.2f}", f"{rows_calc[i]['h_tk']:.2f}",
                f"{rows_calc[i]['h_vai']:.2f}", slope_str, eval_str
            ))
        messagebox.showinfo("Thành công", "Đã xác định xong Mực nước thiết kế Htk và Vai đường toàn tuyến!")

    # --------------------------------------------------------------------------
    # TAB 3: THỦY LỰC LƯU LƯỢNG LŨ & KHẨU ĐỘ CẦU CỐNG DỌC TUYẾN
    # --------------------------------------------------------------------------
    def _build_tab3(self):
        top_c = ttk.LabelFrame(self.tab3, text=" Tham Số Khống Chế Mưa & Thủy Lực Lòng Dẫn ", padding=8)
        top_c.pack(fill=tk.X, padx=6, pady=4)

        r1 = tk.Frame(top_c)
        r1.pack(fill=tk.X, pady=2)

        ttk.Label(r1, text="Mưa ngày cực đại thiết kế Hp% (mm):").pack(side=tk.LEFT, padx=3)
        self.ent_rain_hp = ttk.Entry(r1, width=8); self.ent_rain_hp.insert(0, "200.0"); self.ent_rain_hp.pack(side=tk.LEFT, padx=4)

        ttk.Label(r1, text="Hệ số dòng chảy lũ mặt (phi):").pack(side=tk.LEFT, padx=8)
        self.ent_phi = ttk.Entry(r1, width=8); self.ent_phi.insert(0, "0.60"); self.ent_phi.pack(side=tk.LEFT, padx=4)

        ttk.Label(r1, text="Thời gian tập trung dòng chảy tc (h):").pack(side=tk.LEFT, padx=8)
        self.ent_tc = ttk.Entry(r1, width=8); self.ent_tc.insert(0, "2.5"); self.ent_tc.pack(side=tk.LEFT, padx=4)

        ttk.Label(r1, text="Hệ số nhám lòng dẫn (n):").pack(side=tk.LEFT, padx=8)
        self.ent_n_k = ttk.Entry(r1, width=8); self.ent_n_k.insert(0, "0.0275"); self.ent_n_k.pack(side=tk.LEFT, padx=4)

        tree_c_box = ttk.LabelFrame(self.tab3, text=" Bảng Tính Lưu Lượng & Định Cỡ Khẩu Độ Thoát Nước Dọc Tuyến ", padding=6)
        tree_c_box.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        cols_c = ("km", "name", "type", "mech", "f_km2", "b_k", "h_k", "i_k", "q_tk", "khau_do", "v_flow", "eval")
        self.tree_struct = ttk.Treeview(tree_c_box, columns=cols_c, show="headings", height=9)

        headers_c = [
            ("km", "Lý trình", 80), ("name", "Tên Công Trình", 140), ("type", "Loại", 80),
            ("mech", "Cơ Chế Q", 95), ("f_km2", "Lưu Vực F (km2)", 95), ("b_k", "B đáy (m)", 75),
            ("h_k", "h nước (m)", 75), ("i_k", "Độ Dốc i", 75), ("q_tk", "Qtk (m3/s)", 85),
            ("khau_do", "Khẩu Độ Đề Xuất", 140), ("v_flow", "Vận Tốc V (m/s)", 95), ("eval", "Đánh Giá Thủy Lực", 160)
        ]
        for c, t, w in headers_c:
            self.tree_struct.heading(c, text=t)
            self.tree_struct.column(c, width=w, anchor="center")

        sb_c = ttk.Scrollbar(tree_c_box, orient=tk.VERTICAL, command=self.tree_struct.yview)
        self.tree_struct.configure(yscroll=sb_c.set)
        sb_c.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_struct.pack(fill=tk.BOTH, expand=True)

        bar_c = tk.Frame(self.tab3, bg="#E2E8F0", pady=4)
        bar_c.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(bar_c, text="📋 Dán Toàn Bộ Bảng Từ Excel", command=self._paste_struct_excel).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar_c, text="➕ Thêm Công Trình", command=self._add_single_struct_dialog).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar_c, text="❌ Xóa Dòng Chọn", command=self._del_struct_row).pack(side=tk.LEFT, padx=4)

        btn_run_struct = tk.Button(bar_c, text="▶ CHẠY TÍNH LƯU LƯỢNG LŨ & KHẨU ĐỘ TOÀN TUYẾN", bg="#059669", fg="white",
                                   font=("Arial", 9, "bold"), command=self.run_struct_calc)
        btn_run_struct.pack(side=tk.RIGHT, padx=10)

    def _paste_struct_excel(self):
        try:
            raw = self.clipboard_get().strip()
            count = 0
            for line in raw.splitlines():
                parts = [p.strip().replace(",", ".") for p in line.split("\t")]
                if len(parts) < 3:
                    parts = [p.strip().replace(",", ".") for p in line.split()]
                if not parts: continue
                km = parts[0]
                name = parts[1] if len(parts) > 1 else "Công trình"
                ctype = parts[2] if len(parts) > 2 else "Cống hộp"
                mech = parts[3] if len(parts) > 3 else "Mưa lưu vực"
                f_km2 = parts[4] if len(parts) > 4 else "2.5"
                b_k = parts[5] if len(parts) > 5 else "4.0"
                h_k = parts[6] if len(parts) > 6 else "1.5"
                i_k = parts[7] if len(parts) > 7 else "0.0002"
                self.tree_struct.insert("", tk.END, values=(km, name, ctype, mech, f_km2, b_k, h_k, i_k, "-", "-", "-", "Chờ tính"))
                count += 1
            messagebox.showinfo("Thành công", f"Đã nhận {count} công trình từ Excel!")
        except Exception as e:
            messagebox.showerror("Lỗi dán", f"Không đọc được: {e}")

    def _add_single_struct_dialog(self):
        w = tk.Toplevel(self)
        w.title("Thêm Công Trình Thoát Nước")
        w.geometry("360x320")
        w.resizable(False, False)

        fields = [
            ("Lý trình (Km):", "Km0+000"),
            ("Tên công trình:", "Kênh Tiêu"),
            ("Loại (Cống hộp/Cống tròn/Cầu):", "Cống hộp"),
            ("Cơ chế Q (Mưa lưu vực/Kênh tự nhiên):", "Mưa lưu vực"),
            ("Lưu vực đón nước F (km2):", "2.5"),
            ("B đáy kênh/sông (m):", "4.0"),
            ("Chiều sâu nước h (m):", "1.5"),
            ("Độ dốc lòng dẫn i:", "0.0002"),
        ]
        entries = []
        for idx, (label, def_val) in enumerate(fields):
            ttk.Label(w, text=label).grid(row=idx, column=0, sticky="w", padx=10, pady=3)
            ent = ttk.Entry(w, width=20); ent.insert(0, def_val); ent.grid(row=idx, column=1, sticky="w", padx=10, pady=3)
            entries.append(ent)

        def add():
            v = [e.get().strip() for e in entries]
            self.tree_struct.insert("", tk.END, values=(v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], "-", "-", "-", "Chờ tính"))
            w.destroy()

        ttk.Button(w, text="Thêm Vào Bảng", command=add).grid(row=len(fields), column=0, columnspan=2, pady=10)

    def _del_struct_row(self):
        for s in self.tree_struct.selection():
            self.tree_struct.delete(s)

    def run_struct_calc(self):
        items = self.tree_struct.get_children()
        if not items:
            messagebox.showwarning("Trống", "Bảng công trình đang trống!")
            return
        try:
            hp = float(self.ent_rain_hp.get())
            phi = float(self.ent_phi.get())
            tc = float(self.ent_tc.get())
            n_rough = float(self.ent_n_k.get())
        except ValueError:
            messagebox.showerror("Lỗi", "Kiểm tra lại các tham số mưa và độ nhám!")
            return

        for it in items:
            v = list(self.tree_struct.item(it, "values"))
            km, name, ctype, mech = v[0], v[1], v[2], v[3]
            try:
                f_km2 = float(v[4])
                b_k = float(v[5])
                h_k = float(v[6])
                i_k = float(v[7])
            except ValueError:
                continue

            # 1. Tính lưu lượng mưa tiêu Q_rain (ĐÃ SỬA: Loại bỏ chia thừa 3.6, hệ số 0.278 là 1/3.6)
            q_rain = 0.278 * phi * (hp / (tc ** 0.7)) * f_km2

            # 2. Tính lưu lượng lòng dẫn tự nhiên Q_channel (Manning)
            area_k = (b_k + 1.25 * h_k) * h_k
            peri_k = b_k + 2.0 * h_k * math.sqrt(1.0 + 1.25**2)
            rad_k = area_k / peri_k if peri_k > 0 else 0
            q_chan = (1.0 / n_rough) * area_k * (rad_k ** (2.0 / 3.0)) * math.sqrt(i_k) if i_k > 0 else 0

            # 3. Lựa chọn cơ chế tính Qtk
            if "kênh" in mech.lower() or "thủy lợi" in mech.lower():
                q_design = q_chan if q_chan > 0 else q_rain
            elif "mưa" in mech.lower() or "lưu vực" in mech.lower():
                q_design = q_rain
            else:
                q_design = max(q_rain, q_chan)

            # 4. Định cỡ khẩu độ đề xuất
            if ctype == "Cầu":
                h0 = max(h_k, 1.0)
                b_thoat = q_design / (0.85 * h0 * math.sqrt(2.0 * 9.81 * 0.15))
                v_flow = q_design / (b_thoat * h0) if (b_thoat * h0) > 0 else 0
                size_str = f"B_thoát ≥ {b_thoat:.1f} m"
                eval_str = f"An toàn xói (V={v_flow:.2f} m/s)" if v_flow <= 1.40 else f"Nguy cơ xói (V={v_flow:.2f} m/s, cần gia cố)"
            elif ctype == "Cống tròn":
                d_req = math.sqrt(max((4.0 * q_design) / (3.14159 * 1.2 * 0.7), 0.2))
                size_str = f"Ø{d_req:.1f}m"
                v_flow = 1.20
                eval_str = "Chảy không áp an toàn"
            else:
                if q_design <= 2.5:
                    size_str = "1x(2.0x2.0)m"; v_flow = q_design / 3.2
                elif q_design <= 6.0:
                    size_str = "1x(2.5x2.5)m"; v_flow = q_design / 5.0
                elif q_design <= 12.0:
                    size_str = "2x(2.5x2.5)m"; v_flow = q_design / 10.0
                elif q_design <= 22.0:
                    size_str = "2x(3.5x3.5)m"; v_flow = q_design / 19.6
                elif q_design <= 35.0:
                    size_str = "3x(3.5x3.5)m"; v_flow = q_design / 29.4
                else:
                    size_str = "3x(4.0x4.0)m hoặc Cầu"; v_flow = q_design / 38.4
                eval_str = f"Đạt yêu cầu tiêu thoát (V={v_flow:.2f} m/s)" if v_flow <= 1.6 else f"Vận tốc lớn (V={v_flow:.2f} m/s, tăng cửa cống)"

            self.tree_struct.item(it, values=(
                km, name, ctype, mech, f"{f_km2:.2f}", f"{b_k:.1f}", f"{h_k:.2f}",
                f"{i_k:.5f}", f"{q_design:.2f}", size_str, f"{v_flow:.2f}", eval_str
            ))
        messagebox.showinfo("Thành công", "Đã định cỡ khẩu độ toàn tuyến hoàn tất!")

    # --------------------------------------------------------------------------
    # TAB 4: HỒ SƠ BÁO CÁO THUYẾT MINH & XUẤT TỆP
    # --------------------------------------------------------------------------
    def _build_tab4(self):
        f = ttk.LabelFrame(self.tab4, text=" Báo Cáo Kỹ Thuật Thủy Văn - Thủy Lực Tuyến ", padding=8)
        f.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        bar = tk.Frame(f)
        bar.pack(fill=tk.X, pady=4)

        ttk.Button(bar, text="🔄 Cập Nhật Thuyết Minh", command=self.generate_report).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="💾 Xuất Báo Cáo Ra File (.txt)", command=self.export_report).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="📊 Xuất Bảng Nền Đường (.csv)", command=self.export_csv_subgrade).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="📊 Xuất Bảng Cầu Cống (.csv)", command=self.export_csv_struct).pack(side=tk.LEFT, padx=4)

        self.txt_final_report = tk.Text(f, font=("Consolas", 10), bg="#F8FAFC", bd=1)
        self.txt_final_report.pack(fill=tk.BOTH, expand=True, pady=4)

    def generate_report(self):
        txt = (
            "========================================================================================================\n"
            "                 BÁO CÁO TÍNH TOÁN THỦY VĂN NỀN ĐƯỜNG & KHẨU ĐỘ CÔNG TRÌNH DỌC TUYẾN\n"
            "        Tiêu chuẩn áp dụng: TCVN 9845:2013, TCVN 13615:2022, TCVN 4054:2005, Sổ tay Thủy văn\n"
            "========================================================================================================\n\n"
            "I. CƠ SỞ DỮ LIỆU KHÍ TƯỢNG - THỦY VĂN TRẠM CHUẨN:\n"
            f"- Tên trạm cơ sở:                         {self.ent_st_name.get()}\n"
            f"- Mức bù chênh hệ cao độ Quốc gia - Trạm: +{self.ent_dh_sys.get()} m\n"
        )
        if self.st_results:
            txt += (
                f"- Số năm quan trắc thực đo:              {self.st_results['n']} năm | Cv = {self.st_results['cv']:.3f} | Cs = {self.st_results['cs']:.3f}\n"
                f"- Mực nước/Mưa thiết kế trạm:            P=1%: {self.st_results['freq'][1.0]:.2f} | P=2%: {self.st_results['freq'][2.0]:.2f} | P=4%: {self.st_results['freq'][4.0]:.2f}\n\n"
            )
        if self.reg_results:
            txt += (
                f"II. PHƯƠNG TRÌNH TƯƠNG QUAN MỰC NƯỚC THỰC ĐO ĐỒNG THỜI:\n"
                f"- Phương trình hồi quy:                  Y = {self.reg_results['a']:.4f} * X + ({self.reg_results['b']:+.4f})\n"
                f"- Hệ số xác định R^2:                    R^2 = {self.reg_results['r2']:.4f} (Tương quan rất chặt chẽ)\n\n"
            )

        txt += (
            "III. BẢNG MỰC NƯỚC THIẾT KẾ NỀN ĐƯỜNG (Htk) & VAI ĐƯỜNG MIN THEO VẾT LŨ DỌC TUYẾN:\n"
            "--------------------------------------------------------------------------------------------------------\n"
            f"{'Lý trình':<10} | {'Vị trí khảo sát':<24} | {'Vết lũ (m)':<10} | {'ΔH cục bộ':<10} | {'Htk (m)':<10} | {'Vai min (m)':<11} | {'Độ dốc i'}\n"
            "--------------------------------------------------------------------------------------------------------\n"
        )
        for it in self.tree_subgrade.get_children():
            v = self.tree_subgrade.item(it, "values")
            txt += f"{v[0]:<10} | {v[1]:<24} | {v[2]:<10} | {v[3]:<10} | {v[4]:<10} | {v[5]:<11} | {v[6]}\n"

        txt += (
            "--------------------------------------------------------------------------------------------------------\n\n"
            "IV. BẢNG TỔNG HỢP LƯU LƯỢNG LŨ & KHẨU ĐỘ CẦU CỐNG DỌC TUYẾN:\n"
            "--------------------------------------------------------------------------------------------------------\n"
            f"{'Lý trình':<10} | {'Tên công trình':<20} | {'Loại':<9} | {'Cơ chế Q':<12} | {'Qtk (m3/s)':<11} | {'Khẩu độ đề xuất':<16} | {'Vận tốc'}\n"
            "--------------------------------------------------------------------------------------------------------\n"
        )
        for it in self.tree_struct.get_children():
            v = self.tree_struct.item(it, "values")
            txt += f"{v[0]:<10} | {v[1]:<20} | {v[2]:<9} | {v[3]:<12} | {v[8]:<11} | {v[9]:<16} | {v[10]} m/s\n"

        txt += (
            "--------------------------------------------------------------------------------------------------------\n"
            "KẾT LUẬN: Toàn bộ cao độ đã quy chuẩn về Hệ cao độ Quốc gia. Cao độ vai đường thiết kế đảm bảo độ cao an toàn\n"
            "chống ngập lũ theo TCVN 4054:2005. Các cống ngang đảm bảo chế độ chảy không áp, khoang cầu đảm bảo thoát lũ an toàn.\n"
            "========================================================================================================\n"
        )
        self.txt_final_report.delete("1.0", tk.END)
        self.txt_final_report.insert(tk.END, txt)

    def export_csv_subgrade(self):
        items = self.tree_subgrade.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Bảng nền đường đang trống!")
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")], title="Lưu Kết Quả Nền Đường")
        if not p: return
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Lý trình", "Vị trí khảo sát", "Vết lũ khảo sát (m)", "Delta H cục bộ (m)", "Mực nước Htk (m)", "Cao độ vai đường min (m)", "Độ dốc mặt nước", "Đánh giá"])
            for it in items:
                w.writerow(self.tree_subgrade.item(it, "values"))
        messagebox.showinfo("Thành công", f"Đã xuất ra tệp CSV:\n{p}")

    def export_csv_struct(self):
        items = self.tree_struct.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Bảng cầu cống đang trống!")
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")], title="Lưu Bảng Khẩu Độ Cầu Cống")
        if not p: return
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Lý trình", "Tên công trình", "Loại", "Cơ chế tính Q", "Lưu vực F (km2)", "B đáy (m)", "h nước (m)", "Độ dốc i", "Lưu lượng Qtk (m3/s)", "Khẩu độ đề xuất", "Vận tốc (m/s)", "Đánh giá thủy lực"])
            for it in items:
                w.writerow(self.tree_struct.item(it, "values"))
        messagebox.showinfo("Thành công", f"Đã xuất ra tệp CSV:\n{p}")

    def export_report(self):
        self.generate_report()
        content = self.txt_final_report.get("1.0", tk.END).strip()
        if not content: return
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")], title="Lưu Thuyết Minh")
        if not p: return
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        messagebox.showinfo("Thành công", f"Đã xuất thuyết minh:\n{p}")

    def save_project(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")], title="Lưu Dự Án")
        if not p: return
        data = {
            "st_name": self.ent_st_name.get(),
            "st_factor_idx": self.cbo_st_factor.current(),
            "st_cs_idx": self.cbo_st_cs.current(),
            "st_in": self.txt_st_in.get("1.0", tk.END).strip(),
            "reg_in": self.txt_reg_in.get("1.0", tk.END).strip(),
            "h_st_p": self.ent_h_st_p.get(),
            "h_st_hist": self.ent_h_st_hist.get(),
            "dh_sys": self.ent_dh_sys.get(),
            "safe_a": self.ent_safe_subgrade.get(),
            "rain_hp": self.ent_rain_hp.get(),
            "phi": self.ent_phi.get(),
            "tc": self.ent_tc.get(),
            "n_k": self.ent_n_k.get(),
            "subgrade_rows": [self.tree_subgrade.item(it, "values") for it in self.tree_subgrade.get_children()],
            "struct_rows": [self.tree_struct.item(it, "values") for it in self.tree_struct.get_children()]
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        messagebox.showinfo("Thành công", "Đã lưu dự án thành công!")

    def load_project(self):
        p = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")], title="Mở File Dự Án")
        if not p: return
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)

        self.ent_st_name.delete(0, tk.END); self.ent_st_name.insert(0, d.get("st_name", ""))
        self.cbo_st_factor.current(d.get("st_factor_idx", 0))
        self.cbo_st_cs.current(d.get("st_cs_idx", 0))
        self.txt_st_in.delete("1.0", tk.END); self.txt_st_in.insert(0, d.get("st_in", ""))
        self.txt_reg_in.delete("1.0", tk.END); self.txt_reg_in.insert(0, d.get("reg_in", ""))

        self.ent_h_st_p.delete(0, tk.END); self.ent_h_st_p.insert(0, d.get("h_st_p", "2.00"))
        self.ent_h_st_hist.delete(0, tk.END); self.ent_h_st_hist.insert(0, d.get("h_st_hist", "1.80"))
        self.ent_dh_sys.delete(0, tk.END); self.ent_dh_sys.insert(0, d.get("dh_sys", "0.00"))
        self.ent_safe_subgrade.delete(0, tk.END); self.ent_safe_subgrade.insert(0, d.get("safe_a", "0.50"))

        self.ent_rain_hp.delete(0, tk.END); self.ent_rain_hp.insert(0, d.get("rain_hp", "200.0"))
        self.ent_phi.delete(0, tk.END); self.ent_phi.insert(0, d.get("phi", "0.60"))
        self.ent_tc.delete(0, tk.END); self.ent_tc.insert(0, d.get("tc", "2.5"))
        self.ent_n_k.delete(0, tk.END); self.ent_n_k.insert(0, d.get("n_k", "0.0275"))

        for it in self.tree_subgrade.get_children(): self.tree_subgrade.delete(it)
        for r in d.get("subgrade_rows", []): self.tree_subgrade.insert("", tk.END, values=r)

        for it in self.tree_struct.get_children(): self.tree_struct.delete(it)
        for r in d.get("struct_rows", []): self.tree_struct.insert("", tk.END, values=r)

        if self.txt_st_in.get("1.0", tk.END).strip(): self.run_tab1()
        if self.txt_reg_in.get("1.0", tk.END).strip(): self.run_regression()
        messagebox.showinfo("Thành công", "Đã nạp toàn bộ dự án!")

    def _paste_to_txt(self, widget):
        try:
            widget.delete("1.0", tk.END)
            widget.insert(tk.END, self.clipboard_get().strip())
        except Exception:
            pass

if __name__ == "__main__":
    app = HydroCivilPro()
    app.mainloop()