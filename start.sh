#!/bin/bash
set -x  # 启用调试模式，打印每个命令

echo "========================================"
echo "Starting Polymarket Bot"
echo "========================================"

# 检查环境变量
echo "[INFO] Checking environment variables..."
if [ -z "$POLYMARKET_PK" ]; then
    echo "[ERROR] POLYMARKET_PK is not set!"
    echo "[ERROR] Please set POLYMARKET_PK in Zeabur environment variables"
    exit 1
fi

echo "[OK] POLYMARKET_PK is set: ${POLYMARKET_PK:0:10}...${POLYMARKET_PK: -6}"

# 显示Python版本
echo "[INFO] Python version:"
python --version

# 显示工作目录
echo "[INFO] Working directory:"
pwd

# 列出文件
echo "[INFO] Files in /app:"
ls -la /app

# 检查requirements.txt
echo "[INFO] Checking requirements.txt:"
head -20 /app/requirements.txt

# 检查主脚本是否存在
if [ ! -f "/app/run_15m_market.py" ]; then
    echo "[ERROR] run_15m_market.py not found!"
    exit 1
fi

echo "[OK] run_15m_market.py found"

# 启动Python程序（使用unbuffered模式）
echo "[INFO] Starting Python program..."
echo "========================================"

# 使用python -u确保输出不被缓冲
python -u /app/run_15m_market.py 2>&1

EXIT_CODE=$?

echo "========================================"
echo "[INFO] Python program exited with code: $EXIT_CODE"
echo "========================================"

# 如果程序异常退出，保持容器运行一段时间以便查看日志
if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] Program failed. Keeping container alive for 60 seconds for debugging..."
    sleep 60
fi

exit $EXIT_CODE
