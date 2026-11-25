# Testes da trilha ampliada (v0.7): todas as etapas geram contas válidas, a criança
# responde contas de +, −, × e com 3 algarismos, avança de etapa e de bloco.
import asyncio, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sync_test import S, device, st, idle, check, errs
from playwright.async_api import async_playwright

def calc(label):
    m = re.match(r'Quanto é (\d+) (mais|menos|vezes) (\d+)\?', label)
    a, op, b = int(m[1]), m[2], int(m[3])
    return a + b if op == 'mais' else a - b if op == 'menos' else a * b

async def responder_licao(pg, shot=None):
    await pg.click('[data-act=comecar]')
    if await pg.locator('[data-act=tecla]').count() == 0: await pg.click('[data-act=modo]')
    for i in range(5):
        v = calc(await pg.locator('.conta').get_attribute('aria-label'))
        for ch in str(v): await pg.click(f'[data-act=tecla][data-k="{ch}"]')
        if shot and i == 0: await pg.screenshot(path=shot)
        await pg.click('[data-act=conferir]')
        await pg.click('[data-act=proxima]')

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        A = await device(br, 'T')
        # gerador: todas as etapas e lições, muitas vezes
        r = await A.evaluate('''() => { const E = PINGO_TEST.ETAPAS; let ruins = 0, total = 0, lic = 0;
          for (const e of E) { lic += e.licoes; for (let n = 0; n < e.licoes; n++) for (let k = 0; k < 200; k++) for (const p of e.gerar(n)) { total++; const v = PINGO_TEST.resultado(p); if (!(Number.isInteger(v) && v >= 1 && v <= 999)) ruins++; } }
          return { etapas: E.length, lic, total, ruins, blocos: PINGO_TEST.BLOCOS.length }; }''')
        check(r['etapas'] == 39 and r['lic'] == 157 and r['blocos'] == 4, 'trilha com 4 partes, 39 etapas e 157 lições (%s)' % r)
        check(r['ruins'] == 0, 'nenhuma conta inválida em %d sorteadas' % r['total'])
        dicas = await A.evaluate("[{a:7,b:5,op:'+'},{a:27,b:5,op:'+'},{a:13,b:5,op:'-'},{a:32,b:7,op:'-'},{a:3,b:4,op:'x'},{a:7,b:8,op:'x'}].map(PINGO_TEST.dica)")
        check('complete o 10' in dicas[0] and 'vai um' in dicas[1] and 'volte 5' in dicas[2] and 'emprestada' in dicas[3] and '3 + 3 + 3 + 3' in dicas[4] and '7 × 7 = 49' in dicas[5], 'dicas certas para cada tipo de conta')
        # conta, assinatura e criança
        await A.click('[data-act=contaModo][data-m=criar]')
        await A.fill('input[name=email]', 'trilha@x.com'); await A.fill('input[name=senha]', '12345678'); await A.check('input[name=ok]'); await A.click('button[type=submit]'); await idle(A)
        await A.fill('input[name=cpf]', '52998224725'); await A.click('[data-act=assinar]'); await idle(A, 2500)
        await A.fill('input[name=nome]', 'Téo'); await A.click('form[data-form=perfil] button[type=submit]'); await idle(A, 500)
        t = await A.locator('main').inner_text()
        check('Adição até 20' in t and 'parte 1 de 4' in t.lower() and 'lição 1 de 3' in t, 'início mostra a parte 1 e 3 lições por etapa')
        # vai para a última etapa da subtração (Tirando 9, lição 3) e conclui: abre o bloco "Mais e menos"
        await A.evaluate('(() => { const c = PINGO_TEST.db.criancas[0]; c.hab = 17; c.nivel = 2; })()'); await A.evaluate('PINGO_TEST.salvar && PINGO_TEST.salvar()')
        await A.reload(); await idle(A)
        t = await A.locator('main').inner_text()
        check('Subtração até 20' in t and 'Tirando 9' in t, 'trilha mostra o bloco de subtração')
        await responder_licao(A, '/home/claude/pingo/test/v7_sub.png'); await idle(A, 500)
        f = await A.locator('main').inner_text()
        check('Você destravou: Mais e menos' in f, 'concluir Tirando 9 destrava a revisão Mais e menos')
        await A.click('[data-act=inicio]')
        # pula para o fim da revisão: abre "Contas maiores" (nova parte)
        await A.evaluate('(() => { const c = PINGO_TEST.db.criancas[0]; c.hab = 18; c.nivel = 2; })()'); await A.evaluate('PINGO_TEST.salvar()'); await A.reload(); await idle(A)
        await responder_licao(A); await idle(A, 500)
        f = await A.locator('main').inner_text()
        check('Parte nova: Contas maiores' in f and 'Dezena + unidade' in f, 'concluir o bloco 2 avisa a parte nova')
        await A.click('[data-act=inicio]')
        # centenas (3 algarismos) e tabuada
        await A.evaluate('(() => { const c = PINGO_TEST.db.criancas[0]; c.hab = 27; c.nivel = 3; })()'); await A.evaluate('PINGO_TEST.salvar()'); await A.reload(); await idle(A)
        await responder_licao(A, '/home/claude/pingo/test/v7_centenas.png'); await idle(A, 500)
        hist = (await st(A))['criancas'][0]['historico'][-1]
        check(hist['hab'] == 27 and all(i['deprimeira'] for i in hist['itens']) and max(i['a'] for i in hist['itens']) >= 100, 'respostas de 3 algarismos pelo teclado contam como acerto')
        await A.click('[data-act=inicio]')
        await A.evaluate('(() => { const c = PINGO_TEST.db.criancas[0]; c.hab = 36; c.nivel = 4; })()'); await A.evaluate('PINGO_TEST.salvar()'); await A.reload(); await idle(A)
        t = await A.locator('main').inner_text()
        check('Tabuada' in t and 'parte 4 de 4' in t.lower() and 'Tabuada do 9' in t, 'bloco da tabuada aparece')
        await A.screenshot(path='/home/claude/pingo/test/v7_inicio_tabuada.png', full_page=True)
        await responder_licao(A, '/home/claude/pingo/test/v7_tabuada.png'); await idle(A, 500)
        hist = (await st(A))['criancas'][0]['historico'][-1]
        check(all(i['op'] == 'x' for i in hist['itens']), 'lição da tabuada guarda a operação ×')
        await A.click('[data-act=inicio]')
        # lição com erro mostra dica de multiplicação
        await A.click('[data-act=comecar]')
        await A.click('[data-act=tecla][data-k="1"]'); await A.click('[data-act=conferir]')
        check('Dica' in await A.locator('.aviso').inner_text(), 'errar a tabuada mostra dica')
        await A.click('[data-act=sair]')
        # área dos pais e replay
        await A.click('[data-act=abrirPais] >> nth=0')
        x, y = map(int, re.findall(r'\d+', await A.locator('h2').inner_text())); await A.fill('input[name=r]', str(x * y)); await A.click('button[type=submit]'); await idle(A, 500)
        t = await A.locator('main').inner_text()
        check('Tabuada do 10' in t and 'Somando centenas' in t and '(Tabuada)' in t, 'área dos pais mostra as etapas novas')
        await A.click('[data-act=replay] >> nth=0'); await idle(A, 300)
        check('×' in await A.locator('.modal').inner_text(), 'replay mostra contas de vezes')
        await A.screenshot(path='/home/claude/pingo/test/v7_pais.png', full_page=True)
        # sincronia: a nuvem aceitou etapa alta
        check(any(c['hab'] >= 36 for c in S.cri.values()), 'nuvem recebeu a etapa nova da criança')
        print('erros JS:', errs)
        assert not errs
        await br.close()
asyncio.run(main())
