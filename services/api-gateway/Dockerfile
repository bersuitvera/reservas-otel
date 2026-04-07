FROM python:3.12-slim-bookworm

WORKDIR /app
COPY ../common/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ../common /app/common
COPY main.py /app/main.py

ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
