# Kiểm "đột biến" cho RLS

Mục đích: chứng minh `supabase/tests/rls.sql` thật sự bắt được lỗi phân quyền. Mỗi lần script cố ý làm hỏng
MỘT policy/grant (ví dụ đổi `using (user_id = auth.uid())` thành `using (true)`, bỏ policy, cho `anon` đọc
bảng, làm `delete_my_account()` xoá hết) rồi chạy `rls.sql`; test phải **đỏ**. Nếu test vẫn in `RLS OK`
thì test quá yếu (mutant "sống sót") và script thoát mã 1.

## Cách chạy

Cần Docker, không cần Supabase thật và không cần khoá nào:

```bash
supabase/tests/mutate.sh
```

Script dựng một Postgres tạm (`postgres:17-alpine` ghim digest, khớp `major_version` trong `supabase/config.toml`; đổi bằng `PG_IMAGE=...`), nạp `supabase/tests/local_shim.sql`
(vai trò `anon`/`authenticated`/`service_role`, `auth.users`, `auth.uid()`), áp mọi file trong
`supabase/migrations/`, rồi:

1. Chạy `rls.sql` nguyên bản: phải in `RLS OK`.
2. Với từng đột biến trong mảng `mutations` của `mutate.sh`: tạo DB mới, áp migration, áp đột biến,
   chạy `rls.sql`: phải lỗi. Dòng `caught:` là đạt, `SURVIVED` là lỗi.

Kết quả mong đợi cuối cùng: `all mutations caught`. Cũng chạy trong CI (job `mutation` của `db-test.yml`).

## Thêm đột biến mới

Thêm một câu SQL vào mảng `mutations` (hàm `rewrite 'hàm' 'regex' 'thay'` sửa một dòng trong thân hàm; chuỗi rỗng cho `search_path` viết `'"''"'` trong dấu nháy đơn của bash). Lỗi khi áp đột biến được báo là `SETUP ERROR`, không tính là bắt được. Lưu ý các bảng đã `revoke` quyền của `anon`/`authenticated`: chỉ thêm policy
thì chưa đủ để mở (đó là lớp phòng thủ thứ hai), phải kèm `grant ...` như các ví dụ có sẵn. Đột biến chỉ đổi
policy `update`/`delete` của `watchlists` cũng phải kèm policy `select` mở, vì Postgres cần thấy dòng mới sửa/xoá được.

## Giới hạn

Chạy trên Postgres thường với shim, không phải image Supabase thật; khác biệt thật (extension, trigger của
GoTrue trên `auth.users`) chỉ được kiểm ở job `rls` (Supabase CLI) trên GitHub Actions.
