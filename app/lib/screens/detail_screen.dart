import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../util/format.dart' as f;
import '../widgets/common.dart';
import '../widgets/line_chart.dart';
import '../widgets/price_bar.dart';

const _tabs = ['Tổng quan', 'Dòng tiền', 'Lịch sử', 'Vùng', 'Tin'];

class DetailScreen extends StatefulWidget {
  const DetailScreen({super.key, required this.market, required this.symbol});
  final Market market;
  final String symbol;

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  int _tab = 0;
  String _range = '1T';
  List<DailyBar>? _bars;
  List<SignalRow>? _history;

  @override
  void initState() {
    super.initState();
    final s = AppScope.read(context);
    s.bars(widget.market, widget.symbol, days: 90).then((b) => mounted ? setState(() => _bars = b) : null);
    s.signalHistory(widget.market, widget.symbol).then((h) => mounted ? setState(() => _history = h) : null);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    final m = widget.market;
    final q = s.of(m).quote(widget.symbol);
    if (q == null) {
      return Scaffold(body: SafeArea(child: Column(children: [
        Align(alignment: Alignment.centerLeft, child: IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop())),
        const Expanded(child: EmptyState('search', 'Không có dữ liệu mã này')),
      ])));
    }
    final sig = s.of(m).signals[widget.symbol];
    final vn = m == Market.vn;
    final pct = q.pct;
    final pctColor = pct == null ? c.text2 : pct > 0.004 ? c.up : pct < -0.004 ? c.down : c.ref;
    final watched = s.isWatched(m, q.symbol);
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Sp.s2, Sp.s1, Sp.s2, 0),
            child: Row(children: [
              IconBtn('back', label: 'Quay lại', onTap: () => Navigator.of(context).pop()),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(q.symbol, style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700)),
                  Text(q.exchange.isEmpty ? m.key : q.exchange, style: AppText.base(c.text2, size: Ts.xs)),
                ]),
              ),
              IconBtn(watched ? 'check' : 'star', label: watched ? 'Bỏ theo dõi' : 'Theo dõi', onTap: () => s.toggleWatch(m, q.symbol)),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s2, Sp.s4, Sp.s2),
            child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Expanded(child: Text(f.price(q.price, vn: vn), style: AppText.num(priceColor(c, q), size: 32, weight: FontWeight.w700))),
              Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text(f.percent(pct), style: AppText.num(pctColor, size: Ts.m)),
                const SizedBox(height: 4),
                GestureDetector(onTap: () => _learning(context, sig), child: LevelChip(sig?.level ?? 0)),
              ]),
            ]),
          ),
          SizedBox(
            height: Sp.touch,
            child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: Sp.s2), children: [
              for (var i = 0; i < _tabs.length; i++)
                Semantics(
                  button: true,
                  selected: i == _tab,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => setState(() => _tab = i),
                    child: Container(
                      alignment: Alignment.center,
                      padding: const EdgeInsets.symmetric(horizontal: Sp.s3),
                      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: i == _tab ? c.accent : Colors.transparent, width: 2))),
                      child: Text(_tabs[i], style: AppText.base(i == _tab ? c.text : c.text2, size: Ts.s, weight: FontWeight.w600)),
                    ),
                  ),
                ),
            ]),
          ),
          Divider(height: 1, color: c.line),
          Expanded(child: ListView(padding: const EdgeInsets.only(bottom: Sp.s5), children: switch (_tab) {
            0 => _overview(context, q, sig),
            1 => _flow(context, q),
            2 => _historyTab(context),
            3 => _zones(context, q, s.of(m).zonesOf(q.symbol)),
            _ => _news(context, s.of(m).news.where((n) => n.symbol == q.symbol).toList()),
          })),
        ]),
      ),
    );
  }

  List<Widget> _overview(BuildContext context, Quote q, SignalRow? sig) {
    final c = context.c;
    final vn = q.market == Market.vn;
    final days = _range == '1T' ? 7 : _range == '1M' ? 30 : 90;
    final bars = _bars == null ? const <DailyBar>[] : _bars!.sublist((_bars!.length - days).clamp(0, _bars!.length));
    return [
      PriceBar(q),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
        child: Row(children: [
          Segmented<String>(value: _range, options: const [('1T', '1T'), ('1M', '1M'), ('3M', '3M')], onChanged: (v) => setState(() => _range = v)),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.all(Sp.s4),
        child: bars.length < 2
            ? SizedBox(height: 100, child: Center(child: Text(_bars == null ? '…' : 'Chưa có dữ liệu ngày', style: AppText.base(c.text3, size: Ts.s))))
            : LineChart(bars, color: c.accent),
      ),
      _tiles(context, [
        ('Khối lượng', f.volume(q.vol), null),
        ('Giá trị', f.valueBillions(q.val), null),
        ('NN mua', f.volume(q.fBuy), null),
        ('NN bán', f.volume(q.fSell), null),
        ('NN ròng', f.signed(q.fNet), (q.fNet ?? 0) > 0 ? c.up : (q.fNet ?? 0) < 0 ? c.down : null),
        ('Room NN', q.fRoom == null ? '—' : '${f.fixed(q.fRoom!, 1)}%', null),
        if (vn) ('TT khối lượng', f.volume(q.ptVol), null),
        if (vn) ('TT giá trị', f.valueBillions(q.ptVal), null),
      ]),
      const SectionTitle('Tín hiệu'),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
        child: (sig?.items.isEmpty ?? true)
            ? Text('Không có', style: AppText.base(c.text3, size: Ts.s))
            : Wrap(spacing: Sp.s2, runSpacing: Sp.s2, children: [for (final i in sig!.items) _signalChip(c, i)]),
      ),
    ];
  }

  Widget _signalChip(AppColors c, SignalItem i) {
    final (icon, text) = switch (i.id) {
      'S1' => ('zap', 'KL tăng đột biến'),
      'S2' => ('globe', i.dir == 'sell' ? 'NN ròng âm' : 'NN ròng dương'),
      'S3' => ('swap', 'Thoả thuận lớn'),
      'S4' => (i.dir == 'down' ? 'down' : 'up', 'Biến động giá'),
      _ => (i.dir == 'down' ? 'down' : 'up', 'Gap mở cửa'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Sp.s3, vertical: 6),
      decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(Rd.pill)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        AppIcon(icon, size: 14, color: c.text),
        const SizedBox(width: 6),
        Text(text, style: AppText.base(c.text, size: Ts.s, weight: FontWeight.w600)),
      ]),
    );
  }

  /// Two tiles per row; each row is as tall as its content so large text sizes cannot overflow.
  Widget _tiles(BuildContext context, List<(String, String, Color?)> items) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: Sp.s2),
        child: Column(children: [
          for (var i = 0; i < items.length; i += 2)
            Padding(
              padding: EdgeInsets.only(bottom: i + 2 < items.length ? Sp.s2 : 0),
              child: IntrinsicHeight(
                child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Expanded(child: Tile(items[i].$1, items[i].$2, color: items[i].$3)),
                  const SizedBox(width: Sp.s2),
                  Expanded(child: i + 1 < items.length ? Tile(items[i + 1].$1, items[i + 1].$2, color: items[i + 1].$3) : const SizedBox.shrink()),
                ]),
              ),
            ),
        ]),
      );

  List<Widget> _flow(BuildContext context, Quote q) {
    final c = context.c;
    final buy = q.fBuy ?? 0, sell = q.fSell ?? 0;
    final total = buy + sell;
    return [
      const SectionTitle('Khối ngoại hôm nay'),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
        child: total <= 0
            ? Text('Chưa có dữ liệu', style: AppText.base(c.text3, size: Ts.s))
            : Column(children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: SizedBox(height: 10, child: Row(children: [
                    Expanded(flex: (buy / total * 1000).round().clamp(1, 999), child: Container(color: c.up)),
                    Expanded(flex: (sell / total * 1000).round().clamp(1, 999), child: Container(color: c.down)),
                  ])),
                ),
                const SizedBox(height: Sp.s2),
                Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                  Text('NN mua ${f.volume(buy)}', style: AppText.num(c.up, size: Ts.s)),
                  Text('NN bán ${f.volume(sell)}', style: AppText.num(c.down, size: Ts.s)),
                ]),
              ]),
      ),
      _tiles(context, [
        ('NN ròng', f.signed(q.fNet), (q.fNet ?? 0) > 0 ? c.up : (q.fNet ?? 0) < 0 ? c.down : null),
        ('Room NN', q.fRoom == null ? '—' : '${f.fixed(q.fRoom!, 1)}%', null),
        ('TT khối lượng', f.volume(q.ptVol), null),
        ('TT giá trị', f.valueBillions(q.ptVal), null),
      ]),
    ];
  }

  List<Widget> _historyTab(BuildContext context) {
    final c = context.c;
    final h = _history;
    if (h == null) return [const SkeletonRows(count: 4)];
    if (h.isEmpty) return [const SizedBox(height: 240, child: EmptyState('list', 'Chưa có lịch sử tín hiệu'))];
    return [
      for (final r in h)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: Sp.s2),
          child: Row(children: [
            SizedBox(width: 72, child: Text('${f.dayMonth(r.asof ?? DateTime.now())} ${f.hhmm(r.asof)}', style: AppText.num(c.text2, size: Ts.xs, weight: FontWeight.w500))),
            Container(width: 3, height: 28, margin: const EdgeInsets.symmetric(horizontal: Sp.s3), color: c.levels[r.level]),
            Expanded(child: Row(children: [
              for (final i in r.items) Padding(padding: const EdgeInsets.only(right: 8), child: AppIcon(switch (i.id) { 'S1' => 'zap', 'S2' => 'globe', 'S3' => 'swap', _ => 'up' }, size: 16, color: c.text)),
            ])),
            LevelChip(r.level),
          ]),
        ),
    ];
  }

  List<Widget> _zones(BuildContext context, Quote q, List<Zone> zones) {
    final c = context.c;
    if (zones.isEmpty) return [const SizedBox(height: 240, child: EmptyState('zone', 'Chưa có vùng'))];
    final vn = q.market == Market.vn;
    return [
      for (final z in zones)
        Padding(
          padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s3, Sp.s4, 0),
          child: Container(
            padding: const EdgeInsets.all(Sp.s3),
            decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(Rd.m)),
            child: Row(children: [
              Expanded(child: Text(z.kind, style: AppText.base(c.text, weight: FontWeight.w600))),
              Text('${f.price(z.lo, vn: vn)} – ${f.price(z.hi, vn: vn)}', style: AppText.num(c.text)),
            ]),
          ),
        ),
    ];
  }

  List<Widget> _news(BuildContext context, List<NewsItem> items) {
    if (items.isEmpty) return [const SizedBox(height: 240, child: EmptyState('news', 'Chưa có tin'))];
    return [for (final n in items.take(10)) NewsTile(n)];
  }

  void _learning(BuildContext context, SignalRow? sig) {
    if (!(sig?.learning ?? false)) return;
    final c = context.c;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: c.surface,
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Sp.s4),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Đang học', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700)),
            const SizedBox(height: Sp.s2),
            Text('Đang xây mức nền khối lượng cho mã này.', style: AppText.base(c.text2)),
          ]),
        ),
      ),
    );
  }
}

class NewsTile extends StatelessWidget {
  const NewsTile(this.item, {super.key});
  final NewsItem item;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Semantics(
      button: true,
      child: InkWell(
        onTap: () async {
          final uri = Uri.tryParse(item.url);
          if (uri != null && uri.scheme == 'https') await launchUrl(uri, mode: LaunchMode.externalApplication);
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: Sp.s3),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(item.title, maxLines: 3, overflow: TextOverflow.ellipsis, style: AppText.base(c.text, weight: FontWeight.w600)),
            const SizedBox(height: 4),
            Row(children: [
              if (item.symbol != null && item.symbol!.isNotEmpty) ...[Tag(item.symbol!), const SizedBox(width: 6)],
              Text('${item.source} · ${f.hhmm(item.publishedAt)}', style: AppText.num(c.text2, size: Ts.xs, weight: FontWeight.w400)),
              const Spacer(),
              AppIcon('ext', size: 16, color: c.text3),
            ]),
          ]),
        ),
      ),
    );
  }
}
