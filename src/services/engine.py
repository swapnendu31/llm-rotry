from src.helper.sql import get_all_keys
from src.helper.redis import hset_many
import json
from datetime import datetime

def startup():
    try:
        keys = get_all_keys()
        for i in keys:
            key = json.loads(i.model_dump_json())
            provider = key.get("provider")
            key["loaded_at"] = datetime.now().strftime("%Y-%m-%d--%H:%M:%S")
            print(f"Loading key {key}\n")
            hset_many(f"rottery-key:{key.get('id')}", key)
    except Exception as e:
        print(f"Error during startup: {e}")
        

