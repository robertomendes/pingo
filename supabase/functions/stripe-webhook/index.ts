// Pingo — função "stripe-webhook" (chamada pela Stripe a cada evento de cobrança)
// Confere a assinatura digital do aviso, busca o estado atual da assinatura
// na Stripe e grava no banco. Configure com "Verify JWT" DESLIGADO.
// deno-lint-ignore-file no-explicit-any
import Stripe from 'npm:stripe@23.1.0';
import postgres from 'npm:postgres@3.4.5';

type Deps = { stripe: any | null; sql: any };
const cripto = Stripe.createSubtleCryptoProvider();

export async function aplicarAssinatura(sql: any, sub: any): Promise<boolean> {
  const cliente = typeof sub.customer === 'string' ? sub.customer : sub.customer?.id;
  const item = sub.items?.data?.[0];
  const fim = sub.current_period_end ?? item?.current_period_end ?? null;
  let dono = sub.metadata?.user_id || null;
  if (!dono && cliente) dono = (await sql`select dono from public.assinaturas where stripe_customer_id = ${cliente}`)[0]?.dono ?? null;
  if (!dono) return false;
  const existe = (await sql`select 1 from auth.users where id = ${dono}`).length > 0;
  if (!existe) return false;
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
  if (req.method !== 'POST') return new Response('ok');
  if (!deps.stripe) return new Response('Stripe não configurada', { status: 503 });
  const assinaturaDigital = req.headers.get('stripe-signature');
  const corpo = await req.text();
  const [seg] = await deps.sql`select webhook_secret from public.cobranca_segredos where id = 1`;
  if (!seg?.webhook_secret || !assinaturaDigital) return new Response('webhook não configurado', { status: 400 });
  let ev: any;
  try {
    ev = await deps.stripe.webhooks.constructEventAsync(corpo, assinaturaDigital, seg.webhook_secret, undefined, cripto);
  } catch {
    return new Response('assinatura digital inválida', { status: 400 });
  }
  try {
    const o = ev.data?.object ?? {};
    let subId: any = null;
    if (ev.type.startsWith('customer.subscription.')) subId = o.id;
    else if (ev.type === 'checkout.session.completed') subId = o.subscription;
    else if (ev.type.startsWith('invoice.')) subId = o.subscription ?? o.parent?.subscription_details?.subscription ?? null;
    if (subId) {
      const sub = await deps.stripe.subscriptions.retrieve(typeof subId === 'string' ? subId : subId.id);
      await aplicarAssinatura(deps.sql, sub);
    }
    await deps.sql`insert into public.eventos_stripe (id, tipo) values (${ev.id}, ${ev.type}) on conflict (id) do nothing`;
    return new Response(JSON.stringify({ recebido: true }), { headers: { 'Content-Type': 'application/json' } });
  } catch (e) {
    console.error('webhook', ev?.type, e);
    return new Response('erro ao processar', { status: 500 }); // a Stripe tenta de novo
  }
}

if (!(globalThis as any).__PINGO_TESTE) {
  const chave = Deno.env.get('STRIPE_SECRET_KEY');
  const stripe = chave ? new Stripe(chave, { httpClient: Stripe.createFetchHttpClient() }) : null;
  const sql = postgres(Deno.env.get('SUPABASE_DB_URL')!, { prepare: false, max: 2 });
  Deno.serve((req) => handler(req, { stripe, sql }));
}
