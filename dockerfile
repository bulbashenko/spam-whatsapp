FROM python:3.12-slim

WORKDIR /app

COPY ./backend /app

COPY requirements.txt /app/

RUN pip install -r requirements.txt --no-deps

RUN pip install greenlet==3.0.3

ENV PYTHONPATH=/app:$PYTHONPATH

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]