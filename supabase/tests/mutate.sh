#!/usr/bin/env bash
# Mutation check for rls.sql: breaks one policy/grant at a time on a throwaway Postgres and requires rls.sql to FAIL.
# Needs docker. Usage: supabase/tests/mutate.sh   (exit 0 = baseline passes and every mutation is caught)
set -u
cd "$(dirname "$0")/../.."
IMG=${PG_IMAGE:-postgres:16-alpine@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab}
NAME=rls-mutation-$$
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=x "$IMG" >/dev/null
trap 'docker rm -f "$NAME" >/dev/null 2>&1' EXIT
for _ in $(seq 60); do docker exec "$NAME" pg_isready -U postgres -q && sleep 1 && docker exec "$NAME" pg_isready -U postgres -q && break; sleep 1; done

psql_() { docker exec -i -e PGOPTIONS='-c client_min_messages=error' "$NAME" psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }
fresh() {  # new database with shim + migrations, optional mutation SQL on stdin-less arg $1
  psql_ -d postgres -c "drop database if exists t" -c "create database t" >/dev/null
  psql_ -d t -f - < supabase/tests/local_shim.sql >/dev/null
  for f in supabase/migrations/*.sql; do psql_ -d t -f - < "$f" >/dev/null || return 1; done
  [ -n "${1:-}" ] && psql_ -d t -c "$1" >/dev/null
  return 0
}
run() { psql_ -d t -f - < supabase/tests/rls.sql 2>&1; }

fresh || { echo "migrations failed"; exit 1; }
out=$(run) && grep -q 'RLS OK' <<<"$out" || { echo "BASELINE FAILED"; echo "$out"; exit 1; }
echo "baseline: RLS OK"

# Each mutation weakens one control; rls.sql must then fail.
mutations=(
  'drop policy "own watchlist select" on public.watchlists'
  'drop policy "own watchlist select" on public.watchlists; create policy m on public.watchlists for select to authenticated using (true)'
  'drop policy "own watchlist insert" on public.watchlists; create policy m on public.watchlists for insert to authenticated with check (true)'
  'drop policy "own watchlist select" on public.watchlists; create policy ms on public.watchlists for select to authenticated using (true); drop policy "own watchlist update" on public.watchlists; create policy m on public.watchlists for update to authenticated using (true) with check (true)'
  'drop policy "own watchlist select" on public.watchlists; create policy ms on public.watchlists for select to authenticated using (true); drop policy "own watchlist delete" on public.watchlists; create policy m on public.watchlists for delete to authenticated using (true)'
  'drop policy "own prefs select" on public.prefs; create policy m on public.prefs for select to authenticated using (true)'
  'drop policy "own prefs insert" on public.prefs; create policy m on public.prefs for insert to authenticated with check (true)'
  'drop policy "own consents select" on public.consents; create policy m on public.consents for select to authenticated using (true)'
  'drop policy "own consents insert" on public.consents; create policy m on public.consents for insert to authenticated with check (true)'
  'grant update on public.consents to authenticated; create policy m on public.consents for update to authenticated using (true)'
  'drop policy "read signals by market" on public.signals; create policy m on public.signals for select to authenticated using (true)'
  'drop policy "read quotes by market" on public.quotes_latest; create policy m on public.quotes_latest for select to authenticated using (true)'
  'drop policy "read bars_1d by market" on public.bars_1d'
  'drop policy "read zones by market" on public.zones; create policy m on public.zones for select to authenticated using (true)'
  'drop policy "read digests by market" on public.digests'
  'drop policy "read digests by market" on public.digests; create policy m on public.digests for select to authenticated using (true)'
  'drop policy "read news by market" on public.news; create policy m on public.news for select to authenticated using (true)'
  'create or replace function public.can_read_market(m text) returns boolean language sql stable set search_path = '"''''"' as $f$ select true $f$'
  'create or replace function public.is_app_owner() returns boolean language sql stable security definer set search_path = '"''''"' as $f$ select true $f$'
  'create or replace view public.signal_levels with (security_invoker = false) as select market, asof, symbol, level, learning, items from public.signals'
  'alter view public.signal_levels set (security_invoker = true)'
  'grant select on public.signal_levels to anon'
  'alter function public.delete_my_account() set search_path = public'
  'alter function public.is_app_owner() set search_path = public'
  'grant execute on function public.delete_my_account() to anon'
  'grant execute on function public.cleanup_old_data(int) to authenticated'
  'grant execute on function public.db_size_mb() to anon'
  'alter table public.quotes_latest alter column market set default '"'VN'"
  'alter table public.bars_30m alter column market set default '"'VN'"
  'alter table public.signals alter column market set default '"'VN'"
  'alter table public.prefs drop constraint prefs_data_check'
  'alter table public.watchlists drop constraint watchlists_symbol_check'
  'alter table public.consents drop constraint consents_kind_check'
  'alter table public.consents drop constraint consents_version_check'
  'drop trigger watchlists_cap on public.watchlists'
  'create or replace function public.cleanup_old_data(keep_compact int default 96) returns jsonb language sql security definer set search_path = '"''''"' as $f$ select '"'{}'"'::jsonb $f$'
  'create or replace function public.db_size_mb() returns numeric language sql security definer set search_path = '"''''"' as $f$ select 0::numeric $f$'
  'drop index public.signals_market_symbol_asof_idx'
  'drop index public.zones_market_symbol_asof_idx'
  'create index watchlists_user_id_idx on public.watchlists (user_id)'
  'create index prefs_user_id_idx on public.prefs (user_id)'
  'grant insert on public.digests to authenticated; create policy m on public.digests for insert to authenticated with check (true)'
  'grant delete on public.news to authenticated; create policy m on public.news for delete to authenticated using (true)'
  'grant select on public.bars_30m to authenticated; create policy m on public.bars_30m for select to authenticated using (true)'
  'grant select on public.heartbeat to authenticated; create policy m on public.heartbeat for select to authenticated using (true)'
  'grant select on public.app_owners to authenticated; create policy m on public.app_owners for select to authenticated using (true)'
  'grant update on public.quotes_latest to authenticated; create policy m on public.quotes_latest for update to authenticated using (true)'
  'grant select on public.baseline_30m to anon; create policy m on public.baseline_30m for select to anon using (true)'
  'create policy m on public.digests for select to anon using (true); grant select on public.digests to anon'
  'create or replace function public.delete_my_account() returns void language sql security definer set search_path = '"''''"' as $f$ delete from auth.users $f$'
  'drop policy "signed-in users read snapshot" on public.snapshot_meta'
  'alter table public.snapshot_meta drop constraint snapshot_meta_market_slot_start_key'
)
survived=0
total=${#mutations[@]}; caught=0
for m in "${mutations[@]}"; do
  fresh "$m" || { echo "SETUP ERROR for mutation: $m"; survived=1; continue; }
  if out=$(run) && grep -q 'RLS OK' <<<"$out"; then echo "SURVIVED (test too weak): $m"; survived=1
  else echo "caught: $m"; caught=$((caught + 1)); fi
done
echo "mutations caught: $caught/$total"
[ "$survived" -eq 0 ] && echo "all mutations caught" || { echo "some mutations survived or failed to set up"; exit 1; }
