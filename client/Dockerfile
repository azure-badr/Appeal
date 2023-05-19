FROM python:3.11

RUN pip install hypercorn discord quart pymongo requests

COPY . .

EXPOSE 8080

CMD hypercorn main:app --bind 0.0.0.0:8080
