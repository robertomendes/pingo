-- Pingo — esquema do banco (Supabase / Postgres)
-- Cole este arquivo inteiro no SQL Editor do projeto e clique em Run.
-- Pode rodar de novo sem problema: ele não apaga dados.
--
-- Modelo: a conta é do responsável (adulto). Cada conta tem crianças,
-- e cada criança tem lições. Row Level Security garante que cada conta
-- só lê e escreve as próprias linhas.

create table if not exists public.criancas (
  id          text primary key check (char_length(id) between 4 and 64),
  dono        uuid not null default auth.uid() references auth.users(id) on delete cascade,
  nome        text not null check (char_length(nome) between 1 and 20),
  cor         text not null check (char_length(cor) <= 16),
  hab         int  not null default 0 check (hab between 0 and 8),
  nivel       int  not null default 0 check (nivel between 0 and 2),
  teclado     boolean not null default false,
  reinicio    bigint not null default 0,
  atualizado  bigint not null,
  criado_em   timestamptz not null default now()
);

create table if not exists public.licoes (
  id          text primary key check (char_length(id) between 4 and 64),
  dono        uuid not null default auth.uid() references auth.users(id) on delete cascade,
  crianca_id  text not null references public.criancas(id) on delete cascade,
  dia         date not null,
  ts          bigint not null,
  hab         int  not null check (hab between 0 and 8),
  ms          int  not null check (ms >= 0),
  estrelas    int  not null check (estrelas between 1 and 3),
  itens       jsonb not null check (pg_column_size(itens) < 200000),
  recebido_em timestamptz not null default clock_timestamp()
);

create index if not exists criancas_dono_idx on public.criancas (dono);
create index if not exists licoes_dono_recebido_idx on public.licoes (dono, recebido_em);
create index if not exists licoes_crianca_idx on public.licoes (crianca_id);

alter table public.criancas enable row level security;
alter table public.licoes   enable row level security;

drop policy if exists "criancas: ler as minhas"      on public.criancas;
drop policy if exists "criancas: criar as minhas"    on public.criancas;
drop policy if exists "criancas: alterar as minhas"  on public.criancas;
drop policy if exists "criancas: apagar as minhas"   on public.criancas;
create policy "criancas: ler as minhas"     on public.criancas for select to authenticated using (dono = (select auth.uid()));
create policy "criancas: criar as minhas"   on public.criancas for insert to authenticated with check (dono = (select auth.uid()));
create policy "criancas: alterar as minhas" on public.criancas for update to authenticated using (dono = (select auth.uid())) with check (dono = (select auth.uid()));
create policy "criancas: apagar as minhas"  on public.criancas for delete to authenticated using (dono = (select auth.uid()));

-- Lições são só de inclusão (o app nunca reescreve uma lição já enviada).
drop policy if exists "licoes: ler as minhas"   on public.licoes;
drop policy if exists "licoes: criar as minhas" on public.licoes;
drop policy if exists "licoes: apagar as minhas" on public.licoes;
create policy "licoes: ler as minhas"   on public.licoes for select to authenticated using (dono = (select auth.uid()));
create policy "licoes: criar as minhas" on public.licoes for insert to authenticated with check (
  dono = (select auth.uid())
  and exists (select 1 from public.criancas c where c.id = crianca_id and c.dono = (select auth.uid()))
);
create policy "licoes: apagar as minhas" on public.licoes for delete to authenticated using (dono = (select auth.uid()));

-- O dono nunca muda de mão: impede trocar o "dono" num update.
create or replace function public.pingo_trava_dono() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.dono is distinct from old.dono then
    raise exception 'dono não pode ser alterado';
  end if;
  return new;
end $$;
drop trigger if exists criancas_trava_dono on public.criancas;
create trigger criancas_trava_dono before update on public.criancas
  for each row execute function public.pingo_trava_dono();

-- Exclusão da conta pelo próprio responsável (LGPD/ECA Digital):
-- apaga o usuário e, em cascata, todas as crianças e lições.
create or replace function public.excluir_conta() returns void
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then
    raise exception 'não autenticado';
  end if;
  delete from auth.users where id = auth.uid();
end $$;
revoke all on function public.excluir_conta() from public, anon;
grant execute on function public.excluir_conta() to authenticated;

revoke all on public.criancas, public.licoes from anon;
grant select, insert, update, delete on public.criancas to authenticated;
grant select, insert, delete on public.licoes to authenticated;
