# Giới hạn cần giữ rõ

Trạng thái hiện tại của thí nghiệm lấy từ gate đã chạy, không từ sự tồn tại của mã nguồn. Trong giai đoạn chuẩn bị này chưa có xác nhận toàn bộ v8 hoàn tất.

- Zenodo và DOI được hoãn theo chỉ đạo trực tiếp của người dùng vì danh sách tác giả chưa chốt. Không tạo record và không công bố DOI.
- Chưa có đo chu kỳ Cortex-M hay MCU thật. Numba trên CPU phát triển không thay thế bằng chứng phần cứng nhúng hoặc worst-case execution.
- Chưa có sensor calibration và giới hạn sai số đồng hồ độc lập, nên không chứng nhận công suất vật lý ngoài interpolant tham chiếu.
- CRC chống lỗi ngẫu nhiên, không xác thực người gửi. Sparse audit chỉ cho cận dưới của sai số, không độc lập chứng nhận toàn bộ tín hiệu đã bỏ.
- Bridging qua vùng mất gói là uncertified. XOR được đánh giá recovery hồi cứu, không được diễn giải thành deadline trực tuyến đã đo.
- Iso-guard chỉ tối đa trên catalogue đã khai báo. Common ULEB recoding giữ nguyên decoded fields, không đồng nghĩa mọi decoder có cùng số trường hoặc cùng chi phí native.
- AMOVFLY chưa có giấy phép tái phân phối được xác minh. Public release không chứa raw archive, chuẩn bị lại các sample hay wire mang giá trị mẫu, mà yêu cầu người tái lập lấy dữ liệu gốc theo điều khoản nguồn.
- Solar là một campaign. Campaign span khác với thời gian hợp lệ sau gap split, và event/exposure hazard không tự suy ra completion cho mọi chuyến bay kéo dài hàng giờ.
