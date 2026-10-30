#!/usr/bin/env bash
# Mutation check for rls.sql: breaks one policy/grant at a time on a throwaway Postgres and requires rls.sql to FAIL.
# Needs docker. Usage: supabase/tests/mutate.sh   (exit 0 = baseline passes and every mutation is caught)
set -u
cd "$(dirname "$0")/../.."
IMG=${PG_IMAGE:-postgres:16-alpine}
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
  'drop policy "signed-in users read digests" on public.digests'
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
for m in "${mutations[@]}"; do
  fresh "$m" || { echo "SETUP ERROR for mutation: $m"; survived=1; continue; }
  if out=$(run) && grep -q 'RLS OK' <<<"$out"; then echo "SURVIVED (test too weak): $m"; survived=1
  else echo "caught: $m"; fi
done
[ "$survived" -eq 0 ] && echo "all mutations caught" || { echo "some mutations survived or failed to set up"; exit 1; }
