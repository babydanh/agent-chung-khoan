import 'package:flutter/material.dart';

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
                    final isDigest = it.digest != null;
                    final q = isDigest ? null : s.of(it.market).quote(it.symbol!);
                    return ListTile(
                      leading: Container(
                        width: 40, height: 40,
                        decoration: BoxDecoration(color: c.surface2, shape: BoxShape.circle),
                        child: Center(child: AppIcon(isDigest ? 'news' : 'zap', size: 20, color: isDigest ? c.text : c.levels[it.level])),
                      ),
                      title: Row(children: [
                        Text(isDigest ? 'Bản tin ${it.market.key}' : it.symbol!, style: AppText.base(c.text, weight: FontWeight.w700)),
                        if (!isDigest) ...[const SizedBox(width: 8), LevelChip(it.level)],
                      ]),
                      subtitle: Text(isDigest ? it.digest!.body.split('\n').first : '${f.price(q?.price, vn: it.market == Market.vn)} · ${f.percent(q?.pct)}', maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.num(c.text2, size: Ts.s, weight: FontWeight.w400)),
                      trailing: Text(f.hhmm(it.at), style: AppText.num(c.text2, size: Ts.xs, weight: FontWeight.w400)),
                      onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                        builder: (_) => isDigest ? DigestDetail(it.digest!) : DetailScreen(market: it.market, symbol: it.symbol!),
                      )),
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

class NotifySettings extends StatelessWidget {
  const NotifySettings({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final n = s.notify;
    return Scaffold(
      body: SafeArea(child: Column(children: [
        Row(children: [IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()), Text('Thông báo', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))]),
        Expanded(child: ListView(children: [
          SwitchRow('VN', n.vn, (v) => s.setNotify(n.copyWith(vn: v))),
          SwitchRow('US', n.us, (v) => s.setNotify(n.copyWith(us: v))),
          SwitchRow('Bản tin', n.digest, (v) => s.setNotify(n.copyWith(digest: v))),
          const SectionTitle('Mức tối thiểu'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
            child: Wrap(spacing: Sp.s2, children: [for (final l in const [1, 2, 3]) Pill('Mức $l+', selected: n.minLevel == l, onTap: () => s.setNotify(n.copyWith(minLevel: l)))]),
          ),
          const SizedBox(height: Sp.s3),
          SwitchRow('Giờ yên 22:00–07:00', n.quiet, (v) => s.setNotify(n.copyWith(quiet: v))),
          Padding(
            padding: const EdgeInsets.all(Sp.s4),
            child: Text('Lọc hộp thư trong app. Tin gửi tới điện thoại do bot đảm nhiệm.', style: AppText.base(c.text3, size: Ts.xs)),
          ),
        ])),
      ])),
    );
  }
}
