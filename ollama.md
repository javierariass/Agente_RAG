[27/8, 2:56 p.m.] David Tecnomatica: "baseURL": "http://172.18.201.201:11434/v1"
[27/8, 2:56 p.m.] David Tecnomatica: {
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@warp-dot-dev/opencode-warp@0.1.5","@warp-dot-dev/opencode-warp"],
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": {
        "baseURL": "http://172.18.201.201:11434/v1"
      },
      "models": {
        "qwen3.6:27b": {
          "name": "Qwen 3.6 27B"
        }
      }
    }
  }
}