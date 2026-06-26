FROM python:3.12-slim

WORKDIR /app
COPY app.py /app/app.py
COPY static /app/static

ENV PAINTRACKER_HOST=0.0.0.0
ENV PAINTRACKER_PORT=8080
ENV PAINTRACKER_DATA_DIR=/data

EXPOSE 8080
VOLUME ["/data"]

CMD ["python", "app.py"]
