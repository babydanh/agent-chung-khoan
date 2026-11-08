/// What the app shows of the bot's note on a headline. The bot already guards its text; the app checks again, so
/// wording that reads as advice or a price forecast is never shown, and a lean needs a reason to be shown as a lean.
library;

import '../models/models.dart';
import '../news/rank.dart' show eventByKey;
import 'banned.dart';

const leanPositive = 'Dự đoán: nghiêng tích cực';
const leanNegative = 'Dự đoán: nghiêng tiêu cực';
const leanUnclear = 'Chưa rõ tác động';
const noteDisclaimer = 'Dự đoán tham khảo từ tiêu đề, có thể sai; không phải khuyến nghị đầu tư.';

class ShownNote {
  const ShownNote({required this.kind, required this.aspect, required this.lean, required this.reason, required this.guess});
  final String kind, aspect, lean, reason;
  final bool guess; // true when [lean] is a guess about direction: the disclaimer goes with it
}

ShownNote? shownNote(NewsNote? n) {
  if (n == null) return null;
  final aspect = findBanned(n.aspect).isEmpty ? n.aspect : '';
  final reason = findBanned(n.note).isEmpty ? n.note : '';
  final guess = reason.isNotEmpty && (n.outlook == 'pos' || n.outlook == 'neg');
  return ShownNote(
    kind: eventByKey(n.kind).label,
    aspect: aspect,
    reason: reason,
    lean: !guess ? leanUnclear : (n.outlook == 'pos' ? leanPositive : leanNegative),
    guess: guess,
  );
}
