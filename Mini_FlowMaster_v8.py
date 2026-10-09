"""Thủy lực kênh hở theo Manning SI, chạy trong một file.
Cài thư viện: python -m pip install numpy scipy matplotlib
Phạm vi: dòng chảy đều, nhám đồng nhất, alpha=1; không thay thế mô hình nước dềnh.
Độ sâu tới hạn chọn cực tiểu năng lượng riêng trong phạm vi mặt cắt.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import json
import csv
from scipy.optimize import brentq, minimize_scalar

G = 9.81

def number(value, name):
    try:value=float(str(value).strip().replace(',', '.'))
    except ValueError:raise ValueError(f'{name}: cần nhập số.') from None
    if not np.isfinite(value):raise ValueError(f'{name}: số phải hữu hạn.')
    return value

def coordinates(text):
    rows=[]
    for index,line in enumerate(text.splitlines(),1):
        if not line.strip():continue
        parts=line.split(';') if ';' in line else line.split()
        if len(parts)==1 and ',' in line:parts=line.split(',')
        if len(parts)!=2:raise ValueError(f'Dòng {index}: cần đúng hai tọa độ X và Z; dùng tab, khoảng trắng hoặc dấu chấm phẩy.')
        rows.append([number(v,f'Tọa độ dòng {index}') for v in parts])
    points=np.asarray(rows,dtype=float)
    if len(rows)<3:raise ValueError('Cần ít nhất 3 điểm mô tả đáy và hai bờ.')
    if np.any(np.diff(points[:,0])<0) or points[-1,0]<=points[0,0]:raise ValueError('Tọa độ X phải tăng từ trái sang phải; chỉ cho phép X trùng để mô tả vách đứng.')
    if np.any(np.all(np.diff(points,axis=0)==0,axis=1)):raise ValueError('Có hai điểm liên tiếp trùng nhau.')
    if min(points[0,1],points[-1,1])<=points[:,1].min():raise ValueError('Hai đầu mặt cắt phải cao hơn điểm đáy thấp nhất.')
    return points

def section_properties(points, stage, walls=False):
    A=P=T=0.0
    for (x1,z1),(x2,z2) in zip(points[:-1],points[1:]):
        h1,h2=stage-z1,stage-z2
        if max(h1,h2)<=0:continue
        left,right=0.0,1.0
        if h1<0:left=-h1/(h2-h1)
        if h2<0:right=h1/(h1-h2)
        fraction=right-left
        dx=(x2-x1)*fraction
        A+=dx*(max(h1+(h2-h1)*left,0)+max(h1+(h2-h1)*right,0))/2
        P+=np.hypot(x2-x1,z2-z1)*fraction
        T+=dx
    if walls:P+=max(stage-points[0,1],0)+max(stage-points[-1,1],0)
    return float(A),float(P),float(T)

def conveyance(points,stage,n,walls=False):
    A,P,_=section_properties(points,stage,walls)
    return A*(A/P)**(2/3)/n if A>0 and P>0 else 0.0

def normal_stage(points,Q,n,S,walls=False):
    if Q<=0 or n<=0 or S<=0:raise ValueError('Q, nhám Manning và độ dốc phải dương.')
    bottom=points[:,1].min();high=min(points[0,1],points[-1,1])
    residual=lambda stage:conveyance(points,stage,n,walls)*np.sqrt(S)-Q
    if walls:
        high=max(points[:,1].max(),bottom+1)
        for _ in range(60):
            if residual(high)>=0:break
            high=bottom+2*(high-bottom)
        else:raise ValueError('Không tìm được khoảng nghiệm; kiểm tra dữ liệu.')
    elif residual(high)<0:
        raise ValueError(f'Q vượt khả năng tải tới bờ thấp ({conveyance(points,high,n)*np.sqrt(S):.3f} m³/s). Bổ sung mặt cắt bãi tràn hoặc chọn giả thiết vách đứng.')
    # Chia theo các cao độ gãy: chọn nghiệm nhỏ nhất nếu mặt cắt có nhiều nghiệm.
    levels=np.unique(np.r_[np.linspace(bottom,high,600),points[:,1][(points[:,1]>bottom)&(points[:,1]<high)]])
    values=[residual(z) for z in levels]
    for lo,hi,fl,fh in zip(levels[:-1],levels[1:],values[:-1],values[1:]):
        if fl<=0<=fh:
            stage=brentq(residual,lo,hi,xtol=1e-10)
            if abs(residual(stage))>max(1e-7,Q*1e-7):raise ValueError('Nghiệm không đạt sai số lưu lượng.')
            return stage
    raise ValueError('Không tìm được nghiệm mực nước trong phạm vi mặt cắt.')

def critical_stage(points,Q,walls=False):
    bottom=points[:,1].min();high=min(points[0,1],points[-1,1])
    energy=lambda z:(z-bottom)+Q**2/(2*G*section_properties(points,z,walls)[0]**2) if section_properties(points,z,walls)[0]>0 else float('inf')
    if walls:
        high=max(points[:,1].max(),bottom+1)
        for _ in range(60):
            A,_,T=section_properties(points,high,True)
            if Q**2*T/(G*A**3)<1:break
            high=bottom+2*(high-bottom)
    # Xét cực tiểu năng lượng ở từng khoảng hình học, cả nghiệm bên trong và điểm gãy.
    cuts=np.unique(np.r_[bottom,points[:,1][(points[:,1]>bottom)&(points[:,1]<high)],high])
    candidates=[]
    for lo,hi in zip(cuts[:-1],cuts[1:]):
        if hi-lo<1e-12:continue
        result=minimize_scalar(energy,bounds=(lo+max(1e-10,(hi-lo)*1e-10),hi),method='bounded',options={'xatol':1e-10})
        candidates.extend([result.x,hi])
    if not candidates:return None
    stage=min(candidates,key=energy)
    if abs(stage-high)<max(1e-6,(high-bottom)*1e-6):return None
    return float(stage)

def hydraulic_result(points,n,S,Q=None,stage=None,walls=False):
    if not all(np.isfinite(v) and v>0 for v in (n,S)):raise ValueError('Nhám n và độ dốc S (m/m) phải hữu hạn, dương.')
    if stage is None:
        if Q is None or not np.isfinite(Q) or Q<=0:raise ValueError('Lưu lượng phải hữu hạn và dương.')
        stage=normal_stage(points,Q,n,S,walls)
    else:
        if not np.isfinite(stage) or stage<=points[:,1].min():raise ValueError('Mực nước phải cao hơn đáy thấp nhất.')
        if not walls and stage>min(points[0,1],points[-1,1]):raise ValueError('Mực nước vượt bờ thấp; cần bổ sung mặt cắt hoặc chọn vách đứng.')
        Q=conveyance(points,stage,n,walls)*np.sqrt(S)
    A,P,T=section_properties(points,stage,walls);v=Q/A;Fr=v/np.sqrt(G*A/T)
    critical=critical_stage(points,Q,walls)
    Sc=(Q/conveyance(points,critical,n,walls))**2 if critical is not None else None
    wetted=(stage-points[:,1])>0
    pockets=sum(bool(flag) and (i==0 or not wetted[i-1]) for i,flag in enumerate(wetted))
    return dict(stage=stage,Q=Q,A=A,P=P,T=T,R=A/P,yn=stage-points[:,1].min(),yc=critical-points[:,1].min() if critical is not None else None,Sc=Sc,v=v,hv=v*v/(2*G),E=stage-points[:,1].min()+v*v/(2*G),Fr=Fr,pockets=pockets)



class FlowMasterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Mini FlowMaster — Thủy lực kênh hở")
        self.root.geometry("1240x900")
        self.root.configure(bg="white")

        self.result=None
        self.root.minsize(1050,760)
        style=ttk.Style(root);style.theme_use("clam")
        style.configure("TNotebook.Tab",padding=(18,9),font=("Arial",10))
        self.setup_menu()

        self.tabControl = ttk.Notebook(root)
        self.tab_irreg = ttk.Frame(self.tabControl)
        
        self.tabControl.add(self.tab_irreg, text='Kênh hở — mặt cắt tự nhiên hoặc hình học')
        self.tabControl.pack(expand=1, fill="both")

        self.setup_irregular_tab()
        self.root.after(300,self.watch_inputs)

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Mở file (Open)...", command=self.open_file)
        filemenu.add_command(label="Lưu file (Save)...", command=self.save_file)
        filemenu.add_command(label="Xuất kết quả CSV…",command=self.export_results)
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
                "coords": self.text_coords.get("1.0", tk.END).strip(),
                "mode":self.mode.get(),"stage":self.stage_entry.get(),"walls":self.walls.get()
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
                
                self.mode.set(data.get("mode","Tính mực nước từ lưu lượng"))
                self.walls.set(bool(data.get("walls",False)))
                self.stage_entry.delete(0,tk.END);self.stage_entry.insert(0,data.get("stage",""))
                self.solve_irregular()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở file, định dạng không hợp lệ!\nChi tiết: {str(e)}")

    def setup_irregular_tab(self):
        top_frame = tk.Frame(self.tab_irreg, bg="white")
        top_frame.pack(fill="x", padx=10, pady=5)

        input_frame = tk.LabelFrame(top_frame, text="Thông số thủy lực — hệ SI", bg="white", font=("Arial", 10, "bold"))
        input_frame.pack(side="left", fill="y", padx=5)

        tk.Label(input_frame, text="Hệ số nhám Manning (n):", bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.irreg_n = tk.Entry(input_frame, width=15)
        self.irreg_n.insert(0, "0.056")
        self.irreg_n.grid(row=0, column=1, padx=5)

        tk.Label(input_frame, text="Độ dốc năng lượng S (m/m):", bg="white").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.irreg_S = tk.Entry(input_frame, width=15)
        self.irreg_S.insert(0, "0.005")
        self.irreg_S.grid(row=1, column=1, padx=5)

        tk.Label(input_frame, text="Lưu lượng Q (m³/s):", bg="white").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.irreg_Q = tk.Entry(input_frame, width=15)
        self.irreg_Q.insert(0, "202")
        self.irreg_Q.grid(row=2, column=1, padx=5)

        tk.Label(input_frame, text="Mặt cắt: khoảng cách X, cao độ Z (m):", bg="white").grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 0))
        
        self.text_coords = tk.Text(input_frame, width=35, height=8, font=("Courier", 10))
        self.text_coords.grid(row=4, column=0, columnspan=2, padx=5, pady=5)
        
        default_coords = "0\t899.35\n1.41\t898.75\n8.94\t894.48\n19.02\t894.15\n21.41\t895.42\n41.41\t899.04\n45.03\t899.35"
        self.text_coords.insert(tk.END, default_coords.replace("\\t", "\t").replace("\\n", "\n"))

        self.mode=tk.StringVar(value='Tính mực nước từ lưu lượng')
        ttk.Combobox(input_frame,textvariable=self.mode,state='readonly',width=34,values=['Tính mực nước từ lưu lượng','Tính lưu lượng từ mực nước','Tính độ dốc từ Q và mực nước','Tính nhám từ Q và mực nước']).grid(row=5,column=0,columnspan=2,pady=4)
        tk.Label(input_frame,text='Cao độ mặt nước (m):',bg='white').grid(row=6,column=0,sticky='w',padx=5)
        self.stage_entry=tk.Entry(input_frame,width=15);self.stage_entry.grid(row=6,column=1);self.stage_entry.insert(0,'898')
        self.walls=tk.BooleanVar(value=False)
        ttk.Checkbutton(input_frame,text='Giả thiết vách đứng tại hai đầu',variable=self.walls).grid(row=7,column=0,columnspan=2,sticky='w',padx=5)
        ttk.Button(input_frame,text='Tạo mặt cắt chữ nhật / thang / tam giác…',command=self.geometry_dialog).grid(row=8,column=0,columnspan=2,pady=4)
        tk.Button(input_frame, text="TÍNH TOÁN", command=self.solve_irregular, bg="#0052cc", fg="white", font=("Arial", 10, "bold")).grid(row=9, column=0, columnspan=2, pady=10)

        output_frame = tk.LabelFrame(top_frame, text="Kết quả — dòng chảy đều", bg="white", font=("Arial", 10, "bold"))
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
            tk.Label(output_frame, text={'Flow Area (A):': 'Diện tích dòng chảy (A):', 'Wetted Perimeter (P):': 'Chu vi ướt (P):', 'Hydraulic Radius (R):': 'Bán kính thủy lực (R):', 'Top Width (T):': 'Bề rộng mặt nước (T):', 'Normal Depth (yn):': 'Độ sâu dòng chảy đều:', 'Critical Depth (yc):': 'Độ sâu tới hạn:', 'Critical Slope (Sc):': 'Độ dốc tới hạn:', 'Velocity (v):': 'Vận tốc trung bình:', 'Velocity Head (hv):': 'Cột nước vận tốc:', 'Specific Energy (E):': 'Năng lượng riêng:', 'Froude Number:': 'Số Froude:', 'Flow Type:': 'Trạng thái dòng chảy:'}.get(p_name,p_name), **lbl_style).grid(row=row, column=col, sticky="w", padx=(10, 2), pady=8)
            var_lbl = tk.Label(output_frame, text="---", **val_style)
            var_lbl.grid(row=row, column=col+1, padx=2)
            tk.Label(output_frame, text=unit, bg="white", font=("Arial", 9)).grid(row=row, column=col+2, sticky="w", padx=2)
            self.out_vars[p_name] = var_lbl
            
        self.lbl_wse = tk.Label(output_frame, text="Cao độ mặt nước (WSE): --- m", bg="white", fg="blue", font=("Arial", 11, "bold"))
        self.lbl_wse.grid(row=6, column=0, columnspan=6, pady=10)

        ttk.Label(self.tab_irreg,text='Manning SI: Q = A·R^(2/3)·√S/n. Một hệ số nhám, dòng chảy đều, hệ số năng lượng α = 1. Không tính nước dềnh, cống hay ống có áp.',wraplength=1150).pack(padx=15,pady=5)
        self.graph_tabs = ttk.Notebook(self.tab_irreg)
        self.graph_tabs.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.tab_graphs = ttk.Frame(self.graph_tabs)
        self.graph_tabs.add(self.tab_graphs, text="Quan hệ thủy lực")
        self.fig_rep = plt.Figure(figsize=(10, 4), dpi=100)
        self.ax_wse = self.fig_rep.add_subplot(121)
        self.ax_v = self.fig_rep.add_subplot(122)
        self.fig_rep.tight_layout(pad=3.0)
        self.canvas_rep = FigureCanvasTkAgg(self.fig_rep, self.tab_graphs)
        self.canvas_rep.get_tk_widget().pack(fill="both", expand=True)
        
        self.tab_xs = ttk.Frame(self.graph_tabs)
        self.graph_tabs.add(self.tab_xs, text="Mặt cắt ngang")
        self.fig_xs = plt.Figure(figsize=(10, 4), dpi=100)
        self.ax_xs = self.fig_xs.add_subplot(111)
        self.fig_xs.tight_layout(pad=3.0)
        self.canvas_xs = FigureCanvasTkAgg(self.fig_xs, self.tab_xs)
        self.canvas_xs.get_tk_widget().pack(fill="both", expand=True)

    def parse_coords(self):
        points=coordinates(self.text_coords.get('1.0',tk.END))
        return points[:,0],points[:,1]

    def signature(self):
        return (self.irreg_n.get(),self.irreg_S.get(),self.irreg_Q.get(),self.text_coords.get('1.0',tk.END),self.mode.get(),self.stage_entry.get(),self.walls.get())

    def clear_results(self):
        self.result=None
        for label in self.out_vars.values():label.configure(text='—')
        self.lbl_wse.configure(text='Chưa có kết quả hợp lệ — bấm TÍNH TOÁN')
        for ax in (self.ax_xs,self.ax_wse,self.ax_v):ax.clear()
        self.canvas_rep.draw_idle();self.canvas_xs.draw_idle()

    def watch_inputs(self):
        if self.result is not None and self.signature()!=self._signature:self.clear_results()
        self.root.after(300,self.watch_inputs)

    def geometry_dialog(self):
        window=tk.Toplevel(self.root);window.title('Tạo mặt cắt hình học');window.resizable(False,False)
        entries=[]
        for i,(title,default) in enumerate([('Bề rộng đáy b (m)','5'),('Mái trái z (ngang/đứng)','0'),('Mái phải z (ngang/đứng)','0'),('Chiều cao bờ (m)','3'),('Cao độ đáy (m)','0')]):
            ttk.Label(window,text=title).grid(row=i,column=0,padx=12,pady=6)
            entry=ttk.Entry(window);entry.insert(0,default);entry.grid(row=i,column=1,padx=12);entries.append(entry)
        def apply():
            try:
                b,zl,zr,h,z=[number(e.get(),'Thông số hình học') for e in entries]
                if b<0 or min(zl,zr)<0 or h<=0 or b+zl+zr<=0:raise ValueError('Bề rộng, mái không âm; chiều cao dương; mặt cắt phải có bề rộng.')
                points=[(0,z+h),(zl*h,z),(zl*h+b,z),(zl*h+b+zr*h,z+h)]
                points=[point for i,point in enumerate(points) if i==0 or point!=points[i-1]]
                self.text_coords.delete('1.0',tk.END);self.text_coords.insert('1.0','\n'.join(f'{x:.6g}\t{y:.6g}' for x,y in points));self.clear_results();window.destroy()
            except ValueError as e:messagebox.showerror('Hình học không hợp lệ',str(e),parent=window)
        ttk.Button(window,text='Áp dụng mặt cắt',command=apply).grid(row=5,column=0,columnspan=2,pady=12)

    def export_results(self):
        if self.result is None or self.signature()!=self._signature:
            self.clear_results();messagebox.showwarning('Chưa có kết quả','Hãy tính lại trước khi xuất.');return
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('Bảng CSV mở bằng Excel','*.csv')])
        if not path:return
        try:
            with open(path,'w',encoding='utf-8-sig',newline='') as file:
                writer=csv.writer(file);writer.writerow(['Thông số','Giá trị','Đơn vị'])
                writer.writerow(['Manning n',self._n,'']);writer.writerow(['Độ dốc năng lượng',self._S,'m/m'])
                titles={'stage':('Cao độ mặt nước','m'),'Q':('Lưu lượng','m³/s'),'A':('Diện tích dòng chảy','m²'),'P':('Chu vi ướt','m'),'T':('Bề rộng mặt nước','m'),'R':('Bán kính thủy lực','m'),'yn':('Độ sâu dòng chảy đều','m'),'yc':('Độ sâu tới hạn','m'),'Sc':('Độ dốc tới hạn','m/m'),'v':('Vận tốc trung bình','m/s'),'hv':('Cột nước vận tốc','m'),'E':('Năng lượng riêng','m'),'Fr':('Số Froude',''),'pockets':('Số vùng ướt','')}
                for key,value in self.result.items():
                    title,unit=titles[key];writer.writerow([title,'Ngoài phạm vi mặt cắt' if value is None else value,unit])
                writer.writerow(['Giả thiết','Dòng chảy đều; một hệ số nhám; hệ số năng lượng bằng 1',''])
                writer.writerow(['Hai đầu mặt cắt','Vách đứng giả định' if self.walls.get() else 'Giới hạn tại bờ thấp',''])
                writer.writerow(['Khoảng cách X','Cao độ Z','m'])
                writer.writerows(self._points)
        except OSError as e:messagebox.showerror('Không xuất được',str(e))

    def solve_irregular(self):
        self.clear_results()
        try:
            n=number(self.irreg_n.get(),'Nhám Manning');S=number(self.irreg_S.get(),'Độ dốc năng lượng')
            points=coordinates(self.text_coords.get('1.0',tk.END));walls=self.walls.get()
            mode=self.mode.get()
            if mode in ('Tính độ dốc từ Q và mực nước','Tính nhám từ Q và mực nước'):
                stage=number(self.stage_entry.get(),'Cao độ mặt nước');Q=number(self.irreg_Q.get(),'Lưu lượng')
                if Q<=0 or stage<=points[:,1].min():raise ValueError('Q phải dương, mực nước cao hơn đáy.')
                if not walls and stage>min(points[0,1],points[-1,1]):raise ValueError('Mực nước vượt bờ thấp.')
                if mode.startswith('Tính độ dốc'):
                    if n<=0:raise ValueError('Nhám phải dương.')
                    S=(Q/conveyance(points,stage,n,walls))**2
                else:
                    if S<=0:raise ValueError('Độ dốc phải dương.')
                    n=conveyance(points,stage,1,walls)*np.sqrt(S)/Q
                result=hydraulic_result(points,n,S,stage=stage,walls=walls)
            elif mode=='Tính lưu lượng từ mực nước':
                result=hydraulic_result(points,n,S,stage=number(self.stage_entry.get(),'Cao độ mặt nước'),walls=walls)
            else:result=hydraulic_result(points,n,S,Q=number(self.irreg_Q.get(),'Lưu lượng'),walls=walls)
            keys=['A','P','R','T','yn','yc','Sc','v','hv','E','Fr']
            for label,key in zip(list(self.out_vars.values())[:-1],keys):
                value=result[key];label.configure(text='Ngoài mặt cắt' if value is None else f'{value:.5f}' if key=='Sc' else f'{value:.3f}')
            regime='Tới hạn' if abs(result['Fr']-1)<.01 else 'Êm' if result['Fr']<1 else 'Xiết'
            self.out_vars['Flow Type:'].configure(text=regime)
            note=' | Nhiều vùng ướt: dùng chung mực nước và nhám' if result['pockets']>1 else ''
            self.lbl_wse.configure(text=f"Mực nước: {result['stage']:.3f} m | Q: {result['Q']:.3f} m³/s"+f' | n = {n:.5f}; S = {S:.6f} m/m'+note)
            self.ax_xs.plot(points[:,0],points[:,1],color='#334155',marker='.',label='Mặt cắt khảo sát')
            self.ax_xs.fill_between(points[:,0],points[:,1],result['stage'],where=points[:,1]<=result['stage'],interpolate=True,color='#38bdf8',alpha=.35)
            self.ax_xs.axhline(result['stage'],color='#0284c7',label='Mặt nước')
            if walls:
                for x,z in (points[0],points[-1]):
                    if result['stage']>z:self.ax_xs.plot([x,x],[z,result['stage']],color='#e67e22',linestyle='--',label='Vách giả định')
            self.ax_xs.set(xlabel='Khoảng cách (m)',ylabel='Cao độ (m)',title='Mặt cắt và mực nước');self.ax_xs.grid(alpha=.25);self.ax_xs.legend()
            top=max(points[:,1].max(),result['stage']*0+points[:,1].min()+2*result['yn']) if walls else min(points[0,1],points[-1,1])
            stages=np.linspace(points[:,1].min()+max(1e-8,(top-points[:,1].min())*1e-5),top,100)
            q_values=[conveyance(points,z,n,walls)*np.sqrt(S) for z in stages]
            velocities=[q/section_properties(points,z,walls)[0] for q,z in zip(q_values,stages)]
            self.ax_wse.plot(q_values,stages,color='#0284c7');self.ax_wse.scatter([result['Q']],[result['stage']],color='#e67e22')
            self.ax_v.plot(q_values,velocities,color='#0d9488');self.ax_v.scatter([result['Q']],[result['v']],color='#e67e22')
            self.ax_wse.set(xlabel='Lưu lượng (m³/s)',ylabel='Cao độ mặt nước (m)',title='Quan hệ lưu lượng – mực nước')
            self.ax_v.set(xlabel='Lưu lượng (m³/s)',ylabel='Vận tốc (m/s)',title='Quan hệ lưu lượng – vận tốc')
            for ax in (self.ax_wse,self.ax_v):ax.grid(alpha=.25)
            self.fig_rep.tight_layout();self.fig_xs.tight_layout();self.canvas_rep.draw();self.canvas_xs.draw()
            self.result=result;self._signature=self.signature();self._n=n;self._S=S;self._points=points
        except (ValueError,ArithmeticError) as e:messagebox.showerror('Dữ liệu hoặc phạm vi tính toán',str(e))

if __name__ == '__main__':
    root=tk.Tk();app=FlowMasterApp(root);root.mainloop()
