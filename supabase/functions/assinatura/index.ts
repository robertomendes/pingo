// Pingo — função "assinatura" (chamada pelo app, com o login do responsável)
// Ações: checkout (página de pagamento da Stripe), portal (trocar cartão / cancelar),
// sincronizar (confere a assinatura direto na Stripe) e excluir_conta.
// deno-lint-ignore-file no-explicit-any
import Stripe from 'npm:stripe@23.1.0';
import postgres from 'npm:postgres@3.4.5';

type Usuario = { id: string; email: string };
type Deps = { stripe: any | null; sql: any; usuario: (req: Request) => Promise<Usuario | null>; appUrl: string; origens: string[] };

const ATIVOS = ['active', 'trialing', 'past_due'];

// CPF: só dígitos, com os dois verificadores conferidos.
export function cpfValido(txt: string): string | null {
  const d = String(txt ?? '').replace(/\D/g, '');
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return null;
  for (const n of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < n; i++) soma += Number(d[i]) * (n + 1 - i);
    if (((soma * 10) % 11) % 10 !== Number(d[n])) return null;
  }
  return d;
}
const cpfFormatado = (d: string) => `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
// Data de hoje no horário de Brasília (AAAA-MM-DD).
export const hojeBR = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Sao_Paulo' });

function cors(req: Request, origens: string[]) {
  const o = req.headers.get('origin') || '';
  return {
    'Access-Control-Allow-Origin': origens.includes(o) ? o : origens[0],
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Vary': 'Origin',
  };
}
function resposta(req: Request, deps: Deps, corpo: unknown, status = 200) {
  return new Response(JSON.stringify(corpo), { status, headers: { ...cors(req, deps.origens), 'Content-Type': 'application/json' } });
}

// Grava no banco o estado atual de uma assinatura da Stripe (fonte da verdade).
export async function aplicarAssinatura(sql: any, sub: any): Promise<boolean> {
  const cliente = typeof sub.customer === 'string' ? sub.customer : sub.customer?.id;
  const item = sub.items?.data?.[0];
  const fim = sub.current_period_end ?? item?.current_period_end ?? null;
  let dono = sub.metadata?.user_id || null;
  if (!dono && cliente) dono = (await sql`select dono from public.assinaturas where stripe_customer_id = ${cliente}`)[0]?.dono ?? null;
  if (!dono) return false;
  const existe = (await sql`select 1 from auth.users where id = ${dono}`).length > 0;
  if (!existe) return false; // conta já excluída
  await sql`
    insert into public.assinaturas (dono, stripe_customer_id, stripe_subscription_id, status, preco_centavos, intervalo, fundador, periodo_fim, teste_fim, cancelar_no_fim, ja_teve_teste, atualizado_em)
    values (${dono}, ${cliente}, ${sub.id}, ${sub.status}, ${item?.price?.unit_amount ?? null},
            ${item?.price?.recurring?.interval === 'year' ? 'year' : 'month'}, ${sub.metadata?.fundador === 'sim'},
            ${fim ? new Date(fim * 1000) : null}, ${sub.trial_end ? new Date(sub.trial_end * 1000) : null},
            ${!!(sub.cancel_at_period_end || sub.cancel_at)}, ${!!sub.trial_end}, now())
    on conflict (dono) do update set
      stripe_customer_id = excluded.stripe_customer_id,
      stripe_subscription_id = excluded.stripe_subscription_id,
      status = excluded.status,
      preco_centavos = excluded.preco_centavos,
      intervalo = excluded.intervalo,
      fundador = excluded.fundador,
      periodo_fim = excluded.periodo_fim,
      teste_fim = excluded.teste_fim,
      cancelar_no_fim = excluded.cancelar_no_fim,
      ja_teve_teste = public.assinaturas.ja_teve_teste or excluded.ja_teve_teste,
      atualizado_em = now()
    where public.assinaturas.stripe_subscription_id is null
       or public.assinaturas.stripe_subscription_id = excluded.stripe_subscription_id
       or public.assinaturas.status not in ('active', 'trialing', 'past_due')
       or excluded.status in ('active', 'trialing', 'past_due')`;
  return true;
}

export async function handler(req: Request, deps: Deps): Promise<Response> {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors(req, deps.origens) });
  if (req.method !== 'POST') return resposta(req, deps, { erro: 'Método não permitido.' }, 405);
  const u = await deps.usuario(req);
  if (!u) return resposta(req, deps, { erro: 'Sessão expirada. Entre de novo.' }, 401);
  let corpo: any = {};
  try { corpo = await req.json(); } catch { /* corpo vazio */ }
  const { sql, stripe } = deps;
  try {
    const [cfg] = await sql`select *, fundador_ate::text as fundador_ate from public.config_cobranca where id = 1`;
    const [a] = await sql`select * from public.assinaturas where dono = ${u.id}`;
    const portal = async () => (await stripe.billingPortal.sessions.create({
      customer: a.stripe_customer_id, return_url: deps.appUrl,
      ...(cfg?.stripe_portal_config_id ? { configuration: cfg.stripe_portal_config_id } : {}),
    })).url;

    if (corpo.acao === 'excluir_conta') {
      if (a?.stripe_customer_id && stripe) {
        const lista = await stripe.subscriptions.list({ customer: a.stripe_customer_id, status: 'all', limit: 20 });
        for (const s of lista.data) if (!['canceled', 'incomplete_expired'].includes(s.status)) await stripe.subscriptions.cancel(s.id);
      }
      await sql`delete from auth.users where id = ${u.id}`;
      return resposta(req, deps, { ok: true });
    }
    if (!stripe) return resposta(req, deps, { erro: 'Pagamentos indisponíveis no momento.' }, 503);

    switch (corpo.acao) {
      case 'checkout': {
        if (!cfg?.vendas_abertas || !cfg.stripe_price_id) return resposta(req, deps, { erro: 'As assinaturas ainda não estão abertas.' }, 409);
        if (a && ATIVOS.includes(a.status) && a.stripe_customer_id) return resposta(req, deps, { url: await portal(), jaAssinante: true });
        const anual = corpo.plano === 'anual';
        const precoId = anual ? cfg.stripe_price_anual_id : cfg.stripe_price_id;
        if (!precoId) return resposta(req, deps, { erro: 'O plano anual ainda não está disponível.' }, 409);
        const cpf = cpfValido(corpo.cpf);
        if (!cpf) return resposta(req, deps, { erro: 'Confira o CPF: ele é necessário para o recibo.', campo: 'cpf' }, 400);
        let cliente = a?.stripe_customer_id;
        if (!cliente) {
          cliente = (await stripe.customers.create({ email: u.email, metadata: { user_id: u.id } })).id;
          await sql`insert into public.assinaturas (dono, stripe_customer_id) values (${u.id}, ${cliente})
                    on conflict (dono) do update set stripe_customer_id = excluded.stripe_customer_id, atualizado_em = now()`;
        }
        // CPF do pagador no cadastro da Stripe (sai nos recibos e serve para o imposto).
        const ids = await stripe.customers.listTaxIds(cliente, { limit: 10 });
        if (!ids.data.some((t: any) => t.type === 'br_cpf' && String(t.value).replace(/\D/g, '') === cpf)) {
          for (const t of ids.data) if (t.type === 'br_cpf') await stripe.customers.deleteTaxId(cliente, t.id);
          await stripe.customers.createTaxId(cliente, { type: 'br_cpf', value: cpfFormatado(cpf) });
        }
        const fundador = !!cfg.fundador_ate && hojeBR() <= String(cfg.fundador_ate);
        const teste = cfg.dias_teste > 0 && !a?.ja_teve_teste;
        const sessao = await stripe.checkout.sessions.create({
          mode: 'subscription',
          customer: cliente,
          client_reference_id: u.id,
          line_items: [{ price: precoId, quantity: 1 }],
          subscription_data: { metadata: { user_id: u.id, plano: anual ? 'anual' : 'mensal', fundador: fundador ? 'sim' : 'nao' }, ...(teste ? { trial_period_days: cfg.dias_teste } : {}) },
          allowed_payment_method_types: ['card'], // só cartão (o parâmetro antigo, payment_method_types, saiu da API em 2026-09-30)
          payment_method_collection: 'always',
          locale: 'pt-BR',
          allow_promotion_codes: true,
          success_url: deps.appUrl + '?assinatura=ok',
          cancel_url: deps.appUrl + '?assinatura=cancelada',
        });
        return resposta(req, deps, { url: sessao.url });
      }
      case 'portal': {
        if (!a?.stripe_customer_id) return resposta(req, deps, { erro: 'Ainda não há assinatura nesta conta.' }, 404);
        return resposta(req, deps, { url: await portal() });
      }
      case 'sincronizar': {
        if (!a?.stripe_customer_id) return resposta(req, deps, { status: 'nenhuma' });
        const lista = await stripe.subscriptions.list({ customer: a.stripe_customer_id, status: 'all', limit: 10 });
        const subs = [...lista.data].sort((x: any, y: any) => (ATIVOS.includes(y.status) ? 1 : 0) - (ATIVOS.includes(x.status) ? 1 : 0) || y.created - x.created);
        if (subs[0]) { subs[0].metadata = { ...(subs[0].metadata || {}), user_id: subs[0].metadata?.user_id || u.id }; await aplicarAssinatura(sql, subs[0]); }
        const [novo] = await sql`select status from public.assinaturas where dono = ${u.id}`;
        return resposta(req, deps, { status: novo?.status ?? 'nenhuma' });
      }
      default:
        return resposta(req, deps, { erro: 'Ação desconhecida.' }, 400);
    }
  } catch (e) {
    console.error('assinatura', e);
    return resposta(req, deps, { erro: 'Não foi possível concluir agora. Tente de novo em instantes.' }, 500);
  }
}

async function usuarioDoToken(req: Request): Promise<Usuario | null> {
  const auth = req.headers.get('authorization') || '';
  if (!auth.startsWith('Bearer ')) return null;
  const apikey = req.headers.get('apikey') || Deno.env.get('SUPABASE_ANON_KEY') || '';
  const r = await fetch(Deno.env.get('SUPABASE_URL') + '/auth/v1/user', { headers: { Authorization: auth, apikey } });
  if (!r.ok) return null;
  const u = await r.json();
  return u?.id ? { id: u.id, email: u.email } : null;
}

if (!(globalThis as any).__PINGO_TESTE) {
  const chave = Deno.env.get('STRIPE_SECRET_KEY');
  const stripe = chave ? new Stripe(chave, { httpClient: Stripe.createFetchHttpClient() }) : null;
  const sql = postgres(Deno.env.get('SUPABASE_DB_URL')!, { prepare: false, max: 2 });
  const appUrl = Deno.env.get('APP_URL') ?? 'https://robertomendes.github.io/pingo/';
  const origens = [new URL(appUrl).origin, ...(Deno.env.get('ORIGENS_EXTRAS') ?? '').split(',').filter(Boolean)];
  Deno.serve((req) => handler(req, { stripe, sql, usuario: usuarioDoToken, appUrl, origens }));
}
