import json, numpy as np
from scipy import ndimage
from sklearn.neural_network import MLPClassifier
rng=np.random.default_rng(0)
X=[];y=[]
for d in range(10):
    raw=np.array(json.load(open(f'node_modules/mnist/src/digits/{d}.json'))['data'],dtype=np.float32)
    n=len(raw)//784; X.append(raw[:n*784].reshape(n,28,28)); y+= [d]*n
X=np.concatenate(X); y=np.array(y); print(X.shape)
def recenter(img):
    # mimic app preprocessing: crop bbox, scale longest side to 20, center of mass at 14,14
    ys,xs=np.nonzero(img>0.05)
    if len(ys)==0: return img
    c=img[ys.min():ys.max()+1, xs.min():xs.max()+1]
    h,w=c.shape; s=20/max(h,w)
    c=ndimage.zoom(c,s,order=1); c=np.clip(c,0,1)
    out=np.zeros((28,28),np.float32); h,w=c.shape
    oy=(28-h)//2; ox=(28-w)//2; out[oy:oy+h,ox:ox+w]=c
    cy,cx=ndimage.center_of_mass(out)
    return np.clip(ndimage.shift(out,(14-cy,14-cx),order=1),0,1)
def aug(img):
    a=rng.uniform(-14,14); sc=rng.uniform(0.8,1.15); sx=rng.uniform(0.75,1.25)
    t=np.deg2rad(a); M=np.array([[np.cos(t),-np.sin(t)],[np.sin(t),np.cos(t)]])@np.diag([1/sc,1/(sc*sx)])
    c=np.array([14,14]); off=c-M@c
    o=ndimage.affine_transform(img,M,offset=off,order=1)
    r=rng.random()
    if r<0.3: o=ndimage.grey_dilation(o,size=(2,2))
    elif r<0.45: o=ndimage.grey_erosion(o,size=(2,2))
    return recenter(np.clip(o,0,1))
idx=rng.permutation(len(X)); X=X[idx]; y=y[idx]
nt=int(len(X)*0.9)
Xtr=[recenter(i) for i in X[:nt]]; ytr=list(y[:nt])
for k in range(4):
    Xtr+= [aug(i) for i in X[:nt]]; ytr+=list(y[:nt])
Xtr=np.array(Xtr).reshape(len(Xtr),-1); ytr=np.array(ytr)
# algarismos no estilo brasileiro (1 com tracinho e base, 7 cortado, 4 fechado), rasterizados pelo próprio app
S=np.load('sint_treino.npz'); Xs,ys=S['X'],S['y']
Xtr=np.concatenate([Xtr]+[Xs]*3); ytr=np.concatenate([ytr]+[ys]*3)
print('treino', Xtr.shape)
Xte=np.array([recenter(i) for i in X[nt:]]).reshape(-1,784); yte=y[nt:]
Xte_aug=np.array([aug(i) for i in X[nt:]]).reshape(-1,784)
clf=MLPClassifier(hidden_layer_sizes=(160,),alpha=1e-4,batch_size=256,max_iter=30,early_stopping=False,random_state=0,verbose=False)
clf.fit(Xtr,ytr)
print('test',clf.score(Xte,yte),'test_aug',clf.score(Xte_aug,yte))
T=np.load('sint_teste.npz'); print('sinteticos BR', clf.score(T['X'],T['y']))
W1,W2=clf.coefs_; b1,b2=clf.intercepts_
def q(a):
    s=np.abs(a).max()/127; return np.round(a/s).astype(np.int8),float(s)
import base64
q1,s1=q(W1); q2,s2=q(W2)
model={'w1':base64.b64encode(q1.tobytes()).decode(),'s1':s1,'b1':b1.round(5).tolist(),'w2':base64.b64encode(q2.tobytes()).decode(),'s2':s2,'b2':b2.round(5).tolist(),'h':160}
json.dump(model,open('model_v2.json','w'))
# quantized accuracy
h=np.maximum(0,Xte@(q1*s1)+b1); p=(h@(q2*s2)+b2).argmax(1); print('quant',(p==yte).mean())
hs=np.maximum(0,T['X']@(q1*s1)+b1); ps=(hs@(q2*s2)+b2).argmax(1); print('quant BR',(ps==T['y']).mean(), [round(float((ps[T['y']==k]==k).mean()),3) for k in range(10)])
