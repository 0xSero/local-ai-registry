import zlib,struct,base64,json,urllib.request
W,H=96,64
def px(x,y): return (220,30,30) if x<W//2 else (30,60,220)
raw=b"".join(b"\x00"+bytes(c for x in range(W) for c in px(x,y)) for y in range(H))
def chunk(t,d): return struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
png=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",W,H,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b"")
body={"model":"deepseek-v4.1-flash","temperature":0,"messages":[{"role":"user","content":[
 {"type":"image_url","image_url":{"url":"data:image/png;base64,"+base64.b64encode(png).decode()}},
 {"type":"text","text":"What two colors are in this image, left half and right half? Answer in one short sentence."}]}]}
r=urllib.request.urlopen(urllib.request.Request("http://10.10.10.12:8888/v1/chat/completions",json.dumps(body).encode(),{"Content-Type":"application/json"}),timeout=300)
j=json.load(r); m=j["choices"][0]["message"]; print((m.get("content") or "")[-300:]); print(j["usage"])
