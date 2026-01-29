from nautilus_trader.config import InstrumentProviderConfig

# 创建一个实例看看需要什么参数
try:
    config = InstrumentProviderConfig()
    print("Created empty config")
    print(f"Fields: {dir(config)}")
except Exception as e:
    print(f"Error creating empty config: {e}")

# 查看类属性
print("\nClass attributes:")
for attr in dir(InstrumentProviderConfig):
    if not attr.startswith('_'):
        print(f"  {attr}")

