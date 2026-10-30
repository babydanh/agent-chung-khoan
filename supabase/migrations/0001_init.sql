-- Market data tables. Only the bot (secret key, bypasses RLS) writes; signed-in users only read.

create table public.quotes_latest (
  symbol      text primary key,
  exchange    text not null,
  price       numeric,
  ref_price   numeric,
  ceil_price  numeric,
  floor_price numeric,
  vol         bigint,   -- cumulative volume of the day (KBS TT)
  val         bigint,   -- cumulative value of the day (KBS TV)
  f_buy       bigint,   -- foreign buy volume (FB)
  f_sell      bigint,   -- foreign sell volume (FS)
  f_room      bigint,   -- foreign room left (FR)
  pt_vol      bigint,   -- negotiated volume (PTQ)
  pt_val      bigint,   -- negotiated value (PTV)
  asof        timestamptz not null
);

-- One row per run; the app listens only to this table (realtime).
create table public.snapshot_meta (
  id      bigint generated always as identity primary key,
  market  text not null check (market in ('VN', 'US')),
  asof    timestamptz not null,
  symbols int not null,
  signals int not null,
  unique (market, asof)  -- re-running the same slot cannot duplicate it
);

-- Compact 30-minute windows, used by the bot as the 20-day baseline. Not readable by the app.
create table public.bars_30m (
  symbol    text not null,
  bar_start timestamptz not null,
  vol       bigint not null,
  val       bigint not null,
  fnet      bigint not null,
  pt_val    bigint not null,
  primary key (symbol, bar_start)
);

-- One row per symbol per run, shaped like pipeline.signals.evaluate().
create table public.signals (
  asof     timestamptz not null,
  symbol   text not null,
  level    smallint not null check (level between 0 and 3),
  learning boolean not null,
  items    jsonb not null,
  primary key (asof, symbol)
);

alter table public.quotes_latest enable row level security;
alter table public.snapshot_meta enable row level security;
alter table public.bars_30m      enable row level security;
alter table public.signals       enable row level security;

create policy "signed-in users read quotes"   on public.quotes_latest for select to authenticated using (true);
create policy "signed-in users read snapshot" on public.snapshot_meta for select to authenticated using (true);
create policy "signed-in users read signals"  on public.signals       for select to authenticated using (true);
-- bars_30m: RLS on and no policy, so only the secret key can touch it.

alter publication supabase_realtime add table public.snapshot_meta;
