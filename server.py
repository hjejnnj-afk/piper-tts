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
    def num(k, padrao):
        try:
            return str(float(data.get(k, padrao)))
        except (TypeError, ValueError):
            return str(padrao)

    # ajustes de naturalidade (todos opcionais; o n8n pode sobrescrever)
    extras = ["--length-scale", num("length_scale", 1.1),
              "--noise-scale", num("noise_scale", 0.75),
              "--noise-w-scale", num("noise_w_scale", 0.9),
              "--sentence-silence", num("sentence_silence", 0.35)]
    with tempfile.TemporaryDirectory() as d:
        wav, ogg = os.path.join(d, "a.wav"), os.path.join(d, "a.ogg")
        base = ["python3", "-m", "piper", "-m", VOICE, "--data-dir", VOICE_DIR, "-f", wav]
        p = subprocess.run(base + extras, input=text.encode("utf-8"),
                           capture_output=True, timeout=40)
        if p.returncode != 0 or not os.path.exists(wav):
            # se alguma flag não existir nessa versão, tenta só com o ritmo
            p = subprocess.run(base + ["--length-scale", num("length_scale", 1.1)],
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
