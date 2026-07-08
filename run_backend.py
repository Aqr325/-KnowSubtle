#!/usr/bin/env python
"""启动后端服务器的引导脚本。"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# 在导入 metagpt 之前设置环境变量
os.environ["METAGPT_PROJECT_ROOT"] = PROJECT_DIR
os.environ["OPENAI_API_KEY"] = "sk-test-dummy"
os.environ["OPENAI_API_MODEL"] = "gpt-4o-mini"
os.environ["DISABLE_LLM_PROVIDER_CHECK"] = "true"

# 创建必要配置文件
import yaml
config_dir = os.path.join(PROJECT_DIR, "config")
os.makedirs(config_dir, exist_ok=True)

key_yaml = os.path.join(config_dir, "key.yaml")
if not os.path.exists(key_yaml):
    with open(key_yaml, "w") as f:
        yaml.dump({
            "OPENAI_API_KEY": "sk-test-dummy",
            "OPENAI_API_MODEL": "gpt-4o-mini",
            "DISABLE_LLM_PROVIDER_CHECK": True,
        }, f)

config_yaml = os.path.join(config_dir, "config.yaml")
if not os.path.exists(config_yaml):
    with open(config_yaml, "w") as f:
        yaml.dump({
            "llm": {
                "api_key": "sk-test-dummy",
                "api_type": "openai",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
            }
        }, f)

# 初始化 metagpt 配置
import metagpt.config as _mcfg
try:
    _ = _mcfg.CONFIG
except Exception as e:
    print(f"[Bootstrap] Config already initialized: {e}")

# 导入 app
from app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
