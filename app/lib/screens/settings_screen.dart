import 'package:flutter/material.dart';

import '../data/supabase_repository.dart';
import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../util/format.dart' as f;
import '../widgets/common.dart';
import 'inbox_screen.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    Widget row(String icon, String label, {String? value, VoidCallback? onTap}) => Semantics(
          button: onTap != null,
          child: InkWell(
            onTap: onTap,
            child: SizedBox(
              height: 56,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
                child: Row(children: [
                  AppIcon(icon, size: 20, color: c.text2),
                  const SizedBox(width: Sp.s3),
                  Expanded(child: Text(label, style: AppText.base(c.text))),
                  if (value != null) Flexible(child: Text(value, maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.num(c.text2, size: Ts.s, weight: FontWeight.w400))),
                  if (onTap != null) ...[const SizedBox(width: 4), AppIcon('chev', size: 18, color: c.text3)],
                ]),
              ),
            ),
          ),
        );
    return SafeArea(
      bottom: false,
      child: ListView(children: [
        Padding(padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s4, Sp.s4, 0), child: Text('Cài đặt', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))),
        const SectionTitle('Giao diện'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
          child: Row(children: [
            Segmented<ThemeMode>(value: s.themeMode, options: const [(ThemeMode.dark, 'Tối'), (ThemeMode.light, 'Sáng')], onChanged: s.setTheme),
            const SizedBox(width: Sp.s3),
            Segmented<Market>(value: s.defaultMarket, options: const [(Market.vn, 'VN'), (Market.us, 'US')], onChanged: s.setDefaultMarket),
          ]),
        ),
        const SectionTitle('Dữ liệu'),
        row('refresh', 'Nguồn', value: s.demo ? 'Mẫu' : 'Supabase', onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ConnectionScreen()))),
        row('clock', 'Tình trạng', onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const DataStatusScreen()))),
        const SectionTitle('Thông báo'),
        row('bell', 'Hộp thư và lọc', onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const NotifySettings()))),
        Padding(padding: const EdgeInsets.all(Sp.s5), child: Text('Chỉ là thông tin, không phải khuyến nghị đầu tư.', textAlign: TextAlign.center, style: AppText.base(c.text3, size: Ts.xs))),
        Center(child: Text('Phiên bản 0.1.0', style: AppText.num(c.text3, size: Ts.xs, weight: FontWeight.w400))),
        const SizedBox(height: Sp.s5),
      ]),
    );
  }
}

/// Connection to the database: URL, public (anon) key and the owner's login. Kept on this device only.
class ConnectionScreen extends StatefulWidget {
  const ConnectionScreen({super.key});

  @override
  State<ConnectionScreen> createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends State<ConnectionScreen> {
  late final TextEditingController _url, _key, _mail, _pass;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final c = AppScope.read(context).connection;
    _url = TextEditingController(text: c.url);
    _key = TextEditingController(text: c.anonKey);
    _mail = TextEditingController(text: c.email);
    _pass = TextEditingController(text: c.password);
  }

  @override
  void dispose() {
    for (final t in [_url, _key, _mail, _pass]) {
      t.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    Widget field(String label, TextEditingController ctl, {bool secret = false, TextInputType? type}) => Padding(
          padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s3, Sp.s4, 0),
          child: TextField(
            controller: ctl,
            obscureText: secret,
            keyboardType: type,
            autocorrect: false,
            enableSuggestions: false,
            style: AppText.base(c.text),
            decoration: InputDecoration(labelText: label, labelStyle: AppText.base(c.text2), filled: true, fillColor: c.surface, border: OutlineInputBorder(borderRadius: BorderRadius.circular(Rd.m), borderSide: BorderSide.none)),
          ),
        );
    return Scaffold(
      body: SafeArea(child: Column(children: [
        Row(children: [IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()), Text('Nguồn dữ liệu', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))]),
        Expanded(child: ListView(children: [
          field('URL', _url, type: TextInputType.url),
          field('Khoá công khai (anon)', _key, secret: true),
          field('Email', _mail, type: TextInputType.emailAddress),
          field('Mật khẩu', _pass, secret: true),
          if (s.error != null) Padding(padding: const EdgeInsets.all(Sp.s4), child: Text(s.error!, style: AppText.base(c.danger, size: Ts.s))),
          Padding(
            padding: const EdgeInsets.all(Sp.s4),
            child: Row(children: [
              Expanded(
                child: FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: c.accent, foregroundColor: c.onAccent, minimumSize: const Size.fromHeight(48)),
                  onPressed: _busy ? null : () async {
                    setState(() => _busy = true);
                    await s.saveConnection(SupabaseConfig(url: _url.text.trim(), anonKey: _key.text.trim(), email: _mail.text.trim(), password: _pass.text));
                    if (mounted) setState(() => _busy = false);
                  },
                  child: Text(_busy ? '…' : 'Lưu và tải'),
                ),
              ),
              const SizedBox(width: Sp.s3),
              Pill('Dùng mẫu', onTap: () async {
                await s.saveConnection(const SupabaseConfig(url: '', anonKey: '', email: '', password: ''));
                if (context.mounted) Navigator.of(context).pop();
              }),
            ]),
          ),
          Padding(padding: const EdgeInsets.symmetric(horizontal: Sp.s4), child: Text('Chỉ lưu trên máy này. Dùng khoá công khai, không dùng khoá secret của bot.', style: AppText.base(c.text3, size: Ts.xs))),
        ])),
      ])),
    );
  }
}

class DataStatusScreen extends StatelessWidget {
  const DataStatusScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    Widget line(String l, String v, {Color? dot}) => SizedBox(
          height: 48,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
            child: Row(children: [
              if (dot != null) ...[Container(width: 8, height: 8, decoration: BoxDecoration(color: dot, shape: BoxShape.circle)), const SizedBox(width: 8)],
              Expanded(child: Text(l, style: AppText.base(c.text))),
              Text(v, style: AppText.num(c.text2, size: Ts.s, weight: FontWeight.w400)),
            ]),
          ),
        );
    Widget market(Market m) {
      final d = s.of(m);
      final fresh = s.freshness(m);
      final age = d.asof == null ? null : s.now.difference(d.asof!);
      return Column(children: [
        SectionTitle(m.key),
        line('Cập nhật', f.hhmm(d.asof), dot: fresh == 'fresh' ? c.up : fresh == 'stale' ? c.levels[2] : c.text3),
        line('Độ trễ', age == null ? '—' : '${age.inMinutes} phút'),
        line('Số mã', '${d.quotes.length}'),
        line('Tín hiệu', '${d.signals.length}'),
        line('Mức 3', '${d.signals.values.where((x) => x.level >= 3).length}'),
        line('Vùng', '${d.zones.length}'),
        line('Bản tin', '${d.digests.length}'),
      ]);
    }
    return Scaffold(
      body: SafeArea(child: Column(children: [
        Row(children: [IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()), Text('Tình trạng', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))]),
        Expanded(child: ListView(children: [
          market(Market.vn),
          market(Market.us),
          Padding(padding: const EdgeInsets.all(Sp.s4), child: Text('Số liệu đọc được từ dữ liệu của bot. Nhịp tim và số khung lỡ của bot nằm trong cảnh báo Telegram.', style: AppText.base(c.text3, size: Ts.xs))),
        ])),
      ])),
    );
  }
}
