FROM python:3.11-slim
WORKDIR /verify
COPY acceptance.py ./
# One-shot: run acceptance then exit; its exit code reports pass/fail.
ENTRYPOINT ["python", "/verify/acceptance.py"]
