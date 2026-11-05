import '../models/models.dart';
import 'repository.dart';

/// Built-in sample data (same numbers as the approved design) for trying the app without a database.
class DemoRepository implements Repository {
  DemoRepository({DateTime? now}) : _now = now ?? DateTime.now();
  final DateTime _now;

  static const _rows = <_Row>[
    _Row('VNM', 'Vinamilk', 'HOSE', Market.vn, 62.1, 63.2, 4820000, 3, 1, 1, 0, 0, 612000, 318000, 41.2, 0, [(61.8, 62.6, 'Tích luỹ'), (65.0, 66.2, 'Cung')]),
    _Row('FPT', 'FPT', 'HOSE', Market.vn, 128.5, 131.2, 6100000, 3, 1, 1, 1, 0, 1280000, 640000, 2.8, 850000, [(129.0, 132.5, 'KL lớn'), (124.0, 126.5, 'Cầu')]),
    _Row('HPG', 'Hoà Phát', 'HOSE', Market.vn, 27.4, 26.85, 28400000, 2, 1, -1, 0, 0, 1900000, 3350000, 17.6, 0, [(26.2, 26.9, 'Cầu'), (28.0, 28.8, 'Cung')]),
    _Row('SSI', 'SSI', 'HOSE', Market.vn, 33.8, 36.15, 19700000, 2, 1, 0, 1, 0, 2100000, 1400000, 31.5, 3200000, [(34.5, 35.4, 'KL lớn')]),
    _Row('VIC', 'Vingroup', 'HOSE', Market.vn, 41.5, 38.6, 9300000, 2, 1, -1, 0, 0, 150000, 1250000, 38.2, 0, [(38.0, 39.5, 'Cầu')]),
    _Row('VCB', 'Vietcombank', 'HOSE', Market.vn, 91.3, 91.3, 2150000, 1, 0, 1, 0, 0, 410000, 290000, 6.0, 0, [(90.5, 92.0, 'Tích luỹ')]),
    _Row('MWG', 'Thế Giới Di Động', 'HOSE', Market.vn, 66.8, 65.1, 5400000, 1, 0, -1, 0, 0, 220000, 910000, 12.3, 0, [(64.2, 65.5, 'Cầu'), (68.0, 69.4, 'Cung')]),
    _Row('ACB', 'ACB', 'HOSE', Market.vn, 24.9, 25.1, 8100000, 1, 0, 0, 0, 1, 520000, 480000, 0.0, 0, [(24.6, 25.2, 'Tích luỹ')]),
    _Row('TCB', 'Techcombank', 'HOSE', Market.vn, 25.6, 25.85, 17200000, 0, 0, 0, 0, 1, 800000, 760000, 1.4, 0, [(25.0, 25.5, 'Tích luỹ')]),
    _Row('VHM', 'Vinhomes', 'HOSE', Market.vn, 39.2, 39.4, 3300000, 0, 0, 0, 0, 0, 140000, 120000, 24.7, 0, [(38.8, 39.6, 'KL lớn')]),
    _Row('NVDA', 'NVIDIA', 'NASDAQ', Market.us, 141.2, 146.8, 210000000, 3, 1, null, null, 0, null, null, null, null, [(143, 147, 'Tích luỹ'), (152, 155, 'Cung')]),
    _Row('AAPL', 'Apple', 'NASDAQ', Market.us, 226.4, 228.15, 52000000, 2, 1, null, null, 0, null, null, null, null, [(225, 229, 'KL lớn')]),
    _Row('TSLA', 'Tesla', 'NASDAQ', Market.us, 248.9, 255.3, 98000000, 2, 1, null, null, 0, null, null, null, null, [(250, 256, 'KL lớn')]),
    _Row('MSFT', 'Microsoft', 'NASDAQ', Market.us, 418.5, 416.2, 21000000, 1, 0, null, null, 0, null, null, null, null, [(412, 417, 'Cầu')]),
    _Row('AMZN', 'Amazon', 'NASDAQ', Market.us, 195.6, 195.6, 38000000, 0, 0, null, null, 1, null, null, null, null, [(194, 196.5, 'Tích luỹ')]),
  ];

  @override
  Future<MarketData> load(Market market) async {
    final rows = [for (final r in _rows) if (r.market == market) r];
    final at = DateTime(_now.year, _now.month, _now.day, _now.hour, _now.minute);
    final quotes = <Quote>[];
    final signals = <String, SignalRow>{};
    final zones = <Zone>[];
    for (final r in rows) {
      final vn = market == Market.vn;
      final step = r.ref < 10 ? 0.01 : r.ref < 50 ? 0.05 : 0.1;
      double snap(double v) => (v / step).round() * step;
      quotes.add(Quote(
        market: market, symbol: r.t, exchange: r.ex, name: r.name,
        price: r.p * (vn ? 1000 : 1), ref: r.ref * (vn ? 1000 : 1),
        ceil: vn ? snap(r.ref * 1.07) * 1000 : null, floor: vn ? snap(r.ref * 0.93) * 1000 : null,
        vol: r.vol.toDouble(), val: r.vol * r.p * (vn ? 1000 : 1),
        fBuy: r.nnb?.toDouble(), fSell: r.nns?.toDouble(), fRoom: r.room, ptVol: r.ptv?.toDouble(), ptVal: r.ptv == null ? null : r.ptv! * r.p * 1000,
        asof: at,
      ));
      signals[r.t] = SignalRow(symbol: r.t, level: r.lvl, learning: r.learn == 1, asof: at, items: [
        if (r.s1 == 1) const SignalItem('S1'),
        if (r.s2 != null && r.s2 != 0) SignalItem('S2', r.s2! > 0 ? 'buy' : 'sell'),
        if (r.s3 == 1) const SignalItem('S3'),
      ]);
      for (final z in r.zones) {
        zones.add(Zone(symbol: r.t, kind: z.$3, lo: z.$1 * (vn ? 1000 : 1), hi: z.$2 * (vn ? 1000 : 1), asof: at));
      }
    }
    final stamp = at.subtract(const Duration(hours: 1));
    return MarketData(
      quotes: quotes, signals: signals, zones: zones, asof: at,
      status: BotStatus(lastSnapshot: at, lateMinutes: 0, missedSlots: 0, source: 'demo'),
      digests: [
        Digest(date: '${at.year}-${at.month}-${at.day}', kind: 'slot-0930', createdAt: at,
            body: 'Mức 3: ${rows.where((r) => r.lvl == 3).map((r) => r.t).join(', ')}.\nKhối lượng tăng đột biến ở ${rows.where((r) => r.s1 == 1).length} mã.\nKhối ngoại ròng dương ở ${rows.where((r) => (r.s2 ?? 0) > 0).length} mã.'),
      ],
      news: [
        NewsItem(title: 'FPT ký hợp đồng chuyển đổi số mới tại Nhật Bản', url: 'https://cafef.vn', source: 'CafeF', symbol: 'FPT', publishedAt: stamp),
        NewsItem(title: 'Hoà Phát: sản lượng thép tháng 10 tăng 9% so với cùng kỳ', url: 'https://vietstock.vn', source: 'Vietstock', symbol: 'HPG', publishedAt: stamp.subtract(const Duration(minutes: 30))),
        NewsItem(title: 'Vinamilk công bố lịch chia cổ tức tiền mặt', url: 'https://vnexpress.net', source: 'VnExpress', symbol: 'VNM', publishedAt: stamp.subtract(const Duration(hours: 1))),
      ],
    );
  }

  @override
  Future<List<SignalRow>> signalHistory(Market market, String symbol, {int limit = 60}) async => history(market, symbol, limit);

  @override
  Future<List<DailyBar>> bars(Market market, String symbol, {int days = 60}) async {
    final r = _rows.firstWhere((r) => r.t == symbol && r.market == market, orElse: () => _rows.first);
    final out = <DailyBar>[];
    var v = r.ref * (market == Market.vn ? 1000 : 1);
    for (var i = days; i > 0; i--) {
      v *= 1 + ((i * 37 % 11) - 5) / 400;
      out.add(DailyBar(date: _now.subtract(Duration(days: i)), close: v, vol: r.vol * (0.7 + (i % 5) / 10)));
    }
    return out;
  }
}

extension on DemoRepository {
  List<SignalRow> history(Market market, String symbol, int limit) {
    final r = DemoRepository._rows.firstWhere((r) => r.t == symbol && r.market == market, orElse: () => DemoRepository._rows.first);
    return [
      for (var i = 0; i < 12 && i < limit; i++)
        SignalRow(
          symbol: symbol, level: (r.lvl - (i % 4 == 0 ? 0 : i % 4)).clamp(0, 3), learning: false,
          asof: _now.subtract(Duration(minutes: 30 * i * (i > 5 ? 8 : 1))),
          items: i % 3 == 0 ? const [SignalItem('S1'), SignalItem('S2', 'buy')] : i % 3 == 1 ? const [SignalItem('S3')] : const [],
        ),
    ];
  }
}

class _Row {
  const _Row(this.t, this.name, this.ex, this.market, this.ref, this.p, this.vol, this.lvl, this.s1, this.s2, this.s3, this.learn,
      this.nnb, this.nns, this.room, this.ptv, this.zones);
  final String t, name, ex;
  final Market market;
  final double ref, p;
  final int vol, lvl, s1, learn;
  final int? s2, s3, nnb, nns, ptv;
  final double? room;
  final List<(double, double, String)> zones;
}
