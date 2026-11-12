# Pingo — prática diária de matemática

App de prática diária para crianças de 4 a 10 anos: a criança escreve a resposta com o dedo ou a caneta e o app corrige na hora, com reconhecimento de dígitos rodando no próprio aparelho.

**v0.2** — conta do responsável, backup na nuvem e sincronização entre aparelhos (offline-first).

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
3. Em **Authentication › URL Configuration**: Site URL `https://robertomendes.github.io/pingo/` e o mesmo endereço em Redirect URLs.
4. Em **Settings › API Keys**, copie a Project URL e a chave pública (anon/publishable) para `config.js`. Nunca use a chave `service_role`/secret aqui.
5. Antes de abrir para clientes: configure um SMTP próprio em **Authentication › Emails** (o envio padrão do Supabase é só para testes) e traduza os modelos de e-mail.

## Como a sincronização funciona

- O aparelho é a fonte principal: tudo funciona offline e sobe quando a internet volta.
- Lições só se somam (nunca conflitam). Estrelas e dias seguidos são recalculados a partir delas.
- Progresso na trilha: vale o mais avançado, a menos que alguém tenha usado "Recomeçar a trilha" depois.
- Nome, cor e modo teclado: vale a alteração mais recente.
- Sair da conta limpa o aparelho (os dados continuam na nuvem). Excluir a conta apaga tudo, em cascata.
