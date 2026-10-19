"""Blender-independent HTTP client. Uses only the Python standard library."""
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

_lock = threading.RLock()
_session = None
_ready = False
_busy = False
_active_cancel = None
_status = 'Not started'
_models = [
    ('soma-fp32','Kimodo SOMA v1.2 · FP32','完整精度动作模型',0,100),
    ('soma-int8','Kimodo SOMA v1.2 · ConvRot INT8','本地 ConvRot INT8 W8A8 动作模型',0,200),
]
_model_history = [_models]  # Blender keeps references to dynamic EnumProperty strings.
_encoders = [('awq','AWQ LLM2Vec','近似替代编码器',0,100),
             ('nf4','NF4 LLM2Vec','原插件的预量化编码器',0,200),
             ('bf16','BF16 LLM2Vec','原始完整精度编码器',0,300)]
_encoder_history = [_encoders]
_server_info = {}
_options = {'model':'soma-fp32','steps':100,'cfg_text':2.0,'cfg_constraints':2.0,'post_processing':False}


def model_items(_self=None,_context=None):
    return _models


def encoder_items(_self=None,_context=None):
    return _encoders


def update_model_items():
    global _models,_encoders
    values = []
    for model in _server_info.get('models',[]):
        key = model['id']
        number = {'soma-fp32':100,'soma-int8':200}.get(key,1000+(zlib.crc32(key.encode()) & 0x3fffffff))
        label = model['label']+('（未下载）' if not model.get('available',True) else '')
        values.append((key,label,model.get('precision',''),0,number))
    if values:
        _models = values
        _model_history.append(values)
    values = []
    for encoder in _server_info.get('encoders',[]):
        key = encoder['id']
        number = {'awq':100,'nf4':200,'bf16':300}.get(key,1000+(zlib.crc32(key.encode()) & 0x3fffffff))
        label = encoder['label']+('（未下载）' if not encoder.get('available',True) else '')
        values.append((key,label,encoder.get('kind',''),0,number))
    if values:
        _encoders = values
        _encoder_history.append(values)


def server_info():
    return _server_info.copy()


def set_generation_options(**options):
    with _lock:
        _options.update(options)


class Session:
    def __init__(self,url,token=''):
        parsed = urllib.parse.urlsplit(url.strip())
        if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('服务地址须为 http://主机:端口 或 https://主机:端口')
        if parsed.username or parsed.password:
            raise ValueError('请使用 API Token 字段，不要在 URL 中填写密码')
        self.url = url.strip().rstrip('/')
        self.token = token
        # A LAN endpoint should not accidentally be routed through a system proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self,method,path,body=None,binary=False):
        headers = {'Accept':'application/json','User-Agent':'Kimodo-Blender-API/2.0'}
        if self.token:
            headers['Authorization'] = 'Bearer '+self.token
        data = None
        if body is not None:
            data = json.dumps(body,ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.url+path,data=data,headers=headers,method=method)
        try:
            with self.opener.open(req,timeout=15) as response:
                if binary:
                    return response.read()
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            detail = exc.read(8192).decode('utf-8',errors='replace')
            try:
                detail = json.loads(detail).get('detail',detail)
            except ValueError:
                pass
            raise RuntimeError(f'HTTP {exc.code}: {detail}') from None
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            raise RuntimeError('无法连接 Kimodo API：'+str(exc)) from None


def _wait(session,job,cancel,progress_callback,timeout=3600):
    deadline = time.monotonic()+timeout
    while job['state'] not in {'succeeded','failed','cancelled'}:
        if cancel.is_set():
            session.request('POST','/v1/jobs/'+job['id']+'/cancel')
            return False,'Cancelled by user'
        if time.monotonic()>deadline:
            session.request('POST','/v1/jobs/'+job['id']+'/cancel')
            return False,'等待生成超时，已请求取消任务'
        if progress_callback:
            progress_callback(f"{job.get('message','')} · {int(job.get('progress',0)*100)}%")
        cancel.wait(0.3)
        job = session.request('GET','/v1/jobs/'+job['id'])
    if cancel.is_set() or job['state']=='cancelled':
        return False,'Cancelled by user'
    if job['state']=='failed':
        return False,job.get('error') or '服务端生成失败'
    return True,job


def start(url,model_name,api_token='',encoder_name='awq',progress_callback=None):
    global _session,_ready,_status,_server_info,_active_cancel,_busy
    cancel = threading.Event()
    with _lock:
        if _busy:
            return False,'已有连接或生成任务正在执行'
        _busy = True
        _active_cancel = cancel
    try:
        session = Session(url,api_token)
        health = session.request('GET','/v1/health')
        if health.get('api_version')!=1:
            raise RuntimeError('服务端 API 版本不兼容')
        models = session.request('GET','/v1/models')
        encoders = session.request('GET','/v1/encoders')
        available = {m['id'] for m in models['models'] if m.get('available',True)}
        if model_name and any(m['id']==model_name for m in models['models']) and model_name not in available:
            raise RuntimeError('所选动作模型尚未下载，请先在服务端下载或配置其路径：'+model_name)
        selected = model_name if model_name in available else models['default_model']
        if selected not in available:
            raise RuntimeError('服务端未找到可用模型，请检查服务端 config.json 中的模型路径')
        available_encoders = {e['id'] for e in encoders['encoders'] if e.get('available',True)}
        if encoder_name and any(e['id']==encoder_name for e in encoders['encoders']) and encoder_name not in available_encoders:
            raise RuntimeError('所选文本编码器尚未下载，请先在服务端下载或配置其路径：'+encoder_name)
        selected_encoder = encoder_name if encoder_name in available_encoders else encoders['default_encoder']
        job = session.request('POST','/v1/models/load',{'model':selected,'encoder':selected_encoder})
        success,result = _wait(session,job,cancel,progress_callback,timeout=600)
        if not success:
            return False,result
        with _lock:
            if cancel.is_set():
                return False,'Cancelled by user'
            _session,_ready = session,True
            _server_info = {**health,**models,**encoders,'selected_model':selected,'selected_encoder':selected_encoder}
            _status = '已连接 API · 30 fps'
        return True,_status
    except Exception as exc:
        _ready = False
        return False,str(exc)
    finally:
        with _lock:
            if _active_cancel is cancel:
                _busy,_active_cancel = False,None


def stop():
    """Disconnect this client; the separately running service stays available."""
    global _session,_ready,_status
    request_cancel()
    with _lock:
        _session,_ready,_status = None,False,'Stopped'


def is_running():
    return _ready and _session is not None


def is_busy():
    return _busy


def get_status():
    return _status


def request_cancel():
    with _lock:
        if _active_cancel:
            _active_cancel.set()


def _generate(prompts,durations,seed,output_format,constraints_json=None,
              diffusion_steps=None,num_transition_frames=5,bvh_standard_tpose=True,
              progress_callback=None,seeds=None):
    global _busy,_active_cancel
    cancel = threading.Event()
    with _lock:
        if not is_running():
            return False,'请先连接 Kimodo API'
        if _busy:
            return False,'上一任务尚未结束'
        session,options = _session,_options.copy()
        _busy,_active_cancel = True,cancel
    path = None
    try:
        profile = next((p for p in _server_info.get('models',[]) if p['id']==options['model']),{})
        if constraints_json and profile.get('skeleton','SOMA')!='SOMA':
            raise ValueError('Blender 场景约束目前使用 SOMA 关节映射。切换至 SMPLX/G1 时请关闭场景约束；API 可直接接收对应骨架的约束。')
        body = {**options,'prompts':prompts,'durations':durations,
                'seed':seed if seed>=0 else 42,'seeds':seeds,
                'transition_frames':num_transition_frames,'output_format':output_format,
                'standard_tpose':bvh_standard_tpose,
                'constraints':json.loads(constraints_json) if constraints_json else []}
        if diffusion_steps is not None:
            body['steps'] = diffusion_steps
        job = session.request('POST','/v1/jobs',body)
        success,result = _wait(session,job,cancel,progress_callback)
        if not success:
            return False,result
        # Download bytes rather than using a filesystem path from the server.
        # This also supports a server on another computer.
        content = session.request('GET','/v1/jobs/'+result['id']+'/artifact',binary=True)
        if cancel.is_set():
            return False,'Cancelled by user'
        fd,path = tempfile.mkstemp(prefix='kimodo_api_',suffix='.'+output_format)
        with os.fdopen(fd,'wb') as f:
            f.write(content)
        return True,path
    except Exception as exc:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
        return False,str(exc)
    finally:
        with _lock:
            if _active_cancel is cancel:
                _busy,_active_cancel = False,None


def generate_motion(prompt,duration,seed,output_format,**kwargs):
    return _generate([prompt],[duration],seed,output_format,**kwargs)


def generate_motion_multi(prompts,durations,seed,output_format,**kwargs):
    return _generate(prompts,durations,seed,output_format,**kwargs)
