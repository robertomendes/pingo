# Pingo — prática diária de matemática

App de prática diária para crianças de 4 a 10 anos: a criança escreve a resposta com o dedo ou a caneta e o app corrige na hora, com reconhecimento de dígitos rodando no próprio aparelho.

**v0.8** — página de vendas na raiz do site, app em `/app/`, preço de lançamento. **v0.7** — trilha ampliada: 4 partes (adição até 20, subtração até 20, contas maiores com vai um e empréstimo até centenas, tabuada do 2 ao 10), 39 etapas e 157 lições, com revisão das etapas anteriores e dicas para cada tipo de conta. **v0.6** — Termos de uso e Política de privacidade (LGPD e ECA Digital), autorização do responsável registrada no cadastro e aceite obrigatório para contas antigas. **v0.5** — lista de usuários na administração, com liga/desliga de acesso (cortesia ou bloqueio). Assinatura mensal recorrente com cartão (Stripe), preço configurável na tela de administração, login obrigatório, backup e sincronização entre aparelhos.

## Hospedagem

O site fica no Netlify (projeto `pingo-app`), publicado sozinho a cada push na `main`, em https://pingo.robertomendes.com.br/ (DNS no próprio Netlify). A raiz é a página de vendas (`index.html`, gerada por `fonte/landing/build_landing.py` a partir de `fonte/landing/pagina.dc.html`, o arquivo do canvas de design) e o app mora em `/app/` (`app/index.html`, gerado por `fonte/build.py`). Quem já usa o app no aparelho, ou chega por um link de e-mail, é mandado da raiz direto para `/app/`. O `sw.js` da raiz só desliga o service worker antigo. As configurações estão em `netlify.toml`, que também esconde as pastas `fonte/` e `supabase/`. O endereço antigo do GitHub Pages redireciona para o novo. No Supabase, a variável `APP_URL` das funções e a Site URL do login apontam para o endereço novo.

## Arquivos

- `index.html` — o app completo (PWA: instala na Tela de Início e funciona offline). Gerado por `fonte/build.py`.
- `config.js` — endereço e chave pública do Supabase. Vazio = app só no aparelho, sem conta.
- `supabase/schema.sql` — tabelas, segurança por conta (Row Level Security) e exclusão de conta.
- `vendor/supabase.js` — cliente oficial do Supabase (v2.119.0), servido junto para funcionar offline.
- `sw.js`, `manifest.webmanifest`, ícones — instalação e modo offline.
- `fonte/src/app.html` — fonte do app; `fonte/model.json` — pesos do modelo de dígitos; `fonte/train.py` — treino do modelo.
- `fonte/testes/` — testes automáticos (Playwright) de sincronização entre dois aparelhos.

## Ligar a nuvem (uma vez)

1. Crie um projeto em supabase.com, na região **South America (São Paulo)**.
2. No **SQL Editor**, cole `supabase/schema.sql` inteiro e clique em **Run**.
3. Em **Authentication › URL Configuration**: Site URL `https://pingo.robertomendes.com.br/` e o mesmo endereço em Redirect URLs.
4. Em **Settings › API Keys**, copie a Project URL e a chave pública (anon/publishable) para `config.js`. Nunca use a chave `service_role`/secret aqui.
5. Antes de abrir para clientes: configure um SMTP próprio em **Authentication › Emails** (o envio padrão do Supabase é só para testes) e traduza os modelos de e-mail.

## Como a sincronização funciona

- O aparelho é a fonte principal: tudo funciona offline e sobe quando a internet volta.
- Lições só se somam (nunca conflitam). Estrelas e dias seguidos são recalculados a partir delas.
- Progresso na trilha: vale o mais avançado, a menos que alguém tenha usado "Recomeçar a trilha" depois.
- Nome, cor e modo teclado: vale a alteração mais recente.
- Sem login, o app mostra só as telas de conta. Com a sessão salva, abre mesmo sem internet.
- Sessão expirada tranca o app até entrar de novo, sem apagar o que está no aparelho.
- Sair da conta (Área dos pais) limpa o aparelho (os dados continuam na nuvem). Excluir a conta apaga tudo, em cascata.

## Cobrança (Stripe)

- `supabase/cobranca.sql` — assinaturas, preço, administradores; o banco só aceita gravar progresso de quem tem assinatura em dia (ou é administrador).
- `supabase/functions/assinatura` — página de pagamento (Stripe Checkout), portal do cliente (trocar cartão, recibos, cancelar), conferência da assinatura e exclusão de conta (cancela a cobrança antes de apagar).
- `supabase/functions/stripe-webhook` — recebe os avisos da Stripe, confere a assinatura digital e grava o status. "Verify JWT" desligado.
- `supabase/trilha.sql` — libera os limites de etapa e lição no banco para a trilha ampliada (v0.7).
- `supabase/consentimento.sql` — registro de cada aceite dos termos (versão, data, navegador); só o próprio dono insere e lê, ninguém altera. Para pedir novo aceite de todos, mude `TERMOS_VERSAO` em `fonte/src/app.html` e a data nas páginas `termos.html` e `privacidade.html`.
- `supabase/usuarios.sql` — colunas `cortesia` (acesso sem pagar) e `bloqueado` (acesso cortado pelo administrador) e a regra de acesso atualizada. Rode depois de `cobranca.sql`.
- `supabase/functions/admin-cobranca` — conectar à Stripe (cria produto, preço, webhook e portal), definir preço e dias de teste, abrir vendas, ver os números e a lista de usuários, ligar e desligar o acesso de cada um.

Ligar: em Edge Functions › Secrets, crie `STRIPE_SECRET_KEY` (comece com a chave de teste `sk_test_…`). Depois, no app, Área dos pais › Administração do Pingo › Conectar à Stripe. Para cobrar de verdade, troque pela chave `sk_live_…` e toque em Reconectar.
