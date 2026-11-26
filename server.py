import os, base64, json, re, subprocess, tempfile, urllib.request, urllib.error
from flask import Flask, request, jsonify

app = Flask(__name__)
VOICE = os.environ.get("VOICE", "pt_BR-faber-medium")      # Piper (reserva)
VOICE_DIR = os.environ.get("VOICE_DIR", "/app/voices")
TOKEN = os.environ.get("TTS_TOKEN", "")
MAX_CHARS = 600

# Gemini TTS (chave gratuita do Google AI Studio). Sem chave, usa só o Piper.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-tts-preview")
GEMINI_VOICE = os.environ.get("GEMINI_VOICE", "Achird")
GEMINI_STYLE = os.environ.get(
    "GEMINI_STYLE",
    "Diga em português do Brasil, de forma simpática, natural e descontraída, "
    "como um atendente conversando no WhatsApp, em ritmo normal: ")


def pcm_para_ogg(pcm: bytes, rate: int, pasta: str) -> bytes:
    raw, ogg = os.path.join(pasta, "a.pcm"), os.path.join(pasta, "a.ogg")
    open(raw, "wb").write(pcm)
    f = subprocess.run(
        ["ffmpeg", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", raw,
         "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1", ogg],
        capture_output=True, timeout=30)
    if f.returncode != 0:
        raise RuntimeError("ffmpeg: " + f.stderr.decode()[-300:])
    return open(ogg, "rb").read()


def gemini_ogg(text: str, voz: str, pasta: str) -> bytes:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": GEMINI_STYLE + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY})
    with urllib.request.urlopen(req, timeout=25) as r:
        resp = json.loads(r.read())
    inline = resp["candidates"][0]["content"]["parts"][0]["inlineData"]
    m = re.search(r"rate=(\d+)", inline.get("mimeType", ""))
    return pcm_para_ogg(base64.b64decode(inline["data"]), int(m.group(1)) if m else 24000, pasta)


def piper_ogg(text: str, data: dict, pasta: str) -> bytes:
    def num(k, padrao):
        try:
            return str(float(data.get(k, padrao)))
        except (TypeError, ValueError):
            return str(padrao)
    wav, ogg = os.path.join(pasta, "p.wav"), os.path.join(pasta, "p.ogg")
    base = ["python3", "-m", "piper", "-m", VOICE, "--data-dir", VOICE_DIR, "-f", wav]
    extras = ["--length-scale", num("length_scale", 1.1), "--noise-scale", num("noise_scale", 0.75),
              "--noise-w-scale", num("noise_w_scale", 0.9), "--sentence-silence", num("sentence_silence", 0.35)]
    p = subprocess.run(base + extras, input=text.encode(), capture_output=True, timeout=40)
    if p.returncode != 0 or not os.path.exists(wav):
        p = subprocess.run(base + ["--length-scale", num("length_scale", 1.1)],
                           input=text.encode(), capture_output=True, timeout=40)
    if p.returncode != 0 or not os.path.exists(wav):
        raise RuntimeError("piper: " + p.stderr.decode()[-300:])
    f = subprocess.run(["ffmpeg", "-y", "-i", wav, "-c:a", "libopus", "-b:a", "32k",
                        "-ar", "48000", "-ac", "1", ogg], capture_output=True, timeout=30)
    if f.returncode != 0:
        raise RuntimeError("ffmpeg: " + f.stderr.decode()[-300:])
    return open(ogg, "rb").read()


@app.get("/health")
def health():
    return {"ok": True, "gemini": bool(GEMINI_KEY), "gemini_voice": GEMINI_VOICE, "piper_voice": VOICE}


@app.post("/tts")
def tts():
    if TOKEN and request.headers.get("Authorization") != f"Bearer {TOKEN}":
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()[:MAX_CHARS]
    if not text:
        return jsonify(error="texto vazio"), 400
    engine = str(data.get("engine", "gemini" if GEMINI_KEY else "piper"))
    voz = str(data.get("voice", GEMINI_VOICE))
    erros = []
    with tempfile.TemporaryDirectory() as d:
        ogg = None
        if engine == "gemini" and GEMINI_KEY:
            try:
                ogg, usado = gemini_ogg(text, voz, d), "gemini"
            except Exception as e:                       # limite gratuito, rede, etc. -> cai para o Piper
                erros.append(f"gemini: {type(e).__name__}: {str(e)[:200]}")
        if ogg is None:
            try:
                ogg, usado = piper_ogg(text, data, d), "piper"
            except Exception as e:
                erros.append(str(e)[:300])
                return jsonify(error="falhou", detail=erros), 500
    return jsonify(audioContent=base64.b64encode(ogg).decode(), engine=usado, avisos=erros)
