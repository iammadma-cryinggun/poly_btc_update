"""
做市策略 - 专为 Polymarket 设计

充分利用 NautilusTrader 基础设施：
- Portfolio 自动管理仓位
- BettingAccount 自动计算盈亏
- RiskEngine 自动风险检查

做市策略特点：
- 使用 GTC 订单（Good-Til-Cancelled）：保持挂单状态，赚取价差
- 双边报价：同时挂买单和卖单，保持市场中性
- 不使用 OCO：两边订单独立，成交后继续补单
"""

from decimal import Decimal

from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.objects import Price, Quantity

from .base_strategy import BaseStrategy


class MarketMakingStrategy(BaseStrategy):
    """
    Polymarket 做市策略

    核心逻辑：
    1. 同时挂买单和卖单（赚取价差）
    2. 库存管理（Skew 倾斜）
    3. 动态价差调整
    4. 风险控制

    优势：
    - 不依赖价格方向
    - 提供流动性
    - 利用 Polymarket 大价差特性
    """

    # ========== 默认参数 ==========

    # 价差参数
    DEFAULT_BASE_SPREAD = Decimal("0.02")    # 2% 基础价差
    DEFAULT_MIN_SPREAD = Decimal("0.005")   # 0.5% 最小价差
    DEFAULT_MAX_SPREAD = Decimal("0.10")    # 10% 最大价差

    # 订单参数
    DEFAULT_ORDER_SIZE = 20                 # 每单 20 个
    DEFAULT_MIN_ORDER_SIZE = 5
    DEFAULT_MAX_ORDER_SIZE = 50

    # 库存参数
    DEFAULT_TARGET_INVENTORY = 0            # 目标库存（中性）
    DEFAULT_MAX_INVENTORY = 200             # 最大库存
    DEFAULT_INVENTORY_SKEW_FACTOR = Decimal("0.0001")
    DEFAULT_MAX_SKEW = Decimal("0.02")       # 最大倾斜 2%
    DEFAULT_HEDGE_THRESHOLD = 80            # 对冲阈值
    DEFAULT_HEDGE_SIZE = 20                 # 对冲大小

    # 价格参数
    DEFAULT_MIN_PRICE = Decimal("0.05")     # 5%
    DEFAULT_MAX_PRICE = Decimal("0.95")     # 95%

    # 波动率参数
    DEFAULT_MAX_VOLATILITY = Decimal("0.15") # 15%
    DEFAULT_VOLATILITY_WINDOW = 100         # 100 个 tick

    # 资金参数
    DEFAULT_MAX_POSITION_RATIO = Decimal("0.5")  # 50%
    DEFAULT_MAX_DAILY_LOSS = Decimal("-100.0")  # -100 USDC

    # 行为参数
    DEFAULT_UPDATE_INTERVAL_MS = 1000      # 1 秒更新间隔

    def __init__(self, config):
        super().__init__(config)

        # 必需：instrument_id（BaseStrategy.on_start 需要）
        self.instrument_id = getattr(config, 'instrument_id')

        # 从配置读取参数，使用默认值
        self.base_spread = getattr(config, 'base_spread', self.DEFAULT_BASE_SPREAD)
        self.min_spread = getattr(config, 'min_spread', self.DEFAULT_MIN_SPREAD)
        self.max_spread = getattr(config, 'max_spread', self.DEFAULT_MAX_SPREAD)

        self.order_size = getattr(config, 'order_size', self.DEFAULT_ORDER_SIZE)
        self.min_order_size = getattr(config, 'min_order_size', self.DEFAULT_MIN_ORDER_SIZE)
        self.max_order_size = getattr(config, 'max_order_size', self.DEFAULT_MAX_ORDER_SIZE)

        self.target_inventory = getattr(config, 'target_inventory', self.DEFAULT_TARGET_INVENTORY)
        self.max_inventory = getattr(config, 'max_inventory', self.DEFAULT_MAX_INVENTORY)
        self.inventory_skew_factor = getattr(
            config, 'inventory_skew_factor', self.DEFAULT_INVENTORY_SKEW_FACTOR
        )
        self.max_skew = getattr(config, 'max_skew', self.DEFAULT_MAX_SKEW)
        self.hedge_threshold = getattr(config, 'hedge_threshold', self.DEFAULT_HEDGE_THRESHOLD)
        self.hedge_size = getattr(config, 'hedge_size', self.DEFAULT_HEDGE_SIZE)

        self.min_price = getattr(config, 'min_price', self.DEFAULT_MIN_PRICE)
        self.max_price = getattr(config, 'max_price', self.DEFAULT_MAX_PRICE)

        self.max_volatility = getattr(config, 'max_volatility', self.DEFAULT_MAX_VOLATILITY)
        self.volatility_window = getattr(config, 'volatility_window', self.DEFAULT_VOLATILITY_WINDOW)

        self.max_position_ratio = getattr(config, 'max_position_ratio', self.DEFAULT_MAX_POSITION_RATIO)
        self.max_daily_loss = getattr(config, 'max_daily_loss', self.DEFAULT_MAX_DAILY_LOSS)

        self.update_interval_ms = getattr(config, 'update_interval_ms', self.DEFAULT_UPDATE_INTERVAL_MS)
        self.use_inventory_skew = getattr(config, 'use_inventory_skew', True)
        self.use_dynamic_spread = getattr(config, 'use_dynamic_spread', True)

        # 内部状态
        self._last_update_time_ns = 0
        self._price_history = []  # 用于计算波动率
        self._daily_start_pnl = Decimal("0")
        self._daily_start_balance = Decimal("0")

    # ========== 核心逻辑 ==========

    def on_order_book(self, order_book):
        """处理订单簿更新（核心做市逻辑）"""

        # 1. 检查更新间隔
        now_ns = self.clock.timestamp_ns()
        if now_ns - self._last_update_time_ns < self.update_interval_ms * 1_000_000:
            return

        # 2. 风险检查
        if not self._check_risk(order_book):
            return

        # 3. 获取中间价
        mid = order_book.midpoint()
        if not mid:
            return

        mid_price = Decimal(mid)

        # 4. 记录价格历史（用于波动率计算）
        self._update_price_history(mid_price)

        # 5. 计算价差
        if self.use_dynamic_spread:
            spread = self._calculate_dynamic_spread(order_book)
        else:
            spread = self.base_spread

        # 6. 计算库存倾斜
        if self.use_inventory_skew:
            skew = self._calculate_inventory_skew()
        else:
            skew = Decimal("0")

        # 7. 计算挂单价格
        half_spread = spread / 2
        bid_price = mid_price * (Decimal("1") - half_spread - skew)
        ask_price = mid_price * (Decimal("1") + half_spread + skew)

        # 8. 计算订单大小
        order_size = self._calculate_order_size(order_book)

        # 9. 提交订单
        self._submit_market_quotes(bid_price, ask_price, order_size)

        # 10. 更新时间戳
        self._last_update_time_ns = now_ns

        # 11. 记录日志
        self.log.info(
            f"\n{'='*60}\n"
            f"做市参数:\n"
            f"  中间价: {mid_price:.4f}\n"
            f"  价差: {spread*100:.2f}%\n"
            f"  倾斜: {skew*100:.2f}%\n"
            f"  买价: {bid_price:.4f}\n"
            f"  卖价: {ask_price:.4f}\n"
            f"  订单大小: {order_size}个\n"
            f"{'='*60}"
        )

    def on_order_filled(self, event):
        """订单成交时调用"""
        super().on_order_filled(event)

        # 检查是否需要对冲
        if self._need_hedge():
            self.log.warning("检测到库存过多，执行对冲")
            self._hedge_inventory()

    # ========== 订单提交 ==========

    def _submit_market_quotes(
        self,
        bid_price: Decimal,
        ask_price: Decimal,
        order_size: int,
    ):
        """
        提交做市订单（买单 + 卖单）

        使用 GTC 订单：保持挂单状态，赚取价差
        """
        # 创建买单
        buy_order = self.order_factory.limit(
            instrument_id=self.instrument.id,
            price=Price.from_str(str(bid_price)),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_int(order_size),
            post_only=False,
            time_in_force=TimeInForce.GTC,  # GTC：保持挂单直到成交或取消
        )

        # 创建卖单
        sell_order = self.order_factory.limit(
            instrument_id=self.instrument.id,
            price=Price.from_str(str(ask_price)),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_int(order_size),
            post_only=False,
            time_in_force=TimeInForce.GTC,  # GTC：保持挂单直到成交或取消
        )

        # 提交两个独立的订单（不做 OCO）
        # 做市策略需要同时在两边挂单，保持中性
        self.submit_order(buy_order)
        self.submit_order(sell_order)

    # ========== 计算方法 ==========

    def _calculate_dynamic_spread(self, order_book) -> Decimal:
        """计算动态价差"""
        # 1. 计算波动率
        volatility = self._calculate_volatility()

        # 2. 基础价差
        spread = self.base_spread

        # 3. 根据波动率调整
        if volatility > Decimal("0.05"):  # 高波动 > 5%
            spread = spread * Decimal("1.5")
        elif volatility > Decimal("0.03"):  # 中等波动 > 3%
            spread = spread * Decimal("1.2")

        # 4. 限制范围
        return max(min(spread, self.max_spread), self.min_spread)

    def _calculate_inventory_skew(self) -> Decimal:
        """
        计算库存倾斜

        持有过多 YES（+）→ 降低买价，提高卖价 → 鼓励卖出
        持有过多 NO（-）→ 提高买价，降低卖价 → 鼓励买入
        """
        position = self.get_current_position()

        if not position:
            return Decimal("0")

        # 库存偏差
        current_inventory = position['quantity']
        inventory_delta = Decimal(current_inventory) - Decimal(self.target_inventory)

        # 计算倾斜
        skew = inventory_delta * self.inventory_skew_factor

        # 限制最大倾斜
        return max(min(skew, self.max_skew), -self.max_skew)

    def _calculate_order_size(self, order_book) -> int:
        """动态调整订单大小"""
        # 获取订单簿深度
        bids = order_book.bids()
        asks = order_book.asks()

        bid_depth = sum(level.size() for level in bids[:5])
        ask_depth = sum(level.size() for level in asks[:5])
        avg_depth = (bid_depth + ask_depth) / 2

        # 根据深度调整
        if avg_depth < 50:
            order_size = min(self.order_size, self.min_order_size * 2)
        elif avg_depth < 200:
            order_size = self.order_size
        else:
            order_size = min(self.order_size, self.max_order_size)

        return int(order_size)

    def _calculate_volatility(self) -> Decimal:
        """计算价格波动率"""
        if len(self._price_history) < 10:
            return Decimal("0")

        # 取最近的 N 个价格
        recent_prices = self._price_history[-self.volatility_window:]

        # 计算标准差
        mean_price = sum(recent_prices) / len(recent_prices)
        variance = sum((p - mean_price) ** 2 for p in recent_prices) / len(recent_prices)
        volatility = (variance ** 0.5) / mean_price if mean_price > 0 else Decimal("0")

        return volatility

    def _update_price_history(self, price: Decimal):
        """更新价格历史"""
        self._price_history.append(price)

        # 保持历史长度
        if len(self._price_history) > self.volatility_window * 2:
            self._price_history = self._price_history[-self.volatility_window * 2:]

    # ========== 风险检查 ==========

    def _check_risk(self, order_book) -> bool:
        """综合风险检查"""
        checks = [
            self._check_price_range(order_book),
            self._check_volatility_limit(),
            self._check_inventory_limits(),
            self._check_position_limits(),
            self._check_daily_loss_limit(),
        ]

        return all(checks)

    def _check_price_range(self, order_book) -> bool:
        """检查价格范围"""
        mid = order_book.midpoint()

        if not mid:
            return False

        mid_price = Decimal(mid)

        if mid_price < self.min_price or mid_price > self.max_price:
            self.log.warning(
                f"价格 {mid_price:.4f} 超出范围 "
                f"[{self.min_price:.4f}, {self.max_price:.4f}]"
            )
            return False

        return True

    def _check_volatility_limit(self) -> bool:
        """检查波动率限制"""
        volatility = self._calculate_volatility()

        if volatility > self.max_volatility:
            self.log.warning(
                f"波动率过高: {volatility*100:.2f}% > "
                f"{self.max_volatility*100:.2f}%，暂停做市"
            )
            return False

        return True

    def _check_inventory_limits(self) -> bool:
        """检查库存限制"""
        position = self.get_current_position()

        if not position:
            return True

        current_inventory = abs(position['quantity'])

        if current_inventory >= self.max_inventory:
            self.log.warning(
                f"库存已达上限: {current_inventory} >= {self.max_inventory}"
            )
            return False

        return True

    def _check_position_limits(self) -> bool:
        """检查仓位限制"""
        account = self.get_account_info()

        if not account:
            return False

        free_balance = account['free_balance'].as_decimal()

        position = self.get_current_position()
        if not position:
            return True

        position_value = abs(position['quantity']) * Decimal(position['current_price'])

        if position_value > free_balance * self.max_position_ratio:
            self.log.warning(
                f"仓位过大: {position_value:.2f} > "
                f"{free_balance * self.max_position_ratio:.2f}"
            )
            return False

        return True

    def _check_daily_loss_limit(self) -> bool:
        """检查日最大亏损"""
        account = self.get_account_info()

        if not account:
            return True

        total_pnl = account['realized_pnl'].as_decimal() + account['unrealized_pnl'].as_decimal()

        if total_pnl < self.max_daily_loss:
            self.log.warning(
                f"已达日最大亏损: {total_pnl:.2f} < {self.max_daily_loss:.2f}"
            )
            return False

        return True

    # ========== 库存管理 ==========

    def _need_hedge(self) -> bool:
        """检查是否需要对冲"""
        position = self.get_current_position()

        if not position:
            return False

        current_inventory = abs(position['quantity'])

        return current_inventory >= self.hedge_threshold

    def _hedge_inventory(self):
        """对冲库存"""
        position = self.get_current_position()

        if not position:
            return

        current_inventory = position['quantity']
        hedge_qty = min(abs(current_inventory) // 2, self.hedge_size)

        if hedge_qty <= 0:
            return

        # 持有过多 YES，卖出
        if current_inventory > 0:
            self.log.info(f"对冲: 卖出 {hedge_qty} 个 YES")
            self.submit_market_order(
                side=OrderSide.SELL,
                quantity=Quantity.from_int(hedge_qty),
            )

        # 持有过多 NO，买入
        else:
            self.log.info(f"对冲: 买入 {hedge_qty} 个 YES")
            self.submit_market_order(
                side=OrderSide.BUY,
                quantity=Quantity.from_int(hedge_qty),
            )

    # ========== 初始化 ==========

    def on_start(self):
        """策略启动"""
        super().on_start()

        # 记录初始余额
        account = self.get_account_info()
        if account:
            self._daily_start_balance = account['total_balance'].as_decimal()
            self._daily_start_pnl = account['realized_pnl'].as_decimal()
