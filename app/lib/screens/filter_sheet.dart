import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';

Future<void> showFilterSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: context.c.surface,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(Rd.m * 1.5))),
    builder: (_) => const _FilterSheet(),
  );
}

class _FilterSheet extends StatefulWidget {
  const _FilterSheet();

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  Filters? _f;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final f = _f ??= s.filters;
    final exchanges = s.market.key == 'VN' ? const ['HOSE', 'HNX', 'UPCOM'] : const ['NASDAQ', 'NYSE'];
    Widget group(String title, List<Widget> chips) => Padding(
          padding: const EdgeInsets.only(top: Sp.s3),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: AppText.base(c.text2, size: Ts.s)),
            const SizedBox(height: Sp.s1),
            Wrap(spacing: Sp.s2, children: chips),
          ]),
        );
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s4, Sp.s4, Sp.s4),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text('Lọc', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))),
            Pill('Đặt lại', onTap: () => setState(() => _f = const Filters())),
          ]),
          group('Mức', [
            for (final (v, l) in const [(0, 'Tất cả'), (1, 'Mức 1+'), (2, 'Mức 2+'), (3, 'Mức 3')])
              Pill(l, selected: f.minLevel == v, onTap: () => setState(() => _f = f.copyWith(minLevel: v))),
          ]),
          group('Sàn', [
            for (final e in exchanges)
              Pill(e, selected: f.exchanges.contains(e), onTap: () {
                final n = {...f.exchanges};
                n.contains(e) ? n.remove(e) : n.add(e);
                setState(() => _f = f.copyWith(exchanges: n));
              }),
          ]),
          group('Tín hiệu', [
            for (final (id, l) in const [('S1', 'S1 KL'), ('S2', 'S2 NN'), ('S3', 'S3 TT')])
              Pill(l, selected: f.signals.contains(id), onTap: () {
                final n = {...f.signals};
                n.contains(id) ? n.remove(id) : n.add(id);
                setState(() => _f = f.copyWith(signals: n));
              }),
          ]),
          group('Sắp xếp', [
            for (final (k, l) in const [(SortKey.level, 'Mức'), (SortKey.percent, '%'), (SortKey.volume, 'KL'), (SortKey.symbol, 'Mã')])
              Pill(l, selected: f.sort == k, onTap: () => setState(() => _f = f.copyWith(sort: k))),
          ]),
          const SizedBox(height: Sp.s4),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: c.accent, foregroundColor: c.onAccent, minimumSize: const Size.fromHeight(48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Rd.m))),
              onPressed: () {
                s.setFilters(f);
                Navigator.of(context).pop();
              },
              child: Text('Áp dụng${f.activeCount > 0 ? ' · ${f.activeCount}' : ''}', style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
          ),
        ]),
      ),
    );
  }
}
