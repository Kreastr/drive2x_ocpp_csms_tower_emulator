FROM py312d2x:latest

RUN  mkdir /app
COPY requirements.txt /app

RUN pip install -r /app/requirements.txt

COPY . /app

WORKDIR /app

CMD python ocpp_server.py

