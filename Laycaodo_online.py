import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import requests
import time
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import fiona
import zipfile
import tempfile
import os
import shutil

fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

class ElevationAppAlos:
    def __init__(self, root):
        self.root = root
        self.root.title("Phần Mềm Lấy Cao Độ (Hỗ Trợ Vệ Tinh ALOS 12.5m)")
        self.root.geometry("680x480")
        self.root.resizable(False, False)

        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.num_threads = tk.IntVar(value=5)
        self.dataset_choice = tk.StringVar(value="alos") # Mặc định chọn ALOS
        self.is_running = False

        self.setup_ui()

    def setup_ui(self):
        frame = ttk.Frame(self.root, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # 1. Nguồn dữ liệu vệ tinh
        ttk.Label(frame, text="1. Chọn Nguồn Vệ Tinh Độ Phân Giải Cao:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5), columnspan=3)
        
        radio_frame = ttk.Frame(frame)
        radio_frame.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 15))
        
        ttk.Radiobutton(radio_frame, text="ALOS PALSAR (Nhật Bản - Siêu nét 12.5m)", variable=self.dataset_choice, value="alos").pack(anchor="w")
        ttk.Radiobutton(radio_frame, text="Copernicus DEM (Châu Âu - Chuẩn xác 30m)", variable=self.dataset_choice, value="copernicus30").pack(anchor="w")
        ttk.Radiobutton(radio_frame, text="SRTM (NASA - Dự phòng 30m)", variable=self.dataset_choice, value="srtm30m").pack(anchor="w")

        # 2. Đầu vào
        ttk.Label(frame, text="2. Chọn file tọa độ (CSV, TXT, SHP, KML, KMZ):", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Entry(frame, textvariable=self.input_file, width=70, state='readonly').grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Button(frame, text="Duyệt...", command=self.browse_input).grid(row=3, column=2, padx=5)

        # 3. Đầu ra
        ttk.Label(frame, text="3. Lưu file kết quả:", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(15, 5), columnspan=3)
        ttk.Entry(frame, textvariable=self.output_file, width=70, state='readonly').grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Button(frame, text="Lưu thành...", command=self.browse_output).grid(row=5, column=2, padx=5)

        # 4. Tốc độ
        ttk.Label(frame, text="4. Số luồng xử lý (Tốc độ):", font=("Arial", 10, "bold")).grid(row=6, column=0, sticky="w", pady=(15, 5), columnspan=3)
        thread_frame = ttk.Frame(frame)
        thread_frame.grid(row=7, column=0, columnspan=3, sticky="w")
        ttk.Entry(thread_frame, textvariable=self.num_threads, width=10).pack(side=tk.LEFT)
        ttk.Label(thread_frame, text=" (Khuyến nghị 5 - 8 luồng để không bị máy chủ chặn mạng)").pack(side=tk.LEFT, padx=5)

        # 5. Trạng thái
        self.lbl_status = ttk.Label(frame, text="Sẵn sàng.", foreground="blue")
        self.lbl_status.grid(row=8, column=0, columnspan=3, sticky="w", pady=(15, 5))
        
        self.progress = ttk.Progressbar(frame, orient=tk.HORIZONTAL, length=630, mode='determinate')
        self.progress.grid(row=9, column=0, columnspan=3, pady=(0, 15))

        # 6. Nút bấm
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=10, column=0, columnspan=3)

        self.btn_run = ttk.Button(btn_frame, text="🚀 TRÍCH XUẤT SIÊU TỐC", command=self.start_processing)
        self.btn_run.pack(side=tk.LEFT, padx=10)

        self.btn_stop = ttk.Button(btn_frame, text="⏹ DỪNG LẠI", command=self.stop_processing, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=10)

    def browse_input(self):
        filename = filedialog.askopenfilename(title="Chọn file", filetypes=[("All supported", "*.csv;*.txt;*.shp;*.kml;*.kmz")])
        if filename: self.input_file.set(filename)

    def browse_output(self):
        filename = filedialog.asksaveasfilename(title="Lưu file", defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("TXT", "*.txt"), ("SHP", "*.shp"), ("KML", "*.kml")])
        if filename: self.output_file.set(filename)

    def start_processing(self):
        if not self.input_file.get() or not self.output_file.get():
            messagebox.showwarning("Lỗi", "Vui lòng chọn đủ file đầu vào và đầu ra!")
            return
        
        self.is_running = True
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress['value'] = 0
        
        threading.Thread(target=self.process_logic).start()

    def stop_processing(self):
        self.is_running = False
        self.update_status("Đang yêu cầu hệ thống dừng lại...", "red")

    def fetch_chunk(self, chunk_id, locations_str, total_points_in_chunk, dataset):
        """Hàm con được gọi bởi các luồng (Thread) để lấy dữ liệu"""
        if not self.is_running: return chunk_id, [-9999.0] * total_points_in_chunk
        
        # Ở ĐÂY SỬ DỤNG BỘ DỮ LIỆU VỆ TINH MÀ NGƯỜI DÙNG CHỌN
        url = f"https://api.opentopodata.org/v1/{dataset}?locations={locations_str}"
        try:
            res = requests.get(url, timeout=20)
            if res.status_code == 200:
                data = res.json()
                return chunk_id, [r.get('elevation', -9999.0) if r.get('elevation') is not None else -9999.0 for r in data['results']]
        except Exception:
            pass # Bỏ qua lỗi mạng
        
        return chunk_id, [-9999.0] * total_points_in_chunk

    def process_logic(self):
        in_path = self.input_file.get()
        out_path = self.output_file.get()
        threads_count = self.num_threads.get()
        dataset_name = self.dataset_choice.get() # Lấy tên bộ dữ liệu đang chọn
        
        try:
            self.update_status(f"Đang phân tích file để lấy từ vệ tinh {dataset_name.upper()}...")
            ext = in_path.lower()
            df = pd.DataFrame()
            gdf_original = None

            if ext.endswith('.csv'): df = pd.read_csv(in_path)
            elif ext.endswith('.txt'): df = pd.read_csv(in_path, sep=None, engine='python')
            else:
                if ext.endswith('.kmz'):
                    with zipfile.ZipFile(in_path, 'r') as kmz:
                        kml = [n for n in kmz.namelist() if n.lower().endswith('.kml')][0]
                        tdir = tempfile.mkdtemp()
                        tpath = kmz.extract(kml, tdir)
                        gdf_original = gpd.read_file(tpath)
                        shutil.rmtree(tdir)
                else: gdf_original = gpd.read_file(in_path)
                
                if gdf_original.crs is None or gdf_original.crs.to_epsg() != 4326:
                    gdf_original = gdf_original.to_crs(epsg=4326)
                df['Longitude'] = gdf_original.geometry.x
                df['Latitude'] = gdf_original.geometry.y

            col_names = [c.lower().strip() for c in df.columns]
            df.columns = col_names
            lat_col = next((c for c in ['latitude', 'lat', 'y'] if c in col_names), None)
            lon_col = next((c for c in ['longitude', 'lon', 'long', 'x'] if c in col_names), None)

            if not lat_col or not lon_col: raise Exception("Không tìm thấy cột tọa độ.")
            
            total_points = len(df)
            chunk_size = 100
            total_chunks = math.ceil(total_points / chunk_size)
            
            self.update_status(f"Đã lên lịch {total_chunks} lô cho {total_points} điểm...")

            tasks = []
            for i in range(total_chunks):
                chunk = df.iloc[i * chunk_size : (i + 1) * chunk_size]
                locs = "|".join([f"{r[lat_col]},{r[lon_col]}" for _, r in chunk.iterrows()])
                tasks.append((i, locs, len(chunk)))

            results = {}
            completed = 0
            
            self.update_status(f"Bắt đầu đẩy {threads_count} luồng song song lên máy chủ...")
            
            with ThreadPoolExecutor(max_workers=threads_count) as executor:
                # Truyền tham số dataset vào hàm fetch_chunk
                future_to_chunk = {executor.submit(self.fetch_chunk, t[0], t[1], t[2], dataset_name): t for t in tasks}
                
                for future in as_completed(future_to_chunk):
                    if not self.is_running:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                        
                    chunk_id, elevs = future.result()
                    results[chunk_id] = elevs
                    
                    completed += 1
                    percent = (completed / total_chunks) * 100
                    self.progress['value'] = percent
                    self.update_status(f"Tiến độ ({dataset_name.upper()}): {completed}/{total_chunks} lô ({percent:.1f}%)")

            if not self.is_running:
                self.update_status("Đã hủy quá trình.", "red")
                return

            self.update_status("Đang gom dữ liệu và xuất file...")
            
            final_elevations = []
            for i in range(total_chunks):
                final_elevations.extend(results[i])
                
            df['Elevation'] = final_elevations

            ext_out = out_path.lower()
            if ext_out.endswith('.csv'): df.to_csv(out_path, index=False)
            elif ext_out.endswith('.txt'): df.to_csv(out_path, index=False, sep='\t')
            elif ext_out.endswith('.shp') or ext_out.endswith('.kml'):
                if gdf_original is not None:
                    gdf_out = gdf_original.copy()
                    gdf_out['Elevation'] = final_elevations
                else:
                    geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
                    gdf_out = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
                
                if ext_out.endswith('.shp'):
                    gdf_out.columns = [c[:10] if c != 'geometry' else c for c in gdf_out.columns]
                    gdf_out.to_file(out_path)
                else:
                    gdf_out = gdf_out.select_dtypes(exclude=['datetime64', 'timedelta64'])
                    gdf_out.to_file(out_path, driver='KML')

            self.update_status("HOÀN THÀNH!", "green")
            messagebox.showinfo("Xong", f"Trích xuất thành công {total_points} điểm bằng vệ tinh {dataset_name.upper()}!")

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Lỗi", str(e)))
            self.update_status("Lỗi hệ thống.", "red")
        finally:
            self.root.after(0, self.reset_ui)

    def update_status(self, msg, color="blue"):
        self.root.after(0, lambda: self.lbl_status.config(text=msg, foreground=color))

    def reset_ui(self):
        self.is_running = False
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ElevationAppAlos(root)
    root.mainloop()