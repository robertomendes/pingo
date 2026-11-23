# Gera algarismos escritos "à mão" com variações comuns no Brasil (1 com tracinho
# longo e com base, 7 cortado, 4 fechado...), rasterizados pela MESMA função do app.
import asyncio, json, sys, numpy as np
from playwright.async_api import async_playwright

GEN_JS = r'''
([n, semente]) => {
  let s = semente; const r = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  const U = (a, b) => a + (b - a) * r();
  const T = {
    0: [[[ .5,.05],[.25,.12],[.13,.35],[.13,.65],[.25,.88],[.5,.95],[.75,.88],[.87,.65],[.87,.35],[.75,.12],[.5,.05]]],
    2: [[[.18,.25],[.3,.09],[.5,.05],[.7,.09],[.82,.25],[.75,.47],[.18,.93],[.88,.93]]],
    3: [[[.2,.12],[.55,.05],[.8,.2],[.72,.42],[.45,.48],[.75,.55],[.85,.78],[.6,.95],[.2,.88]]],
    5: [[[.82,.06],[.25,.06],[.2,.45],[.55,.4],[.82,.58],[.78,.85],[.5,.95],[.18,.86]]],
    6: [[[.75,.08],[.4,.2],[.18,.55],[.25,.85],[.5,.95],[.78,.82],[.8,.6],[.55,.48],[.25,.6]]],
    8: [[[.5,.48],[.22,.3],[.3,.08],[.5,.04],[.72,.1],[.76,.3],[.5,.48],[.2,.7],[.3,.92],[.5,.96],[.75,.9],[.8,.7],[.5,.48]]],
    9: [[[.78,.35],[.6,.1],[.35,.08],[.2,.28],[.3,.45],[.55,.45],[.78,.3],[.75,.95]]],
  };
  const variantes = {
    1: () => { const t = r(); const fx = U(.12,.4), fy = U(.18,.45), x = U(.5,.62);
      if (t < .2) return [[[x,.05],[x,.95]]];
      if (t < .7) return [[[fx,fy],[x,.05],[x,.95]]];                                // tracinho (curto a longo)
      if (t < .9) return [[[fx,fy],[x,.05],[x,.95]],[[U(.15,.3),.95],[U(.7,.9),.95]]]; // tracinho + base
      return [[[x,.05],[x,.95]],[[U(.15,.3),.95],[U(.7,.9),.95]]]; },               // só base
    4: () => r() < .5 ? [[[U(.6,.7),.95],[U(.6,.7),.05],[.12,.68],[.9,.68]]]
                      : [[[U(.12,.25),.05],[U(.12,.25),.6],[.9,.6]],[[U(.62,.75),.05],[U(.62,.75),.95]]],
    7: () => { const base = [[U(.1,.2),.07],[U(.8,.9),.07],[U(.3,.5),.95]];
      return r() < .55 ? [base, [[U(.25,.35),.5],[U(.65,.8),.5]]] : [base]; },
  };
  const out = [];
  for (let i = 0; i < n; i++) {
    const d = i % 10;
    let strokes = variantes[d] ? variantes[d]() : T[d];
    const rot = U(-.2,.2), shear = U(-.25,.15), sx = U(.6,1.15), j = U(.005,.035);
    strokes = strokes.map(st => {
      const pts = []; for (let k = 0; k < st.length - 1; k++) { const m = 6; for (let q = 0; q < m; q++) pts.push([st[k][0] + (st[k+1][0]-st[k][0])*q/m, st[k][1] + (st[k+1][1]-st[k][1])*q/m]); } pts.push(st[st.length-1]);
      return pts.map(([x, y]) => { x = (x - .5) * sx; y = y - .5; x += shear * y; const X = x*Math.cos(rot) - y*Math.sin(rot), Y = x*Math.sin(rot) + y*Math.cos(rot); return [(X + U(-j,j)) * 200 + 200, (Y + U(-j,j)) * 200 + 200]; });
    });
    const g = PINGO_TEST.rasterize(strokes);
    let txt = ''; for (let k = 0; k < 784; k++) txt += String.fromCharCode(65 + Math.round(g[k] * 25));
    out.push([d, txt]);
  }
  return out;
}
'''
async def main(total, out):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        pg = await b.new_page(); await pg.goto('http://localhost:8766/app/'); await pg.wait_for_timeout(800)
        X, y = [], []
        for lote in range(total // 2000):
            res = await pg.evaluate(GEN_JS, [2000, 7919 * (lote + 1) + int(sys.argv[3] if len(sys.argv) > 3 else 0)])
            for d, t in res:
                y.append(d); X.append(np.frombuffer(t.encode(), dtype=np.uint8).astype(np.float32) - 65)
        X = np.array(X) / 25.0
        np.savez_compressed(out, X=X.astype(np.float32), y=np.array(y))
        print(out, X.shape)
        await b.close()
asyncio.run(main(int(sys.argv[1]), sys.argv[2]))
