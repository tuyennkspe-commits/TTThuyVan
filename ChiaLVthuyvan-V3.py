"""Chia lưu vực DEM — bản độc lập, không cần thư mục mã nguồn phụ.
Cài thư viện: python -m pip install numpy pysheds numba rasterio pyproj geopandas shapely matplotlib customtkinter pandas openpyxl
Cao độ DEM phải có đơn vị mét; các cửa xả được tính lưu vực toàn phần độc lập.
"""
import numpy as np
if not hasattr(np, 'in1d'):
    np.in1d = np.isin

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.collections import LineCollection
from pysheds.grid import Grid
import tempfile
"""Metric D8 catchment measurements. Elevation must be supplied in metres."""
import numpy as np
from shapely.geometry import shape, LineString
from shapely.ops import unary_union
from rasterio.features import shapes
from pyproj import CRS, Transformer
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
D8={64:(-1,0),128:(-1,1),1:(0,1),2:(1,1),4:(1,0),8:(1,-1),16:(0,-1),32:(-1,-1)}

def metric_dem(source, destination):
    """Reject unknown CRS; warp non-metric/geographic/rotated grids to local UTM."""
    with rasterio.open(source) as src:
        if src.crs is None: raise ValueError('DEM thiếu hệ tọa độ; phải khai báo đúng CRS trước khi xử lý.')
        band=src.read(1,masked=True).astype(float)
        if np.any(~np.isfinite(band.compressed())):
            raise ValueError('DEM có cao độ NaN/vô cực chưa khai báo NoData.')
        crs=CRS(src.crs)
        metric=crs.is_projected and all(abs(a.unit_conversion_factor-1)<1e-9 for a in crs.axis_info[:2])
        if metric and src.transform.b==0 and src.transform.d==0 and src.transform.a>0 and src.transform.e<0:
            if np.any(np.ma.getmaskarray(band)):
                profile=dict(driver='GTiff',height=src.height,width=src.width,transform=src.transform,crs=src.crs,dtype='float64',nodata=-999999.0,count=1)
                with rasterio.open(destination,'w',**profile) as dst:dst.write(band.filled(-999999.0),1)
                return destination
            return source
        lon,lat=Transformer.from_crs(crs,4326,always_xy=True).transform((src.bounds.left+src.bounds.right)/2,(src.bounds.bottom+src.bounds.top)/2)
        if not -80<=lat<=84: raise ValueError('Ngoài miền UTM; hãy cung cấp DEM chiếu phẳng mét phù hợp.')
        target=CRS.from_epsg((32600 if lat>=0 else 32700)+min(60,max(1,int((lon+180)//6)+1)))
        transform,width,height=calculate_default_transform(src.crs,target,src.width,src.height,*src.bounds)
        profile=dict(driver='GTiff',crs=target,transform=transform,width=width,height=height,dtype='float64',nodata=-999999.0,count=1)
        source_data=src.read(1,masked=True).astype(float).filled(-999999.0)
        with rasterio.open(destination,'w',**profile) as dst:
            reproject(source_data,rasterio.band(dst,1),src_transform=src.transform,src_crs=src.crs,src_nodata=-999999.0,dst_transform=transform,dst_crs=target,dst_nodata=-999999.0,resampling=Resampling.bilinear)
    return destination

def valid_dem(dem):
    data=np.asarray(dem,dtype=float)
    valid=np.isfinite(data)
    raster_mask=getattr(dem,'mask',None)
    if raster_mask is not None: valid &= np.asarray(raster_mask,dtype=bool)
    nodata=getattr(dem,'nodata',None)
    if nodata is not None: valid &= data!=nodata
    return data,valid

def snap_outlet(x,y,transform,acc,valid,radius=2):
    c,r=~transform*(x,y);r,c=int(np.floor(r)),int(np.floor(c))
    if not 0<=r<valid.shape[0] or not 0<=c<valid.shape[1]: raise ValueError('Cửa xả nằm ngoài phạm vi DEM.')
    r0,r1=max(0,r-radius),min(valid.shape[0],r+radius+1)
    c0,c1=max(0,c-radius),min(valid.shape[1],c+radius+1)
    local=np.where(valid[r0:r1,c0:c1],np.asarray(acc)[r0:r1,c0:c1],-np.inf)
    if not np.any(np.isfinite(local)): raise ValueError('Không có ô DEM hợp lệ gần cửa xả.')
    best=np.nanmax(local); candidates=np.argwhere(local==best)
    rr,cc=min(candidates,key=lambda rc:(rc[0]+r0-r)**2+(rc[1]+c0-c)**2)
    return int(rr+r0),int(cc+c0)

def terrain_slope(data,valid,dx,dy):
    z=np.where(valid,data,np.nan)
    # Adjacent NoData never treated as an elevation; available one-sided differences at boundaries.
    def derivative(axis,spacing):
        before=np.full_like(z,np.nan);after=before.copy()
        if axis==1: before[:,1:]=z[:,:-1];after[:,:-1]=z[:,1:]
        else: before[1:,:]=z[:-1,:];after[:-1,:]=z[1:,:]
        both=np.isfinite(before)&np.isfinite(after)
        return np.where(both,(after-before)/(2*spacing),np.where(np.isfinite(after),(after-z)/spacing,np.where(np.isfinite(before),(z-before)/spacing,np.nan)))
    return np.hypot(derivative(1,dx),derivative(0,dy))*1000

def measure_basin(mask,dem,fdir,acc,outlet,transform,threshold):
    if int(threshold)!=threshold or threshold<1: raise ValueError('Ngưỡng tạo sông phải là số nguyên dương, tính theo số ô góp nước.')
    data,valid=valid_dem(dem);mask=np.asarray(mask,dtype=bool)&valid
    if not mask[outlet]: raise ValueError('Cửa xả không thuộc lưu vực hợp lệ.')
    dx,dy=abs(transform.a),abs(transform.e)
    if dx<=0 or dy<=0 or transform.b!=0 or transform.d!=0:raise ValueError('Cần lưới thẳng trục với kích thước ô dương.')
    polygons=[shape(g) for g,v in shapes(mask.astype('uint8'),mask=mask,transform=transform,connectivity=4) if v==1]
    polygon=unary_union(polygons)
    slopes=terrain_slope(data,valid,dx,dy)[mask]
    slope=float(np.nanmean(slopes)) if np.any(np.isfinite(slopes)) else np.nan
    streams=(np.asarray(acc)>=threshold)&mask
    edges={}
    for r,c in np.argwhere(streams):
        p=(int(r),int(c))
        if p==outlet:continue
        direction=D8.get(int(fdir[p]))
        if direction is None:continue
        q=(p[0]+direction[0],p[1]+direction[1])
        if 0<=q[0]<mask.shape[0] and 0<=q[1]<mask.shape[1] and mask[q] and streams[q]:
            edges[p]=(q,float(np.hypot(direction[1]*dx,direction[0]*dy)))
    distances={outlet:0.0}
    for source in edges:
        path=[];seen=set();p=source
        while p not in distances and p in edges and p not in seen:
            seen.add(p);path.append(p);p=edges[p][0]
        distance=distances.get(p,np.nan)
        for node in reversed(path):
            distance=distance+edges[node][1];distances[node]=distance
    connected={p:edge for p,edge in edges.items() if np.isfinite(distances.get(p,np.nan))}
    best=max((p for p in connected),key=lambda p:distances[p],default=outlet)
    main_nodes=[best];main_edges=set();p=best
    while p!=outlet:
        main_edges.add(p);p=connected[p][0];main_nodes.append(p)
    def xy(p):return transform*(p[1]+.5,p[0]+.5)
    main=LineString([xy(p) for p in main_nodes]) if len(main_nodes)>1 else None
    branches=[LineString([xy(p),xy(q)]) for p,(q,length) in connected.items() if p not in main_edges]
    length=distances[best] if best!=outlet else 0.0
    source_z=float(data[best]) if main is not None else np.nan
    out_z=float(data[outlet])
    # Negative source-outlet drop is retained: it indicates filled depressions/raw DEM artefacts.
    drop_slope=(source_z-out_z)/length*1000 if length>0 else np.nan
    return dict(geometry=polygon,DienTich=float(mask.sum()*dx*dy/1e6),Doc_LV_pm=slope,Z_Nguon=source_z,Z_CuaXa=out_z,Dai_SC=length/1000,Doc_SC_pm=drop_slope,Dai_SNhanh=sum(e[1] for p,e in connected.items() if p not in main_edges)/1000,main=main,branches=branches)

from numba import njit
@njit(cache=False)
def _catchment_d8(directions, valid, outlet_row, outlet_col):
    rows,cols=directions.shape
    result=np.zeros((rows,cols),dtype=np.bool_)
    stack=np.empty(rows*cols,dtype=np.int64)
    stack[0]=outlet_row*cols+outlet_col;size=1
    result[outlet_row,outlet_col]=True
    drs=(-1,-1,0,1,1,1,0,-1)
    dcs=(0,1,1,1,0,-1,-1,-1)
    incoming=(4,8,16,32,64,128,1,2)
    while size:
        size-=1;index=stack[size];r=index//cols;c=index%cols
        for k in range(8):
            nr=r+drs[k];nc=c+dcs[k]
            if 0<=nr<rows and 0<=nc<cols and valid[nr,nc] and not result[nr,nc] and directions[nr,nc]==incoming[k]:
                result[nr,nc]=True;stack[size]=nr*cols+nc;size+=1
    return result

from heapq import heappush, heappop

@njit(cache=False)
def _fill_depressions_without_generators(elevation, valid):
    """Eight-neighbour priority flood; no generator/count compilation dependency."""
    filled=elevation.copy()
    rows,cols=filled.shape
    visited=np.zeros((rows,cols),dtype=np.bool_)
    heap=[(0.0,0,0)]
    heap.pop()
    for r in range(rows):
        for c in range(cols):
            if not valid[r,c]: continue
            boundary=r==0 or c==0 or r==rows-1 or c==cols-1
            if not boundary:
                for dr in range(-1,2):
                    for dc in range(-1,2):
                        if not valid[r+dr,c+dc]: boundary=True
            if boundary:
                visited[r,c]=True
                heappush(heap,(filled[r,c],r,c))
    while len(heap)>0:
        height,r,c=heappop(heap)
        for dr in range(-1,2):
            for dc in range(-1,2):
                nr,nc=r+dr,c+dc
                if 0<=nr<rows and 0<=nc<cols and valid[nr,nc] and not visited[nr,nc]:
                    visited[nr,nc]=True
                    filled[nr,nc]=max(filled[nr,nc],height)
                    heappush(heap,(filled[nr,nc],nr,nc))
    return filled

def condition_depressions(dem):
    """Fill pits and depressions together, preserving raster metadata and NoData."""
    elevation,valid=valid_dem(dem)
    filled=dem.astype(np.float64)
    filled[:]=_fill_depressions_without_generators(elevation,valid)
    return filled

def catchment_d8(fdir,valid,outlet):
    """Reverse D8 including raster rim cells; do not silently remove boundary contributors."""
    if not valid[outlet]:raise ValueError('Cửa xả nằm trên NoData.')
    return _catchment_d8(np.asarray(fdir),np.asarray(valid,dtype=np.bool_),outlet[0],outlet[1])




try:
    import geopandas as gpd
    from shapely.geometry import shape, LineString, MultiLineString
    HAS_GPD = True
except ImportError:
    HAS_GPD = False

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class GeoCatchmentApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("GeoCatchment Pro - Phân Tích Lưu Vực & Hệ Tọa Độ (Làm rõ sông chính và tính các thông số của lưu vực)")
        self.geometry("1200x800")
        self.minsize(900, 650)

        self.grid_obj = None
        self.dem = None
        self.dem_workspace = tempfile.TemporaryDirectory(prefix="luuvuc-dem-")
        self.fdir = None
        self.acc = None
        self.extent = []
        self.shp_paths = []

        self.xmin = self.xmax = self.ymin = self.ymax = 0

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

        self.left_panel = ctk.CTkFrame(self, width=330, corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_rowconfigure(8, weight=1)

        lbl_title1 = ctk.CTkLabel(self.left_panel, text="1. DỮ LIỆU ĐẦU VÀO", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_title1.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        self.txt_dem = ctk.CTkEntry(self.left_panel, placeholder_text="File DEM (.tif)", width=220)
        self.txt_dem.grid(row=1, column=0, padx=20, pady=5, sticky="w")
        ctk.CTkButton(self.left_panel, text="Duyệt", width=55, command=self.chon_file_dem).grid(row=1, column=0, padx=20, pady=5, sticky="e")

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
        lbl_title2.grid(row=5, column=0, padx=20, pady=10, sticky="w")

        self.tools_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.tools_frame.grid(row=6, column=0, padx=20, sticky="nwe")

        self.btn_add = ctk.CTkButton(self.tools_frame, text="📍 CHẾ ĐỘ: THÊM CỬA XẢ", state="disabled", command=lambda: self.set_mode('add'))
        self.btn_add.pack(pady=5, fill="x")

        self.btn_del = ctk.CTkButton(self.tools_frame, text="✖ CHẾ ĐỘ: XÓA CỬA XẢ", state="disabled", command=lambda: self.set_mode('delete'))
        self.btn_del.pack(pady=5, fill="x")

        self.frame_thresh = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
        self.frame_thresh.pack(pady=(10, 5), fill="x")
        ctk.CTkLabel(self.frame_thresh, text="Ngưỡng sông (số ô góp nước):", font=ctk.CTkFont(size=12)).pack(side="left")
        self.txt_thresh = ctk.CTkEntry(self.frame_thresh, width=65)
        self.txt_thresh.insert(0, "500")
        self.txt_thresh.pack(side="right")
        self.txt_thresh.bind("<KeyRelease>", lambda event: self.invalidate_results())

        self.btn_calc = ctk.CTkButton(self.tools_frame, text="TÍNH LƯU VỰC TOÀN PHẦN VÀ SÔNG", fg_color="#d35400", hover_color="#e67e22", font=ctk.CTkFont(weight="bold"), height=40, state="disabled", command=self.chay_chia_luu_vuc)
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

        self.btn_save = ctk.CTkButton(self.frame_export, text="💾 LƯU SHAPEFILE KẾT QUẢ", fg_color="#27ae60", hover_color="#2ecc71", font=ctk.CTkFont(weight="bold"), height=40, state="disabled", command=self.luu_ket_qua)
        self.btn_save.pack(padx=10, pady=(0, 15), fill="x")

        self.lbl_status = ctk.CTkLabel(self.left_panel, text="💡 Sẵn sàng. Hãy chọn file DEM và nạp bản đồ.", text_color="gray", wraplength=280, justify="left")
        self.lbl_status.grid(row=8, column=0, padx=20, pady=15, sticky="sw")

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

    def chon_file_dem(self):
        p = filedialog.askopenfilename(filetypes=(("TIF files", "*.tif;*.tiff"), ("All", "*.*")))
        if p:
            self.txt_dem.delete(0, "end"); self.txt_dem.insert(0, p)
            self.invalidate_results()
            self.btn_calc.configure(state="disabled")
            self.grid_obj = self.dem = self.fdir = self.acc = None

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

            self.btn_calc.configure(state="disabled")
            self.btn_save.configure(state="disabled")
            dem_path = metric_dem(dem_path, os.path.join(self.dem_workspace.name, "dem_metric.tif"))
            self.grid_obj = Grid.from_raster(dem_path)
            self.dem = self.grid_obj.read_raster(dem_path)
            xmin, ymin, xmax, ymax = self.grid_obj.bbox
            self.cols, self.rows = self.grid_obj.shape[1], self.grid_obj.shape[0]
            self.cell_w, self.cell_h = (xmax - xmin) / self.cols, (ymax - ymin) / self.rows
            self.extent = [xmin, xmax, ymin, ymax]

            self.xmin, self.xmax, self.ymin, self.ymax = xmin, xmax, ymin, ymax

            self.update_status("Đang xử lý hố trũng bằng Priority-Flood tương thích...")
            flooded = condition_depressions(self.dem)
            self.update_status("Đang xử lý vùng địa hình bằng phẳng...")
            inflated = self.grid_obj.resolve_flats(flooded)
            self.dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
            self.update_status("Đang xác định hướng dòng chảy D8...")
            self.fdir = self.grid_obj.flowdir(inflated, dirmap=self.dirmap)
            self.update_status("Đang tính tích lũy dòng chảy...")
            self.acc = self.grid_obj.accumulation(self.fdir, dirmap=self.dirmap)

            self.ax.clear()
            self.ax.axis('on')
            acc_img = np.where(self.acc > 0, self.acc, 1)
            self.ax.imshow(np.log(acc_img), extent=self.extent, cmap='Blues', zorder=1)

            if self.shp_paths and HAS_GPD:
                colors = ['red', 'green', '#9b59b6', '#e67e22', '#1abc9c', '#f1c40f']
                for idx, path in enumerate(self.shp_paths):
                    try:
                        gdf = gpd.read_file(path)
                        if gdf.crs is None: raise ValueError('Lớp nền thiếu hệ tọa độ; không tự gán CRS.')
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
            self.update_status(f"Đã xử lý DEM trong hệ mét {self.grid_obj.crs}. Cao độ DEM phải có đơn vị mét.")
            self.set_mode('add')

        except Exception as e:
            messagebox.showerror("Lỗi nạp dữ liệu", str(e))
            self.grid_obj = self.dem = self.fdir = self.acc = None
            self.update_status("❌ Có lỗi xảy ra khi nạp bản đồ; kết quả cũ không được dùng lại.")

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

        if self.dem is None: return
        cx, cy = event.xdata, event.ydata

        if self.app_state['mode'] == 'add':
            self.invalidate_results()
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
                self.invalidate_results()
                self.app_state['points'].pop(idx_xoa)
                self.draw_points()

    def invalidate_results(self):
        self.app_state['gdf_out'] = self.app_state['gdf_streams'] = None
        self.btn_save.configure(state="disabled")

    def draw_points(self):
        if self.app_state['scatter_points']:
            try: self.app_state['scatter_points'].remove()
            except: pass
            self.app_state['scatter_points'] = None

        if self.app_state['points']:
            xs, ys = [p[0] for p in self.app_state['points']], [p[1] for p in self.app_state['points']]
            self.app_state['scatter_points'] = self.ax.scatter(xs, ys, c='red', marker='^', s=80, edgecolor='black', zorder=10)
        self.canvas.draw_idle()

    def chay_chia_luu_vuc(self):
        if not self.app_state['points']:
            messagebox.showinfo("Báo cáo", "Vui lòng chấm ít nhất 1 cửa xả!")
            return

        self.update_status("⚙️ Đang phân chia ranh giới và tính toán thống kê (diện tích, độ dốc)... Xin chờ!")
        self.update()

        try:
            if self.app_state['catchment_overlay']: self.app_state['catchment_overlay'].remove()
            for t in self.app_state['snapped_texts']: t.remove()
            for line in self.app_state['stream_plot']: line.remove()
        except: pass

        self.app_state['catchment_overlay'], self.app_state['snapped_texts'] = None, []
        self.app_state['stream_plot'], self.app_state['gdf_streams'] = [], None

        self.app_state['gdf_out'] = None
        self.btn_save.configure(state="disabled")
        try:
            if not HAS_GPD: raise ValueError("Cần cài geopandas và shapely để tính và xuất lưu vực.")
            threshold = int(self.txt_thresh.get())
            if threshold < 1: raise ValueError("Ngưỡng tạo sông phải là số nguyên dương.")
            _, valid = valid_dem(self.dem)
            transform = self.dem.affine
            combined = np.zeros(self.dem.shape, dtype=np.int32)
            records=[];snapped_coords=[];used=set()
            tat_ca_nhanh_song=[];tat_ca_song_chinh=[]
            main_basin_ids=[];branch_basin_ids=[]
            for basin_id, (x,y) in enumerate(self.app_state['points'], 1):
                outlet=snap_outlet(x,y,transform,self.acc,valid)
                if outlet in used: raise ValueError("Hai cửa xả được bắt vào cùng một ô; hãy chỉnh lại vị trí.")
                used.add(outlet)
                r,c=outlet
                snapped_coords.append(transform*(c+.5,r+.5))
                catch=catchment_d8(self.fdir,valid,outlet)
                mask=(np.asarray(catch)!=0)&valid
                # Independent full catchments. Overlay only is coloured with the latest ID.
                metrics=measure_basin(mask,self.dem,self.fdir,self.acc,outlet,transform,threshold)
                main=metrics.pop('main');branches=metrics.pop('branches')
                if main is not None:
                    tat_ca_song_chinh.append(main);main_basin_ids.append(basin_id)
                tat_ca_nhanh_song.extend(branches)
                branch_basin_ids.extend([basin_id]*len(branches))
                records.append(dict(ID_LuuVuc=basin_id,**metrics))
                combined[mask]=basin_id
            self.app_state['gdf_out']=gpd.GeoDataFrame(records,crs=self.grid_obj.crs)
        except Exception as exc:
            self.update_status("Không thể tính lưu vực: " + str(exc))
            messagebox.showerror("Lỗi tính lưu vực",str(exc))
            return

        # Vẽ sông suối (Phân biệt Sông chính và Sông nhánh)
        if tat_ca_nhanh_song or tat_ca_song_chinh:
            # 1. Vẽ sông nhánh: Nét mảnh 1.0, màu xanh da trời (#3498db)
            if tat_ca_nhanh_song:
                lines_nhanh = []
                for geom in tat_ca_nhanh_song:
                    if geom.geom_type == 'LineString':
                        lines_nhanh.append(np.array(geom.coords))
                    elif geom.geom_type == 'MultiLineString':
                        for part in geom.geoms:
                            lines_nhanh.append(np.array(part.coords))

                lc_nhanh = LineCollection(lines_nhanh, colors='#3498db', linewidths=1.0, zorder=4)
                self.ax.add_collection(lc_nhanh)
                self.app_state['stream_plot'].append(lc_nhanh)

            # 2. Vẽ sông chính: Nét đậm 2.8, màu xanh Navy đậm (#000080)
            if tat_ca_song_chinh:
                lines_chinh = []
                for geom in tat_ca_song_chinh:
                    if geom.geom_type == 'LineString':
                        lines_chinh.append(np.array(geom.coords))
                    elif geom.geom_type == 'MultiLineString':
                        for part in geom.geoms:
                            lines_chinh.append(np.array(part.coords))

                lc_chinh = LineCollection(lines_chinh, colors='#000080', linewidths=2.8, zorder=5)
                self.ax.add_collection(lc_chinh)
                self.app_state['stream_plot'].append(lc_chinh)

            ds_geom = []
            ds_loai = []
            for g in tat_ca_song_chinh:
                ds_geom.append(g)
                ds_loai.append("Song_Chinh")
            for g in tat_ca_nhanh_song:
                ds_geom.append(g)
                ds_loai.append("Song_Nhanh")

            self.app_state['gdf_streams'] = gpd.GeoDataFrame({
                'ID_LuuVuc': main_basin_ids + branch_basin_ids,
                'Loai_Song': ds_loai,
                'geometry': ds_geom
            }, crs=self.grid_obj.crs)

        plot_data = np.where(combined > 0, combined, np.nan)
        self.app_state['catchment_overlay'] = self.ax.imshow(plot_data, extent=self.extent, cmap='tab10', alpha=0.5, zorder=3)

        for idx, (sx, sy) in enumerate(snapped_coords):
            t = self.ax.text(sx, sy, f" LV_{idx+1}", color='black', fontsize=10, fontweight='bold',
                             bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=2), zorder=11)
            self.app_state['snapped_texts'].append(t)

        self.draw_points()
        self.btn_save.configure(state="normal")
        self.update_status(f"✅ Đã phân chia và thống kê xong {len(self.app_state['points'])} lưu vực!")

        if (self.app_state['gdf_out']['Doc_SC_pm'] < 0).any():
            messagebox.showwarning("Kiểm tra cao độ DEM", "Có cao độ đầu sông thấp hơn cửa xả trên DEM gốc. Kiểm tra hố trũng, công trình chắn dòng và việc làm đầy DEM; không coi độ dốc âm là giá trị thiết kế.")
        self.hien_thi_bang_thong_ke()

    def hien_thi_bang_thong_ke(self):
        if self.app_state['gdf_out'] is None: return

        df = self.app_state['gdf_out'].drop(columns='geometry')

        top = ctk.CTkToplevel(self)
        top.title("Kết quả Thống kê Lưu vực")
        top.geometry("1000x430")
        top.attributes("-topmost", True)

        lbl = ctk.CTkLabel(top, text="BẢNG THỐNG KÊ THÔNG SỐ ĐỊA HÌNH CÁC LƯU VỰC", font=ctk.CTkFont(size=14, weight="bold"))
        lbl.pack(pady=10)

        frame_tb = ctk.CTkFrame(top)
        frame_tb.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        columns = ("ID", "Diện tích (km²)", "Độ dốc địa hình (‰)", "Cao độ đầu sông (m)", "Cao độ cửa xả (m)", "Sông chính (km)", "Độ dốc Sông (‰)", "Sông nhánh (km)")
        tree = ttk.Treeview(frame_tb, columns=columns, show="headings", height=8, selectmode="extended")

        for col in columns:
            tree.heading(col, text=col)
            width = 80 if col == "ID" else 115
            tree.column(col, anchor="center", width=width)

        for _, row in df.iterrows():
            tree.insert("", tk.END, values=(
                f"LV_{int(row['ID_LuuVuc'])}",
                row['DienTich'],
                row['Doc_LV_pm'],
                row['Z_Nguon'],
                row['Z_CuaXa'],
                row['Dai_SC'],
                row['Doc_SC_pm'],
                row['Dai_SNhanh']
            ))

        tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(frame_tb, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # --- CÁC HÀM XỬ LÝ COPY & XUẤT EXCEL ---
        def copy_to_clipboard(selected_only=False):
            """Sao chép dữ liệu ra Clipboard theo định dạng Tab-separated để dán thẳng vào Excel"""
            lines = ["\t".join(columns)]

            items = tree.selection() if selected_only else tree.get_children()
            if not items:
                items = tree.get_children()

            for item in items:
                vals = tree.item(item)['values']
                lines.append("\t".join(str(v) for v in vals))

            clipboard_text = "\n".join(lines)
            top.clipboard_clear()
            top.clipboard_append(clipboard_text)
            top.update()

            so_dong = len(items)
            messagebox.showinfo(
                "Đã sao chép!",
                f"Đã copy {so_dong} dòng thông số vào bộ nhớ tạm.\n\n👉 Bạn hãy mở Excel và nhấn Ctrl + V để dán."
            )

        def copy_shortcut(event=None):
            """Hỗ trợ phím tắt Ctrl + C khi bôi đen các dòng trên bảng"""
            copy_to_clipboard(selected_only=bool(tree.selection()))

        tree.bind("<Control-c>", copy_shortcut)
        tree.bind("<Control-C>", copy_shortcut)

        def export_excel():
            """Xuất trực tiếp ra file Excel (.xlsx hoặc .csv)"""
            file_path = filedialog.asksaveasfilename(
                title="Lưu kết quả ra Excel",
                defaultextension=".xlsx",
                filetypes=[("Excel File", "*.xlsx"), ("CSV UTF-8", "*.csv"), ("All Files", "*.*")],
                initialfile="ThongSo_LuuVuc.xlsx"
            )
            if not file_path:
                return

            try:
                df_export = df.copy()
                df_export['ID_LuuVuc'] = df_export['ID_LuuVuc'].apply(lambda x: f"LV_{int(x)}")
                df_export.columns = columns

                if file_path.endswith('.csv'):
                    df_export.to_csv(file_path, index=False, encoding='utf-8-sig')
                else:
                    try:
                        df_export.to_excel(file_path, index=False)
                    except Exception:
                        csv_path = os.path.splitext(file_path)[0] + ".csv"
                        df_export.to_csv(csv_path, index=False, encoding='utf-8-sig')
                        file_path = csv_path

                messagebox.showinfo("Thành công", f"Đã xuất file dữ liệu thành công:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Lỗi xuất file", f"Không thể lưu file:\n{e}")

        # --- THANH CÔNG CỤ NÚT BẤM ---
        frame_btn = ctk.CTkFrame(top, fg_color="transparent")
        frame_btn.pack(fill="x", padx=15, pady=(0, 5))

        btn_copy = ctk.CTkButton(
            frame_btn,
            text="📋 Sao chép bảng (Dán vào Excel)",
            fg_color="#2980b9",
            hover_color="#3498db",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: copy_to_clipboard(selected_only=False)
        )
        btn_copy.pack(side="left", padx=(0, 10))

        btn_export = ctk.CTkButton(
            frame_btn,
            text="📊 Xuất ra file Excel (.xlsx)",
            fg_color="#27ae60",
            hover_color="#2ecc71",
            font=ctk.CTkFont(weight="bold"),
            command=export_excel
        )
        btn_export.pack(side="left")

        ctk.CTkLabel(
            top,
            text="*Mẹo: Bạn có thể chọn 1 hoặc nhiều dòng trong bảng rồi bấm Ctrl + C để copy riêng các dòng đó.",
            font=ctk.CTkFont(size=11, slant="italic")
        ).pack(pady=(0, 10))

    def clear_all(self):
        self.app_state['points'], self.app_state['gdf_out'], self.app_state['gdf_streams'] = [], None, None
        self.btn_save.configure(state="disabled")

        try:
            if self.app_state['catchment_overlay']: self.app_state['catchment_overlay'].remove()
            for t in self.app_state['snapped_texts']: t.remove()
            for line in self.app_state['stream_plot']: line.remove()
        except: pass

        self.app_state['catchment_overlay'], self.app_state['snapped_texts'], self.app_state['stream_plot'] = None, [], []

        self.draw_points()
        self.update_status("🧹 Đã làm sạch bản đồ.")

    def luu_ket_qua(self):
        if self.app_state['gdf_out'] is None: return

        selected_crs = self.cmb_crs.get()
        if self.app_state['gdf_out'].crs is None:
            messagebox.showerror("Thiếu hệ tọa độ", "Không tự gán WGS84 cho dữ liệu chưa biết CRS.")
            return
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

                if gdf_luuvuc_save.crs is None: raise ValueError("Thiếu CRS lưu vực")
                gdf_luuvuc_save = gdf_luuvuc_save.to_crs(epsg=target_epsg)

                if gdf_song_save is not None:
                    if gdf_song_save.crs is None: raise ValueError("Thiếu CRS mạng sông")
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

                messagebox.showinfo("Thành công", f"Đã xuất dữ liệu thành công với Hệ tọa độ bạn chọn!\n(Các thông số diện tích, độ dốc đã được lưu vào thuộc tính Shapefile)\n\n{msg}")
                self.update_status("💾 Đã lưu thành công 2 bộ Shapefile!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi lưu file:\n{e}")

if __name__ == "__main__":
    app = GeoCatchmentApp()
    app.mainloop()
