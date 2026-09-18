"""Byte-exact parity of row_store v2 against the deployed v1 and the raw file, plus all-miss timing."""
import ctypes as C, json, os, struct, sys, threading, time, pathlib
import numpy as np
P, U = C.c_void_p, C.c_uint64
class Work(C.Structure): _fields_=[('store',P),('ids',P),('weights',P),('scales',P),('count',U)]
def load(path):
    lib=C.CDLL(path); lib.row_store_open.argtypes=[C.c_char_p,U,U,U,U]; lib.row_store_open.restype=P
    lib.row_store_range.argtypes=[P,U,U]; lib.row_store_lookup.argtypes=[P]; lib.row_store_close.argtypes=[P]
    lib.row_store_stats.argtypes=[P,C.POINTER(U)]; return lib
def meta(layer,name):
    path=pathlib.Path('/engram-fp4')/name
    with path.open('rb') as f:
        n=struct.unpack('<Q',f.read(8))[0]; h=json.loads(f.read(n))
    w,s=h[f'layers.{layer}.engram.embed.weight'],h[f'layers.{layer}.engram.embed.scale']
    return path,w['shape'][0],8+n+w['data_offsets'][0],8+n+s['data_offsets'][0]
def lookup(lib,store,ids):
    w=np.zeros((len(ids),128),np.uint8); s=np.zeros((len(ids),8),np.uint8)
    work=Work(store,ids.ctypes.data,w.ctypes.data,s.ctypes.data,len(ids))
    t=time.perf_counter(); lib.row_store_lookup(C.byref(work)); return w,s,time.perf_counter()-t
def stats(lib,store):
    out=(U*4)(); lib.row_store_stats(store,out); return list(out)
V1,V2='/opt/dsv41/adapter/librow_store.so','/w/librow_store_v2.so'
FILES=[(1,'model-00047-of-00048.safetensors'),(14,'model-00048-of-00048.safetensors')]
mode=sys.argv[1]
if mode=='parity':
    v1,v2=load(V1),load(V2); rng=np.random.default_rng(7)
    for layer,name in FILES:
        path,rows,wo,so=meta(layer,name); lo,hi=rows//4,rows//2
        raw=np.memmap(path,np.uint8,'r')
        for budget in (0, 8<<20):
            for scale3 in ('0','1'):
                os.environ['DSV41_NVME_SCALE3']=scale3
                a=v1.row_store_open(str(path).encode(),rows,wo,so,budget); b=v2.row_store_open(str(path).encode(),rows,wo,so,budget)
                assert a and b; v1.row_store_range(a,lo,hi); v2.row_store_range(b,lo,hi)
                for rounds in range(3):
                    ids=np.concatenate([rng.integers(lo,hi,40000),rng.integers(0,rows,8000),rng.integers(lo,lo+3000,12000)]).astype(np.int64)
                    rng.shuffle(ids)
                    if rounds==2: ids=prev            # replay: cache hits + conflict misses
                    prev=ids
                    w1,s1,_=lookup(v1,a,ids); w2,s2,_=lookup(v2,b,ids)
                    assert np.array_equal(w1,w2) and np.array_equal(s1,s2),(layer,budget,scale3,rounds)
                    own=(ids>=lo)&(ids<hi); pick=np.flatnonzero(own)[:4000]
                    for i in pick[:4000:40]:
                        r=int(ids[i]); assert np.array_equal(w2[i],raw[wo+r*128:wo+r*128+128]) and np.array_equal(s2[i],raw[so+r*8:so+r*8+8])
                    assert not w2[~own].any() and not s2[~own].any()
                # concurrent callers on one v2 store
                res={}
                def call(k):
                    q=np.random.default_rng(100+k).integers(lo,hi,20000).astype(np.int64); res[k]=(q,)+lookup(v2,b,q)[:2]
                ts=[threading.Thread(target=call,args=(k,)) for k in range(4)]; [t.start() for t in ts]; [t.join() for t in ts]
                for k,(q,w,s) in res.items():
                    e,f,_=lookup(v1,a,q); assert np.array_equal(w,e) and np.array_equal(s,f),('concurrent',k)
                print(f'parity ok layer={layer} budget={budget} nvme_scale3={scale3} v2stats(h,m,reads)={stats(v2,b)[:3]}',flush=True)
                v1.row_store_close(a); v2.row_store_close(b)
    print('PARITY PASSED')
else:  # bench <lib> <scale3>
    lib=load(V1 if sys.argv[2]=='v1' else V2); os.environ['DSV41_NVME_SCALE3']=sys.argv[3]
    path,rows,wo,so=meta(*FILES[0]); st=lib.row_store_open(str(path).encode(),rows,wo,so,0); lib.row_store_range(st,0,rows)
    rng=np.random.default_rng(int(time.time())); ts=[]
    for _ in range(4):
        ids=rng.integers(0,rows,12288).astype(np.int64); ts.append(lookup(lib,st,ids)[2])
    print(f"{sys.argv[2]} threads={os.environ.get('DSV41_IO_THREADS','-')} scale3={sys.argv[3]}: all-miss 12288 rows median {sorted(ts)[len(ts)//2]*1e3:.1f} ms  ({12288/sorted(ts)[len(ts)//2]/1e3:.0f}k rows/s)",flush=True)
