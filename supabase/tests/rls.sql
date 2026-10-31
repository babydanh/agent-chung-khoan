-- Run after all migrations (psql -v ON_ERROR_STOP=1 -f supabase/tests/rls.sql, or the Supabase SQL Editor).
-- Everything is rolled back; success prints 'RLS OK'. Any failed check raises and aborts the script.
begin;

-- Test helpers (rolled back with the rest). _t_count: rows visible to the current role, 0 if the grant is revoked.
-- _t_exec: rows affected by a statement, -1 if it raised (RLS violation, missing privilege, ...).
create function public._t_count(rel text) returns bigint language plpgsql as $$
declare n bigint;
begin
  execute format('select count(*) from %s', rel) into n;
  return n;
exception when insufficient_privilege then return 0;
end $$;
create function public._t_exec(stmt text) returns int language plpgsql as $$
declare n int;
begin
  execute stmt;
  get diagnostics n = row_count;
  return n;
exception when others then return -1;
end $$;
create function public._t_as(uid uuid) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', uid, 'role', 'authenticated')::text, true) $$;
grant execute on function public._t_count(text), public._t_exec(text), public._t_as(uuid) to anon, authenticated;

-- Fixtures: A and B are normal users, O is the app owner.
insert into auth.users (id) values
  ('aaaaaaaa-0000-0000-0000-00000000000a'), ('bbbbbbbb-0000-0000-0000-00000000000b'), ('cccccccc-0000-0000-0000-00000000000c');
insert into public.app_owners values ('cccccccc-0000-0000-0000-00000000000c');

insert into public.snapshot_meta (market, asof, slot_start, symbols, signals) values ('VN', now(), now(), 1, 0), ('US', now(), now(), 1, 0);
insert into public.quotes_latest (market, symbol, exchange, price, asof) values ('VN', 'TST', 'HOSE', 10, now()), ('US', 'TST', 'NASDAQ', 20, now());
insert into public.bars_30m (market, symbol, bar_start, vol, val, fnet, pt_val) values ('VN', 'TST', now(), 1, 1, 0, 0);
insert into public.signals (market, asof, symbol, level, learning, items) values
  ('VN', now(), 'TST', 1, true, '[{"vol":1}]'), ('US', now(), 'TST', 2, true, '[{"price":20}]');
insert into public.baseline_30m values ('VN', 'TST', 540, 20, 1, 1, 0, 0, now());
insert into public.bars_1d (market, symbol, trade_date, close) values ('VN', 'TST', current_date, 10), ('US', 'TST', current_date, 20);
insert into public.zones (market, symbol, kind, price_lo, price_hi, asof) values ('VN', 'TST', 'support', 9, 10, now()), ('US', 'TST', 'support', 19, 20, now());
insert into public.heartbeat values ('VN', 'engine', now(), null);
insert into public.snapshot_compact values ('VN', now(), '{}');
insert into public.digests (market, digest_date, kind, body) values ('VN', current_date, 'close', 'x');
insert into public.news (market, title, url, published_at) values ('VN', 't', 'https://example.test/1', now());
insert into public.watchlists (user_id, market, symbol) values
  ('aaaaaaaa-0000-0000-0000-00000000000a', 'VN', 'AAA'), ('bbbbbbbb-0000-0000-0000-00000000000b', 'VN', 'BBB');
insert into public.prefs (user_id) values ('aaaaaaaa-0000-0000-0000-00000000000a'), ('bbbbbbbb-0000-0000-0000-00000000000b');
insert into public.consents (user_id, kind, version, granted) values
  ('aaaaaaaa-0000-0000-0000-00000000000a', 'tos', '1', true), ('bbbbbbbb-0000-0000-0000-00000000000b', 'tos', '1', true);

-- Dedupe: the same market+slot cannot be written twice, the same slot in the other market can.
do $$
begin
  if public._t_exec($q$insert into public.snapshot_meta (market, asof, slot_start, symbols, signals)
       select market, now(), slot_start, 1, 0 from public.snapshot_meta where market = 'VN'$q$) <> -1
  then raise exception 'snapshot_meta accepts a duplicate (market, slot_start)'; end if;
end $$;

-- anon: nothing readable in any public table or view.
set local role anon;
do $$
declare r record;
begin
  for r in select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'public' and c.relkind in ('r', 'p', 'v') loop
    if public._t_count('public.' || quote_ident(r.relname)) <> 0 then raise exception 'anon can read %', r.relname; end if;
  end loop;
  if public._t_exec('select public.delete_my_account()') > 0 then raise exception 'anon can call delete_my_account'; end if;
  if public._t_exec('select public.is_app_owner()') > 0 then raise exception 'anon can call is_app_owner'; end if;
end $$;
reset role;

-- A: a normal signed-in user.
select public._t_as('aaaaaaaa-0000-0000-0000-00000000000a');
set local role authenticated;
do $$
declare bid constant text := 'bbbbbbbb-0000-0000-0000-00000000000b';
begin
  if public.is_app_owner() then raise exception 'A is app owner'; end if;

  -- own rows readable, other user's rows invisible
  if public._t_count('public.watchlists') <> 1 then raise exception 'A should see exactly its own watchlist'; end if;
  if public._t_count('public.watchlists where user_id = ''' || bid || '''') <> 0 then raise exception 'A reads B watchlists'; end if;
  if public._t_count('public.prefs') <> 1 or public._t_count('public.prefs where user_id = ''' || bid || '''') <> 0 then raise exception 'prefs isolation broken'; end if;
  if public._t_count('public.consents') <> 1 or public._t_count('public.consents where user_id = ''' || bid || '''') <> 0 then raise exception 'consents isolation broken'; end if;

  -- cannot write as B; can write as self
  if public._t_exec('insert into public.watchlists (user_id, market, symbol) values (''' || bid || ''', ''VN'', ''ZZZ'')') > 0 then raise exception 'A inserted a watchlist row for B'; end if;
  if public._t_exec('insert into public.prefs (user_id) values (''cccccccc-0000-0000-0000-00000000000c'')') > 0 then raise exception 'A inserted prefs for B'; end if;
  if public._t_exec('insert into public.consents (user_id, kind, version, granted) values (''' || bid || ''', ''tos'', ''2'', true)') > 0 then raise exception 'A inserted consent for B'; end if;
  if public._t_exec('update public.watchlists set symbol = ''HACK'' where user_id = ''' || bid || '''') > 0 then raise exception 'A updated B watchlist'; end if;
  if public._t_exec('delete from public.watchlists where user_id = ''' || bid || '''') > 0 then raise exception 'A deleted B watchlist'; end if;
  if public._t_exec('update public.watchlists set user_id = ''' || bid || ''' where symbol = ''AAA''') > 0 then raise exception 'A moved its row to B'; end if;
  if public._t_exec('insert into public.watchlists (market, symbol) values (''VN'', ''NEW'')') <> 1 then raise exception 'A cannot insert its own watchlist row'; end if;
  if public._t_exec('delete from public.watchlists where symbol = ''NEW''') <> 1 then raise exception 'A cannot delete its own watchlist row'; end if;
  if public._t_exec('update public.prefs set data = ''{"a":1}''') <> 1 then raise exception 'A cannot update its prefs'; end if;
  if public._t_exec('insert into public.consents (kind, version, granted) values (''tos'', ''2'', true)') <> 1 then raise exception 'A cannot add a consent'; end if;
  if public._t_exec('update public.consents set granted = false') > 0 or public._t_exec('delete from public.consents') > 0 then raise exception 'consents are not append-only'; end if;

  -- shared market tables: VN readable, US prices/volumes hidden from non-owners
  if public._t_count('public.snapshot_meta') < 2 then raise exception 'A cannot read snapshot_meta'; end if;
  if public._t_count('public.quotes_latest where market = ''VN''') <> 1 then raise exception 'A cannot read VN quotes'; end if;
  if public._t_count('public.quotes_latest where market = ''US''') <> 0 then raise exception 'A reads US quotes'; end if;
  if public._t_count('public.signals where market = ''VN''') <> 1 then raise exception 'A cannot read VN signals'; end if;
  if public._t_count('public.signals where market = ''US''') <> 0 then raise exception 'A reads US signals (items carry price/volume)'; end if;
  if public._t_count('public.signal_levels where market = ''US''') <> 1 then raise exception 'A cannot read US signal levels'; end if;
  if public._t_count('public.bars_1d where market = ''VN''') <> 1 or public._t_count('public.bars_1d where market = ''US''') <> 0 then raise exception 'bars_1d market rule broken'; end if;
  if public._t_count('public.zones where market = ''VN''') <> 1 or public._t_count('public.zones where market = ''US''') <> 0 then raise exception 'zones market rule broken'; end if;
  if public._t_count('public.digests') <> 1 then raise exception 'A cannot read digests'; end if;
  if public._t_count('public.news') <> 1 then raise exception 'A cannot read news'; end if;

  -- bot-only tables
  if public._t_count('public.bars_30m') <> 0 then raise exception 'A reads bars_30m'; end if;
  if public._t_count('public.baseline_30m') <> 0 then raise exception 'A reads baseline_30m'; end if;
  if public._t_count('public.heartbeat') <> 0 then raise exception 'A reads heartbeat'; end if;
  if public._t_count('public.snapshot_compact') <> 0 then raise exception 'A reads snapshot_compact'; end if;
  if public._t_count('public.app_owners') <> 0 then raise exception 'A reads app_owners'; end if;

  -- the app never writes market data
  if public._t_exec('insert into public.digests (market, digest_date, kind, body) values (''VN'', current_date, ''open'', ''x'')') > 0 then raise exception 'A inserted digests'; end if;
  if public._t_exec('update public.digests set body = ''y''') > 0 then raise exception 'A updated digests'; end if;
  if public._t_exec('delete from public.digests') > 0 then raise exception 'A deleted digests'; end if;
  if public._t_exec('insert into public.news (market, title, url, published_at) values (''VN'', ''t'', ''https://example.test/2'', now())') > 0 then raise exception 'A inserted news'; end if;
  if public._t_exec('update public.news set title = ''y''') > 0 or public._t_exec('delete from public.news') > 0 then raise exception 'A changed news'; end if;
  if public._t_exec('insert into public.zones (market, symbol, kind, price_lo, price_hi, asof) values (''VN'', ''X'', ''support'', 1, 2, now())') > 0 then raise exception 'A inserted zones'; end if;
  if public._t_exec('update public.zones set kind = ''y''') > 0 or public._t_exec('delete from public.zones') > 0 then raise exception 'A changed zones'; end if;
  if public._t_exec('insert into public.snapshot_meta (market, asof, slot_start, symbols, signals) values (''VN'', now() + interval ''1 hour'', now() + interval ''1 hour'', 1, 0)') > 0 then raise exception 'A inserted snapshot_meta'; end if;
  if public._t_exec('update public.quotes_latest set price = 1') > 0 then raise exception 'A updated quotes_latest'; end if;
  if public._t_exec('delete from public.signals') > 0 then raise exception 'A deleted signals'; end if;
  if public._t_exec('insert into public.bars_1d (market, symbol, trade_date) values (''VN'', ''X'', current_date)') > 0 then raise exception 'A inserted bars_1d'; end if;
end $$;
reset role;

-- O: the app owner sees US data too, and still cannot write it.
select public._t_as('cccccccc-0000-0000-0000-00000000000c');
set local role authenticated;
do $$
begin
  if not public.is_app_owner() then raise exception 'owner not recognised'; end if;
  if public._t_count('public.quotes_latest') <> 2 then raise exception 'owner cannot read US quotes'; end if;
  if public._t_count('public.signals') <> 2 then raise exception 'owner cannot read US signals'; end if;
  if public._t_count('public.bars_1d') <> 2 or public._t_count('public.zones') <> 2 then raise exception 'owner cannot read US bars_1d/zones'; end if;
  if public._t_count('public.watchlists') <> 0 then raise exception 'owner reads other users watchlists'; end if;
  if public._t_count('public.app_owners') <> 0 then raise exception 'owner reads app_owners directly'; end if;
  if public._t_exec('update public.quotes_latest set price = 1') > 0 then raise exception 'owner updated quotes_latest'; end if;
end $$;
reset role;

-- A deletes its own account: its rows go, B's stay.
select public._t_as('aaaaaaaa-0000-0000-0000-00000000000a');
set local role authenticated;
select public.delete_my_account();
reset role;
do $$
begin
  if (select count(*) from auth.users where id = 'aaaaaaaa-0000-0000-0000-00000000000a') <> 0 then raise exception 'A still in auth.users'; end if;
  if (select count(*) from public.watchlists where user_id = 'aaaaaaaa-0000-0000-0000-00000000000a') <> 0 then raise exception 'A watchlists survived'; end if;
  if (select count(*) from public.prefs      where user_id = 'aaaaaaaa-0000-0000-0000-00000000000a') <> 0 then raise exception 'A prefs survived'; end if;
  if (select count(*) from public.consents   where user_id = 'aaaaaaaa-0000-0000-0000-00000000000a') <> 0 then raise exception 'A consents survived'; end if;
  if (select count(*) from auth.users where id = 'bbbbbbbb-0000-0000-0000-00000000000b') <> 1 then raise exception 'B account deleted'; end if;
  if (select count(*) from public.watchlists where user_id = 'bbbbbbbb-0000-0000-0000-00000000000b') <> 1 then raise exception 'B watchlists changed'; end if;
  if (select count(*) from public.prefs      where user_id = 'bbbbbbbb-0000-0000-0000-00000000000b') <> 1 then raise exception 'B prefs changed'; end if;
  if (select count(*) from public.consents   where user_id = 'bbbbbbbb-0000-0000-0000-00000000000b') <> 1 then raise exception 'B consents changed'; end if;
end $$;

rollback;
select 'RLS OK' as result;
