# --- ĐOẠN VÁ LỖI NẰM Ở ĐẦU TIÊN ---
import numpy as np
if not hasattr(np, 'in1d'):
    np.in1d = np.isin  

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.collections import LineCollection
from pysheds.grid import Grid
import warnings

warnings.filterwarnings('ignore')

try:
    import geopandas as gpd
    from shapely.geometry import shape
    HAS_GPD = True
except ImportError:
    HAS_GPD = False

# Cấu hình Giao diện CustomTkinter
ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("blue")  

class GeoCatchmentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("GeoCatchment Pro - Phân Tích Lưu Vực & Hệ Tọa Độ")
        self.geometry("1200x800")
        self.minsize(900, 650)
        
        # Biến trạng thái dữ liệu không gian
        self.grid_obj = None
        self.dem = None
        self.fdir = None
        self.acc = None
        self.extent = []
        self.shp_paths = [] # Danh sách lưu đường dẫn các file bản đồ nền
        
        # Biến quản lý trạng thái bản đồ
        self.app_state = {
            'points': [],               
            'scatter_points': None,     
            'catchment_overlay': None,  
            'gdf_out': None,            
            'snapped_texts': [],        
            'gdf_streams': None,        
            'stream_plot': [],          
            'mode': 'add'               
        }
        
        self.setup_ui()
        
    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # ==================== KHUNG TRÁI: ĐIỀU KHIỂN ====================
        self.left_panel = ctk.CTkFrame(self, width=330, corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_rowconfigure(8, weight=1)
        
        lbl_title1 = ctk.CTkLabel(self.left_panel, text="1. DỮ LIỆU ĐẦU VÀO", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_title1.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        self.txt_dem = ctk.CTkEntry(self.left_panel, placeholder_text="File DEM (.tif)", width=220)
        self.txt_dem.grid(row=1, column=0, padx=20, pady=5, sticky="w")
        ctk.CTkButton(self.left_panel, text="Duyệt", width=55, command=self.chon_file_dem).grid(row=1, column=0, padx=20, pady=5, sticky="e")
        
        # Khung quản lý Nhiều bản đồ nền
        self.frame_nen = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.frame_nen.grid(row=2, column=0, padx=20, pady=5, sticky="we")
        
        self.btn_chon_nen = ctk.CTkButton(self.frame_nen, text="➕ Thêm lớp nền", width=120, command=self.chon_file_nen)
        self.btn_chon_nen.pack(side="left")
        
        self.btn_xoa_nen = ctk.CTkButton(self.frame_nen, text="🗑 Xóa nền", width=100, fg_color="#e74c3c", hover_color="#c0392b", command=self.xoa_file_nen)
        self.btn_xoa_nen.pack(side="right")
        
        self.txt_list_nen = ctk.CTkTextbox(self.left_panel, height=55, width=280)
        self.txt_list_nen.grid(row=3, column=0, padx=20, pady=(0, 5), sticky="we")
        self.txt_list_nen.insert("1.0", "Chưa có bản đồ nền nào...")
        self.txt_list_nen.configure(state="disabled")
        
        self.btn_load = ctk.CTkButton(self.left_panel, text="🔄 NẠP VÀ XỬ LÝ BẢN ĐỒ", height=35, fg_color="#2980b9", hover_color="#3498db", font=ctk.CTkFont(weight="bold"), command=self.load_data)
        self.btn_load.grid(row=4, column=0, padx=20, pady=(15, 20), sticky="we")
        
        lbl_title2 = ctk.CTkLabel(self.left_panel, text="2. CÔNG CỤ TƯƠNG TÁC", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_title2.grid(row=5, column=0, padx=20, pady=(10, 10), sticky="w")
        
        self.tools_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.tools_frame.grid(row=6, column=0, padx=20, sticky="nwe")
        
        self.btn_add = ctk.CTkButton(self.tools_frame, text="📍 CHẾ ĐỘ: THÊM CỬA XẢ", state="disabled", command=lambda: self.set_mode('add'))
        self.btn_add.pack(pady=5, fill="x")
        
        self.btn_del = ctk.CTkButton(self.tools_frame, text="✖️ CHẾ ĐỘ: XÓA CỬA XẢ", state="disabled", command=lambda: self.set_mode('delete'))
        self.btn_del.pack(pady=5, fill="x")
        
        self.frame_thresh = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
        self.frame_thresh.pack(pady=(10, 5), fill="x")
        ctk.CTkLabel(self.frame_thresh, text="Ngưỡng tạo sông (pixel):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.txt_thresh = ctk.CTkEntry(self.frame_thresh, width=65)
        self.txt_thresh.insert(0, "500") 
        self.txt_thresh.pack(side="right")
        
        self.btn_calc = ctk.CTkButton(self.tools_frame, text="⚙️ TÍNH TOÁN LƯU VỰC & SÔNG", fg_color="#d35400", hover_color="#e67e22", font=ctk.CTkFont(weight="bold"), height=40, state="disabled", command=self.chay_chia_luu_vuc)
        self.btn_calc.pack(pady=(15, 5), fill="x")
        
        self.btn_clear = ctk.CTkButton(self.tools_frame, text="🗑️ Làm sạch bản đồ", fg_color="#7f8c8d", hover_color="#95a5a6", state="disabled", command=self.clear_all)
        self.btn_clear.pack(pady=5, fill="x")
        
        self.frame_export = ctk.CTkFrame(self.left_panel, corner_radius=8, fg_color="#ecf0f1")
        self.frame_export.grid(row=7, column=0, padx=20, pady=(20, 5), sticky="nwe")
        
        ctk.CTkLabel(self.frame_export, text="3. XUẤT DỮ LIỆU", font=ctk.CTkFont(size=14, weight="bold"), text_color="#2c3e50").pack(anchor="w", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(self.frame_export, text="Hệ tọa độ (CRS):", font=ctk.CTkFont(size=12), text_color="#2c3e50").pack(anchor="w", padx=10)
        self.crs_options = [
            "Giữ nguyên như DEM gốc",
            "EPSG:4326 (WGS 84 - Cầu)",
            "EPSG:32648 (UTM Zone 48N)",
            "EPSG:3405 (VN-2000 Toàn quốc)"
        ]
        self.cmb_crs = ctk.CTkComboBox(self.frame_export, values=self.crs_options, width=270, fg_color="white", text_color="black")
        self.cmb_crs.pack(padx=10, pady=5)
        ctk.CTkLabel(self.frame_export, text="*Bạn có thể gõ mã trực tiếp (VD: 3408)", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray").pack(anchor="w", padx=10, pady=(0, 10))
        
        self.btn_save = ctk.CTkButton(self.frame_export, text="💾 LƯU SHAPEFILE KẾT QUẢ", fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(weight="bold"), height=40, state="disabled", command=self.luu_ket_qua)
        self.btn_save.pack(padx=10, pady=(0, 15), fill="x")
        
        self.lbl_status = ctk.CTkLabel(self.left_panel, text="💡 Sẵn sàng. Hãy chọn file DEM và nạp bản đồ.", text_color="gray", wraplength=280, justify="left")
        self.lbl_status.grid(row=8, column=0, padx=20, pady=15, sticky="sw")
        
        # ==================== KHUNG PHẢI: BẢN ĐỒ ====================
        self.right_panel = ctk.CTkFrame(self, corner_radius=0, fg_color="white")
        self.right_panel.grid(row=0, column=1, sticky="nsew")
        
        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.fig.patch.set_facecolor('#ffffff')
        self.fig.subplots_adjust(left=0.05, right=0.98, top=0.95, bottom=0.05)
        self.ax.axis('off')
        self.ax.text(0.5, 0.5, "Khu vực hiển thị Bản đồ", ha='center', va='center', color='gray', fontsize=14)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.right_panel)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.toolbar_frame = ctk.CTkFrame(self.right_panel, corner_radius=0, height=40)
        self.toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.toolbar_frame)
        self.toolbar.update()
        
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)

    # =============== CÁC HÀM XỬ LÝ CHÍNH ===============
    def chon_file_dem(self):
        p = filedialog.askopenfilename(filetypes=(("TIF files", "*.tif;*.tiff"), ("All", "*.*")))
        if p: self.txt_dem.delete(0, "end"); self.txt_dem.insert(0, p)

    def chon_file_nen(self):
        paths = filedialog.askopenfilenames(title="Chọn các lớp bản đồ nền", filetypes=(("Shapefiles", "*.shp"), ("All", "*.*")))
        if paths:
            for p in paths:
                if p not in self.shp_paths:
                    self.shp_paths.append(p)
            self.cap_nhat_hien_thi_nen()
            
    def xoa_file_nen(self):
        self.shp_paths = []
        self.cap_nhat_hien_thi_nen()
        
    def cap_nhat_hien_thi_nen(self):
        self.txt_list_nen.configure(state="normal")
        self.txt_list_nen.delete("1.0", "end")
        if not self.shp_paths:
            self.txt_list_nen.insert("1.0", "Chưa có bản đồ nền nào...")
        else:
            for i, p in enumerate(self.shp_paths):
                ten_file = os.path.basename(p)
                self.txt_list_nen.insert("end", f"{i+1}. {ten_file}\n")
        self.txt_list_nen.configure(state="disabled")

    def update_status(self, msg):
        self.lbl_status.configure(text=msg)
        self.update()

    def set_mode(self, mode):
        self.app_state['mode'] = mode
        if mode == 'add':
            self.btn_add.configure(fg_color="#3498db")  
            self.btn_del.configure(fg_color="transparent", border_width=1, border_color="gray") 
            self.update_status("👉 Đang ở chế độ THÊM: Chấm chuột trái lên bản đồ để thêm cửa xả.")
        else:
            self.btn_add.configure(fg_color="transparent", border_width=1, border_color="gray")
            self.btn_del.configure(fg_color="#e74c3c")
            self.update_status("👉 Đang ở chế độ XÓA: Click sát vào điểm đã chấm để xóa nó đi.")

    def load_data(self):
        dem_path = self.txt_dem.get()
        if not dem_path:
            messagebox.showwarning("Cảnh báo", "Bạn chưa chọn file DEM!")
            return
            
        try:
            self.update_status("⏳ Đang đọc và xử lý DEM... Xin chờ!")
            
            self.grid_obj = Grid.from_raster(dem_path)
            self.dem = self.grid_obj.read_raster(dem_path)
            xmin, ymin, xmax, ymax = self.grid_obj.bbox
            self.cols, self.rows = self.grid_obj.shape[1], self.grid_obj.shape[0]
            self.cell_w, self.cell_h = (xmax - xmin) / self.cols, (ymax - ymin) / self.rows
            self.extent = [xmin, xmax, ymin, ymax]
            self.xmin, self.ymax = xmin, ymax
            
            flooded = self.grid_obj.fill_depressions(self.dem)
            inflated = self.grid_obj.resolve_flats(flooded)
            self.dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
            self.fdir = self.grid_obj.flowdir(inflated, dirmap=self.dirmap)
            self.acc = self.grid_obj.accumulation(self.fdir, dirmap=self.dirmap)
            
            self.ax.clear()
            self.ax.axis('on')
            acc_img = np.where(self.acc > 0, self.acc, 1)
            self.ax.imshow(np.log(acc_img), extent=self.extent, cmap='Blues', zorder=1)
            
            # Khối hiển thị Nhiều lớp SHP
            if self.shp_paths and HAS_GPD:
                colors = ['red', 'green', '#9b59b6', '#e67e22', '#1abc9c', '#f1c40f'] # Bảng màu phân biệt các lớp
                for idx, path in enumerate(self.shp_paths):
                    try:
                        gdf = gpd.read_file(path)
                        if self.grid_obj.crs and gdf.crs and gdf.crs != self.grid_obj.crs:
                            gdf = gdf.to_crs(self.grid_obj.crs)
                        color = colors[idx % len(colors)]
                        gdf.plot(ax=self.ax, facecolor='none', edgecolor=color, linewidth=1, zorder=2)
                    except Exception as e:
                        print(f"Lỗi tải lớp {path}: {e}")
                
            self.canvas.draw()
            
            self.btn_add.configure(state="normal")
            self.btn_del.configure(state="normal")
            self.btn_calc.configure(state="normal")
            self.btn_clear.configure(state="normal")
            self.clear_all()
            self.set_mode('add')
            
        except Exception as e:
            messagebox.showerror("Lỗi nạp dữ liệu", str(e))
            self.update_status("❌ Có lỗi xảy ra khi nạp bản đồ.")

    def on_scroll(self, event):
        if event.inaxes != self.ax: return 
        cur_xlim, cur_ylim = self.ax.get_xlim(), self.ax.get_ylim()
        if event.xdata is None or event.ydata is None: return
        
        base_scale = 1.2
        scale = 1/base_scale if event.button == 'up' else base_scale if event.button == 'down' else 1
        new_w, new_h = (cur_xlim[1]-cur_xlim[0])*scale, (cur_ylim[1]-cur_ylim[0])*scale
        
        rx, ry = (cur_xlim[1]-event.xdata)/(cur_xlim[1]-cur_xlim[0]), (cur_ylim[1]-event.ydata)/(cur_ylim[1]-cur_ylim[0])
        self.ax.set_xlim([event.xdata - new_w*(1-rx), event.xdata + new_w*rx])
        self.ax.set_ylim([event.ydata - new_h*(1-ry), event.ydata + new_h*ry])
        self.canvas.draw_idle()

    def on_click(self, event):
        if self.toolbar.mode != '' or event.inaxes != self.ax or event.button != 1: 
            return
            
        cx, cy = event.xdata, event.ydata
        
        if self.app_state['mode'] == 'add':
            self.app_state['points'].append((cx, cy))
            self.draw_points()
            
        elif self.app_state['mode'] == 'delete':
            if not self.app_state['points']: return
            kc_min, idx_xoa = float('inf'), -1
            for i, (px, py) in enumerate(self.app_state['points']):
                kc = (px - cx)**2 + (py - cy)**2
                if kc < kc_min: kc_min, idx_xoa = kc, i
                    
            nguong = ((self.ax.get_xlim()[1] - self.ax.get_xlim()[0]) * 0.02) ** 2
            if kc_min < nguong and idx_xoa != -1:
                self.app_state['points'].pop(idx_xoa)
                self.draw_points()

    def draw_points(self):
        if self.app_state['scatter_points']:
            try: 
                self.app_state['scatter_points'].remove()
            except: 
                pass # Bỏ qua lỗi nếu đối tượng đã bị ax.clear() xóa trước đó
            self.app_state['scatter_points'] = None
            
        if self.app_state['points']:
            xs, ys = [p[0] for p in self.app_state['points']], [p[1] for p in self.app_state['points']]
            self.app_state['scatter_points'] = self.ax.scatter(xs, ys, c='red', marker='^', s=80, edgecolor='black', zorder=10)
        self.canvas.draw_idle()

    def chay_chia_luu_vuc(self):
        if not self.app_state['points']:
            messagebox.showinfo("Báo cáo", "Vui lòng chấm ít nhất 1 cửa xả!")
            return
            
        self.update_status("⚙️ Đang tính toán phân chia ranh giới và dòng chảy...")
        
        try:
            if self.app_state['catchment_overlay']: self.app_state['catchment_overlay'].remove()
            for t in self.app_state['snapped_texts']: t.remove()
            for line in self.app_state['stream_plot']: line.remove()
        except: 
            pass # Tránh lỗi "cannot remove artist"
            
        self.app_state['catchment_overlay'], self.app_state['snapped_texts'] = None, []
        self.app_state['stream_plot'], self.app_state['gdf_streams'] = [], None
        
        combined = self.dem.astype(np.int32)
        combined.nodata = 0
        try: combined.mask = False
        except: pass
        combined[:] = 0
        
        snapped_coords = []
        for i, (xr, yr) in enumerate(self.app_state['points']):
            col = max(0, min(self.cols - 1, int((xr - self.xmin) / self.cell_w)))
            row = max(0, min(self.rows - 1, int((self.ymax - yr) / self.cell_h)))
            
            r_min, r_max = max(0, row-2), min(self.rows, row+2)
            c_min, c_max = max(0, col-2), min(self.cols, col+2)
            window = self.acc[r_min:r_max, c_min:c_max]
            max_idx = np.unravel_index(np.argmax(window), window.shape)
            
            snap_row, snap_col = r_min + max_idx[0], c_min + max_idx[1]
            sx = self.xmin + snap_col * self.cell_w + (self.cell_w / 2)
            sy = self.ymax - snap_row * self.cell_h - (self.cell_h / 2)
            snapped_coords.append((sx, sy))
            
            catch = self.grid_obj.catchment(x=snap_col, y=snap_row, fdir=self.fdir, dirmap=self.dirmap, xytype='index')
            combined[catch != 0] = i + 1 
            
        if not np.any(combined > 0):
            self.update_status("⚠️ Lỗi: Không bắt được dòng chảy ở các điểm đã chọn.")
            return
            
        shapes = self.grid_obj.polygonize(combined)
        polygons, basin_ids = [], []
        for geom, val in shapes:
            if val > 0:
                polygons.append(shape(geom))
                basin_ids.append(int(val))
        
        self.app_state['gdf_out'] = gpd.GeoDataFrame({'ID_LuuVuc': basin_ids, 'geometry': polygons}, crs=self.grid_obj.crs)
        
        try: thresh_val = int(self.txt_thresh.get())
        except: thresh_val = 500
            
        stream_mask = (self.acc > thresh_val) & (combined > 0)
        if np.any(stream_mask):
            branches = self.grid_obj.extract_river_network(self.fdir, stream_mask, dirmap=self.dirmap)
            if branches['features']:
                self.app_state['gdf_streams'] = gpd.GeoDataFrame.from_features(branches)
                self.app_state['gdf_streams'].crs = self.grid_obj.crs
                
                lines = []
                for geom in self.app_state['gdf_streams'].geometry:
                    if geom.geom_type == 'LineString': lines.append(np.array(geom.coords))
                    elif geom.geom_type == 'MultiLineString':
                        for part in geom.geoms: lines.append(np.array(part.coords))
                
                lc = LineCollection(lines, colors='#00008B', linewidths=1.5, zorder=4)
                self.ax.add_collection(lc)
                self.app_state['stream_plot'].append(lc)
        
        plot_data = np.where(combined > 0, combined, np.nan)
        self.app_state['catchment_overlay'] = self.ax.imshow(plot_data, extent=self.extent, cmap='tab10', alpha=0.5, zorder=3)
        
        for idx, (sx, sy) in enumerate(snapped_coords):
            t = self.ax.text(sx, sy, f" LV_{idx+1}", color='black', fontsize=10, fontweight='bold', 
                             bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=2), zorder=11)
            self.app_state['snapped_texts'].append(t)
            
        self.draw_points()
        self.btn_save.configure(state="normal")
        self.update_status(f"✅ Đã phân chia {len(self.app_state['points'])} lưu vực và trích xuất sông thành công!")

    def clear_all(self):
        self.app_state['points'], self.app_state['gdf_out'], self.app_state['gdf_streams'] = [], None, None
        self.btn_save.configure(state="disabled")
        
        try:
            if self.app_state['catchment_overlay']: self.app_state['catchment_overlay'].remove()
            for t in self.app_state['snapped_texts']: t.remove()
            for line in self.app_state['stream_plot']: line.remove()
        except: 
            pass # Tránh lỗi khi đối tượng đã bị xóa bởi hàm ax.clear()
            
        self.app_state['catchment_overlay'], self.app_state['snapped_texts'], self.app_state['stream_plot'] = None, [], []
        
        self.draw_points()
        self.update_status("🧹 Đã làm sạch bản đồ.")

    def luu_ket_qua(self):
        if self.app_state['gdf_out'] is None: return
        
        selected_crs = self.cmb_crs.get()
        target_epsg = None
        
        if "Giữ nguyên" not in selected_crs:
            match = re.search(r'(?:EPSG:)?(\d+)', selected_crs.upper())
            if match:
                target_epsg = int(match.group(1))
            else:
                messagebox.showerror("Lỗi nhận diện CRS", "Không nhận diện được mã số EPSG.\nHãy nhập dạng số hoặc chữ (VD: 3405 hoặc EPSG:3405).")
                return
        
        gdf_luuvuc_save = self.app_state['gdf_out'].copy()
        gdf_song_save = self.app_state['gdf_streams'].copy() if self.app_state['gdf_streams'] is not None else None
        
        if target_epsg is not None:
            try:
                self.update_status(f"⏳ Đang chuyển đổi sang hệ tọa độ EPSG:{target_epsg}...")
                self.update()
                gdf_luuvuc_save = gdf_luuvuc_save.to_crs(epsg=target_epsg)
                if gdf_song_save is not None:
                    gdf_song_save = gdf_song_save.to_crs(epsg=target_epsg)
            except Exception as e:
                messagebox.showerror("Lỗi chuyển hệ tọa độ", f"Mã EPSG không hợp lệ hoặc thiếu dữ liệu tham chiếu trong máy:\n{e}")
                self.update_status("⚠️ Lỗi chuyển đổi tọa độ.")
                return
        
        out_file = filedialog.asksaveasfilename(
            title="Lưu file Ranh Giới & Sông Suối", defaultextension=".shp",
            filetypes=[("Shapefile", "*.shp"), ("GeoJSON", "*.geojson")], initialfile="KetQua.shp"
        )
        if out_file: 
            try:
                base, ext = os.path.splitext(out_file)
                file_luuvuc = f"{base}_LuuVuc{ext}"
                file_song = f"{base}_SongSuoi{ext}"
                
                if ext.lower() == '.shp':
                    gdf_luuvuc_save.to_file(file_luuvuc, encoding='utf-8')
                    if gdf_song_save is not None:
                        gdf_song_save.to_file(file_song, encoding='utf-8')
                else:
                    gdf_luuvuc_save.to_file(file_luuvuc, driver='GeoJSON', encoding='utf-8')
                    if gdf_song_save is not None:
                        gdf_song_save.to_file(file_song, driver='GeoJSON', encoding='utf-8')
                        
                msg = f"- Lưu vực: {os.path.basename(file_luuvuc)}"
                if gdf_song_save is not None:
                    msg += f"\n- Sông suối: {os.path.basename(file_song)}"
                    
                messagebox.showinfo("Thành công", f"Đã xuất dữ liệu thành công với Hệ tọa độ bạn chọn!\n\n{msg}")
                self.update_status("💾 Đã lưu thành công 2 bộ Shapefile!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi lưu file:\n{e}")

if __name__ == "__main__":
    app = GeoCatchmentApp()
    app.mainloop()