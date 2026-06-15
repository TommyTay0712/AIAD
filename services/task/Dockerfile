FROM aiad-base:latest

WORKDIR /app

COPY app/ app/
COPY services/ services/

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "services.task.main:app", "--host", "0.0.0.0", "--port", "8001"]
