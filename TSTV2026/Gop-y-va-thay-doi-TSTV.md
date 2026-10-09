# Rà soát TSTV 2026

Bản sửa dựa trên tệp TSTV-2026-V1.py được cung cấp trong cuộc trò chuyện. Không ghi đè tệp gốc.

## Giao diện

- Cửa sổ thay đổi kích thước, có thanh cuộn cho bảng và phần thiết lập.
- Tách số liệu, phân tích, thông tin bản vẽ; nhóm riêng tham số của từng phương pháp.
- Dùng một phông giao diện, màu xanh đậm và màu trung tính; giữ phông kỹ thuật trên bản vẽ.
- Viết rõ số thứ tự, giá trị quan trắc, giá trị sắp xếp, giá trị trung bình, hệ số biến thiên, hệ số bất đối xứng và tên nút tần suất.
- Bảng số liệu gốc và cột sắp xếp là hai thứ tự độc lập; năm bên trái không phải năm ứng với giá trị sắp xếp bên phải.
- Đóng ứng dụng qua vòng lặp Tk và đóng hình Matplotlib, thay cho cưỡng bức os._exit.

## Công thức và phương pháp

1. Mô men mẫu: trung bình, độ lệch chuẩn mẫu ddof=1 và hệ số bất đối xứng hiệu chỉnh trong mã gốc là đúng. Đã kiểm tra hệ số bất đối xứng với scipy.stats.skew(bias=False).
2. Xếp chuỗi giảm dần nên P là tần suất vượt; phân vị dùng q = 1 − P/100. Giữ quy ước này.
3. Hazen đúng là (m−0,5)/n. Công thức (m−0,25)/(n+0,5) được giữ nguyên số nhưng đổi tên thành vị trí vẽ α=0,25, không còn gán tên Hazen. Weibull m/(n+1) giữ nguyên. Điểm ba điểm mặc định là nội suy tuyến tính từ chuỗi; ngoài miền tần suất quan trắc lấy giá trị biên, không phải ngoại suy đuôi phân phối. Người dùng cần kiểm tra hoặc nhập điểm xác định riêng. Khi đổi công thức, các điểm nội suy 5%, 50%, 95% được cập nhật theo lựa chọn.
4. Pearson III: dùng đúng trung bình, độ lệch chuẩn và hệ số bất đối xứng; Cs=0 được giữ chính xác thay cho ép thành 0,0001.
5. Log-Pearson III: tính mô men trên toàn bộ log10(X). Bắt buộc mọi X > 0; không tự bỏ số liệu. Các tham số nhập trực tiếp nay là trung bình log10, độ lệch chuẩn log10 và hệ số bất đối xứng log10, với nhãn tương ứng. Trước đây hai tham số đầu bị bỏ qua khi tính phân vị. Không dùng Cv của biến log vì trung bình log có thể bằng 0 hoặc âm.
6. Ba điểm: mã gốc luôn khớp Pearson III bất kể phân phối chọn. Bản sửa khớp đúng phân phối; Log-Pearson III khớp trong miền log10; kiểm tra thứ tự X5 > X50 > X95, dữ liệu hữu hạn, hội tụ và sai số khớp Pearson. Gumbel chỉ có hai tham số nên khớp ba điểm theo bình phương tối thiểu, không hứa đi chính xác qua ba điểm tùy ý.
7. Gumbel: β = σ√6/π, vị trí = trung bình − γβ; hệ số bất đối xứng lý thuyết cố định xấp xỉ 1,139547, không phải một tham số tự do. Giữ công thức phân vị tương đương mã gốc.
8. Chuỗi hằng được xử lý với độ phân tán 0; chặn NaN/vô cực và P ngoài (0,100). Chu kỳ lặp = 100/P, bỏ ngoại lệ gán 0,33% chính xác bằng 300 năm.
9. Khi mở dự án, mô men được tính lại từ dữ liệu thay vì tin số tổng hợp đã lưu. Dự án Log-Pearson III cũ chưa ghi quy ước tham số sẽ được đặt lại tham số thích hợp bằng mô men log và báo cho người dùng kiểm tra.
10. Hệ số Kp trong bảng lý luận dùng giá trị trung bình của chuỗi gốc làm mẫu số, không lấy trung bình log làm mẫu số.

## Kiểm chứng

10 kiểm tra tự động: mô men, Pearson không lệch, Gumbel, Log-Pearson mô men, tham số nhập log, ba điểm của cả ba phân phối, dữ liệu log không hợp lệ, chuỗi hằng, miền P, Hazen.

Đã mở giao diện thực với Tk, tính bảng và tạo hình cho ba phân phối, thử tham số thích hợp, bảng kinh nghiệm, lưu/mở lại dự án Log-Pearson III và thu nhỏ cửa sổ.

Đối chiếu quy ước thư viện:
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearson3.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.gumbel_r.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.skew.html

Đây là kiểm tra công thức thống kê, chưa phải xác nhận tuân thủ một TCVN cụ thể. Nhãn TCVN chung trên cửa sổ được bỏ vì mã không chỉ rõ số hiệu và điều khoản. Cần lựa chọn phân phối theo đặc điểm chuỗi, đánh giá tính độc lập/đồng nhất, ngoại lai và mức độ khớp trước khi dùng số liệu thiết kế. Bản này chưa bổ sung khoảng tin cậy hoặc kiểm định độ khớp.

## Cách chạy trên Windows

Cài Python có Tkinter. Trong PowerShell:

```powershell
python -m pip install numpy scipy matplotlib
python .\TSTV-2026-V1-GiaoDien.py
python .\kiem_tra_tstv.py
```

Với phương pháp thích hợp của Log-Pearson III, phải nhập tham số trong miền log10, không nhập X trung bình và Cv của chuỗi gốc. Các dự án cũ được giữ nguyên tệp; hãy lưu bản dự án mới sau khi kiểm tra tham số.
