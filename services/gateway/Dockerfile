FROM aiad-base:latest

WORKDIR /app

COPY app/ app/
COPY services/ services/

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "services.gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
