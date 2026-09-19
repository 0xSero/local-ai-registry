import json,random,time,urllib.request,sys,os
K=open(os.path.expanduser("~/NewModels/DS4.1/state-tp4/api-key")).read().strip() if os.path.exists(os.path.expanduser("~/NewModels/DS4.1/state-tp4/api-key")) else ""
AUTH={"Authorization":"Bearer "+K} if K else {}
n=int(sys.argv[1]); seed=int(sys.argv[2])
r=random.Random(seed)
body={"model":"deepseek-v4.1-flash","prompt":[r.randrange(1000,120000) for _ in range(n)],"max_tokens":8,"temperature":0}
req=urllib.request.Request("http://10.10.10.12:8888/v1/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json",**AUTH})
t=time.time()
try:
    out=json.loads(urllib.request.urlopen(req,timeout=3000).read()); dt=time.time()-t; u=out.get("usage",{})
    print(f"DEEP PREFILL OK: {n} cold tokens in {dt:.1f}s = {n/dt:.0f} tok/s | usage={u}")
except Exception as e:
    print("DEEP PREFILL FAILED after %.1fs: %r"%(time.time()-t,e)); 
    try: print(e.read()[:500])
    except Exception: pass
