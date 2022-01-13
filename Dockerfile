FROM python:3-alpine

WORKDIR /app
RUN apk add --no-cache uwsgi-python3
COPY ./app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app/ .
ENV FLASK_APP=app2

USER nobody

CMD ["flask", "run", "--port=8000", "--host=0.0.0.0"]
# CMD ["uwsgi", "--http", "127.0.0.1:8000", "--wsgi-file", "app2.py", "--callable", "app"]
