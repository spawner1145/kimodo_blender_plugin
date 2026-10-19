"""Keyless web translation, following WeiLin-Comfyui-Tools' Alibaba/Youdao flow.

Reference: https://github.com/weilin9999/WeiLin-Comfyui-Tools/tree/main/app/server/translate
Uses only Python's standard library so Blender needs no pip installation.
Only explicit translation actions send text to the selected online service.
"""
from collections import OrderedDict
import http.cookiejar
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class TranslationError(RuntimeError):
    pass


def contains_chinese(text):
    return bool(re.search(r'[\u3400-\u9fff\U00020000-\U0002fa1f]', text))


class WebTranslator:
    def __init__(self, timeout=12):
        self.timeout = timeout
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._csrf = None
        self._csrf_time = 0
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def _json(self, url, data=None, headers=None):
        base = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        base.update(headers or {})
        with self._opener.open(urllib.request.Request(url, data=data, headers=base),
                               timeout=self.timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    def _alibaba(self, text, source='zh', target='en'):
        host = 'https://translate.alibaba.com'
        headers = {'Referer': host+'/', 'Origin': host,
                   'User-Agent': 'Mozilla/5.0'}
        if not self._csrf or time.monotonic()-self._csrf_time > 1200:
            with self._opener.open(urllib.request.Request(host, headers=headers),
                                   timeout=self.timeout) as r:
                r.read()
            self._json(host+'/api/translate/csrftoken', headers=headers)
            self._csrf = self._json(host+'/api/translate/csrftoken', headers=headers)
            if not isinstance(self._csrf, dict) or not self._csrf.get('headerName') or not self._csrf.get('token'):
                raise TranslationError('Alibaba: invalid session response')
            self._csrf_time = time.monotonic()
        boundary = '----Kimodo'+uuid.uuid4().hex
        fields = {'query': text, 'srcLang': source, 'tgtLang': target,
                  '_csrf': self._csrf['token'], 'domain': 'general'}
        parts = []
        for name, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n')
        data = (''.join(parts)+f'--{boundary}--\r\n').encode('utf-8')
        headers[self._csrf['headerName']] = self._csrf['token']
        headers['Content-Type'] = 'multipart/form-data; boundary='+boundary
        result = self._json(host+'/api/translate/text', data, headers)
        payload = result.get('data') if isinstance(result, dict) else None
        output = payload.get('translateText') if isinstance(payload, dict) else None
        if not isinstance(output, str) or not output.strip():
            self._csrf = None
            raise TranslationError('Alibaba: empty or invalid translation response')
        return html.unescape(output).strip()

    def _youdao(self, text, source='zh-CHS', target='en'):
        if len(text) > 1000:
            raise TranslationError('Youdao accepts at most 1000 characters per prompt')
        data = urllib.parse.urlencode({'q': text, 'from': source, 'to': target}).encode('utf-8')
        result = self._json('https://aidemo.youdao.com/trans', data,
                            {'Content-Type': 'application/x-www-form-urlencoded'})
        items = result.get('translation') if isinstance(result, dict) else None
        if (not isinstance(result, dict) or str(result.get('errorCode')) != '0'
                or not isinstance(items, list) or not items
                or not all(isinstance(item, str) for item in items)):
            raise TranslationError('Youdao: translation request rejected')
        return html.unescape('\n'.join(items)).strip()

    def translate(self, text, service='AUTO'):
        if not isinstance(text, str) or not text.strip():
            raise TranslationError('Prompt is empty')
        if not contains_chinese(text):
            return text
        if len(text) > 4900:
            raise TranslationError('Prompt exceeds 4900 characters')
        if service not in {'AUTO', 'ALIBABA', 'YOUDAO'}:
            raise TranslationError('Unknown translation service')
        key = (service, text)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            errors = []
            for name in (['ALIBABA', 'YOUDAO'] if service == 'AUTO' else [service]):
                try:
                    output = self._alibaba(text) if name == 'ALIBABA' else self._youdao(text)
                    if not output or contains_chinese(output):
                        raise TranslationError('Service returned untranslated Chinese text')
                    self._cache[key] = output
                    if len(self._cache) > 128:
                        self._cache.popitem(last=False)
                    return output
                except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                        KeyError, TypeError, TranslationError) as exc:
                    errors.append(f'{name}: {exc}')
                    if name == 'ALIBABA':
                        self._csrf = None
            raise TranslationError('; '.join(errors))


translator = WebTranslator()
