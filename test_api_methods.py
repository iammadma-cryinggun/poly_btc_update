"""
测试 Polymarket API - 使用正确的方法
"""
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from pathlib import Path

def main():
    print("=" * 80)
    print("测试 Polymarket API")
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

    print(f"\n私钥: {private_key[:10]}...{private_key[-6:]}")
    print(f"API Key: {api_key}")

    # 创建客户端
    print("\n[1] 创建客户端...")
    client = ClobClient(
        host='https://clob.polymarket.com',
        chain_id=POLYGON,
        key=private_key,
        signature_type=2,
    )

    # 获取地址
    print("\n[2] 获取地址...")
    address = client.get_address()
    print(f"   地址: {address}")

    # 设置 API 凭证
    print("\n[3] 设置 API 凭证...")
    if api_key and api_secret and passphrase:
        from py_clob_client.clob_types import ApiCreds
        creds = ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=passphrase
        )
        client.set_api_creds(creds)
        print("   成功")
    else:
        print("   凭证不完整")
        return 1

    # 测试 API 调用
    print("\n[4] 测试获取订单...")
    try:
        orders = client.get_orders()
        print(f"   成功! 订单数量: {len(orders.get('data', []))}")
    except Exception as e:
        print(f"   失败: {e}")

    print("\n[5] 测试获取市场...")
    try:
        markets = client.get_markets(limit=1)
        print(f"   成功!")
    except Exception as e:
        print(f"   失败: {e}")

    print("\n" + "=" * 80)
    print(f"get_address() 返回: {address}")
    print(f"您的充值地址（截图）: 0x18Ddc...CD2d")
    print(f"\n如果 API 调用成功，说明配置正确！")
    print("=" * 80)

if __name__ == "__main__":
    main()
