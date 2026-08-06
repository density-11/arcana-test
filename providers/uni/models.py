"""Model catalog and aliases exposed by the UNI route."""


CHAT_MODELS = {
        "S1Lite": "S1-Base-Lite",
        "S1Pro": "S1-Base-Pro",
        "S1Ultra": "S1-Base-Ultra",
        "DeepSeek": "deepseek-v4-flash",
        "DeepSeekAistar": "deepseek-v4-flash-aistar",
        "GLM": "glm5.2",
        "GPTOss": "gpt-oss-120b",
        "Kimi": "kimi-k2.6",
        "MiniMaxM27": "minimax-m27",
        "MiniMaxM3": "minimax-m3",
        "Qwen3p5": "qwen3.5",
        "Qwen3p6": "qwen3.6-27b",
        }
ARC_VISION_MODEL_IDS = {"qwen3.5", "qwen3.6-27b"}
MODEL_ALIASES = {
        "GPT": "GPTOss",
        "GPT5": "GPTOss",
        "deepseek": "DeepSeek",
        "Qwen": "Qwen3p5",
        }
