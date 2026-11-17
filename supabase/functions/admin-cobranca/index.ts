// Pingo — função "admin-cobranca" (só para administradores)
// Ações: resumo (configuração e números), conectar (cria produto, preço,
// webhook e portal na Stripe), salvar (preço, dias de teste, vendas abertas),
// usuarios (lista de contas e situação de acesso) e acesso (ativa/desativa uma conta).
// deno-lint-ignore-file no-explicit-any
import Stripe from 'npm:stripe@23.1.0';
import postgres from 'npm:postgres@3.4.5';

type Usuario = { id: string; email: string };
type Deps = { stripe: any | null; chave: string; sql: any; usuario: (req: Request) => Promise<Usuario | null>; webhookUrl: string; appUrl: string; origens: string[] };

const EVENTOS = [
  'checkout.session.completed',
  'customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted',
  'customer.subscription.paused', 'customer.subscription.resumed',
  'invoice.paid', 'invoice.payment_failed',
];
const ATIVOS = ['active', 'trialing', 'past_due'];

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
function modoDaChave(chave: string): 'teste' | 'producao' | null {
  if (/^(sk|rk)_test_/.test(chave)) return 'teste';
  if (/^(sk|rk)_live_/.test(chave)) return 'producao';
  return null;
}

// Mesma regra de public.tem_acesso(), calculada para qualquer conta.
function pagoEmDia(a: any): boolean {
  if (!a) return false;
  const fim = a.periodo_fim ? new Date(a.periodo_fim).getTime() : null, dia = 86400000;
  if ((a.status === 'active' || a.status === 'trialing') && (fim === null || fim > Date.now() - 3 * dia)) return true;
  return a.status === 'past_due' && fim !== null && fim > Date.now() - 10 * dia;
}
function situacao(l: any): { ativo: boolean; motivo: string } {
  if (l.admin) return { ativo: true, motivo: 'admin' };
  if (l.bloqueado) return { ativo: false, motivo: 'bloqueado' };
  if (l.cortesia) return { ativo: true, motivo: 'cortesia' };
  if (pagoEmDia(l)) return { ativo: true, motivo: l.status === 'trialing' ? 'teste' : l.status === 'past_due' ? 'pendente' : 'assinante' };
  return { ativo: false, motivo: l.status === 'canceled' ? 'cancelado' : 'sem_assinatura' };
}
async function usuarios(deps: Deps) {
  const linhas = await deps.sql`
    select u.id, u.email, u.created_at, u.last_sign_in_at, (u.email_confirmed_at is not null) as confirmado,
           (ad.user_id is not null) as admin, coalesce(a.status, 'nenhuma') as status, a.periodo_fim, a.preco_centavos,
           coalesce(a.cortesia, false) as cortesia, coalesce(a.bloqueado, false) as bloqueado,
           (a.stripe_subscription_id is not null) as pago,
           (select count(*) from public.criancas c where c.dono = u.id)::int as criancas
      from auth.users u
      left join public.assinaturas a on a.dono = u.id
      left join public.admins ad on ad.user_id = u.id
     order by u.created_at desc
     limit 1000`;
  return linhas.map((l: any) => ({
    id: l.id, email: l.email, criado_em: l.created_at, ultimo_login: l.last_sign_in_at, confirmado: l.confirmado,
    criancas: l.criancas, status: l.status, pago: !!l.pago && pagoEmDia(l), preco_centavos: l.preco_centavos, periodo_fim: l.periodo_fim,
    ...situacao(l),
  }));
}

async function resumo(deps: Deps) {
  const [cfg] = await deps.sql`select preco_centavos, dias_teste, moeda, vendas_abertas, modo, stripe_price_id, atualizado_em from public.config_cobranca where id = 1`;
  const [seg] = await deps.sql`select webhook_endpoint_id from public.cobranca_segredos where id = 1`;
  const linhas = await deps.sql`select status, count(*)::int as n, coalesce(sum(preco_centavos), 0)::int as soma from public.assinaturas group by status`;
  const n = (s: string) => linhas.find((l: any) => l.status === s)?.n ?? 0;
  const mrr = linhas.filter((l: any) => l.status === 'active' || l.status === 'past_due').reduce((t: number, l: any) => t + l.soma, 0);
  return {
    config: { preco_centavos: cfg.preco_centavos, dias_teste: cfg.dias_teste, vendas_abertas: cfg.vendas_abertas, modo: cfg.modo, atualizado_em: cfg.atualizado_em },
    stripe: { chave: !!deps.stripe, modoChave: modoDaChave(deps.chave), conectada: !!(cfg.stripe_price_id && seg?.webhook_endpoint_id && cfg.modo === modoDaChave(deps.chave)) },
    numeros: { ativos: n('active'), em_teste: n('trialing'), pendentes: n('past_due') + n('unpaid'), cancelados: n('canceled'), mrr_centavos: mrr,
      cortesias: (await deps.sql`select count(*)::int as n from public.assinaturas where cortesia and not bloqueado`)[0].n },
  };
}

async function criarPreco(deps: Deps, produto: string, centavos: number) {
  return (await deps.stripe.prices.create({ product: produto, currency: 'brl', unit_amount: centavos, recurring: { interval: 'month' }, metadata: { app: 'pingo' } })).id;
}

export async function handler(req: Request, deps: Deps): Promise<Response> {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors(req, deps.origens) });
  if (req.method !== 'POST') return resposta(req, deps, { erro: 'Método não permitido.' }, 405);
  const u = await deps.usuario(req);
  if (!u) return resposta(req, deps, { erro: 'Sessão expirada. Entre de novo.' }, 401);
  const [adm] = await deps.sql`select 1 as ok from public.admins where user_id = ${u.id}`;
  if (!adm) return resposta(req, deps, { erro: 'Acesso só para administradores.' }, 403);
  let corpo: any = {};
  try { corpo = await req.json(); } catch { /* vazio */ }
  const { sql, stripe } = deps;
  try {
    if (corpo.acao === 'resumo') return resposta(req, deps, await resumo(deps));

    if (corpo.acao === 'usuarios') return resposta(req, deps, { usuarios: await usuarios(deps) });

    if (corpo.acao === 'acesso') {
      const alvo = String(corpo.user_id ?? '');
      if (!/^[0-9a-f-]{36}$/i.test(alvo) || typeof corpo.ativo !== 'boolean') return resposta(req, deps, { erro: 'Pedido inválido.' }, 400);
      const [l] = await sql`
        select u.id, (ad.user_id is not null) as admin, a.status, a.periodo_fim, a.stripe_subscription_id
          from auth.users u left join public.assinaturas a on a.dono = u.id left join public.admins ad on ad.user_id = u.id
         where u.id = ${alvo}`;
      if (!l) return resposta(req, deps, { erro: 'Usuário não encontrado.' }, 404);
      if (l.admin) return resposta(req, deps, { erro: 'Administradores sempre têm acesso.' }, 400);
      const pago = !!l.stripe_subscription_id && pagoEmDia(l);
      if (corpo.ativo) {
        // Quem paga em dia só é desbloqueado; quem não paga ganha cortesia.
        await sql`insert into public.assinaturas (dono, cortesia, bloqueado, atualizado_em) values (${alvo}, ${!pago}, false, now())
                  on conflict (dono) do update set bloqueado = false, cortesia = public.assinaturas.cortesia or excluded.cortesia, atualizado_em = now()`;
      } else {
        // Tira a cortesia; se ainda houver assinatura paga em dia, bloqueia.
        await sql`update public.assinaturas set cortesia = false, bloqueado = ${pago}, atualizado_em = now() where dono = ${alvo}`;
      }
      return resposta(req, deps, { usuarios: await usuarios(deps), aviso: !corpo.ativo && pago ? 'Acesso bloqueado, mas a assinatura continua sendo cobrada na Stripe. Para parar a cobrança, cancele lá.' : null });
    }

    if (corpo.acao === 'conectar') {
      const modo = modoDaChave(deps.chave);
      if (!stripe || !modo) return resposta(req, deps, { erro: 'Falta a chave secreta da Stripe (STRIPE_SECRET_KEY) nos segredos das Edge Functions do Supabase.' }, 400);
      const [cfg] = await sql`select * from public.config_cobranca where id = 1`;
      const mesmoModo = cfg.modo === modo;
      let produto: string | null = null;
      if (mesmoModo && cfg.stripe_product_id) { try { produto = (await stripe.products.retrieve(cfg.stripe_product_id)).id; } catch { produto = null; } }
      const produtoId: string = produto ?? (await stripe.products.create({ name: 'Pingo — assinatura mensal', metadata: { app: 'pingo' } })).id;
      let preco: string | null = null;
      if (mesmoModo && cfg.stripe_price_id) {
        try { const p = await stripe.prices.retrieve(cfg.stripe_price_id); if (p.active && p.unit_amount === cfg.preco_centavos && p.product === produtoId) preco = p.id; } catch { preco = null; }
      }
      if (!preco) preco = await criarPreco(deps, produtoId, cfg.preco_centavos);
      // webhook: remove o antigo deste endereço e cria um novo (o segredo só vem na criação)
      const existentes = await stripe.webhookEndpoints.list({ limit: 100 });
      for (const w of existentes.data) if (w.url === deps.webhookUrl) await stripe.webhookEndpoints.del(w.id);
      const wh = await stripe.webhookEndpoints.create({ url: deps.webhookUrl, enabled_events: EVENTOS, description: 'Pingo — assinaturas' });
      const portal = await stripe.billingPortal.configurations.create({
        business_profile: { headline: 'Pingo — sua assinatura' },
        default_return_url: deps.appUrl,
        features: {
          customer_update: { enabled: true, allowed_updates: ['email', 'name'] },
          invoice_history: { enabled: true },
          payment_method_update: { enabled: true },
          subscription_cancel: { enabled: true, mode: 'at_period_end', cancellation_reason: { enabled: true, options: ['too_expensive', 'unused', 'other'] } },
        },
      });
      await sql`update public.config_cobranca set stripe_product_id = ${produtoId}, stripe_price_id = ${preco}, stripe_portal_config_id = ${portal.id}, modo = ${modo}, atualizado_em = now() where id = 1`;
      await sql`insert into public.cobranca_segredos (id, modo, webhook_endpoint_id, webhook_secret, atualizado_em) values (1, ${modo}, ${wh.id}, ${wh.secret}, now())
                on conflict (id) do update set modo = excluded.modo, webhook_endpoint_id = excluded.webhook_endpoint_id, webhook_secret = excluded.webhook_secret, atualizado_em = now()`;
      return resposta(req, deps, await resumo(deps));
    }

    if (corpo.acao === 'salvar') {
      const centavos = Math.round(Number(corpo.preco_centavos));
      const dias = Math.round(Number(corpo.dias_teste));
      if (!Number.isFinite(centavos) || centavos < 100 || centavos > 1000000) return resposta(req, deps, { erro: 'Preço inválido: use um valor entre R$ 1,00 e R$ 10.000,00.' }, 400);
      if (!Number.isFinite(dias) || dias < 0 || dias > 60) return resposta(req, deps, { erro: 'Dias de teste: de 0 a 60.' }, 400);
      const [cfg] = await sql`select * from public.config_cobranca where id = 1`;
      const conectada = !!(stripe && cfg.stripe_price_id && cfg.modo === modoDaChave(deps.chave));
      if (corpo.vendas_abertas && !conectada) return resposta(req, deps, { erro: 'Conecte a Stripe antes de abrir as vendas.' }, 400);
      let precoId = cfg.stripe_price_id, migrados = 0, falhas = 0;
      if (conectada && centavos !== cfg.preco_centavos) {
        precoId = await criarPreco(deps, cfg.stripe_product_id, centavos);
        try { await stripe.prices.update(cfg.stripe_price_id, { active: false }); } catch { /* preço antigo já arquivado */ }
      }
      await sql`update public.config_cobranca set preco_centavos = ${centavos}, dias_teste = ${dias}, vendas_abertas = ${!!corpo.vendas_abertas}, stripe_price_id = ${precoId}, atualizado_em = now() where id = 1`;
      if (conectada && corpo.aplicar_atuais && precoId) {
        const subs = await sql`select stripe_subscription_id from public.assinaturas where status = any(${ATIVOS}) and stripe_subscription_id is not null`;
        for (const s of subs) {
          try {
            const sub = await stripe.subscriptions.retrieve(s.stripe_subscription_id);
            const item = sub.items.data[0];
            if (item && item.price.id !== precoId) {
              await stripe.subscriptions.update(sub.id, { items: [{ id: item.id, price: precoId }], proration_behavior: 'none' });
              migrados++;
            }
          } catch (e) { console.error('migrar preço', s.stripe_subscription_id, e); falhas++; }
        }
      }
      return resposta(req, deps, { ...(await resumo(deps)), migrados, falhas });
    }
    return resposta(req, deps, { erro: 'Ação desconhecida.' }, 400);
  } catch (e) {
    console.error('admin-cobranca', e);
    return resposta(req, deps, { erro: 'A Stripe recusou a operação: ' + String((e as any)?.message ?? e).slice(0, 160) }, 500);
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
  const chave = Deno.env.get('STRIPE_SECRET_KEY') ?? '';
  const stripe = chave ? new Stripe(chave, { httpClient: Stripe.createFetchHttpClient() }) : null;
  const sql = postgres(Deno.env.get('SUPABASE_DB_URL')!, { prepare: false, max: 2 });
  const appUrl = Deno.env.get('APP_URL') ?? 'https://robertomendes.github.io/pingo/';
  const origens = [new URL(appUrl).origin, ...(Deno.env.get('ORIGENS_EXTRAS') ?? '').split(',').filter(Boolean)];
  const webhookUrl = Deno.env.get('SUPABASE_URL') + '/functions/v1/stripe-webhook';
  Deno.serve((req) => handler(req, { stripe, chave, sql, usuario: usuarioDoToken, webhookUrl, appUrl, origens }));
}
