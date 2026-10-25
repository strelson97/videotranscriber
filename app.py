"""
Транскрибатор видео по ссылке (YouTube, Instagram, TikTok, X и ещё ~1000 сайтов).
Ссылка -> скачивание аудио (yt-dlp) -> распознавание речи (Whisper) -> перевод на 40+ языков.

Запуск:  python app.py   ->  открыть http://localhost:5000
"""
import os
import shutil
import tempfile
import threading

import yt_dlp
from deep_translator import GoogleTranslator
import requests
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# Файл cookies.txt нужен для приватных/закрытых видео и для Instagram (экспорт из браузера)
COOKIES_FILE = os.environ.get("COOKIES_FILE", "cookies.txt")

LANGUAGES = {
    "ru": "Русский", "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch",
    "it": "Italiano", "pt": "Português", "zh-CN": "中文 (упрощённый)", "zh-TW": "中文 (традиционный)",
    "ja": "日本語", "ko": "한국어", "ar": "العربية", "hi": "हिन्दी", "tr": "Türkçe", "pl": "Polski",
    "uk": "Українська", "nl": "Nederlands", "sv": "Svenska", "no": "Norsk", "da": "Dansk",
    "fi": "Suomi", "cs": "Čeština", "el": "Ελληνικά", "iw": "עברית", "hu": "Magyar",
    "ro": "Română", "bg": "Български", "sr": "Српски", "hr": "Hrvatski", "sk": "Slovenčina",
    "id": "Bahasa Indonesia", "ms": "Bahasa Melayu", "th": "ไทย", "vi": "Tiếng Việt",
    "fa": "فارسی", "bn": "বাংলা", "ur": "اردو", "kk": "Қазақша", "uz": "Oʻzbekcha",
    "az": "Azərbaycanca", "ka": "ქართული", "hy": "Հայերեն",
}

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")


def download_audio(url, folder):
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info), info.get("title", "video")


def transcribe(path, size):
    """Распознавание через Groq (Whisper large-v3-turbo). Лимит файла ~25 МБ."""
    if not GROQ_KEY:
        raise RuntimeError("Не задан GROQ_API_KEY на сервере")
    if os.path.getsize(path) > 25 * 1024 * 1024:
        raise RuntimeError("Аудио больше 25 МБ — видео слишком длинное")
    with open(path, "rb") as f:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": "Bearer " + GROQ_KEY},
            files={"file": (os.path.basename(path), f)},
            data={"model": "whisper-large-v3-turbo", "response_format": "verbose_json"},
            timeout=600,
        )
    if r.status_code != 200:
        raise RuntimeError("Groq: " + r.text[:300])
    j = r.json()
    lines = [x["text"].strip() for x in j.get("segments", []) if x["text"].strip()]
    return lines or [j.get("text", "")], j.get("language", "auto")


def translate(lines, src, target):
    """Переводит пачками (лимит ~5000 символов на запрос)."""
    out, batch, size = [], [], 0
    tr = GoogleTranslator(source="auto", target=target)

    def flush():
        if batch:
            out.extend(tr.translate("\n".join(batch)).split("\n"))

    for line in lines:
        if size + len(line) > 4000:
            flush()
            batch, size = [], 0
        batch.append(line)
        size += len(line) + 1
    flush()
    return out


@app.post("/api/process")
def process():
    data = request.get_json(force=True)
    urls = [u.strip() for u in data.get("urls", []) if u.strip()]
    target = data.get("lang", "ru")
    size = data.get("model", "small")
    results = []
    for url in urls:
        folder = tempfile.mkdtemp()
        try:
            path, title = download_audio(url, folder)
            lines, lang = transcribe(path, size)
            translated = translate(lines, "auto", target)
            results.append({"url": url, "title": title, "detected": lang,
                            "original": "\n".join(lines), "translated": "\n".join(translated)})
        except Exception as e:  # показываем понятную ошибку по каждой ссылке
            results.append({"url": url, "error": str(e)})
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    return jsonify(results)


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Транскрибатор видео</title>
<style>
body{font:16px system-ui,sans-serif;max-width:900px;margin:30px auto;padding:0 16px;background:#f6f7f9;color:#222}
textarea,select,button{font:inherit;padding:10px;border-radius:8px;border:1px solid #ccc;width:100%;box-sizing:border-box}
textarea{height:110px}.row{display:flex;gap:10px;margin:10px 0}button{background:#2b6cff;color:#fff;border:0;cursor:pointer}
.card{background:#fff;border-radius:12px;padding:16px;margin:16px 0;box-shadow:0 1px 4px #0001}
pre{white-space:pre-wrap;background:#f0f2f5;padding:12px;border-radius:8px}small{color:#666}
</style></head><body>
<h1>🎬 Транскрибатор видео</h1>
<textarea id="urls" placeholder="Вставьте ссылки на YouTube / Instagram / TikTok — по одной на строку"></textarea>
<div class="row">
<select id="lang">{% for c,n in langs.items() %}<option value="{{c}}">{{n}}</option>{% endfor %}</select>
<select id="model"><option value="base">Быстро (base)</option><option value="small" selected>Баланс (small)</option>
<option value="medium">Точно (medium)</option><option value="large-v3">Максимум (large-v3)</option></select></div>
<button id="go">Транскрибировать и перевести</button>
<p><small>Язык видео определяется автоматически. Перевод — на выбранный язык.</small></p>
<div id="out"></div>
<script>
const out=document.getElementById('out'),go=document.getElementById('go');
function dl(name,text){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/plain'}));a.download=name;a.click()}
go.onclick=async()=>{
  const urls=document.getElementById('urls').value.split('\\n').filter(x=>x.trim());
  if(!urls.length)return;
  go.disabled=true;go.textContent='Работаю… (длинные видео занимают время)';out.innerHTML='';
  try{
    const r=await fetch('/api/process',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({urls,lang:lang.value,model:model.value})});
    for(const x of await r.json()){
      const c=document.createElement('div');c.className='card';
      const h=document.createElement('h3');h.textContent=x.title||x.url;c.append(h);
      if(x.error){const p=document.createElement('p');p.textContent='Ошибка: '+x.error;c.append(p)}
      else{
        const s=document.createElement('small');s.textContent='Определён язык: '+x.detected;c.append(s);
        for(const [label,t] of [['Перевод',x.translated],['Оригинал',x.original]]){
          const b=document.createElement('b');b.textContent=label;const pre=document.createElement('pre');pre.textContent=t;
          const bt=document.createElement('button');bt.textContent='Скачать .txt';bt.style.width='auto';
          bt.onclick=()=>dl(label+'.txt',t);c.append(document.createElement('br'),b,pre,bt);
        }
      }
      out.append(c);
    }
  }catch(e){out.textContent='Ошибка: '+e}
  go.disabled=false;go.textContent='Транскрибировать и перевести';
};
</script></body></html>"""


@app.get("/")
def index():
    return render_template_string(PAGE, langs=LANGUAGES)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
