"""
测试 Polymarket 连接
"""
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
import os
from pathlib import Path

def main():
    print("=" * 80)
    print("测试 Polymarket 连接")
    print("=" * 80)

    # 读取 .env 文件
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

    print(f"\n[INFO] 私钥: {private_key[:10]}...{private_key[-6:]}")
    print(f"[INFO] API Key: {api_key}")

    # 创建客户端
    print("\n[INFO] 正在创建客户端...")
    client = ClobClient(
        host='https://clob.polymarket.com',
        chain_id=POLYGON,
        key=private_key,
        signature_type=2,
    )

    # 获取地址
    address = client.get_address()
    print(f"\n[INFO] 私钥对应的地址: {address}")

    # 尝试获取账户余额
    print("\n[INFO] 尝试获取账户余额...")
    try:
        # 使用 derive 获取完整凭证
        creds = client.derive_api_key()
        print(f"[OK] API Key: {creds.api_key}")
        print(f"[OK] API Secret: {creds.api_secret[:10]}...")
        print(f"[OK] Passphrase: {creds.api_passphrase}")

        # 创建带凭证的客户端
        client_full = ClobClient(
            host='https://clob.polymarket.com',
            chain_id=POLYGON,
            key=private_key,
            signature_type=2,
            api_key=creds.api_key,
            api_secret=creds.api_secret,
            api_passphrase=creds.api_passphrase,
        )

        # 获取余额
        balance_dict = client_full.get_balance_sensitive()
        print(f"\n[OK] 账户余额:")
        print(f"   USDC: {balance_dict.get('usdc', 'N/A')}")

    except Exception as e:
        print(f"[ERROR] 获取余额失败: {e}")

    print("\n" + "=" * 80)
    print(f"您的钱包地址（截图）: 0x18DdcbD977e5b7Ff751A3BAd6F274b67A311CD2d")
    print(f"私钥对应的地址（计算）: {address}")
    print(f"是否匹配: {'✅ 是' if address.lower() == '0x18DdcbD977e5b7Ff751A3BAd6F274b67A311CD2d'.lower() else '❌ 否'}")
    print("=" * 80)

if __name__ == "__main__":
    main()
