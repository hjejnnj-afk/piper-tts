import os, base64, subprocess, tempfile
from flask import Flask, request, jsonify

app = Flask(__name__)
VOICE = os.environ.get("VOICE", "pt_BR-faber-medium")
VOICE_DIR = os.environ.get("VOICE_DIR", "/app/voices")
TOKEN = os.environ.get("TTS_TOKEN", "")  # defina no EasyPanel
MAX_CHARS = 600


@app.get("/health")
def health():
    return {"ok": True, "voice": VOICE}


@app.post("/tts")
def tts():
    if TOKEN and request.headers.get("Authorization") != f"Bearer {TOKEN}":
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()[:MAX_CHARS]
    if not text:
        return jsonify(error="texto vazio"), 400
    length_scale = str(data.get("length_scale", 1.0))  # <1 = mais rápido
    with tempfile.TemporaryDirectory() as d:
        wav, ogg = os.path.join(d, "a.wav"), os.path.join(d, "a.ogg")
        p = subprocess.run(
            ["python3", "-m", "piper", "-m", VOICE, "--data-dir", VOICE_DIR,
             "--length-scale", length_scale, "-f", wav],
            input=text.encode("utf-8"), capture_output=True, timeout=40)
        if p.returncode != 0 or not os.path.exists(wav):
            return jsonify(error="piper", detail=p.stderr.decode()[-400:]), 500
        f = subprocess.run(
            ["ffmpeg", "-y", "-i", wav, "-c:a", "libopus", "-b:a", "32k",
             "-ar", "48000", "-ac", "1", ogg],
            capture_output=True, timeout=30)
        if f.returncode != 0:
            return jsonify(error="ffmpeg", detail=f.stderr.decode()[-400:]), 500
        audio = base64.b64encode(open(ogg, "rb").read()).decode()
    return jsonify(audioContent=audio)  # mesmo formato do Google: o nó seguinte não muda
