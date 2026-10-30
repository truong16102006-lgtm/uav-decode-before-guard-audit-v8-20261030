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

Đây là kế hoạch đối chiếu mã và bằng chứng, không phải xác nhận rằng các thí nghiệm v8 đã chạy xong. Trạng thái hoàn tất chỉ lấy từ các gate đã sinh thật và kiểm tra PDF sau cùng. Abstract, Introduction và Related Work giữ nguyên văn. Không sửa các câu mở đầu chỉ để làm kết quả mới thuận lợi hơn.
