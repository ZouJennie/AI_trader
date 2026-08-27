create table if not exists public.user_ledgers (
  user_id uuid primary key references auth.users(id) on delete cascade,
  ledger jsonb not null default '{"version":1,"initialCash":200,"trades":[],"priceOverrides":{}}'::jsonb,
  updated_at timestamptz not null default now(),
  constraint user_ledgers_ledger_object check (jsonb_typeof(ledger) = 'object'),
  constraint user_ledgers_size_limit check (pg_column_size(ledger) <= 1048576)
);

alter table public.user_ledgers enable row level security;

revoke all on table public.user_ledgers from anon;
revoke all on table public.user_ledgers from authenticated;
grant select, insert, update on table public.user_ledgers to authenticated;
grant all on table public.user_ledgers to service_role;

drop policy if exists "users_select_own_ledger" on public.user_ledgers;
create policy "users_select_own_ledger"
on public.user_ledgers for select
to authenticated
using ((select auth.uid()) is not null and (select auth.uid()) = user_id);

drop policy if exists "users_insert_own_ledger" on public.user_ledgers;
create policy "users_insert_own_ledger"
on public.user_ledgers for insert
to authenticated
with check ((select auth.uid()) is not null and (select auth.uid()) = user_id);

drop policy if exists "users_update_own_ledger" on public.user_ledgers;
create policy "users_update_own_ledger"
on public.user_ledgers for update
to authenticated
using ((select auth.uid()) is not null and (select auth.uid()) = user_id)
with check ((select auth.uid()) is not null and (select auth.uid()) = user_id);
