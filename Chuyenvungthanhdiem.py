import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import geopandas as gpd
from shapely.geometry import Point, Polygon
import numpy as np
import fiona
import os
import zipfile
import tempfile
import shutil

# Kích hoạt hỗ trợ đọc/ghi file KML và TAB
fiona.drvsupport.supported_drivers['KML'] = 'rw'
fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'
fiona.drvsupport.supported_drivers['MapInfo File'] = 'rw'

class GridGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Phần Mềm Trích Xuất Lưới Điểm Từ Ranh Giới (Polygon)")
        self.root.geometry("620x300")
        self.root.resizable(False, False)

        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.spacing = tk.DoubleVar(value=10.0)

        self.setup_ui()

    def setup_ui(self):
        frame = ttk.Frame(self.root, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="1. Chọn file ranh giới (KMZ, SHP, KML, TAB):", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5), columnspan=3)
        ttk.Entry(frame, textvariable=self.input_file, width=60, state='readonly').grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(frame, text="Duyệt...", command=self.browse_input).grid(row=1, column=2, padx=5)

        ttk.Label(frame, text="2. Khoảng cách giữa các điểm:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(15, 5), columnspan=3)
        spacing_frame = ttk.Frame(frame)
        spacing_frame.grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Entry(spacing_frame, textvariable=self.spacing, width=15).pack(side=tk.LEFT)
        ttk.Label(spacing_frame, text=" mét (m)").pack(side=tk.LEFT, padx=5)

        ttk.Label(frame, text="3. Lưu file kết quả (CSV, SHP, KML, KMZ):", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(15, 5), columnspan=3)
        ttk.Entry(frame, textvariable=self.output_file, width=60, state='readonly').grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Button(frame, text="Lưu thành...", command=self.browse_output).grid(row=5, column=2, padx=5)

        self.btn_run = ttk.Button(frame, text="🚀 XỬ LÝ & TẠO LƯỚI ĐIỂM", command=self.process_data)
        self.btn_run.grid(row=6, column=0, columnspan=3, pady=25)

    def browse_input(self):
        file_types = [
            ("Tất cả định dạng", "*.shp;*.kml;*.kmz;*.tab;*.geojson"),
            ("Google Earth KMZ/KML", "*.kml;*.kmz"),
            ("Shapefile", "*.shp"),
            ("MapInfo TAB", "*.tab")
        ]
        filename = filedialog.askopenfilename(title="Chọn file ranh giới", filetypes=file_types)
        if filename:
            self.input_file.set(filename)

    def browse_output(self):
        file_types = [
            ("CSV Text (Để web lấy cao độ)", "*.csv"),
            ("Google Earth KMZ", "*.kmz"),
            ("Google Earth KML", "*.kml"),
            ("Shapefile (Cho phần mềm GIS)", "*.shp")
        ]
        filename = filedialog.asksaveasfilename(title="Lưu file kết quả", defaultextension=".csv", filetypes=file_types)
        if filename:
            self.output_file.set(filename)

    def process_data(self):
        in_path = self.input_file.get()
        out_path = self.output_file.get()
        space_m = self.spacing.get()

        if not in_path or not out_path:
            messagebox.showwarning("Lỗi", "Vui lòng chọn đầy đủ file!")
            return
        if space_m <= 0:
            messagebox.showwarning("Lỗi", "Khoảng cách phải > 0!")
            return

        self.btn_run.config(text="Đang xử lý... Vui lòng đợi", state=tk.DISABLED)
        self.root.update()

        try:
            # --- 1. ĐỌC FILE VECTOR (Khắc phục lỗi KMZ trên Windows) ---
            if in_path.lower().endswith('.kmz'):
                with zipfile.ZipFile(in_path, 'r') as kmz:
                    kml_names = [name for name in kmz.namelist() if name.lower().endswith('.kml')]
                    if not kml_names:
                        raise Exception("Không tìm thấy file .kml trong file .kmz này!")
                    
                    temp_dir = tempfile.mkdtemp()
                    temp_kml_path = kmz.extract(kml_names[0], temp_dir)
                    gdf = gpd.read_file(temp_kml_path)
                    shutil.rmtree(temp_dir)
            else:
                gdf = gpd.read_file(in_path)

            if gdf.crs is None or gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)

            # --- 2. KHẮC PHỤC LỖI NGƯỜI DÙNG VẼ "PATH" THAY VÌ "POLYGON" ---
            # Tự động biến đổi đường bao khép kín thành vùng (Polygon)
            def force_polygon(geom):
                if geom is None:
                    return geom
                # Nếu là LineString và có đủ điểm, biến thành Polygon
                if geom.geom_type == 'LineString' and len(geom.coords) >= 3:
                    return Polygon(geom.coords)
                elif geom.geom_type == 'MultiLineString':
                    return geom.convex_hull
                return geom

            gdf.geometry = gdf.geometry.apply(force_polygon)

            if not any(gdf.geom_type == 'Polygon') and not any(gdf.geom_type == 'MultiPolygon'):
                raise Exception("Dữ liệu của bạn là Điểm hoặc đoạn thẳng quá ngắn. Vui lòng vẽ lại Polygon bao quanh khu vực.")

            # --- 3. XỬ LÝ LƯỚI ĐIỂM ---
            centroid = gdf.geometry.unary_union.centroid
            lon, lat = centroid.x, centroid.y
            utm_zone = int((lon + 180) / 6) + 1
            epsg_utm = 32600 + utm_zone if lat >= 0 else 32700 + utm_zone
            
            gdf_metric = gdf.to_crs(epsg=epsg_utm)

            minx, miny, maxx, maxy = gdf_metric.total_bounds
            x_coords = np.arange(minx, maxx, space_m)
            y_coords = np.arange(miny, maxy, space_m)
            
            points = [Point(x, y) for x in x_coords for y in y_coords]
            grid_gdf = gpd.GeoDataFrame(geometry=points, crs=f"EPSG:{epsg_utm}")

            points_inside = gpd.sjoin(grid_gdf, gdf_metric, predicate='within')

            if points_inside.empty:
                raise Exception("Không tạo được điểm nào. Ranh giới quá nhỏ so với khoảng cách.")

            points_final_wgs84 = points_inside.to_crs(epsg=4326)[['geometry']]

            # --- 4. XUẤT FILE ---
            ext = out_path.lower()
            if ext.endswith('.csv'):
                import pandas as pd
                df = pd.DataFrame({'Longitude': points_final_wgs84.geometry.x, 'Latitude': points_final_wgs84.geometry.y})
                df.to_csv(out_path, index=False)
            elif ext.endswith('.shp'):
                points_final_wgs84.to_file(out_path)
            elif ext.endswith('.kml'):
                points_final_wgs84.to_file(out_path, driver='KML')
            elif ext.endswith('.kmz'):
                temp_kml = out_path.replace('.kmz', '_temp.kml')
                points_final_wgs84.to_file(temp_kml, driver='KML')
                with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as kmz_out:
                    kmz_out.write(temp_kml, arcname='doc.kml')
                os.remove(temp_kml)

            messagebox.showinfo("Thành công", f"Tuyệt vời! Đã tạo được {len(points_final_wgs84)} điểm!\nĐã lưu tại: {out_path}")

        except Exception as e:
            messagebox.showerror("Lỗi Xử Lý", f"Đã có lỗi xảy ra:\n{str(e)}")
        finally:
            self.btn_run.config(text="🚀 XỬ LÝ & TẠO LƯỚI ĐIỂM", state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = GridGeneratorApp(root)
    root.mainloop()