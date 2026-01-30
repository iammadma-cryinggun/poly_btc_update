"""
预测市场做市策略 - 基于学术论文优化

论文：Market Making in Prediction Markets
核心思想：
1. Avellaneda-Stoikov 模型应用到二元期权市场
2. 价差 = γσ²T（随时间衰减动态调整）
3. 库存管理（根据持仓调整报价倾斜）
4. 价格收敛性（随到期时间接近，价格向0或1收敛）

优化点：
- 时间衰减价差（15分钟内动态调整）
- 库存风险感知
- 最后5分钟保护机制
"""

from decimal import Decimal
import time
import math

from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.objects import Price, Quantity

from .base_strategy import BaseStrategy
from .data_recorder import TradeDataRecorder


class PredictionMarketMMStrategy(BaseStrategy):
    """
    预测市场做市策略（基于论文优化）

    核心改进：
    1. 时间衰减价差：s = γσ²T
    2. 库存风险管理：倾斜调整
    3. 价格收敛保护：最后5分钟特殊处理
    """

    # ========== 默认参数 ==========

    # 风险参数（论文中的γ）
    DEFAULT_RISK_AVERSION = Decimal("0.5")  # 风险厌恶系数

    # 价差参数
    DEFAULT_BASE_SPREAD = Decimal("0.02")    # 2% 基础价差
    DEFAULT_MIN_SPREAD = Decimal("0.01")     # 1% 最小价差
    DEFAULT_MAX_SPREAD = Decimal("0.15")     # 15% 最大价差

    # 时间衰减参数（关键！）
    DEFAULT_TIME_DECAY_FACTOR = Decimal("2.0")  # 时间衰减因子

    # 订单参数
    DEFAULT_ORDER_SIZE = 2                 # 每单 2 个（1U）
    DEFAULT_MIN_ORDER_SIZE = 1
    DEFAULT_MAX_ORDER_SIZE = 5

    # 库存参数
    DEFAULT_TARGET_INVENTORY = 0
    DEFAULT_MAX_INVENTORY = 10              # 最大 10 个（5U）
    DEFAULT_INVENTORY_SKEW_FACTOR = Decimal("0.001")  # 更敏感
    DEFAULT_MAX_SKEW = Decimal("0.05")
    DEFAULT_HEDGE_THRESHOLD = 4
    DEFAULT_HEDGE_SIZE = 3

    # 价格参数
    DEFAULT_MIN_PRICE = Decimal("0.05")
    DEFAULT_MAX_PRICE = Decimal("0.95")

    # 波动率参数
    DEFAULT_MAX_VOLATILITY = Decimal("0.15")
    DEFAULT_MIN_VOLATILITY = Decimal("0.03")  # 3% 最小波动率底线（防止价差过小）
    DEFAULT_VOLATILITY_WINDOW = 30

    # 资金参数
    DEFAULT_MAX_POSITION_RATIO = Decimal("0.4")
    DEFAULT_MAX_DAILY_LOSS = Decimal("-3.0")

    # 行为参数
    DEFAULT_UPDATE_INTERVAL_MS = 1000      # 1 秒
    DEFAULT_END_BUFFER_MINUTES = 5         # 最后5分钟保护

    def __init__(self, config):
        super().__init__(config)

        self.instrument_id = getattr(config, 'instrument_id')

        # 从配置读取参数
        self.base_spread = getattr(config, 'base_spread', self.DEFAULT_BASE_SPREAD)
        self.min_spread = getattr(config, 'min_spread', self.DEFAULT_MIN_SPREAD)
        self.max_spread = getattr(config, 'max_spread', self.DEFAULT_MAX_SPREAD)

        self.risk_aversion = getattr(config, 'risk_aversion', self.DEFAULT_RISK_AVERSION)
        self.time_decay_factor = getattr(config, 'time_decay_factor', self.DEFAULT_TIME_DECAY_FACTOR)
        self.end_buffer_minutes = getattr(config, 'end_buffer_minutes', self.DEFAULT_END_BUFFER_MINUTES)

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
        self.min_volatility = getattr(config, 'min_volatility', self.DEFAULT_MIN_VOLATILITY)
        self.volatility_window = getattr(config, 'volatility_window', self.DEFAULT_VOLATILITY_WINDOW)

        self.max_position_ratio = getattr(config, 'max_position_ratio', self.DEFAULT_MAX_POSITION_RATIO)
        self.max_daily_loss = getattr(config, 'max_daily_loss', self.DEFAULT_MAX_DAILY_LOSS)

        self.update_interval_ms = getattr(config, 'update_interval_ms', self.DEFAULT_UPDATE_INTERVAL_MS)
        self.use_inventory_skew = getattr(config, 'use_inventory_skew', True)
        self.use_dynamic_spread = getattr(config, 'use_dynamic_spread', True)

        # 内部状态
        self._last_update_time_ns = 0
        self._price_history = []
        self._daily_start_pnl = Decimal("0")
        self._daily_start_balance = Decimal("0")
        self._market_start_time = None  # 市场开始时间（用于计算T）

        # ========== 数据记录器 ==========
        self.recorder = TradeDataRecorder()
        self._recording_enabled = True  # 可开关记录功能

    # ========== 核心逻辑 ==========

    def on_order_book(self, order_book):
        """处理订单簿更新（基于论文优化的做市逻辑）"""

        # 1. 检查更新间隔
        now_ns = self.clock.timestamp_ns()
        if now_ns - self._last_update_time_ns < self.update_interval_ms * 1_000_000:
            return

        # 2. 风险检查
        if not self._check_risk(order_book):
            return

        # 3. 获取中间价（带冷启动逻辑）
        mid = order_book.midpoint()

        # ========== 冷启动修复：处理空盘口 ==========
        if mid is None:
            # 尝试从 bid/ask 重建中间价
            best_bid = order_book.best_bid_price()
            best_ask = order_book.best_ask_price()

            # ========== 僵尸市场检测（早期拦截）==========
            # 在计算 mid_price 之前就检测原始 bid/ask 值
            if best_ask is not None and best_bid is None:
                ask_val = Decimal(best_ask)
                if ask_val <= Decimal("0.02"):
                    self.log.warning(
                        f"[ZOMBIE] 检测到僵尸市场：ask={ask_val:.4f}（接近0），"
                        f"市场已判定结果，停止做市"
                    )
                    return

            if best_bid is not None and best_ask is None:
                bid_val = Decimal(best_bid)
                if bid_val >= Decimal("0.98"):
                    self.log.warning(
                        f"[ZOMBIE] 检测到僵尸市场：bid={bid_val:.4f}（接近1），"
                        f"市场已判定结果，停止做市"
                    )
                    return

            if best_bid is None and best_ask is None:
                # 情况A：完全空盘 → 使用默认 0.50
                self.log.warning("[COLD START] 完全空盘口，使用默认中间价 0.50")
                mid_price = Decimal("0.50")

            elif best_bid is None:
                # 情况B：只有卖单 → 中间价 = ask - spread
                ask_price = Decimal(best_ask)
                mid_price = ask_price * (Decimal("1") - self.base_spread)
                self.log.warning(f"[COLD START] 只有卖单 {ask_price:.4f}，推算中间价 {mid_price:.4f}")

            elif best_ask is None:
                # 情况C：只有买单 → 中间价 = bid + spread
                bid_price = Decimal(best_bid)
                mid_price = bid_price * (Decimal("1") + self.base_spread)
                self.log.warning(f"[COLD START] 只有买单 {bid_price:.4f}，推算中间价 {mid_price:.4f}")

            else:
                # 双方都有但还是 midpoint 返回 None（理论上不会）
                self.log.warning("[COLD START] midpoint 为 None，尝试直接计算")
                mid_price = (Decimal(best_bid) + Decimal(best_ask)) / 2
        else:
            mid_price = Decimal(mid)

        # ========== 极端价格保护（双重保险）==========
        if mid_price >= Decimal("0.94") or mid_price <= Decimal("0.06"):
            self.log.warning(
                f"[RISK] 价格过于极端 {mid_price:.4f}，停止做市以防单边风险"
            )
            return

        # 4. 记录价格历史
        self._update_price_history(mid_price)

        # 5. 计算剩余时间（关键！）
        time_remaining = self._get_time_remaining()

        # ⚠️ 最后5分钟保护：停止做市
        if time_remaining <= self.end_buffer_minutes * 60:
            self.log.warning(
                f"距离到期不足 {self.end_buffer_minutes} 分钟，停止做市"
            )
            return

        # 6. 计算时间衰减价差（论文公式：s = γσ²T）
        # 检测是否为冷启动状态
        is_cold_start = (mid is None)

        if self.use_dynamic_spread:
            spread = self._calculate_time_decay_spread(time_remaining)

            # ========== 冷启动优化：使用更小价差吸引交易 ==========
            if is_cold_start:
                # 冷启动时：使用 1/3 价差，更快成交
                spread = max(spread / 3, self.min_spread)
                self.log.info(f"[COLD START] 使用激进价差 {spread*100:.2f}% 吸引首笔交易")
        else:
            spread = self.base_spread

        # 7. 计算库存倾斜
        if self.use_inventory_skew:
            skew = self._calculate_inventory_skew()
        else:
            skew = Decimal("0")

        # 8. 计算挂单价格
        half_spread = spread / 2
        bid_price = mid_price * (Decimal("1") - half_spread - skew)
        ask_price = mid_price * (Decimal("1") + half_spread + skew)

        # 9. 提交订单
        self._submit_market_quotes(bid_price, ask_price, self.order_size)

        # 10. 更新时间戳
        self._last_update_time_ns = now_ns

        # 11. 记录日志
        time_remaining_min = time_remaining / 60

        self.log.info(
            f"\n{'='*60}\n"
            f"预测市场做市（基于论文优化）:\n"
            f"  状态: {'🔥 冷启动' if is_cold_start else '✅ 正常'}\n"
            f"  中间价: {mid_price:.4f}\n"
            f"  剩余时间: {time_remaining_min:.1f} 分钟\n"
            f"  价差: {spread*100:.2f}% (时间衰减调整)\n"
            f"  倾斜: {skew*100:.2f}% (库存风险)\n"
            f"  买价: {bid_price:.4f}\n"
            f"  卖价: {ask_price:.4f}\n"
            f"  订单大小: {self.order_size}个\n"
            f"{'='*60}"
        )

        # ========== 数据记录 ==========
        if self._recording_enabled:
            volatility = self._calculate_volatility()
            self.recorder.record_orderbook(
                mid_price=mid_price,
                bid_price=bid_price,
                ask_price=ask_price,
                spread=spread,
                time_remaining_min=time_remaining_min,
                volatility=volatility,
                skew=skew,
            )

    def on_order_filled(self, event):
        """订单成交时调用"""
        super().on_order_filled(event)

        # ========== 记录成交数据 ==========
        if self._recording_enabled:
            # 计算此交易的盈亏（简化版本：手续费=成本）
            commission = Decimal(str(event.commission)) if event.commission else Decimal("0")
            pnl = -commission  # 简化：只扣除手续费

            self.recorder.record_trade(
                order_id=str(event.order_cl_order_id),
                side=event.order_side.name,
                price=Decimal(str(event.last_px)),
                quantity=event.last_qty,
                commission=commission,
                pnl=pnl
            )

            # 记录库存变化
            account = self.get_account_info()
            position = self.get_current_position()

            if account and position:
                inventory_value = abs(position['quantity']) * Decimal(position['current_price'])

                self.recorder.record_inventory(
                    inventory_qty=position['quantity'],
                    inventory_value=inventory_value,
                    free_balance=account['free_balance'].as_decimal(),
                    total_balance=account['total_balance'].as_decimal(),
                    realized_pnl=account['realized_pnl'].as_decimal(),
                    unrealized_pnl=account['unrealized_pnl'].as_decimal()
                )

        # 检查是否需要对冲
        if self._need_hedge():
            self.log.warning("检测到库存过多，执行对冲")
            self._hedge_inventory()

    # ========== 论文公式实现 ==========

    def _get_time_remaining(self) -> int:
        """
        计算距离到期的剩余时间（秒）

        对于15分钟市场：
        - 如果能获取到期时间，使用实际时间
        - 否则假设15分钟轮次
        """
        # TODO: 从市场数据获取实际到期时间
        # 目前使用简化假设：每15分钟一轮

        if not self._market_start_time:
            self._market_start_time = time.time()

        elapsed = time.time() - self._market_start_time
        total_duration = 15 * 60  # 15分钟

        remaining = max(0, total_duration - elapsed)
        return int(remaining)

    def _calculate_time_decay_spread(self, time_remaining: int) -> Decimal:
        """
        基于论文公式计算时间衰减价差

        公式：s = γσ²T

        其中：
        - γ (gamma) = risk_aversion (风险厌恶系数)
        - σ² (sigma²) = volatility² (方差)
        - T = time_remaining (剩余时间)

        逻辑：
        - 时间越多 → 价差越大（不确定性高）
        - 时间越少 → 价差越小（但最后5分钟会停止）
        """
        # 1. 计算波动率
        volatility = self._calculate_volatility()

        # 2. 计算时间权重（归一化到0-1）
        time_normalized = time_remaining / (15 * 60)  # 15分钟归一化

        # 3. 论文公式：s = γσ²T
        # 调整：使价差在合理范围内
        gamma = self.risk_aversion
        sigma_squared = volatility ** 2
        T = Decimal(time_normalized) * self.time_decay_factor

        theoretical_spread = gamma * sigma_squared * T

        # 4. 结合基础价差
        spread = self.base_spread + theoretical_spread

        # 5. 限制范围
        return max(min(spread, self.max_spread), self.min_spread)

    def _calculate_inventory_skew(self) -> Decimal:
        """
        计算库存倾斜（非线性版本 - 防止爆仓）

        持有过多 YES（+）→ 降低买价，提高卖价 → 鼓励卖出
        持有过多 NO（-）→ 提高买价，降低卖价 → 鼓励买入

        改进：使用非线性倾斜，库存越多，倾斜力度呈指数增长
        公式：skew = sign(delta) * (delta² * factor)
        """
        position = self.get_current_position()

        if not position:
            return Decimal("0")

        # 库存偏差
        current_inventory = position['quantity']
        inventory_delta = Decimal(current_inventory) - Decimal(self.target_inventory)

        # ========== 非线性倾斜（关键改进）==========
        # 当 delta=2 时，skew≈0.2%；当 delta=8 时，skew≈3.2%
        delta_abs = abs(inventory_delta)

        # 使用平方函数，库存越大倾斜力度越强
        skew_magnitude = (delta_abs ** 2) * self.inventory_skew_factor

        # 保持方向
        skew = skew_magnitude if inventory_delta > 0 else -skew_magnitude

        # 限制最大倾斜
        return max(min(skew, self.max_skew), -self.max_skew)

    # ========== 订单提交 ==========

    def _submit_market_quotes(
        self,
        bid_price: Decimal,
        ask_price: Decimal,
        order_size: int,
    ):
        """
        提交做市订单（GTC订单）

        关键修复：量化价格到 instrument 的价格精度，避免 Decimal 高精度导致错误
        """
        # ========== 量化价格到 instrument 精度 ==========
        # Polymarket price_precision=3，所以量化到 3 位小数
        # 避免 "precision greater than max 16, was 28" 错误
        price_quantization = Decimal("0.001")  # 3位小数
        bid_price_quantized = bid_price.quantize(price_quantization)
        ask_price_quantized = ask_price.quantize(price_quantization)

        # 创建买单
        buy_order = self.order_factory.limit(
            instrument_id=self.instrument.id,
            price=Price.from_str(str(bid_price_quantized)),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_int(order_size),
            post_only=False,
            time_in_force=TimeInForce.GTC,
        )

        # 创建卖单
        sell_order = self.order_factory.limit(
            instrument_id=self.instrument.id,
            price=Price.from_str(str(ask_price_quantized)),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_int(order_size),
            post_only=False,
            time_in_force=TimeInForce.GTC,
        )

        # 提交两个独立订单
        self.submit_order(buy_order)
        self.submit_order(sell_order)

        # ========== 记录订单提交 ==========
        if self._recording_enabled:
            self.recorder.record_order(
                order_id=str(buy_order.client_order_id),
                side='BUY',
                price=bid_price,
                quantity=order_size,
                order_type='LIMIT',
                status='SUBMITTED'
            )
            self.recorder.record_order(
                order_id=str(sell_order.client_order_id),
                side='SELL',
                price=ask_price,
                quantity=order_size,
                order_type='LIMIT',
                status='SUBMITTED'
            )

    # ========== 计算方法 ==========

    def _calculate_volatility(self) -> Decimal:
        """计算价格波动率（带最小波动率底线）"""
        if len(self._price_history) < 10:
            return Decimal("0.05")  # 默认5%

        # 取最近的 N 个价格
        recent_prices = self._price_history[-self.volatility_window:]

        # 计算标准差
        mean_price = sum(recent_prices) / len(recent_prices)
        variance = sum((p - mean_price) ** 2 for p in recent_prices) / len(recent_prices)
        volatility = (variance ** 0.5) / mean_price if mean_price > 0 else Decimal("0")

        # ========== 关键改进：最小波动率底线 ==========
        # 防止在横盘时价差过小，被变盘埋伏
        return max(volatility, self.min_volatility)

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

        # 记录市场开始时间
        self._market_start_time = time.time()

        # ========== 保存策略配置 ==========
        if self._recording_enabled:
            config_dict = {
                'instrument_id': str(self.instrument_id),
                'base_spread': str(self.base_spread),
                'min_spread': str(self.min_spread),
                'max_spread': str(self.max_spread),
                'risk_aversion': str(self.risk_aversion),
                'time_decay_factor': str(self.time_decay_factor),
                'order_size': self.order_size,
                'max_inventory': self.max_inventory,
                'inventory_skew_factor': str(self.inventory_skew_factor),
                'max_skew': str(self.max_skew),
                'min_volatility': str(self.min_volatility),
                'max_volatility': str(self.max_volatility),
                'end_buffer_minutes': self.end_buffer_minutes,
            }
            self.recorder.save_config(config_dict)
            self.log.info("[DATA] Strategy configuration saved")

            # 记录初始库存状态
            account = self.get_account_info()
            position = self.get_current_position()
            if account and position:
                inventory_value = abs(position['quantity']) * Decimal(position['current_price'])
                self.recorder.record_inventory(
                    inventory_qty=position['quantity'],
                    inventory_value=inventory_value,
                    free_balance=account['free_balance'].as_decimal(),
                    total_balance=account['total_balance'].as_decimal(),
                    realized_pnl=account['realized_pnl'].as_decimal(),
                    unrealized_pnl=account['unrealized_pnl'].as_decimal()
                )

    def on_stop(self):
        """策略停止时调用"""
        super().on_stop()

        # ========== 记录最终库存状态 ==========
        if self._recording_enabled:
            account = self.get_account_info()
            position = self.get_current_position()

            if account and position:
                inventory_value = abs(position['quantity']) * Decimal(position['current_price'])
                self.recorder.record_inventory(
                    inventory_qty=position['quantity'],
                    inventory_value=inventory_value,
                    free_balance=account['free_balance'].as_decimal(),
                    total_balance=account['total_balance'].as_decimal(),
                    realized_pnl=account['realized_pnl'].as_decimal(),
                    unrealized_pnl=account['unrealized_pnl'].as_decimal()
                )

            # 打印数据摘要
            summary = self.recorder.get_summary()
            self.log.info(f"\n{summary}")
            self.log.info("[DATA] Final inventory state recorded")
