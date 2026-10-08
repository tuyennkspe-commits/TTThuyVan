import math
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import cv2
import geopandas as gpd
import numpy as np
from PIL import Image, ImageTk
import pymupdf as fitz
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.ops import linemerge
from skimage.morphology import skeletonize


class ProfessionalTopoDigitizerApp:

  def __init__(self, root):
    self.root = root
    self.root.title(
        "Hệ Thống Số Hóa Bản Đồ Địa Hình & Gán Cao Độ 3D Hàng Loạt (Transect"
        " Engine)"
    )
    self.root.geometry("1300x880")

    self.input_file = ""
    self.dpi = 200

    self.orig_image = None
    self.tk_image = None
    self.scale = 1.0

    # Dữ liệu hình học
    # Mỗi phần tử: {'id': int, 'coords': [(x,y)], 'elevation': float, 'line_geom': LineString}
    self.contour_features = []

    # Biến tương tác đường cắt gán cao độ (Transect Tagging)
    self.mode = tk.StringVar(value="VIEW")  # 'VIEW' hoặc 'TRANSECT'
    self.transect_pts = []

    self._build_ui()

  def _build_ui(self):
    # --- THANH CÔNG CỤ ĐIỀU KHIỂN CHÍNH ---
    tb1 = ttk.Frame(self.root, padding=6)
    tb1.pack(side="top", fill="x")

    ttk.Button(
        tb1, text="📁 1. Mở Bản Đồ", command=self._load_file
    ).pack(side="left", padx=4)

    self.btn_auto = ttk.Button(
        tb1,
        text="⚡ 2. Tự Động Số Hóa & Hàn Nối",
        command=self._start_auto_digitize,
    )
    self.btn_auto.pack(side="left", padx=6)

    ttk.Separator(tb1, orient="vertical").pack(
        side="left", fill="y", padx=8, pady=2
    )

    # Nút chuyển chế độ kẻ đường cắt gán cao độ
    self.btn_transect = ttk.Button(
        tb1,
        text="📏 3. Kẻ Đường Cắt Gán Cao Độ Hàng Loạt",
        command=self._enable_transect_mode,
    )
    self.btn_transect.pack(side="left", padx=6)

    ttk.Button(
        tb1, text="💾 4. Xuất Shapefile 3D (Có Z)", command=self._save_shapefile
    ).pack(side="left", padx=6)

    # Nút Thu phóng
    ttk.Button(
        tb1, text="➕", width=3, command=lambda: self._zoom(1.25)
    ).pack(side="left", padx=2)
    ttk.Button(
        tb1, text="➖", width=3, command=lambda: self._zoom(0.8)
    ).pack(side="left", padx=2)
    ttk.Button(tb1, text="↺ Vừa khung", command=self._fit_to_screen).pack(
        side="left", padx=2
    )

    # --- THANH HƯỚNG DẪN THAO TÁC NHANH ---
    tb2 = ttk.Frame(self.root, padding=(6, 2))
    tb2.pack(side="top", fill="x")

    self.lbl_guide = ttk.Label(
        tb2,
        text=(
            "Cách gán cao độ hàng loạt: Bấm nút '📏 3. Kẻ Đường Cắt' -> Click"
            " chuột điểm đầu (chân đồi) -> Click điểm cuối (đỉnh đồi) -> Nhập"
            " Z đầu, Z cuối, khoảng cao đều."
        ),
        foreground="#004d40",
        font=("Segoe UI", 9, "bold"),
    )
    self.lbl_guide.pack(side="left", padx=4)

    self.prog = ttk.Progressbar(tb2, mode="indeterminate", length=130)
    self.prog.pack(side="right", padx=8)

    # --- KHU VỰC VẼ CHÍNH CANVAS ---
    c_frame = ttk.Frame(self.root)
    c_frame.pack(fill="both", expand=True)

    self.canvas = tk.Canvas(
        c_frame, bg="#202020", cursor="cross", highlightthickness=0
    )
    self.v_bar = ttk.Scrollbar(
        c_frame, orient="vertical", command=self.canvas.yview
    )
    self.h_bar = ttk.Scrollbar(
        c_frame, orient="horizontal", command=self.canvas.xview
    )

    self.canvas.configure(
        xscrollcommand=self.h_bar.set, yscrollcommand=self.v_bar.set
    )
    self.v_bar.pack(side="right", fill="y")
    self.h_bar.pack(side="bottom", fill="x")
    self.canvas.pack(side="left", fill="both", expand=True)

    self.lbl_status = ttk.Label(
        self.root,
        text="Sẵn sàng. Vui lòng mở tệp bản đồ.",
        relief="sunken",
        anchor="w",
        padding=5,
    )
    self.lbl_status.pack(side="bottom", fill="x")

    # Sự kiện chuột
    self.canvas.bind("<Button-1>", self._on_canvas_left_click)
    self.canvas.bind(
        "<ButtonPress-3>", lambda e: self.canvas.scan_mark(e.x, e.y)
    )
    self.canvas.bind(
        "<B3-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1)
    )
    self.canvas.bind("<MouseWheel>", self._on_mousewheel)
    self.root.bind("<Escape>", lambda e: self._cancel_current_action())

  def _load_file(self):
    path = filedialog.askopenfilename(
        title="Chọn bản đồ địa hình",
        filetypes=[
            ("Tất cả", "*.pdf;*.png;*.jpg;*.jpeg;*.tif"),
            ("PDF (*.pdf)", "*.pdf"),
            ("Ảnh", "*.png;*.jpg;*.jpeg;*.tif"),
        ],
    )
    if not path:
      return

    self.input_file = path
    ext = os.path.splitext(path)[-1].lower()

    try:
      self.lbl_status.config(text=f"Đang nạp: {os.path.basename(path)}...")
      self.root.update()

      if ext == ".pdf":
        doc = fitz.open(path)
        page = doc.load_page(0)
        scale = self.dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        self.orig_image = Image.frombytes(
            "RGB", (pix.width, pix.height), pix.samples
        )
        doc.close()
      else:
        self.orig_image = Image.open(path).convert("RGB")

      self.contour_features.clear()
      self.transect_pts.clear()
      self._fit_to_screen()
      self.lbl_status.config(
          text=(
              f"Đã mở tệp ({self.orig_image.width}x{self.orig_image.height}px)."
              " Hãy bấm nút '⚡ 2. Tự Động Số Hóa & Hàn Nối'."
          )
      )
    except Exception as ex:
      messagebox.showerror("Lỗi mở tệp", str(ex))

  def _fit_to_screen(self):
    if self.orig_image is None:
      return
    cw = self.canvas.winfo_width() or 1100
    ch = self.canvas.winfo_height() or 750
    self.scale = min(cw / self.orig_image.width, ch / self.orig_image.height)
    self._redraw()

  def _zoom(self, factor):
    if self.orig_image is None:
      return
    self.scale = max(0.15, min(self.scale * factor, 6.0))
    self._redraw()

  def _on_mousewheel(self, event):
    if event.delta > 0:
      self._zoom(1.15)
    else:
      self._zoom(0.85)

  def _enable_transect_mode(self):
    if not self.contour_features:
      messagebox.showwarning(
          "Chưa có dữ liệu",
          "Vui lòng bấm nút '⚡ 2. Tự Động Số Hóa & Hàn Nối' trước khi gán cao"
          " độ!",
      )
      return
    self.mode.set("TRANSECT")
    self.transect_pts.clear()
    self.lbl_status.config(
        text=(
            "CHẾ ĐỘ KẺ ĐƯỜNG CẮT: Click chuột trái vào điểm đầu (ví dụ: chân"
            " dốc)..."
        )
    )

  def _cancel_current_action(self):
    self.mode.set("VIEW")
    self.transect_pts.clear()
    self._redraw()
    self.lbl_status.config(text="Đã thoát chế độ kẻ đường cắt.")

  def _start_auto_digitize(self):
    if self.orig_image is None:
      messagebox.showwarning("Thông báo", "Vui lòng mở file bản đồ trước!")
      return

    self.btn_auto.config(state="disabled")
    self.prog.start(10)
    self.lbl_status.config(
        text=(
            "Đang xử lý: Bóc tách phổ nâu vi phân -> Tẩy chữ/Lưới -> Hàn mút"
            " tiếp tuyến -> Ghép liền mạch..."
        )
    )

    threading.Thread(target=self._run_digitize_and_stitch, daemon=True).start()

  def _bridge_lines(self, lines, max_gap=26.0):
    """Hàn nối các đoạn mút bị đứt gãy qua các vị trí chữ và lưới tọa độ."""
    if len(lines) < 2:
      return lines

    res_lines = list(lines)
    changed = True

    while changed:
      changed = False
      if len(res_lines) < 2:
        break

      endpoints = []
      for idx, pts in enumerate(res_lines):
        endpoints.append((pts[0][0], pts[0][1], idx, True))
        endpoints.append((pts[-1][0], pts[-1][1], idx, False))

      coords_arr = np.array([[p[0], p[1]] for p in endpoints])
      tree = cKDTree(coords_arr)
      pairs = tree.query_pairs(r=max_gap)

      merged_indices = set()
      new_lines = []

      sorted_pairs = sorted(
          pairs,
          key=lambda pr: math.hypot(
              coords_arr[pr[0]][0] - coords_arr[pr[1]][0],
              coords_arr[pr[0]][1] - coords_arr[pr[1]][1],
          ),
      )

      for i1, i2 in sorted_pairs:
        p1 = endpoints[i1]
        p2 = endpoints[i2]
        idx1, is_start1 = p1[2], p1[3]
        idx2, is_start2 = p2[2], p2[3]

        if idx1 == idx2 or idx1 in merged_indices or idx2 in merged_indices:
          continue

        pts1 = res_lines[idx1]
        pts2 = res_lines[idx2]

        if not is_start1 and is_start2:
          combined = pts1 + pts2
        elif is_start1 and not is_start2:
          combined = pts2 + pts1
        elif is_start1 and is_start2:
          combined = pts1[::-1] + pts2
        else:
          combined = pts1 + pts2[::-1]

        new_lines.append(combined)
        merged_indices.add(idx1)
        merged_indices.add(idx2)
        changed = True

      for idx, line in enumerate(res_lines):
        if idx not in merged_indices:
          new_lines.append(line)

      res_lines = new_lines

    return res_lines

  def _run_digitize_and_stitch(self):
    try:
      img_rgb = np.array(self.orig_image)
      img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
      h, w = img_bgr.shape[:2]

      # 1. Bóc tách tuyến đỏ công trình (KM1 -> KM13)
      hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
      m_red = cv2.inRange(
          hsv, np.array([0, 110, 80]), np.array([10, 255, 255])
      ) | cv2.inRange(hsv, np.array([165, 110, 80]), np.array([180, 255, 255]))
      red_dilated = cv2.dilate(
          m_red, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
      )

      # 2. Loại trừ chữ in đen và lưới tọa độ
      gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
      _, dark_px = cv2.threshold(gray, 85, 255, cv2.THRESH_BINARY_INV)
      dark_dilated = cv2.dilate(
          dark_px, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
      )

      # 3. Tính phổ vi phân cục bộ Δ(R - G) bắt trọn nét mảnh trong rừng
      smoothed = cv2.GaussianBlur(img_bgr, (3, 3), 0)
      r = smoothed[:, :, 2].astype(np.float32)
      g = smoothed[:, :, 1].astype(np.float32)
      b = smoothed[:, :, 0].astype(np.float32)

      diff_rg = r - g
      diff_rb = r - b
      bg_rg = cv2.GaussianBlur(diff_rg, (25, 25), 5.0)
      delta_rg = diff_rg - bg_rg

      # Bản đồ phản ứng nét bình đồ
      response = delta_rg + 0.3 * np.maximum(
          0.0, cv2.GaussianBlur(gray.astype(np.float32), (25, 25), 5.0) - gray
      )
      response[dark_dilated > 0] = -50.0
      response[red_dilated > 0] = -50.0
      response[diff_rb < -5.0] = -50.0
      response[r > 248] = -50.0

      # Nhị phân hóa
      binary = (response >= 9.0).astype(np.uint8) * 255
      closed = cv2.morphologyEx(
          binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
      )

      # 4. Rút mỏng về tim 1-pixel
      skel = skeletonize(closed > 0)
      skel_u8 = (skel * 255).astype(np.uint8)

      contours, _ = cv2.findContours(
          skel_u8, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
      )

      raw_lines = []
      for c in contours:
        if len(c) < 8:
          continue
        pts = [tuple(p[0]) for p in c]
        if LineString(pts).length >= 8.0:
          raw_lines.append(pts)

      # 5. Hàn nối khoảng hở do chữ/lưới
      stitched = self._bridge_lines(raw_lines, max_gap=26.0)

      # 6. Ghép các đoạn tiếp xúc thành đường dài liên tục (Linemerge)
      shapely_lines = [
          LineString(pts).simplify(1.0, preserve_topology=True)
          for pts in stitched
          if LineString(pts).length >= 15.0
      ]

      merged_res = linemerge(shapely_lines)
      if merged_res.geom_type == "LineString":
        final_shapely = [merged_res]
      else:
        final_shapely = list(merged_res.geoms)

      features = []
      for i, geom in enumerate(final_shapely):
        features.append({
            "id": i + 1,
            "coords": list(geom.coords),
            "elevation": 0.0,  # Chưa gán Z
            "line_geom": geom,
        })

      self.contour_features = features
      self.root.after(0, lambda: self._on_auto_completed(len(features)))

    except Exception as ex:
      self.root.after(0, lambda: messagebox.showerror("Lỗi xử lý", str(ex)))
    finally:
      self.root.after(0, self._reset_ui)

  def _on_auto_completed(self, count):
    self._redraw()
    self.lbl_status.config(
        text=(
            f"✔ ĐÃ SỐ HÓA & GHÉP NỐI THÀNH CÔNG {count} TUYẾN BÌNH ĐỒ! (Các"
            " đường màu tím nhạt là đường chưa có cao độ Z)."
        )
    )
    messagebox.showinfo(
        "Bước 1 hoàn tất",
        f"Đã trích xuất và hàn nối thành công {count} đường bình đồ liền"
        " mạch!\n\n"
        "BƯỚC TIẾP THEO (GÁN CAO ĐỘ HÀNG LOẠT):\n"
        "1. Bấm nút '📏 3. Kẻ Đường Cắt Gán Cao Độ Hàng Loạt'\n"
        "2. Click 1 điểm ở chân dốc, click 1 điểm ở đỉnh đồi\n"
        "3. Nhập cao độ đầu/cuối. Hệ thống sẽ tự động gán Z cho toàn bộ các"
        " đường nằm giữa.",
    )

  def _reset_ui(self):
    self.prog.stop()
    self.btn_auto.config(state="normal")

  def _on_canvas_left_click(self, event):
    if self.orig_image is None or self.mode.get() != "TRANSECT":
      return

    cx = self.canvas.canvasx(event.x)
    cy = self.canvas.canvasy(event.y)
    orig_x = cx / self.scale
    orig_y = cy / self.scale

    self.transect_pts.append((orig_x, orig_y))

    if len(self.transect_pts) == 1:
      self.lbl_status.config(
          text=(
              "Đã chọn điểm đầu (A). Hãy click chuột vào điểm kết thúc (B) ở sườn"
              " bên kia để cắt ngang qua các đường bình đồ."
          )
      )
      self._redraw()

    elif len(self.transect_pts) == 2:
      # Đã xác định xong đường cắt AB
      self._redraw()
      self._apply_transect_tagging(self.transect_pts[0], self.transect_pts[1])
      self.transect_pts.clear()
      self.mode.set("VIEW")

  def _apply_transect_tagging(self, pt_a, pt_b):
    """Tính toán giao điểm giữa đường cắt AB và các đường bình đồ, tự động gán cao độ Z hàng loạt."""
    cut_line = LineString([pt_a, pt_b])

    # Tìm các đường bình đồ giao cắt với cut_line
    intersected_items = []
    for feat in self.contour_features:
      geom = feat["line_geom"]
      if cut_line.intersects(geom):
        inter = cut_line.intersection(geom)
        # Lấy tọa độ điểm giao
        if inter.geom_type == "Point":
          d = cut_line.project(inter)  # Khoảng cách từ A đến điểm giao
          intersected_items.append((d, feat))
        elif inter.geom_type == "MultiPoint":
          for p in inter.geoms:
            d = cut_line.project(p)
            intersected_items.append((d, feat))

    if not intersected_items:
      messagebox.showwarning(
          "Không có giao điểm",
          "Đường cắt bạn vừa kẻ không giao cắt với đường bình đồ nào. Vui lòng"
          " kẻ lại!",
      )
      self._redraw()
      return

    # Sắp xếp các đường theo thứ tự từ điểm A đến điểm B dọc theo sườn dốc
    intersected_items.sort(key=lambda x: x[0])

    # Lọc bỏ trùng lặp nếu 1 đường uốn lượn cắt qua 2 lần
    unique_feats = []
    seen_ids = set()
    for d, feat in intersected_items:
      if feat["id"] not in seen_ids:
        unique_feats.append(feat)
        seen_ids.add(feat["id"])

    count = len(unique_feats)

    # Mở hộp thoại nhập thông số cao độ sườn dốc
    dialog = tk.Toplevel(self.root)
    dialog.title("Gán cao độ hàng loạt qua đường cắt")
    dialog.geometry("420x260")
    dialog.transient(self.root)
    dialog.grab_set()

    ttk.Label(
        dialog,
        text=(
            f"Đường cắt đi qua {count} đường bình đồ liên tiếp.\nVui lòng nhập"
            " cao độ sườn dốc:"
        ),
        font=("Segoe UI", 10, "bold"),
    ).pack(pady=10)

    f_in = ttk.Frame(dialog, padding=10)
    f_in.pack(fill="x")

    ttk.Label(f_in, text="Cao độ điểm đầu A (m):").grid(
        row=0, column=0, sticky="w", pady=4
    )
    e_start = ttk.Entry(f_in, width=12)
    e_start.grid(row=0, column=1, pady=4)
    e_start.insert(0, "50.0")

    ttk.Label(f_in, text="Cao độ điểm cuối B (m):").grid(
        row=1, column=0, sticky="w", pady=4
    )
    e_end = ttk.Entry(f_in, width=12)
    e_end.grid(row=1, column=1, pady=4)
    e_end.insert(0, str(50.0 + (count - 1) * 10.0))

    ttk.Label(f_in, text="Khoảng cao đều (m):").grid(
        row=2, column=0, sticky="w", pady=4
    )
    e_step = ttk.Entry(f_in, width=12)
    e_step.grid(row=2, column=1, pady=4)
    e_step.insert(0, "10.0")

    def confirm():
      try:
        z_start = float(e_start.get())
        z_end = float(e_end.get())
        step = float(e_step.get())

        # Gán cao độ lũy tiến theo chiều dốc
        sign = 1.0 if z_end >= z_start else -1.0
        for idx, feat in enumerate(unique_feats):
          elev_val = z_start + sign * (idx * step)
          feat["elevation"] = round(elev_val, 1)

        dialog.destroy()
        self._redraw()
        self.lbl_status.config(
            text=(
                f"✔ ĐÃ GÁN CAO ĐỘ THÀNH CÔNG CHO {count} ĐƯỜNG BÌNH ĐỒ! (Các"
                " đường đã có Z chuyển sang màu sắc phân tầng độ cao)."
            )
        )
        messagebox.showinfo(
            "Thành công",
            f"Đã gán cao độ chính xác từ {z_start}m đến"
            f" {z_start + sign * ((count - 1) * step)}m cho {count} đường bình"
            " đồ!",
        )
      except Exception as ex:
        messagebox.showerror("Lỗi dữ liệu", str(ex))

    ttk.Button(dialog, text="✔ XÁC NHẬN GÁN CAO ĐỘ", command=confirm).pack(
        pady=12, ipady=4
    )

  def _redraw(self):
    if self.orig_image is None:
      return

    nw = int(self.orig_image.width * self.scale)
    nh = int(self.orig_image.height * self.scale)

    resized = self.orig_image.resize((nw, nh), Image.Resampling.BILINEAR)
    self.tk_image = ImageTk.PhotoImage(resized)

    self.canvas.delete("all")
    self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)
    self.canvas.config(scrollregion=(0, 0, nw, nh))

    # Vẽ toàn bộ các đường bình đồ
    for feat in self.contour_features:
      elev = feat["elevation"]
      pts = feat["coords"]
      scaled = [(p[0] * self.scale, p[1] * self.scale) for p in pts]
      flat = [c for pt in scaled for c in pt]

      if len(flat) >= 4:
        # Đường chưa có Z: Màu tím nhạt
        if elev == 0.0:
          color = "#9c27b0"
          width = 1
        # Đường đã có Z: Phân tầng màu (Thấp = Xanh lục, Cao = Đỏ/Vàng)
        else:
          color = (
              "#00e676"
              if elev < 70
              else ("#ffea00" if elev < 100 else "#ff1744")
          )
          width = 2

        self.canvas.create_line(flat, fill=color, width=width)

        # Hiển thị nhãn cao độ trên bản vẽ nếu đã gán Z
        if elev > 0:
          mid_pt = scaled[len(scaled) // 2]
          self.canvas.create_text(
              mid_pt[0],
              mid_pt[1] - 8,
              text=f"{int(elev)}",
              fill="#ffffff",
              font=("Segoe UI", 9, "bold"),
          )

    # Vẽ đường cắt tương tác (Màu xanh dương nét đứt)
    if len(self.transect_pts) == 1:
      p = self.transect_pts[0]
      cx, cy = p[0] * self.scale, p[1] * self.scale
      self.canvas.create_oval(
          cx - 4, cy - 4, cx + 4, cy + 4, fill="#00e5ff", outline="#ffffff"
      )

  def _save_shapefile(self):
    if not self.contour_features:
      messagebox.showwarning(
          "Cảnh báo", "Chưa có dữ liệu đường bình đồ nào để xuất!"
      )
      return

    out_p = filedialog.asksaveasfilename(
        title="Lưu file Shapefile 3D chuẩn cao độ",
        defaultextension=".shp",
        filetypes=[("ESRI Shapefile (*.shp)", "*.shp")],
        initialfile="BinhDo_MaDa_Chuan3D_CoZ.shp",
    )
    if not out_p:
      return

    try:
      records = []
      assigned_count = 0

      for feat in self.contour_features:
        elev = feat["elevation"]
        if elev > 0:
          assigned_count += 1

        # TẠO TỌA ĐỘ HÌNH HỌC 3D THỰC SỰ: (X, -Y, Z)
        pts_3d = [(p[0], -p[1], elev) for p in feat["coords"]]
        geom_3d = LineString(pts_3d)

        records.append({
            "id": feat["id"],
            "elevation": elev,
            "has_z": 1 if elev > 0 else 0,
            "type": (
                "Index"
                if (elev > 0 and int(elev) % 50 == 0)
                else "Intermediate"
            ),
            "length_px": round(geom_3d.length, 2),
            "geometry": geom_3d,
        })

      gdf = gpd.GeoDataFrame(records)
      os.makedirs(os.path.dirname(out_p), exist_ok=True)
      # Xuất Shapefile kèm thông tin độ cao 3D thực
      gdf.to_file(out_p, driver="ESRI Shapefile", encoding="utf-8")

      messagebox.showinfo(
          "Xuất Shapefile 3D thành công",
          f"ĐÃ LƯU THÀNH CÔNG {len(records)} ĐƯỜNG BÌNH ĐỒ VÀO SHAPEFILE:\n{out_p}\n\n"
          f"• Có {assigned_count} đường đã mang giá trị cao độ Z thực tế (khác 0).\n"
          "• Định dạng hình học: Polyline ZM (3D).\n"
          "• Mở trong ArcGIS hoặc AutoCAD Civil 3D sẽ có ngay cao trình chuẩn!",
      )

    except Exception as ex:
      messagebox.showerror("Lỗi khi lưu Shapefile", str(ex))


if __name__ == "__main__":
  root = tk.Tk()
  app = ProfessionalTopoDigitizerApp(root)
  root.mainloop()