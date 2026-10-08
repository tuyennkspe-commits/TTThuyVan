import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import json

class FlowMasterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Mini FlowMaster v8.0 - Graphic Fix")
        self.root.geometry("1100x850")
        self.root.configure(bg="white")

        self.setup_menu()

        self.tabControl = ttk.Notebook(root)
        self.tab_irreg = ttk.Frame(self.tabControl)
        
        self.tabControl.add(self.tab_irreg, text='Sông tự nhiên (Irregular Section)')
        self.tabControl.pack(expand=1, fill="both")

        self.setup_irregular_tab()

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Mở file (Open)...", command=self.open_file)
        filemenu.add_command(label="Lưu file (Save)...", command=self.save_file)
        filemenu.add_separator()
        filemenu.add_command(label="Thoát (Exit)", command=self.root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        self.root.config(menu=menubar)

    def save_file(self):
        try:
            data = {
                "n": self.irreg_n.get(),
                "S": self.irreg_S.get(),
                "Q": self.irreg_Q.get(),
                "coords": self.text_coords.get("1.0", tk.END).strip()
            }
            filepath = filedialog.asksaveasfilename(
                defaultextension=".fm", 
                filetypes=[("FlowMaster Files", "*.fm"), ("JSON Files", "*.json")],
                title="Lưu file dự án"
            )
            if filepath:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                messagebox.showinfo("Thành công", f"Đã lưu file thành công tại:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu file: {str(e)}")

    def open_file(self):
        try:
            filepath = filedialog.askopenfilename(
                filetypes=[("FlowMaster Files", "*.fm"), ("JSON Files", "*.json"), ("All Files", "*.*")],
                title="Mở file dự án"
            )
            if filepath:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                self.irreg_n.delete(0, tk.END); self.irreg_n.insert(0, data.get("n", ""))
                self.irreg_S.delete(0, tk.END); self.irreg_S.insert(0, data.get("S", ""))
                self.irreg_Q.delete(0, tk.END); self.irreg_Q.insert(0, data.get("Q", ""))
                self.text_coords.delete("1.0", tk.END); self.text_coords.insert(tk.END, data.get("coords", ""))
                
                self.solve_irregular()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở file, định dạng không hợp lệ!\nChi tiết: {str(e)}")

    def setup_irregular_tab(self):
        top_frame = tk.Frame(self.tab_irreg, bg="white")
        top_frame.pack(fill="x", padx=10, pady=5)

        input_frame = tk.LabelFrame(top_frame, text="Thông số đầu vào (Inputs)", bg="white", font=("Arial", 10, "bold"))
        input_frame.pack(side="left", fill="y", padx=5)

        tk.Label(input_frame, text="Hệ số nhám Manning (n):", bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.irreg_n = tk.Entry(input_frame, width=15)
        self.irreg_n.insert(0, "0.056")
        self.irreg_n.grid(row=0, column=1, padx=5)

        tk.Label(input_frame, text="Độ dốc đáy (S):", bg="white").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.irreg_S = tk.Entry(input_frame, width=15)
        self.irreg_S.insert(0, "0.005")
        self.irreg_S.grid(row=1, column=1, padx=5)

        tk.Label(input_frame, text="Lưu lượng Q (m³/s):", bg="white").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.irreg_Q = tk.Entry(input_frame, width=15)
        self.irreg_Q.insert(0, "202")
        self.irreg_Q.grid(row=2, column=1, padx=5)

        tk.Label(input_frame, text="Tọa độ mặt cắt (X, Y):", bg="white").grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 0))
        
        self.text_coords = tk.Text(input_frame, width=35, height=8, font=("Courier", 10))
        self.text_coords.grid(row=4, column=0, columnspan=2, padx=5, pady=5)
        
        default_coords = "0\t899.35\n1.41\t898.75\n8.94\t894.48\n19.02\t894.15\n21.41\t895.42\n41.41\t899.04\n45.03\t899.35"
        self.text_coords.insert(tk.END, default_coords.replace("\\t", "\t").replace("\\n", "\n"))

        tk.Button(input_frame, text="Tính Toán Mực Nước", command=self.solve_irregular, bg="#0052cc", fg="white", font=("Arial", 10, "bold")).grid(row=5, column=0, columnspan=2, pady=10)

        output_frame = tk.LabelFrame(top_frame, text="Kết quả tính toán (Outputs)", bg="white", font=("Arial", 10, "bold"))
        output_frame.pack(side="right", fill="both", expand=True, padx=5)

        lbl_style = {"bg": "white", "font": ("Arial", 10), "anchor": "w"}
        val_style = {"bg": "#f0f0f0", "font": ("Arial", 10, "bold"), "width": 12, "anchor": "e", "relief": "sunken"}

        self.out_vars = {}
        params = [
            ("Flow Area (A):", "m²"), ("Wetted Perimeter (P):", "m"),
            ("Hydraulic Radius (R):", "m"), ("Top Width (T):", "m"),
            ("Normal Depth (yn):", "m"), ("Critical Depth (yc):", "m"),
            ("Critical Slope (Sc):", "m/m"), ("Velocity (v):", "m/s"),
            ("Velocity Head (hv):", "m"), ("Specific Energy (E):", "m"),
            ("Froude Number:", ""), ("Flow Type:", "")
        ]

        for i, (p_name, unit) in enumerate(params):
            row = i // 2
            col = (i % 2) * 3
            tk.Label(output_frame, text=p_name, **lbl_style).grid(row=row, column=col, sticky="w", padx=(10, 2), pady=8)
            var_lbl = tk.Label(output_frame, text="---", **val_style)
            var_lbl.grid(row=row, column=col+1, padx=2)
            tk.Label(output_frame, text=unit, bg="white", font=("Arial", 9)).grid(row=row, column=col+2, sticky="w", padx=2)
            self.out_vars[p_name] = var_lbl
            
        self.lbl_wse = tk.Label(output_frame, text="Cao độ mặt nước (WSE): --- m", bg="white", fg="blue", font=("Arial", 11, "bold"))
        self.lbl_wse.grid(row=6, column=0, columnspan=6, pady=10)

        self.graph_tabs = ttk.Notebook(self.tab_irreg)
        self.graph_tabs.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.tab_graphs = ttk.Frame(self.graph_tabs)
        self.graph_tabs.add(self.tab_graphs, text="Biểu đồ Báo cáo (WSE & Velocity vs Q)")
        self.fig_rep = plt.Figure(figsize=(10, 4), dpi=100)
        self.ax_wse = self.fig_rep.add_subplot(121)
        self.ax_v = self.fig_rep.add_subplot(122)
        self.fig_rep.tight_layout(pad=3.0)
        self.canvas_rep = FigureCanvasTkAgg(self.fig_rep, self.tab_graphs)
        self.canvas_rep.get_tk_widget().pack(fill="both", expand=True)
        
        self.tab_xs = ttk.Frame(self.graph_tabs)
        self.graph_tabs.add(self.tab_xs, text="Mặt cắt ngang (Cross Section)")
        self.fig_xs = plt.Figure(figsize=(10, 4), dpi=100)
        self.ax_xs = self.fig_xs.add_subplot(111)
        self.fig_xs.tight_layout(pad=3.0)
        self.canvas_xs = FigureCanvasTkAgg(self.fig_xs, self.tab_xs)
        self.canvas_xs.get_tk_widget().pack(fill="both", expand=True)

    def parse_coords(self):
        raw_text = self.text_coords.get("1.0", tk.END).strip()
        x_c, y_c = [], []
        for line in raw_text.split("\n"):
            line = line.strip()
            if line:
                parts = line.replace(",", " ").split()
                if len(parts) >= 2:
                    x_c.append(float(parts[0]))
                    y_c.append(float(parts[1]))
        return np.array(x_c), np.array(y_c)

    def calc_irreg_APT(self, x_coords, y_coords, WSE):
        A = 0.0; P = 0.0; T = 0.0
        for i in range(len(x_coords)-1):
            x1, y1 = x_coords[i], y_coords[i]
            x2, y2 = x_coords[i+1], y_coords[i+1]
            if y1 >= WSE and y2 >= WSE: continue
            if y1 > WSE and y2 < WSE:
                xi = x1 + (x2 - x1) * (WSE - y1) / (y2 - y1)
                xw1, yw1 = xi, WSE
                xw2, yw2 = x2, y2
            elif y1 < WSE and y2 > WSE:
                xi = x1 + (x2 - x1) * (WSE - y1) / (y2 - y1)
                xw1, yw1 = x1, y1
                xw2, yw2 = xi, WSE
            else:
                xw1, yw1 = x1, y1
                xw2, yw2 = x2, y2
            A += 0.5 * ((WSE - yw1) + (WSE - yw2)) * (xw2 - xw1)
            P += np.sqrt((xw2 - xw1)**2 + (yw2 - yw1)**2)
            T += abs(xw2 - xw1)
            
        if WSE > y_coords[0]: P += (WSE - y_coords[0])
        if WSE > y_coords[-1]: P += (WSE - y_coords[-1])
        return A, P, T

    def find_critical(self, Q, x_coords, y_coords, y_min, y_max):
        wse_low = y_min + 0.001
        wse_high = y_max + 500.0
        g = 9.81
        for _ in range(100):
            wse_mid = (wse_low + wse_high) / 2.0
            A, P, T = self.calc_irreg_APT(x_coords, y_coords, wse_mid)
            if A <= 0 or T <= 0:
                wse_low = wse_mid
                continue
            Fr_sq = (Q**2 * T) / (g * A**3)
            if Fr_sq > 1: wse_low = wse_mid
            else: wse_high = wse_mid
        wse_c = (wse_low + wse_high) / 2.0
        A_c, P_c, T_c = self.calc_irreg_APT(x_coords, y_coords, wse_c)
        return wse_c, A_c, P_c

    def solve_irregular(self):
        try:
            n = float(self.irreg_n.get())
            S = float(self.irreg_S.get())
            Q_target = float(self.irreg_Q.get())
            g = 9.81
            
            x_coords, y_coords = self.parse_coords()
            if len(x_coords) < 2: raise ValueError("Cần ít nhất 2 điểm tọa độ!")

            y_min, y_max = np.min(y_coords), np.max(y_coords)
            
            wse_low, wse_high = y_min + 0.001, y_max + 500.0
            for _ in range(100):
                wse_mid = (wse_low + wse_high) / 2.0
                A, P, T = self.calc_irreg_APT(x_coords, y_coords, wse_mid)
                Q_calc = (1/n) * A * ((A/P)**(2/3)) * np.sqrt(S) if P > 0 else 0
                if Q_calc < Q_target: wse_low = wse_mid
                else: wse_high = wse_mid
            wse_solution = (wse_low + wse_high) / 2.0
            A, P, T = self.calc_irreg_APT(x_coords, y_coords, wse_solution)

            R = A / P if P > 0 else 0
            yn = wse_solution - y_min
            v = Q_target / A if A > 0 else 0
            hv = v**2 / (2 * g)
            E = yn + hv
            
            Hydraulic_Depth = A / T if T > 0 else 0
            Fr = v / np.sqrt(g * Hydraulic_Depth) if Hydraulic_Depth > 0 else 0
            
            if abs(Fr - 1) < 0.01: flow_type = "Critical"
            elif Fr < 1: flow_type = "Subcritical"
            else: flow_type = "Supercritical"
            
            wse_c, A_c, P_c = self.find_critical(Q_target, x_coords, y_coords, y_min, y_max)
            yc = wse_c - y_min
            Sc = ((Q_target * n) / (A_c * (A_c/P_c)**(2/3)))**2 if (P_c > 0 and A_c > 0) else 0

            self.lbl_wse.config(text=f"Cao độ mặt nước (WSE): {wse_solution:.2f} m")
            self.out_vars["Flow Area (A):"].config(text=f"{A:.2f}")
            self.out_vars["Wetted Perimeter (P):"].config(text=f"{P:.2f}")
            self.out_vars["Hydraulic Radius (R):"].config(text=f"{R:.2f}")
            self.out_vars["Top Width (T):"].config(text=f"{T:.2f}")
            self.out_vars["Normal Depth (yn):"].config(text=f"{yn:.2f}")
            self.out_vars["Critical Depth (yc):"].config(text=f"{yc:.2f}")
            self.out_vars["Critical Slope (Sc):"].config(text=f"{Sc:.5f}")
            self.out_vars["Velocity (v):"].config(text=f"{v:.2f}")
            self.out_vars["Velocity Head (hv):"].config(text=f"{hv:.2f}")
            self.out_vars["Specific Energy (E):"].config(text=f"{E:.2f}")
            self.out_vars["Froude Number:"].config(text=f"{Fr:.2f}")
            self.out_vars["Flow Type:"].config(text=flow_type)

            self.ax_wse.clear()
            self.ax_v.clear()
            self.ax_xs.clear()
            
            plot_x = list(x_coords)
            plot_y = list(y_coords)
            if wse_solution > y_coords[0]: plot_x.insert(0, x_coords[0]); plot_y.insert(0, wse_solution)
            if wse_solution > y_coords[-1]: plot_x.append(x_coords[-1]); plot_y.append(wse_solution)

            self.ax_xs.plot(plot_x, plot_y, marker=".", color="black", linewidth=2, label="Đáy sông")
            self.ax_xs.axhline(wse_solution, color="blue", linestyle="-", linewidth=2, label=f"WSE ({wse_solution:.2f}m)")
            
            # SỬA LỖI HIỂN THỊ: THÊM interpolate=True
            self.ax_xs.fill_between(plot_x, plot_y, wse_solution, where=(np.array(plot_y) <= wse_solution), interpolate=True, color="cyan", alpha=0.4)
            
            self.ax_xs.set_title("Cross Section Plot", fontsize=10, fontweight="bold")
            self.ax_xs.set_xlabel("Khoảng cách (m)"); self.ax_xs.set_ylabel("Cao độ (m)")
            self.ax_xs.grid(True, linestyle=":"); self.ax_xs.legend(loc="lower right")
            
            q_vals = np.linspace(Q_target * 0.5, Q_target * 1.2, 15)
            wse_vals = []; v_vals = []
            
            for q in q_vals:
                wl, wh = y_min + 0.001, y_max + 500.0
                for _ in range(50):
                    wm = (wl + wh) / 2.0
                    A_q, P_q, _ = self.calc_irreg_APT(x_coords, y_coords, wm)
                    q_c = (1/n) * A_q * ((A_q/P_q)**(2/3)) * np.sqrt(S) if P_q > 0 else 0
                    if q_c < q: wl = wm
                    else: wh = wm
                wse_q = (wl + wh) / 2.0
                A_q, P_q, _ = self.calc_irreg_APT(x_coords, y_coords, wse_q)
                wse_vals.append(wse_q)
                v_vals.append(q / A_q if A_q > 0 else 0)
                
            self.ax_wse.plot(q_vals, wse_vals, marker="o", color="black", linestyle="-", markersize=4)
            self.ax_wse.axvline(x=Q_target, color="red", linestyle="--", alpha=0.5)
            self.ax_wse.axhline(y=wse_solution, color="blue", linestyle="--", alpha=0.5)
            self.ax_wse.set_title("Water Surface Elevation (m) vs Discharge (m³/s)", fontsize=9, fontweight="bold")
            self.ax_wse.set_xlabel("Discharge (m³/s)"); self.ax_wse.set_ylabel("Water Surface Elevation (m)")
            self.ax_wse.grid(True, linestyle=":")
            
            self.ax_v.plot(q_vals, v_vals, marker="o", color="black", linestyle="-", markersize=4)
            self.ax_v.axvline(x=Q_target, color="red", linestyle="--", alpha=0.5)
            self.ax_v.axhline(y=v, color="blue", linestyle="--", alpha=0.5)
            self.ax_v.set_title("Velocity (m/s) vs Discharge (m³/s)", fontsize=9, fontweight="bold")
            self.ax_v.set_xlabel("Discharge (m³/s)"); self.ax_v.set_ylabel("Velocity (m/s)")
            self.ax_v.grid(True, linestyle=":")

            self.fig_rep.tight_layout(pad=2.0)
            self.fig_xs.tight_layout(pad=2.0)
            self.canvas_rep.draw()
            self.canvas_xs.draw()
            
        except Exception as e:
            messagebox.showerror("Lỗi", f"Lỗi dữ liệu: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FlowMasterApp(root)
    root.mainloop()
