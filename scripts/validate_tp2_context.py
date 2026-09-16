import argparse
import base64
import json
import pathlib
import struct
import subprocess
import time
import urllib.request
import zlib

p = argparse.ArgumentParser()
p.add_argument('port', type=int)
p.add_argument('kind', choices=['vllm', 'llama'])
p.add_argument('output')
a = p.parse_args()
out = pathlib.Path(a.output)
out.mkdir(parents=True, exist_ok=True)
base = f'http://127.0.0.1:{a.port}'
results = {'engine': a.kind, 'configured_context': 262144, 'tests': {}}

def request(path, payload=None, timeout=60):
    req = urllib.request.Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return json.loads(body) if body else None

def save():
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')

def check(name, payload, expected=None, timeout=120):
    started = time.monotonic()
    try:
        r = request('/v1/chat/completions', {'model': model, 'temperature': 0, 'max_tokens': 96,
                    'chat_template_kwargs': {'enable_thinking': False}, **payload}, timeout)
        (out / (name + '.json')).write_text(json.dumps(r, indent=2) + '\n')
        msg = r['choices'][0]['message']
        answer = msg.get('content') or ''
        ok = expected.lower() in answer.lower() if expected else bool(msg.get('tool_calls'))
        results['tests'][name] = {'passed': ok, 'seconds': round(time.monotonic()-started, 2),
                                 'usage': r.get('usage'), 'finish_reason': r['choices'][0]['finish_reason'],
                                 'answer': answer, 'tool_calls': msg.get('tool_calls')}
    except Exception as e:
        results['tests'][name] = {'passed': False, 'error': str(e), 'seconds': round(time.monotonic()-started, 2)}
    save()
    print(name, json.dumps(results['tests'][name]), flush=True)

deadline = time.monotonic()+900
while True:
    try:
        request('/health', timeout=3)
        models = request('/v1/models')
        model = models['data'][0]['id']
        results['models'] = models
        break
    except Exception:
        if time.monotonic() > deadline:
            raise RuntimeError('startup deadline exceeded')
        time.sleep(5)

check('chat', {'messages': [{'role':'user','content':'Reply with exactly: READY_256K'}]}, 'READY_256K')
def chunk(kind, data):
    return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',128,128,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\0\0'*128)*128))+chunk(b'IEND',b'')
image = 'data:image/png;base64,' + base64.b64encode(png).decode()
check('vision', {'messages':[{'role':'user','content':[{'type':'text','text':'What single color fills this image? Answer one word.'},
            {'type':'image_url','image_url':{'url':image}}]}]}, 'red')
check('tools', {'messages':[{'role':'user','content':'Call get_weather for Paris.'}],
    'tools':[{'type':'function','function':{'name':'get_weather','description':'Get weather for a city',
        'parameters':{'type':'object','properties':{'city':{'type':'string'}},'required':['city']}}}], 'tool_choice':'auto'})
video = out / 'red.mp4'
subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=red:s=128x128:r=2:d=2','-pix_fmt','yuv420p',str(video)],check=True,timeout=30)
url = 'data:video/mp4;base64,'+base64.b64encode(video.read_bytes()).decode()
check('video', {'messages':[{'role':'user','content':[{'type':'text','text':'What single color fills the video? Answer one word.'},
    {'type':'video_url','video_url':{'url':url}}]}]}, 'red', timeout=180)

unit = 'alpha beta gamma delta epsilon zeta eta theta.\n'
prefix = 'Read the following archive.\n'
suffix = '\nThe archive is complete. Reply with exactly: CONTEXT_256K_OK'
def messages(n):
    return [{'role':'user','content': prefix + unit*n + suffix}]
def count(n):
    payload = {'model':model,'messages':messages(n),'chat_template_kwargs':{'enable_thinking':False}} if a.kind=='vllm' else {'content':messages(n)[0]['content']}
    r = request('/tokenize',payload,timeout=60)
    return r.get('count',len(r.get('tokens',[])))
n = 18000
for _ in range(4):
    actual = count(n)
    if 261000 <= actual <= 261700:
        break
    n = max(1,int(n*261500/actual))
results['tokenized_prompt'] = count(n)
save()
print('long_context_start',results['tokenized_prompt'],flush=True)
check('long_context',{'messages':messages(n),'max_tokens':64},'CONTEXT_256K_OK',timeout=2400)
t = results['tests']['long_context']
if t.get('passed'):
    t['passed'] = 261000 <= (t.get('usage') or {}).get('prompt_tokens',0) <= 262144
save()
