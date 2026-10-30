# Đối chiếu prompt vòng 2

| Yêu cầu | Thay đổi | Bằng chứng sau khi chạy |
|---|---|---|
| Bước 0 | Giải nén gói v7 và chạy độc lập, so mọi wire, Tables 2–8 và 14 CSV | `audit/step0.json`, `audit/STEP0_VI.md` |
| M1 | Escape tuyến tính có cờ, endpoint binary64, kiểm tra lại decoded fields từ anchor đã phát thật | `encoders.py`, kết quả 120/full, bảng support |
| M2 | Tối đa chín cặp count lân cận, chọn theo byte rồi sai số, giữ nguyên chẩn đoán thất bại | `legacy_21_refusal_causes.csv`, main CSV |
| M3 | Horizon k=2/4 trên toàn prefix/full, oracle weighted-node theo byte thật | main CSV, bảng horizon, wire replay |
| E1 | Catalogue iso-guard đầy đủ, native wire và common ULEB không đổi decoded values, energy-aware Swing/Slide, Native32, SZ3 nếu cài được | baseline CSV và wires |
| E2 | Tập hoàn thành chung cả ba profile và effective byte có prefix phát dở, Dense restart hoặc escape | matched support CSV |
| E3 | Giữ đủ 36 test gốc, HL/CI, TOST, wild studentization, LOCO và phân nhóm aircraft/collector | statistics CSV và phụ lục |
| E4 | Solar toàn campaign streaming, modulo sequence, no-absolute-energy trên path khớp full/Solar 30 phút | solar gate, drift CSV |
| P1 | Datagram m=1/4/16, Bernoulli/GE, repeat/XOR, EOS, certified duration, anchor availability và bridging uncertified | loss parquet, replicate CSV và SD |
| P2 | Receiver shape/order khác với sender eP/eE assertions, CRC16/32 và audit midpoint thưa | receiver/CRC CSV |
| P3 | Khớp first-episode raw adapter, đo sai khác hai PL references và cận tam giác | preprocessing CSV và gate |
| P4 | Numba không fastmath, đối chiếu kernel, thời gian từng guard và full encoder | kernel gate và timing CSV |
| P5 | Grid 3×3 power×energy, strict/escape, completion và effective byte rate | heatmap CSV/PDF |
| P6 | Code/results công khai khi đã kiểm chứng và quét secret, dữ liệu ngoài giữ điều khoản gốc | trạng thái public release thật, không DOI |

Các thí nghiệm trong bảng đã chạy và kết quả được đối chiếu bằng gate thực tế. Kiểm chứng sau cùng đã giải mã 24.080 wire, kiểm tra 2.146.616 đoạn liên tục và 16.089 đoạn escape, giữ nguyên 236 file v7 cùng 273 file bảo vệ của Paper 4. Chi tiết số mới và các kết quả bất lợi nằm trong `KET_QUA_V8_VI.md`.

Abstract, Introduction và Related Work giữ nguyên văn. Các lỗi exponent ZFP và clock Solar có amendment riêng, checkpoint lỗi được lưu và không trộn vào kết quả chính. TOST Swing thường là bổ sung exploratory sau khi đã xem kết quả, tách biệt họ energy-aware Swing đã khai báo trước. Tên journal được viết tắt, danh sách tác giả tham khảo dài dùng et al. và DOI bài báo được lược khỏi PDF để tiết kiệm chỗ; metadata cùng liên kết đầy đủ vẫn được lưu trong bằng chứng.

Repo công khai được xác minh bằng commit trong `audit/public_release.json`. Không phát hành raw source hay bản thảo/tác giả chưa chốt, không tạo Zenodo hoặc DOI. Chưa đo MCU, không khẳng định tiết kiệm năng lượng vô tuyến. Trạng thái PDF và ZIP sau cùng phải lấy từ audit render, visual review và package.
