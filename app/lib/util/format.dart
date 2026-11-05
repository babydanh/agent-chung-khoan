/// Vietnamese number formatting: comma decimals, dot thousands, compact volume suffixes.
String _group(String digits) {
  final b = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) b.write('.');
    b.write(digits[i]);
  }
  return b.toString();
}

String fixed(double v, int decimals) {
  final neg = v < 0;
  final s = v.abs().toStringAsFixed(decimals);
  final parts = s.split('.');
  final out = decimals == 0 ? _group(parts[0]) : '${_group(parts[0])},${parts[1]}';
  return neg ? '−$out' : out;
}

/// Prices in the table: two decimals. Vietnamese boards quote whole dong, shown here in thousands.
String price(double? v, {bool vn = true}) {
  if (v == null) return '—';
  return fixed(vn && v >= 1000 ? v / 1000 : v, 2);
}

String percent(double? v) {
  if (v == null) return '—';
  final s = fixed(v.abs(), 2);
  if (v.abs() < 0.005) return '0,00%';
  return '${v > 0 ? '+' : '−'}$s%';
}

/// 6,10tr / 410k / 2,1 tỷ style compact quantity.
String volume(double? v) {
  if (v == null) return '—';
  final a = v.abs();
  final sign = v < 0 ? '−' : '';
  if (a >= 1e9) return '$sign${_trim(a / 1e9)} tỷ';
  if (a >= 1e6) return '$sign${_trim(a / 1e6)}tr';
  if (a >= 1e3) return '$sign${_trim(a / 1e3, 0)}k';
  return '$sign${a.toStringAsFixed(0)}';
}

String signed(double? v) {
  if (v == null) return '—';
  final t = volume(v.abs());
  return v > 0 ? '+$t' : v < 0 ? '−$t' : t;
}

/// Value in dong as billions: 800,3 tỷ.
String valueBillions(double? v) {
  if (v == null) return '—';
  return '${fixed(v / 1e9, 1)} tỷ';
}

String _trim(double v, [int decimals = 2]) => fixed(v, decimals);

String hhmm(DateTime? t) {
  if (t == null) return '—';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(t.hour)}:${two(t.minute)}';
}

String dayMonth(DateTime t) => '${t.day.toString().padLeft(2, '0')}/${t.month.toString().padLeft(2, '0')}';

String ago(DateTime? t, DateTime now) {
  if (t == null) return '—';
  final m = now.difference(t).inMinutes;
  if (m < 1) return 'vừa xong';
  if (m < 60) return '$m phút';
  if (m < 60 * 24) return '${m ~/ 60} giờ';
  return '${m ~/ (60 * 24)} ngày';
}
