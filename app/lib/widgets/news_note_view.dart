import 'package:flutter/material.dart';

import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../util/news_note.dart';
import 'common.dart';

/// The bot's note under a headline: kind and lean as tags, what such stories touch, the reason, and, when the lean is a
/// guess about direction, the disclaimer.
class NewsNoteView extends StatelessWidget {
  const NewsNoteView(this.note, {super.key, this.showKind = true});
  final ShownNote note;
  final bool showKind; // a tile that already shows its own event tag leaves the kind out

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final small = AppText.base(c.text2, size: Ts.xs);
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
          if (showKind) Tag(note.kind),
          Tag(note.lean),
        ]),
        if (note.aspect.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text(note.aspect, style: small)),
        if (note.reason.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 2), child: Text(note.reason, style: small)),
        if (note.guess) Padding(padding: const EdgeInsets.only(top: 2), child: Text(noteDisclaimer, style: AppText.base(c.text3, size: Ts.xs))),
      ]),
    );
  }
}
