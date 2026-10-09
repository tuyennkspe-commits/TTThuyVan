# Kiểm tra phương pháp chia lưu vực từ DEM

Ứng dụng: `../ChiaLVthuyvan-V3.py`. Giữ cả thư mục `LuuVucDEM` cạnh tệp này khi chạy.

## Kết luận và phạm vi

Chuỗi xử lý hố trũng → vùng bằng → hướng dòng D8 → tích lũy dòng → lưu vực theo cửa xả là phương pháp GIS thủy văn thông dụng. Bản gốc có lỗi trong phép đo và ghép kết quả, nên chưa thể coi mọi thông số xuất ra là đúng. Bản sửa kiểm chứng bằng DEM giả lập; chưa có DEM thực tế của công trình để đối chiếu ranh giới khảo sát. Không xác nhận tuân thủ một tiêu chuẩn thiết kế cụ thể.

## Các điểm sửa

- Không đo diện tích/chiều dài theo tọa độ độ, không đoán CRS từ khoảng tọa độ, không tự gán EPSG:3405 hay WGS84 cho dữ liệu chưa biết. DEM cần CRS đã khai báo đúng. Lưới chiếu phẳng thẳng trục dùng mét được giữ; DEM địa lý, đơn vị khác hoặc lưới xoay được chuyển sang UTM tại tâm bằng rasterio trước khi tính D8. Cao độ DEM phải có đơn vị mét, cùng mốc cao độ; không tự suy hoặc đổi đơn vị đứng.
- Thêm bước fill_pits trước fill_depressions và resolve_flats. DEM gốc được dùng để tính cao độ và độ dốc, DEM hiệu chỉnh dùng để xác định đường thoát nước.
- Đọc NoData từ chính raster, loại cả mặt nạ hợp lệ và NaN/vô cực; không dùng ngưỡng cao độ −10000 để suy NoData. Raster có dữ liệu không hữu hạn chưa khai báo NoData bị từ chối.
- Bắt cửa xả theo ô tích lũy lớn nhất trong đủ cửa sổ 5×5, loại NoData, kiểm tra ngoài DEM và cửa xả trùng. Bản gốc cắt cửa sổ thiếu một hàng/cột. Khi tích lũy bằng nhau chọn ô gần điểm chấm nhất. Phạm vi bắt là 2 ô, không tự tìm sông ở khoảng cách vô hạn.
- Mỗi cửa xả tính **lưu vực toàn phần độc lập**, không bị lưu vực chọn sau ghi đè. Với cửa xả lồng nhau, lưu vực lớn chứa lưu vực nhỏ; đây không phải các tiểu lưu vực gia nhập loại trừ nhau. Màu bản đồ chỉ là lớp hiển thị; polygon và thống kê vẫn độc lập.
- Duyệt ngược D8 có kiểm tra ô hợp lệ và vòng lặp, gồm cả ô mép DEM. Qua thử nghiệm, catchment của pysheds 0.5 loại các hướng trên vành raster, nên không dùng nó để bỏ mất ô góp nước tại mép. Numba giúp duyệt toàn bộ lưu vực mà không phụ thuộc ngăn xếp đệ quy Python.
- Một cửa xả xuất một hình hợp các vùng ô của nó, tránh polygon rời bị tính như nhiều lưu vực. Diện tích = số ô hợp lệ × diện tích ô / 10⁶, đơn vị km².
- Độ dốc địa hình trung bình = trung bình độ lớn gradient DEM trong lưu vực, đơn vị ‰; khoảng cách ngang là kích thước ô mét. Cạnh NoData dùng sai phân một phía khi có dữ liệu, không lấy giá trị NoData làm cao độ. Đây là **độ dốc địa hình trung bình theo ô**, không tự thay cho độ dốc thủy lực hay công thức tổng chiều dài đường đồng mức của một tiêu chuẩn.
- Mạng sông gồm các ô góp nước ≥ ngưỡng nhập. Ngưỡng là số ô, diện tích góp tương ứng = ngưỡng × diện tích ô. Kết quả sông phụ thuộc độ phân giải và ngưỡng này.
- Sông chính là đường dài nhất trong **mạng sông theo ngưỡng** chảy đến cửa xả, không phải đường dòng dài nhất của toàn bộ lưu vực và không nhất thiết là tuyến sông được đặt tên ngoài thực địa. Đo chiều dài từ tâm ô tới tâm ô, tính đúng các bước chéo. Sông nhánh chỉ gồm các cạnh ngoài tuyến chính; không xuất cả mạng sông thành nhánh rồi lặp thêm sông chính.
- Tuyến sông xuất có ID lưu vực. Một đoạn có thể xuất riêng cho nhiều lưu vực toàn phần lồng nhau; đây là quan hệ sở hữu theo lưu vực, không phải chiều dài cần cộng gộp xuyên các lưu vực.
- Độ dốc sông = (cao độ đầu tuyến − cao độ cửa xả) / chiều dài × 1000. Đây là độ dốc dây cung trung bình, không phải độ dốc tương đương thủy lực/độ dốc đoạn dốc nhất. Không lấy trị tuyệt đối để che trường hợp cao độ ngược; trường hợp này hiện cảnh báo để kiểm tra DEM và làm đầy hố trũng.
- Chưa trích được tuyến sông thì cao độ nguồn và độ dốc sông là chưa xác định (NaN), không giả tạo bằng 0. Cao độ cửa xả luôn lấy từ DEM gốc.
- Bỏ làm tròn trong dữ liệu tính; dữ liệu GIS giữ độ chính xác. Đổi cửa xả/ngưỡng thì khóa xuất kết quả cũ. Lỗi nạp DEM không cho dùng lại kết quả trước.

## Kiểm chứng

11 kiểm tra tự động: mặt phẳng với NoData, diện tích và ngân sách chiều dài chính+nhánh, phạm vi bắt 5×5, ngoài DEM/NoData, không có sông, lưu vực lồng nhau, vòng dòng, chênh cao ngược, chuyển CRS/thiếu CRS, xử lý hố trũng và số ô lưu vực bằng tích lũy tại cửa xả.

Thử giao diện: nạp DEM giả lập, tính cửa xả lồng nhau theo hai thứ tự, polygon hợp lệ, xuất GeoJSON lưu vực/mạng sông và khóa kết quả cũ.

## Cách chạy

Trong thư mục kho, dùng Python có Tkinter:

```powershell
python -m pip install -r LuuVucDEM/requirements.txt
python ChiaLVthuyvan-V3.py
python LuuVucDEM/test_dem_hydrology.py
```

Lần đầu Numba có thể mất thời gian biên dịch. Dùng DEM đã cắt phù hợp nhưng bao trọn thượng lưu; lưu vực chạm mép DEM có thể bị cắt thiếu. Ngưỡng sông và vị trí cửa xả cần đối chiếu bản đồ/khảo sát. D8 và làm đầy DEM chưa mô tả cống, cầu, đê, dòng ngầm, trầm tích hay dòng phân tán. Phải xem lại các hố trũng tự nhiên trước khi coi việc làm đầy là hợp lý. Chuyển UTM tự động phù hợp vùng địa phương; với lưu vực lớn xuyên múi hoặc yêu cầu đo diện tích rất chính xác cần chuẩn bị hệ chiếu chuyên dụng và kiểm tra méo chiếu.

Tài liệu phương pháp/phần mềm:
- https://mattbartos.com/pysheds/dem-conditioning.html
- https://mattbartos.com/pysheds/flow-directions.html
- https://rasterio.readthedocs.io/en/stable/topics/reproject.html

