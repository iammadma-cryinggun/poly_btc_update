"""
验证 Polymarket 私钥对应的地址

使用方法：
    python verify_private_key.py
"""

from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

def main():
    print("=" * 80)
    print("Polymarket 私钥验证工具")
    print("=" * 80)

    print("\n请输入你的私钥：")
    private_key = input("私钥: ").strip()

    if not private_key:
        print("[错误] 未输入私钥")
        return 1

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    print(f"\n正在验证私钥: {private_key[:10]}...{private_key[-6:]}")

    try:
        client = ClobClient(
            host='https://clob.polymarket.com',
            chain_id=POLYGON,
            key=private_key,
            signature_type=2,
        )
        address = client.get_address()

        print("\n" + "=" * 80)
        print("验证结果")
        print("=" * 80)
        print(f"\n钱包地址: {address}")
        print("\n请确认：")
        print(f"  1. 这个地址是否与 Polymarket 网页上显示的地址一致？")
        print(f"  2. 地址应该是: 0x18DdcbD977e5b7Ff751A3BAd6F274b67A311CD2d")

        if address.lower() == "0x18DdcbD977e5b7Ff751A3BAd6F274b67A311CD2d".lower():
            print("\n✅ 地址匹配！私钥正确")
        else:
            print("\n❌ 地址不匹配！请检查私钥")

        print("=" * 80)

    except Exception as e:
        print(f"\n[错误] 验证失败: {e}")
        return 1

    return 0

if __name__ == "__main__":
    import sys
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已取消")
        sys.exit(1)
