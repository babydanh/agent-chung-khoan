# Checklist dựng hệ thống (làm một lần)

Code đã đủ để chạy; còn lại là các bước cần quyền của chủ project. Không ghi khoá thật vào file nào trong repo.

## 1. Supabase (project thật)
1. Tạo project (vùng Nhật). Chạy `SHOW server_version;` rồi so với `supabase/config.toml` (`major_version`, hiện 17); lệch thì sửa `config.toml` và `mutate.sh`.
2. **Tắt Anonymous sign-ins** (Authentication → Sign In / Providers).
3. Áp migration theo thứ tự: `0001_init.sql`, `0002_market_and_app_tables.sql`, `0003_anon_reads_vn.sql` (SQL Editor hoặc `supabase db push`).
4. Chạy `supabase/tests/rls.sql` trong SQL Editor: phải thấy `RLS OK` (nó rollback hết).
5. Thêm chủ ứng dụng (xem được dữ liệu Mỹ): đăng nhập một lần, rồi `insert into public.app_owners values ('<uuid của bạn>');`.
6. Lấy `Project URL` và **secret key** (không phải publishable/anon key) cho bot.

## 2. GitHub (repo bot)
1. Các workflow đã nằm sẵn ở `.github/workflows/`. Workflow chạy theo lịch (`snap-vn`, `snap-us`, `eod`) chỉ chạy khi repo có biến **BOT_ENABLED = true** (Settings → Secrets and variables → Actions → tab Variables → New repository variable). Đặt biến này SAU khi đã đặt các secret bên dưới.
2. Secrets của repo: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` (Alpaca, thị trường Mỹ), `ANTHROPIC_API_KEY` (bản tin; hoặc thay bằng `CLAUDE_CODE_OAUTH_TOKEN` lấy từ `claude setup-token`, bản tin sẽ chạy qua lệnh `claude` gốc. Có cả hai thì dùng API key. Rủi ro điều khoản gói: xem https://code.claude.com/docs/en/legal-and-compliance), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (báo lỗi).
3. Chạy tay `snap-vn` bằng `workflow_dispatch` trong giờ chạy (9:00–15:40 giờ VN) rồi xem `snapshot_meta`, `quotes_latest`, `heartbeat` có dòng chưa. Lịch tự chạy bật ngay khi workflow có trên nhánh mặc định.
4. Job `rls` của `db-test.yml` trên GitHub chưa từng chạy: xem kết quả lần đầu.

## 3. Việc code CHƯA có (đừng chờ nó chạy)
- **Gửi push thật**: `pipeline/push.py` chỉ quyết định nội dung/thời điểm; `bulletin.py` ghi quyết định vào `heartbeat.detail.push`. Chưa có kênh gửi (FCM/…) và chưa có hàng đợi giữ bản Mỹ 22:00–07:00 đến 07:00.
- **S4/S5** (giá so với ATR, gap mở cửa Mỹ) chưa bật vì chưa có nguồn nến ngày cho `bars_1d` (`docs/s4-s5-pending.md`).
- **Model ID**: `pipeline/agent.py` đặt `MODEL = "claude-haiku-5-5"` (test cố định giá trị này). Nếu API trả 400/404 thì mỗi lần chạy bản tin sẽ đỏ (chủ ý, để thấy lỗi cấu hình) và dùng bản tin dự phòng do code dựng. Kiểm tên model với tài khoản Anthropic của bạn trước lần chạy đầu; PR #4 từng ghi `claude-haiku-5-5` không tồn tại và dùng `claude-haiku-4-5`. Nếu đổi: sửa `MODEL` và hai test ghim giá trị.
- Ứng dụng (đọc `digests`, `news`, realtime `snapshot_meta`) không nằm trong repo này.
