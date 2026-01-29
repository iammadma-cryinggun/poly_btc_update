# Polymarket 做市策略

基于 NautilusTrader 的 Polymarket 做市策略实现。

## ⚡ 快速开始

### 1. 配置市场

```bash
python market_config_manager.py
```

选择"手动输入配置"，然后：
1. 访问 https://polymarket.com/event/bitcoin-up-or-down-on-january-29
2. 按 F12 打开开发者工具
3. 在 Console 中运行:
   ```javascript
   const m = __INITIAL_STATE__.markets.activeMarkets[0];
   console.log('conditionId:', m.conditionId);
   console.log('token_id:', m.clobTokenIds[0]);
   ```
4. 复制并粘贴到配置工具

### 2. 生成 API 凭证

```bash
python generate_api_credentials.py
```

### 3. 运行策略

```bash
python run_market_making_safe.py
```

**配置:**
- 资金需求: 5-10 USDC
- 日亏损限制: 1 USDC
- 订单大小: 1 token
- 运行时间: 建议 1-2 小时

## 📅 每天更新市场

### 自动滚动（推荐）

```bash
python market_config_manager.py --next-day
```

工具会自动生成下一天的市场 URL，您只需输入新市场的 token。

### 手动更新

```bash
python market_config_manager.py --manual
```

## 🛠️ 工具

### market_config_manager.py

市场配置管理工具。

```bash
# 交互式菜单
python market_config_manager.py

# 手动配置
python market_config_manager.py --manual

# 自动滚动到下一天
python market_config_manager.py --next-day

# 显示当前配置
python market_config_manager.py --show
```

### generate_api_credentials.py

生成 Polymarket API 凭证。

```bash
python generate_api_credentials.py
```

---

## 策略说明

### 核心思想
市场做市（Market Making）- 同时在买卖双方挂单，通过买卖价差赚取利润。

### 策略特性
- **方向中性**: 不预测市场涨跌
- **持续盈利**: 每笔交易都赚取价差
- **风险可控**: 多层风险检查
- **库存管理**: 自动维持中性仓位

## 配置参数

### 小资金安全配置
```python
订单大小: 1 token
最大库存: 5 tokens
基础价差: 5%
日亏损限制: -1 USDC
更新频率: 5 秒
```

### 标准配置
```python
订单大小: 2 tokens
最大库存: 20 tokens
基础价差: 3%
日亏损限制: -20 USDC
更新频率: 2 秒
```

## 风险控制

### 多重止损
1. **日亏损限制**: 达到限制自动停止
2. **最大库存**: 防止过度持仓
3. **价格限制**: 0.05-0.95 USDC
4. **波动率限制**: 市场异常时停止
5. **库存倾斜**: 持仓越多价格越不优

### 库存管理
```
目标库存: 0 tokens（中性）
持仓 > 0 → 降低买价，提高卖价（鼓励平仓）
持仓 < 0 → 提高买价，降低卖价（鼓励建仓）
```

## 部署到 Zeabur

### 推荐步骤

1. **推送到 GitHub**
```bash
cd D:/翻倍项目/polymarket_v2
git init
git add .
git commit -m "Initial commit: Market making strategy"
git remote add origin https://github.com/iammadma-cryinggun/poly_btc_update.git
git push -u origin main
```

2. **在 Zeabur 部署**
   - 创建新项目
   - 连接 GitHub 仓库
   - 配置环境变量（从 .env 复制）
   - 启动服务

3. **监控运行**
   - 查看实时日志
   - 观察策略表现
   - 必要时调整参数

## 注意事项

⚠️ **这是真实交易模式，会使用真实资金！**

- 建议先用小资金测试（5-10 USDC）
- 监控 1-2 小时观察策略表现
- 设置合理的止损限制
- 网络不稳定时建议部署到 Zeabur

## 常见问题

### Q: 为什么无法回测？
A: Polymarket 没有历史订单簿数据，只能实盘验证。

### Q: 最小资金需求是多少？
A: 建议 5-10 USDC 起步。

### Q: 策略是否盈利？
A: 需要实盘验证。理论计算可盈利，但实际情况未知。

### Q: 网络不稳定怎么办？
A: 建议部署到 Zeabur，网络更稳定。

### Q: 可以停掉策略吗？
A: 可以，按 Ctrl+C 停止，会自动平仓。

## 项目结构

```
polymarket_v2/
├── strategies/
│   └── market_making_strategy.py   # 做市策略核心逻辑
├── run_market_making_safe.py       # 小资金安全版 ⭐
├── run_market_making_complete.py   # 完整版
├── .env                            # 环境变量配置
└── README.md                       # 说明文档
```

## 技术架构

- **框架**: NautilusTrader 1.222.0
- **语言**: Python 3.14
- **交易所**: Polymarket CLOB
- **订单类型**: FOK 限价单

## 许可证

MIT License
