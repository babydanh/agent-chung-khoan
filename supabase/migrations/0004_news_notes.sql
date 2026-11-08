-- One short note per headline, written by the bulletin job: the kind of story, what such stories usually touch (code-made
-- sentence), a lean (pos / neg / unclear, a guess shown as a guess) and the one-sentence reason. Keyed by the headline link,
-- which is how the app finds the note for a headline it read from the feeds itself.
-- Same access as `news`: VN rows for the public (anon) key and signed-in users, US rows for the app owner, no writes from the app.
create table public.news_notes (
  url        text primary key,
  market     text not null check (market in ('VN', 'US')),
  kind       text not null,
  aspect     text not null default '',
  outlook    text not null check (outlook in ('pos', 'neg', 'unclear')),
  note       text not null default '',
  created_at timestamptz not null default now()
);
create index news_notes_market_created_idx on public.news_notes (market, created_at desc);

-- Supabase default privileges hand anon/authenticated everything on a new table; take it back, then add the read.
revoke all on public.news_notes from anon, authenticated;
grant select on public.news_notes to anon, authenticated;

alter table public.news_notes enable row level security;
create policy "read news_notes by market" on public.news_notes for select to authenticated
  using (market = 'VN' or (select public.is_app_owner()));
create policy "anon reads VN news_notes" on public.news_notes for select to anon using (market = 'VN');
