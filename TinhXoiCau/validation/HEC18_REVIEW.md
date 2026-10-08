# Đối chiếu TTXoiCau_v4 với HEC-18, Fifth Edition (FHWA, 2012)

Nguồn: PDF **HEC No.18, 2012.pdf** người dùng cung cấp (340 trang). Số trang dưới đây là số in trong tài liệu. Kiểm tra này xác nhận các công thức đã triển khai trong phạm vi lòng dẫn hạt rời, dòng chảy mặt thoáng; không xác nhận toàn bộ các trường hợp thiết kế trong HEC-18.

## Các điểm đã sửa

- **§6.2–6.4, (6.1)–(6.4):** vận tốc tới hạn dùng D50 thực; giới hạn D50 = 0,2 mm chỉ áp dụng thành phần xói nước trong, có thông báo. Cho nhập riêng Q1 lòng chủ, y1 thượng lưu và y0 tại cầu. Vận tốc phân loại lấy Q1/(W1·y1). Chọn lớp bọc đáy rõ ràng thay cho tự suy từ D50 ≥ 20 mm.
- **§7.5.3–7.5.4, Hình 7.6–7.7, (7.24)–(7.27):** bộ công thức chuẩn chọn Case theo h2; giao diện dùng chế độ cố định theo cao độ ban đầu theo yêu cầu người dùng, không tự chuyển trường hợp sau xói. Hệ số K1 theo hình dạng bệ, K2 theo Lpc/apc gốc, Kw theo điều kiện của từng Case. Ks = D84 cho cát hoặc 3,5D84 cho sỏi/cuội; không tự suy D84 = 2D50. Case 2 không cộng thêm xói nhóm cọc và có lưu ý giả thiết móng không bị khoét dưới đáy bệ.
- **§7.5.5, Hình 7.10–7.13, (7.28)–(7.31):** hình chiếu cọc đều tính hợp các khoảng chiếu của hai hàng đầu và một cột. Có tùy chọn aproj nhập riêng cho bố trí đặc biệt. Km giới hạn sáu hàng, bằng 1 khi xiên dòng. Giới hạn y3 = 3,5apg* cho hệ số chiều cao và bước tính nhóm cọc theo ví dụ §7.10.4. Cọc tròn dùng K1 = 1; (7.31) không nhân K2.
- **§8.3–8.4:** không phát sinh xói mố khi vận tốc bằng 0. Mố mới cần nhập thủy lực Qe, Ae, ya, L′ thay vì tự dùng số liệu minh họa. L′ là chiều dài dòng chảy hoạt động bị chắn, có thể khác chiều dài hình học nền đường (ví dụ §8.7.1).
- **Thủy lực và tính nhất quán:** tích phân h^(5/3) liên tục cho đoạn mặt cắt tuyến tính tại mép nước. Hình chiếu thân/bệ dùng B|cosθ| + L|sinθ|. Trụ đơn đặc không bị cộng choán dòng bệ/cọc. Độ sâu và vận tốc tiếp cận trụ lấy tại thời điểm ban đầu từ PPLL. Kiểm tra số hữu hạn, kích thước, góc, số hàng/cột, tên trùng và diện tích thoát nước. Khi đầu vào đổi, xóa kết quả cũ và khóa xuất báo cáo đến khi tính lại.

## Công thức đúng cần giữ

Hình 7.6 dùng **(0,4075 − 0,0669·f/a)**, không phải dấu cộng như một công thức trong mẫu. Đồ thị bao gồm h1/a âm; không ép h1 về 0. Bảng 7.3 có các khoảng chiều cao cồn cát xấp xỉ **0,6–3–9 m**; giữ các khoảng này. K3 = 1,2 là đầu bảo thủ của khoảng 1,1–1,2 cho cồn trung bình.

## Kiểm chứng bằng ví dụ tài liệu

Chạy từ thư mục kho:

```powershell
python TinhXoiCau/validation/test_hec18.py
```

29 kiểm tra gồm bảy ví dụ dưới đây cùng các trường hợp biên, không cần mở giao diện.

| Ví dụ | Trang | Kết quả tài liệu / đối chiếu |
|---|---|---|
| §6.6.1, xói thu hẹp | 6.13–6.15 | y2 ≈ 17,2 ft; xói ≈ 10,1 ft |
| §7.10.1, trụ đơn | 7.27–7.28 | xói chưa giới hạn ≈ 9,9 ft; giới hạn trụ tròn thẳng dòng 9,6 ft |
| §7.10.2, góc 20° | 7.28 | K2 ≈ 2,86; xói ≈ 28,3 ft |
| §7.10.3, bệ lộ Case 2 | 7.28–7.30 | thân ≈ 0,6 ft; bệ ≈ 14,8 ft; tổng ≈ 15,4 ft |
| §7.10.4, bệ và cọc Case 1 | 7.30–7.33 | thân ≈ 3,2 ft; bệ ≈ 12,8 ft; cọc ≈ 21,24 ft |
| §8.7.1, Froehlich | 8.21–8.22 | L′ ≈ 42 ft, không dùng L = 75 ft; xói ≈ 13 ft |
| §8.7.2, HIRE | 8.22–8.23 | xói ≈ 33,9 ft |

Sai số kiểm tra cho phép do hệ số đọc đồ thị và làm tròn trong ví dụ. §7.10.3 dùng Kh ≈ 0,06 trong ví dụ, phương trình đồ thị cho ≈ 0,065. §7.10.4 đọc đồ thị apc*/apc ≈ 0,07, Ksp ≈ 0,58, Km ≈ 1,16, Khpg ≈ 0,79; phương trình giải tích cho các thành phần **3,266 / 13,116 / 21,521 ft**. Không sửa công thức để ép khớp số làm tròn. Dòng cộng tổng §7.10.4 dùng 3,7 ft thay cho thành phần thân 3,2 ft ở bước trước; kiểm tra từng thành phần tránh dựa vào bất nhất này.

Đã thử mở giao diện, hộp thoại trụ/mố, bảo toàn tổng Qi = Qtk, tính tám mố/trụ minh họa, xuất Word/Excel, từ chối đầu vào sai và ngăn xuất kết quả cũ. Báo cáo giữ 11 bảng Word và 14 sheet Excel theo mẫu; nội dung giải thích, phần công thức tĩnh, hình/OLE và định dạng của mẫu được giữ lại. Các hệ số và kết quả động phản ánh bộ tính mới. Vì yêu cầu giữ nguyên mẫu, dấu công thức tĩnh khác HEC nêu trên chưa được sửa trong tài liệu mẫu.

## Điều kiện còn cần kỹ sư kiểm tra

- Phân phối lưu lượng/độ sâu trong ứng dụng là xấp xỉ 1D, một hệ số nhám cho mặt cắt. W2 suy từ choán dòng bình quân chưa thay thế việc xác định riêng lòng chủ, bãi và phân phối dòng qua cầu bằng mô hình thủy lực. Các trường Q1, W1, y1, y0 cho phép cung cấp dữ liệu riêng khi phù hợp; với mặt cắt phức tạp cần mô hình chuyên dụng.
- Phần **nước dềnh** giữ phương pháp trong mẫu; hệ số a do người dùng chọn. Công thức này không được xem là công thức xói HEC-18 đã kiểm chứng. Không dùng kết quả này thay cho tính đường mặt nước của công trình.
- Cần đánh giá riêng dòng có áp/ngập dầm, đất dính, đá, rác bám, vật liệu phân tầng, dịch chuyển lòng sông; ứng dụng chưa triển khai các phương pháp HEC cho những trường hợp đó. Không coi kết quả hiện tại là chứng nhận thiết kế cho mọi tình huống.
- Kw có giới hạn thực nghiệm và cần phán đoán kỹ thuật (§7.4); tỷ số vượt đồ thị Kh, bệ tại h2 = 0 và giả thiết Case 2 cần người thiết kế xét. Hình chiếu tự động giả thiết lưới cọc đều, không mô tả được toàn bộ bố trí cọc lệch hàng.
- Dữ liệu khởi động là **minh họa**. Phải nhập số liệu thủy lực, cấp phối và hình học thực tế của công trình trước khi dùng kết quả.

## Bổ sung kiểm tra cao độ và lấy thủy lực từ PPLL

Trạng thái ban đầu được xác định bằng **CĐTN, cao độ đáy bệ, cao độ đỉnh bệ = đáy bệ + T, mực nước** và việc móng thực tế có bệ/cọc hay không:

| Quan hệ ban đầu | Trạng thái hình học |
|---|---|
| Đỉnh bệ ≤ CĐTN | Bệ/cọc còn chôn, chưa tiếp xúc dòng chảy |
| Đáy bệ ≤ CĐTN < đỉnh bệ | Có thể lộ bệ; chưa lộ đoạn cọc dưới đáy bệ |
| CĐTN < đáy bệ | Có thể lộ cọc dưới bệ; chỉ phần nằm dưới mực nước chịu dòng chảy |

Theo yêu cầu người dùng, tab **7.5 Cao độ ban đầu** chỉ thể hiện trạng thái tại CĐTN. Bệ còn chôn chỉ tính thân; bệ lộ nhưng đáy còn chôn tính thân và bệ; đoạn cọc dưới bệ lộ và ngập mới tham gia thành phần cọc. Kiểm tra thêm mực nước và hai lựa chọn cấu tạo Có bệ / Có cọc. Không đổi trường hợp do hạ thấp dài hạn, xói thu hẹp hoặc kết quả xói cục bộ. Các đại lượng hiệu chỉnh trong công thức vẫn được tính, nhưng không dùng để phân loại lại móng. Đây là phạm vi tính ban đầu được yêu cầu, không phải đánh giá đầy đủ diễn biến lộ móng trong HEC-18.

Nhập mố trực tiếp cần **ya, L′ và Ve**, hoặc **ya, L′, Qe, Ae** để suy Ve. Có thể cung cấp hai đại lượng Qe/Ae/Ve để suy đại lượng còn lại. Nếu chỉ biết Ve, Qe và Ae được giữ chưa biết, hiển thị dấu —. Không mặc định Ae = ya × L′: ví dụ §8.7.1 có bề rộng tính diện tích 75 ft trong khi L′ hoạt động khoảng 42 ft. Chỉ suy Ae hoặc ya từ bề rộng tính diện tích B khi người dùng cung cấp B. Đầu vào dư phải nhất quán, thiếu dữ liệu thì báo rõ; hỗ trợ dấu phẩy thập phân.

Trong hộp thoại mố, có công cụ **Tính PPLL & lấy thông số** theo đoạn X đầu–X cuối do người dùng xác định là dòng chảy bị chắn. Tích phân chỉ phần đoạn được chọn, kể cả cắt giữa hai điểm hoặc qua mép nước: Qe = tổng lưu lượng đoạn; Ae = diện tích ướt đoạn; L′ = tổng bề rộng dòng chảy hoạt động; ya = Ae/L′. Có thể tính PPLL trước khi nhập xong thủy lực mố, tránh việc bắt buộc có Qe/Ae mới được tạo bảng dùng để suy Qe/Ae. Lấy giá trị vào biểu mẫu rồi bấm Lưu; không tự chọn phạm vi M1–M2 hoặc dùng Q toàn sông. Đoạn PPLL này là ước tính 1D theo mặt cắt đã nhập; người dùng phải xác định phạm vi nền đường chắn dòng và tính đại diện cho mặt cắt thượng lưu.

Bộ kiểm tra gồm **29 kiểm tra**, bao gồm ví dụ tài liệu, quan hệ cao độ ban đầu, bệ/cọc không có thực, móng còn chôn dù kết quả xói lớn, các cách nhập mố và tích phân PPLL. Đã thử trực tiếp lấy/sửa/lưu thủy lực mố, vận tốc nhập riêng không cần giả tạo Qe/Ae, tính toàn hệ thống và xuất báo cáo.
