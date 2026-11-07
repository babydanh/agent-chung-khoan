import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../widgets/common.dart';
import '../widgets/stock_row.dart';
import 'board_screen.dart';
import 'detail_screen.dart';
import 'search_screen.dart';

class WatchScreen extends StatefulWidget {
  const WatchScreen({super.key});

  @override
  State<WatchScreen> createState() => _WatchScreenState();
}

class _WatchScreenState extends State<WatchScreen> {
  Market _m = Market.vn;
  bool _reorder = false;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final symbols = s.watch[_m]!;
    final d = s.of(_m);
    return SafeArea(
      bottom: false,
      child: Column(children: [
        MarketBar(market: _m, onMarket: (m) {
          setState(() => _m = m);
          if (!s.data.containsKey(m)) s.load(m);
        }, actions: [
          IconBtn(_reorder ? 'check' : 'list', label: _reorder ? 'Xong' : 'Sắp xếp', onTap: () => setState(() => _reorder = !_reorder)),
          IconBtn('plus', label: 'Thêm', onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => SearchScreen(onPick: (m, sym) => s.toggleWatch(m, sym))))),
        ]),
        DataBanner(_m),
        Expanded(
          child: symbols.isEmpty
              ? EmptyState('star', 'Chưa theo dõi mã nào', action: 'Thêm mã', onAction: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => SearchScreen(onPick: (m, sym) => s.toggleWatch(m, sym)))))
              : ReorderableListView.builder(
                  buildDefaultDragHandles: false,
                  itemCount: symbols.length,
                  onReorderItem: (a, b) => s.reorderWatch(_m, a, b),
                  itemBuilder: (_, i) {
                    final sym = symbols[i];
                    final q = d.quote(sym);
                    final row = q == null
                        ? ListTile(title: Text(sym, style: AppText.base(c.text, weight: FontWeight.w700)), subtitle: Text('Chưa có giá', style: AppText.base(c.text3, size: Ts.xs)))
                        : StockRow(
                            quote: q,
                            signal: d.signals[sym],
                            trailing: _reorder ? ReorderableDragStartListener(index: i, child: SizedBox(width: Sp.touch, height: Sp.touch, child: Center(child: AppIcon('list', color: c.text2)))) : null,
                            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DetailScreen(market: _m, symbol: sym))),
                          );
                    return Dismissible(
                      key: ValueKey('$_m$sym'),
                      direction: DismissDirection.endToStart,
                      background: Container(color: c.danger, alignment: Alignment.centerRight, padding: const EdgeInsets.only(right: Sp.s4), child: const AppIcon('trash', color: Colors.white)),
                      onDismissed: (_) => s.toggleWatch(_m, sym),
                      child: Container(color: c.bg, child: row),
                    );
                  },
                ),
        ),
      ]),
    );
  }
}
