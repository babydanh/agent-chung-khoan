-- The app opens without a login: the public (anon) key may read the VN rows of the market tables, nothing else.
-- US rows, the owner tables, the bot-only tables and every write stay closed to anon.
grant select on public.quotes_latest, public.snapshot_meta, public.signals, public.bars_1d, public.zones,
                public.digests, public.news to anon;

create policy "anon reads VN quotes"   on public.quotes_latest for select to anon using (market = 'VN');
create policy "anon reads VN snapshot" on public.snapshot_meta for select to anon using (market = 'VN');
create policy "anon reads VN signals"  on public.signals       for select to anon using (market = 'VN');
create policy "anon reads VN bars_1d"  on public.bars_1d       for select to anon using (market = 'VN');
create policy "anon reads VN zones"    on public.zones         for select to anon using (market = 'VN');
create policy "anon reads VN digests"  on public.digests       for select to anon using (market = 'VN');
create policy "anon reads VN news"     on public.news          for select to anon using (market = 'VN');
