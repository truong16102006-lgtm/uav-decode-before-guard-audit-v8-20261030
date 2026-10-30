# Kiểm tra bổ sung ngày 31/10/2026

Vấn đề: phát hiện endpoint cuối bị mất chỉ có ý nghĩa khi phân biệt footer còn tới và footer cũng bị mất.

Đã đối chiếu trực tiếp 21.180 lượt record–replicate không gồm Solar trong benchmark 120 giây, với Bernoulli p=0,1, một checkpoint mỗi datagram và không bảo vệ. Trong từng replicate, gộp các sự kiện terminal erasure rồi mới tính tỷ lệ. Qua 30 replicate:

- Có footer tới: phát hiện 100,0% ± 0,0% endpoint cuối bị mất.
- Không điều kiện hóa việc footer tới: phát hiện 89,3% ± 4,0%.

Đây là mean ± sample SD của mô phỏng trên corpus cố định, không là bảo đảm truyền vô tuyến. Mọi sự kiện được phát hiện đều khớp terminal erasure thật và footer đã nhận. Nếu footer mất thì trạng thái kết thúc vẫn chưa biết.

Mã tái lập: `python -X utf8 development_v8/code/followup_audit.py`. Kết quả đọc từ Parquet đã chạy, không mô phỏng lại để chọn seed thuận lợi và không sửa wire hoặc số liệu gốc. Bản thảo bổ sung định lượng đúng mẫu số.
