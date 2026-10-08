import os
import re
import io
import zipfile
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd

print("=" * 65)
print("[*] ĐANG KHỞI ĐỘNG PHẦN MỀM TÍNH MỰC NƯỚC NGẬP THƯỜNG XUYÊN...")
print("=" * 65)

class HydroFloodApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tính Mực Nước Ngập Thường Xuyên N Ngày (TBNN & Năm Điển Hình)")
        self.root.geometry("900x720")
        self.root.minsize(820, 600)

        self.df_daily = None
        self.file_path = tk.StringVar()
        self.n_days = tk.IntVar(value=20)
        self.station_name = tk.StringVar(value="Tân An")
        self.chosen_year = tk.StringVar(value="2024")

        self.setup_ui()

    def setup_ui(self):
        # 1. Khung chọn File & Tên trạm
        f1 = ttk.LabelFrame(self.root, text=" 1. Nạp file số liệu thực đo ", padding=10)
        f1.pack(fill=tk.X, padx=12, pady=5)

        ttk.Label(f1, text="Tên trạm:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(f1, textvariable=self.station_name, width=15).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(f1, text="File Excel:").grid(row=0, column=2, sticky=tk.W, padx=(15, 0))
        ttk.Entry(f1, textvariable=self.file_path, width=45).grid(row=0, column=3, sticky=tk.EW, padx=5)
        ttk.Button(f1, text="Chọn file...", command=self.browse_file).grid(row=0, column=4)
        f1.columnconfigure(3, weight=1)

        # 2. Khung thiết lập thông số
        f2 = ttk.LabelFrame(self.root, text=" 2. Thiết lập thông số ngập ", padding=10)
        f2.pack(fill=tk.X, padx=12, pady=5)

        ttk.Label(f2, text="Số ngày ngập (N ngày):", font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        ttk.Spinbox(f2, from_=10, to=60, textvariable=self.n_days, width=6, font=('Segoe UI', 10, 'bold')).grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(f2, text="ngày").grid(row=0, column=2, sticky=tk.W)

        ttk.Label(f2, text="Năm điển hình khảo sát:").grid(row=0, column=3, sticky=tk.W, padx=(25, 0))
        self.cb_year = ttk.Combobox(f2, textvariable=self.chosen_year, width=8, state='readonly')
        self.cb_year.grid(row=0, column=4, sticky=tk.W, padx=5)

        btn_run = ttk.Button(f2, text="BẮT ĐẦU TÍNH TOÁN", command=self.calculate)
        btn_run.grid(row=0, column=5, padx=25)

        # 3. Khung kết quả hiển thị
        f3 = ttk.LabelFrame(self.root, text=" 3. Kết quả tính toán & Mẫu câu thuyết minh ", padding=10)
        f3.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

        self.txt_out = tk.Text(f3, wrap=tk.WORD, font=('Consolas', 10), bg='#F8F9FA')
        scroll = ttk.Scrollbar(f3, orient="vertical", command=self.txt_out.yview)
        self.txt_out.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_out.pack(fill=tk.BOTH, expand=True)

        # Nút tiện ích copy
        btn_box = ttk.Frame(self.root)
        btn_box.pack(fill=tk.X, padx=12, pady=4)
        ttk.Button(btn_box, text="Sao chép toàn bộ kết quả vào Clipboard", command=self.copy_to_clipboard).pack(side=tk.RIGHT)

        # Thanh trạng thái
        self.status = ttk.Label(self.root, text="Sẵn sàng. Hãy chọn file số liệu trạm.", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def browse_file(self):
        f = filedialog.askopenfilename(
            title="Chọn file Excel số liệu trạm",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        if f:
            self.file_path.set(f)
            fname = os.path.basename(f).lower()
            if "tanan" in fname or "tân an" in fname:
                self.station_name.set("Tân An")
            elif "benluc" in fname or "bến lức" in fname:
                self.station_name.set("Bến Lức")
            elif "godau" in fname or "gò dầu" in fname:
                self.station_name.set("Gò Dầu Hạ")
            elif "nhabe" in fname or "nhà bè" in fname:
                self.station_name.set("Nhà Bè")

            self.load_data(f)

    def load_data(self, fpath):
        try:
            self.status.config(text=f"Đang đọc: {os.path.basename(fpath)} ...")
            self.root.update_idletasks()

            # Khắc phục lỗi definedNames cũ trong file Excel KTTV
            try:
                with zipfile.ZipFile(fpath, 'r') as zin:
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, 'w') as zout:
                        for item in zin.infolist():
                            data = zin.read(item.filename)
                            if item.filename == 'xl/workbook.xml':
                                s = data.decode('utf-8', errors='ignore')
                                s = re.sub(r'<definedNames>.*?</definedNames>', '<definedNames/>', s, flags=re.DOTALL)
                                data = s.encode('utf-8')
                            zout.writestr(item, data)
                    buf.seek(0)
                    xls = pd.ExcelFile(buf)
            except Exception:
                xls = pd.ExcelFile(fpath)

            sheet = 'Hn' if 'Hn' in xls.sheet_names else xls.sheet_names[0]
            df_raw = pd.read_excel(xls, sheet_name=sheet, header=None)

            records = []
            n_rows = len(df_raw)
            r = 0
            while r < n_rows:
                txt = " ".join([str(x).strip() for x in df_raw.iloc[r].tolist() if pd.notna(x)])
                if "NĂM" in txt or "Năm" in txt:
                    yr = None
                    for c in range(df_raw.shape[1]):
                        val = str(df_raw.iat[r, c]).strip()
                        if "NĂM" in val or "Năm" in val:
                            m = re.search(r'\b(19\d\d|20\d\d)\b', val)
                            if m:
                                yr = int(m.group(1))
                            else:
                                for off in [1, 2, 3]:
                                    if c + off < df_raw.shape[1]:
                                        m2 = re.search(r'\b(19\d\d|20\d\d)\b', str(df_raw.iat[r, c+off]))
                                        if m2:
                                            yr = int(m2.group(1))
                                            break
                            break
                    if yr is not None:
                        hr = None
                        for h_idx in range(r + 1, min(r + 6, n_rows)):
                            c0 = str(df_raw.iat[h_idx, 0]).strip().lower()
                            if "ngày" in c0 or "ngay" in c0 or c0 == "1":
                                hr = h_idx
                                break
                        if hr is not None:
                            d_start = hr + 1 if "ngày" in str(df_raw.iat[hr, 0]).lower() else hr
                            for d in range(1, 32):
                                cur = d_start + d - 1
                                if cur >= n_rows:
                                    break
                                for m_col in range(1, 13):
                                    if m_col < df_raw.shape[1]:
                                        v = df_raw.iat[cur, m_col]
                                        if pd.notna(v):
                                            try:
                                                h_val = float(v)
                                                dt = pd.Timestamp(year=yr, month=m_col, day=d)
                                                records.append({'Date': dt, 'Year': yr, 'H': h_val})
                                            except (ValueError, TypeError):
                                                pass
                            r = d_start + 31
                            continue
                r += 1

            self.df_daily = pd.DataFrame(records)
            if self.df_daily.empty:
                df_s = pd.read_excel(fpath).iloc[:, [0, 1]].dropna()
                df_s.columns = ['Date', 'H']
                df_s['Date'] = pd.to_datetime(df_s['Date'])
                df_s['H'] = pd.to_numeric(df_s['H'])
                df_s['Year'] = df_s['Date'].dt.year
                self.df_daily = df_s

            all_years = sorted(self.df_daily['Year'].unique(), reverse=True)
            self.cb_year['values'] = [str(y) for y in all_years]
            if 2024 in all_years:
                self.chosen_year.set("2024")
            else:
                self.chosen_year.set(str(all_years[0]))

            self.status.config(text=f"Đã nạp thành công {len(self.df_daily):,} ngày ({all_years[-1]} - {all_years[0]}).")
            self.calculate()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file: {e}")
            self.status.config(text="Lỗi đọc file Excel!")

    def calculate(self):
        if self.df_daily is None or self.df_daily.empty:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn file số liệu trạm trước!")
            return

        tram = self.station_name.get().strip() or "Trạm KTTV"
        n = int(self.n_days.get())
        sel_year = int(self.chosen_year.get())
        ref_year = 2023  # Năm chuẩn không nhuận để quy đổi ngày trong năm

        years = sorted(self.df_daily['Year'].unique())
        
        # ----------------------------------------------------
        # 1. TÍNH TOÁN TRUNG BÌNH NHIỀU NĂM (TOÀN CHUỖI)
        # ----------------------------------------------------
        yearly_records = []
        for y in years:
            df_y = self.df_daily[self.df_daily['Year'] == y].sort_values('Date').reset_index(drop=True)
            if len(df_y) < 300:
                continue
            roll = df_y['H'].rolling(window=n).mean()
            idx = roll.idxmax()
            s_d = df_y.loc[idx - n + 1, 'Date']
            e_d = df_y.loc[idx, 'Date']

            yearly_records.append({
                'Year': y,
                'Max_N_Mean': roll.loc[idx],
                'Start_DOY': s_d.dayofyear,
                'End_DOY': e_d.dayofyear
            })
        df_yearly = pd.DataFrame(yearly_records)

        num_years = len(df_yearly)
        y_min = df_yearly['Year'].min()
        y_max = df_yearly['Year'].max()

        # Mực nước TB nhiều năm
        multi_mean_cm = df_yearly['Max_N_Mean'].mean()
        is_cm = multi_mean_cm > 10.0
        multi_mean_m = multi_mean_cm / 100.0 if is_cm else multi_mean_cm

        # Khoảng thời gian TB nhiều năm
        doy_start_mean = int(round(df_yearly['Start_DOY'].mean()))
        doy_end_mean = int(round(df_yearly['End_DOY'].mean()))
        multi_start_str = (datetime.date(ref_year, 1, 1) + datetime.timedelta(days=doy_start_mean - 1)).strftime('%d/%m')
        multi_end_str = (datetime.date(ref_year, 1, 1) + datetime.timedelta(days=doy_end_mean - 1)).strftime('%d/%m')

        # ----------------------------------------------------
        # 2. TÍNH TOÁN THEO NĂM ĐIỂN HÌNH ĐƯỢC CHỌN
        # ----------------------------------------------------
        df_sel = self.df_daily[self.df_daily['Year'] == sel_year].sort_values('Date').reset_index(drop=True)
        if len(df_sel) < 300:
            messagebox.showwarning("Cảnh báo", f"Năm {sel_year} không đủ số liệu thực đo!")
            return

        roll_sel = df_sel['H'].rolling(window=n).mean()
        idx_sel = roll_sel.idxmax()
        sel_mean_cm = roll_sel.loc[idx_sel]
        sel_mean_m = sel_mean_cm / 100.0 if is_cm else sel_mean_cm
        sel_s_date = df_sel.loc[idx_sel - n + 1, 'Date']
        sel_e_date = df_sel.loc[idx_sel, 'Date']

        # Bảng phương án loanh quanh N ngày của năm điển hình
        options_text = ""
        for w in range(max(15, n - 2), min(35, n + 6)):
            r_w = df_sel['H'].rolling(window=w).mean()
            i_w = r_w.idxmax()
            val_m = r_w.loc[i_w] / 100.0 if is_cm else r_w.loc[i_w]
            s_w = df_sel.loc[i_w - w + 1, 'Date'].strftime('%d/%m')
            e_w = df_sel.loc[i_w, 'Date'].strftime('%d/%m/%Y')
            star = f"  <-- (CHUẨN ĐÚNG {n} NGÀY)" if w == n else ""
            options_text += f"   * {w:2d} ngày: H = {val_m:.2f} m  (từ ngày {s_w} đến ngày {e_w}){star}\n"

        # ----------------------------------------------------
        # 3. TẠO VĂN BẢN BÁO CÁO HOÀN CHỈNH
        # ----------------------------------------------------
        report = f"""========================================================================================
BÁO CÁO XÁC ĐỊNH MỰC NƯỚC NGẬP THƯỜNG XUYÊN TRUNG BÌNH {n} NGÀY TẠI TRẠM {tram.upper()}
Số liệu thực đo: {num_years} năm (Từ năm {y_min} đến năm {y_max})
========================================================================================

PHƯƠNG ÁN 1: THEO TRUNG BÌNH NHIỀU NĂM (TOÀN BỘ CHUỖI QUAN TRẮC {num_years} NĂM)
(Dùng khi thẩm định yêu cầu số liệu đặc trưng dài hạn toàn chuỗi)
----------------------------------------------------------------------------------------
- Tại trạm {tram} theo thống kê số liệu thực đo trong nhiều năm ({num_years} năm từ {y_min} đến {y_max}) tại trạm, Tư vấn xác định mực nước ngập thường xuyên trung bình trên {n} ngày tại trạm H{n}ngày = {multi_mean_m:.2f}m, (thời kỳ xuất hiện trung bình hàng năm từ ngày {multi_start_str} đến ngày {multi_end_str}). Tư vấn kiến nghị lấy H{n}ngày = {multi_mean_m:.2f}m làm mực nước ngập thường xuyên tại trạm.

----------------------------------------------------------------------------------------
PHƯƠNG ÁN 2: THEO NĂM ĐIỂN HÌNH {sel_year}
(Dùng khi tính theo đợt lũ/triều dâng bất lợi thực tế gần nhất)
----------------------------------------------------------------------------------------
- Tại trạm {tram} theo thống kê số liệu thực đo trong nhiều năm tại trạm, Tư vấn xác định mực nước ngập thường xuyên trung bình trên {n} ngày tại trạm H{n}ngày = {sel_mean_m:.2f}m, (từ ngày {sel_s_date.strftime('%d/%m')} đến ngày {sel_e_date.strftime('%d/%m/%Y')}). Tư vấn kiến nghị lấy H{n}ngày = {sel_mean_m:.2f}m làm mực nước ngập thường xuyên tại trạm.

========================================================================================
TRA CỨU CÁC THỜI ĐOẠN ĐỈNH TRIỀU/LŨ LOANH QUANH {n} NGÀY TRONG NĂM {sel_year}:
========================================================================================
{options_text}
Ghi chú kỹ thuật:
- Mực nước ngập thường xuyên trung bình nhiều năm H_{n}ngay = {multi_mean_m:.2f} m ({multi_mean_cm:.2f} cm).
- Mực nước ngập đợt {n} ngày năm điển hình {sel_year} H_{n}ngay = {sel_mean_m:.2f} m ({sel_mean_cm:.2f} cm).
- Căn cứ quy chuẩn TCVN 4054:2005 & 22 TCN 211-06 khống chế cao độ đáy áo đường theo mực nước ngập >= 20 ngày.
"""
        self.txt_out.delete("1.0", tk.END)
        self.txt_out.insert(tk.END, report)
        self.status.config(text=f"Hoàn thành tính toán trạm {tram}: TBNN ({y_min}-{y_max}) = {multi_mean_m:.2f}m | Năm {sel_year} = {sel_mean_m:.2f}m.")

    def copy_to_clipboard(self):
        text = self.txt_out.get("1.0", tk.END).strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Đã sao chép", "Đã chép toàn bộ nội dung thuyết minh vào bộ nhớ đệm (Clipboard)!")

if __name__ == '__main__':
    root = tk.Tk()
    app = HydroFloodApp(root)
    root.mainloop()