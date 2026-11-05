import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../util/format.dart' as f;
import '../widgets/common.dart';
import 'detail_screen.dart';
import 'news_screen.dart';

/// What the bot flagged lately, read from the data (nothing is pushed to the phone from here).
class InboxScreen extends StatelessWidget {
  const InboxScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final items = s.inbox();
    return Scaffold(
      body: SafeArea(child: Column(children: [
        Row(children: [
          IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()),
          Expanded(child: Text('Thông báo', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))),
          IconBtn('settings', label: 'Cài đặt', onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const NotifySettings()))),
        ]),
        Expanded(
          child: items.isEmpty
              ? const EmptyState('bell', 'Chưa có thông báo')
              : ListView.separated(
                  itemCount: items.length,
                  separatorBuilder: (_, _) => Divider(height: 1, indent: Sp.s4, endIndent: Sp.s4, color: c.line),
                  itemBuilder: (_, i) {
                    final it = items[i];
                    final st = it.story;
                    final isDigest = it.digest != null;
                    final q = isDigest || st != null ? null : s.of(it.market).quote(it.symbol!);
                    return ListTile(
                      leading: Container(
                        width: 40, height: 40,
                        decoration: BoxDecoration(color: c.surface2, shape: BoxShape.circle),
                        child: Center(child: AppIcon(isDigest || st != null ? 'news' : 'zap', size: 20, color: isDigest ? c.text : st != null ? c.levels[3] : c.levels[it.level])),
                      ),
                      title: Row(children: [
                        Text(isDigest ? 'Bản tin ${it.market.key}' : st != null ? '${st.head.symbols.isEmpty ? 'Thị trường' : st.head.symbols.first} · ${st.event.label}' : it.symbol!, style: AppText.base(c.text, weight: FontWeight.w700)),
                        if (!isDigest && st == null) ...[const SizedBox(width: 8), LevelChip(it.level)],
                      ]),
                      subtitle: Text(st != null ? st.head.title : isDigest ? it.digest!.body.split('\n').first : '${f.price(q?.price, vn: it.market == Market.vn)} · ${f.percent(q?.pct)}', maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.num(c.text2, size: Ts.s, weight: FontWeight.w400)),
                      trailing: Text(f.hhmm(it.at), style: AppText.num(c.text2, size: Ts.xs, weight: FontWeight.w400)),
                      onTap: () async {
                        if (st != null) {
                          final uri = Uri.tryParse(st.head.link);
                          if (uri != null && uri.scheme == 'https') await launchUrl(uri, mode: LaunchMode.externalApplication);
                          return;
                        }
                        if (!context.mounted) return;
                        await Navigator.of(context).push(MaterialPageRoute<void>(
                          builder: (_) => isDigest ? DigestDetail(it.digest!) : DetailScreen(market: it.market, symbol: it.symbol!),
                        ));
                      },
                    );
                  },
                ),
        ),
      ])),
    );
  }
}

class SwitchRow extends StatelessWidget {
  const SwitchRow(this.label, this.value, this.onChanged, {super.key});
  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return MergeSemantics(
      child: SizedBox(
        height: 56,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
          child: Row(children: [
            Expanded(child: Text(label, style: AppText.base(c.text))),
            Switch(value: value, onChanged: onChanged, activeThumbColor: c.onAccent, activeTrackColor: c.accent),
          ]),
        ),
      ),
    );
  }
}

class NotifySettings extends StatefulWidget {
  const NotifySettings({super.key});

  @override
  State<NotifySettings> createState() => _NotifySettingsState();
}

class _NotifySettingsState extends State<NotifySettings> {
  String? _msg;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final n = s.notify;
    Widget pills(String title, List<(int, String)> options, int value, void Function(int) set) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SectionTitle(title),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
            child: Wrap(spacing: Sp.s2, children: [for (final (v, l) in options) Pill(l, selected: value == v, onTap: () => set(v))]),
          ),
        ]);
    return Scaffold(
      body: SafeArea(child: Column(children: [
        Row(children: [IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()), Text('Thông báo', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))]),
        Expanded(child: ListView(children: [
          SwitchRow('VN', n.vn, (v) => s.setNotify(n.copyWith(vn: v))),
          SwitchRow('US', n.us, (v) => s.setNotify(n.copyWith(us: v))),
          SwitchRow('Bản tin', n.digest, (v) => s.setNotify(n.copyWith(digest: v))),
          SwitchRow('Tin nóng', n.news, (v) => s.setNotify(n.copyWith(news: v))),
          pills('Mức tối thiểu', const [(1, 'Mức 1+'), (2, 'Mức 2+'), (3, 'Mức 3')], n.minLevel, (v) => s.setNotify(n.copyWith(minLevel: v))),
          pills('Ngưỡng tin nóng', const [(50, '50'), (60, '60'), (70, '70'), (80, '80')], n.hot, (v) => s.setNotify(n.copyWith(hot: v))),
          pills('Tối đa mỗi giờ', const [(3, '3'), (6, '6'), (10, '10')], n.maxPerHour, (v) => s.setNotify(n.copyWith(maxPerHour: v))),
          const SizedBox(height: Sp.s3),
          SwitchRow('Giờ yên 22:00–07:00', n.quiet, (v) => s.setNotify(n.copyWith(quiet: v))),
          Padding(
            padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s3, Sp.s4, 0),
            child: Wrap(spacing: Sp.s2, children: [
              Pill('Cho phép thông báo', selected: true, onTap: () async {
                final ok = await s.allowNotifications();
                if (mounted) setState(() => _msg = ok ? 'Đã cho phép' : 'Chưa được cho phép');
              }),
              Pill('Gửi thử', onTap: () async {
                await s.sendTestNotice();
                if (mounted) setState(() => _msg = 'Đã gửi thử');
              }),
            ]),
          ),
          if (_msg != null) Padding(padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s2, Sp.s4, 0), child: Text(_msg!, style: AppText.base(c.text2, size: Ts.s))),
          Padding(
            padding: const EdgeInsets.all(Sp.s4),
            child: Text('App tự kiểm tra mỗi 15 phút khi máy cho phép chạy nền. Tiết kiệm pin có thể làm chậm.', style: AppText.base(c.text3, size: Ts.xs)),
          ),
        ])),
      ])),
    );
  }
}
