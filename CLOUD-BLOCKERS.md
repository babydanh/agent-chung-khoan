# CLOUD-BLOCKERS (không commit)

## Nhóm 2
- Workflow: token máy không có quyền `workflow` (push bị từ chối: "refusing to allow a Personal Access Token to create or update workflow ... without `workflow` scope"). Đã đặt `snap-vn.yml`, `snap-us.yml`, `eod.yml`, `ci.yml` ở `ci-pending/workflows/`. Cần người chép sang `.github/workflows/` (và đặt secret SUPABASE_URL, SUPABASE_SECRET_KEY, APCA_API_KEY_ID, APCA_API_SECRET_KEY).
- VCI: probe chỉ xác nhận 3 khoá cấp 1 (bidAsk, listingInfo, matchPrice). Tên khoá bên trong (accumulatedVolume, foreignBuyVolume, ...) là phỏng theo bảng giá Vietcap, chưa kiểm với phản hồi thật; PTQ/PTV đặt 0 ở nguồn VCI. Cần chạy lại probe in khoá cấp 2.
- Supabase: `supabase/` trên main còn bản 0001 (draft, "superseded by 0002" chưa có). run.py ghi theo 0001 (quotes_latest, snapshot_meta, bars_30m, signals). Thiếu: bảng `heartbeat` (market, asof, status) và hàm RPC `db_size_mb()`; run.py/cleanup.py chỉ log cảnh báo khi thiếu, không hỏng.
- ATR/S4/S5: chưa có nguồn nến ngày nên run.py chưa truyền `atr` vào evaluate, S4/S5 chưa chạy thật (logic và test đã có ở nhóm 1).
- config/symbols.json: danh sách mã VN/US do tôi tự chọn (đại diện), cần người xác nhận/thay.
- US: khối `US` trong thresholds.json là số tạm; Alpaca feed `iex` chỉ tính khối lượng sàn IEX; khoá env dùng tên APCA_API_KEY_ID / APCA_API_SECRET_KEY.

## Nhóm 3
- Model: `claude-haiku-5-5` không có trong bảng model hiện hành (Haiku mới nhất là `claude-haiku-4-5`). agent.py dùng `claude-haiku-4-5` (hằng MODEL). Haiku 4.5 trả lỗi nếu gửi `effort`, và thinking mặc định đã tắt, nên "effort low" chỉ được gửi cho model hỗ trợ (sonnet/opus...). Cần người chốt model.
- ANTHROPIC_API_KEY: không có khoá trên máy; chỉ test bằng phản hồi giả. Chưa kiểm schema `output_config.format` với API thật.
- RSS: URL 3 nguồn (CafeF, Vietstock, VnExpress Kinh doanh) tôi chưa gọi thử; cần kiểm lại khi có mạng.
- push.py: hiểu "không chữ số" là không có số nào ngoài giờ HH:mm; chặn bản Mỹ theo giờ lúc gửi (22:00–07:00 giờ VN). Chưa nối FCM.
- Chưa có chỗ gọi: news/agent/push chưa được run.py gọi (chỉ là module + test); cần phiên sau nối vào luồng bản tin.

## Review fixes, nhóm B
- `db_size_mb()`: lần merge đầu chưa có; sau lần merge thứ hai (supabase-ci 9cd6733) đã có trong 0002, cùng `cleanup_old_data()` giữ bars_30m/signals 30 ngày. Còn lệch: bot cleanup.py giữ bars_30m 40 phiên, hàm SQL xoá ở 30 ngày — nếu cả hai chạy thì 30 ngày thắng; cần người chốt một nguồn.
- Lịch VN 2027: chỉ thêm ngày tính được theo luật cố định: 2027-04-30, 2027-05-03 (bù Chủ nhật 1/5... thực tế 1/5/2027 là Thứ Bảy, nghỉ bù thứ Hai 3/5), 2027-09-02. CHƯA có: Tết Nguyên đán 2027 (khoảng 6/2/2027, UBCK chưa công bố lịch), Giỗ Tổ Hùng Vương 10/3 âm lịch 2027, ngày liền kề 2/9 (1/9 hoặc 3/9 do Thủ tướng chọn hằng năm). Cần người cập nhật khi có thông báo; trong lúc thiếu, cổng "đóng cửa" sẽ thoát 1 vào ngày nghỉ chưa liệt kê (đúng ý B3).
- Lịch Mỹ 2027 theo quy tắc NYSE (Thanksgiving 25/11, Giáng sinh rơi Thứ Bảy → nghỉ Thứ Sáu 24/12, Juneteenth Thứ Bảy → nghỉ 18/6, Quốc khánh Chủ nhật → nghỉ 5/7, Good Friday 26/3). Chưa đối chiếu với lịch NYSE công bố; early_close chỉ có 26/11/2027 (không chắc 2/7/2027).
- B10: chọn ghi docs (docs/s4-s5-pending.md), không nối ATR vì chưa có nến ngày (bars_1d chưa ai ghi).
- Bắt buộc trong B3: lượt VN 15:05 và lượt Mỹ 16:50 (cửa sổ 0 phút giao dịch) được miễn cổng "đóng cửa".

## Review fixes, nhóm C
- C1: không chặn từ `lan` (không dấu) vì "lan tỏa" là cụm hợp lệ hay gặp trong bản tin; chặn `lần`, `mười`, `mươi`, `chục`... có dấu và các dạng không dấu `mot/hai/ba/bon/chin/muoi/chuc/tram/trieu/nghin/ngan/ty/ti/nua`. Không chặn `sau/nam/tam/bay` không dấu (từ thường). Hệ quả: câu có "một số", "năm nay", "lần đầu" bị bỏ (đúng yêu cầu "một…chín"); prompt đã dặn model không viết số.
- C3: `dang mua` khớp cả "đang mua" (sau khi bỏ dấu), nên tiêu đề "khối ngoại đang mua mạnh" cũng bị chặn; theo yêu cầu, chấp nhận báo động nhầm.
- C4: tin không có `pubDate` được giữ (không biết tuổi); tin có ngày cũ hơn 3 ngày bị lọc.
- C5: `push.build` nay trả `status` "send"/"defer" kèm `send_at` (07:00 giờ VN). Chưa có hàng đợi để phát lại bản hoãn; từ 01/11 cả 14 lượt Mỹ đều hoãn, khi có hàng đợi nên gộp thành một thông báo.

## Vòng 3, nhóm B (PR #3)
- B10: bước `Alert on failure` chạy bằng `python3 -m pipeline.alert` nên cần checkout thành công; nếu chính bước checkout lỗi (GitHub sự cố) thì không có cảnh báo, nhưng eod (B11) sẽ thấy thiếu lượt. `if: failure()` cũng không phủ trường hợp job bị CANCEL (hàng đợi concurrency bị huỷ): eod bắt trường hợp đó qua đếm lượt thiếu. Cần người đặt 2 secret `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (token/chat id chưa có, chưa thử gửi thật).
- B11: eod chạy 18:00 giờ VN, kiểm ngày giao dịch gần nhất đã kết thúc của từng thị trường (VN: hôm nay; Mỹ: hôm qua giờ New York). Lượt Mỹ cuối (16:50 ET) xong lúc ~03:50 giờ VN hôm sau nên ngày Mỹ luôn được kiểm trễ một ngày: một lượt Mỹ chết chỉ bị bắt vào 18:00 hôm sau, không phải trong ngày.
- B12: không đổi, S4/S5 vẫn chờ nến ngày (docs/s4-s5-pending.md); nhánh chưa có nguồn nến ngày.
- Workflow vẫn nằm ở ci-pending/workflows/ vì token máy không có quyền `workflow`.

## Vòng 3, nhóm G (PR #4)
- G6: đã đặt MODEL = `claude-haiku-5-5` theo yêu cầu (thinking `disabled`, effort `low`, JSON schema, không còn rẽ nhánh theo tiền tố). Bằng chứng tôi KHÔNG xác minh được: bảng model đệm trong skill claude-api (ngày 2026-09-25) và môi trường phiên này chỉ liệt kê Haiku 4.5 là Haiku mới nhất, và không có khoá API để thử. Nếu API từ chối id (400/404), `make_bulletin` trả `fatal` + `reason=config_error:<status>`, `exit_code` = 1: chạy đỏ chứ không âm thầm dùng mẫu. Cũng chưa biết Haiku 5.5 có nhận `thinking: {type: "disabled"}` + `effort` hay không: nếu 400 sẽ lộ ra ngay ở lần chạy thật đầu tiên.
- G7: chưa có hàng đợi push cho bản "hoãn" (docstring đã sửa nói rõ người gọi phải giữ và gửi lúc `send_at`).
- G8: `news`, `agent`, `push` CHƯA được nối vào `run.py`. Lý do: nhánh chưa có thiết kế luồng bản tin (chạy khi nào, lưu bản tin ở bảng `digests`, ai gọi `push`). `agent.heartbeat_detail()` và `agent.exit_code()` đã sẵn để nối: reason của bản tin dự phòng vào detail của heartbeat, lỗi cấu hình làm job đỏ rồi bước Telegram báo.
- G1/G2 hệ quả: guard chặn cả "không", "một", "năm", "lần", "hai", "ba" (đúng yêu cầu) nên model phải viết câu không dùng các từ này; câu có từ đó bị bỏ và rơi về bản tin mẫu của code. Chưa đo tỷ lệ bỏ với model thật.
- G4: mọi từ viết hoa 2–5 chữ cái (trừ VN, US) và mọi mã trong config/symbols.json (không phân biệt hoa thường) đều bị coi là mã viết trần. Danh sách mã chỉ gồm những mã trong symbols.json; mã ngoài danh sách chỉ bị bắt nếu viết hoa.
