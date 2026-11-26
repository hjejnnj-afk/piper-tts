FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir piper-tts flask gunicorn
# baixa a voz durante o build (o servidor do EasyPanel tem acesso à internet)
RUN python3 -m piper.download_voices --data-dir /app/voices pt_BR-faber-medium
COPY server.py .
ENV VOICE=pt_BR-faber-medium
EXPOSE 5000
CMD ["gunicorn","-b","0.0.0.0:5000","-w","2","-t","60","server:app"]
