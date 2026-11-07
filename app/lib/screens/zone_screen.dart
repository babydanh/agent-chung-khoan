import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../util/format.dart' as f;
import '../widgets/common.dart';
import 'board_screen.dart';
import 'detail_screen.dart';

/// Symbols whose price sits near a recorded zone, closest first.
class ZoneScreen extends StatefulWidget {
  const ZoneScreen({super.key});

  @override
  State<ZoneScreen> createState() => _ZoneScreenState();
}

double _distance(Zone z, double? price) {
  if (price == null || price <= 0) return double.infinity;
  if (price >= z.lo && price <= z.hi) return 0;
  return (price < z.lo ? z.lo - price : price - z.hi) / price * 100;
}

class _ZoneScreenState extends State<ZoneScreen> {
  Market _m = Market.vn;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final d = s.of(_m);
    final rows = [for (final z in d.zones) (z, d.quote(z.symbol))]..sort((a, b) => _distance(a.$1, a.$2?.price).compareTo(_distance(b.$1, b.$2?.price)));
    return SafeArea(
      bottom: false,
      child: Column(children: [
        MarketBar(market: _m, onMarket: (m) {
          setState(() => _m = m);
          if (!s.data.containsKey(m)) s.load(m);
        }),
        DataBanner(_m),
        Expanded(
          child: rows.isEmpty
              ? const EmptyState('zone', 'Chưa có vùng')
              : ListView.separated(
                  itemCount: rows.length,
                  separatorBuilder: (_, _) => Divider(height: 1, indent: Sp.s4, endIndent: Sp.s4, color: c.line),
                  itemBuilder: (_, i) => _ZoneRow(zone: rows[i].$1, quote: rows[i].$2),
                ),
        ),
      ]),
    );
  }
}

class _ZoneRow extends StatelessWidget {
  const _ZoneRow({required this.zone, required this.quote});
  final Zone zone;
  final Quote? quote;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final q = quote;
    final vn = (q?.market ?? Market.vn) == Market.vn;
    final span = zone.hi - zone.lo;
    // Position of the price inside a band widened by one zone-width on each side.
    final pos = q?.price == null || span <= 0 ? null : ((q!.price! - (zone.lo - span)) / (span * 3)).clamp(0.0, 1.0);
    return InkWell(
      onTap: q == null ? null : () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DetailScreen(market: q.market, symbol: q.symbol))),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: Sp.s3),
        child: Row(children: [
          Expanded(
            flex: 3,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(zone.symbol, style: AppText.base(c.text, weight: FontWeight.w700)),
              Text(zone.kind, style: AppText.base(c.text2, size: Ts.xs)),
            ]),
          ),
          Expanded(
            flex: 4,
            child: SizedBox(
              height: 14,
              child: LayoutBuilder(builder: (_, box) => Stack(alignment: Alignment.centerLeft, children: [
                Container(height: 6, decoration: BoxDecoration(color: c.surface2, borderRadius: BorderRadius.circular(3))),
                Positioned(left: box.maxWidth / 3, width: box.maxWidth / 3, child: Container(height: 6, color: c.accent.withValues(alpha: 0.6))),
                if (pos != null) Positioned(left: box.maxWidth * pos - 5, child: Container(width: 10, height: 10, decoration: BoxDecoration(color: c.text, shape: BoxShape.circle))),
              ])),
            ),
          ),
          Expanded(
            flex: 4,
            child: Text('${f.price(zone.lo, vn: vn)} – ${f.price(zone.hi, vn: vn)}', textAlign: TextAlign.right, style: AppText.num(c.text, size: Ts.s)),
          ),
        ]),
      ),
    );
  }
}
