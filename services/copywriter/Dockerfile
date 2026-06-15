FROM aiad-base:latest

WORKDIR /app

COPY app/ app/
COPY services/ services/

EXPOSE 8004

CMD ["python", "-m", "uvicorn", "services.copywriter.main:app", "--host", "0.0.0.0", "--port", "8004"]
