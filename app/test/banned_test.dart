import 'dart:io';

import 'package:agent_ck/util/banned.dart';
import 'package:flutter_test/flutter_test.dart';

const _short = 'Tham khảo, không phải khuyến nghị đầu tư.';
const _long = 'Nội dung chỉ mang tính thông tin tham khảo, không phải tư vấn đầu tư, khuyến nghị mua/bán hay lời mời giao dịch.';

void main() {
  test('normalize strips every Vietnamese accent exactly like the Python rules', () {
    const letters = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ';
    expect(normalize(letters + letters.toUpperCase()), 'aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyydaaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd');
  });

  test('flags each forbidden phrase', () {
    for (final t in ['Nên mua HPG', 'Nên bán FPT', 'Khuyến nghị nắm giữ', 'Mua ngay kẻo lỡ', 'Vùng mua hấp dẫn', 'Tín hiệu bán',
      'Giá mục tiêu 30.000', 'Mã vàng tuần này', 'Chắc chắn tăng', 'Cá mập sắp kéo', 'You should buy this', 'Price target raised']) {
      expect(findBanned(t), isNotEmpty, reason: t);
    }
  });

  test('flags variants without accents, with hidden characters and odd case', () {
    for (final t in ['nen mua', 'NÊN MUA', 'n​ên m‍ua', 'khuyen nghi', 'Khuyến nghị']) {
      expect(findBanned(t), isNotEmpty, reason: t);
    }
  });

  test('allows neutral wording and plain foreign-flow reporting', () {
    for (final t in ['Khối ngoại mua vào 2 triệu cổ phiếu', 'Khối ngoại bán ra', 'Vùng giá đáng chú ý 25.000 – 26.000',
      'Dấu hiệu dòng tiền lớn mức 2', 'Dữ liệu trễ 15 phút', 'Tự doanh mua vào, khối ngoại bán ra', 'Khối ngoại mua ròng lớn', 'NN mua', 'NN bán']) {
      expect(findBanned(t), isEmpty, reason: t);
    }
  });

  test('flags advice and forecasts in headlines', () {
    for (final t in ['HPG đáng mua vào lúc này', 'Nhà đầu tư nên mua vào HPG', 'Khối ngoại đang mua mạnh HPG', 'VNM sẽ tăng mạnh',
      'HPG gấp đôi lợi nhuận trong năm', 'Dự kiến tăng 20%', 'Hãy mua ngay']) {
      expect(findBanned(t), isNotEmpty, reason: t);
    }
  });

  test('the required disclaimers are allowed but never shelter a real recommendation', () {
    expect(findBanned(_short), isEmpty);
    expect(findBanned(_long), isEmpty);
    expect(findBanned('$_short Khuyến nghị mua HPG.'), isNotEmpty);
  });

  test('no string literal in the app source reads as advice', () {
    final literals = [RegExp(r"'((?:[^'\\]|\\.)*)'"), RegExp(r'"((?:[^"\\]|\\.)*)"')];
    final bad = <String>[];
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart') && !f.path.endsWith('util/banned.dart'))) {  // util/banned.dart holds the rules themselves
      for (final line in f.readAsLinesSync()) {
        if (line.trimLeft().startsWith('import ') || line.trimLeft().startsWith('//')) continue;
        for (final re in literals) {
          for (final m in re.allMatches(line)) {
            final s = m.group(1) ?? '';
            if (s.length > 3 && findBanned(s).isNotEmpty) bad.add('${f.path}: $s');
          }
        }
      }
    }
    expect(bad, isEmpty);
  });
}
