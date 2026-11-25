// Testes das funções de cobrança: Postgres local + Stripe simulada.
// deno test -A supabase/functions/testes/cobranca_test.ts  (com PG_URL apontando para um banco com schema.sql + cobranca.sql)
// deno-lint-ignore-file no-explicit-any
(globalThis as any).__PINGO_TESTE = true;
import Stripe from 'npm:stripe@23.1.0';
import postgres from 'npm:postgres@3.4.5';
import { ok as assert, deepStrictEqual } from 'node:assert';
const assertEquals = (a: any, b: any, m?: string) => deepStrictEqual(a, b, m);

const { handler: assinatura } = await import('../assinatura/index.ts');
const { handler: webhook } = await import('../stripe-webhook/index.ts');
const { handler: admin } = await import('../admin-cobranca/index.ts');

const sql = postgres({ host: '/tmp', port: 5499, database: Deno.env.get('PG_DB') ?? 't3', username: 'postgres', max: 2, onnotice: () => {} });
const real = new Stripe('sk_test_simulada', { httpClient: Stripe.createFetchHttpClient() });

// ---------- Stripe simulada (só o que as funções usam) ----------
let seq = 0; const id = (p: string) => `${p}_${++seq}`;
const agora = () => Math.floor(Date.now() / 1000);
const S: any = { customers: {}, prices: {}, products: {}, subs: {}, webhooks: {}, sessoes: [] as any[] };
const stripe: any = {
  customers: {
    create: async (o: any) => (S.customers[id('cus')] = { ...o, taxIds: [] }, { id: `cus_${seq}` }),
    listTaxIds: async (c: string) => ({ data: [...S.customers[c].taxIds] }),
    createTaxId: async (c: string, o: any) => { if (!/^\d{3}\.\d{3}\.\d{3}-\d{2}$/.test(o.value)) throw new Error('formato'); const t = { id: id('txi'), ...o }; S.customers[c].taxIds.push(t); return t; },
    deleteTaxId: async (c: string, i: string) => { S.customers[c].taxIds = S.customers[c].taxIds.filter((t: any) => t.id !== i); },
  },
  products: { create: async (o: any) => { const i = id('prod'); S.products[i] = o; return { id: i }; }, retrieve: async (i: string) => { if (!S.products[i]) throw new Error('no such product'); return { id: i }; } },
  prices: {
    create: async (o: any) => { const i = id('price'); S.prices[i] = { id: i, active: true, ...o }; return S.prices[i]; },
    retrieve: async (i: string) => S.prices[i], update: async (i: string, o: any) => Object.assign(S.prices[i], o),
  },
  webhookEndpoints: {
    list: async () => ({ data: Object.values(S.webhooks) }), del: async (i: string) => { delete S.webhooks[i]; },
    create: async (o: any) => { const i = id('we'); S.webhooks[i] = { id: i, url: o.url, secret: 'whsec_' + i }; return S.webhooks[i]; },
  },
  billingPortal: {
    configurations: { create: async () => ({ id: id('bpc') }) },
    sessions: { create: async (o: any) => ({ url: 'https://billing.stripe.test/' + o.customer }) },
  },
  checkout: { sessions: { create: async (o: any) => { S.sessoes.push(o); return { url: 'https://checkout.stripe.test/' + id('cs') }; } } },
  subscriptions: {
    list: async (o: any) => ({ data: Object.values(S.subs).filter((s: any) => s.customer === o.customer) }),
    retrieve: async (i: string) => structuredClone(S.subs[i]),
    update: async (i: string, o: any) => { const s = S.subs[i]; for (const it of o.items) s.items.data[0].price = S.prices[it.price]; return s; },
    cancel: async (i: string) => { S.subs[i].status = 'canceled'; return S.subs[i]; },
  },
  webhooks: real.webhooks,
};
function criarAssinaturaNaStripe(cliente: string, preco: string, userId: string, status = 'active', diasTeste = 0) {
  const i = id('sub'); const fim = agora() + 30 * 86400;
  S.subs[i] = { id: i, customer: cliente, status, created: agora() + seq, metadata: { user_id: userId }, cancel_at_period_end: false, cancel_at: null,
    trial_end: diasTeste ? agora() + diasTeste * 86400 : null, items: { data: [{ id: id('si'), current_period_end: fim, price: S.prices[preco] }] } };
  return S.subs[i];
}
async function avisar(tipo: string, objeto: any, segredo?: string, eventoId?: string) {
  const corpo = JSON.stringify({ id: eventoId ?? id('evt'), type: tipo, data: { object: objeto } });
  const [seg] = await sql`select webhook_secret from public.cobranca_segredos where id = 1`;
  const header = await real.webhooks.generateTestHeaderStringAsync({ payload: corpo, secret: segredo ?? seg.webhook_secret });
  return webhook(new Request('http://x/stripe-webhook', { method: 'POST', body: corpo, headers: { 'stripe-signature': header } }), { stripe, sql });
}

// ---------- usuários ----------
const A = { id: 'aaaaaaaa-0000-0000-0000-000000000001', email: 'pai@x.com' };
const B = { id: 'bbbbbbbb-0000-0000-0000-000000000002', email: 'mae@x.com' };
const ADM = { id: 'cccccccc-0000-0000-0000-000000000003', email: 'roberto@x.com' };
const C = { id: 'cccccccc-0000-0000-0000-000000000004', email: 'fundadora@x.com' };
const CPF = '529.982.247-25', CPF2 = '11144477735';
await sql`insert into auth.users (id, email) values (${A.id}, ${A.email}), (${B.id}, ${B.email}), (${ADM.id}, ${ADM.email}) on conflict do nothing`;
await sql`insert into public.admins (user_id) values (${ADM.id}) on conflict do nothing`;
const usuario = async (req: Request) => { const h = req.headers.get('authorization') ?? ''; const u = [A, B, ADM, C].find((x) => h === 'Bearer ' + x.id); return u ?? null; };
const base = { sql, usuario, appUrl: 'https://robertomendes.github.io/pingo/', origens: ['https://robertomendes.github.io'] };
const chamar = async (fn: any, deps: any, quem: any, corpo: any) => {
  const r = await fn(new Request('http://x', { method: 'POST', body: JSON.stringify(corpo), headers: quem ? { authorization: 'Bearer ' + quem.id, origin: 'https://robertomendes.github.io' } : {} }), deps);
  return { status: r.status, corpo: await r.json(), cors: r.headers.get('access-control-allow-origin') };
};
const depsAdmin = { ...base, stripe, chave: 'sk_test_simulada', webhookUrl: 'https://p.supabase.co/functions/v1/stripe-webhook' };
const depsAss = { ...base, stripe };
const acesso = (u: any) => sql.begin(async (tx: any) => { await tx`set local role authenticated`; await tx`select set_config('request.jwt.claim.sub', ${u.id}, true)`; return (await tx`select public.tem_acesso() as ok`)[0].ok; });
const statusDe = async (u: any) => (await sql`select * from public.assinaturas where dono = ${u.id}`)[0];

Deno.test('fluxo completo de cobrança', async (t) => {
  await t.step('sem login → 401; não-admin no painel → 403', async () => {
    assertEquals((await chamar(assinatura, depsAss, null, { acao: 'checkout' })).status, 401);
    assertEquals((await chamar(admin, depsAdmin, A, { acao: 'resumo' })).status, 403);
  });
  await t.step('vendas fechadas: checkout recusado', async () => {
    const r = await chamar(assinatura, depsAss, A, { acao: 'checkout' });
    assertEquals(r.status, 409);
  });
  await t.step('admin conecta a Stripe: produto, preço, webhook e portal', async () => {
    const r = await chamar(admin, depsAdmin, ADM, { acao: 'conectar' });
    assertEquals(r.status, 200, JSON.stringify(r.corpo));
    assert(r.corpo.stripe.conectada); assertEquals(r.corpo.stripe.modoChave, 'teste'); assert(r.corpo.stripe.anual);
    const [cfg] = await sql`select * from public.config_cobranca`;
    assertEquals(S.prices[cfg.stripe_price_anual_id].recurring.interval, 'year');
    assertEquals(S.prices[cfg.stripe_price_anual_id].unit_amount, 29700);
    assertEquals(S.prices[cfg.stripe_price_id].recurring.interval, 'month');
    assertEquals(Object.keys(S.webhooks).length, 1);
    const r2 = await chamar(admin, depsAdmin, ADM, { acao: 'conectar' }); // reconectar não duplica webhook
    assertEquals(r2.status, 200); assertEquals(Object.keys(S.webhooks).length, 1);
  });
  await t.step('admin define R$ 49,90, 7 dias de teste e abre as vendas', async () => {
    const r = await chamar(admin, depsAdmin, ADM, { acao: 'salvar', preco_centavos: 4990, dias_teste: 7, vendas_abertas: true, fundador_ate: '' });
    assertEquals(r.status, 200, JSON.stringify(r.corpo));
    const [cfg] = await sql`select * from public.config_cobranca`;
    assertEquals(cfg.preco_centavos, 4990); assertEquals(S.prices[cfg.stripe_price_id].unit_amount, 4990);
    assertEquals(Object.values(S.prices).filter((p: any) => p.active).length, 2); // mensal antigo arquivado; anual mantido
    assertEquals(cfg.fundador_ate, null);
    assertEquals((await chamar(admin, depsAdmin, ADM, { acao: 'salvar', preco_centavos: 4990, dias_teste: 7, vendas_abertas: true, fundador_ate: '31/12' })).status, 400);
    assertEquals((await chamar(admin, depsAdmin, ADM, { acao: 'salvar', preco_centavos: 50, dias_teste: 7, vendas_abertas: true })).status, 400);
  });
  let cliente = '';
  await t.step('checkout exige CPF válido', async () => {
    let r = await chamar(assinatura, depsAss, A, { acao: 'checkout' });
    assertEquals([r.status, r.corpo.campo], [400, 'cpf']);
    r = await chamar(assinatura, depsAss, A, { acao: 'checkout', cpf: '529.982.247-24' });
    assertEquals(r.status, 400);
    r = await chamar(assinatura, depsAss, A, { acao: 'checkout', cpf: '111.111.111-11' });
    assertEquals(r.status, 400);
  });
  await t.step('A vai para a página de pagamento com teste grátis', async () => {
    const r = await chamar(assinatura, depsAss, A, { acao: 'checkout', cpf: CPF });
    assertEquals(r.status, 200); assert(r.corpo.url.startsWith('https://checkout.stripe.test/'));
    assertEquals(r.cors, 'https://robertomendes.github.io');
    const s = S.sessoes.at(-1);
    assertEquals(s.mode, 'subscription'); assertEquals(s.subscription_data.trial_period_days, 7); assertEquals(s.locale, 'pt-BR');
    assertEquals(s.success_url, 'https://robertomendes.github.io/pingo/?assinatura=ok');
    cliente = (await statusDe(A)).stripe_customer_id; assert(cliente);
    assertEquals(S.customers[cliente].taxIds.map((t: any) => [t.type, t.value]), [['br_cpf', CPF]]);
    assertEquals(s.subscription_data.metadata.fundador, 'nao'); assertEquals(s.subscription_data.metadata.plano, 'mensal');
    // tentar de novo com outro CPF troca o cadastrado (sem duplicar)
    await chamar(assinatura, depsAss, A, { acao: 'checkout', cpf: CPF2 });
    assertEquals(S.customers[cliente].taxIds.map((t: any) => t.value), ['111.444.777-35']);
  });
  let sub: any;
  await t.step('Stripe avisa: assinatura em teste → acesso liberado', async () => {
    const [cfg] = await sql`select stripe_price_id from public.config_cobranca`;
    sub = criarAssinaturaNaStripe(cliente, cfg.stripe_price_id, A.id, 'trialing', 7);
    const r = await avisar('customer.subscription.created', sub);
    assertEquals(r.status, 200);
    const a = await statusDe(A);
    assertEquals(a.status, 'trialing'); assertEquals(a.preco_centavos, 4990); assertEquals([a.intervalo, a.fundador], ['month', false]); assert(a.ja_teve_teste); assert(a.periodo_fim > new Date());
    await sql.begin(async (tx: any) => { await tx`set local role authenticated`; await tx`select set_config('request.jwt.claim.sub', ${A.id}, true)`; const [x] = await tx`select public.tem_acesso() as ok`; assert(x.ok); });
  });
  await t.step('aviso com assinatura digital falsa é rejeitado', async () => {
    assertEquals((await avisar('customer.subscription.updated', sub, 'whsec_falso')).status, 400);
  });
  await t.step('aviso repetido não quebra nada', async () => {
    assertEquals((await avisar('customer.subscription.created', sub, undefined, 'evt_repetido')).status, 200);
    assertEquals((await avisar('customer.subscription.created', sub, undefined, 'evt_repetido')).status, 200);
  });
  await t.step('quem já assina vai para o portal, não paga duas vezes', async () => {
    const r = await chamar(assinatura, depsAss, A, { acao: 'checkout' }); // nem pede CPF
    assert(r.corpo.jaAssinante); assert(r.corpo.url.startsWith('https://billing.stripe.test/'));
  });
  await t.step('aviso atrasado de uma assinatura antiga cancelada não derruba a atual', async () => {
    const [cfg] = await sql`select stripe_price_id from public.config_cobranca`;
    const velha = criarAssinaturaNaStripe(cliente, cfg.stripe_price_id, A.id, 'canceled');
    assertEquals((await avisar('customer.subscription.deleted', velha)).status, 200);
    assertEquals((await statusDe(A)).status, 'trialing');
    delete S.subs[velha.id];
  });
  await t.step('pagamento recusado → pendente (acesso mantido na tolerância)', async () => {
    S.subs[sub.id].status = 'past_due';
    assertEquals((await avisar('invoice.payment_failed', { id: 'in_1', subscription: sub.id })).status, 200);
    assertEquals((await statusDe(A)).status, 'past_due');
    S.subs[sub.id].status = 'active';
    assertEquals((await avisar('invoice.paid', { id: 'in_2', parent: { subscription_details: { subscription: sub.id } } })).status, 200);
    assertEquals((await statusDe(A)).status, 'active');
  });
  await t.step('cancelamento no portal: continua até o fim do período', async () => {
    S.subs[sub.id].cancel_at_period_end = true;
    await avisar('customer.subscription.updated', S.subs[sub.id]);
    const a = await statusDe(A); assertEquals(a.status, 'active'); assert(a.cancelar_no_fim);
    S.subs[sub.id].cancel_at_period_end = false;
    await avisar('customer.subscription.updated', S.subs[sub.id]);
  });
  await t.step('novo preço aplicado também aos atuais', async () => {
    const r = await chamar(admin, depsAdmin, ADM, { acao: 'salvar', preco_centavos: 5990, dias_teste: 7, vendas_abertas: true, aplicar_atuais: true });
    assertEquals(r.corpo.migrados, 1);
    assertEquals(S.subs[sub.id].items.data[0].price.unit_amount, 5990);
    await avisar('customer.subscription.updated', S.subs[sub.id]);
    assertEquals((await statusDe(A)).preco_centavos, 5990);
    assertEquals(r.corpo.numeros.ativos, 1);
  });
  await t.step('B não ganha teste duas vezes (já teve) e sincronizar acha a assinatura sem webhook', async () => {
    await chamar(assinatura, depsAss, B, { acao: 'checkout', cpf: CPF });
    assertEquals(S.sessoes.at(-1).subscription_data.trial_period_days, 7);
    const cb = (await statusDe(B)).stripe_customer_id;
    const [cfg] = await sql`select stripe_price_id from public.config_cobranca`;
    const sb = criarAssinaturaNaStripe(cb, cfg.stripe_price_id, B.id, 'trialing', 7);
    const r = await chamar(assinatura, depsAss, B, { acao: 'sincronizar' });
    assertEquals(r.corpo.status, 'trialing');
    S.subs[sb.id].status = 'canceled'; await chamar(assinatura, depsAss, B, { acao: 'sincronizar' });
    await chamar(assinatura, depsAss, B, { acao: 'checkout', cpf: CPF });
    assertEquals(S.sessoes.at(-1).subscription_data.trial_period_days, undefined);
  });
  await t.step('resumo do admin', async () => {
    const r = await chamar(admin, depsAdmin, ADM, { acao: 'resumo' });
    assertEquals(r.corpo.numeros.ativos, 1); assertEquals(r.corpo.numeros.cancelados, 1); assertEquals(r.corpo.numeros.mrr_centavos, 5990);
  });
  await t.step('usuários: lista, cortesia, bloqueio de pagante e proteção do admin', async () => {
    let r = await chamar(admin, depsAdmin, A, { acao: 'usuarios' });
    assertEquals(r.status, 403);
    r = await chamar(admin, depsAdmin, ADM, { acao: 'usuarios' });
    const de = (u: any) => r.corpo.usuarios.find((x: any) => x.id === u.id);
    assertEquals(r.corpo.usuarios.length, 3);
    assertEquals([de(ADM).ativo, de(ADM).motivo], [true, 'admin']);
    assertEquals([de(A).ativo, de(A).motivo, de(A).pago], [true, 'assinante', true]);
    assertEquals([de(B).ativo, de(B).motivo], [false, 'cancelado']);
    // cortesia para B
    r = await chamar(admin, depsAdmin, ADM, { acao: 'acesso', user_id: B.id, ativo: true });
    assertEquals([de(B).ativo, de(B).motivo], [true, 'cortesia']);
    assertEquals(await acesso(B), true);
    assertEquals((await chamar(admin, depsAdmin, ADM, { acao: 'resumo' })).corpo.numeros.cortesias, 1);
    // tira a cortesia
    r = await chamar(admin, depsAdmin, ADM, { acao: 'acesso', user_id: B.id, ativo: false });
    assertEquals([de(B).ativo, r.corpo.aviso], [false, null]);
    assertEquals(await acesso(B), false);
    // bloqueia A, que paga: avisa que a Stripe continua cobrando
    r = await chamar(admin, depsAdmin, ADM, { acao: 'acesso', user_id: A.id, ativo: false });
    assertEquals([de(A).ativo, de(A).motivo], [false, 'bloqueado']);
    assert(String(r.corpo.aviso).includes('Stripe'));
    assertEquals(await acesso(A), false);
    // webhook não desfaz o bloqueio
    await avisar('customer.subscription.updated', S.subs[sub.id]);
    assertEquals((await statusDe(A)).bloqueado, true);
    // reativa A: volta como assinante, sem virar cortesia
    r = await chamar(admin, depsAdmin, ADM, { acao: 'acesso', user_id: A.id, ativo: true });
    assertEquals([de(A).ativo, de(A).motivo], [true, 'assinante']);
    assertEquals((await statusDe(A)).cortesia, false);
    // admin e pedidos inválidos
    assertEquals((await chamar(admin, depsAdmin, ADM, { acao: 'acesso', user_id: ADM.id, ativo: false })).status, 400);
    assertEquals((await chamar(admin, depsAdmin, ADM, { acao: 'acesso', user_id: 'x', ativo: false })).status, 400);
    assertEquals((await chamar(admin, depsAdmin, ADM, { acao: 'acesso', user_id: 'dddddddd-0000-0000-0000-000000000009', ativo: true })).status, 404);
  });
  await t.step('plano anual com preço de fundador: fica de fora do reajuste', async () => {
    await sql`insert into auth.users (id, email) values (${C.id}, ${C.email}) on conflict do nothing`;
    let r = await chamar(admin, depsAdmin, ADM, { acao: 'salvar', preco_centavos: 5990, dias_teste: 7, vendas_abertas: true, fundador_ate: '2099-12-31' });
    assertEquals(r.corpo.config.fundador_ate, '2099-12-31');
    r = await chamar(assinatura, depsAss, C, { acao: 'checkout', cpf: CPF, plano: 'anual' });
    assertEquals(r.status, 200);
    const s = S.sessoes.at(-1), [cfg] = await sql`select * from public.config_cobranca`;
    assertEquals(s.line_items[0].price, cfg.stripe_price_anual_id);
    assertEquals([s.subscription_data.metadata.plano, s.subscription_data.metadata.fundador], ['anual', 'sim']);
    const sc = criarAssinaturaNaStripe((await statusDe(C)).stripe_customer_id, cfg.stripe_price_anual_id, C.id, 'active');
    sc.metadata.fundador = 'sim';
    await avisar('customer.subscription.created', sc);
    const c = await statusDe(C); assertEquals([c.intervalo, c.fundador, c.preco_centavos], ['year', true, 29700]);
    // MRR: A paga 5990/mês; C paga 29700/ano = 2475/mês
    r = await chamar(admin, depsAdmin, ADM, { acao: 'resumo' });
    assertEquals([r.corpo.numeros.mrr_centavos, r.corpo.numeros.anuais, r.corpo.numeros.fundadores], [5990 + 2475, 1, 1]);
    // reajuste do anual para todos: a fundadora fica no preço antigo
    r = await chamar(admin, depsAdmin, ADM, { acao: 'salvar', preco_centavos: 5990, preco_anual_centavos: 47900, dias_teste: 7, vendas_abertas: true, fundador_ate: '2099-12-31', aplicar_atuais: true });
    assertEquals([r.corpo.fundadores, r.corpo.falhas], [1, 0]);
    assertEquals(S.subs[sc.id].items.data[0].price.unit_amount, 29700);
    const [cfg2] = await sql`select * from public.config_cobranca`;
    assertEquals([cfg2.preco_anual_centavos, S.prices[cfg2.stripe_price_anual_id].unit_amount], [47900, 47900]);
    assertEquals(S.prices[cfg.stripe_price_anual_id].active, false);
    assertEquals((await chamar(admin, depsAdmin, ADM, { acao: 'salvar', preco_centavos: 5990, preco_anual_centavos: 0, dias_teste: 7, vendas_abertas: true })).status, 400);
  });
  await t.step('excluir conta cancela a cobrança e apaga tudo', async () => {
    const r = await chamar(assinatura, depsAss, A, { acao: 'excluir_conta' });
    assertEquals(r.status, 200);
    assertEquals(S.subs[sub.id].status, 'canceled');
    assertEquals((await sql`select count(*)::int as n from auth.users where id = ${A.id}`)[0].n, 0);
    assertEquals(await statusDe(A), undefined);
    assertEquals((await avisar('customer.subscription.deleted', S.subs[sub.id])).status, 200); // aviso tardio não quebra
  });
  await sql.end();
});
