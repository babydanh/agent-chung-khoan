-- Run in the Supabase SQL Editor after 0001_init.sql. Everything is rolled back; success prints 'RLS OK'.
begin;

insert into public.snapshot_meta (market, asof, symbols, signals) values ('VN', now(), 1, 0);
insert into public.quotes_latest (symbol, exchange, asof) values ('TST', 'HOSE', now());
insert into public.bars_30m values ('TST', now(), 1, 1, 0, 0);
insert into public.signals values (now(), 'TST', 0, true, '[]');

set local role anon;
do $$
begin
  if (select count(*) from public.snapshot_meta) <> 0 then raise exception 'anon can read snapshot_meta'; end if;
  if (select count(*) from public.quotes_latest) <> 0 then raise exception 'anon can read quotes_latest'; end if;
  if (select count(*) from public.signals) <> 0 then raise exception 'anon can read signals'; end if;
end $$;
reset role;

set local role authenticated;
do $$
declare
  blocked boolean;
  n int;
begin
  if (select count(*) from public.snapshot_meta) < 1 then raise exception 'authenticated cannot read snapshot_meta'; end if;
  if (select count(*) from public.quotes_latest) < 1 then raise exception 'authenticated cannot read quotes_latest'; end if;
  if (select count(*) from public.signals) < 1 then raise exception 'authenticated cannot read signals'; end if;
  if (select count(*) from public.bars_30m) <> 0 then raise exception 'authenticated can read bars_30m'; end if;

  blocked := false;
  begin
    insert into public.snapshot_meta (market, asof, symbols, signals) values ('VN', now() + interval '1 hour', 1, 0);
  exception when others then blocked := true;
  end;
  if not blocked then raise exception 'authenticated can insert snapshot_meta'; end if;

  begin
    update public.quotes_latest set price = 1;
    get diagnostics n = row_count;
  exception when others then n := 0;
  end;
  if n <> 0 then raise exception 'authenticated can update quotes_latest'; end if;

  begin
    delete from public.signals;
    get diagnostics n = row_count;
  exception when others then n := 0;
  end;
  if n <> 0 then raise exception 'authenticated can delete signals'; end if;
end $$;
reset role;

rollback;
select 'RLS OK' as result;
