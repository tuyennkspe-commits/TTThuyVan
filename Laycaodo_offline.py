import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import rasterio
import fiona
import zipfile
import tempfile
import shutil
import os
import threading

# Bật các driver (trình điều khiển) để đọc/ghi nhiều loại định dạng bản đồ
fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'
fiona.drvsupport.supported_drivers['MapInfo File'] = 'rw'
fiona.drvsupport.supported_drivers['GeoJSON'] = 'rw'
fiona.drvsupport.supported_drivers['GPKG'] = 'rw'

class ElevationOfflineAppPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Phần Mềm Trích Xuất Cao Độ OFFLINE (Hỗ trợ Đa Định Dạng)")
        self.root.geometry("700x420")
        self.root.resizable(False, False)

        self.input_points = tk.StringVar()
        self.input_dem = tk.StringVar()
        self.output_file = tk.StringVar()

        self.setup_ui()

    def setup_ui(self):
        frame = ttk.Frame(self.root, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # 1. File DEM
        ttk.Label(frame, text="1. Chọn file bản đồ cao độ DEM (Định dạng .tif):", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Entry(frame, textvariable=self.input_dem, width=72, state='readonly').grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(frame, text="Duyệt...", command=self.browse_dem).grid(row=1, column=2, padx=5)
        ttk.Label(frame, text="(Ví dụ: File ALOS 12.5m, SRTM, Copernicus DEM...)", foreground="gray").grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 15))

        # 2. File Tọa độ
        ttk.Label(frame, text="2. Chọn file lưới tọa độ (Excel, CSV, KML, SHP, TAB...):", font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Entry(frame, textvariable=self.input_points, width=72, state='readonly').grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Button(frame, text="Duyệt...", command=self.browse_points).grid(row=4, column=2, padx=5)
        ttk.Label(frame, text="(File Bảng tính cần có cột 'Latitude' và 'Longitude' hoặc 'X', 'Y')", foreground="gray").grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 15))

        # 3. File Đầu ra
        ttk.Label(frame, text="3. Chọn nơi lưu file kết quả (Có thêm cột Elevation Z):", font=("Arial", 10, "bold")).grid(row=6, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Entry(frame, textvariable=self.output_file, width=72, state='readonly').grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Button(frame, text="Lưu thành...", command=self.browse_output).grid(row=7, column=2, padx=5)

        # Trạng thái
        self.lbl_status = ttk.Label(frame, text="Trạng thái: Sẵn sàng.", foreground="blue", font=("Arial", 9))
        self.lbl_status.grid(row=8, column=0, columnspan=3, sticky="w", pady=(15, 5))

        # Nút thực thi
        self.btn_run = ttk.Button(frame, text="⚡ XỬ LÝ SIÊU TỐC ĐA ĐỊNH DẠNG ⚡", command=self.start_processing)
        self.btn_run.grid(row=9, column=0, columnspan=3, pady=10)

    def browse_dem(self):
        filename = filedialog.askopenfilename(title="Chọn file DEM", filetypes=[("TIFF Image", "*.tif;*.tiff")])
        if filename: self.input_dem.set(filename)

    def browse_points(self):
        file_types = [
            ("Tất cả định dạng hỗ trợ", "*.csv;*.txt;*.xlsx;*.shp;*.kml;*.kmz;*.tab;*.geojson;*.gpkg"),
            ("Bảng tính (Excel/CSV/TXT)", "*.xlsx;*.csv;*.txt"),
            ("Google Earth (KML/KMZ)", "*.kml;*.kmz"),
            ("GIS Vector (SHP/TAB/GeoJSON/GPKG)", "*.shp;*.tab;*.geojson;*.gpkg")
        ]
        filename = filedialog.askopenfilename(title="Chọn file chứa tọa độ", filetypes=file_types)
        if filename: self.input_points.set(filename)

    def browse_output(self):
        file_types = [
            ("Excel Spreadsheet", "*.xlsx"),
            ("CSV (Dùng cho phần mềm vẽ Contour)", "*.csv"),
            ("Google Earth KMZ", "*.kmz"),
            ("Google Earth KML", "*.kml"),
            ("Shapefile (ArcGIS/QGIS)", "*.shp"),
            ("MapInfo TAB", "*.tab"),
            ("GeoJSON", "*.geojson"),
            ("GeoPackage", "*.gpkg"),
            ("Text TXT", "*.txt")
        ]
        filename = filedialog.asksaveasfilename(title="Lưu file kết quả", defaultextension=".csv", filetypes=file_types)
        if filename: self.output_file.set(filename)

    def update_status(self, message, color="blue"):
        self.root.after(0, lambda: self.lbl_status.config(text=f"Trạng thái: {message}", foreground=color))

    def start_processing(self):
        dem_path = self.input_dem.get()
        pts_path = self.input_points.get()
        out_path = self.output_file.get()

        if not dem_path or not pts_path or not out_path:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn đầy đủ cả 3 đường dẫn!")
            return

        self.btn_run.config(text="Đang xử lý... Vui lòng đợi", state=tk.DISABLED)
        self.update_status("Bắt đầu đọc dữ liệu...", "orange")

        threading.Thread(target=self.process_offline, args=(dem_path, pts_path, out_path)).start()

    def process_offline(self, dem_path, pts_path, out_path):
        try:
            # ==========================================
            # 1. ĐỌC DỮ LIỆU ĐẦU VÀO ĐA ĐỊNH DẠNG
            # ==========================================
            self.update_status("Đang phân tích định dạng file đầu vào...", "orange")
            ext = pts_path.lower()
            df = pd.DataFrame()
            gdf_original = None

            if ext.endswith('.csv'): 
                df = pd.read_csv(pts_path)
            elif ext.endswith('.txt'): 
                df = pd.read_csv(pts_path, sep=None, engine='python')
            elif ext.endswith('.xlsx'):
                try:
                    df = pd.read_excel(pts_path)
                except ImportError:
                    raise Exception("Chưa cài thư viện 'openpyxl'. Mở CMD gõ: pip install openpyxl")
            else:
                # Xử lý các định dạng Không gian (Spatial / GIS)
                if ext.endswith('.kmz'):
                    with zipfile.ZipFile(pts_path, 'r') as kmz:
                        kml = [n for n in kmz.namelist() if n.lower().endswith('.kml')][0]
                        tdir = tempfile.mkdtemp()
                        tpath = kmz.extract(kml, tdir)
                        gdf_original = gpd.read_file(tpath)
                        shutil.rmtree(tdir)
                else:
                    gdf_original = gpd.read_file(pts_path)
                
                # Ép về hệ tọa độ WGS84 (Kinh tuyến, Vĩ tuyến) để khớp với DEM vệ tinh
                if gdf_original.crs is None or gdf_original.crs.to_epsg() != 4326:
                    gdf_original = gdf_original.to_crs(epsg=4326)
                
                if not all(gdf_original.geometry.geom_type == 'Point'):
                    raise Exception("File bản đồ chứa đoạn thẳng/vùng. File phải chứa các Điểm (Point)!")

                df['Longitude'] = gdf_original.geometry.x
                df['Latitude'] = gdf_original.geometry.y

            # Nhận diện cột tọa độ cho Excel/CSV
            col_names = [str(c).lower().strip() for c in df.columns]
            df.columns = df.columns # Giữ nguyên tên gốc để xuất ra cho đẹp
            
            lat_col = next((df.columns[i] for i, c in enumerate(col_names) if c in ['latitude', 'lat', 'y', 'vi_do']), None)
            lon_col = next((df.columns[i] for i, c in enumerate(col_names) if c in ['longitude', 'lon', 'long', 'x', 'kinh_do']), None)

            if not lat_col or not lon_col: 
                raise Exception("Không tìm thấy cột tọa độ. Bảng tính cần có cột tên là 'Latitude' và 'Longitude' (hoặc X, Y).")

            coords = [(row[lon_col], row[lat_col]) for _, row in df.iterrows()]
            total_points = len(coords)
            self.update_status(f"Đã nạp {total_points} điểm. Đang trích xuất cao độ từ ảnh DEM...", "orange")

            # ==========================================
            # 2. XỬ LÝ LẤY CAO ĐỘ TỪ FILE DEM
            # ==========================================
            elevations = []
            with rasterio.open(dem_path) as src:
                for val in src.sample(coords):
                    elev = val[0]
                    # Loại bỏ giá trị ngoài vùng ảnh
                    if elev < -500 or elev > 9000:
                        elevations.append(-9999.0)
                    else:
                        elevations.append(round(float(elev), 3))

            self.update_status("Trích xuất xong. Đang lưu sang định dạng bạn chọn...", "orange")

            # ==========================================
            # 3. GHI RA FILE THEO NHIỀU ĐỊNH DẠNG
            # ==========================================
            df['Elevation'] = elevations
            
            ext_out = out_path.lower()

            # Các định dạng Bảng tính (Bỏ qua geometry)
            if ext_out.endswith('.csv'): 
                df.to_csv(out_path, index=False)
            elif ext_out.endswith('.txt'): 
                df.to_csv(out_path, index=False, sep='\t')
            elif ext_out.endswith('.xlsx'):
                df.to_excel(out_path, index=False)
            
            # Các định dạng GIS/Bản đồ
            else:
                if gdf_original is not None:
                    # Giữ nguyên toàn bộ thuộc tính cũ (tên đường, loại đất, v.v...)
                    gdf_out = gdf_original.copy()
                    gdf_out['Elevation'] = elevations
                else:
                    # Tạo mới bản đồ từ bảng tính Excel/CSV
                    geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
                    gdf_out = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

                # Sửa đổi dữ liệu để phù hợp với từng định dạng
                if ext_out.endswith('.shp'):
                    # Shapefile không nhận tên cột > 10 ký tự
                    gdf_out.columns = [str(c)[:10] if c != 'geometry' else c for c in gdf_out.columns]
                    # Bỏ các cột DateTime vì Shapefile rất hay lỗi
                    gdf_out = gdf_out.select_dtypes(exclude=['datetime64', 'timedelta64'])
                    gdf_out.to_file(out_path)

                elif ext_out.endswith('.kml'):
                    gdf_out = gdf_out.select_dtypes(exclude=['datetime64', 'timedelta64'])
                    gdf_out.to_file(out_path, driver='KML')

                elif ext_out.endswith('.kmz'):
                    gdf_out = gdf_out.select_dtypes(exclude=['datetime64', 'timedelta64'])
                    temp_kml = out_path.replace('.kmz', '_temp.kml')
                    gdf_out.to_file(temp_kml, driver='KML')
                    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as kmz_out:
                        kmz_out.write(temp_kml, arcname='doc.kml')
                    os.remove(temp_kml)

                elif ext_out.endswith('.tab'):
                    gdf_out.to_file(out_path, driver='MapInfo File')

                elif ext_out.endswith('.geojson'):
                    gdf_out.to_file(out_path, driver='GeoJSON')
                
                elif ext_out.endswith('.gpkg'):
                    gdf_out.to_file(out_path, driver='GPKG')

            self.update_status(f"HOÀN THÀNH! Đã lưu {total_points} điểm.", "green")
            self.root.after(0, lambda: messagebox.showinfo("Tuyệt vời", f"Quá trình lấy cao độ và chuyển đổi định dạng thành công!\nĐã xử lý: {total_points} điểm.\nFile đã lưu tại: {out_path}"))

        except Exception as e:
            self.update_status("Đã xảy ra lỗi hệ thống.", "red")
            self.root.after(0, lambda: messagebox.showerror("Lỗi", f"Chi tiết lỗi:\n{str(e)}"))
        
        finally:
            self.root.after(0, lambda: self.btn_run.config(text="⚡ XỬ LÝ SIÊU TỐC ĐA ĐỊNH DẠNG ⚡", state=tk.NORMAL))

if __name__ == "__main__":
    root = tk.Tk()
    app = ElevationOfflineAppPro(root)
    root.mainloop()