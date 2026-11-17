-- Pingo v0.5 — gestão de usuários pelo administrador.
-- Rode depois de schema.sql e cobranca.sql. Pode rodar de novo sem problema.
--
-- cortesia:  acesso liberado sem pagar (família, professores, parceiros).
-- bloqueado: acesso cortado pelo administrador, mesmo com assinatura paga.
--            A cobrança na Stripe NÃO para sozinha: cancele lá se for o caso.

alter table public.assinaturas add column if not exists cortesia  boolean not null default false;
alter table public.assinaturas add column if not exists bloqueado boolean not null default false;
grant select (cortesia, bloqueado) on public.assinaturas to authenticated;

-- Cortesias antigas (status 'active' sem assinatura na Stripe) viram cortesia explícita.
update public.assinaturas
   set cortesia = true, status = 'nenhuma', atualizado_em = now()
 where stripe_subscription_id is null and status = 'active';

create or replace function public.tem_acesso() returns boolean
language sql stable security definer set search_path = '' as $$
  select public.sou_admin() or exists (
    select 1 from public.assinaturas a
    where a.dono = auth.uid()
      and not a.bloqueado
      and (
        a.cortesia
        or (a.status in ('active', 'trialing') and (a.periodo_fim is null or a.periodo_fim > now() - interval '3 days'))
        or (a.status = 'past_due' and a.periodo_fim > now() - interval '10 days')
      )
  );
$$;
revoke all on function public.tem_acesso() from public, anon;
grant execute on function public.tem_acesso() to authenticated;
