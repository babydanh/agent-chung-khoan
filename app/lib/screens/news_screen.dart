import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/models.dart';
import '../news/rank.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../util/format.dart' as f;
import '../util/news_note.dart';
import '../widgets/common.dart';
import '../widgets/news_note_view.dart';
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
    final vn = _m == Market.vn;
    final stories = vn ? [for (final st in s.rankedStories()) if (_symbol == null || st.head.symbols.contains(_symbol)) st] : const <Story>[];
    final news = vn && s.stories.isNotEmpty ? const <NewsItem>[] : [for (final n in d.news) if (_symbol == null || n.symbol == _symbol) n];
    final symbols = vn && s.stories.isNotEmpty
        ? ({for (final st in s.stories) ...st.head.symbols}.toList()..sort())
        : ({for (final n in d.news) if (n.symbol != null && n.symbol!.isNotEmpty) n.symbol!}.toList()..sort());
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
            onRefresh: () => vn ? s.refreshAll() : s.load(_m),
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
              if (vn && s.newsError != null)
                Padding(padding: const EdgeInsets.fromLTRB(Sp.s4, 0, Sp.s4, Sp.s2), child: Text(s.newsError!, style: AppText.base(c.text3, size: Ts.xs))),
              if (stories.isEmpty && news.isEmpty)
                const SizedBox(height: 260, child: EmptyState('news', 'Chưa có tin'))
              else ...[
                for (final st in stories) ...[StoryTile(st, hot: s.isHot(st), flow: s.flowMatch(st), note: d.notes[st.head.link]), Divider(height: 1, indent: Sp.s4, endIndent: Sp.s4, color: c.line)],
                for (final n in news) ...[NewsTile(n, note: d.notes[n.url]), Divider(height: 1, indent: Sp.s4, endIndent: Sp.s4, color: c.line)],
              ],
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
          Text('Chỉ là thông tin, không phải khuyến nghị đầu tư.', style: AppText.base(c.text3, size: Ts.xs)),
        ])),
      ])),
    );
  }
}


/// A ranked story: title, event, symbols, source and time, with "Nóng" and "Khớp" flags.
class StoryTile extends StatelessWidget {
  const StoryTile(this.story, {super.key, required this.hot, required this.flow, this.note});
  final Story story;
  final bool hot, flow;
  final NewsNote? note; // the bot's note on the head headline, if it wrote one

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final h = story.head;
    final shown = shownNote(note);
    final vnTime = h.published?.toUtc().add(const Duration(hours: 7));
    return Semantics(
      button: true,
      child: InkWell(
        onTap: () async {
          final uri = Uri.tryParse(h.link);
          if (uri != null && uri.scheme == 'https') await launchUrl(uri, mode: LaunchMode.externalApplication);
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: Sp.s3),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
              if (hot) Tag('Nóng', icon: 'zap', color: c.levels[3]),
              if (flow) Tag('Khớp', icon: 'swap', color: c.accent),
              Tag(story.event.label),
              for (final sym in h.symbols.take(3)) Tag(sym),
            ]),
            const SizedBox(height: 6),
            Text(h.title, maxLines: 3, overflow: TextOverflow.ellipsis, style: AppText.base(c.text, weight: FontWeight.w600)),
            const SizedBox(height: 4),
            Row(children: [
              Expanded(child: Text('${story.sources > 1 ? '${story.sources} nguồn · ' : ''}${h.source} · ${f.hhmm(vnTime)}', style: AppText.num(c.text2, size: Ts.xs, weight: FontWeight.w400))),
              AppIcon('ext', size: 16, color: c.text3),
            ]),
            if (shown != null) NewsNoteView(shown, showKind: false), // the story already shows its event tag
          ]),
        ),
      ),
    );
  }
}
