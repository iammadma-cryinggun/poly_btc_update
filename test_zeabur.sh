#!/bin/bash
# Zeabur 环境测试脚本
# 运行: bash test_zeabur.sh

echo "=========================================="
echo "Zeabur 环境测试"
echo "=========================================="

echo ""
echo "[1] 检查工作目录:"
pwd

echo ""
echo "[2] 检查 Git commit:"
cd /app 2>/dev/null && git log --oneline -1 2>/dev/null || echo "  不是 Git 目录或 /app 不存在"

echo ""
echo "[3] 检查关键文件:"
ls -la /app/patches/ 2>/dev/null || echo "  patches 目录不存在"
ls -la /app/run_15m_market.py 2>/dev/null || echo "  run_15m_market.py 不存在"
ls -la /app/.env 2>/dev/null || echo "  .env 不存在"

echo ""
echo "[4] 检查 run_15m_market.py 第 26 行（导入语句）:"
sed -n '26p' /app/run_15m_market.py 2>/dev/null || echo "  无法读取"

echo ""
echo "[5] 检查环境变量:"
env | grep POLYMARKET || echo "  没有 POLYMARKET 环境变量"

echo ""
echo "[6] 检查 Python 版本:"
python --version

echo ""
echo "[7] 测试补丁加载（3秒超时）:"
timeout 3 python -c "import sys; sys.path.insert(0, '/app'); import patches; print('  补丁加载成功')" 2>&1 || echo "  补丁加载失败或超时"

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
