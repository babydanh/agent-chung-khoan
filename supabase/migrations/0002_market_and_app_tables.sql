-- 0002: multi-market (VN/US) keys, new bot tables, per-user app tables, RLS tightening.
-- Expand-style: 0001 is untouched, no table/column is dropped. Tables here are small (pre-launch), so key
-- swaps and the CHECK scan are cheap; no large index is built, so CONCURRENTLY (not allowed in a
-- migration transaction anyway) is not needed. Only the bot (secret key, bypasses RLS) writes market data.

-- New tables/sequences created from here on are NOT open to the API roles; section 5 grants reads explicitly.
alter default privileges in schema public revoke all on tables from anon, authenticated;

------------------------------------------------------------------------------------------------------
-- 1. market column + composite keys, so a VN and a US ticker with the same symbol never collide
------------------------------------------------------------------------------------------------------
-- No DEFAULT on purpose: the primary keys change below, so an old writer breaks anyway, and a silent default
-- would file a US row under VN. Existing rows (all VN so far) are backfilled, then the column becomes NOT NULL.
alter table public.quotes_latest add column market text check (market in ('VN', 'US'));
alter table public.bars_30m      add column market text check (market in ('VN', 'US'));
alter table public.signals       add column market text check (market in ('VN', 'US'));
update public.quotes_latest set market = 'VN' where market is null;
update public.bars_30m      set market = 'VN' where market is null;
update public.signals       set market = 'VN' where market is null;
alter table public.quotes_latest alter column market set not null;
alter table public.bars_30m      alter column market set not null;
alter table public.signals       alter column market set not null;

alter table public.quotes_latest drop constraint quotes_latest_pkey, add primary key (market, symbol);
alter table public.bars_30m      drop constraint bars_30m_pkey,      add primary key (market, symbol, bar_start);
alter table public.signals       drop constraint signals_pkey,       add primary key (market, asof, symbol);

create index signals_market_symbol_asof_idx on public.signals (market, symbol, asof desc);

-- snapshot_meta: one row per (market, slot). slot_start is the scheduled window start, not the wall clock,
-- so a re-run or a late run of the same slot hits the unique key instead of duplicating.
alter table public.snapshot_meta add column slot_start timestamptz;
update public.snapshot_meta set slot_start = asof where slot_start is null;
alter table public.snapshot_meta alter column slot_start set not null;
alter table public.snapshot_meta add constraint snapshot_meta_market_slot_start_key unique (market, slot_start);
alter table public.snapshot_meta drop constraint snapshot_meta_market_asof_key;  -- replaced by the slot key above

------------------------------------------------------------------------------------------------------
-- 2. new bot-side / shared market tables
------------------------------------------------------------------------------------------------------
-- 20-day average per 30-minute slot of the trading day. Bot-only.
create table public.baseline_30m (
  market     text not null check (market in ('VN', 'US')),
  symbol     text not null,
  slot       smallint not null check (slot between 0 and 1439),  -- minute of day at slot start (exchange local time)
  days       smallint not null check (days >= 0),                 -- sessions that went into the averages
  avg_vol    numeric not null,
  avg_val    numeric not null,
  avg_fnet   numeric not null,
  avg_pt_val numeric not null,
  updated_at timestamptz not null default now(),
  primary key (market, symbol, slot)
);

create table public.bars_1d (
  market     text not null check (market in ('VN', 'US')),
  symbol     text not null,
  trade_date date not null,
  open       numeric,
  high       numeric,
  low        numeric,
  close      numeric,
  vol        bigint,
  val        bigint,
  primary key (market, symbol, trade_date)
);

create table public.zones (
  id       bigint generated always as identity primary key,
  market   text not null check (market in ('VN', 'US')),
  symbol   text not null,
  kind     text not null,            -- e.g. support / resistance, free text from the engine
  price_lo numeric not null,
  price_hi numeric not null,
  asof     timestamptz not null,
  check (price_lo <= price_hi)
);
create index zones_market_symbol_asof_idx on public.zones (market, symbol, asof desc);

-- Bot liveness, one row per (market, job). Bot-only.
create table public.heartbeat (
  market    text not null check (market in ('VN', 'US')),
  job       text not null,
  last_seen timestamptz not null,
  detail    jsonb,
  primary key (market, job)
);

-- Compact previous-run state used by the engine to diff snapshots. Bot-only.
create table public.snapshot_compact (
  market     text not null check (market in ('VN', 'US')),
  slot_start timestamptz not null,
  payload    jsonb not null,
  primary key (market, slot_start)
);

create table public.digests (
  id          bigint generated always as identity primary key,
  market      text not null check (market in ('VN', 'US')),
  digest_date date not null,
  kind        text not null,         -- e.g. open / midday / close
  body        text not null,
  created_at  timestamptz not null default now(),
  unique (market, digest_date, kind)
);

create table public.news (
  id           bigint generated always as identity primary key,
  market       text not null check (market in ('VN', 'US')),
  symbol       text,
  title        text not null,
  url          text not null unique,
  source       text,
  published_at timestamptz not null
);
create index news_market_published_idx on public.news (market, published_at desc);

------------------------------------------------------------------------------------------------------
-- 3. app owner + helpers
------------------------------------------------------------------------------------------------------
-- Who counts as "the app owner" lives in a table, not in a JWT claim: user_metadata is user-editable and
-- app_metadata needs an admin call to set. A table is auditable and only the secret key can change it.
create table public.app_owners (
  user_id uuid primary key references auth.users (id) on delete cascade
);

create function public.is_app_owner() returns boolean
language sql stable security definer set search_path = ''
as $$ select exists (select 1 from public.app_owners where user_id = auth.uid()) $$;

-- VN data is shared with every signed-in user; US prices/volumes only with the app owner.
create function public.can_read_market(m text) returns boolean
language sql stable set search_path = ''
as $$ select m = 'VN' or public.is_app_owner() $$;

revoke all on function public.is_app_owner()          from public, anon;
revoke all on function public.can_read_market(text)   from public, anon;
grant execute on function public.is_app_owner()        to authenticated;
grant execute on function public.can_read_market(text) to authenticated;

------------------------------------------------------------------------------------------------------
-- 4. per-user tables (FK to auth.users, cascade on account deletion)
------------------------------------------------------------------------------------------------------
create table public.watchlists (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  market     text not null check (market in ('VN', 'US')),
  symbol     text not null check (char_length(symbol) <= 12),
  created_at timestamptz not null default now(),
  unique (user_id, market, symbol)  -- also serves lookups by user_id (leading column)
);

-- At most 200 rows per user. The advisory lock serialises one user's concurrent inserts so the cap holds.
create function public.watchlists_cap() returns trigger
language plpgsql set search_path = ''
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.user_id::text, 0));
  if (select count(*) from public.watchlists where user_id = new.user_id) >= 200 then
    raise exception 'watchlist limit (200) reached' using errcode = 'check_violation';
  end if;
  return new;
end;
$$;
create trigger watchlists_cap before insert on public.watchlists
  for each row execute function public.watchlists_cap();

create table public.prefs (
  user_id    uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  data       jsonb not null default '{}' check (octet_length(data::text) <= 8192),
  updated_at timestamptz not null default now()
);  -- the primary key already indexes user_id

-- Append-only record of what the user agreed to (no update/delete policy on purpose).
create table public.consents (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind       text not null check (char_length(kind) <= 32),
  version    text not null check (char_length(version) <= 32),
  granted    boolean not null,
  created_at timestamptz not null default now()
);
create index consents_user_id_idx on public.consents (user_id);

-- Deletes only the caller. SECURITY DEFINER is needed because users cannot touch auth.users; the target is
-- always auth.uid(), never a parameter. ON DELETE CASCADE removes the caller's rows in the tables above.
create function public.delete_my_account() returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if auth.uid() is null then
    raise exception 'not authenticated';
  end if;
  delete from auth.users where id = auth.uid();
end;
$$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

------------------------------------------------------------------------------------------------------
-- 5. grants (Supabase default privileges give anon/authenticated everything; take it back, then add reads)
------------------------------------------------------------------------------------------------------
revoke all on public.quotes_latest, public.snapshot_meta, public.bars_30m, public.signals,
              public.baseline_30m, public.bars_1d, public.zones, public.heartbeat, public.snapshot_compact,
              public.digests, public.news, public.app_owners, public.watchlists, public.prefs, public.consents
  from anon, authenticated;

grant select on public.quotes_latest, public.snapshot_meta, public.signals, public.bars_1d, public.zones,
                public.digests, public.news to authenticated;
grant select, insert, update, delete on public.watchlists to authenticated;
grant select, insert, update         on public.prefs      to authenticated;
grant select, insert                 on public.consents   to authenticated;

------------------------------------------------------------------------------------------------------
-- 6. RLS
------------------------------------------------------------------------------------------------------
alter table public.baseline_30m     enable row level security;
alter table public.bars_1d          enable row level security;
alter table public.zones            enable row level security;
alter table public.heartbeat        enable row level security;
alter table public.snapshot_compact enable row level security;
alter table public.digests          enable row level security;
alter table public.news             enable row level security;
alter table public.app_owners       enable row level security;
alter table public.watchlists       enable row level security;
alter table public.prefs            enable row level security;
alter table public.consents         enable row level security;

-- Replace the 0001 "using (true)" policies: policies are OR-ed, so leaving them would leak US rows.
drop policy "signed-in users read quotes"  on public.quotes_latest;
drop policy "signed-in users read signals" on public.signals;
create policy "read quotes by market"  on public.quotes_latest for select to authenticated using ((select public.can_read_market(market)));
create policy "read signals by market" on public.signals       for select to authenticated using ((select public.can_read_market(market)));
create policy "read bars_1d by market" on public.bars_1d       for select to authenticated using ((select public.can_read_market(market)));
create policy "read zones by market"   on public.zones         for select to authenticated using ((select public.can_read_market(market)));
create policy "read digests by market" on public.digests       for select to authenticated using ((select public.can_read_market(market)));
create policy "read news by market"    on public.news          for select to authenticated using ((select public.can_read_market(market)));
-- (select ...) lets the planner evaluate the helper once per query instead of once per row.
-- snapshot_meta keeps its 0001 read policy (counts only, no prices).
-- bars_30m, baseline_30m, heartbeat, snapshot_compact, app_owners: RLS on, no policy -> secret key only.
-- No insert/update/delete policy on any market table: the app can never write them.

-- Non-owners still see US signal levels (no items, which carry price/volume) through this view. It runs with
-- the owner's rights, so it bypasses the signals policy, but it exposes only these columns.
create view public.signal_levels with (security_invoker = false) as
  select market, asof, symbol, level, learning from public.signals;
revoke all on public.signal_levels from anon, authenticated;
grant select on public.signal_levels to authenticated;

create policy "own watchlist select" on public.watchlists for select to authenticated using (user_id = (select auth.uid()));
create policy "own watchlist insert" on public.watchlists for insert to authenticated with check (user_id = (select auth.uid()));
create policy "own watchlist update" on public.watchlists for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own watchlist delete" on public.watchlists for delete to authenticated using (user_id = (select auth.uid()));

create policy "own prefs select" on public.prefs for select to authenticated using (user_id = (select auth.uid()));
create policy "own prefs insert" on public.prefs for insert to authenticated with check (user_id = (select auth.uid()));
create policy "own prefs update" on public.prefs for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own consents select" on public.consents for select to authenticated using (user_id = (select auth.uid()));
create policy "own consents insert" on public.consents for insert to authenticated with check (user_id = (select auth.uid()));

------------------------------------------------------------------------------------------------------
-- 7. bot helpers (RPC, secret key only)
------------------------------------------------------------------------------------------------------
-- Retention: signals/bars_30m 30 days (the baseline needs 20), snapshot_meta 60 days, snapshot_compact newest N slots per market.
create function public.cleanup_old_data(keep_compact int default 96) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare n_sig bigint; n_bars bigint; n_meta bigint; n_compact bigint;
begin
  delete from public.signals  where asof < now() - interval '30 days';           get diagnostics n_sig = row_count;
  delete from public.bars_30m where bar_start < now() - interval '30 days';      get diagnostics n_bars = row_count;
  delete from public.snapshot_meta where asof < now() - interval '60 days';      get diagnostics n_meta = row_count;
  delete from public.snapshot_compact sc using (
    select market, slot_start, row_number() over (partition by market order by slot_start desc) as rn
    from public.snapshot_compact
  ) r where sc.market = r.market and sc.slot_start = r.slot_start and r.rn > keep_compact;
  get diagnostics n_compact = row_count;
  return jsonb_build_object('signals', n_sig, 'bars_30m', n_bars, 'snapshot_meta', n_meta, 'snapshot_compact', n_compact);
end;
$$;

-- Database size in MB, so the bot can watch the free-tier budget.
create function public.db_size_mb() returns numeric
language sql stable security definer set search_path = ''
as $$ select round(pg_database_size(current_database()) / 1048576.0, 1) $$;

revoke all on function public.cleanup_old_data(int) from public, anon, authenticated;
revoke all on function public.db_size_mb()          from public, anon, authenticated;
grant execute on function public.cleanup_old_data(int) to service_role;
grant execute on function public.db_size_mb()          to service_role;
