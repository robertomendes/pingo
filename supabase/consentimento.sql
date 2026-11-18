-- Pingo v0.6 — registro do consentimento do responsável (LGPD art. 14 §1º).
-- Cada aceite dos Termos de uso e da Política de privacidade vira uma linha.
-- Só dá para inserir e ler os próprios registros; ninguém altera nem apaga
-- (somem junto com a conta, quando o responsável a exclui).
-- Rode depois de schema.sql. Pode rodar de novo sem problema.

create table if not exists public.consentimentos (
  id          bigint generated always as identity primary key,
  dono        uuid not null default auth.uid() references auth.users(id) on delete cascade,
  versao      text not null check (length(versao) between 1 and 40),
  origem      text not null default 'app' check (origem in ('cadastro', 'aceite', 'app')),
  user_agent  text check (length(user_agent) <= 400),
  aceito_em   timestamptz not null default now()
);
create index if not exists consentimentos_dono on public.consentimentos (dono, aceito_em desc);
alter table public.consentimentos enable row level security;

drop policy if exists "consentimentos: ler os meus"    on public.consentimentos;
drop policy if exists "consentimentos: registrar o meu" on public.consentimentos;
create policy "consentimentos: ler os meus" on public.consentimentos for select to authenticated
  using (dono = (select auth.uid()));
create policy "consentimentos: registrar o meu" on public.consentimentos for insert to authenticated
  with check (dono = (select auth.uid()));

revoke all on public.consentimentos from anon, authenticated;
grant select on public.consentimentos to authenticated;
grant insert (versao, origem, user_agent) on public.consentimentos to authenticated;
