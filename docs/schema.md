# Lược đồ Supabase (migration 0001 + 0002)

Ghi: **bot** = khoá secret/service (bỏ qua RLS). **App** = người dùng đã đăng nhập (`authenticated`). `anon` không đọc/ghi được bảng nào.
`market` luôn là `'VN'` hoặc `'US'`. Chủ ứng dụng = user có dòng trong `app_owners`.

## Dữ liệu thị trường (chỉ bot ghi; app không có policy insert/update/delete)

| Bảng | Khoá | Cột chính | App đọc | Bot |
|---|---|---|---|---|
| `quotes_latest` | (market, symbol) | exchange, price, ref/ceil/floor_price, vol, val, f_buy, f_sell, f_room, pt_vol, pt_val, asof | VN: mọi user; US: chỉ chủ | ghi |
| `snapshot_meta` | id; unique (market, slot_start) | market, asof, slot_start, symbols, signals | mọi user (realtime) | ghi |
| `signals` | (market, asof, symbol) | level 0-3, learning, items (jsonb) | VN: mọi user; US: chỉ chủ | ghi |
| `signal_levels` (view) | - | market, asof, symbol, level, learning | mọi user, gồm US (không có items/giá) | - |
| `bars_1d` | (market, symbol, trade_date) | open, high, low, close, vol, val | VN: mọi user; US: chỉ chủ | ghi |
| `zones` | id | market, symbol, kind, price_lo, price_hi, asof | VN: mọi user; US: chỉ chủ | ghi |
| `digests` | id; unique (market, digest_date, kind) | body, created_at | VN: mọi user; US: chỉ chủ | ghi |
| `news` | id; unique url | market, symbol, title, url, source, published_at | VN: mọi user; US: chỉ chủ (lọc luôn cho nhất quán) | ghi |

## Bảng nội bộ của bot (RLS bật, không policy: app không đọc, không ghi)

| Bảng | Khoá | Cột chính |
|---|---|---|
| `bars_30m` | (market, symbol, bar_start) | vol, val, fnet, pt_val |
| `baseline_30m` | (market, symbol, slot) | days, avg_vol, avg_val, avg_fnet, avg_pt_val, updated_at |
| `heartbeat` | (market, job) | last_seen, detail |
| `snapshot_compact` | (market, slot_start) | payload (jsonb) |
| `app_owners` | user_id | danh sách chủ ứng dụng (chỉ bot sửa) |

## Dữ liệu người dùng (FK `user_id` → `auth.users`, `on delete cascade`, có index `user_id`)

| Bảng | Cột chính | User đọc | User ghi |
|---|---|---|---|
| `watchlists` | id, user_id, market, symbol (≤12 ký tự); unique (user_id, market, symbol) | chỉ của mình | thêm/sửa/xoá của mình; tối đa 200 dòng/người |
| `prefs` | user_id, data (jsonb ≤ 8192 byte), updated_at | chỉ của mình | thêm/sửa của mình |
| `consents` | id, user_id, kind (≤32), version (≤32), granted, created_at | chỉ của mình | chỉ thêm (nhật ký, không sửa/xoá); tối đa 100 dòng/người |

## Hàm

- `delete_my_account()`: `security definer`, chỉ xoá chính người gọi (`auth.uid()`); cascade xoá watchlists/prefs/consents. Chỉ `authenticated` gọi được.
- `is_app_owner()`: dùng trong policy (`market = 'VN' or (select public.is_app_owner())`). Vì không có cột nào của dòng trong lời gọi, planner coi nó là InitPlan (chạy một lần mỗi truy vấn; `EXPLAIN` hiện `Filter: ((market = 'VN') OR (InitPlan 1).col1)`); `rls.sql` kiểm kế hoạch này cho 6 bảng. Một hàm nhận cột `market` của dòng sẽ thành SubPlan chạy từng dòng. Chủ ứng dụng nằm ở bảng `app_owners` (không dùng claim JWT vì `user_metadata` do user tự sửa được).

## Hàm cho bot (RPC, chỉ `service_role` gọi được)

- `cleanup_old_data(keep_compact int default 96)`: xoá theo bảng retention dưới đây, giữ `keep_compact` slot mới nhất mỗi thị trường của `snapshot_compact`; trả jsonb số dòng đã xoá mỗi bảng.

### Retention (nguồn sự thật duy nhất là `cleanup_old_data` trong 0002; bot không tự xoá theo số khác)

| Bảng | Giữ | Cột tính tuổi |
|---|---|---|
| `signals` | 30 ngày | `asof` |
| `bars_30m` | **45 ngày** | `bar_start` |
| `snapshot_meta` | 60 ngày | `asof` |
| `zones` | 30 ngày | `asof` |
| `news` | 90 ngày | `published_at` |
| `digests` | 90 ngày | `created_at` |
| `heartbeat` | 30 ngày | `last_seen` |
| `snapshot_compact` | `keep_compact` slot mới nhất/thị trường | `slot_start` |

`bars_30m`: bot giữ 40 phiên, nhưng 20 phiên có thể trải hơn 30 ngày lịch quanh Tết, nên SQL dùng 45 ngày (số này thắng; nếu bot đổi số phiên thì sửa ở SQL). `baseline_30m`, `bars_1d`, `quotes_latest` không bị xoá (ghi đè hoặc nhỏ).
- `db_size_mb()`: dung lượng database (MB) để bot theo dõi hạn mức gói Free (500 MB).

## Ngân sách dung lượng (ƯỚC TÍNH, chưa đo trên dữ liệu thật)

Giả định ~1.600 mã (VN ~1.600 + US một danh sách nhỏ), 1 lần chạy/30 phút, ~14 slot/ngày mỗi thị trường:
`bars_30m` ≈ 1.600 × 14 × 45 ngày × ~100 B ≈ 100 MB; `signals` (một dòng/mã/lần chạy, jsonb nhỏ) ≈ 100-250 MB nếu ghi hết mọi mã,
nên bot chỉ nên ghi mã có tín hiệu; `quotes_latest`, `baseline_30m` (1.600 × 14 dòng), `bars_1d` (≈ 0,4 triệu dòng/năm, ~40 MB/năm) nhỏ.
`news`/`digests`/`zones` giữ 30-90 ngày, nhỏ so với hai bảng trên. Tổng mục tiêu dưới ~300 MB; dùng `db_size_mb()` để cảnh báo sớm khi vượt ~400 MB.

## Quy tắc đã khoá

- Mã VN và US trùng tên không đè nhau (khoá chính có `market`). Chạy lặp một slot không tạo dòng thứ hai (`unique (market, slot_start)`).
- Giá/khối lượng Mỹ chỉ chủ ứng dụng thấy; người khác chỉ thấy mức tín hiệu Mỹ qua `signal_levels`.
- Bot phải gửi `slot_start` khi ghi `snapshot_meta` (cột bắt buộc, dòng cũ đã backfill = `asof`).
- Giới hạn tổng số dòng theo người dùng: `watchlists` 200, `consents` 100 (trigger + advisory lock theo user; chưa có test song song, cùng cơ chế với `watchlists_cap`).
- Test: `supabase/tests/rls.sql` (in `RLS OK`), kiểm đột biến: `docs/rls-mutation.md`.

## Checklist cho project Supabase thật (làm một lần, trước khi cho người dùng vào)

- [ ] **Tắt Anonymous sign-ins**: Dashboard → Authentication → Sign In / Providers → tắt "Allow anonymous sign-ins", hoặc đặt `enable_anonymous_sign_ins = false` trong `supabase/config.toml` rồi chạy `supabase config push`. `config.toml` chỉ có tác dụng với stack local/CI, **không tự đổi project thật**. Người dùng ẩn danh nhận vai trò `authenticated`, nên nếu để bật họ tạo tài khoản vô hạn và vượt các giới hạn theo tài khoản (200 watchlist, 100 consent) cũng như đọc được dữ liệu VN.
- [ ] Chạy `SHOW server_version;` trên project thật và so với `major_version` trong `supabase/config.toml` (xem "Phiên bản Postgres" dưới đây).
- [ ] Áp migration, rồi chạy `supabase/tests/rls.sql` (phải in `RLS OK`).

## Phiên bản Postgres

Supabase CLI 2.122.0 chỉ chấp nhận `db.major_version` = 13, 14, 15 hoặc 17 (đọc `apps/cli-go/pkg/config/config.go`; 16 báo lỗi `Invalid db.major_version`), và template mặc định là 17, cũng là bản project mới tạo dùng. Tài liệu này trước đây không ghi phiên bản của project thật, nên chọn **17**: `config.toml` (`major_version = 17`) và `mutate.sh` (`postgres:17-alpine`) khớp nhau. **Chưa xác nhận** với project thật (checklist ở trên); nếu project là 15 thì đổi cả hai chỗ về 15.

## Giới hạn của bằng chứng kiểm thử

- `supabase/tests/local_shim.sql` DỄ hơn Supabase thật: kết nối bằng superuser, `auth.users` rút gọn (chỉ `id`, `email`), không có `auth.identities`/`auth.sessions`, không có trigger của GoTrue.
- Vì vậy job `rls` (`supabase start` + `db reset` + `rls.sql` trên GitHub Actions) mới là bằng chứng chính, và nó **CHƯA chạy**; job `mutation` chỉ chứng minh test đủ nhạy.
- `0002` chưa được áp ở project Supabase thật nào, nên được sửa thẳng thay vì thêm `0003`.
