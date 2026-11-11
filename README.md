# Pingo — prática diária de matemática

MVP (v0.1) de um app de prática diária para crianças de 4 a 10 anos: a criança escreve a resposta com o dedo ou a caneta e o app corrige na hora, com reconhecimento de dígitos rodando no próprio aparelho.

- `index.html` — o app completo (PWA: instala na Tela de Início e funciona offline)
- `sw.js`, `manifest.webmanifest`, ícones — instalação e modo offline
- `fonte/src/app.html` — fonte do app antes de embutir o modelo
- `fonte/train.py` — treino do modelo de dígitos (MLP 784-160-10, pesos int8)

Os dados das crianças ficam só no navegador do aparelho; nada é enviado para servidores.
