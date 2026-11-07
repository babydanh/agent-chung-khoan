import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../util/format.dart' as f;

/// Floor / reference / ceiling of the day with a marker at the current price.
class PriceBar extends StatelessWidget {
  const PriceBar(this.quote, {super.key});
  final Quote quote;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final q = quote;
    final lo = q.floor, hi = q.ceil, r = q.ref, p = q.price;
    if (lo == null || hi == null || r == null || hi <= lo) return const SizedBox.shrink();
    double at(double v) => ((v - lo) / (hi - lo)).clamp(0.0, 1.0);
    final vn = q.market == Market.vn;
    Widget label(String t, double v, Color col, CrossAxisAlignment a) => Column(crossAxisAlignment: a, children: [
          Text(t, style: AppText.base(c.text2, size: Ts.xs)),
          Text(f.price(v, vn: vn), style: AppText.num(col, size: Ts.m)),
        ]);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: Sp.s3),
      child: Column(children: [
        SizedBox(
          height: 14,
          child: LayoutBuilder(builder: (_, box) {
            final w = box.maxWidth;
            return Stack(clipBehavior: Clip.none, alignment: Alignment.centerLeft, children: [
              Container(height: 6, decoration: BoxDecoration(color: c.surface2, borderRadius: BorderRadius.circular(3))),
              Positioned(left: w * at(r) - 1.5, child: Container(width: 3, height: 14, color: c.ref)),
              if (p != null) Positioned(left: w * at(p) - 5, child: Container(width: 10, height: 10, decoration: BoxDecoration(color: c.text, shape: BoxShape.circle, border: Border.all(color: c.bg, width: 2)))),
            ]);
          }),
        ),
        const SizedBox(height: Sp.s2),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          label('Sàn', lo, c.floor, CrossAxisAlignment.start),
          label('TC', r, c.ref, CrossAxisAlignment.center),
          label('Trần', hi, c.ceil, CrossAxisAlignment.end),
        ]),
      ]),
    );
  }
}
