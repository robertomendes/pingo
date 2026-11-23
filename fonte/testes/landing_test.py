# Página de vendas (raiz): abre para visitante novo, manda quem já usa direto para /app/.
import asyncio
from playwright.async_api import async_playwright
BASE = 'http://localhost:8766/'
def check(c, m): print(('OK   ' if c else 'FALHA ') + m); assert c, m
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        ctx = await br.new_context(viewport={'width': 1366, 'height': 900}, service_workers='block')
        pg = await ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(BASE); await pg.wait_for_timeout(1200)
        t = await pg.locator('body').inner_text()
        check(pg.url == BASE and '10 minutos por dia' in t, 'visitante novo vê a página de vendas')
        check('R$ 39' in t and 'R$ 59' in t and 'PREÇO DE LANÇAMENTO' in t.upper(), 'preço de lançamento R$ 39 e normal R$ 59 aparecem')
        check('{{' not in await pg.content(), 'nenhum campo do editor sobrou sem trocar')
        hrefs = await pg.eval_on_selector_all('a.cta', 'as => as.map(a => a.getAttribute("href"))')
        check(len(hrefs) >= 4 and all(h == '/app/' for h in hrefs), 'todos os botões levam ao app (%d)' % len(hrefs))
        await pg.screenshot(path='/home/claude/pingo/test/landing_desktop.png', full_page=True)
        m = await br.new_context(viewport={'width': 390, 'height': 844}, service_workers='block', is_mobile=True)
        pm = await m.new_page(); await pm.goto(BASE); await pm.wait_for_timeout(1000)
        larg = await pm.evaluate('document.documentElement.scrollWidth')
        check(larg <= 392, 'no celular não há rolagem lateral (%d px)' % larg)
        await pm.screenshot(path='/home/claude/pingo/test/landing_celular.png', full_page=True)
        # quem já usa vai direto ao app
        await pg.evaluate("localStorage.setItem('pingo.v1', JSON.stringify({conta:{id:'x'}}))")
        await pg.goto(BASE); await pg.wait_for_timeout(800)
        check(pg.url.endswith('/app/'), 'quem já tem conta no aparelho cai direto no app')
        await pg.evaluate("localStorage.clear()")
        await pg.goto(BASE + '#access_token=abc&type=recovery'); await pg.wait_for_timeout(800)
        check('/app/' in pg.url and 'type=recovery' in pg.url, 'link de e-mail antigo (raiz) é repassado ao app com o token')
        await pg.goto(BASE + 'termos.html'); await pg.wait_for_timeout(500)
        check('Termos de uso' in await pg.title(), 'termos continuam na raiz')
        check(not errs, 'sem erros de JS: %s' % errs)
        await br.close()
asyncio.run(main())
