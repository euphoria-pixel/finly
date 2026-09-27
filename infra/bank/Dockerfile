FROM python:3.11-slim
WORKDIR /opt/bank
COPY upstream/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . .
CMD ["python", "launch.py"]
