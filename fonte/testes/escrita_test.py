# Leitura da escrita à mão: estilos comuns no Brasil (1 com tracinho/base, 7 cortado, 4 fechado)
# e números de 1 a 3 algarismos, desenhados com traços independentes do gerador de treino.
import asyncio
from playwright.async_api import async_playwright
def ch(c, x): return [[(x + u, v) for u, v in s] for s in c]
DIG = {
 '0': [[(.5,.05),(.25,.12),(.13,.35),(.13,.65),(.25,.88),(.5,.95),(.75,.88),(.87,.65),(.87,.35),(.75,.12),(.5,.05)]],
 '1': [[(.5,.05),(.5,.95)]], '1f': [[(.22,.32),(.55,.05),(.55,.95)]], '1b': [[(.25,.28),(.55,.05),(.55,.95)],[(.25,.95),(.85,.95)]],
 '2': [[(.18,.25),(.35,.07),(.65,.06),(.82,.25),(.75,.5),(.18,.93),(.88,.93)]],
 '3': [[(.2,.12),(.55,.05),(.8,.2),(.72,.42),(.45,.48),(.75,.55),(.85,.78),(.6,.95),(.2,.88)]],
 '4': [[(.65,.95),(.65,.05),(.12,.68),(.9,.68)]], '4c': [[(.2,.05),(.2,.6),(.9,.6)],[(.7,.05),(.7,.95)]],
 '5': [[(.82,.06),(.25,.06),(.2,.45),(.55,.4),(.82,.58),(.78,.85),(.5,.95),(.18,.86)]],
 '6': [[(.75,.08),(.4,.2),(.18,.55),(.25,.85),(.5,.95),(.78,.82),(.8,.6),(.55,.48),(.25,.6)]],
 '7': [[(.15,.07),(.85,.07),(.4,.95)]], '7c': [[(.15,.07),(.85,.07),(.4,.95)],[(.3,.5),(.75,.5)]],
 '8': [[(.5,.48),(.22,.3),(.3,.08),(.5,.04),(.72,.1),(.76,.3),(.5,.48),(.2,.7),(.3,.92),(.5,.96),(.75,.9),(.8,.7),(.5,.48)]],
 '9': [[(.78,.35),(.6,.1),(.35,.08),(.2,.28),(.3,.45),(.55,.45),(.78,.3),(.75,.95)]],
}
CASOS = [('1f','1'),('1b','1'),('1','1'),('7c','7'),('4c','4')] + [(d, d) for d in '0123456789'] + \
        [(('1f','2'),'12'), (('1b','7c'),'17'), (('1f','4c'),'14'), (('9','1f'),'91'), (('4','7c','9'),'479'), (('1b','0','0'),'100'), (('6','3','1f'),'631')]
def interp(p, n=6):
    o = []
    for (a,b),(c,d) in zip(p, p[1:]): o += [(a+(c-a)*k/n, b+(d-b)*k/n) for k in range(n)]
    return o + [p[-1]]
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        pg = await br.new_page(); await pg.goto('http://localhost:8766/app/'); await pg.wait_for_timeout(800)
        W, H = 460, 240; falhas = []
        for chave, esperado in CASOS:
            ks = chave if isinstance(chave, tuple) else (chave,)
            n = len(ks); w = min(W*0.26, H*0.62*0.7); h = H*0.62; x0 = (W - n*w - (n-1)*w*0.3)/2; y0 = H*0.19
            strokes = []
            for i, k in enumerate(ks):
                ox = x0 + i*w*1.3
                for s in DIG[k]: strokes.append([[(ox+u*w)/W*1000, (y0+v*h)/H*1000] for u, v in interp(s)])
            r = await pg.evaluate('([s,w,h]) => PINGO_TEST.recognize(s,w,h)', [strokes, W, H])
            ok = r and r.get('texto') == esperado
            print(('OK   ' if ok else 'FALHA ') + '%s -> %s (conf %.2f)' % ('+'.join(ks), r.get('texto'), r.get('conf', 0)))
            if not ok: falhas.append(chave)
        await br.close()
        assert not falhas, falhas
asyncio.run(main())
