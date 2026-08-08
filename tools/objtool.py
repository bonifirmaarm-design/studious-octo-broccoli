import numpy as np
from collections import defaultdict

def read_obj(path):
    V=[]; VT=[]; VN=[]; F=[]   # F: list of (vidx, vtidx, vnidx) triples, 0-based, -1 if missing
    mtllib=None; usemtl=None; oname=None
    for line in open(path, 'r', errors='ignore'):
        if not line or line[0]=='#': continue
        p=line.split()
        if not p: continue
        t=p[0]
        if t=='v': V.append([float(x) for x in p[1:4]])
        elif t=='vt': VT.append([float(x) for x in p[1:3]])
        elif t=='vn': VN.append([float(x) for x in p[1:4]])
        elif t=='f':
            corners=[]
            for tok in p[1:]:
                a=tok.split('/')
                vi=int(a[0])-1
                ti=int(a[1])-1 if len(a)>1 and a[1] else -1
                ni=int(a[2])-1 if len(a)>2 and a[2] else -1
                corners.append((vi,ti,ni))
            for k in range(1,len(corners)-1):
                F.append((corners[0],corners[k],corners[k+1]))
        elif t=='mtllib': mtllib=p[1]
        elif t=='usemtl': usemtl=p[1]
        elif t=='o': oname=p[1]
    return (np.array(V,dtype=np.float64), np.array(VT,dtype=np.float64) if VT else None,
            np.array(VN,dtype=np.float64) if VN else None, np.array(F,dtype=np.int64),
            mtllib, usemtl, oname)

def write_obj(path, V, VT, F, mtllib='output.mtl', usemtl='Material', oname='mesh'):
    with open(path,'w') as f:
        f.write('# cleaned mesh\n')
        if mtllib: f.write(f'mtllib {mtllib}\n')
        f.write(f'o {oname}\n')
        for v in V: f.write(f'v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')
        if VT is not None:
            for t in VT: f.write(f'vt {t[0]:.6f} {t[1]:.6f}\n')
        if usemtl: f.write(f'usemtl {usemtl}\n')
        f.write('s 1\n')
        for tri in F:
            if VT is not None:
                f.write('f ' + ' '.join(f'{a+1}/{b+1}' for a,b,_ in tri) + '\n')
            else:
                f.write('f ' + ' '.join(f'{a+1}' for a,_,_ in tri) + '\n')

def weld(V, F, decimals=6):
    key = np.round(V, decimals)
    U, inv = np.unique(key, axis=0, return_inverse=True)
    Fw = inv[F[:,:,0]]
    return U, inv, Fw

def boundary_loops(Fw):
    cnt = defaultdict(int); pair = defaultdict(list)
    for tri in Fw:
        for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):
            k=(min(a,b),max(a,b)); cnt[k]+=1
    adj=defaultdict(list)
    for (a,b),c in cnt.items():
        if c==1:
            adj[a].append(b); adj[b].append(a)
    seen=set(); loops=[]
    for s in list(adj):
        if s in seen: continue
        loop=[s]; seen.add(s); cur=s; prev=None
        while True:
            nx=None
            for c in adj[cur]:
                if c!=prev and c not in seen: nx=c; break
            if nx is None: break
            loop.append(nx); seen.add(nx); prev=cur; cur=nx
        if len(loop)>=3: loops.append(loop)
    return loops
