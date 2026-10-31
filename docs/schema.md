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
| `consents` | id, user_id, kind (≤32), version (≤32), granted, created_at | chỉ của mình | chỉ thêm (nhật ký, không sửa/xoá) |

## Hàm

- `delete_my_account()`: `security definer`, chỉ xoá chính người gọi (`auth.uid()`); cascade xoá watchlists/prefs/consents. Chỉ `authenticated` gọi được.
- `is_app_owner()`, `can_read_market(market)`: dùng trong policy. Chủ ứng dụng nằm ở bảng `app_owners` (không dùng claim JWT vì `user_metadata` do user tự sửa được).

## Hàm cho bot (RPC, chỉ `service_role` gọi được)

- `cleanup_old_data(keep_compact int default 96)`: xoá `signals`/`bars_30m` quá 30 ngày, `snapshot_meta` quá 60 ngày, giữ `keep_compact` slot mới nhất mỗi thị trường của `snapshot_compact`; trả jsonb số dòng đã xoá.
- `db_size_mb()`: dung lượng database (MB) để bot theo dõi hạn mức gói Free (500 MB).

## Ngân sách dung lượng (ƯỚC TÍNH, chưa đo trên dữ liệu thật)

Giả định ~1.600 mã (VN ~1.600 + US một danh sách nhỏ), 1 lần chạy/30 phút, ~14 slot/ngày mỗi thị trường:
`bars_30m` ≈ 1.600 × 14 × 30 ngày × ~100 B ≈ 65 MB; `signals` (một dòng/mã/lần chạy, jsonb nhỏ) ≈ 100-250 MB nếu ghi hết mọi mã,
nên bot chỉ nên ghi mã có tín hiệu; `quotes_latest`, `baseline_30m` (1.600 × 14 dòng), `bars_1d` (≈ 0,4 triệu dòng/năm, ~40 MB/năm) nhỏ.
Tổng mục tiêu dưới ~300 MB; dùng `db_size_mb()` để cảnh báo sớm khi vượt ~400 MB.

## Quy tắc đã khoá

- Mã VN và US trùng tên không đè nhau (khoá chính có `market`). Chạy lặp một slot không tạo dòng thứ hai (`unique (market, slot_start)`).
- Giá/khối lượng Mỹ chỉ chủ ứng dụng thấy; người khác chỉ thấy mức tín hiệu Mỹ qua `signal_levels`.
- Bot phải gửi `slot_start` khi ghi `snapshot_meta` (cột bắt buộc, dòng cũ đã backfill = `asof`).
- Test: `supabase/tests/rls.sql` (in `RLS OK`), kiểm đột biến: `docs/rls-mutation.md`.

## Giới hạn của bằng chứng kiểm thử

- `supabase/tests/local_shim.sql` DỄ hơn Supabase thật: kết nối bằng superuser, `auth.users` rút gọn (chỉ `id`, `email`), không có `auth.identities`/`auth.sessions`, không có trigger của GoTrue.
- Vì vậy job `rls` (`supabase start` + `db reset` + `rls.sql` trên GitHub Actions) mới là bằng chứng chính, và nó **CHƯA chạy**; job `mutation` chỉ chứng minh test đủ nhạy.
- `0002` chưa được áp ở project Supabase thật nào, nên được sửa thẳng thay vì thêm `0003`.
