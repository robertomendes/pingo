-- Pingo — cobrança por assinatura (Stripe)
-- Rode DEPOIS de schema.sql. Pode rodar de novo sem perder dados.
--
-- Quem escreve nas tabelas de cobrança são só as funções do servidor
-- (Edge Functions), conectadas direto ao banco. O app apenas LÊ a própria
-- assinatura e o preço público.

-- Administradores do Pingo (inclua o seu usuário com o insert do final).
create table if not exists public.admins (
  user_id   uuid primary key references auth.users(id) on delete cascade,
  criado_em timestamptz not null default now()
);
alter table public.admins enable row level security;

-- Configuração pública da cobrança (uma linha só).
create table if not exists public.config_cobranca (
  id                       int primary key default 1 check (id = 1),
  preco_centavos           int  not null default 5900 check (preco_centavos between 100 and 1000000),
  dias_teste               int  not null default 7 check (dias_teste between 0 and 60),
  moeda                    text not null default 'brl',
  vendas_abertas           boolean not null default false,
  modo                     text check (modo in ('teste', 'producao')),
  stripe_product_id        text,
  stripe_price_id          text,
  stripe_portal_config_id  text,
  atualizado_em            timestamptz not null default now()
);
insert into public.config_cobranca (id) values (1) on conflict (id) do nothing;
alter table public.config_cobranca enable row level security;
drop policy if exists "config: leitura" on public.config_cobranca;
create policy "config: leitura" on public.config_cobranca for select to authenticated using (true);
revoke all on public.config_cobranca from anon, authenticated;
grant select (id, preco_centavos, dias_teste, moeda, vendas_abertas, modo) on public.config_cobranca to authenticated;

-- Segredos da integração (nunca expostos à API).
create table if not exists public.cobranca_segredos (
  id                   int primary key default 1 check (id = 1),
  modo                 text,
  webhook_endpoint_id  text,
  webhook_secret       text,
  atualizado_em        timestamptz not null default now()
);
alter table public.cobranca_segredos enable row level security;
revoke all on public.cobranca_segredos from anon, authenticated;

-- Assinatura de cada conta (espelho do que a Stripe informa).
create table if not exists public.assinaturas (
  dono                    uuid primary key references auth.users(id) on delete cascade,
  stripe_customer_id      text unique,
  stripe_subscription_id  text unique,
  status                  text not null default 'nenhuma',
  preco_centavos          int,
  periodo_fim             timestamptz,
  teste_fim               timestamptz,
  cancelar_no_fim         boolean not null default false,
  ja_teve_teste           boolean not null default false,
  atualizado_em           timestamptz not null default now()
);
alter table public.assinaturas enable row level security;
drop policy if exists "assinaturas: ler a minha" on public.assinaturas;
create policy "assinaturas: ler a minha" on public.assinaturas for select to authenticated using (dono = (select auth.uid()));
revoke all on public.assinaturas from anon, authenticated;
grant select (dono, status, preco_centavos, periodo_fim, teste_fim, cancelar_no_fim, ja_teve_teste) on public.assinaturas to authenticated;

-- Registro dos avisos recebidos da Stripe (auditoria).
create table if not exists public.eventos_stripe (
  id           text primary key,
  tipo         text not null,
  recebido_em  timestamptz not null default now()
);
alter table public.eventos_stripe enable row level security;
revoke all on public.eventos_stripe from anon, authenticated;

-- Quem é administrador.
create or replace function public.sou_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.admins where user_id = auth.uid());
$$;
revoke all on function public.sou_admin() from public, anon;
grant execute on function public.sou_admin() to authenticated;

-- Quem pode usar o Pingo: administradores e assinaturas em dia.
-- Tolerância: 3 dias após o fim do período (atraso do aviso da Stripe)
-- e 10 dias quando o pagamento está pendente (a Stripe ainda tenta cobrar).
create or replace function public.tem_acesso() returns boolean
language sql stable security definer set search_path = '' as $$
  select public.sou_admin() or exists (
    select 1 from public.assinaturas a
    where a.dono = auth.uid()
      and (
        (a.status in ('active', 'trialing') and (a.periodo_fim is null or a.periodo_fim > now() - interval '3 days'))
        or (a.status = 'past_due' and a.periodo_fim > now() - interval '10 days')
      )
  );
$$;
revoke all on function public.tem_acesso() from public, anon;
grant execute on function public.tem_acesso() to authenticated;

-- Gravar progresso exige acesso. Ler e apagar os próprios dados, não (LGPD).
drop policy if exists "criancas: criar as minhas"   on public.criancas;
drop policy if exists "criancas: alterar as minhas" on public.criancas;
drop policy if exists "licoes: criar as minhas"     on public.licoes;
create policy "criancas: criar as minhas"   on public.criancas for insert to authenticated
  with check (dono = (select auth.uid()) and (select public.tem_acesso()));
create policy "criancas: alterar as minhas" on public.criancas for update to authenticated
  using (dono = (select auth.uid())) with check (dono = (select auth.uid()) and (select public.tem_acesso()));
create policy "licoes: criar as minhas" on public.licoes for insert to authenticated with check (
  dono = (select auth.uid())
  and (select public.tem_acesso())
  and exists (select 1 from public.criancas c where c.id = crianca_id and c.dono = (select auth.uid()))
);

-- A exclusão de conta passa a ser feita pela função do servidor,
-- que cancela a cobrança na Stripe antes de apagar os dados.
revoke execute on function public.excluir_conta() from authenticated;

-- Para se tornar administrador, rode uma vez trocando o e-mail:
-- insert into public.admins (user_id) select id from auth.users where email = 'seu-email@exemplo.com' on conflict do nothing;
