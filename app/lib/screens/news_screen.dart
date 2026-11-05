import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../util/format.dart' as f;
import '../widgets/common.dart';
import 'board_screen.dart';
import 'detail_screen.dart';

class NewsScreen extends StatefulWidget {
  const NewsScreen({super.key});

  @override
  State<NewsScreen> createState() => _NewsScreenState();
}

class _NewsScreenState extends State<NewsScreen> {
  Market _m = Market.vn;
  String? _symbol;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final d = s.of(_m);
    final news = [for (final n in d.news) if (_symbol == null || n.symbol == _symbol) n];
    final symbols = {for (final n in d.news) if (n.symbol != null && n.symbol!.isNotEmpty) n.symbol!}.toList()..sort();
    return SafeArea(
      bottom: false,
      child: Column(children: [
        MarketBar(market: _m, onMarket: (m) {
          setState(() { _m = m; _symbol = null; });
          if (!s.data.containsKey(m)) s.load(m);
        }),
        DataBanner(_m),
        Expanded(
          child: RefreshIndicator(
            color: c.accent,
            backgroundColor: c.surface,
            onRefresh: () => s.load(_m),
            child: ListView(physics: const AlwaysScrollableScrollPhysics(), children: [
              if (d.digests.isNotEmpty) _DigestCard(d.digests.first, onAll: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DigestHistory(market: _m)))),
              if (symbols.isNotEmpty)
                SizedBox(
                  height: Sp.touch,
                  child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: Sp.s4), children: [
                    Padding(padding: const EdgeInsets.only(right: Sp.s2), child: Pill('Tất cả', selected: _symbol == null, onTap: () => setState(() => _symbol = null))),
                    for (final sym in symbols) Padding(padding: const EdgeInsets.only(right: Sp.s2), child: Pill(sym, selected: _symbol == sym, onTap: () => setState(() => _symbol = sym))),
                  ]),
                ),
              if (news.isEmpty)
                const SizedBox(height: 260, child: EmptyState('news', 'Chưa có tin'))
              else
                for (final n in news) ...[NewsTile(n), Divider(height: 1, indent: Sp.s4, endIndent: Sp.s4, color: c.line)],
            ]),
          ),
        ),
      ]),
    );
  }
}

class _DigestCard extends StatelessWidget {
  const _DigestCard(this.digest, {required this.onAll});
  final Digest digest;
  final VoidCallback onAll;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final lines = digest.body.split('\n').where((l) => l.trim().isNotEmpty).take(5).toList();
    return Padding(
      padding: const EdgeInsets.all(Sp.s4),
      child: GestureDetector(
        onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DigestDetail(digest))),
        child: Container(
          padding: const EdgeInsets.all(Sp.s4),
          decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(Rd.m)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text('Bản tin', style: AppText.base(c.text, size: Ts.m, weight: FontWeight.w700))),
              Text(f.hhmm(digest.createdAt), style: AppText.num(c.text2, size: Ts.s, weight: FontWeight.w400)),
            ]),
            const SizedBox(height: Sp.s2),
            for (final l in lines) Padding(padding: const EdgeInsets.only(bottom: 4), child: Text(l, style: AppText.base(c.text, size: Ts.s))),
            const SizedBox(height: Sp.s2),
            GestureDetector(onTap: onAll, child: Text('Lịch sử', style: AppText.base(c.accent, size: Ts.s, weight: FontWeight.w600))),
          ]),
        ),
      ),
    );
  }
}

class DigestHistory extends StatelessWidget {
  const DigestHistory({super.key, required this.market});
  final Market market;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final list = s.of(market).digests;
    return Scaffold(
      body: SafeArea(child: Column(children: [
        Row(children: [IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()), Text('Bản tin', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700))]),
        Expanded(
          child: list.isEmpty
              ? const EmptyState('news', 'Chưa có bản tin')
              : ListView.separated(
                  itemCount: list.length,
                  separatorBuilder: (_, _) => Divider(height: 1, color: c.line),
                  itemBuilder: (_, i) => ListTile(
                    title: Text('${list[i].date} · ${f.hhmm(list[i].createdAt)}', style: AppText.num(c.text, size: Ts.s)),
                    subtitle: Text(list[i].body.split('\n').first, maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.base(c.text2, size: Ts.xs)),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DigestDetail(list[i]))),
                  ),
                ),
        ),
      ])),
    );
  }
}

class DigestDetail extends StatelessWidget {
  const DigestDetail(this.digest, {super.key});
  final Digest digest;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final s = AppScope.of(context);
    final known = {for (final m in Market.values) for (final q in s.of(m).quotes) q.symbol: m};
    final tickers = RegExp(r'(?<![A-Za-z0-9])[A-Z]{2,5}(?![A-Za-z0-9])').allMatches(digest.body).map((m) => m.group(0)!).where(known.containsKey).toSet();
    return Scaffold(
      body: SafeArea(child: Column(children: [
        Row(children: [IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()), Text('${digest.date} · ${f.hhmm(digest.createdAt)}', style: AppText.num(c.text, size: Ts.m))]),
        Expanded(child: ListView(padding: const EdgeInsets.all(Sp.s4), children: [
          Text(digest.body, style: AppText.base(c.text).copyWith(height: 1.5)),
          if (tickers.isNotEmpty) ...[
            const SizedBox(height: Sp.s4),
            Wrap(spacing: Sp.s2, children: [for (final t in tickers) Pill(t, onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DetailScreen(market: known[t]!, symbol: t))))]),
          ],
          const SizedBox(height: Sp.s5),
          Text('Chỉ là thông tin, không phải khuyến nghị.', style: AppText.base(c.text3, size: Ts.xs)),
        ])),
      ])),
    );
  }
}
