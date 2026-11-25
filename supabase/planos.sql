-- Pingo — plano anual e oferta de fundador
-- Rode DEPOIS de cobranca.sql e usuarios.sql. Pode rodar de novo sem perder dados.

-- Preço anual e prazo da oferta de fundador (quem assina até essa data,
-- inclusive, mantém o preço enquanto a assinatura continuar ativa).
alter table public.config_cobranca add column if not exists preco_anual_centavos int not null default 29700;
alter table public.config_cobranca add column if not exists stripe_price_anual_id text;
alter table public.config_cobranca add column if not exists fundador_ate date default '2026-12-31';
do $$ begin
  alter table public.config_cobranca add constraint config_cobranca_anual_check check (preco_anual_centavos between 100 and 10000000);
exception when duplicate_object then null; end $$;
grant select (preco_anual_centavos, fundador_ate) on public.config_cobranca to authenticated;

-- Plano de cada assinatura (mês ou ano) e se ela tem preço de fundador.
alter table public.assinaturas add column if not exists intervalo text;
alter table public.assinaturas add column if not exists fundador boolean not null default false;
do $$ begin
  alter table public.assinaturas add constraint assinaturas_intervalo_check check (intervalo in ('month', 'year'));
exception when duplicate_object then null; end $$;
grant select (intervalo, fundador) on public.assinaturas to authenticated;
