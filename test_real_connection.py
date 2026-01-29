"""
直接测试 Polymarket API 是否能正常工作
"""
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from pathlib import Path
import json

def main():
    print("=" * 80)
    print("测试 Polymarket API 连接（使用当前 .env 配置）")
    print("=" * 80)

    # 读取 .env
    env_file = Path(__file__).parent / ".env"
    env_vars = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()

    private_key = env_vars.get('POLYMARKET_PK')
    api_key = env_vars.get('POLYMARKET_API_KEY')
    api_secret = env_vars.get('POLYMARKET_API_SECRET')
    passphrase = env_vars.get('POLYMARKET_PASSPHRASE')

    print(f"\n[配置]")
    print(f"  私钥: {private_key[:10]}...{private_key[-6:]}")
    print(f"  API Key: {api_key}")
    print(f"  API Secret: {api_secret[:10]}..." if api_secret else "  API Secret: (空)")
    print(f"  Passphrase: {passphrase[:10]}..." if passphrase else "  Passphrase: (空)")

    # 创建客户端（L1 认证）
    print("\n[测试 1] 创建客户端（L1 认证）")
    client = ClobClient(
        host='https://clob.polymarket.com',
        chain_id=POLYGON,
        key=private_key,
        signature_type=2,
    )

    # 获取地址
    print("\n[测试 2] 获取钱包地址")
    try:
        address = client.get_address()
        print(f"  地址: {address}")
    except Exception as e:
        print(f"  失败: {e}")
        return 1

    # 创建带 API 凭证的客户端（L2 认证）
    print("\n[测试 3] 创建 L2 认证客户端")
    try:
        if api_key and api_secret and passphrase:
            client_l2 = ClobClient(
                host='https://clob.polymarket.com',
                chain_id=POLYGON,
                key=private_key,
                signature_type=2,
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=passphrase,
            )
            print("  成功创建 L2 客户端")
        else:
            print("  API 凭证不完整，跳过 L2 测试")
            client_l2 = None
    except Exception as e:
        print(f"  失败: {e}")
        client_l2 = None

    # 获取余额（L1）
    print("\n[测试 4] 获取余额（L1）")
    try:
        balances = client.get_balance()
        print(f"  余额: {balances}")
    except Exception as e:
        print(f"  失败: {e}")

    # 获取敏感余额（L2，包含更多细节）
    if client_l2:
        print("\n[测试 5] 获取敏感余额（L2）")
        try:
            balance_dict = client_l2.get_balance_sensitive()
            print(f"  USDC: {balance_dict}")
        except Exception as e:
            print(f"  失败: {e}")

    # 获取订单
    print("\n[测试 6] 获取当前订单")
    try:
        if client_l2:
            orders = client_l2.get_open_orders()
            print(f"  开放订单数量: {len(orders) if orders else 0}")
        else:
            print("  跳过（需要 L2 认证）")
    except Exception as e:
        print(f"  失败: {e}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
    print(f"\n您真正的钱包地址: {address}")
    print(f"截图中的充值地址: 0x18DdcbD977e5b7Ff751A3BAd6F274b67A311CD2d")
    print(f"\n[结论] 如果上述测试成功，说明当前配置可以正常使用")
    print("        get_address() 返回的地址可能不是实际的钱包地址")
    print("=" * 80)

if __name__ == "__main__":
    main()
