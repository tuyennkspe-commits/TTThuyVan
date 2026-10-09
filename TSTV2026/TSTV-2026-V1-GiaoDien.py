import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import sys
import numpy as np
from scipy.stats import norm, pearson3, gumbel_r
from scipy.optimize import least_squares
from matplotlib.ticker import MaxNLocator
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Cấu hình font hệ thống chuẩn Times New Roman đồng bộ toàn bản vẽ
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman', 'Times', 'DejaVu Serif']
plt.rcParams['mathtext.fontset'] = 'stix'   # STIX chuẩn toán học của Times New Roman
plt.rcParams['axes.unicode_minus'] = False


class TSTVAdvancedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Phân tích tần suất thủy văn | TSTV 2026")
        self.root.geometry("1180x820")
        self.root.minsize(960, 640)
        self.root.resizable(True, True)

        # Bắt sự kiện bấm dấu 'X' để tắt sạch 100% tiến trình chạy ngầm
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Quản lý các cửa sổ con
        self.plot_win = None
        self.tbl_win = None
        self.tbl_emp_win = None

        # Dữ liệu chuỗi
        self.years = []
        self.raw_data = []
        self.sorted_data = []
        self.xbq_calc = 0.0
        self.cv_calc = 0.0
        self.cs_calc = 0.0

        self.setup_ui()

    def on_close(self):
        """Hàm dập tắt hoàn toàn ứng dụng và tiến trình Windows ngay lập tức"""
        try:
            plt.close('all')
            if self.plot_win and self.plot_win.winfo_exists():
                self.plot_win.destroy()
            if self.tbl_win and self.tbl_win.winfo_exists():
                self.tbl_win.destroy()
            if self.tbl_emp_win and self.tbl_emp_win.winfo_exists():
                self.tbl_emp_win.destroy()
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        finally:
            return

    def setup_ui(self):
        self.root.configure(bg="#eef2f7")
        self.root.option_add("*Font", ("Segoe UI", 10))
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef2f7")
        style.configure("TLabel", background="#eef2f7", foreground="#26364b")
        style.configure("TLabelframe", background="#eef2f7", bordercolor="#ccd6e3")
        style.configure("TLabelframe.Label", background="#eef2f7", foreground="#153c67", font=("Segoe UI", 11, "bold"))
        style.configure("TNotebook", background="#eef2f7", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 9), background="#dce5f0", foreground="#26364b")
        style.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", "#175b99")])
        style.configure("TRadiobutton", background="#eef2f7", foreground="#26364b", padding=3)
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 10))
        style.configure("Primary.TButton", background="#175b99", foreground="white")
        style.map("Primary.TButton", background=[("active", "#10477b")])
        style.configure("Treeview", rowheight=29, background="white", fieldbackground="white", foreground="#26364b")
        style.configure("Treeview.Heading", padding=8, font=("Segoe UI", 10, "bold"), background="#e1e9f3")
        style.map("Treeview", background=[("selected", "#175b99")], foreground=[("selected", "white")])
        header = tk.Frame(self.root, bg="#153c67", padx=22, pady=15)
        header.pack(fill="x")
        tk.Label(header, text="Phân tích tần suất thủy văn", bg="#153c67", fg="white", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(header, text="Số liệu quan trắc • Phân tích thống kê • Bản vẽ kỹ thuật", bg="#153c67", fg="#c7ddf2").pack(anchor="w", pady=(5, 0))
        actions = ttk.Frame(self.root, padding=(18, 10))
        actions.pack(side="bottom", fill="x")
        ttk.Button(actions, text="Bảng tần suất kinh nghiệm", command=lambda: self.run_action(self.show_emp_table_window)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Bảng tần suất lý luận", command=lambda: self.run_action(self.show_xp_table_window)).pack(side="left")
        ttk.Button(actions, text="Vẽ đồ thị tần suất", style="Primary.TButton", command=lambda: self.run_action(self.plot_cad_style)).pack(side="right")
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=18, pady=(12, 0))
        left = ttk.Frame(body, padding=8)
        right = ttk.Frame(body, padding=8)
        body.add(left, weight=2); body.add(right, weight=3)
        ttk.Label(left, text="1. Số liệu quan trắc", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(left, text="Giá trị sắp xếp được xếp độc lập, từ lớn đến nhỏ.", wraplength=380).pack(anchor="w", pady=(4, 10))
        table = ttk.Frame(left)
        table.pack(fill="both", expand=True)
        cols = ("stt", "nam", "xi", "xss")
        self.tree = ttk.Treeview(table, columns=cols, show="headings")
        for key, title, width in zip(cols, ("Số thứ tự", "Năm", "Giá trị quan trắc", "Giá trị sắp xếp"), (80, 70, 140, 140)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=60, anchor="center" if key in ("stt", "nam") else "e")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        table.rowconfigure(0, weight=1); table.columnconfigure(0, weight=1)
        ttk.Button(left, text="Nhập số liệu từ tệp văn bản (.txt)", command=self.load_txt_file).pack(fill="x", pady=(10, 6))
        project = ttk.Frame(left); project.pack(fill="x")
        ttk.Button(project, text="Mở dự án (.tsh)", command=self.load_project).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(project, text="Lưu dự án (.tsh)", command=self.save_project).pack(side="left", fill="x", expand=True, padx=(4, 0))
        notebook = ttk.Notebook(right); notebook.pack(fill="both", expand=True)
        def scroll_page(title):
            page = ttk.Frame(notebook)
            notebook.add(page, text=title)
            canvas = tk.Canvas(page, bg="#eef2f7", highlightthickness=0)
            scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
            canvas.configure(yscrollcommand=scrollbar.set)
            contents = ttk.Frame(canvas, padding=12)
            item = canvas.create_window((0, 0), window=contents, anchor="nw")
            contents.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
            return contents
        analysis = scroll_page("2. Thiết lập phân tích")
        drawing = scroll_page("3. Thông tin bản vẽ")
        def group(parent, title):
            box = ttk.LabelFrame(parent, text=title, padding=12)
            box.pack(fill="x", pady=(0, 12))
            return box
        def field(parent, row, title, name, default=""):
            ttk.Label(parent, text=title).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 12))
            entry = ttk.Entry(parent, width=20)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            entry.insert(0, default); setattr(self, name, entry)
            parent.columnconfigure(1, weight=1)
            return entry
        stats = group(analysis, "Đặc trưng thống kê của mẫu")
        field(stats, 0, "Giá trị trung bình (X̄)", "txt_xbq")
        field(stats, 1, "Hệ số biến thiên (Cv)", "txt_cv")
        field(stats, 2, "Hệ số bất đối xứng (Cs)", "txt_cs")
        empirical = group(analysis, "Tần suất kinh nghiệm")
        self.cbo_formula = ttk.Combobox(empirical, state="readonly", values=[
            "Vị trí vẽ α=0,25 : P = (m-0.25)/(n+0.5) x100%",
            "Weibull : P = m/(n+1) x100%",
            "Hazen : P = (m-0.5)/n x100%"])
        self.cbo_formula.current(0); self.cbo_formula.pack(fill="x")
        self.cbo_formula.bind("<<ComboboxSelected>>", lambda event: self.update_three_points())
        theoretical = group(analysis, "Phân phối và phương pháp tính")
        distributions = ttk.Frame(theoretical); distributions.pack(fill="x")
        self.dist_var = tk.StringVar(value="PEARSON III")
        for title, value in (("Pearson III", "PEARSON III"), ("Log-Pearson III", "LOG-PEARSON III"), ("Gumbel", "GUMBEL")):
            ttk.Radiobutton(distributions, text=title, value=value, variable=self.dist_var).pack(side="left", padx=(0, 10))
        self.method_var = tk.IntVar(value=1)
        self.parameter_tabs = ttk.Notebook(theoretical)
        self.parameter_tabs.pack(fill="x", pady=(12, 0))
        moment = ttk.Frame(self.parameter_tabs, padding=10)
        fit = ttk.Frame(self.parameter_tabs, padding=10)
        three = ttk.Frame(self.parameter_tabs, padding=10)
        for panel, title in ((moment, "Mô men"), (fit, "Thích hợp"), (three, "Ba điểm")):
            self.parameter_tabs.add(panel, text=title)
        ttk.Label(moment, text="Tính tham số trực tiếp từ chuỗi số liệu quan trắc.", wraplength=420).pack(anchor="w")
        field(fit, 0, "Giá trị trung bình (X̄)", "ent_fit_xbq")
        field(fit, 1, "Hệ số biến thiên (Cv)", "ent_fit_cv")
        field(fit, 2, "Hệ số bất đối xứng (Cs)", "ent_fit_cs")
        self.fit_labels = [fit.grid_slaves(row=row, column=0)[0] for row in range(3)]
        self.dist_var.trace_add("write", self.distribution_changed)
        field(three, 0, "Giá trị tại tần suất 5%", "ent_x5")
        field(three, 1, "Giá trị tại tần suất 50%", "ent_x50")
        field(three, 2, "Giá trị tại tần suất 95%", "ent_x95")
        self.parameter_tabs.bind("<<NotebookTabChanged>>", lambda event: self.method_var.set(self.parameter_tabs.index("current") + 1))
        ttk.Label(three, text="Gumbel khớp ba điểm theo bình phương tối thiểu. Điểm mặc định chỉ nội suy trong chuỗi, ngoài miền lấy giá trị biên; cần kiểm tra trước khi dùng.", wraplength=400).grid(row=3, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Label(fit, text="Nhập tham số để điều chỉnh đường lý luận; không tự tối ưu theo toàn bộ chuỗi.", wraplength=400).grid(row=3, column=0, columnspan=2, sticky="w", pady=8)
        self.method_var.trace_add("write", lambda *args: self.parameter_tabs.select(self.method_var.get() - 1) if self.parameter_tabs.index("current") != self.method_var.get() - 1 else None)
        details = group(drawing, "Thông tin trong khung tên")
        field(details, 0, "Tên trạm / Tiêu đề đồ thị", "txt_title", "ĐƯỜNG TẦN SUẤT LƯỢNG MƯA 1 NGÀY LỚN NHẤT NĂM TRẠM CHŨ")
        field(details, 1, "Ký hiệu đại lượng quan trắc", "txt_kyhieu", "X")
        field(details, 2, "Đơn vị đo", "txt_donvi", "mm")
        field(details, 3, "Người lập bản vẽ", "txt_ng_ve", "Nguyễn Kim Tuyên")
        field(details, 4, "Người kiểm tra", "txt_ng_kt")
        field(details, 5, "Năm lập bản vẽ", "txt_year_draw", "2026")
        limits = group(drawing, "Giới hạn trục giá trị")
        field(limits, 0, "Giá trị nhỏ nhất", "txt_ymin", "0")
        field(limits, 1, "Giá trị lớn nhất", "txt_ymax")
        ttk.Label(limits, text="Để trống giá trị lớn nhất để phần mềm tự xác định.", wraplength=430).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def run_action(self, action):
        try:
            return action()
        except (ValueError, FloatingPointError, OverflowError) as exc:
            messagebox.showerror("Không thể tạo kết quả", str(exc))

    def style_dialog(self, window):
        """Apply the same typography and quiet palette to auxiliary windows."""
        for widget in window.winfo_children():
            if isinstance(widget, tk.Button):
                widget.configure(font=("Segoe UI", 10), bg="#175b99", fg="white", activebackground="#10477b", activeforeground="white", relief="flat", padx=12, pady=7)
            elif isinstance(widget, (tk.Label, tk.LabelFrame)):
                widget.configure(font=("Segoe UI", 10), fg="#26364b", bg="#eef2f7")
            elif isinstance(widget, tk.Frame):
                widget.configure(bg="#eef2f7")
            self.style_dialog(widget)

    def load_txt_file(self):
        fp = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not fp:
            return
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            vals = []
            years = []
            c = 1
            for l in lines:
                parts = l.replace(",", " ").split()
                if not parts:
                    continue
                if len(parts) == 1:
                    vals.append(float(parts[0]))
                    years.append(c)
                    c += 1
                elif len(parts) >= 2:
                    try:
                        years.append(int(parts[0]))
                        vals.append(float(parts[1]))
                    except ValueError:
                        vals.append(float(parts[0]))
                        years.append(c)
                        c += 1
                        vals.append(float(parts[1]))
                        years.append(c)
                        c += 1

            if len(vals) < 3:
                messagebox.showwarning("Cảnh báo", "Chuỗi số liệu phải có ít nhất 3 năm.")
                return

            self.validate_sample(vals)
            self.years = years
            self.raw_data = np.array(vals)
            self.sorted_data = np.sort(self.raw_data)[::-1]

            self.update_data_table_and_stats()

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được tệp TXT: {e}")

    def update_data_table_and_stats(self):
        """Cập nhật bảng TreeView và các chỉ số thống kê mẫu"""
        self.tree.delete(*self.tree.get_children())
        for i in range(len(self.raw_data)):
            self.tree.insert("", tk.END, values=(
                i + 1,
                self.years[i] if i < len(self.years) else i + 1,
                f"{self.raw_data[i]:.2f}",
                f"{self.sorted_data[i]:.2f}"
            ))

        self.validate_sample(self.sorted_data)
        n = len(self.sorted_data)
        self.xbq_calc = float(np.mean(self.sorted_data))
        s = float(np.std(self.sorted_data, ddof=1))
        self.cv_calc = s / self.xbq_calc if self.xbq_calc != 0 else 0.0
        diff = self.sorted_data - self.xbq_calc
        self.cs_calc = float((n / ((n - 1) * (n - 2))) * np.sum(diff**3) / (s**3)) if s != 0 else 0.0

        self.txt_xbq.delete(0, tk.END); self.txt_xbq.insert(0, f"{self.xbq_calc:.2f}")
        self.txt_cv.delete(0, tk.END); self.txt_cv.insert(0, f"{self.cv_calc:.2f}")
        self.txt_cs.delete(0, tk.END); self.txt_cs.insert(0, f"{self.cs_calc:.2f}")

        self.ent_fit_xbq.delete(0, tk.END); self.ent_fit_xbq.insert(0, f"{self.xbq_calc:.2f}")
        self.ent_fit_cv.delete(0, tk.END); self.ent_fit_cv.insert(0, f"{self.cv_calc:.2f}")
        self.ent_fit_cs.delete(0, tk.END); self.ent_fit_cs.insert(0, f"{self.cs_calc:.2f}")

        self.update_three_points()
        self.distribution_changed()

    def update_three_points(self):
        if len(self.sorted_data) < 3: return
        _, p_haz, _ = self.get_empirical_probabilities()
        x5 = float(np.interp(5.0, p_haz, self.sorted_data))
        x50 = float(np.interp(50.0, p_haz, self.sorted_data))
        x95 = float(np.interp(95.0, p_haz, self.sorted_data))
        self.ent_x5.delete(0, tk.END); self.ent_x5.insert(0, f"{x5:.2f}")
        self.ent_x50.delete(0, tk.END); self.ent_x50.insert(0, f"{x50:.2f}")
        self.ent_x95.delete(0, tk.END); self.ent_x95.insert(0, f"{x95:.2f}")


    # =========================================================================
    # CHỨC NĂNG LƯU VÀ MỞ DỰ ÁN (.TSH) TỰ ĐỘNG XUẤT ẢNH BẢN VẼ
    # =========================================================================
    def save_project(self):
        """Lưu toàn bộ số liệu dự án (.TSH) đồng thời lưu luôn 1 file ảnh bản vẽ (.png)"""
        if len(self.sorted_data) == 0:
            messagebox.showwarning("Cảnh báo", "Chưa có số liệu để lưu dự án!")
            return

        f_path = filedialog.asksaveasfilename(
            defaultextension=".TSH",
            filetypes=[("TSTV Project File (*.TSH)", "*.TSH"), ("JSON files (*.json)", "*.json"), ("All files", "*.*")]
        )
        if not f_path:
            return

        project_state = {
            "parameter_schema": 2,
            "years": [int(y) for y in self.years],
            "raw_data": [float(x) for x in self.raw_data],
            "sorted_data": [float(x) for x in self.sorted_data],
            "xbq_calc": self.xbq_calc,
            "cv_calc": self.cv_calc,
            "cs_calc": self.cs_calc,
            "formula_idx": self.cbo_formula.current(),
            "dist_name": self.dist_var.get(),
            "method_id": self.method_var.get(),
            "fit_xbq": self.ent_fit_xbq.get(),
            "fit_cv": self.ent_fit_cv.get(),
            "fit_cs": self.ent_fit_cs.get(),
            "x5": self.ent_x5.get(),
            "x50": self.ent_x50.get(),
            "x95": self.ent_x95.get(),
            "title": self.txt_title.get(),
            "kyhieu": self.txt_kyhieu.get(),
            "donvi": self.txt_donvi.get(),
            "ng_ve": self.txt_ng_ve.get(),
            "ng_kt": self.txt_ng_kt.get(),
            "year_draw": self.txt_year_draw.get(),
            "ymin": self.txt_ymin.get(),
            "ymax": self.txt_ymax.get()
        }

        try:
            # 1. Lưu file cấu hình dự án (.TSH)
            with open(f_path, "w", encoding="utf-8") as f:
                json.dump(project_state, f, ensure_ascii=False, indent=2)

            # 2. Tự động lưu 1 file ảnh bản vẽ đường tần suất (.png) cùng tên
            img_path = os.path.splitext(f_path)[0] + ".png"
            img_saved = False
            try:
                fig = self.create_cad_figure()
                if fig is not None:
                    # Xuất ảnh độ phân giải cao 300 DPI
                    fig.savefig(img_path, dpi=300)
                    plt.close(fig)
                    img_saved = True
            except Exception as e_img:
                print(f"Lỗi khi lưu ảnh đồ thị tự động: {e_img}")

            if img_saved:
                messagebox.showinfo(
                    "Thành công",
                    f"Đã lưu tệp dự án và xuất bản vẽ thành công!\n\n"
                    f"📁 Tệp dự án: {f_path}\n"
                    f"🖼️ Tệp ảnh: {img_path}"
                )
            else:
                messagebox.showinfo("Thành công", f"Đã lưu tệp dự án thành công tại:\n{f_path}")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu dự án: {e}")

    def load_project(self):
        """Mở tệp dự án (.TSH) đã lưu để khôi phục lại toàn bộ công việc"""
        f_path = filedialog.askopenfilename(
            filetypes=[("TSTV Project File (*.TSH)", "*.TSH"), ("JSON files (*.json)", "*.json"), ("All files", "*.*")]
        )
        if not f_path:
            return

        try:
            with open(f_path, "r", encoding="utf-8") as f:
                ps = json.load(f)

            self.validate_sample(ps.get("raw_data", []))
            self.years = ps.get("years", [])
            self.raw_data = np.array(ps.get("raw_data", []))
            self.sorted_data = np.sort(self.raw_data)[::-1]
            self.update_data_table_and_stats()

            # Đổ dữ liệu vào bảng
            self.tree.delete(*self.tree.get_children())
            for i in range(len(self.raw_data)):
                self.tree.insert("", tk.END, values=(
                    i + 1,
                    self.years[i] if i < len(self.years) else i + 1,
                    f"{self.raw_data[i]:.2f}",
                    f"{self.sorted_data[i]:.2f}"
                ))

            # Khôi phục các ô đặc trưng mẫu
            self.txt_xbq.delete(0, tk.END); self.txt_xbq.insert(0, f"{self.xbq_calc:.2f}")
            self.txt_cv.delete(0, tk.END); self.txt_cv.insert(0, f"{self.cv_calc:.2f}")
            self.txt_cs.delete(0, tk.END); self.txt_cs.insert(0, f"{self.cs_calc:.2f}")

            # Khôi phục công thức và phân phối
            if "formula_idx" in ps:
                self.cbo_formula.current(ps["formula_idx"])
            if "dist_name" in ps:
                self.dist_var.set(ps["dist_name"])
            if "method_id" in ps:
                self.method_var.set(ps["method_id"])

            # Khôi phục tham số nắn tuyến & 3 điểm
            self.ent_fit_xbq.delete(0, tk.END); self.ent_fit_xbq.insert(0, ps.get("fit_xbq", ""))
            self.ent_fit_cv.delete(0, tk.END); self.ent_fit_cv.insert(0, ps.get("fit_cv", ""))
            self.ent_fit_cs.delete(0, tk.END); self.ent_fit_cs.insert(0, ps.get("fit_cs", ""))

            self.ent_x5.delete(0, tk.END); self.ent_x5.insert(0, ps.get("x5", ""))
            self.ent_x50.delete(0, tk.END); self.ent_x50.insert(0, ps.get("x50", ""))
            self.ent_x95.delete(0, tk.END); self.ent_x95.insert(0, ps.get("x95", ""))

            if ps.get("parameter_schema", 1) < 2 and self.dist_var.get() == "LOG-PEARSON III":
                self.distribution_changed()
                messagebox.showwarning("Tham số dự án cũ", "Tham số Log-Pearson III cũ không cùng quy ước. Đã đặt lại bằng mô men log₁₀; hãy kiểm tra tham số thích hợp trước khi tính.")

            # Khôi phục khung tên
            self.txt_title.delete(0, tk.END); self.txt_title.insert(0, ps.get("title", ""))
            self.txt_kyhieu.delete(0, tk.END); self.txt_kyhieu.insert(0, ps.get("kyhieu", "X"))
            self.txt_donvi.delete(0, tk.END); self.txt_donvi.insert(0, ps.get("donvi", "mm"))
            self.txt_ng_ve.delete(0, tk.END); self.txt_ng_ve.insert(0, ps.get("ng_ve", "Nguyễn Kim Tuyên"))
            self.txt_ng_kt.delete(0, tk.END); self.txt_ng_kt.insert(0, ps.get("ng_kt", ""))
            self.txt_year_draw.delete(0, tk.END); self.txt_year_draw.insert(0, ps.get("year_draw", "2026"))

            # Khôi phục Ymin, Ymax
            self.txt_ymin.delete(0, tk.END); self.txt_ymin.insert(0, ps.get("ymin", "0"))
            self.txt_ymax.delete(0, tk.END); self.txt_ymax.insert(0, ps.get("ymax", ""))

            messagebox.showinfo("Thành công", f"Đã mở và khôi phục dự án thành công từ:\n{f_path}")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc tệp dự án: {e}")

    def get_empirical_probabilities(self):
        """Tính tần suất kinh nghiệm P (%) theo công thức đã chọn"""
        n = len(self.sorted_data)
        m = np.arange(1, n + 1)
        idx_f = self.cbo_formula.current()
        if idx_f == 0:
            formula_name = "Vị trí vẽ α=0,25 [P = (m-0.25)/(n+0.5) * 100%]"
            p_emp = (m - 0.25) / (n + 0.5) * 100.0
        elif idx_f == 1:
            formula_name = "Weibull [P = m/(n+1) * 100%]"
            p_emp = m / (n + 1) * 100.0
        else:
            formula_name = "Hazen [P = (m-0.5)/n * 100%]"
            p_emp = (m - 0.5) / n * 100.0
        return m, p_emp, formula_name

    def show_emp_table_window(self):
        """Hiển thị cửa sổ Kết quả tần suất kinh nghiệm"""
        if len(self.sorted_data) == 0:
            messagebox.showwarning("Cảnh báo", "Vui lòng mở tệp số liệu TXT hoặc tệp dự án .TSH trước.")
            return

        if self.tbl_emp_win is not None and self.tbl_emp_win.winfo_exists():
            self.tbl_emp_win.destroy()

        n = len(self.sorted_data)
        m_arr, p_emp, formula_name = self.get_empirical_probabilities()
        donvi = self.txt_donvi.get()

        self.tbl_emp_win = tk.Toplevel(self.root)
        self.tbl_emp_win.title("Kết quả tần suất kinh nghiệm")
        self.tbl_emp_win.geometry("720x620")
        self.tbl_emp_win.configure(bg="#eef2f7")
        self.tbl_emp_win.after_idle(lambda window=self.tbl_emp_win: self.style_dialog(window))

        tk.Label(self.tbl_emp_win, text="Kết quả tần suất kinh nghiệm", 
                 font=("Times New Roman", 13, "bold"), fg="#6a1b9a").pack(pady=(8, 2))
        tk.Label(self.tbl_emp_win, text=f"Công thức: {formula_name} | Số năm quan trắc: n = {n}", 
                 font=("Times New Roman", 10, "italic")).pack(pady=(0, 2))
        tk.Label(self.tbl_emp_win, text="Hướng dẫn: Bấm chuột trái vào tiêu đề cột hoặc nhấp chuột phải để sao chép riêng từng cột", 
                 font=("Arial", 8, "italic"), fg="#004d40").pack(pady=(0, 4))

        cols_emp = ("stt", "nam", "xi", "xss", "p", "note")
        col_titles_emp = {
            "stt": "STT",
            "nam": "NĂM",
            "xi": f"X(i) ({donvi})",
            "xss": f"X(i) sắp xếp ({donvi})",
            "p": "Tần suất P (%)",
            "note": "Ghi chú"
        }

        tbl_fr = tk.Frame(self.tbl_emp_win)
        tbl_fr.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree_emp = ttk.Treeview(tbl_fr, columns=cols_emp, show="headings", height=16)

        sb_y = ttk.Scrollbar(tbl_fr, orient=tk.VERTICAL, command=tree_emp.yview)
        tree_emp.configure(yscroll=sb_y.set)
        tree_emp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)

        def copy_single_emp_col(col_key, include_header=True):
            col_idx = cols_emp.index(col_key)
            c_name = col_titles_emp[col_key]
            lines = [c_name] if include_header else []
            for item in tree_emp.get_children():
                vals = tree_emp.item(item, "values")
                lines.append(str(vals[col_idx]))
            out_str = "\n".join(lines)
            self.root.clipboard_clear()
            self.root.clipboard_append(out_str)
            messagebox.showinfo("Đã sao chép", f"Đã sao chép cột '{c_name}' vào Clipboard!\nBạn có thể dán (Ctrl+V) vào Excel.")

        for col_k in cols_emp:
            tree_emp.heading(col_k, text=col_titles_emp[col_k], 
                             command=lambda ck=col_k: copy_single_emp_col(ck, include_header=True))

        tree_emp.column("stt", width=45, anchor=tk.CENTER)
        tree_emp.column("nam", width=70, anchor=tk.CENTER)
        tree_emp.column("xi", width=105, anchor=tk.E)
        tree_emp.column("xss", width=125, anchor=tk.E)
        tree_emp.column("p", width=110, anchor=tk.CENTER)
        tree_emp.column("note", width=125, anchor=tk.CENTER)

        for i in range(n):
            stt_val = i + 1
            nam_val = self.years[i] if i < len(self.years) else i + 1
            xi_val = self.raw_data[i]
            xss_val = self.sorted_data[i]
            p_val = p_emp[i]
            if p_val <= 50.0:
                t_val = 100.0 / p_val if p_val > 0 else 0.0
                note_str = f"T ≈ {t_val:.1f} năm"
            else:
                note_str = "-"

            tree_emp.insert("", tk.END, values=(
                stt_val,
                nam_val,
                f"{xi_val:.2f}",
                f"{xss_val:.2f}",
                f"{p_val:.2f}%",
                note_str
            ))

        def popup_menu_emp(event):
            col_id = tree_emp.identify_column(event.x)
            row_id = tree_emp.identify_row(event.y)
            menu = tk.Menu(self.tbl_emp_win, tearoff=0)
            
            if col_id:
                col_idx = int(col_id.replace('#', '')) - 1
                if 0 <= col_idx < len(cols_emp):
                    col_k = cols_emp[col_idx]
                    c_title = col_titles_emp[col_k]
                    menu.add_command(label=f"Sao chép cột '{c_title}' (kèm tiêu đề)", 
                                     command=lambda: copy_single_emp_col(col_k, True))
                    menu.add_command(label=f"Sao chép cột '{c_title}' (chỉ số liệu)", 
                                     command=lambda: copy_single_emp_col(col_k, False))
                    menu.add_separator()
            
            if row_id and col_id:
                col_idx = int(col_id.replace('#', '')) - 1
                cell_val = tree_emp.item(row_id, "values")[col_idx]
                def copy_cell(v=cell_val):
                    self.root.clipboard_clear()
                    self.root.clipboard_append(str(v))
                menu.add_command(label=f"📄 Sao chép ô này: {cell_val}", command=copy_cell)
                menu.add_separator()

            menu.add_command(label="Sao chép toàn bộ bảng", command=copy_emp_to_clipboard)
            menu.tk_popup(event.x_root, event.y_root)

        tree_emp.bind("<Button-3>", popup_menu_emp)
        tree_emp.bind("<Button-2>", popup_menu_emp)

        def copy_emp_to_clipboard():
            out = f"STT\tNAM\tX(i) ({donvi})\tX(i) sap xep ({donvi})\tTan suat P(%)\tGhi chu\n"
            for i in range(n):
                nam_val = self.years[i] if i < len(self.years) else i + 1
                p_val = p_emp[i]
                note_val = f"T ≈ {100.0/p_val:.1f} nam" if p_val <= 50.0 else "-"
                out += f"{i+1}\t{nam_val}\t{self.raw_data[i]:.2f}\t{self.sorted_data[i]:.2f}\t{p_val:.2f}%\t{note_val}\n"
            self.root.clipboard_clear()
            self.root.clipboard_append(out)
            messagebox.showinfo("Thành công", "Đã sao chép toàn bộ bảng kinh nghiệm vào Clipboard!")

        def export_emp_csv():
            f_save = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV file", "*.csv")])
            if not f_save: return
            with open(f_save, "w", encoding="utf-8-sig") as f:
                f.write(f"STT,NAM,X(i) ({donvi}),X(i) sap xep ({donvi}),Tan suat P(%),Ghi chu\n")
                for i in range(n):
                    nam_val = self.years[i] if i < len(self.years) else i + 1
                    p_val = p_emp[i]
                    note_val = f"T ≈ {100.0/p_val:.1f} nam" if p_val <= 50.0 else "-"
                    f.write(f"{i+1},{nam_val},{self.raw_data[i]:.2f},{self.sorted_data[i]:.2f},{p_val:.2f}%,{note_val}\n")
            messagebox.showinfo("Thành công", f"Đã lưu bảng tần suất kinh nghiệm: {f_save}")

        btn_box = tk.Frame(self.tbl_emp_win, pady=8)
        btn_box.pack(fill=tk.X, padx=10)

        tk.Button(btn_box, text="Sao chép cả bảng", bg="#6a1b9a", fg="white", font=("Arial", 9, "bold"),
                  padx=6, pady=4, command=copy_emp_to_clipboard).pack(side=tk.LEFT, padx=3)

        cbo_box = tk.LabelFrame(btn_box, text=" Sao chép cột riêng ", font=("Arial", 8, "bold"), padx=4, pady=2)
        cbo_box.pack(side=tk.LEFT, padx=8)

        col_display_list = [col_titles_emp[c] for c in cols_emp]
        cbo_emp_col = ttk.Combobox(cbo_box, values=col_display_list, state="readonly", width=16)
        cbo_emp_col.current(3)
        cbo_emp_col.pack(side=tk.LEFT, padx=3)

        def on_copy_emp_selected_col():
            idx = cbo_emp_col.current()
            if idx >= 0:
                copy_single_emp_col(cols_emp[idx], include_header=True)

        tk.Button(cbo_box, text="Sao chép cột", bg="#ede7f6", fg="#4a148c", font=("Arial", 8, "bold"),
                  command=on_copy_emp_selected_col).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_box, text="Xuất bảng dữ liệu (.csv)", bg="#388e3c", fg="white", font=("Arial", 9, "bold"),
                  padx=8, pady=4, command=export_emp_csv).pack(side=tk.RIGHT, padx=3)

    @staticmethod
    def validate_sample(data, logarithmic=False):
        values = np.asarray(data, dtype=float)
        if values.ndim != 1 or len(values) < 3 or not np.all(np.isfinite(values)):
            raise ValueError("Cần ít nhất 3 giá trị quan trắc hữu hạn.")
        if logarithmic and np.any(values <= 0):
            raise ValueError("Log-Pearson III yêu cầu toàn bộ số liệu lớn hơn 0; không tự bỏ giá trị 0 hoặc âm.")
        return values

    @staticmethod
    def sample_moments(data):
        values = TSTVAdvancedApp.validate_sample(data)
        mean = float(np.mean(values)); sd = float(np.std(values, ddof=1))
        n = len(values)
        skew = float(n * np.sum((values-mean)**3) / ((n-1)*(n-2)*sd**3)) if sd > 0 else 0.0
        return mean, sd, skew

    def distribution_changed(self, *args):
        logarithmic = self.dist_var.get() == "LOG-PEARSON III"
        labels = ("Trung bình của log₁₀(X)", "Độ lệch chuẩn của log₁₀(X)", "Hệ số bất đối xứng của log₁₀(X)") if logarithmic else ("Giá trị trung bình (X̄)", "Hệ số biến thiên (Cv)", "Hệ số bất đối xứng (Cs)")
        for row, label in enumerate(labels):
            self.fit_labels[row].configure(text=label)
        if len(self.sorted_data) >= 3:
            try:
                data = self.validate_sample(self.sorted_data, logarithmic)
                mean, sd, skew = self.sample_moments(np.log10(data) if logarithmic else data)
                second = sd if logarithmic else (sd / mean if mean > 0 else 0)
                for entry, value in zip((self.ent_fit_xbq, self.ent_fit_cv, self.ent_fit_cs), (mean, second, skew)):
                    entry.delete(0, tk.END); entry.insert(0, format(value, '.10g'))
            except ValueError:
                for entry in (self.ent_fit_xbq, self.ent_fit_cv, self.ent_fit_cs): entry.delete(0, tk.END)

    def get_distribution_parameters(self):
        dist_name = self.dist_var.get(); method_id = self.method_var.get()
        logarithmic = dist_name == "LOG-PEARSON III"
        try:
            data = self.validate_sample(self.sorted_data, logarithmic)
            if method_id == 1:
                mean, sd, cs = self.sample_moments(np.log10(data) if logarithmic else data)
                if not logarithmic and mean <= 0:
                    raise ValueError("Biểu diễn bằng Cv yêu cầu giá trị trung bình dương.")
                cv = sd if logarithmic else sd / mean
                method_desc = "Phương pháp mô men"
            elif method_id == 2:
                mean, cv, cs = (float(e.get().replace(',', '.')) for e in (self.ent_fit_xbq,self.ent_fit_cv,self.ent_fit_cs))
                method_desc = "Phương pháp thích hợp (tham số nhập trực tiếp)"
            else:
                points = np.array([float(e.get().replace(',', '.')) for e in (self.ent_x5,self.ent_x50,self.ent_x95)])
                if not np.all(np.isfinite(points)) or not points[0] > points[1] > points[2]:
                    raise ValueError("Ba điểm phải hữu hạn và có X(5%) > X(50%) > X(95%).")
                if logarithmic and np.any(points <= 0): raise ValueError("Ba điểm Log-Pearson III phải lớn hơn 0.")
                target = np.log10(points) if logarithmic else points
                mean0, sd0, skew0 = self.sample_moments(np.log10(data) if logarithmic else data)
                scale0 = max(float(np.ptp(target)), sd0, 1e-6)
                def residual(params):
                    location, logscale = params[:2]; scale = np.exp(logscale)
                    predicted = gumbel_r.ppf([.95,.5,.05],loc=location,scale=scale) if dist_name == "GUMBEL" else pearson3.ppf([.95,.5,.05],skew=params[2],loc=location,scale=scale)
                    return (predicted-target)/scale0
                initial = [mean0, np.log(scale0)] if dist_name == "GUMBEL" else [mean0, np.log(scale0), skew0]
                fit = least_squares(residual, initial, max_nfev=3000)
                if not fit.success or not np.all(np.isfinite(fit.x)) or not np.all(np.isfinite(fit.fun)):
                    raise ValueError("Phương pháp ba điểm chưa hội tụ; kiểm tra lại số liệu.")
                if dist_name == "GUMBEL":
                    # Two parameters cannot generally pass exactly through all three points.
                    sd = np.exp(fit.x[1])*np.pi/np.sqrt(6)
                    mean = fit.x[0] + np.euler_gamma*np.exp(fit.x[1]); cs = 1.1395470994
                else:
                    mean, sd, cs = float(fit.x[0]), float(np.exp(fit.x[1])), float(fit.x[2])
                    if np.max(np.abs(fit.fun)) > 1e-4: raise ValueError("Ba điểm không khớp phân phối Pearson III trong dung sai yêu cầu.")
                if not logarithmic and mean <= 0: raise ValueError("Ba điểm cho trung bình không dương; kiểm tra lại.")
                cv = sd if logarithmic else sd/mean
                method_desc = "Phương pháp ba điểm" + (" (Gumbel: bình phương tối thiểu)" if dist_name == "GUMBEL" else "")
            if not np.all(np.isfinite([mean,cv,cs])) or cv < 0 or (not logarithmic and mean <= 0):
                raise ValueError("Tham số phải hữu hạn; độ phân tán không âm và trung bình trên miền gốc phải dương.")
            if dist_name == "GUMBEL": cs = 1.1395470994
            return mean, cv, cs, dist_name, method_desc + " — " + dist_name
        except (ValueError, FloatingPointError, OverflowError) as exc:
            messagebox.showerror("Không thể tính tần suất", str(exc)); return None

    def calculate_xp(self, p_percent, mean, cv, cs, dist_name):
        probabilities = np.asarray(p_percent, dtype=float)
        if not np.all(np.isfinite(probabilities)) or np.any((probabilities <= 0) | (probabilities >= 100)):
            raise ValueError("Tần suất phải nằm trong khoảng 0% < P < 100%.")
        if not np.all(np.isfinite([mean,cv,cs])) or cv < 0:
            raise ValueError("Tham số phân phối không hợp lệ.")
        q = 1-probabilities/100
        scale = cv if dist_name == "LOG-PEARSON III" else mean*cv
        if scale < 0: raise ValueError("Độ lệch chuẩn không được âm.")
        if scale == 0:
            values = np.full_like(q, mean)
        elif dist_name in ("PEARSON III", "LOG-PEARSON III"):
            values = pearson3.ppf(q, skew=cs, loc=mean, scale=scale)
        elif dist_name == "GUMBEL":
            beta = scale*np.sqrt(6)/np.pi
            values = gumbel_r.ppf(q, loc=mean-np.euler_gamma*beta, scale=beta)
        else: raise ValueError("Phân phối không được hỗ trợ.")
        if dist_name == "LOG-PEARSON III": values = np.power(10.0, values)
        if not np.all(np.isfinite(values)): raise ValueError("Kết quả vượt miền số hữu hạn; kiểm tra tham số.")
        return values

    def parameter_summary(self, mean, cv, cs, dist_name):
        if dist_name == "LOG-PEARSON III":
            return f"Trung bình log₁₀(X) = {mean:.4g} | Độ lệch chuẩn log₁₀(X) = {cv:.4g} | Hệ số bất đối xứng = {cs:.4g}"
        return f"Giá trị trung bình = {mean:.4g} | Hệ số biến thiên = {cv:.4g} | Hệ số bất đối xứng = {cs:.4g}"

    def get_return_period_note(self, p):
        """Tính chu kỳ lặp lại T cho các tần suất thiết kế thủy văn chuẩn"""
        if p > 50.0:
            return "-"
        t = 100.0 / p
        if abs(t - round(t)) < 1e-3:
            return f"T = {int(round(t))} năm"
        elif abs(t * 10 - round(t * 10)) < 1e-3:
            return f"T = {t:.1f} năm"
        return f"T ≈ {t:.1f} năm"

    def show_xp_table_window(self):
        """Hiển thị cửa sổ Kết quả tần suất lý luận"""
        if len(self.sorted_data) == 0:
            messagebox.showwarning("Cảnh báo", "Vui lòng mở tệp số liệu TXT hoặc tệp dự án .TSH trước.")
            return

        params = self.get_distribution_parameters()
        if not params: return
        mean, cv, cs, dist_name, method_desc = params

        if self.tbl_win is not None and self.tbl_win.winfo_exists():
            self.tbl_win.destroy()

        p_list = [
            0.01, 0.10, 0.20, 0.33, 0.50, 1.00, 1.50, 2.00, 3.00, 4.0,
            5.00, 10.00, 20.00, 25.00, 30.00, 40.00, 50.00, 60.00, 70.00,
            75.00, 80.00, 85.00, 90.00, 95.00, 97.00, 99.00, 99.90, 99.99
        ]
        xp_vals = self.calculate_xp(p_list, mean, cv, cs, dist_name)
        donvi = self.txt_donvi.get()

        self.tbl_win = tk.Toplevel(self.root)
        self.tbl_win.title("Kết quả tần suất lý luận")
        self.tbl_win.geometry("700x640")
        self.tbl_win.configure(bg="#eef2f7")
        self.tbl_win.after_idle(lambda window=self.tbl_win: self.style_dialog(window))

        tk.Label(self.tbl_win, text="Kết quả tần suất lý luận", 
                 font=("Times New Roman", 13, "bold"), fg="blue").pack(pady=(8, 2))
        tk.Label(self.tbl_win, text=self.parameter_summary(mean, cv, cs, dist_name), 
                 font=("Times New Roman", 10, "italic")).pack(pady=(0, 2))
        tk.Label(self.tbl_win, text="Hướng dẫn: Bấm chuột trái vào tiêu đề cột hoặc nhấp chuột phải để sao chép riêng từng cột", 
                 font=("Arial", 8, "italic"), fg="#004d40").pack(pady=(0, 4))

        cols_tbl = ("stt", "p", "kp", "xp", "note")
        col_titles_xp = {
            "stt": "STT",
            "p": "Tần suất P (%)",
            "kp": "Kp",
            "xp": f"Xp ({donvi})",
            "note": "Ghi chú"
        }

        tbl_fr = tk.Frame(self.tbl_win)
        tbl_fr.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree_xp = ttk.Treeview(tbl_fr, columns=cols_tbl, show="headings", height=18)

        sb_y = ttk.Scrollbar(tbl_fr, orient=tk.VERTICAL, command=tree_xp.yview)
        tree_xp.configure(yscroll=sb_y.set)
        tree_xp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)

        def copy_single_xp_col(col_key, include_header=True):
            col_idx = cols_tbl.index(col_key)
            c_name = col_titles_xp[col_key]
            lines = [c_name] if include_header else []
            for item in tree_xp.get_children():
                vals = tree_xp.item(item, "values")
                lines.append(str(vals[col_idx]))
            out_str = "\n".join(lines)
            self.root.clipboard_clear()
            self.root.clipboard_append(out_str)
            messagebox.showinfo("Đã sao chép", f"Đã sao chép cột '{c_name}' vào Clipboard!\nBạn có thể dán (Ctrl+V) vào Excel.")

        for col_k in cols_tbl:
            tree_xp.heading(col_k, text=col_titles_xp[col_k], 
                            command=lambda ck=col_k: copy_single_xp_col(ck, include_header=True))

        tree_xp.column("stt", width=45, anchor=tk.CENTER)
        tree_xp.column("p", width=115, anchor=tk.CENTER)
        tree_xp.column("kp", width=90, anchor=tk.CENTER)
        tree_xp.column("xp", width=130, anchor=tk.E)
        tree_xp.column("note", width=140, anchor=tk.CENTER)

        for idx, (p, val) in enumerate(zip(p_list, xp_vals), start=1):
            kp_val = (val / self.xbq_calc) if self.xbq_calc != 0 else 0.0
            note_str = self.get_return_period_note(p)
            p_display = f"{p:.2f}%" if p != 4.0 else "4.00%"
            tree_xp.insert("", tk.END, values=(idx, p_display, f"{kp_val:.2f}", f"{val:.2f}", note_str))

        def popup_menu_xp(event):
            col_id = tree_xp.identify_column(event.x)
            row_id = tree_xp.identify_row(event.y)
            menu = tk.Menu(self.tbl_win, tearoff=0)
            
            if col_id:
                col_idx = int(col_id.replace('#', '')) - 1
                if 0 <= col_idx < len(cols_tbl):
                    col_k = cols_tbl[col_idx]
                    c_title = col_titles_xp[col_k]
                    menu.add_command(label=f"Sao chép cột '{c_title}' (kèm tiêu đề)", 
                                     command=lambda: copy_single_xp_col(col_k, True))
                    menu.add_command(label=f"Sao chép cột '{c_title}' (chỉ số liệu)", 
                                     command=lambda: copy_single_xp_col(col_k, False))
                    menu.add_separator()
            
            if row_id and col_id:
                col_idx = int(col_id.replace('#', '')) - 1
                cell_val = tree_xp.item(row_id, "values")[col_idx]
                def copy_cell(v=cell_val):
                    self.root.clipboard_clear()
                    self.root.clipboard_append(str(v))
                menu.add_command(label=f"📄 Sao chép ô này: {cell_val}", command=copy_cell)
                menu.add_separator()

            menu.add_command(label="Sao chép toàn bộ bảng", command=copy_to_clipboard)
            menu.tk_popup(event.x_root, event.y_root)

        tree_xp.bind("<Button-3>", popup_menu_xp)
        tree_xp.bind("<Button-2>", popup_menu_xp)

        def copy_to_clipboard():
            out = f"STT\tTan suat P(%)\tKp\tXp ({donvi})\tGhi chu\n"
            for idx, (p, val) in enumerate(zip(p_list, xp_vals), start=1):
                kp_val = (val / self.xbq_calc) if self.xbq_calc != 0 else 0.0
                note_str = self.get_return_period_note(p)
                p_display = f"{p:.2f}%"
                out += f"{idx}\t{p_display}\t{kp_val:.2f}\t{val:.2f}\t{note_str}\n"
            self.root.clipboard_clear()
            self.root.clipboard_append(out)
            messagebox.showinfo("Thành công", f"Đã sao chép toàn bộ {len(p_list)} dòng bảng lý luận vào Clipboard!")

        def export_csv():
            f_save = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV file", "*.csv")])
            if not f_save: return
            with open(f_save, "w", encoding="utf-8-sig") as f:
                f.write(f"STT,Tan suat P(%),Kp,Xp ({donvi}),Ghi chu\n")
                for idx, (p, val) in enumerate(zip(p_list, xp_vals), start=1):
                    kp_val = (val / self.xbq_calc) if self.xbq_calc != 0 else 0.0
                    note_str = self.get_return_period_note(p)
                    f.write(f"{idx},{p:.2f}%,{kp_val:.2f},{val:.2f},{note_str}\n")
            messagebox.showinfo("Thành công", f"Đã lưu bảng ra file: {f_save}")

        btn_box = tk.Frame(self.tbl_win, pady=8)
        btn_box.pack(fill=tk.X, padx=10)

        tk.Button(btn_box, text="Sao chép cả bảng", bg="#1976d2", fg="white", font=("Arial", 9, "bold"),
                  padx=6, pady=4, command=copy_to_clipboard).pack(side=tk.LEFT, padx=3)

        cbo_box = tk.LabelFrame(btn_box, text=" Sao chép cột riêng ", font=("Arial", 8, "bold"), padx=4, pady=2)
        cbo_box.pack(side=tk.LEFT, padx=8)

        col_display_list = [col_titles_xp[c] for c in cols_tbl]
        cbo_xp_col = ttk.Combobox(cbo_box, values=col_display_list, state="readonly", width=16)
        cbo_xp_col.current(3)
        cbo_xp_col.pack(side=tk.LEFT, padx=3)

        def on_copy_xp_selected_col():
            idx = cbo_xp_col.current()
            if idx >= 0:
                copy_single_xp_col(cols_tbl[idx], include_header=True)

        tk.Button(cbo_box, text="Sao chép cột", bg="#e3f2fd", fg="#0d47a1", font=("Arial", 8, "bold"),
                  command=on_copy_xp_selected_col).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_box, text="Xuất bảng dữ liệu (.csv)", bg="#388e3c", fg="white", font=("Arial", 9, "bold"),
                  padx=8, pady=4, command=export_csv).pack(side=tk.RIGHT, padx=3)

    # =========================================================================
    # HÀM DỰNG ĐỒ THỊ BẢN VẼ CHUẨN CAD (TÁI SỬ DỤNG CHO XEM VÀ XUẤT FILE)
    # =========================================================================
    def create_cad_figure(self):
        """Khởi tạo Figure đồ thị tần suất kỹ thuật hoàn chỉnh để hiển thị hoặc lưu ảnh"""
        if len(self.sorted_data) == 0:
            return None

        params = self.get_distribution_parameters()
        if not params:
            return None
        mean, cv, cs, dist_name, method_desc = params

        m_arr, p_emp, formula_name = self.get_empirical_probabilities()

        fig = plt.figure(figsize=(11.5, 7.8), dpi=100, facecolor='white')

        # 1. Khung viền ngoài cùng khổ giấy
        fig.patches.append(patches.Rectangle((0.038, 0.04), 0.924, 0.92, fill=False, 
                                             edgecolor='black', linewidth=1.5, transform=fig.transFigure))

        ax = fig.add_axes([0.09, 0.08, 0.85, 0.83])
        ax.grid(False)

        # 2. Tính toán đường cong lý thuyết
        p_dense = np.logspace(np.log10(0.01), np.log10(99.99), 800)
        x_dense = self.calculate_xp(p_dense, mean, cv, cs, dist_name)

        x_emp_axis = norm.ppf(p_emp / 100.0)
        x_theory_axis = norm.ppf(p_dense / 100.0)

        # 3. Giới hạn trục Y
        try:
            y_min = float(self.txt_ymin.get().strip())
        except (ValueError, AttributeError):
            y_min = 0.0

        ymax_input = self.txt_ymax.get().strip() if hasattr(self, 'txt_ymax') else ""
        try:
            custom_y_max = float(ymax_input) if ymax_input else None
        except ValueError:
            custom_y_max = None

        y_curve_peak = max(np.max(self.sorted_data), float(np.max(x_dense[p_dense >= 0.05])))

        if custom_y_max is not None and custom_y_max > y_min:
            y_max = custom_y_max
            step = (y_max - y_min) / 14.0
        else:
            span = max(float(y_curve_peak-y_min), abs(float(y_curve_peak))*.1, 1e-6)
            ticks = MaxNLocator(nbins=13).tick_values(y_min, y_min+span)
            step = float(ticks[1]-ticks[0])
            y_max = y_min + 14.0 * step

        y_ticks = np.array([y_min + i * step for i in range(14)])

        # Mốc tần suất trục X
        x_min_bound = norm.ppf(0.0001)   # P = 0.01%
        x_max_bound = norm.ppf(0.9999)   # P = 99.99%
        x_p5 = norm.ppf(0.05)             # P = 5%
        x_p20 = norm.ppf(0.20)           # P = 20%
        x_p75 = norm.ppf(0.75)           # P = 75%
        x_p92 = norm.ppf(0.92)           # P = 92%
        x_p99 = norm.ppf(0.99)           # P = 99%
        x_p999 = norm.ppf(0.999)         # P = 99.9%

        # 4. Kẻ lưới trục Y
        for y_val in y_ticks:
            ax.axhline(y_val, color='#777777', linewidth=0.75, zorder=2)
        ax.axhline(y_max, color='black', linewidth=1.2, zorder=2)

        for i in range(14):
            for k in range(1, 5):
                y_sub = y_min + i * step + k * (step / 5.0)
                ax.axhline(y_sub, color='#e0e0e0', linewidth=0.4, zorder=1)

        # 5. Kẻ lưới trục X
        ticks_p = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 15.0, 20.0, 30.0, 
                   40.0, 50.0, 60.0, 70.0, 80.0, 85.0, 90.0, 95.0, 99.0, 99.9, 99.95, 99.99]
        ticks_labels = ["001", "005", "01", "05", "10", "5", "10", "15", "20", "30", 
                        "40", "50", "60", "70", "80", "85", "90", "95", "99", "999", "9995", "9999"]
        
        for p in ticks_p:
            ax.axvline(norm.ppf(p / 100.0), color='#777777', linewidth=0.75, zorder=2)

        sub_p = (
            list(np.arange(0.02, 0.05, 0.01)) +
            list(np.arange(0.06, 0.10, 0.01)) +
            list(np.arange(0.20, 0.50, 0.10)) +
            list(np.arange(0.60, 1.00, 0.10)) +
            list(np.arange(2.0, 5.0, 1.0)) +
            list(np.arange(6.0, 10.0, 1.0)) +
            list(np.arange(91.0, 95.0, 1.0)) +
            list(np.arange(96.0, 99.0, 1.0)) +
            [99.2, 99.4, 99.6, 99.8, 99.92, 99.94, 99.96, 99.98]
        )
        for sp in sub_p:
            ax.axvline(norm.ppf(sp / 100.0), color='#e0e0e0', linewidth=0.4, zorder=1)

        # 6. Đường cong lý thuyết & Điểm kinh nghiệm
        ax.plot(x_theory_axis, x_dense, color='black', linewidth=1.2, zorder=4)
        ax.plot(x_emp_axis, self.sorted_data, 'o', color='black', markersize=2.2, zorder=5)

        ax.set_xlim([x_min_bound, x_max_bound])
        ax.set_ylim([y_min, y_max])
        ax.set_xticks([norm.ppf(p / 100.0) for p in ticks_p])
        ax.set_xticklabels(ticks_labels, fontsize=8.5)
        ax.set_yticks(y_ticks)
        ax.set_yticklabels([f"{y:.1f}" for y in y_ticks], fontsize=9)

        for spine in ax.spines.values():
            spine.set_color('black')
            spine.set_linewidth(1.2)

        # 7. Khung tiêu đề
        title_box = patches.Rectangle((x_p5, y_max - step), x_max_bound - x_p5, step,
                                      facecolor='white', edgecolor='black', linewidth=1.1, zorder=6)
        ax.add_patch(title_box)
        ax.text((x_p5 + x_max_bound) / 2.0, y_max - 0.5 * step, self.txt_title.get(), 
                fontsize=11, fontweight='bold', ha='center', va='center', zorder=7)

        # Ký hiệu trục Y
        kyhieu_txt = self.txt_kyhieu.get()
        donvi_txt = self.txt_donvi.get()
        ax.text(-0.035, y_max - 0.35 * step, kyhieu_txt, transform=ax.get_yaxis_transform(),
                fontsize=11.5, fontweight='bold', ha='center', va='center', zorder=7)
        ax.text(-0.035, y_max - 0.75 * step, f"({donvi_txt})", transform=ax.get_yaxis_transform(),
                fontsize=9.0, ha='center', va='center', zorder=7)

        # 8. Bảng thống kê tham số
        x_tbl_l = norm.ppf(0.40)
        x_tbl_r = norm.ppf(0.99)
        w_tbl = x_tbl_r - x_tbl_l
        h_tbl = 2.0 * step
        y_tbl_b = y_max - 3.0 * step

        ax.add_patch(patches.Rectangle((x_tbl_l, y_tbl_b), w_tbl, h_tbl,
                                       facecolor='white', edgecolor='black', linewidth=1.1, zorder=6))

        sym = kyhieu_txt if kyhieu_txt else "X"
        x_bar_math = f"Mean log10 = {mean:.3f}" if dist_name == "LOG-PEARSON III" else rf"$\overline{{\mathrm{{{sym}}}}} = {mean:.2f}$"

        ax.text(x_tbl_l + 0.06 * w_tbl, y_tbl_b + 1.62 * step, x_bar_math, fontsize=10.0, va='center', zorder=8)
        ax.text(x_tbl_l + 0.68 * w_tbl, y_tbl_b + 1.62 * step, f"N = {len(self.sorted_data)}", fontsize=10.0, va='center', zorder=8)
        ax.text(x_tbl_l + 0.06 * w_tbl, y_tbl_b + 1.18 * step, (f"SD log10 = {cv:.3f}" if dist_name == "LOG-PEARSON III" else f"Cv = {cv:.2f}"), fontsize=10.0, va='center', zorder=8)
        ax.text(x_tbl_l + 0.06 * w_tbl, y_tbl_b + 0.74 * step, f"Cs = {cs:.2f}", fontsize=10.0, va='center', zorder=8)
        ax.text((x_tbl_l + x_tbl_r) / 2.0, y_tbl_b + 0.28 * step, method_desc.upper(), 
                fontsize=8.0, fontweight='bold', ha='center', va='center', zorder=8)

        # 9. Khung tên bản vẽ
        h_kt = 1.35 * step
        w_kt = x_max_bound - x_p5
        ax.add_patch(patches.Rectangle((x_p5, y_min), w_kt, h_kt,
                                       facecolor='white', edgecolor='black', linewidth=1.1, zorder=6))

        ax.plot([x_p999, x_p999], [y_min, y_min + h_kt], color='black', linewidth=0.9, zorder=7)
        ax.text((x_p999 + x_max_bound) / 2.0, y_min + h_kt / 2.0, self.txt_year_draw.get(), 
                fontsize=11.0, fontweight='bold', ha='center', va='center', zorder=8)

        y_kt_mid = y_min + h_kt / 2.0
        ax.plot([x_p5, x_p999], [y_kt_mid, y_kt_mid], color='black', linewidth=0.9, zorder=7)

        ax.plot([x_p20, x_p20], [y_min, y_kt_mid], color='black', linewidth=0.8, zorder=7)
        ax.plot([x_p75, x_p75], [y_min, y_kt_mid], color='black', linewidth=0.8, zorder=7)
        ax.plot([x_p92, x_p92], [y_min, y_kt_mid], color='black', linewidth=0.8, zorder=7)

        y_txt_b = y_min + h_kt / 4.0
        ax.text((x_p5 + x_p20) / 2.0, y_txt_b, "Người vẽ", fontsize=9.0, style='italic', ha='center', va='center', zorder=8)
        ax.text((x_p20 + x_p75) / 2.0, y_txt_b, self.txt_ng_ve.get(), fontsize=9.5, fontweight='bold', ha='center', va='center', zorder=8)
        ax.text((x_p75 + x_p92) / 2.0, y_txt_b, "Người kiểm tra", fontsize=9.0, style='italic', ha='center', va='center', zorder=8)
        ax.text((x_p92 + x_p999) / 2.0, y_txt_b, self.txt_ng_kt.get(), fontsize=9.5, fontweight='bold', ha='center', va='center', zorder=8)

        return fig

    def plot_cad_style(self):
        """Vẽ đồ thị chuẩn bản vẽ kỹ thuật TCVN lên giao diện xem trước"""
        if len(self.sorted_data) == 0:
            messagebox.showwarning("Cảnh báo", "Vui lòng mở tệp số liệu TXT hoặc tệp dự án .TSH trước.")
            return

        if self.plot_win is not None and self.plot_win.winfo_exists():
            self.plot_win.destroy()
        plt.close('all')

        fig = self.create_cad_figure()
        if fig is None:
            return

        self.plot_win = tk.Toplevel(self.root)
        self.plot_win.title(f"Bản vẽ kỹ thuật: {self.txt_title.get()}")
        self.plot_win.geometry("1140x800")
        self.plot_win.configure(bg="#eef2f7")
        self.plot_win.after_idle(lambda window=self.plot_win: self.style_dialog(window))

        # Nhúng vào Canvas Tkinter
        canvas = FigureCanvasTkAgg(fig, master=self.plot_win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(canvas, self.plot_win)
        toolbar.update()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    root = tk.Tk()
    app = TSTVAdvancedApp(root)
    root.mainloop()