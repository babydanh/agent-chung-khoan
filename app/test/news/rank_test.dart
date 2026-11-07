import 'package:agent_ck/news/rank.dart';
import 'package:agent_ck/util/banned.dart';
import 'package:flutter_test/flutter_test.dart';

final now = DateTime.utc(2026, 11, 5, 3);

Headline item(String title, {String source = 'CafeF', int ageMin = 0, List<String> symbols = const [], String? link}) => Headline(
      title: title,
      link: link ?? 'https://x.test/${title.hashCode.abs()}',
      source: source,
      published: now.subtract(Duration(minutes: ageMin)),
      symbols: symbols,
    );

Story story({String event = 'earnings', int sources = 1, DateTime? published, bool noTime = false, List<String> symbols = const ['HPG']}) => Story(
      head: Headline(title: 't', link: 'https://x.test/a', source: 'CafeF', published: noTime ? null : (published ?? now), symbols: symbols),
      event: eventByKey(event),
      sources: sources,
      cluster: 'c',
    );

void main() {
  group('classify', () {
    String key(String t) => classify(t).key;

    test('common headlines map to their event', () {
      const cases = {
        'Vinamilk công bố lịch chia cổ tức tiền mặt': 'dividend',
        'HPG báo lãi quý 3 tăng 20% so với cùng kỳ': 'earnings',
        'Doanh thu FPT 9 tháng vượt kế hoạch': 'earnings',
        'Thanh tra xử phạt công ty chứng khoán X': 'legal',
        'Khởi tố nguyên chủ tịch công ty Y': 'legal',
        'VIC phát hành thêm cổ phiếu tăng vốn điều lệ': 'issuance',
        'SSI thâu tóm công ty quản lý quỹ': 'deal',
        'FPT ký hợp đồng chuyển đổi số mới': 'contract',
        'Cổ đông lớn đăng ký giao dịch 2 triệu cổ phiếu': 'insider',
        'Ngân hàng Nhà nước giảm lãi suất điều hành': 'macro',
        'Dư nợ margin toàn thị trường đạt kỷ lục': 'liquidity',
        'VN-Index đóng cửa phiên trước ở 1.268 điểm': 'other',
      };
      cases.forEach((t, k) => expect(key(t), k, reason: t));
    });

    test('interest rate is macro, not earnings', () => expect(key('Lãi suất huy động tăng nhẹ'), 'macro'));
    test('keywords match whole words only', () {
      expect(key('Tập đoàn ký kết hợp đồng'), 'contract');
      expect(key('Phan Đình Dự nhận giải thưởng'), 'other');
    });

    test('every event has a label and a weight between zero and one, and the labels are clean', () {
      for (final e in events) {
        expect(e.label, isNotEmpty);
        expect(e.weight, inInclusiveRange(0, 1), reason: e.key);
        expect(findBanned(e.label), isEmpty, reason: e.label);
      }
    });
  });

  group('cluster', () {
    test('the same story from two sources is one cluster; the newest headline represents it', () {
      final a = item('FPT ký hợp đồng chuyển đổi số tại Nhật Bản', ageMin: 10, symbols: ['FPT']);
      final b = item('FPT ký hợp đồng chuyển đổi số mới tại Nhật', source: 'Vietstock', ageMin: 20, symbols: ['FPT']);
      final c = item('HPG báo lãi quý 3 tăng 20%', ageMin: 30, symbols: ['HPG']);
      final out = clusterStories([a, b, c]);
      expect(out, hasLength(2));
      final fpt = out.firstWhere((s) => s.head.symbols.contains('FPT'));
      expect(fpt.sources, 2);
      expect(fpt.head.link, a.link);
      expect(fpt.event.key, 'contract');
    });

    test('the cluster id does not depend on the order', () {
      final a = item('FPT ký hợp đồng chuyển đổi số tại Nhật Bản', ageMin: 10, symbols: ['FPT']);
      final b = item('FPT ký hợp đồng chuyển đổi số mới tại Nhật', source: 'Vietstock', ageMin: 20, symbols: ['FPT']);
      expect(clusterStories([a, b]).first.cluster, clusterStories([b, a]).first.cluster);
    });

    test('different stories about one symbol stay apart', () {
      final a = item('FPT ký hợp đồng chuyển đổi số', symbols: ['FPT']);
      final b = item('FPT chia cổ tức tiền mặt 10%', ageMin: 5, symbols: ['FPT']);
      expect(clusterStories([a, b]), hasLength(2));
    });

    test('the same source twice counts once', () {
      final a = item('FPT ký hợp đồng chuyển đổi số tại Nhật Bản', ageMin: 10, symbols: ['FPT']);
      final b = item('FPT ký hợp đồng chuyển đổi số mới tại Nhật', ageMin: 20, symbols: ['FPT']);
      expect(clusterStories([a, b]).first.sources, 1);
    });
  });

  group('hotScore', () {
    int score(Story s, {Set<String> watch = const {}, Set<String> flows = const {}}) => hotScore(s, now, watch, flows);

    test('a fresh earnings story that is watched and matches money flow scores 87', () {
      expect(score(story(), watch: {'HPG'}, flows: {'HPG'}), 87);
    });

    test('a perfect story scores 100', () => expect(score(story(sources: 3), watch: {'HPG'}, flows: {'HPG'}), 100));

    test('freshness fades from one hour to twelve', () {
      final fresh = score(story(published: now.subtract(const Duration(minutes: 30))));
      final half = score(story(published: now.subtract(const Duration(hours: 6, minutes: 30))));
      final old = score(story(published: now.subtract(const Duration(hours: 13))));
      expect(fresh, greaterThan(half));
      expect(half, greaterThan(old));
      expect(fresh, score(story()));
    });

    test('more sources score higher up to three', () {
      expect(score(story(sources: 1)), lessThan(score(story(sources: 2))));
      expect(score(story(sources: 2)), lessThan(score(story(sources: 3))));
      expect(score(story(sources: 3)), score(story(sources: 9)));
    });

    test('flow and watch each add fifteen, but only for symbols the story mentions', () {
      final base = score(story());
      expect(score(story(), watch: {'HPG'}) - base, 15);
      expect(score(story(), flows: {'HPG'}) - base, 15);
      expect(score(story(), watch: {'VNM'}, flows: {'VNM'}), base);
    });

    test('event weight orders the stories', () => expect(score(story(event: 'legal')), greaterThan(score(story(event: 'other')))));
    test('a missing publish time counts as somewhat old', () => expect(score(story(noTime: true)), lessThan(score(story()))));
  });
}
