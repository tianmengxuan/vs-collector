FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 创建数据目录
RUN mkdir -p data logs

# 暴露端口
EXPOSE 8866 5000

# 启动命令
CMD ["python", "main.py"]
