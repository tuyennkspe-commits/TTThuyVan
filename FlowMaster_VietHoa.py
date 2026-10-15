"""Việt hóa giao diện FlowMaster đang chạy bằng Windows API, kèm từ điển thủy lực.
Chạy: python FlowMaster_VietHoa.py (Python chuẩn có tkinter; Windows 10/11).
Chỉ thay nhãn/menu được hỗ trợ; không sửa ô nhập, danh sách chọn hoặc chữ vẽ trên đồ thị.
"""
import os
import re
import ctypes
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox

# English, short interface label, full technical explanation.
TERMS = [
('File','Tệp','Menu quản lý tệp dự án.'),('Edit','Chỉnh sửa','Menu chỉnh sửa.'),
('Analysis','Phân tích','Phân tích thủy lực.'),('View','Hiển thị','Thiết lập cách hiển thị.'),
('Tools','Công cụ','Các công cụ và thiết lập.'),('Window','Cửa sổ','Quản lý cửa sổ làm việc.'),('Help','Trợ giúp','Tài liệu và thông tin phần mềm.'),
('New','Tạo mới','Tạo dự án hoặc phần tử mới.'),('Open','Mở','Mở tệp đã có.'),('Save','Lưu','Lưu dự án.'),('Save As','Lưu thành','Lưu thành tệp khác.'),
('Close','Đóng','Đóng cửa sổ/tệp.'),('Exit','Thoát','Thoát chương trình.'),('Print','In','In tài liệu.'),('Print Preview','Xem trước khi in','Xem bố cục trước khi in.'),
('Undo','Hoàn tác','Hủy thao tác vừa thực hiện.'),('Redo','Làm lại','Thực hiện lại thao tác đã hoàn tác.'),('Cut','Cắt','Cắt đối tượng.'),('Copy','Sao chép','Sao chép đối tượng.'),('Paste','Dán','Dán đối tượng.'),('Delete','Xóa','Xóa đối tượng được chọn.'),
('Select All','Chọn tất cả','Chọn toàn bộ đối tượng.'),('Properties','Thuộc tính','Thuộc tính của đối tượng.'),('Options','Tùy chọn','Các tùy chọn tính toán/hiển thị.'),
('OK','Đồng ý','Xác nhận.'),('Cancel','Hủy','Hủy thao tác.'),('Apply','Áp dụng','Áp dụng thiết lập.'),('Yes','Có','Đồng ý.'),('No','Không','Không đồng ý.'),
('Search','Tìm kiếm','Tìm đối tượng hoặc thuật ngữ.'),('Project Explorer','Cây dự án','Danh sách phân cấp các đối tượng trong dự án.'),
('Engineering Library Explorer','Thư viện kỹ thuật','Cây quản lý thư viện vật liệu và dữ liệu kỹ thuật.'),('Material Libraries','Thư viện vật liệu','Các thư viện vật liệu/độ nhám.'),
('Worksheet','Bảng tính','Bảng tính thủy lực của một phần tử.'),('Uniform Flow','Dòng chảy đều','Dòng chảy có các đặc trưng không đổi theo chiều dài trong điều kiện tính.'),
('Gradually Varied Flow','Dòng biến đổi chậm','Dòng chảy không đều biến đổi chậm theo chiều dài; tính đường mặt nước.'),
('Messages','Thông báo','Các thông báo tính toán và kiểm tra dữ liệu.'),('Solve For','Đại lượng cần tìm','Chọn ẩn số cần giải; không phải tất cả các trường đều là dữ liệu nhập.'),
('Friction Method','Công thức sức cản','Phương pháp tính tổn thất/sức cản dòng chảy.'),('Manning Formula','Công thức Manning','Q = A R^(2/3) S^(1/2) / n trong hệ SI.'),
('Roughness Coefficient','Hệ số nhám (n)','Hệ số nhám Manning n; giá trị phụ thuộc bề mặt và điều kiện dòng chảy.'),
('Manning n','Hệ số nhám Manning','Hệ số nhám n trong công thức Manning.'),
('Channel Slope','Độ dốc đáy kênh','Độ dốc dọc kênh S0; với dòng chảy đều, bằng độ dốc năng lượng.'),
('Energy Slope','Độ dốc năng lượng','Độ dốc đường năng lượng Sf, không mặc nhiên bằng độ dốc đáy khi dòng chảy không đều.'),
('Friction Slope','Độ dốc tổn thất','Độ dốc tổn thất năng lượng dọc đường Sf.'),
('Elevation','Cao độ','Cao độ so với mốc của dự án; cần đọc theo ngữ cảnh của trường dữ liệu.'),
('Water Surface Elevation','Cao độ mặt nước','Cao độ mặt nước so với mốc cao độ.'),('Elevation Range','Khoảng cao độ','Khoảng cao độ của mặt cắt hoặc phạm vi tính toán.'),
('Discharge','Lưu lượng (Q)','Thể tích nước qua mặt cắt trong một đơn vị thời gian; cần kiểm tra đơn vị m³/s hay L/s.'),
('Flow Area','Diện tích ướt (A)','Diện tích mặt cắt dòng chảy, đơn vị m² trong hệ SI.'),
('Wetted Perimeter','Chu vi ướt (P)','Chiều dài biên rắn tiếp xúc với nước; không bao gồm bề rộng mặt thoáng.'),
('Hydraulic Radius','Bán kính thủy lực','R = A/P; khác với độ sâu thủy lực.'),
('Hydraulic Depth','Độ sâu thủy lực','D = A/T, với T là bề rộng mặt nước.'),
('Top Width','Bề rộng mặt nước','T: bề rộng mặt thoáng của dòng chảy tại mặt cắt.'),
('Normal Depth','Độ sâu dòng chảy đều','Độ sâu ứng với dòng chảy đều tại lưu lượng, độ dốc và độ nhám đã cho.'),
('Critical Depth','Độ sâu tới hạn','Độ sâu tại trạng thái tới hạn; với giả thiết thông thường, năng lượng riêng đạt cực tiểu tại Q đã cho.'),
('Critical Slope','Độ dốc tới hạn','Độ dốc tạo dòng chảy đều có độ sâu bằng độ sâu tới hạn.'),
('Velocity','Vận tốc trung bình','V = Q/A, là vận tốc trung bình mặt cắt.'),
('Velocity Head','Cột nước vận tốc','αV²/(2g); kiểm tra hệ số hiệu chỉnh động năng α trong mô hình.'),
('Specific Energy','Năng lượng riêng','E = y + αV²/(2g), lấy mốc tại đáy mặt cắt đang xét.'),
('Froude Number','Số Froude','Fr = V/√(gD), D = A/T, trong điều kiện mặt cắt và giả thiết mô hình tương ứng.'),
('Flow Type','Trạng thái dòng chảy','Phân loại dòng chảy theo số Froude.'),
('Subcritical','Chảy êm','Fr < 1; độ sâu thường lớn hơn độ sâu tới hạn trên nhánh tương ứng.'),
('Supercritical','Chảy xiết','Fr > 1; độ sâu thường nhỏ hơn độ sâu tới hạn trên nhánh tương ứng.'),
('Critical','Chảy tới hạn','Fr = 1 trong mô hình thông thường.'),
('Edit Section','Sửa mặt cắt','Nhập hoặc chỉnh tọa độ mặt cắt.'),('Cross Section','Mặt cắt ngang','Hình dạng mặt cắt vuông góc hướng dòng chảy.'),
('Irregular Section','Mặt cắt tự nhiên','Mặt cắt bất kỳ được mô tả bằng các điểm tọa độ.'),
('Rectangular Channel','Kênh chữ nhật','Mặt cắt kênh hình chữ nhật.'),('Trapezoidal Channel','Kênh hình thang','Mặt cắt kênh hình thang.'),
('Triangular Channel','Kênh tam giác','Mặt cắt kênh hình tam giác.'),('Circular Channel','Mặt cắt tròn','Mặt cắt tròn; phân biệt chảy không đầy và chảy có áp.'),
('Bottom Width','Bề rộng đáy','Bề rộng đáy kênh.'),('Side Slope','Hệ số mái dốc','Kiểm tra quy ước ngang:đứng (H:V) trong trường nhập.'),
('Station','Khoảng cách mặt cắt','Trong bảng mặt cắt: tọa độ khoảng cách dọc mặt cắt, không phải trạm thủy văn.'),
('Depth','Độ sâu','Độ sâu dòng chảy hoặc cấu kiện theo ngữ cảnh.'),('Length','Chiều dài','Chiều dài phần tử.'),('Diameter','Đường kính','Đường kính hình học.'),
('Rating Table','Bảng quan hệ','Bảng quan hệ giữa các đại lượng thủy lực; không nhất thiết chỉ Q–H.'),
('Rating Curve','Đường quan hệ','Đường quan hệ thủy lực; đọc tên các trục để biết cặp đại lượng.'),
('Define Rating Curve','Chọn đại lượng vẽ','Thiết lập các đại lượng và phạm vi của đường quan hệ.'),
('Tabular Reports','Báo cáo dạng bảng','Báo cáo nhiều phần tử hoặc thông số theo bảng.'),('Detailed Report','Báo cáo chi tiết','Báo cáo đầy đủ của phần tử.'),
('GVF Profile','Đường mặt nước','Đường mặt nước của dòng chảy biến đổi chậm.'),('GVF Profile Table','Bảng đường mặt nước','Bảng kết quả tính dòng chảy biến đổi chậm.'),
('Hydraulic Grade Line','Đường đo áp','Đường biểu diễn cao độ cột nước áp suất và vị trí.'),('Energy Grade Line','Đường năng lượng','Đường biểu diễn tổng cột nước năng lượng.'),
('Head Loss','Tổn thất cột nước','Độ giảm cột nước do tổn thất năng lượng.'),('Tailwater','Mực nước hạ lưu','Điều kiện mực nước phía hạ lưu.'),('Headwater','Mực nước thượng lưu','Điều kiện mực nước phía thượng lưu.'),
('Units','Đơn vị','Thiết lập đơn vị hiển thị/tính toán.'),('Units and Formatting','Đơn vị và định dạng','Thiết lập đơn vị và số chữ số hiển thị.'),
('Calculation Successful.','Tính toán thành công.','Thông báo đã hoàn thành phép tính; vẫn cần kiểm tra tính hợp lý của dữ liệu và mô hình.'),
('Calculation Successful','Tính toán thành công','Thông báo đã hoàn thành phép tính.'),('Calculate','Tính toán','Thực hiện phép tính.'),
('Select a single element.','Chọn một phần tử.','Chọn một phần tử để xem hoặc chỉnh sửa thuộc tính.')]

def normalize(text):
    return re.sub(r'\s+',' ',text.replace('&&','\0').replace('&','').replace('\0','&')).strip().casefold()

TRANSLATIONS={normalize(en):vi for en,vi,detail in TERMS}

def translate_text(text):
    """Exact UI phrases only: preserve numbers, unit strings, shortcuts and names."""
    if not isinstance(text,str) or not text.strip():return None
    label,separator,shortcut=text.partition('\t')
    trailing=re.search(r'(\s*(?:\.\.\.|…|:)\s*)$',label)
    suffix=trailing.group(0) if trailing else ''
    stem=label[:trailing.start()] if trailing else label
    translated=TRANSLATIONS.get(normalize(label)) or TRANSLATIONS.get(normalize(stem))
    if translated:
        if suffix and not translated.endswith((':','…','...')):translated+=suffix
        return translated+(separator+shortcut if separator else '')
    for prefix in ('Worksheet','Rating Curve','Rating Table','Cross Section','GVF Profile'):
        match=re.match(r'^\s*'+re.escape(prefix)+r'\s*:\s*(.+)$',label,re.I)
        if match:return TRANSLATIONS[normalize(prefix)]+': '+match.group(1)+(separator+shortcut if separator else '')
    return None

def translatable_control(class_name):
    value=class_name.casefold()
    return value in ('static','button','#32770') or value.startswith(('windowsforms10.static.','windowsforms10.button.','thunderrt6label','thunderrt5label'))

class WindowsBackend:
    def __init__(self):
        if os.name!='nt':raise RuntimeError('Việt hóa trực tiếp cần Windows. Từ điển vẫn dùng được trên hệ điều hành khác.')
        from ctypes import wintypes as w
        self.w=w;self.user=ctypes.WinDLL('user32',use_last_error=True);self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
        self.user.EnumWindows.argtypes=[self.callback_type,w.LPARAM];self.user.EnumWindows.restype=w.BOOL
        self.user.EnumChildWindows.argtypes=[w.HWND,self.callback_type,w.LPARAM];self.user.EnumChildWindows.restype=w.BOOL
        self.user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)];self.user.GetWindowThreadProcessId.restype=w.DWORD
        self.user.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];self.user.GetClassNameW.restype=ctypes.c_int
        self.user.IsWindow.argtypes=[w.HWND];self.user.IsWindow.restype=w.BOOL
        self.user.IsWindowVisible.argtypes=[w.HWND];self.user.IsWindowVisible.restype=w.BOOL
        self.user.IsHungAppWindow.argtypes=[w.HWND];self.user.IsHungAppWindow.restype=w.BOOL
        self.user.SendMessageTimeoutW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM,w.UINT,w.UINT,ctypes.POINTER(ctypes.c_size_t)];self.user.SendMessageTimeoutW.restype=ctypes.c_ssize_t
        self.kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];self.kernel.OpenProcess.restype=w.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)];self.kernel.QueryFullProcessImageNameW.restype=w.BOOL
        self.kernel.CloseHandle.argtypes=[w.HANDLE];self.kernel.CloseHandle.restype=w.BOOL
        self.user.GetMenu.argtypes=[w.HWND];self.user.GetMenu.restype=w.HMENU
        self.user.GetSubMenu.argtypes=[w.HMENU,ctypes.c_int];self.user.GetSubMenu.restype=w.HMENU
        self.user.GetMenuItemCount.argtypes=[w.HMENU];self.user.GetMenuItemCount.restype=ctypes.c_int
        self.user.GetMenuItemID.argtypes=[w.HMENU,ctypes.c_int];self.user.GetMenuItemID.restype=w.UINT
        self.user.GetMenuStringW.argtypes=[w.HMENU,w.UINT,w.LPWSTR,ctypes.c_int,w.UINT];self.user.GetMenuStringW.restype=ctypes.c_int
        self.user.IsMenu.argtypes=[w.HMENU];self.user.IsMenu.restype=w.BOOL
        self.user.DrawMenuBar.argtypes=[w.HWND];self.user.DrawMenuBar.restype=w.BOOL
        class MenuInfo(ctypes.Structure):
            _fields_=[('cbSize',w.UINT),('fMask',w.UINT),('fType',w.UINT),('fState',w.UINT),('wID',w.UINT),('hSubMenu',w.HMENU),('hbmpChecked',w.HBITMAP),('hbmpUnchecked',w.HBITMAP),('dwItemData',ctypes.c_size_t),('dwTypeData',w.LPWSTR),('cch',w.UINT),('hbmpItem',w.HBITMAP)]
        self.MenuInfo=MenuInfo
        self.user.SetMenuItemInfoW.argtypes=[w.HMENU,w.UINT,w.BOOL,ctypes.POINTER(MenuInfo)];self.user.SetMenuItemInfoW.restype=w.BOOL
        self.texts={};self.menus={};self.cancel=threading.Event();self.target_pid=None

    def pid(self,window):
        pid=self.w.DWORD();self.user.GetWindowThreadProcessId(window,ctypes.byref(pid));return pid.value
    def classname(self,window):
        value=ctypes.create_unicode_buffer(256);self.user.GetClassNameW(window,value,len(value));return value.value
    def text(self,window):
        value=ctypes.create_unicode_buffer(4096);result=ctypes.c_size_t()
        ok=self.user.SendMessageTimeoutW(window,13,len(value),ctypes.cast(value,ctypes.c_void_p).value,2,80,ctypes.byref(result))
        return value.value if ok else ''
    def set_text(self,window,value):
        text=ctypes.create_unicode_buffer(value);result=ctypes.c_size_t()
        ok=self.user.SendMessageTimeoutW(window,12,0,ctypes.cast(text,ctypes.c_void_p).value,2,100,ctypes.byref(result))
        return bool(ok and result.value and self.text(window)==value)
    def executable(self,pid):
        handle=self.kernel.OpenProcess(0x1000,False,pid)
        if not handle:return ''
        try:
            text=ctypes.create_unicode_buffer(32768);size=self.w.DWORD(len(text))
            return text.value if self.kernel.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(size)) else ''
        finally:self.kernel.CloseHandle(handle)
    def windows(self):
        result=[]
        def visit(window,param):
            if self.user.IsWindowVisible(window) and self.pid(window)!=os.getpid():
                pid=self.pid(window);name=os.path.basename(self.executable(pid)).casefold()
                if name in ('flowmaster.exe','flowmaster64.exe','openflowsflowmaster.exe'):
                    title=self.text(window)
                    if title:result.append((int(window),pid,title))
            return True
        callback=self.callback_type(visit);self.user.EnumWindows(callback,0);return result
    def menu_text(self,menu,index):
        text=ctypes.create_unicode_buffer(2048);self.user.GetMenuStringW(menu,index,text,len(text),0x400);return text.value
    def set_menu_text(self,menu,index,value):
        buffer=ctypes.create_unicode_buffer(value);info=self.MenuInfo();info.cbSize=ctypes.sizeof(info);info.fMask=0x40
        info.dwTypeData=ctypes.cast(buffer,self.w.LPWSTR);info.cch=len(value)
        return bool(self.user.SetMenuItemInfoW(menu,index,True,ctypes.byref(info)))
    def apply(self,pid):
        if self.target_pid is not None and self.target_pid!=pid:self.restore()
        self.target_pid=pid;changed=0;failed=0;seen=set()
        roots=[window for window,p,caption in self.windows() if p==pid]
        if not roots:raise ValueError('Không còn cửa sổ FlowMaster được chọn. Mở FlowMaster rồi quét lại.')
        def visit(window,param):
            nonlocal changed,failed
            if self.cancel.is_set():return False
            if self.pid(window)!=pid or not translatable_control(self.classname(window)):return True
            original=self.text(window);translated=translate_text(original)
            if translated and translated!=original:
                if self.set_text(window,translated):
                    self.texts[int(window)]=(pid,self.classname(window),original,translated);changed+=1
                else:failed+=1
            return True
        callback=self.callback_type(visit)
        def menus(menu,depth=0):
            nonlocal changed,failed
            if not menu or menu in seen or depth>8 or self.cancel.is_set():return
            seen.add(menu)
            for index in range(min(max(0,self.user.GetMenuItemCount(menu)),500)):
                if self.cancel.is_set():break
                original=self.menu_text(menu,index);translated=translate_text(original)
                sub=self.user.GetSubMenu(menu,index);command=self.user.GetMenuItemID(menu,index)
                if translated and translated!=original:
                    if self.set_menu_text(menu,index,translated):self.menus[(int(menu),index)]=(command,sub,original,translated);changed+=1
                    else:failed+=1
                menus(sub,depth+1)
        for window in roots:
            if self.cancel.is_set():break
            if self.user.IsHungAppWindow(window):failed+=1;continue
            visit(window,0);self.user.EnumChildWindows(window,callback,0)
            menus(self.user.GetMenu(window));self.user.DrawMenuBar(window)
        return f'Đã đổi thêm {changed} nhãn/menu; đang theo dõi {len(self.texts)+len(self.menus)} mục.'+(f' {failed} mục chưa đổi được; kiểm tra quyền chạy hoặc kiểu giao diện.' if failed else '')
    def restore(self):
        restored=0;owned=set()
        def collect(menu,depth=0):
            if not menu or menu in owned or depth>8:return
            owned.add(menu)
            for index in range(min(max(0,self.user.GetMenuItemCount(menu)),500)):collect(self.user.GetSubMenu(menu,index),depth+1)
        for window,pid,caption in self.windows():
            if pid==self.target_pid:collect(self.user.GetMenu(window))
        for window,(pid,klass,original,translated) in list(self.texts.items()):
            if self.user.IsWindow(window) and self.pid(window)==pid and self.classname(window)==klass and self.text(window)==translated:
                if self.set_text(window,original):restored+=1
        for (menu,index),(command,sub,original,translated) in list(self.menus.items()):
            if menu in owned and self.user.IsMenu(menu) and self.user.GetMenuItemID(menu,index)==command and self.user.GetSubMenu(menu,index)==sub and self.menu_text(menu,index)==translated:
                if self.set_menu_text(menu,index,original):restored+=1
        for window,pid,caption in self.windows():self.user.DrawMenuBar(window)
        self.texts.clear();self.menus.clear();self.target_pid=None
        return f'Đã khôi phục {restored} nhãn/menu về tiếng Anh.'

class TranslatorApp:
    def __init__(self,root,backend=None):
        self.root=root;self.backend=backend;self.busy=False;self.pending_restore=False;self.closing=False;self.results=queue.Queue();self.targets=[]
        root.title('FlowMaster — Việt hóa thuật ngữ thủy lực');root.geometry('1020x700');root.minsize(800,560)
        style=ttk.Style();style.theme_use('clam');style.configure('Treeview',rowheight=27);style.configure('TButton',padding=7)
        ttk.Label(root,text='FLOWMASTER · TIẾNG VIỆT CHUYÊN NGÀNH',font=('Segoe UI',15,'bold'),foreground='#174d7d').pack(anchor='w',padx=14,pady=(12,5))
        ttk.Label(root,text='Mở FlowMaster → Quét cửa sổ → chọn cửa sổ → Bật Việt hóa.',wraplength=950).pack(anchor='w',padx=14)
        bar=ttk.Frame(root,padding=10);bar.pack(fill='x')
        self.choice=ttk.Combobox(bar,state='readonly',width=60);self.choice.pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(bar,text='Quét cửa sổ',command=self.scan).pack(side='left',padx=4)
        self.auto=tk.BooleanVar(root,value=False)
        controls=ttk.Frame(root,padding=(10,0));controls.pack(fill='x')
        ttk.Button(controls,text='Bật Việt hóa',command=self.start).pack(side='left',padx=4)
        ttk.Button(controls,text='Khôi phục tiếng Anh',command=self.restore).pack(side='left',padx=4)
        ttk.Checkbutton(controls,text='Cập nhật khi mở bảng tính mới',variable=self.auto).pack(side='left',padx=10)
        self.status=ttk.Label(root,text='Sẵn sàng.',wraplength=950,foreground='#174d7d');self.status.pack(fill='x',padx=14,pady=8)
        ttk.Separator(root).pack(fill='x',padx=12)
        searchbar=ttk.Frame(root,padding=10);searchbar.pack(fill='x')
        ttk.Label(searchbar,text='Tra thuật ngữ Anh / Việt:').pack(side='left')
        self.search=tk.StringVar(root);ttk.Entry(searchbar,textvariable=self.search).pack(side='left',fill='x',expand=True,padx=8)
        self.search.trace_add('write',lambda *args:self.filter_terms())
        body=ttk.Frame(root);body.pack(fill='both',expand=True,padx=12)
        self.tree=ttk.Treeview(body,columns=('en','vi'),show='headings',selectmode='browse')
        self.tree.heading('en',text='Tiếng Anh');self.tree.heading('vi',text='Tiếng Việt chuyên ngành')
        self.tree.column('en',width=350);self.tree.column('vi',width=500)
        scroll=ttk.Scrollbar(body,orient='vertical',command=self.tree.yview);scroll.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scroll.set);self.tree.pack(fill='both',expand=True)
        self.detail=tk.Text(root,height=4,wrap='word',font=('Segoe UI',10),state='disabled');self.detail.pack(fill='x',padx=12,pady=8)
        self.tree.bind('<<TreeviewSelect>>',self.explain)
        ttk.Label(root,text='Phạm vi: nhãn và menu Windows hỗ trợ. Danh sách chọn, ô dữ liệu, tab tùy biến và chữ trên đồ thị có thể vẫn là tiếng Anh; tra ở bảng thuật ngữ. Khi thoát, tool khôi phục các mục còn nhận diện được. Không cần chọn thư mục cài đặt.',wraplength=970,foreground='#52657c').pack(fill='x',padx=12,pady=(0,10))
        self.filter_terms();root.protocol('WM_DELETE_WINDOW',self.close);root.after(150,self.poll);root.after(1500,self.tick)
        if self.backend is None and os.name=='nt':
            try:self.backend=WindowsBackend()
            except Exception as error:self.status.configure(text=str(error))
        if self.backend is None:self.status.configure(text='Chế độ từ điển. Việt hóa trực tiếp cần Windows 10/11.')
        else:self.scan()
    def filter_terms(self):
        query=self.search.get().strip().casefold();self.tree.delete(*self.tree.get_children())
        for index,(en,vi,detail) in enumerate(TERMS):
            if not query or query in (en+' '+vi+' '+detail).casefold():self.tree.insert('', 'end',iid=str(index),values=(en,vi))
    def explain(self,event=None):
        selected=self.tree.selection()
        if not selected:return
        en,vi,detail=TERMS[int(selected[0])]
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',f'{en} → {vi}\n{detail}');self.detail.configure(state='disabled')
    def scan(self):
        if not self.backend:return
        if self.busy:return
        self.targets=self.backend.windows();self.choice.configure(values=[f'{title} · PID {pid}' for window,pid,title in self.targets])
        if self.targets:self.choice.current(0);self.status.configure(text=f'Tìm thấy {len(self.targets)} cửa sổ FlowMaster.')
        else:self.choice.set('');self.status.configure(text='Chưa tìm thấy FlowMaster.exe. Mở chương trình chính rồi quét lại; nếu FlowMaster chạy quyền quản trị, tool cần cùng mức quyền.')
    def start(self):
        if not self.backend:return
        if self.choice.current()<0:messagebox.showinfo('Chọn FlowMaster','Mở FlowMaster và chọn cửa sổ trước.');return
        self.auto.set(True);self.launch('apply')
    def launch(self,action):
        if self.busy or not self.backend:return
        if action=='apply' and self.choice.current()<0:return
        pid=self.targets[self.choice.current()][1] if action=='apply' else None
        self.busy=True;self.backend.cancel.clear();self.status.configure(text='Đang Việt hóa…' if action=='apply' else 'Đang khôi phục…')
        def work():
            try:self.results.put((True,self.backend.apply(pid) if action=='apply' else self.backend.restore(),action))
            except Exception as error:self.results.put((False,str(error),action))
        threading.Thread(target=work,daemon=True).start()
    def restore(self):
        self.auto.set(False)
        if not self.backend:
            if self.closing:self.root.destroy()
            return
        if self.busy:self.backend.cancel.set();self.pending_restore=True
        else:self.launch('restore')
    def poll(self):
        try:
            ok,text,action=self.results.get_nowait();self.busy=False;self.status.configure(text=text)
            if self.pending_restore:self.pending_restore=False;self.launch('restore')
            elif self.closing and action=='restore':self.root.destroy();return
            elif not ok:self.auto.set(False)
        except queue.Empty:pass
        self.root.after(150,self.poll)
    def tick(self):
        if self.auto.get() and not self.busy and not self.closing:self.launch('apply')
        self.root.after(1500,self.tick)
    def close(self):
        self.closing=True;self.restore()

if __name__=='__main__':
    root=tk.Tk();TranslatorApp(root);root.mainloop()
