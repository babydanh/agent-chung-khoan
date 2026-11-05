import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../util/format.dart' as f;
import '../widgets/common.dart';
import '../widgets/stock_row.dart';
import 'detail_screen.dart';
import 'filter_sheet.dart';
import 'inbox_screen.dart';
import 'search_screen.dart';

/// Shared top part of the list tabs: market switch, update stamp and the status strip.
class MarketBar extends StatelessWidget {
  const MarketBar({super.key, required this.market, required this.onMarket, this.actions = const []});
  final Market market;
  final ValueChanged<Market> onMarket;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final s = AppScope.of(context);
    final fresh = s.freshness(market);
    final dot = fresh == 'fresh' ? c.up : fresh == 'stale' ? c.levels[2] : c.text3;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s2, Sp.s2, 0),
      child: Row(children: [
        Segmented<Market>(value: market, options: const [(Market.vn, 'VN'), (Market.us, 'US')], onChanged: onMarket),
        const SizedBox(width: Sp.s3),
        Container(width: 8, height: 8, decoration: BoxDecoration(color: dot, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Expanded(child: Text('cập nhật ${f.hhmm(s.of(market).asof)}', maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.num(c.text2, size: Ts.s, weight: FontWeight.w400))),
        ...actions,
      ]),
    );
  }
}

/// Banner for offline, error, stale and closed states of a market.
class DataBanner extends StatelessWidget {
  const DataBanner(this.market, {super.key});
  final Market market;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final at = s.of(market).asof;
    if (s.offline) return StatusBanner(icon: 'wifioff', text: 'Ngoại tuyến', trailing: at == null ? null : f.hhmm(at), onTap: () => s.load(market));
    if (s.error != null) {
      return StatusBanner(icon: 'alert', text: s.authError ? 'Cần đăng nhập lại' : 'Lỗi tải', trailing: 'Thử lại', color: c.danger, onTap: () => s.load(market));
    }
    switch (s.freshness(market)) {
      case 'stale':
        return StatusBanner(icon: 'clock', text: 'Dữ liệu cũ', trailing: f.hhmm(at), color: c.levels[2]);
      case 'closed':
        return StatusBanner(icon: 'moon', text: 'Đóng cửa', trailing: f.hhmm(at));
    }
    return const SizedBox.shrink();
  }
}

class BoardScreen extends StatelessWidget {
  const BoardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final m = s.market;
    final rows = s.board();
    final empty = s.of(m).quotes.isEmpty;
    return SafeArea(
      bottom: false,
      child: Column(children: [
        MarketBar(market: m, onMarket: s.setMarket, actions: [
          IconBtn('bell', label: 'Thông báo', dot: s.inbox().isNotEmpty, onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const InboxScreen()))),
          IconBtn('search', label: 'Tìm', onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const SearchScreen()))),
        ]),
        Padding(
          padding: const EdgeInsets.only(left: Sp.s2, top: Sp.s1),
          child: Row(children: [
            Stack(alignment: Alignment.center, children: [
              IconBtn('sort', label: 'Lọc', onTap: () => showFilterSheet(context)),
              if (s.filters.activeCount > 0)
                Positioned(
                  right: 6,
                  top: 6,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 5),
                    decoration: BoxDecoration(color: c.accent, borderRadius: BorderRadius.circular(8)),
                    child: Text('${s.filters.activeCount}', style: AppText.num(c.onAccent, size: 10)),
                  ),
                ),
            ]),
            Expanded(
              child: SizedBox(
                height: Sp.touch,
                child: ListView(scrollDirection: Axis.horizontal, children: [
                  for (final (q, label) in const [
                    (QuickFilter.all, 'Tất cả'), (QuickFilter.level2, 'Mức 2+'), (QuickFilter.level3, 'Mức 3'), (QuickFilter.watch, 'Theo dõi'),
                  ])
                    Padding(padding: const EdgeInsets.only(right: Sp.s2), child: Pill(label, selected: s.quick == q, onTap: () => s.setQuick(q))),
                ]),
              ),
            ),
          ]),
        ),
        DataBanner(m),
        Expanded(
          child: RefreshIndicator(
            color: c.accent,
            backgroundColor: c.surface,
            onRefresh: () => s.load(m),
            child: s.loading && empty
                ? const SingleChildScrollView(physics: AlwaysScrollableScrollPhysics(), child: SkeletonRows())
                : rows.isEmpty
                    ? ListView(physics: const AlwaysScrollableScrollPhysics(), children: [
                        SizedBox(
                          height: 320,
                          child: EmptyState(empty ? 'board' : 'search', empty ? 'Chưa có dữ liệu' : 'Không có mã phù hợp',
                              action: empty ? 'Tải lại' : 'Bỏ lọc',
                              onAction: empty ? () => s.load(m) : () { s.setQuick(QuickFilter.all); s.setFilters(const Filters()); }),
                        ),
                      ])
                    : ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: rows.length,
                        separatorBuilder: (_, _) => Divider(height: 1, indent: Sp.s4, endIndent: Sp.s4, color: c.line),
                        itemBuilder: (_, i) {
                          final q = rows[i];
                          return StockRow(
                            quote: q,
                            signal: s.of(m).signals[q.symbol],
                            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DetailScreen(market: m, symbol: q.symbol))),
                          );
                        },
                      ),
          ),
        ),
      ]),
    );
  }
}
