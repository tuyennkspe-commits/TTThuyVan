"""TopoContour Digitizer Pro — sửa lõi số hóa 2026-10.

Cài: python -m pip install customtkinter pillow opencv-python numpy scipy
     scikit-image shapely pyproj pyshp ezdxf
Chạy: python TopoContourDigitizer_Pro.py

Ảnh gốc không bị sửa. Tọa độ pixel tính tại tâm pixel. Tách tự động chỉ tạo
ứng viên, không suy đoán cao độ. Đọc Hướng dẫn trong giao diện trước khi xuất.
"""
import os
import math
import threading
import queue
import tempfile
import json
import copy
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
try:
    import customtkinter as ctk
    from PIL import Image, ImageTk
    import cv2
    import numpy as np
    from skimage.morphology import skeletonize
    from skimage.graph import route_through_array
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree
    from scipy import ndimage
    from pyproj import CRS
    import ezdxf
except ImportError as exc:
    instructions=(f"Thiếu hoặc lỗi thư viện: {exc}\n\nMở Terminal trong thư mục phần mềm rồi chạy:\n"
                  "python -m pip install customtkinter pillow opencv-python numpy scipy "
                  "scikit-image shapely pyproj pyshp ezdxf")
    try:
        root=tk.Tk();root.withdraw();messagebox.showerror('Thư viện cần cài',instructions);root.destroy()
    except Exception:print(instructions)
    raise SystemExit(1)

# Cảnh báo ảnh rất lớn thay vì vô hiệu hóa mọi giới hạn giải nén.
Image.MAX_IMAGE_PIXELS = 120_000_000

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
ctk.ThemeManager.theme['CTkFont']['family']='Segoe UI' if os.name=='nt' else 'DejaVu Sans'


def finite_number(value):
    result = float(str(value).strip().replace(",", "."))
    if not math.isfinite(result):
        raise ValueError("Giá trị phải là số hữu hạn.")
    return result


def lab_colors(bgr):
    return cv2.cvtColor(np.asarray(bgr, dtype=np.float32) / 255., cv2.COLOR_BGR2LAB)


def contour_mask(bgr, params):
    """Conservative HSV gate + foreground Lab examples; no blur that bleeds ink."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    lo, hi = params["h_min"], params["h_max"]
    hue = ((h >= lo) & (h <= hi)) if lo <= hi else ((h >= lo) | (h <= hi))
    # V max alone does NOT remove black lettering. Black has low V; neutral ink low S.
    mask = hue & (s >= max(18, params["s_min"])) & (v >= params["v_min"]) & (v <= params["v_max"])
    samples = params.get("positive", [])
    rejects = params.get("negative", [])
    lab = lab_colors(bgr)
    foreground_distance = np.full(bgr.shape[:2], np.inf, np.float32)
    weights = np.array([.35, 1., 1.], dtype=np.float32)
    if samples:
        examples = lab_colors(np.array(samples, dtype=np.uint8).reshape(1,-1,3))[0]
        for color in examples:
            distance = np.linalg.norm((lab-color)*weights, axis=2)
            foreground_distance = np.minimum(foreground_distance, distance)
        mask &= foreground_distance <= params["tolerance"]
    if rejects:
        examples = lab_colors(np.array(rejects,dtype=np.uint8).reshape(1,-1,3))[0]
        for color in examples:
            distance = np.linalg.norm((lab-color)*weights, axis=2)
            mask &= ~((distance < params["tolerance"]) & (distance < foreground_distance))
    if params.get("contrast", 0) > 0:
        local_background = cv2.GaussianBlur(lab[:,:,0], (0,0), 6)
        mask &= local_background-lab[:,:,0] >= params["contrast"]
    # Disabled by default. Closing can join neighboring contours; never perform it silently.
    radius = params.get("close_radius", 0)
    if radius:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1,2*radius+1))
        mask = cv2.morphologyEx(mask.astype(np.uint8),cv2.MORPH_CLOSE,kernel).astype(bool)
        # Keep black/neutral crossings blocked even after closing.
        mask &= (v >= params["v_min"]) & (s >= max(18, params["s_min"]))
    return mask


_DIRECTIONS = ((-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1))
_POPCOUNT = np.array([int(i).bit_count() for i in range(256)], dtype=np.uint8)


def trace_skeleton(skeleton, min_length=20., simplify=.4, stop=None):
    """Trace every undirected edge once; junctions split, cycles stay closed.

    Unlike findContours, this follows a graph centerline, so an open line is not
    traversed out and back. Degree-two nodes continue; ambiguous nodes never do.
    Compact uint8 arrays avoid millions of Python node/edge objects.
    """
    skeleton = np.asarray(skeleton, dtype=bool)
    height,width = skeleton.shape
    links = np.zeros(skeleton.shape, dtype=np.uint8)
    for drdc,(dr,dc) in enumerate(_DIRECTIONS):
        for row in range(max(0,-dr), min(height,height-dr), 512):
            if stop is not None and stop.is_set():raise InterruptedError("Đã dừng số hóa.")
            end=min(row+512,height,height-dr)
            left=max(0,-dc);right=min(width,width-dc)
            center=skeleton[row:end,left:right]
            neighbor=skeleton[row+dr:end+dr,left+dc:right+dc]
            valid=center & neighbor
            if dr and dc:
                valid &= ~(skeleton[row+dr:end+dr,left:right] | skeleton[row:end,left+dc:right+dc])
            links[row:end,left:right] |= valid.astype(np.uint8) * (1 << drdc)
    degree=_POPCOUNT[links]
    visited=np.zeros(skeleton.shape,dtype=np.uint8)
    result=[]
    def walk(r,c,direction):
        origin=(r,c);path=[(float(c),float(r))];length=0.
        branch=degree[r,c]>2
        while True:
            bit=1 << direction
            if visited[r,c] & bit:break
            visited[r,c] |= bit
            dr,dc=_DIRECTIONS[direction];r+=dr;c+=dc
            visited[r,c] |= 1 << ((direction+4)%8)
            length+=math.sqrt(2) if dr and dc else 1.
            path.append((float(c),float(r)))
            if degree[r,c] != 2 or (r,c)==origin:
                branch=branch or degree[r,c]>2;break
            remaining=int(links[r,c]) & ~int(visited[r,c])
            if remaining==0:break
            direction=(remaining & -remaining).bit_length()-1
            if len(path)%4096==0 and stop is not None and stop.is_set():raise InterruptedError("Đã dừng số hóa.")
        if length < min_length or len(path)<2:return
        points=np.array(path,dtype=np.float64)
        if simplify>0 and len(points)>3:
            # Double precision RDP preserves first/last points, including closed loops.
            from skimage.measure import approximate_polygon
            points=approximate_polygon(points,tolerance=simplify)
        if len(points)>=2 and np.any(np.diff(points,axis=0)):
            result.append((points, bool(branch)))
    for endpoints_first in (True,False):
        for r in range(height):
            if stop is not None and stop.is_set():raise InterruptedError("Đã dừng số hóa.")
            candidates=(links[r]!=visited[r]) & ((degree[r]!=2) if endpoints_first else (degree[r]==2))
            for c in np.flatnonzero(candidates):
                remaining=int(links[r,c]) & ~int(visited[r,c])
                while remaining:
                    direction=(remaining & -remaining).bit_length()-1
                    walk(r,int(c),direction)
                    remaining=int(links[r,c]) & ~int(visited[r,c])
    return result


def image_to_world(points, coefficients):
    # World file order: A, D, B, E, C, F. C,F are centers of the upper-left pixel.
    a,d,b,e,c,f = coefficients
    xy=np.asarray(points,dtype=np.float64)
    return np.column_stack((a*xy[:,0]+b*xy[:,1]+c, d*xy[:,0]+e*xy[:,1]+f))


def record_from_pixels(points, coefficients, elevation=None, branch=False):
    world=image_to_world(points,coefficients)
    geometry=LineString(world if elevation is None else np.column_stack((world,np.full(len(world),elevation))))
    return dict(pixels=np.asarray(points,dtype=float).tolist(),geometry=geometry,ELEVATION=elevation,
                LENGTH_M=round(geometry.length,3),REVIEWED=False,BRANCH=branch)


def extract_patch(bgr, params, coefficients, offset=(0,0), stop=None):
    mask=contour_mask(bgr,params)
    skel=skeletonize(mask)
    paths=trace_skeleton(skel,params["min_length"],params["simplify"],stop)
    records=[record_from_pixels(pts+np.array(offset),coefficients,branch=branch) for pts,branch in paths]
    return paths,records,skel


def extract_tiled(pil_image, params, coefficients, stop, progress=None, tile_size=2048, halo=64):
    """Halo in processing, disjoint ownership in storage, ONE global graph trace.

    No line-merging heuristics across tiles, and no duplicated overlap edges.
    Isolated ambiguous seam pixels remain subject to visual review, not snapped.
    """
    width,height=pil_image.size
    if width*height>120_000_000:
        raise ValueError("Ảnh vượt 120 triệu pixel. Hãy cắt mảnh ở độ phân giải gốc để xử lý an toàn.")
    with tempfile.TemporaryDirectory(prefix="topocontour-") as directory:
        thin=None
        try:
            thin=np.memmap(os.path.join(directory,"skeleton.bin"),mode="w+",dtype=bool,shape=(height,width))
            total=math.ceil(width/tile_size)*math.ceil(height/tile_size);processed=0
            for y in range(0,height,tile_size):
                for x in range(0,width,tile_size):
                    if stop.is_set():raise InterruptedError("Đã dừng; giữ nguyên kết quả cũ.")
                    right,bottom=min(x+tile_size,width),min(y+tile_size,height)
                    x0,y0=max(0,x-halo),max(0,y-halo)
                    rgb=np.array(pil_image.crop((x0,y0,min(right+halo,width),min(bottom+halo,height))).convert("RGB"))
                    mask=contour_mask(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),params)
                    skel=skeletonize(mask)
                    thin[y:bottom,x:right]=skel[y-y0:bottom-y0,x-x0:right-x0]
                    processed+=1
                    if progress:progress(processed/total*.72,f"Tách nét ô {processed}/{total}")
            thin.flush()
            if progress:progress(.75,"Truy vết toàn bản đồ, khử trùng vùng chồng lấn…")
            paths=trace_skeleton(thin,params["min_length"],params["simplify"],stop)
            if stop.is_set():raise InterruptedError("Đã dừng; giữ nguyên kết quả cũ.")
            return [record_from_pixels(pts,coefficients,branch=branch) for pts,branch in paths]
        finally:
            # Release Windows mmap handles before TemporaryDirectory removes the file.
            if thin is not None:
                thin.flush();thin._mmap.close();del thin


def validate_records(records):
    problems=[]
    lines=[LineString(record["pixels"]) for record in records]
    for i,(record,line) in enumerate(zip(records,lines)):
        if not line.is_simple:problems.append((i,"Tự giao/chồng nét"))
        if record.get("BRANCH"):problems.append((i,"Đầu mút tại ngã rẽ: cần xem lại"))
        if record["ELEVATION"] is None:problems.append((i,"Chưa gán cao độ"))
        if not record.get("REVIEWED"):problems.append((i,"Chưa xác nhận kiểm tra"))
    if lines:
        tree=STRtree(lines)
        for i,line in enumerate(lines):
            for j in tree.query(line,predicate="intersects"):
                j=int(j)
                if j<=i:continue
                intersection=line.intersection(lines[j])
                shared_end=intersection.geom_type=="Point" and all(
                    min(intersection.distance(Point(g.coords[0])),intersection.distance(Point(g.coords[-1])))<1e-8
                    for g in (line,lines[j]))
                if shared_end and records[i]["ELEVATION"]==records[j]["ELEVATION"]:continue
                problems.append((i,f"Giao/chồng đường #{j+1}"))
    return problems


def guided_segment(pil_image,start,end,params):
    """Semi-automatic tracing in a small corridor; retain uncertain breaks."""
    points=np.array([start,end],dtype=float)
    lower=np.maximum(0,np.floor(points.min(axis=0)-30)).astype(int)
    upper=np.minimum(pil_image.size,np.ceil(points.max(axis=0)+31)).astype(int)
    if np.prod(upper-lower)>1_000_000:
        raise ValueError("Hai điểm dẫn quá xa; bấm thêm điểm gần nhau trên cùng đường.")
    rgb=np.array(pil_image.crop((*lower,*upper)).convert('RGB'))
    mask=contour_mask(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),params)
    if not mask.any():raise ValueError("Không nhận diện được nét trong hành lang. Lấy mẫu màu/chỉnh ngưỡng trước.")
    distance=ndimage.distance_transform_edt(~mask)
    p=np.rint(points-lower).astype(int)
    if np.any(p<0) or np.any(p[:,0]>=mask.shape[1]) or np.any(p[:,1]>=mask.shape[0]):
        raise ValueError("Điểm dẫn nằm ngoài ảnh.")
    path,_=route_through_array(1.+distance**2*10.,tuple(p[0,::-1]),tuple(p[1,::-1]),fully_connected=True)
    pixels=np.array(path)
    if distance[pixels[:,0],pixels[:,1]].max()>4.:
        raise ValueError("Đoạn dò rời nét hơn 4 pixel. Thêm điểm dẫn hoặc vẽ tay qua chỗ đứt.")
    return (pixels[:,::-1]+lower).astype(float).tolist()


class TopoContourDigitizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TopoContour Digitizer Pro — Tâm nét, kiểm tra cao độ & tọa độ")
        self.geometry("1400x850")

        # Biến dữ liệu
        self.image_path = None
        self.pil_img = None
        self.img_width = 0
        self.img_height = 0
        self.preview_scale = 1.0
        self.crop_box = None  # (x1, y1, x2, y2) trên ảnh gốc để test nhanh

        # Thông số lọc màu HSV mặc định cho đường đồng mức màu nâu/cam trên bản đồ địa hình VN
        self.hsv_lower = np.array([5, 45, 60], dtype=np.uint8)
        self.hsv_upper = np.array([28, 255, 235], dtype=np.uint8)

        # Danh sách kết quả Vector (Shapely LineStrings + Elevation)
        self.extracted_contours = []  # List of dicts: {'geometry': LineString, 'elevation': float}
        self.preview_records = []
        self.positive_samples = []
        self.negative_samples = []
        self.world_coefficients = None
        self.world_signature = None
        self.geo_confirmed = False
        self.busy = False
        self.stop_event = threading.Event()
        self.event_queue = queue.Queue()
        self.select_ids = set()
        self.pending_points = []
        self.display_transform = (0., 0., 1.)
        self.history = []
        self.project_path = None
        self.dirty = False
        self.gcps = []
        self.gcp_fit_signature = None
        self.drag_vertex = None
        self.last_mouse = None
        self._build_ui()
        for entry in (self.ent_x_origin,self.ent_y_origin,self.ent_pixel_size,self.ent_epsg):
            entry.bind('<KeyRelease>',self._geo_field_changed,add='+')
        self.after(100,self._poll_events)
        self.protocol("WM_DELETE_WINDOW",self.on_close)

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ================= PANEL ĐIỀU KHIỂN BÊN TRÁI =================
        self.sidebar = ctk.CTkScrollableFrame(self, width=380, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        ctk.CTkLabel(
            self.sidebar, text="SỐ HÓA ĐƯỜNG ĐỒNG MỨC",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(10, 5))
        ctk.CTkLabel(
            self.sidebar, text="Truy vết tâm nét • Không tự suy đoán cao độ",
            font=ctk.CTkFont(size=12), text_color="gray"
        ).pack(pady=(0, 15))

        # --- Bước 1: Tải ảnh & Tọa độ ---
        frame_step1 = ctk.CTkFrame(self.sidebar)
        frame_step1.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame_step1, text="1. Dữ liệu Bản đồ & Tọa độ (Georef)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        ctk.CTkButton(frame_step1, text="📂 Chọn ảnh bản đồ (10000.jpg...)", command=self.load_image).pack(fill="x", padx=10, pady=4)
        self.lbl_img_info = ctk.CTkLabel(frame_step1, text="Chưa tải ảnh", font=ctk.CTkFont(size=11), text_color="#A0A0A0")
        self.lbl_img_info.pack(padx=10, pady=2)

        # Tọa độ góc (World File hoặc nhập tay Góc Trái-Trên + Độ phân giải m/pixel)
        grid_geo = ctk.CTkFrame(frame_step1, fg_color="transparent")
        grid_geo.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(grid_geo, text="X Gốc (Trái-Trên):").grid(row=0, column=0, sticky="w", pady=2)
        self.ent_x_origin = ctk.CTkEntry(grid_geo, width=120)
        self.ent_x_origin.insert(0, "")
        self.ent_x_origin.grid(row=0, column=1, padx=5, pady=2)

        ctk.CTkLabel(grid_geo, text="Y Gốc (Trái-Trên):").grid(row=1, column=0, sticky="w", pady=2)
        self.ent_y_origin = ctk.CTkEntry(grid_geo, width=120)
        self.ent_y_origin.insert(0, "")
        self.ent_y_origin.grid(row=1, column=1, padx=5, pady=2)

        ctk.CTkLabel(grid_geo, text="Cỡ Pixel (m/px):").grid(row=2, column=0, sticky="w", pady=2)
        self.ent_pixel_size = ctk.CTkEntry(grid_geo, width=120)
        self.ent_pixel_size.insert(0, "")  # Không suy ra cỡ pixel chỉ từ tỷ lệ ghi trên bản đồ.
        self.ent_pixel_size.grid(row=2, column=1, padx=5, pady=2)

        ctk.CTkLabel(grid_geo, text="Mã EPSG (VN2000):").grid(row=3, column=0, sticky="w", pady=2)
        self.ent_epsg = ctk.CTkEntry(grid_geo, width=120)
        self.ent_epsg.insert(0, "")  # Phải khai báo đúng múi / kinh tuyến trục; không đoán EPSG.
        self.ent_epsg.grid(row=3, column=1, padx=5, pady=2)

        ctk.CTkButton(frame_step1, text="📍 Nạp file .tfw / .jgw (Nếu có)", fg_color="#3B5998", command=self.load_world_file).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(frame_step1,text="Điểm khống chế / nắn affine…",command=self.open_gcp_editor).pack(fill="x",padx=10,pady=4)
        ctk.CTkButton(frame_step1,text="Lưu dự án / mở dự án…",command=self.project_menu).pack(fill="x",padx=10,pady=4)
        ctk.CTkButton(frame_step1,text="Hướng dẫn & giới hạn độ chính xác",command=self.show_help).pack(fill="x",padx=10,pady=4)

        # --- Bước 2: Lọc màu đường đồng mức (HSV) ---
        frame_step2 = ctk.CTkFrame(self.sidebar)
        frame_step2.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame_step2, text="2. Tách màu Đường đồng mức (Nâu/Cam)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        ctk.CTkLabel(
            frame_step2,
            text="Lấy nhiều mẫu trực tiếp trên nét, không lấy nền giấy.\nMẫu loại bỏ giúp loại đường/ký hiệu khác màu.",
            font=ctk.CTkFont(size=11), text_color="#66D9EF"
        ).pack(padx=10, pady=2)

        self.slider_h_min = self._create_slider(frame_step2, "Hue Min (Màu):", 0, 179, 5)
        self.slider_h_max = self._create_slider(frame_step2, "Hue Max (Màu):", 0, 179, 28)
        self.slider_s_min = self._create_slider(frame_step2, "Sat Min (Độ đậm):", 0, 255, 45)
        self.slider_v_max = self._create_slider(frame_step2, "V tối đa (loại nền sáng):", 50, 255, 245)
        self.slider_v_min = self._create_slider(frame_step2, "V tối thiểu (loại chữ đen):", 0, 180, 55)
        self.slider_tol = self._create_slider(frame_step2, "Dung sai Lab mẫu nét:", 2, 40, 12)
        self.slider_contrast = self._create_slider(frame_step2,"Tương phản nét / nền:",0.,8.,1.)
        self.sample_info = ctk.CTkLabel(frame_step2,text="0 mẫu nét; 0 mẫu loại.",font=ctk.CTkFont(size=11))
        self.sample_info.pack(fill="x",padx=10,pady=3)
        ctk.CTkButton(frame_step2,text="Xóa toàn bộ mẫu màu",command=self.clear_samples).pack(fill="x",padx=10,pady=4)

        # --- Bước 3: Tham số Hình học & Khử nhiễu ---
        frame_step3 = ctk.CTkFrame(self.sidebar)
        frame_step3.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame_step3, text="3. Truy vết tâm nét & Đơn giản hóa", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        self.slider_close_gap = self._create_slider(frame_step3, "Bán kính hàn nét (0 = tắt):", 0, 2, 0)
        self.slider_min_len = self._create_slider(frame_step3, "Bỏ đoạn ngắn (<px):", 2, 300, 20)
        self.slider_simplify = self._create_slider(frame_step3, "Sai lệch Douglas-Peucker (px):", 0., 3., .4)

        grid_elev = ctk.CTkFrame(frame_step3, fg_color="transparent")
        grid_elev.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(grid_elev, text="Z của đường đã chọn (m):").grid(row=0, column=0, sticky="w")
        self.ent_default_z = ctk.CTkEntry(grid_elev, width=90)
        self.ent_default_z.insert(0, "")
        self.ent_default_z.grid(row=0, column=1, padx=5)
        ctk.CTkButton(frame_step3,text="Bảng đường / gán Z / kiểm tra…",command=self.open_result_table).pack(fill="x",padx=10,pady=5)

        # --- Bước 4: Thực thi & Xuất dữ liệu ---
        frame_step4 = ctk.CTkFrame(self.sidebar)
        frame_step4.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(frame_step4, text="4. Xử lý & Xuất CAD / GIS", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        ctk.CTkButton(
            frame_step4, text="🔍 Test thử trên Vùng Đang Xem (Preview)",
            fg_color="#E67E22", hover_color="#D35400", command=self.run_preview_extraction
        ).pack(fill="x", padx=10, pady=4)

        self.btn_full_run = ctk.CTkButton(
            frame_step4, text="⚡ SỐ HÓA TOÀN BỘ BẢN ĐỒ (Tiled Mode)",
            fg_color="#27AE60", hover_color="#1E8449", height=38,
            font=ctk.CTkFont(weight="bold"), command=self.run_full_map_extraction_thread
        )
        self.btn_full_run.pack(fill="x", padx=10, pady=6)

        self.progress_bar = ctk.CTkProgressBar(frame_step4)
        self.progress_bar.pack(fill="x", padx=10, pady=4)
        self.progress_bar.set(0)
        ctk.CTkButton(frame_step4,text="Dừng xử lý",fg_color="#9c4343",command=self.stop_event.set).pack(fill="x",padx=10,pady=3)

        self.lbl_status = ctk.CTkLabel(frame_step4, text="Sẵn sàng.", font=ctk.CTkFont(size=12))
        self.lbl_status.pack(padx=10, pady=2)

        btn_export_frame = ctk.CTkFrame(frame_step4, fg_color="transparent")
        btn_export_frame.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(btn_export_frame, text="💾 Xuất AutoCAD (.DXF)", width=160, command=self.export_dxf).pack(side="left", padx=2)
        ctk.CTkButton(btn_export_frame, text="🌍 Xuất 3D Shapefile (.SHP)", width=160, command=self.export_shapefile).pack(side="right", padx=2)

        # ================= KHUNG HIỂN THỊ BẢN ĐỒ BÊN PHẢI =================
        self.main_view = ctk.CTkFrame(self)
        self.main_view.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.main_view.grid_rowconfigure(1, weight=1)
        self.main_view.grid_columnconfigure(0, weight=1)

        # Thanh công cụ điều hướng vùng xem
        toolbar = ctk.CTkFrame(self.main_view, height=40)
        toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        self.tool_mode = tk.StringVar(value="Lấy màu nét")
        ctk.CTkOptionMenu(toolbar,variable=self.tool_mode,values=["Lấy màu nét","Lấy màu loại","Chọn đường","Vẽ tay","Dò theo điểm","Sửa đỉnh","Cắt đường","Điểm nắn"],
                          command=self.set_tool).pack(side="left",padx=5)
        ctk.CTkLabel(toolbar,text="Chuột phải: kéo | Cuộn: zoom | Enter: kết thúc vẽ").pack(side="left",padx=5)
        ctk.CTkButton(toolbar, text="🔄 Xem toàn cảnh", width=120, command=self.reset_view).pack(side="right", padx=5)

        # Canvas hiển thị ảnh
        self.canvas = tk.Canvas(self.main_view, bg="#1E1E1E", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Gán sự kiện chuột trên Canvas
        self.canvas.bind("<Button-1>", self.on_canvas_left_click)       # Lấy mẫu màu HSV
        self.canvas.bind("<ButtonPress-3>", self.on_pan_start)          # Bắt đầu kéo ảnh
        self.canvas.bind("<B3-Motion>", self.on_pan_move)               # Di chuyển vùng xem
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)           # Phóng to / Thu nhỏ
        self.canvas.bind("<Button-4>",lambda e:self.on_mouse_wheel(e,1))
        self.canvas.bind("<Button-5>",lambda e:self.on_mouse_wheel(e,-1))
        self.canvas.bind("<Configure>",lambda e:self.render_viewport())
        self.canvas.bind("<Return>",lambda e:self.finish_manual_line())
        self.canvas.bind("<Escape>",lambda e:self.cancel_manual_line())
        self.canvas.bind("<BackSpace>",lambda e:self.backspace_manual_line())
        self.canvas.bind('<B1-Motion>',self.on_vertex_drag)
        self.canvas.bind('<ButtonRelease-1>',self.on_vertex_release)
        self.canvas.bind('<Motion>',lambda e:setattr(self,'last_mouse',(e.x,e.y)))
        self.canvas.bind('<Delete>',self.delete_vertex)

        # Biến điều khiển khung nhìn (Viewport trên ảnh gốc)
        self.view_x = 0
        self.view_y = 0
        self.view_w = 1000
        self.view_h = 800
        self.pan_start_x = 0
        self.pan_start_y = 0

    def _create_slider(self, parent, label_text, min_val, max_val, init_val):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=2)
        lbl = ctk.CTkLabel(frame, text=f"{label_text} {init_val}", font=ctk.CTkFont(size=11))
        lbl.pack(anchor="w")

        def update_lbl(val):
            v = round(float(val), 1) if isinstance(init_val, float) else int(float(val))
            lbl.configure(text=f"{label_text} {v}")
            self.dirty=True

        slider = ctk.CTkSlider(frame, from_=min_val, to=max_val, command=update_lbl)
        slider.set(init_val)
        slider.pack(fill="x", pady=1)
        slider.value_label=lbl
        slider.label_text=label_text
        return slider

    # ================= XỬ LÝ TẢI ẢNH & HIỂN THỊ =================





    # ================= SỰ KIỆN TƯƠNG TÁC CHUỘT =================




    # ================= LÕI THUẬT TOÁN SỐ HÓA ĐƯỜNG ĐỒNG MỨC =================




    # ================= XUẤT FILE AUTOCAD (.DXF) & GIS (.SHP) =================


    def _warn_busy(self):
        if self.busy:
            messagebox.showinfo("Đang xử lý","Nhấn Dừng và chờ hoàn tất trước khi thay đổi dữ liệu.")
            return True
        return False

    def _parameters(self):
        params=dict(h_min=int(self.slider_h_min.get()),h_max=int(self.slider_h_max.get()),
                    s_min=int(self.slider_s_min.get()),v_min=int(self.slider_v_min.get()),
                    v_max=int(self.slider_v_max.get()),tolerance=float(self.slider_tol.get()),
                    contrast=float(self.slider_contrast.get()),close_radius=int(round(self.slider_close_gap.get())),
                    min_length=float(self.slider_min_len.get()),simplify=float(self.slider_simplify.get()),
                    positive=copy.deepcopy(self.positive_samples),negative=copy.deepcopy(self.negative_samples))
        if params['v_min']>=params['v_max']:
            raise ValueError("V tối thiểu phải nhỏ hơn V tối đa.")
        return params

    def _set_slider(self,slider,value):
        slider.set(value)
        slider.value_label.configure(text=f"{slider.label_text} {value:.2f}")

    def _get_geo(self,required=False):
        if required and self.gcp_fit_signature is not None and self.gcp_fit_signature!=json.dumps(self.gcps,sort_keys=True):
            raise ValueError('Điểm khống chế đã thay đổi. Tính nắn affine lại trước khi xuất.')
        values=[self.ent_x_origin.get(),self.ent_y_origin.get(),self.ent_pixel_size.get()]
        if not all(str(v).strip() for v in values):
            if required:raise ValueError("Chưa nắn ảnh. Nạp World File hoặc nhập gốc X,Y và cỡ pixel, hoặc dùng điểm nắn.")
            return (1.,0.,0.,-1.,0.,0.)
        signature=tuple(finite_number(v) for v in values)
        x,y,size=signature
        if size<=0:raise ValueError("Cỡ pixel phải >0.")
        if self.world_coefficients is not None and signature==self.world_signature:
            return tuple(self.world_coefficients)
        if required and (not self.geo_confirmed or
                         (self.world_coefficients is not None and signature!=self.world_signature)):
            if not messagebox.askyesno("Xác nhận tọa độ nhập tay",
                    "Ảnh chưa có phép nắn được kiểm chứng. Chỉ dùng gốc và cỡ pixel cho ảnh không xoay, không méo.\n"
                    "Bạn đã kiểm tra các thông số này với lưới tọa độ trên bản đồ?"):
                raise ValueError("Cần nắn/kiểm tra tọa độ trước khi xuất.")
            self.geo_confirmed=True
        return (size,0.,0.,-size,x,y)

    def load_image(self):
        if self._warn_busy():return
        path=filedialog.askopenfilename(title="Chọn ảnh bản đồ gốc",filetypes=[("Ảnh bản đồ","*.jpg *.jpeg *.tif *.tiff *.png *.bmp")])
        if not path:return
        if self.dirty and not messagebox.askyesno("Đổi ảnh","Bỏ thay đổi chưa lưu của dự án hiện tại?"):return
        try:
            self._install_image(path)
            base=os.path.splitext(path)[0]
            for ext in ('.jgw','.tfw','.jpgw','.pgw','.wld'):
                if os.path.exists(base+ext):self._parse_world_file(base+ext,notify=False);break
            prj=base+'.prj'
            if os.path.exists(prj):
                crs=CRS.from_wkt(open(prj,encoding='utf-8').read())
                self.ent_epsg.delete(0,'end');self.ent_epsg.insert(0,crs.to_string())
            self.lbl_status.configure(text="Đã mở ảnh. Lấy nhiều mẫu trên nét; Preview trước khi chạy toàn bộ.")
        except Exception as exc:messagebox.showerror("Lỗi đọc ảnh",str(exc))

    def _install_image(self,path):
        image=Image.open(path)
        width,height=image.size
        if width*height>120_000_000:
            image.close();raise ValueError("Ảnh >120 triệu pixel; cắt thành các mảnh ở độ phân giải gốc trước khi xử lý.")
        if self.pil_img:self.pil_img.close()
        self.image_path=os.path.abspath(path);self.pil_img=image;self.img_width,self.img_height=image.size
        self.extracted_contours=[];self.preview_records=[];self.select_ids=set();self.pending_points=[]
        self.history=[];self.gcps=[];self.gcp_fit_signature=None;self.positive_samples=[];self.negative_samples=[]
        self.world_coefficients=None;self.world_signature=None;self.geo_confirmed=False
        self.project_path=None;self.dirty=False
        for entry in (self.ent_x_origin,self.ent_y_origin,self.ent_pixel_size,self.ent_epsg,self.ent_default_z):entry.delete(0,'end')
        self.sample_info.configure(text="0 mẫu nét; 0 mẫu loại.")
        self.lbl_img_info.configure(text=f"{os.path.basename(path)} ({os.path.getsize(path)/1048576:.1f} MiB)\n{width} × {height} pixel gốc")
        self.reset_view()

    def load_world_file(self):
        if self._warn_busy():return
        path=filedialog.askopenfilename(title="Nạp đầy đủ 6 hệ số World File",filetypes=[("World File","*.jgw *.tfw *.jpgw *.pgw *.wld")])
        if path:self._parse_world_file(path)

    def _parse_world_file(self,filepath,notify=True):
        try:
            with open(filepath,encoding='utf-8-sig') as handle:values=[finite_number(v) for v in handle.read().split()]
            if len(values)!=6:raise ValueError("World File phải có đúng 6 hệ số A,D,B,E,C,F.")
            a,d,b,e,c,f=values
            if abs(a*e-b*d)<1e-15:raise ValueError("Phép chuyển tọa độ suy biến.")
            self.world_coefficients=tuple(values)
            self.gcp_fit_signature=None
            size=math.hypot(a,d)
            for entry,value in [(self.ent_x_origin,c),(self.ent_y_origin,f),(self.ent_pixel_size,size)]:
                entry.delete(0,'end');entry.insert(0,repr(value))
            self.world_signature=(c,f,size);self.geo_confirmed=True;self.dirty=True
            if notify:messagebox.showinfo("World File","Đã nạp đủ hệ số xoay, pixel X/Y và tọa độ tâm pixel.\nVẫn cần khai báo đúng CRS; World File không chứa CRS.")
        except Exception as exc:messagebox.showerror("World File",str(exc))

    def reset_view(self):
        if self.pil_img is None:return
        self.view_x=0.;self.view_y=0.;self.view_w=float(self.img_width);self.view_h=float(self.img_height)
        self.render_viewport()

    def render_viewport(self,overlay_bgr=None):
        if self.pil_img is None:return
        cw=max(self.canvas.winfo_width(),1);ch=max(self.canvas.winfo_height(),1)
        if cw<5 or ch<5:return
        x1=max(0,int(self.view_x));y1=max(0,int(self.view_y))
        x2=min(self.img_width,max(x1+1,int(math.ceil(self.view_x+self.view_w))))
        y2=min(self.img_height,max(y1+1,int(math.ceil(self.view_y+self.view_h))))
        self.crop_box=(x1,y1,x2,y2)
        scale=min(cw/(x2-x1),ch/(y2-y1))
        display_w=max(1,round((x2-x1)*scale));display_h=max(1,round((y2-y1)*scale))
        left=(cw-display_w)/2;top=(ch-display_h)/2
        self.display_transform=(left,top,scale)
        patch=self.pil_img.crop(self.crop_box).convert('RGB')
        patch=patch.resize((display_w,display_h),Image.Resampling.BILINEAR)
        self.tk_img=ImageTk.PhotoImage(patch)
        self.canvas.delete('all');self.canvas.create_image(left,top,anchor='nw',image=self.tk_img)
        # Draw thin vector overlays at display scale, never bake thick green strokes into the source.
        for records,color,width in [(self.extracted_contours,'#00d7e8',1),(self.preview_records,'#53ed58',1)]:
            for i,item in enumerate(records):
                pts=np.asarray(item['pixels'],dtype=float)
                low=pts.min(axis=0);high=pts.max(axis=0)
                if high[0]<x1 or low[0]>x2 or high[1]<y1 or low[1]>y2:continue
                xy=(pts-np.array([x1,y1]))*scale+np.array([left,top])
                selected=records is self.extracted_contours and i in self.select_ids
                line_color='#ff38b9' if selected else '#5cce84' if item.get('REVIEWED') else color
                self.canvas.create_line(*xy.ravel().tolist(),fill=line_color,width=2 if selected else width)
                if selected and self.tool_mode.get()=='Sửa đỉnh':
                    for vx,vy in xy:
                        if 0<=vx<=cw and 0<=vy<=ch:self.canvas.create_oval(vx-2,vy-2,vx+2,vy+2,fill='#ff38b9')
        if self.pending_points:
            xy=(np.array(self.pending_points)-[x1,y1])*scale+[left,top]
            if len(xy)>1:self.canvas.create_line(*xy.ravel().tolist(),fill='#ff38b9',width=2)
            for x,y in xy:self.canvas.create_oval(x-2,y-2,x+2,y+2,fill='#ff38b9')
        for i,p in enumerate(self.gcps):
            x=(p['px']-x1)*scale+left;y=(p['py']-y1)*scale+top
            self.canvas.create_line(x-4,y,x+4,y,fill='#ff339e');self.canvas.create_line(x,y-4,x,y+4,fill='#ff339e')
            self.canvas.create_text(x+7,y-6,text=str(i+1),fill='#ff339e',anchor='w')

    def _canvas_to_image(self,x,y):
        if not self.crop_box:return None
        left,top,scale=self.display_transform;x1,y1,x2,y2=self.crop_box
        px=x1+(x-left)/scale;py=y1+(y-top)/scale
        return (px,py) if x1<=px<x2 and y1<=py<y2 else None

    def on_pan_start(self,event):
        self.pan_start_x=event.x;self.pan_start_y=event.y

    def on_pan_move(self,event):
        if self.pil_img is None:return
        scale=self.display_transform[2]
        self.view_x=float(np.clip(self.view_x+(self.pan_start_x-event.x)/scale,0,max(0,self.img_width-self.view_w)))
        self.view_y=float(np.clip(self.view_y+(self.pan_start_y-event.y)/scale,0,max(0,self.img_height-self.view_h)))
        self.pan_start_x=event.x;self.pan_start_y=event.y;self.render_viewport()

    def on_mouse_wheel(self,event,direction=None):
        if self.pil_img is None:return
        point=self._canvas_to_image(event.x,event.y)
        if point is None:return
        direction=direction if direction is not None else event.delta
        factor=.8 if direction>0 else 1.25
        px,py=point;rx=(px-self.view_x)/self.view_w;ry=(py-self.view_y)/self.view_h
        self.view_w=float(np.clip(self.view_w*factor,min(20,self.img_width),self.img_width))
        self.view_h=float(np.clip(self.view_h*factor,min(20,self.img_height),self.img_height))
        self.view_x=float(np.clip(px-rx*self.view_w,0,max(0,self.img_width-self.view_w)))
        self.view_y=float(np.clip(py-ry*self.view_h,0,max(0,self.img_height-self.view_h)))
        self.render_viewport()

    def set_tool(self,value):
        self.pending_points=[];self.drag_vertex=None;self.canvas.focus_set();self.render_viewport()
        self.lbl_status.configure(text=value+": bấm trên ảnh gốc; cuộn chuột để phóng to.")

    def on_canvas_left_click(self,event):
        if self.pil_img is None or self._warn_busy():return
        point=self._canvas_to_image(event.x,event.y)
        if point is None:return
        self.canvas.focus_set();px,py=point;mode=self.tool_mode.get()
        if mode=='Điểm nắn':self.add_gcp(px,py);return
        if mode in ('Vẽ tay','Dò theo điểm'):
            try:
                if mode=='Dò theo điểm' and self.pending_points:
                    segment=guided_segment(self.pil_img,self.pending_points[-1],[px,py],self._parameters())
                    self.pending_points.extend(segment[1:])
                else:self.pending_points.append([px,py])
                self.render_viewport()
            except Exception as exc:messagebox.showinfo('Dò đường',str(exc))
            return
        if mode in ('Sửa đỉnh','Cắt đường'):
            self.edit_at_point(px,py,event);return
        if mode=='Chọn đường':
            query=Point(px,py);scale=self.display_transform[2];nearest=(8/scale,None)
            for i,item in enumerate(self.extracted_contours):
                distance=LineString(item['pixels']).distance(query)
                if distance<nearest[0]:nearest=distance,i
            if not event.state & 0x0004:self.select_ids=set()
            if nearest[1] is not None:
                i=nearest[1]
                if i in self.select_ids:self.select_ids.remove(i)
                else:self.select_ids.add(i)
                z=self.extracted_contours[i]['ELEVATION'];self.ent_default_z.delete(0,'end')
                if z is not None:self.ent_default_z.insert(0,str(z))
                self.lbl_status.configure(text=f"Đường #{i+1}: {len(self.extracted_contours[i]['pixels'])} đỉnh; Z={z if z is not None else 'chưa biết'}")
            self.render_viewport();return
        # Center pixel, not median of a 3x3 patch that is often mostly yellow paper.
        rgb=self.pil_img.crop((int(px),int(py),int(px)+1,int(py)+1)).convert('RGB')
        bgr=np.array(rgb)[0,0,::-1].copy();h,s,v=cv2.cvtColor(bgr.reshape(1,1,3),cv2.COLOR_BGR2HSV)[0,0]
        if mode=='Lấy màu nét':
            if int(s)<18 or int(v)<55:
                messagebox.showinfo("Lấy mẫu nét","Pixel này gần màu đen/xám hoặc quá tối. Phóng to và bấm chính giữa nét nâu.");return
            self.positive_samples.append(bgr.tolist())
            # Broad enough hue gate for ALL existing samples; Lab still limits the foreground.
            sample_hsv=cv2.cvtColor(np.array(self.positive_samples,dtype=np.uint8).reshape(1,-1,3),cv2.COLOR_BGR2HSV)[0]
            angles=sample_hsv[:,0].astype(float)*2*np.pi/180
            center=math.atan2(float(np.sin(angles).mean()),float(np.cos(angles).mean()))*180/(2*np.pi)%180
            differences=np.abs((sample_hsv[:,0].astype(float)-center+90)%180-90)
            radius=min(89,float(differences.max())+8)
            self._set_slider(self.slider_h_min,int((center-radius)%180));self._set_slider(self.slider_h_max,int((center+radius)%180))
            self._set_slider(self.slider_s_min,max(18,int(sample_hsv[:,1].min())-35))
            self._set_slider(self.slider_v_max,min(255,int(sample_hsv[:,2].max())+30))
        else:self.negative_samples.append(bgr.tolist())
        self.sample_info.configure(text=f"{len(self.positive_samples)} mẫu nét; {len(self.negative_samples)} mẫu loại.")
        self.dirty=True
        self.lbl_status.configure(text=f"Đã lấy mẫu tại ({px:.1f}, {py:.1f}). Nhấn Preview để xem nét nhận diện.")

    def clear_samples(self):
        if self._warn_busy():return
        self.positive_samples=[];self.negative_samples=[];self.preview_records=[]
        self.sample_info.configure(text="0 mẫu nét; 0 mẫu loại.");self.dirty=True;self.render_viewport()

    def _process_patch_to_polylines(self,bgr_img,offset_x=0,offset_y=0,params=None,coefficients=None):
        # GUI parameters must be captured on Tk's main thread, never inside worker threads.
        params=params if params is not None else self._parameters()
        coefficients=coefficients if coefficients is not None else self._get_geo()
        paths,records,skel=extract_patch(bgr_img,params,coefficients,(offset_x,offset_y))
        return [points for points,branch in paths],records,(skel*255).astype(np.uint8)

    def _start_worker(self,function,done):
        if self.busy:return
        self.busy=True;self.stop_event.clear();self.btn_full_run.configure(state='disabled')
        def run():
            try:self.event_queue.put(('done',done,function()))
            except Exception as exc:self.event_queue.put(('error',None,exc))
        threading.Thread(target=run,daemon=True).start()

    def _poll_events(self):
        try:
            while True:
                kind,callback,value=self.event_queue.get_nowait()
                if kind=='progress':self.progress_bar.set(value[0]);self.lbl_status.configure(text=value[1]);continue
                self.busy=False;self.btn_full_run.configure(state='normal')
                if kind=='error':
                    self.lbl_status.configure(text=str(value))
                    if not isinstance(value,InterruptedError):messagebox.showerror('Xử lý',str(value))
                elif self.stop_event.is_set():self.lbl_status.configure(text='Đã dừng; giữ nguyên kết quả cũ.')
                else:
                    try:callback(value)
                    except Exception as exc:messagebox.showerror('Kết quả',str(exc))
        except queue.Empty:pass
        self.after(100,self._poll_events)

    def run_preview_extraction(self):
        if self._warn_busy():return
        if self.pil_img is None or not self.crop_box:
            messagebox.showinfo('Chưa có ảnh','Mở bản đồ trước.');return
        x1,y1,x2,y2=self.crop_box
        if (x2-x1)*(y2-y1)>12_000_000:
            messagebox.showinfo('Phóng to thêm','Vùng xem vượt 12 triệu pixel; phóng to để kiểm tra nét ở độ phân giải gốc.');return
        try:params=self._parameters();coefficients=self._get_geo()
        except Exception as exc:messagebox.showerror('Thông số',str(exc));return
        self.lbl_status.configure(text='Đang kiểm tra tâm nét trong vùng xem…')
        def work():
            rgb=np.array(self.pil_img.crop((x1,y1,x2,y2)).convert('RGB'))
            _,records,_=extract_patch(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),params,coefficients,(x1,y1),self.stop_event)
            return records
        def done(records):
            self.preview_records=records;self.render_viewport()
            self.lbl_status.configure(text=f'Preview: {len(records)} đoạn ứng viên; chưa thay thế kết quả toàn bản đồ.')
        self._start_worker(work,done)

    def run_full_map_extraction_thread(self):
        if self._warn_busy():return
        if self.pil_img is None:messagebox.showinfo('Chưa có ảnh','Mở ảnh trước.');return
        if self.extracted_contours and not messagebox.askyesno('Thay kết quả','Số hóa lại sẽ thay toàn bộ đường đang chỉnh. Tiếp tục?'):return
        try:params=self._parameters();coefficients=self._get_geo()
        except Exception as exc:messagebox.showerror('Thông số',str(exc));return
        if params['close_radius']>0 and not messagebox.askyesno('Nguy cơ dính nét',
                'Đang bật hàn nét. Hai đường đồng mức gần nhau có thể bị nối nhầm. Tiếp tục?'):return
        self.lbl_status.configure(text='Đang xử lý từng ô có vùng đệm; kết quả cũ được giữ đến khi chạy xong.')
        def done(records):
            self._snapshot();self.extracted_contours=records;self.preview_records=[];self.select_ids=set()
            self.dirty=True;self.progress_bar.set(1);self.render_viewport()
            self.lbl_status.configure(text=f'Hoàn tất {len(records)} đoạn tâm nét. Mở bảng đường để kiểm tra/gán Z trước khi xuất.')
        self._start_worker(lambda:self._run_full_map_tiled(params,coefficients),done)

    def _run_full_map_tiled(self,params,coefficients):
        return extract_tiled(self.pil_img,params,coefficients,self.stop_event,
            lambda value,text:self.event_queue.put(('progress',None,(value,text))))

    def _snapshot(self):
        self.history.append(copy.deepcopy(self.extracted_contours));self.history=self.history[-15:]

    def finish_manual_line(self):
        if self.busy or len(self.pending_points)<2:return
        if len(set(map(tuple,self.pending_points)))<2:return
        self._snapshot();record=record_from_pixels(self.pending_points,self._get_geo())
        self.extracted_contours.append(record);self.select_ids={len(self.extracted_contours)-1}
        self.pending_points=[];self.dirty=True;self.render_viewport()

    def _geo_field_changed(self,event=None):
        self.geo_confirmed=False;self.dirty=True

    def edit_at_point(self,px,py,event):
        try:
            if len(self.select_ids)!=1:
                raise ValueError('Chọn đúng 1 đường bằng công cụ Chọn đường trước.')
            index=next(iter(self.select_ids));record=self.extracted_contours[index]
            points=np.array(record['pixels']);scale=self.display_transform[2]
            distances=np.linalg.norm(points-[px,py],axis=1);nearest=int(distances.argmin())
            if self.tool_mode.get()=='Cắt đường':
                # Cut at the closest segment instead of requiring a vertex near the click.
                segment=min(range(len(points)-1),key=lambda i:LineString(points[i:i+2]).distance(Point(px,py)))
                edge=LineString(points[segment:segment+2]);point=edge.interpolate(edge.project(Point(px,py)))
                if edge.distance(Point(px,py))*scale>12:raise ValueError('Bấm gần đoạn muốn cắt.')
                middle=[point.x,point.y]
                first=record['pixels'][:segment+1]+[middle];second=[middle]+record['pixels'][segment+1:]
                if LineString(first).length<1e-6 or LineString(second).length<1e-6:raise ValueError('Điểm cắt quá gần đầu mút.')
                self._snapshot()
                self.extracted_contours[index]=record_from_pixels(first,self._get_geo(),record['ELEVATION'])
                self.extracted_contours.append(record_from_pixels(second,self._get_geo(),record['ELEVATION']))
            elif event.state & 0x0001:
                segment=min(range(len(points)-1),key=lambda i:LineString(points[i:i+2]).distance(Point(px,py)))
                if LineString(points[segment:segment+2]).distance(Point(px,py))*scale>12:raise ValueError('Shift+bấm gần đoạn cần chèn đỉnh.')
                self._snapshot();record['pixels'].insert(segment+1,[px,py]);record['REVIEWED']=False
            else:
                if distances[nearest]*scale>12:raise ValueError('Bấm gần đỉnh để kéo; Shift+bấm lên đoạn để chèn đỉnh.')
                self._snapshot();self.drag_vertex=(index,nearest)
            self.dirty=True;self.render_viewport()
        except Exception as exc:messagebox.showinfo('Sửa đường',str(exc))

    def on_vertex_drag(self,event):
        if self.drag_vertex is None or self.busy:return
        point=self._canvas_to_image(event.x,event.y)
        if point is None:return
        index,vertex=self.drag_vertex;record=self.extracted_contours[index]
        closed=np.allclose(record['pixels'][0],record['pixels'][-1],rtol=0,atol=1e-8)
        record['pixels'][vertex]=list(point)
        if closed and vertex in (0,len(record['pixels'])-1):
            record['pixels'][0]=list(point);record['pixels'][-1]=list(point)
        record['REVIEWED']=False;self.dirty=True;self.render_viewport()

    def on_vertex_release(self,event):self.drag_vertex=None

    def delete_vertex(self,event=None):
        if self.busy or self.tool_mode.get()!='Sửa đỉnh' or len(self.select_ids)!=1 or not self.last_mouse:return
        point=self._canvas_to_image(*self.last_mouse)
        if point is None:return
        index=next(iter(self.select_ids));record=self.extracted_contours[index];points=np.array(record['pixels'])
        distance=np.linalg.norm(points-point,axis=1);vertex=int(distance.argmin())
        if distance[vertex]*self.display_transform[2]>12:return
        closed=np.allclose(points[0],points[-1],rtol=0,atol=1e-8)
        if len(points)<=(4 if closed else 2):return
        self._snapshot()
        if closed and vertex in (0,len(points)-1):record['pixels']=record['pixels'][1:-1]+[record['pixels'][1].copy()]
        else:record['pixels'].pop(vertex)
        record['REVIEWED']=False;self.dirty=True;self.render_viewport()

    def cancel_manual_line(self):self.pending_points=[];self.render_viewport()

    def backspace_manual_line(self):
        if self.pending_points:self.pending_points.pop();self.render_viewport()

    def open_result_table(self):
        if self._warn_busy():return
        dialog=ctk.CTkToplevel(self);dialog.title('Đường đồng mức — kiểm tra, chỉnh sửa & cao độ');dialog.geometry('980x660')
        dialog.transient(self)
        tree=ttk.Treeview(dialog,columns=('id','z','check','n','note'),show='headings',selectmode='extended')
        for key,title,width in [('id','#',50),('z','Z (m)',110),('check','Đã kiểm tra',120),('n','Số đỉnh',100),('note','Ghi chú',380)]:
            tree.heading(key,text=title);tree.column(key,width=width)
        tree.pack(fill='both',expand=True,padx=10,pady=10)
        scrollbar=ttk.Scrollbar(tree,orient='vertical',command=tree.yview);scrollbar.pack(side='right',fill='y');tree.configure(yscrollcommand=scrollbar.set)
        status=ctk.CTkLabel(dialog,text='Ctrl/Shift chọn nhiều dòng. Cao độ chưa biết được để trống.');status.pack()
        def refresh():
            tree.delete(*tree.get_children())
            for i,r in enumerate(self.extracted_contours):
                tree.insert('','end',iid=str(i),values=(i+1,'—' if r['ELEVATION'] is None else f"{r['ELEVATION']:.3f}",
                    'Có' if r.get('REVIEWED') else 'Chưa',len(r['pixels']),'Đầu mút ngã rẽ' if r.get('BRANCH') else ''))
        def chosen():
            ids=list(map(int,tree.selection()))
            if not ids:raise ValueError('Chọn đường trong bảng trước.')
            return ids
        def select(event=None):
            self.select_ids=set(map(int,tree.selection()));self.render_viewport()
        def zoom(event=None):
            ids=chosen();points=np.array([p for i in ids for p in self.extracted_contours[i]['pixels']])
            low=points.min(axis=0)-15;high=points.max(axis=0)+15
            self.view_x=max(0,float(low[0]));self.view_y=max(0,float(low[1]))
            self.view_w=min(self.img_width-self.view_x,max(20,float(high[0]-low[0])))
            self.view_h=min(self.img_height-self.view_y,max(20,float(high[1]-low[1])));self.render_viewport()
        def guard(fn):
            try:
                if self.busy:raise ValueError('Đang xử lý; chờ hoàn tất.')
                fn()
            except Exception as exc:messagebox.showerror('Chỉnh đường',str(exc),parent=dialog)
        def assign():
            ids=chosen();z=simpledialog.askstring('Cao độ','Cao độ Z (m) đã đọc từ bản đồ:',parent=dialog,initialvalue=self.ent_default_z.get())
            if z is None:return
            z=finite_number(z);self._snapshot()
            for i in ids:self.extracted_contours[i]['ELEVATION']=z;self.extracted_contours[i]['REVIEWED']=False
            self.dirty=True;refresh();self.render_viewport()
        def review():
            ids=chosen()
            if any(self.extracted_contours[i]['ELEVATION'] is None for i in ids):raise ValueError('Gán cao độ đúng trước khi xác nhận.')
            if not messagebox.askyesno('Xác nhận',f'Đã đối chiếu hình học và cao độ {len(ids)} đường với bản gốc?',parent=dialog):return
            self._snapshot()
            for i in ids:self.extracted_contours[i]['REVIEWED']=True
            self.dirty=True;refresh();self.render_viewport()
        def delete():
            ids=chosen()
            if not messagebox.askyesno('Xóa đoạn',f'Xóa {len(ids)} đoạn đã chọn?',parent=dialog):return
            self._snapshot();self.extracted_contours=[r for i,r in enumerate(self.extracted_contours) if i not in ids]
            self.select_ids=set();self.dirty=True;refresh();self.render_viewport()
        def join():
            ids=chosen()
            if len(ids)!=2:raise ValueError('Chọn đúng 2 đoạn để nối.')
            a,b=[self.extracted_contours[i] for i in ids]
            if a['ELEVATION'] is not None and b['ELEVATION'] is not None and a['ELEVATION']!=b['ELEVATION']:raise ValueError('Cao độ khác nhau; không nối.')
            if any(np.allclose(r['pixels'][0],r['pixels'][-1],rtol=0,atol=1e-8) for r in (a,b)):raise ValueError('Không nối đường đã khép kín.')
            distance,i,j=min((float(np.linalg.norm(np.array(a['pixels'][i])-b['pixels'][j])),i,j) for i in (0,-1) for j in (0,-1))
            if distance>12:raise ValueError(f'Hai đầu cách {distance:.2f} px >12 px; vẽ bổ sung hoặc kiểm tra đường đã chọn.')
            if not messagebox.askyesno('Nối có kiểm soát',f'Hai đầu cách {distance:.2f} px. Đã kiểm tra đây là cùng một đường đồng mức?',parent=dialog):return
            self._snapshot();first=a['pixels'][::-1] if i==0 else a['pixels'];second=b['pixels'][::-1] if j==-1 else b['pixels']
            a['pixels']=first+(second[1:] if distance<1e-8 else second)
            a['ELEVATION']=a['ELEVATION'] if a['ELEVATION'] is not None else b['ELEVATION'];a['REVIEWED']=False
            del self.extracted_contours[ids[1]];self.select_ids=set();self.dirty=True;refresh();self.render_viewport()
        def qa():
            problems=validate_records(self.extracted_contours)
            self._show_text('Kiểm tra chất lượng',f'{len(problems)} mục cần xem:\n\n'+'\n'.join(f'#{i+1}: {msg}' for i,msg in problems[:5000])+
                '\n\nKiểm tra tự động không thay thế đối chiếu bản đồ gốc.')
        def use_preview():
            if not self.preview_records:raise ValueError('Chưa có Preview.')
            if not messagebox.askyesno('Thêm Preview','Thêm các đoạn Preview vào danh sách chính? Có thể trùng vùng đã số hóa.',parent=dialog):return
            self._snapshot();self.extracted_contours.extend(copy.deepcopy(self.preview_records));self.preview_records=[]
            self.dirty=True;refresh();self.render_viewport()
        def undo():
            if self.history:self.extracted_contours=self.history.pop();self.select_ids=set();self.dirty=True;refresh();self.render_viewport()
        tools=ctk.CTkFrame(dialog);tools.pack(fill='x',padx=10,pady=8)
        for label,fn in [('Gán Z',assign),('Xác nhận',review),('Xóa đoạn',delete),('Nối 2 đoạn',join),('Undo',undo),('Kiểm tra',qa),('Nhận Preview',use_preview)]:
            ctk.CTkButton(tools,text=label,width=110,command=lambda f=fn:guard(f)).pack(side='left',padx=3)
        tree.bind('<<TreeviewSelect>>',select);tree.bind('<Double-1>',lambda e:guard(zoom));refresh()

    def _export_records(self):
        if self._warn_busy():raise ValueError('Chờ xử lý hoàn tất.')
        selected=[r for r in self.extracted_contours if r.get('REVIEWED')]
        if not selected:raise ValueError('Mở Bảng đường, gán Z và xác nhận kiểm tra các đường cần xuất trước.')
        if any(r['ELEVATION'] is None for r in selected):raise ValueError('Đường chưa có cao độ; không tự gán 0/10 m.')
        coefficients=self._get_geo(required=True)
        crs_text=self.ent_epsg.get().strip()
        if not crs_text:raise ValueError('Khai báo EPSG hoặc WKT chính xác, không tự đoán múi VN-2000.')
        crs=CRS.from_user_input(int(crs_text) if crs_text.isdigit() else crs_text)
        if not crs.is_projected or abs(crs.axis_info[0].unit_conversion_factor-1)>1e-9:
            raise ValueError('Xuất CAD/GIS này cần CRS phẳng đơn vị mét. Không gán tọa độ mét cho EPSG:4326.')
        return [record_from_pixels(r['pixels'],coefficients,finite_number(r['ELEVATION']),r.get('BRANCH',False)) for r in selected],crs

    def export_dxf(self):
        try:
            records,crs=self._export_records()
            path=filedialog.asksaveasfilename(title='DXF 3D chỉ gồm đường đã kiểm tra',defaultextension='.dxf',filetypes=[('DXF 3D','*.dxf')])
            if not path:return
            doc=ezdxf.new('R2013');doc.units=6;space=doc.modelspace()
            for record in records:
                z=record['ELEVATION'];layer=f'DM_{z:g}'.replace('.','_').replace('-','AM')
                if layer not in doc.layers:doc.layers.new(layer,dxfattribs={'color':30})
                coords=list(record['geometry'].coords)
                space.add_polyline3d(coords,close=np.allclose(coords[0],coords[-1],rtol=0,atol=1e-8),dxfattribs={'layer':layer})
            doc.saveas(path)
            with open(os.path.splitext(path)[0]+'.prj','w',encoding='utf-8') as f:f.write(crs.to_wkt())
            messagebox.showinfo('Đã xuất',f'{len(records)} đường 3D; đơn vị mét. DXF kèm PRJ. Cao độ giữ theo hệ bạn nhập.')
        except Exception as exc:messagebox.showerror('Xuất DXF',str(exc))

    def export_shapefile(self):
        try:
            import shapefile
            records,crs=self._export_records()
            path=filedialog.asksaveasfilename(title='SHP Polyline Z',defaultextension='.shp',filetypes=[('SHP Z','*.shp')])
            if not path:return
            base=os.path.splitext(path)[0]
            with shapefile.Writer(base,shapeType=shapefile.POLYLINEZ,encoding='utf-8') as writer:
                writer.field('ID','N',10);writer.field('ELEVATION','F',18,3);writer.field('LENGTH_M','F',20,3)
                for i,record in enumerate(records):
                    writer.linez([list(record['geometry'].coords)])
                    writer.record(i+1,record['ELEVATION'],record['LENGTH_M'])
            with open(base+'.prj','w',encoding='utf-8') as f:f.write(crs.to_wkt(version='WKT1_ESRI'))
            with open(base+'.cpg','w',encoding='ascii') as f:f.write('UTF-8')
            messagebox.showinfo('Đã xuất',f'{len(records)} đường SHP Z. Giữ đủ SHP/SHX/DBF/PRJ/CPG cùng thư mục.')
        except Exception as exc:messagebox.showerror('Xuất SHP',str(exc))

    def add_gcp(self,px,py):
        try:
            x=simpledialog.askstring('Điểm khống chế',f'Pixel ({px:.2f}, {py:.2f}) — X / Easting:',parent=self)
            if x is None:return
            y=simpledialog.askstring('Điểm khống chế','Y / Northing:',parent=self)
            if y is None:return
            check=messagebox.askyesno('Loại điểm','Dùng làm điểm KIỂM TRA độc lập, không tham gia nắn?\nChọn No để dùng làm điểm nắn.')
            self.gcps.append(dict(px=px,py=py,x=finite_number(x),y=finite_number(y),check=check))
            self.dirty=True;self.render_viewport()
        except Exception as exc:messagebox.showerror('Điểm nắn',str(exc))

    def open_gcp_editor(self):
        if self._warn_busy():return
        dialog=ctk.CTkToplevel(self);dialog.title('Nắn affine theo điểm khống chế');dialog.geometry('780x520')
        tree=ttk.Treeview(dialog,columns=('id','px','py','x','y','role'),show='headings')
        for key,label in [('id','#'),('px','Pixel X'),('py','Pixel Y'),('x','Easting'),('y','Northing'),('role','Vai trò')]:
            tree.heading(key,text=label);tree.column(key,width=110)
        tree.pack(fill='both',expand=True,padx=10,pady=10)
        def refresh():
            tree.delete(*tree.get_children())
            for i,p in enumerate(self.gcps):tree.insert('','end',iid=str(i),values=(i+1,f"{p['px']:.2f}",f"{p['py']:.2f}",p['x'],p['y'],'KT' if p['check'] else 'Nắn'))
        def add():self.tool_mode.set('Điểm nắn');self.set_tool('Điểm nắn');dialog.destroy()
        def delete():
            self.gcps=[p for i,p in enumerate(self.gcps) if str(i) not in tree.selection()];self.dirty=True;refresh();self.render_viewport()
        def fit():
            try:
                rows=[p for p in self.gcps if not p['check']]
                if len(rows)<3:raise ValueError('Cần ≥3 điểm nắn không thẳng hàng, thêm điểm KT độc lập.')
                src=np.array([[p['px'],p['py']] for p in rows]);target=np.array([[p['x'],p['y']] for p in rows])
                center=src.mean(axis=0);scale=max(float(src.std()),1e-9)
                design=np.column_stack(((src-center)/scale,np.ones(len(src))))
                if np.linalg.matrix_rank(design)<3:raise ValueError('Điểm nắn thẳng hàng; chọn điểm quanh ảnh.')
                coef=np.linalg.lstsq(design,target,rcond=None)[0]
                linear=coef[:2]/scale;origin=coef[2]-center@linear
                if abs(np.linalg.det(linear))<1e-12:raise ValueError('Tọa độ đích suy biến; kiểm tra X/Y.')
                coefficients=(linear[0,0],linear[0,1],linear[1,0],linear[1,1],origin[0],origin[1])
                residuals=[]
                for p in self.gcps:
                    predicted=image_to_world([[p['px'],p['py']]],coefficients)[0]
                    residuals.append(float(np.linalg.norm(predicted-[p['x'],p['y']])))
                unit='đơn vị CRS';crs_text=self.ent_epsg.get().strip()
                if crs_text:
                    crs=CRS.from_user_input(int(crs_text) if crs_text.isdigit() else crs_text);unit=crs.axis_info[0].unit_name
                self.world_coefficients=coefficients
                size=math.hypot(coefficients[0],coefficients[1])
                for entry,value in [(self.ent_x_origin,origin[0]),(self.ent_y_origin,origin[1]),(self.ent_pixel_size,size)]:
                    entry.delete(0,'end');entry.insert(0,repr(float(value)))
                self.world_signature=(float(origin[0]),float(origin[1]),size);self.geo_confirmed=True;self.dirty=True
                self.gcp_fit_signature=json.dumps(self.gcps,sort_keys=True)
                train=[v for p,v in zip(self.gcps,residuals) if not p['check']];checks=[v for p,v in zip(self.gcps,residuals) if p['check']]
                text=f"RMSE điểm nắn: {np.sqrt(np.mean(np.square(train))):.3f} {unit}.\n"
                text+=f"RMSE KT: {np.sqrt(np.mean(np.square(checks))):.3f} {unit}.\n" if checks else 'Chưa có điểm kiểm tra độc lập.\n'
                text+='\n'.join(f"#{i+1}: {v:.3f} {unit}" for i,v in enumerate(residuals))
                self._show_text('Sai số nắn ảnh',text+'\n\nKhớp 3 điểm tối thiểu không chứng minh độ chính xác toàn bản đồ.')
            except Exception as exc:messagebox.showerror('Nắn ảnh',str(exc),parent=dialog)
        bar=ctk.CTkFrame(dialog);bar.pack(fill='x',padx=10,pady=8)
        for label,fn in [('Bấm thêm điểm trên ảnh',add),('Xóa điểm',delete),('Tính nắn affine',fit)]:ctk.CTkButton(bar,text=label,command=fn).pack(side='left',padx=5)
        refresh()

    def _show_text(self,title,text):
        dialog=ctk.CTkToplevel(self);dialog.title(title);dialog.geometry('850x650')
        box=ctk.CTkTextbox(dialog,wrap='word');box.pack(fill='both',expand=True,padx=10,pady=10)
        box.insert('1.0',text);box.configure(state='disabled')

    def show_help(self):
        self._show_text('Hướng dẫn / giới hạn độ chính xác',
            '1. Mở ảnh gốc, phóng to tới nhìn rõ nét. Lấy nhiều mẫu đúng giữa nét nâu. Không lấy nền vàng hoặc chữ đen.\n\n'
            '2. HSV là cửa lọc rộng, Lab giúp phân biệt màu nét/nền. V tối thiểu loại chữ đen, V tối đa loại nền sáng. '
            'Mẫu loại bỏ dùng cho đường/ký hiệu khác màu. Các đối tượng CÙNG MÀU vẫn cần kiểm tra/xóa thủ công.\n\n'
            '3. Hàn nét mặc định TẮT để không nối hai đường cạnh nhau. Tăng lên 1–2 px có nguy cơ dính nét. '
            'Đơn giản hóa là giới hạn sai lệch pixel, không phải làm mượt spline. Chữ chắn nét có thể tạo đầu hở: không tự nối qua chữ.\n\n'
            '4. Preview chỉ hiển thị ứng viên, không ghi đè kết quả toàn bản đồ. Bảng đường → Nhận Preview để đưa vào danh sách. '
            'Chạy toàn bộ theo ô có vùng đệm, chỉ ghi vùng lõi rồi truy vết toàn ảnh để tránh trùng vùng chồng lấn. '
            'Ảnh lớn có thể vẫn cần RAM đáng kể khi giải mã nguồn và truy vết; giới hạn 120 triệu pixel/mảnh.\n\n'
            '5. Bảng đường: bấm đúp phóng tới đoạn; Ctrl/Shift chọn nhiều; xóa nét sai, nối đúng hai đoạn (tối đa 12 pixel), '
            'hoặc Vẽ tay / Dò theo điểm bổ sung đường. Enter kết thúc, Esc hủy, Backspace lùi đỉnh. Dò theo điểm cần '
            'các điểm gần nhau trên cùng nét; không chấp nhận đoạn rời nét quá 4 pixel. '
            'Chọn một đường rồi Sửa đỉnh: kéo đỉnh, Shift+bấm chèn, Delete xóa đỉnh gần chuột. '
            'Cắt đường: bấm lên đoạn để tách đôi. Undo trong bảng khôi phục chỉnh sửa. '
            'Tại ngã rẽ chương trình tách đoạn, không đoán hướng đi tiếp.\n\n'
            '6. Cao độ không được tự suy từ màu/độ đậm. Đọc nhãn, gán Z theo mét và xác nhận đã kiểm tra. '
            'Cao độ chưa biết giữ trống, không gán mặc định 10 m cho tất cả đường. '
            'DXF/SHP Z chỉ xuất đường đã xác nhận. Hệ cao độ giữ theo số nhập, không chuyển hệ cao độ.\n\n'
            '7. Nạp World File giữ đủ 6 hệ số (A,D,B,E,C,F), tọa độ tại tâm pixel. Nếu chưa có, dùng điểm nắn affine ≥3 điểm '
            '(nên ≥6 phân bố quanh ảnh) và thêm điểm KIỂM TRA độc lập. Affine không sửa được ảnh chụp phối cảnh hoặc giấy co giãn cục bộ; '
            'cần nắn ảnh chuyên dụng/chia mảnh trước trong trường hợp đó. EPSG phải đúng múi và kinh tuyến trục, không tự đoán VN-2000.\n\n'
            '8. Lưu dự án giữ tham chiếu ảnh gốc, mẫu màu, tham số, điểm nắn và đường; khi chuyển máy cần mang ảnh gốc theo. '
            'Phần mềm không thực thi mã trong file dự án JSON.\n\n'
            'Không có thuật toán tự động nào bảo đảm đúng 100% trên bản đồ giấy. Độ chính xác phụ thuộc tỷ lệ, scan, nét in, '
            'điểm nắn và kiểm tra thực tế. Chưa có ảnh bản đồ gốc đi kèm để đánh giá định lượng trên bản đồ của bạn.')

    def project_menu(self):
        if self._warn_busy():return
        dialog=ctk.CTkToplevel(self);dialog.title('Dự án số hóa');dialog.geometry('360x180')
        ctk.CTkButton(dialog,text='Lưu dự án…',command=lambda:(dialog.destroy(),self.save_project())).pack(fill='x',padx=20,pady=20)
        ctk.CTkButton(dialog,text='Mở dự án…',command=lambda:(dialog.destroy(),self.load_project())).pack(fill='x',padx=20,pady=5)

    def save_project(self):
        if self._warn_busy():return
        if self.pil_img is None:return
        path=filedialog.asksaveasfilename(defaultextension='.topocontour.json',filetypes=[('Dự án','*.json')])
        if not path:return
        try:
            params=self._parameters()
            data=dict(version=2,image=os.path.relpath(self.image_path,os.path.dirname(path)),size=[self.img_width,self.img_height],
                      source_bytes=os.path.getsize(self.image_path),params=params,geo=list(self._get_geo()),
                      has_geo=bool(self.ent_x_origin.get().strip() and self.ent_y_origin.get().strip() and self.ent_pixel_size.get().strip()),
                      crs=self.ent_epsg.get(),gcps=self.gcps,gcp_fit_signature=self.gcp_fit_signature,
                      records=[{k:v for k,v in r.items() if k!='geometry'} for r in self.extracted_contours])
            with open(self.image_path,'rb') as original:data['source_sha256']=hashlib.file_digest(original,'sha256').hexdigest()
            fd,temp=tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),suffix='.tmp');os.close(fd)
            try:
                with open(temp,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,allow_nan=False)
                os.replace(temp,path)
            finally:
                if os.path.exists(temp):os.unlink(temp)
            self.project_path=path;self.dirty=False;self.lbl_status.configure(text='Đã lưu dự án JSON; giữ ảnh gốc cùng thư mục khi chuyển máy.')
        except Exception as exc:messagebox.showerror('Lưu dự án',str(exc))

    def load_project(self):
        if self._warn_busy():return
        if self.dirty and not messagebox.askyesno('Mở dự án','Bỏ thay đổi chưa lưu?'):return
        path=filedialog.askopenfilename(filetypes=[('Dự án JSON','*.json')])
        if not path:return
        try:
            if os.path.getsize(path)>200_000_000:raise ValueError('JSON dự án quá lớn (>200 MB).')
            with open(path,encoding='utf-8') as f:data=json.load(f)
            if data.get('version')!=2:raise ValueError('Phiên bản dự án không hỗ trợ.')
            image=os.path.normpath(os.path.join(os.path.dirname(path),data['image']))
            if not os.path.isfile(image):
                image=filedialog.askopenfilename(title='Chọn lại đúng ảnh gốc của dự án')
                if not image:return
            with Image.open(image) as im:
                if list(im.size)!=data['size'] or os.path.getsize(image)!=data['source_bytes']:
                    raise ValueError('Ảnh không khớp kích thước/dung lượng nguồn. Không áp đường lên ảnh khác.')
            with open(image,'rb') as original:
                if hashlib.file_digest(original,'sha256').hexdigest()!=data.get('source_sha256'):
                    raise ValueError('Ảnh gốc khác nội dung (SHA-256 không khớp). Chọn đúng ảnh đã lưu dự án.')
            geo=[finite_number(v) for v in data['geo']]
            if len(geo)!=6 or abs(geo[0]*geo[3]-geo[2]*geo[1])<1e-15:raise ValueError('Phép nắn không hợp lệ.')
            records=[]
            for r in data['records']:
                pts=np.array(r['pixels'],dtype=float)
                if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<2 or not np.isfinite(pts).all():raise ValueError('Đường có tọa độ không hợp lệ.')
                z=None if r['ELEVATION'] is None else finite_number(r['ELEVATION'])
                record=record_from_pixels(pts,geo,z,r.get('BRANCH',False));record['REVIEWED']=bool(r.get('REVIEWED',False));records.append(record)
            self._install_image(image)
            self.extracted_contours=records;self.gcps=data.get('gcps',[])
            self.gcp_fit_signature=data.get('gcp_fit_signature')
            if data['has_geo']:
                self.world_coefficients=tuple(geo);size=math.hypot(geo[0],geo[1])
                for entry,value in [(self.ent_x_origin,geo[4]),(self.ent_y_origin,geo[5]),(self.ent_pixel_size,size)]:entry.delete(0,'end');entry.insert(0,repr(value))
                self.world_signature=(geo[4],geo[5],size);self.geo_confirmed=True
            self.ent_epsg.insert(0,data['crs']);params=data['params']
            self.positive_samples=params['positive'];self.negative_samples=params['negative']
            for slider,key in [(self.slider_h_min,'h_min'),(self.slider_h_max,'h_max'),(self.slider_s_min,'s_min'),
                               (self.slider_v_min,'v_min'),(self.slider_v_max,'v_max'),(self.slider_tol,'tolerance'),
                               (self.slider_contrast,'contrast'),(self.slider_close_gap,'close_radius'),
                               (self.slider_min_len,'min_length'),(self.slider_simplify,'simplify')]:self._set_slider(slider,params[key])
            self.sample_info.configure(text=f'{len(self.positive_samples)} mẫu nét; {len(self.negative_samples)} mẫu loại.')
            self.project_path=path;self.dirty=False;self.render_viewport();self.lbl_status.configure(text=f'Đã mở dự án: {len(records)} đường.')
        except Exception as exc:messagebox.showerror('Mở dự án',str(exc))

    def on_close(self):
        if self.busy:
            messagebox.showinfo('Đang xử lý','Nhấn Dừng, chờ hoàn tất rồi đóng phần mềm.');return
        if self.dirty and not messagebox.askyesno('Đóng','Dự án chưa lưu. Đóng và bỏ thay đổi?'):return
        if self.pil_img:self.pil_img.close()
        self.destroy()


if __name__ == "__main__":
    app = TopoContourDigitizerApp()
    app.mainloop()
