import json,random,time,urllib.request,threading,os
K=open(os.path.expanduser("~/NewModels/DS4.1/state-tp4/api-key")).read().strip() if os.path.exists(os.path.expanduser("~/NewModels/DS4.1/state-tp4/api-key")) else ""
AUTH={"Authorization":"Bearer "+K} if K else {}
N,TOK=4,150000
res=[None]*N
def go(i):
    r=random.Random(5000+i)
    body={"model":"deepseek-v4.1-flash","prompt":[r.randrange(1000,120000) for _ in range(TOK)],"max_tokens":256,"temperature":1.0,"stream":True}
    req=urllib.request.Request("http://10.10.10.12:8888/v1/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json",**AUTH})
    t=time.time(); first=None; n=0
    try:
        with urllib.request.urlopen(req,timeout=3000) as resp:
            for line in resp:
                if line.startswith(b"data: {"):
                    n+=1
                    if first is None: first=time.time()-t
        res[i]=dict(ok=True,ttft=first,total=time.time()-t,chunks=n)
    except Exception as e: res[i]=dict(ok=False,err=repr(e)[:200],total=time.time()-t)
t0=time.time(); ts=[threading.Thread(target=go,args=(i,)) for i in range(N)]
[t.start() for t in ts]; [t.join() for t in ts]; wall=time.time()-t0
ok=[r for r in res if r and r['ok']]
print(json.dumps(dict(requests=N,prompt_tokens_each=TOK,succeeded=len(ok),wall_s=round(wall,1),aggregate_prefill_tok_s=round(N*TOK/max(r['ttft'] for r in ok)) if ok else None,
  ttft_s=[round(r['ttft'],1) for r in ok],total_s=[round(r['total'],1) for r in ok],failures=[r for r in res if r and not r['ok']])))
