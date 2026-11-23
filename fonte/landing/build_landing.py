# Gera ../../index.html (a página de vendas) a partir de pagina.dc.html,
# o arquivo editado no canvas de design. Troca os {{campos}} pelos valores
# padrão declarados no próprio arquivo e tira a parte que só o editor usa.
import os, re, json, html
base = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(base, 'pagina.dc.html'), encoding='utf-8').read()

props = json.loads(html.unescape(re.search(r"data-props='([^']*)'", src).group(1)))
vals = {k: v['default'] for k, v in props.items() if isinstance(v, dict) and 'default' in v}

helmet = re.search(r'<helmet>(.*?)</helmet>', src, re.S).group(1)
corpo = re.search(r'<x-dc>(.*?)</x-dc>', src, re.S).group(1)
corpo = re.sub(r'<helmet>.*?</helmet>', '', corpo, flags=re.S)

def troca(m):
    k = m.group(1).strip()
    if k not in vals: raise SystemExit('campo sem valor padrão: ' + k)
    return html.escape(str(vals[k]), quote=True)
corpo = re.sub(r'\{\{\s*([\w.]+)\s*\}\}', troca, corpo)
# links absolutos para o próprio site viram relativos (funcionam em qualquer endereço)
corpo = corpo.replace('https://pingo.robertomendes.com.br/', '/')

titulo = 'Pingo — 10 minutos por dia de matemática para seu filho'
desc = ('Prática diária de matemática para crianças de 5 a 10 anos: a criança escreve a resposta, '
        'recebe a correção na hora e avança no próprio ritmo. Adição, subtração, contas maiores e tabuada. 7 dias grátis.')
pagina = f'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<script>/* endereço antigo (GitHub Pages) -> endereço oficial */
if (location.hostname === 'robertomendes.github.io') location.replace('https://pingo.robertomendes.com.br/' + location.pathname.replace(/^\\/pingo\\/?(index\\.html)?/, '') + location.search + location.hash);
/* quem já usa o app (ícone na tela inicial, já logado ou voltando de um e-mail de login) vai direto para o app */
(function () {{
  try {{
    var h = location.hash + location.search;
    var deEmail = /access_token|type=recovery|type=signup|code=|assinatura=/.test(h);
    var instalado = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone;
    var logado = false;
    for (var i = 0; i < localStorage.length; i++) {{ if (/^sb-.*-auth-token$/.test(localStorage.key(i))) logado = true; }}
    var d = JSON.parse(localStorage.getItem('pingo.v1') || 'null'); if (d && d.conta) logado = true;
    if (deEmail || instalado || logado) location.replace('/app/' + location.search + location.hash);
  }} catch (e) {{ }}
}})();
</script>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{titulo}</title>
<meta name="description" content="{html.escape(desc, quote=True)}">
<meta name="theme-color" content="#2F4BC7">
<meta property="og:type" content="website">
<meta property="og:title" content="{titulo}">
<meta property="og:description" content="{html.escape(desc, quote=True)}">
<meta property="og:url" content="https://pingo.robertomendes.com.br/">
<meta property="og:image" content="https://pingo.robertomendes.com.br/icon-512.png">
<meta property="og:locale" content="pt_BR">
<link rel="canonical" href="https://pingo.robertomendes.com.br/">
<link rel="icon" type="image/png" href="/icon-192.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{helmet.strip()}
<style>html{{scroll-behavior:smooth}}section[id]{{scroll-margin-top:80px}}</style>
</head>
<body>
{corpo.strip()}
</body>
</html>
'''
open(os.path.join(base, '..', '..', 'index.html'), 'w', encoding='utf-8').write(pagina)
print('index.html (página de vendas) gerado')
