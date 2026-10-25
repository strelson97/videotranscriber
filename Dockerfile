FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV PORT=7860
EXPOSE 7860
CMD gunicorn app:app -b 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 1200
