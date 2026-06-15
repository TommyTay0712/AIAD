FROM aiad-base:latest

WORKDIR /app

COPY app/ app/
COPY services/ services/

EXPOSE 8003

CMD ["python", "-m", "uvicorn", "services.analysis.main:app", "--host", "0.0.0.0", "--port", "8003"]
