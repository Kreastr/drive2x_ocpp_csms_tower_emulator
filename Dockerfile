FROM python:3.12

RUN  mkdir /app
COPY requirements.txt /app

RUN pip install -r /app/requirements.txt

COPY *.py /app

WORKDIR /app

CMD uvicorn ocpp_server:app

