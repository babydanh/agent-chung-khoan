import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../widgets/common.dart';
import '../widgets/stock_row.dart';
import 'detail_screen.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, this.onPick});

  /// When set, picking a symbol calls this instead of opening the detail (used to add to the watchlist).
  final void Function(Market, String)? onPick;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _ctl = TextEditingController();
  Market? _m;

  @override
  void dispose() {
    _ctl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final m = _m ?? s.market;
    final hits = s.search(m, _ctl.text);
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Sp.s2, Sp.s2, Sp.s4, 0),
            child: Row(children: [
              IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()),
              Expanded(
                child: TextField(
                  controller: _ctl,
                  autofocus: true,
                  textCapitalization: TextCapitalization.characters,
                  style: AppText.base(c.text),
                  onChanged: (_) => setState(() {}),
                  onSubmitted: s.remember,
                  decoration: InputDecoration(
                    hintText: 'Mã hoặc tên',
                    hintStyle: AppText.base(c.text3),
                    filled: true,
                    fillColor: c.surface,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(Rd.m), borderSide: BorderSide.none),
                    contentPadding: const EdgeInsets.symmetric(horizontal: Sp.s3),
                  ),
                ),
              ),
              const SizedBox(width: Sp.s2),
              Segmented<Market>(value: m, options: const [(Market.vn, 'VN'), (Market.us, 'US')], onChanged: (v) => setState(() => _m = v)),
            ]),
          ),
          Expanded(
            child: _ctl.text.trim().isEmpty
                ? ListView(children: [
                    if (s.recentSearches.isNotEmpty) const SectionTitle('Gần đây'),
                    for (final r in s.recentSearches)
                      ListTile(
                        leading: AppIcon('clock', size: 18, color: c.text3),
                        title: Text(r, style: AppText.base(c.text)),
                        onTap: () => setState(() => _ctl.text = r),
                      ),
                  ])
                : hits.isEmpty
                    ? const EmptyState('search', 'Không thấy mã')
                    : ListView.builder(
                        itemCount: hits.length,
                        itemBuilder: (_, i) {
                          final q = hits[i];
                          return StockRow(
                            quote: q,
                            signal: s.of(m).signals[q.symbol],
                            trailing: widget.onPick != null ? AppIcon(s.isWatched(m, q.symbol) ? 'check' : 'plus', size: 20, color: c.accent) : null,
                            onTap: () {
                              s.remember(_ctl.text);
                              if (widget.onPick != null) {
                                widget.onPick!(m, q.symbol);
                                setState(() {});
                              } else {
                                Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DetailScreen(market: m, symbol: q.symbol)));
                              }
                            },
                          );
                        },
                      ),
          ),
        ]),
      ),
    );
  }
}
