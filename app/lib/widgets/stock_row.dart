import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../util/format.dart' as f;
import 'common.dart';

/// One symbol on the board / watchlist: ticker, price, change, volume, signal icons and level.
class StockRow extends StatelessWidget {
  const StockRow({super.key, required this.quote, required this.signal, required this.onTap, this.trailing});
  final Quote quote;
  final SignalRow? signal;
  final VoidCallback onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final q = quote;
    final vn = q.market == Market.vn;
    final pc = priceColor(c, q);
    final pct = q.pct;
    final pctColor = pct == null ? c.text2 : pct > 0.004 ? c.up : pct < -0.004 ? c.down : c.ref;
    final sig = signal;
    Widget icon(String name, String id) => Padding(
          padding: const EdgeInsets.only(right: 6),
          child: AppIcon(name, size: 14, color: (sig?.has(id) ?? false) ? c.text : c.text3.withValues(alpha: 0.35)),
        );
    return Semantics(
      button: true,
      label: '${q.symbol} ${f.price(q.price, vn: vn)} ${f.percent(pct)}',
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 56),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: Sp.s2),
            child: Row(children: [
              Expanded(
                flex: 5,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(q.symbol, style: AppText.base(c.text, weight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  if (sig?.learning ?? false)
                    const Tag('đang học', icon: 'book')
                  else
                    Row(children: [icon('zap', 'S1'), icon('globe', 'S2'), icon('swap', 'S3')]),
                ]),
              ),
              Expanded(
                flex: 4,
                child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text(f.price(q.price, vn: vn), style: AppText.num(pc)),
                  const SizedBox(height: 2),
                  Text(f.volume(q.vol), style: AppText.num(c.text2, size: Ts.xs, weight: FontWeight.w500)),
                ]),
              ),
              Expanded(
                flex: 4,
                child: Align(
                  alignment: Alignment.topRight,
                  child: Text(f.percent(pct), style: AppText.num(pctColor, size: Ts.s)),
                ),
              ),
              const SizedBox(width: Sp.s3),
              trailing ?? LevelChip(sig?.level ?? 0),
            ]),
          ),
        ),
      ),
    );
  }
}
