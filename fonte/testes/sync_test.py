import asyncio, json, re, itertools, datetime
from playwright.async_api import async_playwright
BASE='http://localhost:8766/'
class Server:
    def __init__(s): s.users={}; s.toks={}; s.cri={}; s.lic=[]; s.offline=set(); s.clock=itertools.count(1); s.PAG=3; s.calls=[]; s.assin={}; s.admins=set(); s.config={'preco_centavos':4990,'dias_teste':7,'vendas_abertas':True,'modo':'teste'}; s.checkouts=0; s.termos={}; s.consents=[]
    def tem(s,uid):
        a=s.assin.get(uid) or {}
        if uid in s.admins: return True
        if a.get('bloqueado'): return False
        if a.get('cortesia'): return True
        if a.get('status') in ('active','trialing'): return True
        if a.get('status')=='past_due' and a.get('periodo_fim','')> (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=10)).isoformat(): return True
        return False
    def ts(s): return (datetime.datetime(2026,11,12,tzinfo=datetime.timezone.utc)+datetime.timedelta(seconds=next(s.clock))).isoformat()
    def handle(s, dev, op, args, tok):
        s.calls.append((dev,op))
        if dev in s.offline: return {'erro':'Failed to fetch'}
        a=json.loads(args)
        if op=='criar':
            if a['email'] in s.users: return {'erro':'User already registered'}
            uid=f'u{len(s.users)+1}'; s.users[a['email']]={'id':uid,'senha':a['senha']}; t='t'+uid+str(next(s.clock)); s.toks[t]=uid; s.users[a['email']]['meta']=a.get('termos'); return {'ok':{'tok':t,'u':{'id':uid,'email':a['email'],'termos':a.get('termos')}}}
        if op=='entrar':
            u=s.users.get(a['email'])
            if not u or u['senha']!=a['senha']: return {'erro':'Invalid login credentials'}
            t='t'+u['id']+str(next(s.clock)); s.toks[t]=u['id']; return {'ok':{'tok':t,'u':{'id':u['id'],'email':a['email']}}}
        uid=s.toks.get(tok)
        if not uid: return {'erro':'JWT expired','status':401}
        email=[e for e,u in s.users.items() if u['id']==uid][0]
        if op=='sessao': return {'ok':{'id':uid,'email':email}}
        if op=='baixar':
            cs=[{k:v for k,v in c.items() if k!='dono'} for c in s.cri.values() if c['dono']==uid]
            ls=[l for l in s.lic if l['dono']==uid and (not a.get('cursor') or l['recebido_em']>a['cursor'])][:s.PAG]
            return {'ok':{'criancas':cs,'licoes':[{k:v for k,v in l.items() if k!='dono'} for l in ls],'pagina':s.PAG}}
        if op=='cobranca': return {'ok':{'assin':s.assin.get(uid),'config':s.config,'admin':uid in s.admins,'termos':s.termos.get(uid)}}
        if op=='consent': s.termos[uid]=a['versao']; s.consents.append((uid,a['versao'],a['origem'])); return {'ok':None}
        if op=='funcao':
            nome=a['nome']; c=a['corpo']; acao=c.get('acao')
            if nome=='assinatura' and acao=='checkout':
                if not s.config['vendas_abertas']: return {'erro':'As assinaturas ainda não estão abertas.','status':409}
                s.checkouts+=1; fim=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=7)).isoformat()
                s.assin[uid]={'status':'trialing','preco_centavos':s.config['preco_centavos'],'periodo_fim':fim,'teste_fim':fim,'cancelar_no_fim':False,'ja_teve_teste':True}
                return {'ok':{'url':'http://localhost:8766/?assinatura=ok'}}
            if nome=='assinatura' and acao=='sincronizar': return {'ok':{'status':(s.assin.get(uid) or {}).get('status','nenhuma')}}
            if nome=='assinatura' and acao=='portal': return {'ok':{'url':'http://localhost:8766/#portal'}}
            if nome=='assinatura' and acao=='excluir_conta': return s.handle(dev,'excluir','{}',tok)
            if nome=='admin-cobranca':
                if uid not in s.admins: return {'erro':'Acesso só para administradores.','status':403}
                def lista():
                    out=[]
                    for em,u in s.users.items():
                        i=u['id']; x=s.assin.get(i) or {}; pago=x.get('status') in ('active','trialing','past_due') and not x.get('cortesia_mock')
                        if i in s.admins: mot='admin'
                        elif x.get('bloqueado'): mot='bloqueado'
                        elif x.get('cortesia'): mot='cortesia'
                        elif pago: mot='assinante'
                        else: mot='sem_assinatura'
                        out.append({'id':i,'email':em,'criado_em':'2026-11-12T10:00:00Z','ultimo_login':None,'confirmado':True,'criancas':sum(1 for c in s.cri.values() if c['dono']==i),'status':x.get('status','nenhuma'),'pago':pago,'ativo':mot in ('admin','cortesia','assinante'),'motivo':mot})
                    return out
                if acao=='usuarios': return {'ok':{'usuarios':lista()}}
                if acao=='acesso':
                    i=c['user_id']
                    if i in s.admins: return {'erro':'Administradores sempre têm acesso.','status':400}
                    x=s.assin.setdefault(i,{'status':'nenhuma'}); pago=x.get('status') in ('active','trialing','past_due')
                    if c['ativo']: x['bloqueado']=False; x['cortesia']=x.get('cortesia') or not pago
                    else: x['cortesia']=False; x['bloqueado']=pago
                    return {'ok':{'usuarios':lista(),'aviso':'Acesso bloqueado, mas a assinatura continua sendo cobrada na Stripe.' if (not c['ativo'] and pago) else None}}
                if acao=='salvar': s.config.update(preco_centavos=c['preco_centavos'],dias_teste=c['dias_teste'],vendas_abertas=c['vendas_abertas']); s.ultimo_salvar=c
                n=lambda st: sum(1 for x in s.assin.values() if x.get('status')==st)
                return {'ok':{'config':dict(s.config),'stripe':{'chave':True,'modoChave':'teste','conectada':True},'numeros':{'ativos':n('active'),'em_teste':n('trialing'),'pendentes':n('past_due'),'cancelados':n('canceled'),'mrr_centavos':sum(x['preco_centavos'] for x in s.assin.values() if x.get('status')=='active')},'migrados':0,'falhas':0}}
            return {'erro':'acao?'}
        if op in ('upC','upL') and not s.tem(uid): return {'erro':'new row violates row-level security policy'}
        if op=='upC':
            for r in a['rows']:
                ex=s.cri.get(r['id'])
                if ex and ex['dono']!=uid: return {'erro':'rls'}
                s.cri[r['id']]=dict(r,dono=uid)
            return {'ok':None}
        if op=='upL':
            have={l['id'] for l in s.lic}
            for r in a['rows']:
                c=s.cri.get(r['crianca_id'])
                if not c or c['dono']!=uid: return {'erro':'new row violates row-level security policy'}
                if r['id'] not in have: s.lic.append(dict(r,dono=uid,recebido_em=s.ts()))
            return {'ok':None}
        if op=='delC':
            for i in a['ids']:
                if i in s.cri and s.cri[i]['dono']==uid: del s.cri[i]; s.lic=[l for l in s.lic if l['crianca_id']!=i]
            return {'ok':None}
        if op=='excluir':
            s.cri={k:v for k,v in s.cri.items() if v['dono']!=uid}; s.lic=[l for l in s.lic if l['dono']!=uid]
            s.users={e:u for e,u in s.users.items() if u['id']!=uid}; s.toks={t:u for t,u in s.toks.items() if u!=uid}; return {'ok':None}
        return {'erro':'op?'}
MOCK_JS='''window.PINGO_BACKEND=(function(){const call=async(op,args)=>{const r=JSON.parse(await window.mockServer(op,JSON.stringify(args||{}),localStorage.getItem('mock.tok')||''));if(r.erro){const e=new Error(r.erro);e.status=r.status;throw e;}return r.ok;};
return{sessao:async()=>{const u=localStorage.getItem('mock.user');return localStorage.getItem('mock.tok')&&u?JSON.parse(u):null},aoMudar:()=>{},
criarConta:async(email,senha)=>{const r=await call('criar',{email,senha,termos:TERMOS_VERSAO});localStorage.setItem('mock.tok',r.tok);localStorage.setItem('mock.user',JSON.stringify(r.u));return{usuario:r.u,confirmar:false}},
entrar:async(email,senha)=>{const r=await call('entrar',{email,senha});localStorage.setItem('mock.tok',r.tok);localStorage.setItem('mock.user',JSON.stringify(r.u));return r.u},
sair:async()=>{localStorage.removeItem('mock.tok');localStorage.removeItem('mock.user')},recuperar:async()=>{},novaSenha:async()=>{},
baixar:c=>call('baixar',{cursor:c}),enviarCriancas:rows=>call('upC',{rows}),enviarLicoes:rows=>call('upL',{rows}),apagarCriancas:ids=>call('delC',{ids}),
excluirConta:async()=>{await call('funcao',{nome:'assinatura',corpo:{acao:'excluir_conta'}});localStorage.removeItem('mock.tok');localStorage.removeItem('mock.user')},
cobranca:()=>call('cobranca'),registrarConsentimento:o=>call('consent',{versao:TERMOS_VERSAO,origem:o}),funcao:async(nome,corpo)=>{try{return await call('funcao',{nome,corpo})}catch(e){e.daFuncao=true;throw e}}}})();'''
S=Server(); errs=[]
async def device(br,name):
    ctx=await br.new_context(viewport={'width':1180,'height':820},service_workers='block')
    await ctx.expose_function('mockServer', lambda op,args,tok: json.dumps(S.handle(name,op,args,tok)))
    await ctx.add_init_script(MOCK_JS)
    pg=await ctx.new_page(); pg.on('pageerror',lambda e:errs.append(name+': '+str(e)))
    await pg.goto(BASE); return pg
async def st(pg): return await pg.evaluate('JSON.parse(JSON.stringify(PINGO_TEST.db))')
async def idle(pg,t=1200): await pg.wait_for_timeout(t)
async def lesson(pg, wrong=False):
    await pg.click('[data-act=comecar]')
    db=await st(pg); c=[x for x in db['criancas'] if x['id']==db['ativa']][0]
    if not c['teclado']: await pg.click('[data-act=modo]')
    for i in range(5):
        a,b=map(int,re.findall(r'\d+',await pg.locator('.conta').get_attribute('aria-label')))
        v=a+b+(1 if wrong and i<2 else 0)
        for ch in str(v): await pg.click(f'[data-act=tecla][data-k="{ch}"]')
        await pg.click('[data-act=conferir]')
        if wrong and i<2:
            for ch in str(a+b): await pg.click(f'[data-act=tecla][data-k="{ch}"]')
            await pg.click('[data-act=conferir]')
        await pg.click('[data-act=proxima]')
    await pg.click('[data-act=inicio]')
async def pais(pg):
    await pg.click('[data-act=abrirPais] >> nth=0')
    x,y=map(int,re.findall(r'\d+',await pg.locator('h2').inner_text())); await pg.fill('input[name=r]',str(x*y)); await pg.click('button[type=submit]')
def resumo(db): return [(c['nome'],c['hab'],c['nivel'],c['estrelas'],len(c['historico']),c.get('teclado'),sum(1 for l in c['historico'] if not l.get('sinc'))) for c in db['criancas']]
def check(cond,msg): print(('OK   ' if cond else 'FALHA ')+msg); assert cond, msg
async def main():
    async with async_playwright() as p:
        br=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
        A=await device(br,'A')
        check(await A.locator('form[data-form=conta]').count()==1 and await A.locator('[data-act=comecar]').count()==0,'sem login: só aparece a tela de conta')
        check(await A.locator('[data-act=contaVoltar]').count()==0,'sem login: não há botão Voltar para escapar')
        await A.click('[data-act=contaModo][data-m=criar]')
        await A.fill('input[name=email]','pai@x.com'); await A.fill('input[name=senha]','12345678'); await A.click('button[type=submit]'); await idle(A,400)
        check('autorização' in await A.locator('[role=alert]').inner_text(),'criar conta exige marcar a autorização do responsável')
        check(await A.locator('form[data-form=conta] a[href="termos.html"]').count()==1 and await A.locator('form[data-form=conta] a[href="privacidade.html"]').count()==1,'cadastro tem links para termos e privacidade')
        await A.check('input[name=ok]'); await A.click('button[type=submit]'); await idle(A)
        uidA=S.users['pai@x.com']['id']
        check(S.consents and S.consents[-1][0]==uidA and S.consents[-1][2]=='cadastro','aceite do cadastro fica registrado no servidor')
        t=await A.locator('main').inner_text()
        check('Assine o Pingo' in t and 'R$ 49,90' in t and '7 dias grátis' in t,'conta nova sem assinatura vê a oferta com preço e teste grátis')
        await A.screenshot(path='/home/claude/pingo/test/v4_assinar.png',full_page=True)
        await A.evaluate("PINGO_TEST.db.criancas"); 
        await A.click('[data-act=assinar]'); await A.wait_for_url('**/pingo/**',timeout=3000) if False else None
        await idle(A,2500)
        check(await A.locator('input[name=nome]').count()==1,'depois do pagamento confirmado, o app libera o cadastro da criança')
        check('assinatura=' not in A.url,'o endereço de retorno é limpo')
        await A.fill('input[name=nome]','Nina'); await A.click('form[data-form=perfil] button[type=submit]')
        check(await A.locator('input[name=ok]').count()==0,'consentimento não é pedido de novo')
        await lesson(A); await idle(A)
        check(len(S.cri)==1 and len(S.lic)==1,'A criou conta, criança e lição na nuvem (%d,%d)'%(len(S.cri),len(S.lic)))
        await pais(A); selo=await A.locator('#selo-sinc').inner_text(); check('Backup em dia' in selo,'selo: '+selo)
        await A.screenshot(path='/home/claude/pingo/test/v3_pais.png',full_page=True)
        await A.click('[data-act=voltarCrianca]')
        B=await device(br,'B')
        await B.fill('input[name=email]','pai@x.com'); await B.fill('input[name=senha]','errada12'); await B.click('button[type=submit]'); await idle(B,500)
        check('incorretos' in await B.locator('[role=alert]').inner_text(),'senha errada mostra erro em português')
        await B.fill('input[name=senha]','12345678'); await B.click('button[type=submit]'); await idle(B)
        check(await B.locator('.perfil').count()==1,'B entrou e vê a Nina')
        await B.click('.perfil'); await lesson(B); await lesson(B); await idle(B)
        dA=await st(A); dB=await st(B)
        check(len(S.lic)==3,'servidor tem 3 lições')
        await A.reload(); await idle(A); dA=await st(A)
        check(resumo(dA)==resumo(await st(B)),'A e B iguais depois de sincronizar: %s'%resumo(dA))
        check(dA['criancas'][0]['hab']==1,'progresso feito no B (destravou +2) chegou no A')
        # conflito offline
        S.offline.add('A'); await A.click('[data-act=escolher] >> nth=0') if await A.locator('.perfil').count() else None
        await lesson(A, wrong=True); await idle(A)
        check(resumo(await st(A))[0][6]==1,'A offline: lição fica pendente')
        await pais(B); await B.click('[data-act=toggleTeclado]'); await idle(B)
        S.offline.discard('A'); await A.reload(); await idle(A,1500)
        await B.reload(); await idle(B,1500)
        rA=resumo(await st(A)); rB=resumo(await st(B))
        check(rA==rB and rA[0][4]==4,'após voltar online: 4 lições nos dois %s'%rA)
        check(rA[0][5] is False,'ajuste mais recente (teclado desligado no B) venceu no A')
        # recomeçar trilha
        await pais(B); await B.click('[data-act=reiniciar]'); await idle(B); await A.reload(); await idle(A)
        check(resumo(await st(A))[0][1]==0,'recomeçar a trilha no B vale no A')
        # segunda criança e exclusão
        await B.click('[data-act=novaCrianca]'); await B.fill('input[name=nome]','Leo'); await B.click('button[type=submit]'); await idle(B)
        await A.reload(); await idle(A); check(len((await st(A))['criancas'])==2,'Leo criado no B aparece no A')
        await pais(B); await B.click('[data-act=abaPais] >> text=Leo'); await B.click('[data-act=pedeApagar]'); await B.click('[data-act=apagarCrianca]'); await idle(B)
        await A.reload(); await idle(A); check([c['nome'] for c in (await st(A))['criancas']]==['Nina'],'Leo apagado no B some do A')
        # sair
        # sessão expirada: dados ficam, mas o app tranca até entrar de novo
        await A.evaluate("localStorage.removeItem('mock.tok');localStorage.removeItem('mock.user')"); await A.reload(); await idle(A)
        check(await A.locator('form[data-form=conta]').count()==1 and 'expirou' in await A.locator('[role=alert]').inner_text(),'sessão expirada tranca o app com aviso')
        check(len((await st(A))['criancas'])==1,'sessão expirada não apaga os dados do aparelho')
        await A.fill('input[name=senha]','12345678'); await A.click('button[type=submit]'); await idle(A)
        check(await A.locator('[data-act=comecar]').count()+await A.locator('.perfil').count()>0,'entrar de novo libera o app')
        # offline com sessão válida: criança continua praticando
        S.offline.add('A'); await A.reload(); await idle(A)
        check(await A.locator('form[data-form=conta]').count()==0,'sem internet, com sessão salva, o app abre normalmente')
        S.offline.discard('A')
        # assinatura: pendente dentro da tolerância, vencida, cancelada, vendas fechadas, admin
        await pais(A); t=await A.locator('main').inner_text(); check('Teste grátis até' in t,'área dos pais mostra a assinatura em teste')
        await A.click('[data-act=voltarCrianca]')
        uid=S.users['pai@x.com']['id']; hoje=datetime.datetime.now(datetime.timezone.utc)
        S.assin[uid]={'status':'past_due','preco_centavos':4990,'periodo_fim':(hoje-datetime.timedelta(days=2)).isoformat(),'cancelar_no_fim':False,'ja_teve_teste':True}
        await A.reload(); await idle(A); check(await A.locator('form[data-form=conta]').count()==0 and await A.locator('[data-act=assinar]').count()==0,'pagamento pendente há 2 dias: acesso mantido')
        S.assin[uid]['periodo_fim']=(hoje-datetime.timedelta(days=15)).isoformat()
        await A.reload(); await idle(A); t=await A.locator('main').inner_text()
        check('Pagamento pendente' in t and await A.locator('[data-act=portal]').count()==1,'pendente há 15 dias: bloqueia e oferece atualizar o cartão')
        S.assin[uid]['status']='canceled'
        await A.reload(); await idle(A); t=await A.locator('main').inner_text()
        check('Sua assinatura terminou' in t and 'grátis' not in t,'assinatura encerrada: oferece assinar de novo, sem novo teste grátis')
        S.config['vendas_abertas']=False; await A.reload(); await idle(A)
        check('em breve' in await A.locator('main').inner_text(),'vendas fechadas: aviso de em breve')
        S.admins.add(uid); await A.reload(); await idle(A)
        check(await A.locator('[data-act=assinar]').count()==0 and await A.locator('form[data-form=conta]').count()==0,'administrador entra sem assinatura')
        await pais(A); await A.click('[data-act=abrirAdmin]'); await idle(A,600)
        await A.screenshot(path='/home/claude/pingo/test/v4_admin.png',full_page=True)
        await A.fill('input[name=preco]','39,90'); await A.fill('input[name=dias]','14'); await A.check('input[name=abertas]'); await A.click('form[data-form=admin] button[type=submit]'); await idle(A,600)
        check(S.config['preco_centavos']==3990 and S.config['dias_teste']==14 and S.config['vendas_abertas'],'admin salva R$ 39,90, 14 dias e abre as vendas')
        check('Salvo' in await A.locator('[role=alert]').inner_text(),'admin vê confirmação')
        await A.fill('input[name=preco]','abc'); await A.click('form[data-form=admin] button[type=submit]'); await idle(A,300)
        check('inválido' in await A.locator('[role=alert]').inner_text() and S.config['preco_centavos']==3990,'preço inválido é recusado no app')
        # usuários: lista e liga/desliga
        S.users['avo@x.com']={'id':'u99','senha':'x'}; outro='u99'
        await A.click('[data-act=voltarPais]'); await A.click('[data-act=abrirAdmin]'); await idle(A,600)
        t=await A.locator('#titUsu >> xpath=..').inner_text()
        check('Ativos (1)' in t and 'pai@x.com' in t and 'Administrador' in t,'admin vê a lista de usuários ativos')
        await A.click('[data-act=adminFiltro][data-f=todos]'); await idle(A,200)
        sw=A.locator(f'[data-act=adminAcesso][data-id={outro}]')
        check(await sw.get_attribute('aria-checked')=='false','lista completa mostra quem está sem acesso')
        await sw.click(); await idle(A,400)
        check(S.assin[outro].get('cortesia') and await sw.get_attribute('aria-checked')=='true' and 'Cortesia' in await A.locator('#titUsu >> xpath=..').inner_text(),'ligar dá cortesia')
        await A.screenshot(path='/home/claude/pingo/test/v5_usuarios.png',full_page=True)
        await sw.click(); await idle(A,400)
        check(not S.assin[outro].get('cortesia') and await sw.get_attribute('aria-checked')=='false','desligar tira a cortesia')
        S.assin[outro]={'status':'active','preco_centavos':4990,'periodo_fim':(hoje+datetime.timedelta(days=20)).isoformat()}
        await A.click('[data-act=voltarPais]'); await A.click('[data-act=abrirAdmin]'); await idle(A,600); await A.click('[data-act=adminFiltro][data-f=todos]')
        await A.click(f'[data-act=adminAcesso][data-id={outro}]'); await idle(A,200)
        check(not S.assin[outro].get('bloqueado') and 'Stripe' in await A.locator('.confirma').inner_text(),'bloquear quem paga pede confirmação')
        await A.click('.confirma [data-ok]'); await idle(A,400)
        check(S.assin[outro].get('bloqueado') and 'Stripe' in await A.locator('[role=alert]').first.inner_text(),'bloqueio de pagante confirmado, com aviso da cobrança')
        S.assin.pop(outro,None); S.users.pop('avo@x.com')
        await A.click('[data-act=voltarPais]'); await A.click('[data-act=voltarCrianca]')
        S.admins.discard(uid); S.assin[uid]={'status':'active','preco_centavos':4990,'periodo_fim':(hoje+datetime.timedelta(days=20)).isoformat(),'cancelar_no_fim':False,'ja_teve_teste':True}
        await A.reload(); await idle(A)
        # conta antiga sem aceite registrado: tela de aceite antes de tudo
        S.termos.pop(uid,None); await A.reload(); await idle(A)
        check(await A.locator('form[data-form=aceite]').count()==1 and 'Antes de continuar' in await A.locator('main').inner_text(),'conta sem aceite vê a tela de autorização')
        await A.screenshot(path='/home/claude/pingo/test/v6_aceite.png',full_page=True)
        await A.click('form[data-form=aceite] button[type=submit]'); await idle(A,300)
        check('autorização' in await A.locator('[role=alert]').inner_text() and S.termos.get(uid) is None,'sem marcar, não passa')
        await A.check('form[data-form=aceite] input[name=ok]'); await A.click('form[data-form=aceite] button[type=submit]'); await idle(A)
        check(await A.locator('form[data-form=aceite]').count()==0 and S.consents[-1][2]=='aceite','aceite registrado e app liberado')
        S.termos[uid]='2020-01-01'; await A.reload(); await idle(A)
        check('Atualizamos os termos' in await A.locator('main').inner_text(),'versão nova dos termos pede novo aceite')
        await A.check('form[data-form=aceite] input[name=ok]'); await A.click('form[data-form=aceite] button[type=submit]'); await idle(A)
        # logoff pelo topo da área dos pais
        await pais(A); await A.click('[data-act=pedeSair] >> nth=0'); await A.screenshot(path='/home/claude/pingo/test/v3_sair.png')
        await A.click('[data-act=sairConta]'); await idle(A,800)
        check((await st(A))['criancas']==[] and len(S.cri)==1,'sair limpa o aparelho e mantém a nuvem')
        check(await A.locator('form[data-form=conta]').count()==1 and 'saiu' in await A.locator('[role=alert]').inner_text(),'depois de sair: tela de login com aviso')
        await A.reload(); await idle(A,500)
        check(await A.locator('[data-act=comecar]').count()==0 and await A.locator('.perfil').count()==0,'depois de sair, recarregar não dá acesso')
        # excluir conta
        await B.click('[data-act=pedeExcluir]'); await B.screenshot(path='/home/claude/pingo/test/v2_excluir.png',full_page=True); await B.click('[data-act=excluirConta]'); await idle(B,500)
        check(len(S.cri)==0 and len(S.lic)==0 and not S.users,'excluir conta apaga tudo no servidor')
        check(await B.locator('form[data-form=conta]').count()==1,'B volta para a tela de login')
        print('erros JS:',errs)
        await br.close()
asyncio.run(main())
