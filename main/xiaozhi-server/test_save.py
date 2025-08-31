from config.config_loader import load_config
from config.manage_api_client import init_service, save_mem_local_short
conf = load_config()
init_service(conf)
print(save_mem_local_short("YOUR_DEVICE_ID", "テスト: 誕生日 5月1日"))
