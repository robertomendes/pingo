-- Pingo v0.7 — trilha ampliada (adição, subtração, contas maiores e tabuada).
-- A trilha passou de 9 para 39 etapas, com até 5 lições cada.
-- Afrouxa os limites de "hab" (etapa) e "nivel" (lição dentro da etapa).
-- Rode depois de schema.sql. Pode rodar de novo sem problema.

alter table public.criancas drop constraint if exists criancas_hab_check;
alter table public.criancas drop constraint if exists criancas_nivel_check;
alter table public.licoes   drop constraint if exists licoes_hab_check;

alter table public.criancas add constraint criancas_hab_check   check (hab between 0 and 99);
alter table public.criancas add constraint criancas_nivel_check check (nivel between 0 and 9);
alter table public.licoes   add constraint licoes_hab_check     check (hab between 0 and 99);
