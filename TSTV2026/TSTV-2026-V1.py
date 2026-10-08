import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import sys
import numpy as np
from scipy.stats import norm, pearson3
from scipy.optimize import minimize
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
        self.root.title("PHẦN MỀM TÍNH VÀ VẼ TẦN SUẤT THỦY VĂN - TCVN")
        self.root.geometry("880x760")
        self.root.resizable(False, False)

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
            os._exit(0)

    def setup_ui(self):
        # 1. TIÊU ĐỀ
        hdr = tk.Frame(self.root, pady=4)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="TẦN SUẤT THUỶ VĂN", font=("Times New Roman", 18, "bold"), fg="blue").pack(side=tk.LEFT, padx=15)
        tk.Label(hdr, text="[ Phân tích thống kê & Xuất bản vẽ kỹ thuật ]", font=("Times New Roman", 10, "italic"), fg="#8B5A00").pack(side=tk.LEFT, pady=6)

        # 2. KHUNG NỘI DUNG CHÍNH
        body = tk.Frame(self.root, padx=10, pady=5)
        body.pack(fill=tk.BOTH, expand=True)

        # --- CỘT TRÁI: BẢNG SỐ LIỆU ---
        left_col = tk.Frame(body, width=330)
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        tk.Label(left_col, text="Chuỗi số liệu quan trắc x1...xn", font=("Times New Roman", 11, "italic bold"), fg="blue").pack(anchor=tk.W)

        tbl_frame = tk.Frame(left_col)
        tbl_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        cols = ("stt", "nam", "xi", "xss")
        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=14)
        self.tree.heading("stt", text="STT")
        self.tree.heading("nam", text="Năm")
        self.tree.heading("xi", text="X(i)")
        self.tree.heading("xss", text="Xss(i)")
        self.tree.column("stt", width=40, anchor=tk.CENTER)
        self.tree.column("nam", width=65, anchor=tk.CENTER)
        self.tree.column("xi", width=75, anchor=tk.E)
        self.tree.column("xss", width=75, anchor=tk.E)

        sb = ttk.Scrollbar(tbl_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Button(left_col, text="📁 Nhập số liệu từ tệp TXT . . .", font=("Arial", 9, "bold"),
                  bg="#e8e8e8", command=self.load_txt_file).pack(fill=tk.X, pady=(4, 2))

        proj_btn_frame = tk.Frame(left_col)
        proj_btn_frame.pack(fill=tk.X, pady=2)
        tk.Button(proj_btn_frame, text="📂 Mở dự án (.TSH)", font=("Arial", 8, "bold"),
                  bg="#fff3e0", fg="#b26a00", command=self.load_project).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        tk.Button(proj_btn_frame, text="💾 Lưu dự án (.TSH)", font=("Arial", 8, "bold"),
                  bg="#e8f5e9", fg="#2e7d32", command=self.save_project).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        # --- CỘT PHẢI: THAM SỐ VÀ CÁC PHƯƠNG PHÁP ---
        right_col = tk.Frame(body)
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        stat_fr = tk.LabelFrame(right_col, text=" Đặc trưng mẫu quan trắc ", font=("Arial", 9, "bold"), padx=5, pady=4)
        stat_fr.pack(fill=tk.X, pady=2)
        
        tk.Label(stat_fr, text="Xbq=").grid(row=0, column=0, padx=2)
        self.txt_xbq = tk.Entry(stat_fr, width=8, bg="#f5f5f5")
        self.txt_xbq.grid(row=0, column=1, padx=4)

        tk.Label(stat_fr, text="Cv=").grid(row=0, column=2, padx=2)
        self.txt_cv = tk.Entry(stat_fr, width=8, bg="#f5f5f5")
        self.txt_cv.grid(row=0, column=3, padx=4)

        tk.Label(stat_fr, text="Cs=").grid(row=0, column=4, padx=2)
        self.txt_cs = tk.Entry(stat_fr, width=8, bg="#f5f5f5")
        self.txt_cs.grid(row=0, column=5, padx=4)

        # Đường kinh nghiệm
        exp_fr = tk.LabelFrame(right_col, text=" Đường kinh nghiệm ", font=("Arial", 9, "bold"), fg="blue", padx=6, pady=4)
        exp_fr.pack(fill=tk.X, pady=4)
        
        row_exp = tk.Frame(exp_fr)
        row_exp.pack(fill=tk.X, pady=2)
        tk.Label(row_exp, text="Công thức:").pack(side=tk.LEFT)
        self.cbo_formula = ttk.Combobox(row_exp, width=28, state="readonly", values=[
            "Hazen : P = (m-0.25)/(n+0.5) x100%",
            "Weibull : P = m/(n+1) x100%",
            "Trung bình : P = (m-0.5)/n x100%"
        ])
        self.cbo_formula.current(0)
        self.cbo_formula.pack(side=tk.LEFT, padx=5)

        # Đường lý luận: Dạng phân phối & Phương pháp
        theo_fr = tk.LabelFrame(right_col, text=" Đường lý luận & Phương pháp tính ", font=("Arial", 9, "bold"), fg="blue", padx=6, pady=4)
        theo_fr.pack(fill=tk.X, pady=4)

        p_dist = tk.Frame(theo_fr)
        p_dist.pack(fill=tk.X, pady=2)
        tk.Label(p_dist, text="Dạng phân bố:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.dist_var = tk.StringVar(value="PEARSON III")
        ttk.Radiobutton(p_dist, text="Pearson III", variable=self.dist_var, value="PEARSON III").pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(p_dist, text="Log-Pearson III", variable=self.dist_var, value="LOG-PEARSON III").pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(p_dist, text="Gumbel", variable=self.dist_var, value="GUMBEL").pack(side=tk.LEFT, padx=8)

        self.method_var = tk.IntVar(value=1)
        tk.Radiobutton(theo_fr, text="1. Phương pháp Mô men (Tính trực tiếp từ chuỗi mẫu)", 
                       variable=self.method_var, value=1, fg="#b30000", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=2)

        tk.Radiobutton(theo_fr, text="2. Phương pháp Thích hợp (Nắn tuyến tự do theo Cs)", 
                       variable=self.method_var, value=2, fg="#b30000", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=2)

        fit_box = tk.Frame(theo_fr)
        fit_box.pack(fill=tk.X, padx=18, pady=1)
        tk.Label(fit_box, text="Xbq=").grid(row=0, column=0)
        self.ent_fit_xbq = tk.Entry(fit_box, width=7)
        self.ent_fit_xbq.grid(row=0, column=1, padx=2)
        tk.Label(fit_box, text="Cv=").grid(row=0, column=2)
        self.ent_fit_cv = tk.Entry(fit_box, width=7)
        self.ent_fit_cv.grid(row=0, column=3, padx=2)
        tk.Label(fit_box, text="Cs=").grid(row=0, column=4)
        self.ent_fit_cs = tk.Entry(fit_box, width=7)
        self.ent_fit_cs.grid(row=0, column=5, padx=2)

        tk.Radiobutton(theo_fr, text="3. Phương pháp Ba điểm (P1=5%, P2=50%, P3=95%)", 
                       variable=self.method_var, value=3, fg="#b30000", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=2)

        p3_box = tk.Frame(theo_fr)
        p3_box.pack(fill=tk.X, padx=18, pady=1)
        tk.Label(p3_box, text="X(5%)=").grid(row=0, column=0)
        self.ent_x5 = tk.Entry(p3_box, width=7)
        self.ent_x5.grid(row=0, column=1, padx=2)
        tk.Label(p3_box, text="X(50%)=").grid(row=0, column=2)
        self.ent_x50 = tk.Entry(p3_box, width=7)
        self.ent_x50.grid(row=0, column=3, padx=2)
        tk.Label(p3_box, text="X(95%)=").grid(row=0, column=4)
        self.ent_x95 = tk.Entry(p3_box, width=7)
        self.ent_x95.grid(row=0, column=5, padx=2)

        # 3. THÔNG TIN KHUNG BẢN VẼ KỸ THUẬT & TRỤC TỌA ĐỘ
        info_fr = tk.LabelFrame(self.root, text=" Khung tên bản vẽ & Cấu hình trục Y ", padx=10, pady=5)
        info_fr.pack(fill=tk.X, padx=10, pady=2)

        r_info1 = tk.Frame(info_fr)
        r_info1.pack(fill=tk.X, pady=2)
        tk.Label(r_info1, text="Tên trạm / Đồ thị:", width=15, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_title = tk.Entry(r_info1, font=("Times New Roman", 10, "bold"))
        self.txt_title.insert(0, "ĐƯỜNG TẦN SUẤT LƯỢNG MƯA 1 NGÀY LỚN NHẤT NĂM TRẠM CHŨ")
        self.txt_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        r_info2 = tk.Frame(info_fr)
        r_info2.pack(fill=tk.X, pady=2)
        tk.Label(r_info2, text="Ký hiệu trục X:", width=15, anchor=tk.W).pack(side=tk.LEFT)
        self.txt_kyhieu = tk.Entry(r_info2, width=8)
        self.txt_kyhieu.insert(0, "X")
        self.txt_kyhieu.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_info2, text="Đơn vị:").pack(side=tk.LEFT)
        self.txt_donvi = tk.Entry(r_info2, width=8)
        self.txt_donvi.insert(0, "mm")
        self.txt_donvi.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_info2, text="Người vẽ:").pack(side=tk.LEFT)
        self.txt_ng_ve = tk.Entry(r_info2, width=16)
        self.txt_ng_ve.insert(0, "Nguyễn Kim Tuyên")
        self.txt_ng_ve.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_info2, text="Người kiểm tra:").pack(side=tk.LEFT)
        self.txt_ng_kt = tk.Entry(r_info2, width=14)
        self.txt_ng_kt.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(r_info2, text="Năm:").pack(side=tk.LEFT)
        self.txt_year_draw = tk.Entry(r_info2, width=6)
        self.txt_year_draw.insert(0, "2026")
        self.txt_year_draw.pack(side=tk.LEFT)

        # HÀNG CẤU HÌNH YMIN, YMAX
        r_info3 = tk.Frame(info_fr)
        r_info3.pack(fill=tk.X, pady=2)
        tk.Label(r_info3, text="Giới hạn trục Y:", width=15, anchor=tk.W, font=("Arial", 9, "bold"), fg="#b30000").pack(side=tk.LEFT)
        
        tk.Label(r_info3, text="Y min:").pack(side=tk.LEFT)
        self.txt_ymin = tk.Entry(r_info3, width=8)
        self.txt_ymin.insert(0, "0")
        self.txt_ymin.pack(side=tk.LEFT, padx=(2, 20))

        tk.Label(r_info3, text="Y max (để trống = tự động):").pack(side=tk.LEFT)
        self.txt_ymax = tk.Entry(r_info3, width=8)
        self.txt_ymax.pack(side=tk.LEFT, padx=(2, 10))

        # 4. HÀNG NÚT HÀNH ĐỘNG
        act_fr = tk.Frame(self.root, pady=8)
        act_fr.pack(fill=tk.X, padx=10)

        tk.Button(act_fr, text="📋 BẢNG TS KINH NGHIỆM", font=("Arial", 9, "bold"),
                  bg="#6a1b9a", fg="white", padx=10, pady=5, command=self.show_emp_table_window).pack(side=tk.LEFT, padx=3)

        tk.Button(act_fr, text="📊 BẢNG TS LÝ LUẬN", font=("Arial", 9, "bold"),
                  bg="#2e7d32", fg="white", padx=10, pady=5, command=self.show_xp_table_window).pack(side=tk.LEFT, padx=3)

        tk.Button(act_fr, text="📈 VẼ ĐỒ THỊ TẦN SUẤT >>", font=("Arial", 10, "bold"),
                  bg="#0d47a1", fg="white", padx=14, pady=5, command=self.plot_cad_style).pack(side=tk.RIGHT, padx=3)

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

        m = np.arange(1, n + 1)
        p_haz = (m - 0.25) / (n + 0.5) * 100.0
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

            self.years = ps.get("years", [])
            self.raw_data = np.array(ps.get("raw_data", []))
            self.sorted_data = np.sort(self.raw_data)[::-1]
            self.xbq_calc = ps.get("xbq_calc", 0.0)
            self.cv_calc = ps.get("cv_calc", 0.0)
            self.cs_calc = ps.get("cs_calc", 0.0)

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
            formula_name = "Hazen [P = (m-0.25)/(n+0.5) * 100%]"
            p_emp = (m - 0.25) / (n + 0.5) * 100.0
        elif idx_f == 1:
            formula_name = "Weibull [P = m/(n+1) * 100%]"
            p_emp = m / (n + 1) * 100.0
        else:
            formula_name = "Trung bình [P = (m-0.5)/n * 100%]"
            p_emp = (m - 0.5) / n * 100.0
        return m, p_emp, formula_name

    def show_emp_table_window(self):
        """Hiển thị cửa sổ BẢNG KẾT QUẢ TÍNH TOÁN TẦN SUẤT KINH NGHIỆM"""
        if len(self.sorted_data) == 0:
            messagebox.showwarning("Cảnh báo", "Vui lòng mở tệp số liệu TXT hoặc tệp dự án .TSH trước.")
            return

        if self.tbl_emp_win is not None and self.tbl_emp_win.winfo_exists():
            self.tbl_emp_win.destroy()

        n = len(self.sorted_data)
        m_arr, p_emp, formula_name = self.get_empirical_probabilities()
        donvi = self.txt_donvi.get()

        self.tbl_emp_win = tk.Toplevel(self.root)
        self.tbl_emp_win.title("BẢNG KẾT QUẢ TÍNH TOÁN TẦN SUẤT KINH NGHIỆM")
        self.tbl_emp_win.geometry("720x620")

        tk.Label(self.tbl_emp_win, text="BẢNG KẾT QUẢ TÍNH TOÁN TẦN SUẤT KINH NGHIỆM", 
                 font=("Times New Roman", 13, "bold"), fg="#6a1b9a").pack(pady=(8, 2))
        tk.Label(self.tbl_emp_win, text=f"Công thức: {formula_name} | Số năm quan trắc: n = {n}", 
                 font=("Times New Roman", 10, "italic")).pack(pady=(0, 2))
        tk.Label(self.tbl_emp_win, text="💡 Mẹo: Bấm chuột trái vào tiêu đề cột hoặc nhấp chuột phải để sao chép riêng từng cột", 
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
                    menu.add_command(label=f"📋 Sao chép cột '{c_title}' (kèm tiêu đề)", 
                                     command=lambda: copy_single_emp_col(col_k, True))
                    menu.add_command(label=f"📋 Sao chép cột '{c_title}' (chỉ số liệu)", 
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

            menu.add_command(label="📋 Sao chép toàn bộ bảng", command=copy_emp_to_clipboard)
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

        tk.Button(btn_box, text="📋 Sao chép cả bảng", bg="#6a1b9a", fg="white", font=("Arial", 9, "bold"),
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

        tk.Button(cbo_box, text="📋 Sao chép cột", bg="#ede7f6", fg="#4a148c", font=("Arial", 8, "bold"),
                  command=on_copy_emp_selected_col).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_box, text="💾 Xuất file CSV", bg="#388e3c", fg="white", font=("Arial", 9, "bold"),
                  padx=8, pady=4, command=export_emp_csv).pack(side=tk.RIGHT, padx=3)

    def get_distribution_parameters(self):
        dist_name = self.dist_var.get()
        method_id = self.method_var.get()

        if method_id == 1:
            mean = self.xbq_calc
            cv = self.cv_calc
            cs = self.cs_calc
            method_desc = f"PHƯƠNG PHÁP MOMEN - {dist_name}"

        elif method_id == 2:
            try:
                mean = float(self.ent_fit_xbq.get())
                cv = float(self.ent_fit_cv.get())
                cs = float(self.ent_fit_cs.get())
                method_desc = f"PHƯƠNG PHÁP THÍCH HỢP - {dist_name}"
            except ValueError:
                messagebox.showerror("Lỗi", "Vui lòng nhập đúng giá trị Xbq, Cv, Cs.")
                return None

        else:
            try:
                x5 = float(self.ent_x5.get())
                x50 = float(self.ent_x50.get())
                x95 = float(self.ent_x95.get())
            except ValueError:
                messagebox.showerror("Lỗi", "Vui lòng nhập đủ 3 điểm X(5%), X(50%), X(95%).")
                return None

            def obj(p):
                m_t, cv_t, cs_t = p
                s_t = m_t * cv_t
                if s_t <= 0 or cv_t <= 0: return 999999
                t1 = pearson3.ppf(0.95, skew=cs_t, loc=m_t, scale=s_t)
                t2 = pearson3.ppf(0.50, skew=cs_t, loc=m_t, scale=s_t)
                t3 = pearson3.ppf(0.05, skew=cs_t, loc=m_t, scale=s_t)
                return (t1 - x5)**2 + (t2 - x50)**2 + (t3 - x95)**2

            res = minimize(obj, [x50, 0.4, 0.5], method='Nelder-Mead')
            mean, cv, cs = res.x
            method_desc = f"PHƯƠNG PHÁP 3 ĐIỂM - {dist_name}"

        return mean, cv, cs, dist_name, method_desc

    def calculate_xp(self, p_percent, mean, cv, cs, dist_name):
        q = 1.0 - np.array(p_percent) / 100.0
        
        if dist_name == "PEARSON III":
            scale = mean * cv
            skew = cs if abs(cs) > 1e-4 else 1e-4
            return pearson3.ppf(q, skew=skew, loc=mean, scale=scale)

        elif dist_name == "LOG-PEARSON III":
            y = np.log10(self.sorted_data[self.sorted_data > 0])
            y_mean = np.mean(y)
            y_std = np.std(y, ddof=1)
            y_diff = y - y_mean
            y_cs = (len(y) / ((len(y)-1)*(len(y)-2))) * np.sum(y_diff**3) / (y_std**3)
            eff_cs = cs if self.method_var.get() == 2 else y_cs
            eff_cs = eff_cs if abs(eff_cs) > 1e-4 else 1e-4
            y_p = pearson3.ppf(q, skew=eff_cs, loc=y_mean, scale=y_std)
            return 10.0**y_p

        else:
            s = mean * cv
            alpha = np.pi / (np.sqrt(6.0) * s)
            u = mean - 0.5772156649 / alpha
            return u - (1.0 / alpha) * np.log(-np.log(q))

    def get_return_period_note(self, p):
        """Tính chu kỳ lặp lại T cho các tần suất thiết kế thủy văn chuẩn"""
        if p > 50.0:
            return "-"
        if abs(p - 0.33) < 0.01:
            return "T = 300 năm"
        t = 100.0 / p
        if abs(t - round(t)) < 1e-3:
            return f"T = {int(round(t))} năm"
        elif abs(t * 10 - round(t * 10)) < 1e-3:
            return f"T = {t:.1f} năm"
        return f"T ≈ {t:.1f} năm"

    def show_xp_table_window(self):
        """Hiển thị cửa sổ BẢNG KẾT QUẢ TÍNH TOÁN TẦN SUẤT LÝ LUẬN"""
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
        self.tbl_win.title("BẢNG KẾT QUẢ TÍNH TOÁN TẦN SUẤT LÝ LUẬN")
        self.tbl_win.geometry("700x640")

        tk.Label(self.tbl_win, text="BẢNG KẾT QUẢ TÍNH TOÁN TẦN SUẤT LÝ LUẬN", 
                 font=("Times New Roman", 13, "bold"), fg="blue").pack(pady=(8, 2))
        tk.Label(self.tbl_win, text=f"X̄ = {mean:.2f} | Cv = {cv:.2f} | Cs = {cs:.2f} ({method_desc})", 
                 font=("Times New Roman", 10, "italic")).pack(pady=(0, 2))
        tk.Label(self.tbl_win, text="💡 Mẹo: Bấm chuột trái vào tiêu đề cột hoặc nhấp chuột phải để sao chép riêng từng cột", 
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
            kp_val = (val / mean) if mean != 0 else 0.0
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
                    menu.add_command(label=f"📋 Sao chép cột '{c_title}' (kèm tiêu đề)", 
                                     command=lambda: copy_single_xp_col(col_k, True))
                    menu.add_command(label=f"📋 Sao chép cột '{c_title}' (chỉ số liệu)", 
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

            menu.add_command(label="📋 Sao chép toàn bộ bảng", command=copy_to_clipboard)
            menu.tk_popup(event.x_root, event.y_root)

        tree_xp.bind("<Button-3>", popup_menu_xp)
        tree_xp.bind("<Button-2>", popup_menu_xp)

        def copy_to_clipboard():
            out = f"STT\tTan suat P(%)\tKp\tXp ({donvi})\tGhi chu\n"
            for idx, (p, val) in enumerate(zip(p_list, xp_vals), start=1):
                kp_val = (val / mean) if mean != 0 else 0.0
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
                    kp_val = (val / mean) if mean != 0 else 0.0
                    note_str = self.get_return_period_note(p)
                    f.write(f"{idx},{p:.2f}%,{kp_val:.2f},{val:.2f},{note_str}\n")
            messagebox.showinfo("Thành công", f"Đã lưu bảng ra file: {f_save}")

        btn_box = tk.Frame(self.tbl_win, pady=8)
        btn_box.pack(fill=tk.X, padx=10)

        tk.Button(btn_box, text="📋 Sao chép cả bảng", bg="#1976d2", fg="white", font=("Arial", 9, "bold"),
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

        tk.Button(cbo_box, text="📋 Sao chép cột", bg="#e3f2fd", fg="#0d47a1", font=("Arial", 8, "bold"),
                  command=on_copy_xp_selected_col).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_box, text="💾 Xuất file CSV", bg="#388e3c", fg="white", font=("Arial", 9, "bold"),
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
            step = round((y_curve_peak - y_min) / 12.8, 1)
            if step <= 0: step = 20.0
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
        x_bar_math = rf"$\overline{{\mathrm{{{sym}}}}} = {mean:.2f}$"

        ax.text(x_tbl_l + 0.06 * w_tbl, y_tbl_b + 1.62 * step, x_bar_math, fontsize=10.0, va='center', zorder=8)
        ax.text(x_tbl_l + 0.68 * w_tbl, y_tbl_b + 1.62 * step, f"N = {len(self.sorted_data)}", fontsize=10.0, va='center', zorder=8)
        ax.text(x_tbl_l + 0.06 * w_tbl, y_tbl_b + 1.18 * step, f"Cv = {cv:.2f}", fontsize=10.0, va='center', zorder=8)
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