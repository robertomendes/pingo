# Gera ../index.html a partir de src/app.html, embutindo o modelo de dígitos.
import os
base = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(base, 'src', 'app.html')).read()
m = open(os.path.join(base, 'model.json')).read()
assert '__MODEL__' in s
open(os.path.join(base, '..', 'index.html'), 'w').write(s.replace('__MODEL__', m))
print('index.html gerado')
