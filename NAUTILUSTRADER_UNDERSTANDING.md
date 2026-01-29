# NautilusTrader + Polymarket 正确理解

## 核心架构理解

### NautilusTrader 提供的能力

```
┌─────────────────────────────────────────────────┐
│ NautilusTrader Framework                        │
│                                                 │
│ 1. PolymarketDataClient                         │
│    - 自动连接 Polymarket API                   │
│    - 获取订单簿、成交、价格                      │
│    - WebSocket 实时数据流                       │
│                                                 │
│ 2. PolymarketExecClient                         │
│    - 自动提交订单                                │
│    - 处理订单状态                                │
│    - 管理订单生命周期                            │
│                                                 │
│ 3. PolymarketInstrumentProvider                  │
│    - 自动加载市场列表                            │
│    - 管理 instrument 元数据                      │
│                                                 │
│ 4. Portfolio & BettingAccount                   │
│    - 专门为 Polymarket 设计                     │
│    - 自动计算二元期权盈亏                        │
│    - 管理仓位和风险                              │
│                                                 │
│ 5. TradingNode                                  │
│    - 整合所有组件                                │
│    - 协调数据流和订单流                          │
│    - 管理策略生命周期                            │
└─────────────────────────────────────────────────┘
```

### 我应该做什么

**✅ 正确的做法**：
1. 专注于策略逻辑（做市算法）
2. 提供正确的 instrument_id
3. 适应 Polymarket 的特殊性
4. 让框架处理其他一切

**❌ 错误的做法（我之前做的）**：
1. 重复获取市场数据
2. 创建复杂的配置工具
3. 手动处理框架已经处理的事情
4. 过度设计

---

## Polymarket 的特殊性

### 1. 每日到期市场

```
问题：每天都是新的市场
解决：提供简单的市场切换机制

不是问题：NautilusTrader 会自动处理
  - InstrumentProvider 自动加载市场
  - 只需提供正确的 condition_id 和 token_id
```

### 2. 二元期权结构

```
特殊性：YES/NO tokens，价格 0-1
框架支持：BettingAccount 自动处理
  - stake 计算
  - liability 计算
  - win/lose payoff
```

### 3. 数据获取

```
方法：Gamma API 或 WebSocket
框架自动处理：
  - PolymarketDataClient 连接 API
  - 自动获取订单簿
  - 自动订阅更新
```

---

## 正确的工作流程

### 步骤 1: 获取市场 Token（一次性）

使用旧项目的方法：
```python
# 方法 A: Gamma API（如果网络正常）
url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"
condition_id, token_id = get_market_info(slug)

# 方法 B: 浏览器提取（如果网络受限）
# 从 Polymarket 页面的 JavaScript 获取
```

### 步骤 2: 配置环境变量（一次性）

```env
# .env 文件
POLYMARKET_PK=0x...

# 或者直接在代码中硬编码（不推荐）
```

### 步骤 3: 启动策略（每天）

```python
# 策略自动处理：
# 1. NautilusTrader 加载 instrument
# 2. DataClient 连接市场
# 3. 策略接收订单簿更新
# 4. 策略提交订单
# 5. ExecClient 执行订单
# 6. Portfolio 计算盈亏
```

---

## 真正的自洽设计

### 配置层（一次性）

```python
# 配置文件 market_config.json
{
  "slug": "bitcoin-up-or-down-on-january-29",
  "condition_id": "0x...",
  "token_id": "..."
}
```

### 策略层（核心）

```python
class MarketMakingStrategy(Strategy):
    def on_order_book(self, order_book):
        # 1. 获取中间价（框架提供）
        mid = order_book.midpoint()

        # 2. 计算价差（策略逻辑）
        spread = self.calculate_spread()

        # 3. 计算库存倾斜（策略逻辑）
        skew = self.calculate_skew()

        # 4. 提交订单（框架执行）
        self.submit_orders(mid, spread, skew)
```

### 执行层（框架处理）

```python
# 框架自动处理：
# - 连接到 Polymarket API
# - 获取市场数据
# - 提交订单
# - 管理仓位
# - 计算盈亏
```

---

## 我的错误总结

### 错误 1: 混淆了层次

```
我应该做：策略逻辑（做市算法）
我实际做了：数据获取（框架的职责）
```

### 错误 2: 过度设计

```
旧项目：
  - 1 个主文件
  - 直接 Gamma API
  - 备用 ID fallback

我的项目：
  - 5+ 个工具
  - 复杂的配置流程
  - 手动操作步骤
```

### 错误 3: 不必要的复杂性

```
问题：网络连接失败
我的"解决"：创建手动配置工具
真正的解决：部署到 Zeabur（网络正常）
```

---

## 正确的方法

### 方案 A: 简单直接（本地开发）

```python
# run_market_making.py
def main():
    # 1. 尝试获取 token
    try:
        condition_id, token_id = get_market_info(slug)
    except:
        # 2. 使用备用 token
        condition_id, token_id = FALLBACK_IDS

    # 3. 启动策略
    node = TradingNode(...)
    strategy = MarketMakingStrategy(...)
    node.run()
```

### 方案 B: 部署到 Zeabur（生产环境）

```bash
# 1. 本地测试（使用备用 token）
python run_market_making.py

# 2. 推送到 GitHub
git push

# 3. Zeabur 自动部署
# （网络正常，Gamma API 可用）
```

---

## 结论

### 我应该专注的地方

1. **策略优化**
   - 价差算法
   - 库存管理
   - 风险控制

2. **适应特殊性**
   - 每日市场切换
   - 二元期权风险模型
   - Polymarket 订单类型（FOK/IOC）

3. **利用框架**
   - 让 NautilusTrader 处理数据
   - 让框架处理订单执行
   - 让框架计算盈亏

### 我不应该做的地方

1. ❌ 重复获取市场数据
2. ❌ 创建复杂的配置工具
3. ❌ 手动处理框架的事情

---

**关键理解**：NautilusTrader 已经为我们处理了基础设施，我们只需要专注于策略逻辑！
