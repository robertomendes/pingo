import asyncio, json
from playwright.async_api import async_playwright
V01={"criancas":[{"id":"c1731400000000","nome":"Nina","cor":"#FFE3C7","hab":2,"nivel":1,"estrelas":30,"sequencia":3,"ultimoDia":"2026-11-11","teclado":False,"historico":[{"id":"l1731400000001","dia":"2026-11-11","hab":2,"itens":[],"ms":60000,"estrelas":3}]}],"ativa":"c1731400000000","consentimento":True}
async def main():
    async with async_playwright() as p:
        br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
        # 1) supabase-js real, sem configuração
        ctx=await br.new_context(service_workers='block'); pg=await ctx.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.goto('http://localhost:8766/'); await pg.wait_for_timeout(800)
        print('supabase carregado:', await pg.evaluate('typeof window.supabase.createClient'), '| erros:', errs)
        # 2) com configuração falsa (sem rede até o Supabase): app abre normal, conta disponível
        ctx2=await br.new_context(service_workers='block'); 
        await ctx2.route('**/config.js', lambda r: r.fulfill(content_type='application/javascript', body="window.PINGO_CONFIG={supabaseUrl:'https://exemplo.supabase.co',supabaseAnonKey:'sb_publishable_teste',contato:'contato@exemplo.com'};"))
        await ctx2.route('https://exemplo.supabase.co/**', lambda r: r.abort())
        pg2=await ctx2.new_page(); errs2=[]; pg2.on('pageerror',lambda e:errs2.append(str(e)))
        await pg2.goto('http://localhost:8766/'); await pg2.wait_for_timeout(1000)
        print('botão entrar na boas-vindas:', await pg2.locator('[data-act=abrirConta]').count(), '| erros:', errs2)
        await pg2.click('[data-act=abrirConta]'); await pg2.fill('input[name=email]','a@b.com'); await pg2.fill('input[name=senha]','12345678'); await pg2.click('button[type=submit]'); await pg2.wait_for_timeout(1500)
        print('login sem rede ->', await pg2.locator('[role=alert]').inner_text())
        await pg2.click('[data-act=contaModo][data-m=criar]'); await pg2.click('[data-act=privacidade]'); await pg2.wait_for_timeout(300)
        await pg2.screenshot(path='v2_privacidade.png'); await pg2.click('[data-act=fecharModal]')
        print('email preservado após modal:', await pg2.locator('input[name=email]').input_value())
        await pg2.screenshot(path='v2_criar.png')
        # 3) migração v0.1
        ctx3=await br.new_context(service_workers='block'); await ctx3.add_init_script('localStorage.setItem("pingo.v1", %s)' % json.dumps(json.dumps(V01)))
        pg3=await ctx3.new_page(); errs3=[]; pg3.on('pageerror',lambda e:errs3.append(str(e)))
        await pg3.goto('http://localhost:8766/'); await pg3.wait_for_timeout(500)
        t=await pg3.locator('main').inner_text()
        print('migração v0.1:', '30 estrelas' in t, 'Somando 3' in t, '| erros:', errs3)
        await br.close()
asyncio.run(main())
