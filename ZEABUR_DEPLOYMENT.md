# Zeabur 部署指南

本文档说明如何将 Polymarket 做市策略部署到 Zeabur。

## 为什么选择 Zeabur？

- ✅ 网络稳定（美国服务器，靠近 Polymarket）
- ✅ 24/7 运行
- ✅ 免费额度足够
- ✅ 支持环境变量配置
- ✅ 实时日志查看

## 部署步骤

### 1. 准备 GitHub 仓库

✅ **已完成！** 代码已推送到：
```
https://github.com/iammadma-cryinggun/poly_btc_update
```

### 2. 注册 Zeabur

1. 访问：https://zeabur.com
2. 使用 GitHub 账号登录
3. 授权 Zeabur 访问你的仓库

### 3. 创建新项目

1. 登录 Zeabur 后，点击 **"New Project"**
2. 选择 **"Deploy from GitHub"**
3. 找到并选择 `poly_btc_update` 仓库
4. 选择 `main` 分支

### 4. 配置服务

#### 基础配置

```
Service Type: Python
Project Path: (自动检测)
Build Command: (留空，使用默认)
Start Command: python run_market_making_safe.py
```

#### 环境变量

在 **Environment Variables** 部分添加：

```bash
POLYMARKET_PK=0x876d0b340ce80ede52a8a80dc281f981f07f2132948588bc696c787b228c9fb0
POLYMARKET_FUNDER=0x886236898293c1d7d40c7722b60ecfb76c7b68d0
POLYMARKET_API_KEY=35a22cbd-1cc9-82ff-c9d9-848ba2e0d2a9
POLYMARKET_API_SECRET=iIzM2Z1GoZKWk9rCW9rqJihPoSwRGmG2Zwybzsk6Ve8=
POLYMARKET_PASSPHRASE=ee7658afaf75e3e4cbee1feecb331285dde187daaafdbcfa1441415d5cfd42a8
SIGNATURE_TYPE=0
```

⚠️ **重要**：
- 不要在公开场合泄露这些密钥！
- Zeabur 的环境变量是加密存储的

### 5. 部署服务

1. 点击 **"Deploy"** 按钮
2. 等待构建完成（大约 2-3 分钟）
3. 部署成功后，服务会自动启动

### 6. 监控运行

#### 查看日志

在 Zeabur 控制台：
1. 点击你的服务
2. 选择 **"Logs"** 标签
3. 实时查看策略运行日志

#### 关键日志信息

正常启动应该看到：
```
[INFO] TradingNode 初始化成功
[INFO] MarketMakingStrategy: READY
[INFO] 正在获取市场信息...
[OK] Instrument ID: ...
[INFO] 策略已启动
```

#### 监控指标

关注这些信息：
- ✅ 订单是否成功提交
- ✅ 成交率（每分钟成交次数）
- ✅ 当前盈亏
- ⚠️ 是否有错误信息
- ⚠️ 网络连接状态

### 7. 管理服务

#### 停止服务

```
方法 1: 在 Zeabur 控制台点击 "Stop"
方法 2: 修改启动命令为不执行任何操作
```

#### 重启服务

```
点击 "Restart" 按钮
```

#### 更新代码

```bash
# 本地修改代码
git add .
git commit -m "Update strategy"
git push

# Zeabur 会自动检测到更新并重新部署
```

## 资源配置

### 推荐配置

```
CPU: 0.5 vCPU（免费额度）
RAM: 512 MB（免费额度）
磁盘: 1 GB（免费额度）
```

这个配置足够运行策略：
- Python 进程：~50 MB
- NautilusTrader：~100 MB
- 策略逻辑：~50 MB
- 缓冲：~300 MB

### 费用估算

免费额度：
- ✅ 每月 1000 小时运行时间
- ✅ 10 GB 网络流量
- ✅ 足够策略 24/7 运行

如果超出免费额度：
- 预计费用：$5-10/月

## 故障排除

### 问题 1: 部署失败

**症状**：构建过程报错

**解决方案**：
```bash
1. 检查 requirements.txt 是否完整
2. 确认 Python 版本兼容性（需要 3.10+）
3. 查看构建日志中的错误信息
```

### 问题 2: 策略无法连接

**症状**：日志显示网络超时

**解决方案**：
```bash
1. 检查环境变量是否正确配置
2. 确认私钥格式正确（0x 开头）
3. 重启服务
```

### 问题 3: 策略频繁崩溃

**症状**：日志显示异常退出

**解决方案**：
```bash
1. 查看完整错误日志
2. 检查参数配置是否合理
3. 确认账户余额充足
4. 考虑使用更保守的配置
```

### 问题 4: 内存不足

**症状**：OOM (Out of Memory) 错误

**解决方案**：
```bash
1. 增加服务内存配置（升级套餐）
2. 减少缓存和历史数据
3. 使用更小的更新间隔
```

## 安全建议

### 1. 密钥管理

- ✅ 使用 Zeabur 的环境变量
- ❌ 不要将 .env 文件提交到 Git
- ❌ 不要在日志中打印完整私钥

### 2. 访问控制

- 在 Zeabur 设置项目访问权限
- 只允许受信任的团队成员访问

### 3. 监控告警

建议设置告警：
- 服务停止
- 错误日志激增
- 资源使用超过 80%

## 优化建议

### 1. 日志管理

```python
# 在策略中设置合适的日志级别
logging_config = LoggingConfig(
    log_level="INFO",  # 生产环境使用 INFO
    log_colors=False,  # 远程环境禁用颜色
)
```

### 2. 性能优化

```python
# 降低更新频率以减少 CPU 使用
config = MarketMakingSafeConfig(
    update_interval_ms=5000,  # 5 秒更新
    ...
)
```

### 3. 资源监控

定期检查：
- CPU 使用率
- 内存使用量
- 网络流量
- 运行时间

## 备份策略

### 自动备份

Zeabur 不提供持久化存储，需要：

1. **定期导出日志**
   - 手动下载日志文件
   - 或设置日志转发到外部服务

2. **记录交易数据**
   - 策略内置日志记录
   - 定期导出到本地

### 手动备份

```bash
# 导出重要数据
1. Zeabur 控制台 → Logs → Download
2. 保存交易记录
3. 记录参数配置
```

## 下一步

部署成功后：

1. **运行 1-2 小时测试**
   - 观察策略表现
   - 检查是否有错误
   - 验证盈利情况

2. **根据表现调整**
   - 如果盈利：继续运行或加大资金
   - 如果亏损：调整参数或停止策略

3. **长期监控**
   - 每天检查日志
   - 记录盈亏情况
   - 定期优化参数

## 支持

遇到问题？

1. 查看 [Zeabur 文档](https://zeabur.com/docs)
2. 检查 [GitHub Issues](https://github.com/iammadma-cryinggun/poly_btc_update/issues)
3. 查看 NautilusTrader 文档

---

**最后更新**: 2026-01-28
**维护者**: Martin + Claude Code
