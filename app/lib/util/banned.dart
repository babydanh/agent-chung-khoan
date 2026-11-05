/// Scanner for wording that reads as investment advice (same rules as pipeline/banned.py).
///
/// Text is lower-cased and stripped of accents and invisible characters first, so one pattern covers "Nên mua",
/// "nen mua" and "n<zero-width>ên mua". A false alarm only drops one sentence.
library;

/// Disclaimers shown next to the data; they contain a banned word on purpose.
const allowedPhrases = [
  'không phải khuyến nghị đầu tư',
  'không phải tư vấn đầu tư, khuyến nghị mua/bán hay lời mời giao dịch',
];

final _patterns = <RegExp>[
  for (final p in [
    r'\bnen\s+(mua|ban|giu|gom|chot loi|cat lo|bat day|nam giu)\b',
    r'khuyen\s*nghi',
    r'khuyen cao\s+(mua|ban|nam giu)',
    r'\b(mua|ban)\s+ngay\b',
    r'chac\s*chan',
    r'cam\s*ket',
    r'dam bao loi nhuan',
    r'loi nhuan dam bao',
    r'chac an',
    r'ma vang',
    r'sieu co phieu',
    r'ca map',
    r'sap\s+(keo|tang manh|bay)',
    r'\b(diem|vung|tin hieu)\s+(mua|ban)\b',
    r'gia muc tieu',
    r'tat tay',
    r'\ball\s*in\b',
    r'phim hang',
    r'\bdang\s+(mua|ban)\b',
    r'\bnen\b(\s+\w+){0,3}\s+(mua vao|ban ra)\b',
    r'\bse\s+(tang|giam)\b',
    r'\bgap\s+(doi|ba)\b',
    r'\bhay\s+(mua|ban)\b',
    r'\bnen\s+can\s+nhac\s+(mua|ban)\b',
    r'\bnen\s+(xuong\s+tien|giai\s+ngan|chot\s+loi|cat\s+lo|gom|canh\s+mua|canh\s+ban)\b',
    r'\bco\s+hoi\s+(mua|ban)\b',
    r'\bgood\s+time\s+to\s+(buy|sell)\b',
    r'\bconsider\s+(buying|selling)\b',
    r'\btime\s+to\s+(buy|sell)\b',
    r'\b(du\s+kien|ky\s+vong|nhieu\s+kha\s+nang|co\s+the)\s+(se\s+)?(tang|giam)\b',
    r'\b(should|strong)\s+(buy|sell)\b',
    r'price target',
    r'\brecommend',
    r'\bguarantee',
  ])
    RegExp(p),
];

/// Lower case, no accents (đ becomes d), no combining marks or invisible format characters, single spaces.
String normalize(String text) {
  var t = text.toLowerCase().replaceAll('đ', 'd');
  t = _stripAccents(t);
  t = t.replaceAll(RegExp('[​-‏‪-‮⁠-⁤﻿­]'), '');
  return t.replaceAll(RegExp(r'\s+'), ' ');
}

const _from = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹ';
const _to = 'aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyy';
final _map = {for (var i = 0; i < _from.length; i++) _from[i]: _to[i]};

String _stripAccents(String s) {
  final b = StringBuffer();
  for (final r in s.runes) {
    final c = String.fromCharCode(r);
    if (r >= 0x300 && r <= 0x36f) continue; // combining marks of decomposed text
    b.write(_map[c] ?? c);
  }
  return b.toString();
}

final _allowed = [for (final p in allowedPhrases) normalize(p)];

/// The patterns that match; an empty list means the text is clean.
List<String> findBanned(String text) {
  var t = normalize(text);
  for (final p in _allowed) {
    t = t.replaceAll(p, ' ');
  }
  return [for (final p in _patterns) if (p.hasMatch(t)) p.pattern];
}
