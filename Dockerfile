FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# 启动15分钟市场策略（基于论文优化）
# 将所有输出重定向到文件和stderr，确保日志被捕获
CMD ["sh", "-c", "python -u run_15m_market.py > /tmp/app.log 2>&1 && cat /tmp/app.log"]
