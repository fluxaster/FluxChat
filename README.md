# OpenAI 兼容多模型聊天应用

这是一个基于 FastAPI 构建的轻量级聊天应用，它提供了一个 Web 界面和一套 API 接口，用于与 OpenAI 兼容的多个大型语言模型进行交互。项目核心特点是支持对话历史记录管理和独特的**消息插入**功能。

## 🚀 主要特性

*   **多模型支持**: 可以在 [`main.py`](main.py) 中配置和使用多个不同的模型客户端。
*   **上下文管理**: 自动维护每个模型的对话历史记录。
*   **流式响应**: `/chat/` 端点支持流式（Streaming）和非流式响应。
*   **消息插入**: 独特的 `/insert-message/` 端点允许用户在下一次 `/chat/` 请求之前，将一组消息动态插入到对话历史的任意位置，实现灵活的上下文控制。
*   **Web 界面**: 提供一个简单的前端界面 (`templates/index.html`) 进行交互。

## 🛠️ 技术栈

*   **后端**: Python, FastAPI, Uvicorn
*   **API 客户端**: `requests` 库 (用于与外部 API 通信)
*   **前端**: Jinja2 模板, HTML, CSS, JavaScript

## ⚙️ 安装与配置

### 1. 安装依赖

确保您已安装 Python 3.8+。

```bash
pip install -r requirements.txt
```

### 2. API 配置

您需要在 [`main.py`](main.py) 文件中配置 API 密钥和基础地址。建议通过环境变量 `API_KEY` 和 `API_BASE` 进行配置。

```python
# main.py (部分)
API_BASE = os.getenv("API_BASE", "https://api.openai.com") # 替换为您的 OpenAI 兼容 API 地址
API_KEY = os.getenv("API_KEY", "YOUR_API_KEY_HERE") # 替换为您的实际密钥
MODEL_NAMES = ["gemini-flash-latest","gemini-2.5-pro"] # 配置您要使用的模型列表
```

### 3. 运行应用

您可以使用提供的 `start.bat` 脚本或直接使用 uvicorn 启动应用：

```bash
# 使用 start.bat
start.bat

# 或手动启动
uvicorn main:app --reload
```

应用默认将在 `http://127.0.0.1:8000` 运行。

## 🌐 API 端点

| 方法 | 路径 | 描述 |
| :--- | :--- | :--- |
| `GET` | `/` | 访问 Web 聊天界面。 |
| `POST` | `/chat/` | 发送聊天请求，支持历史记录和流式/非流式响应。 |
| `POST` | `/insert-message/` | **核心功能**：存储待插入的消息列表，用于下一次 `/chat/` 请求。 |
| `POST` | `/clear-history/` | 清除指定模型的对话历史记录和待插入消息。 |

### 消息插入 (`POST /insert-message/`) 示例

此端点用于预设下一次 `/chat/` 请求的上下文。

**请求体 (JSON):**

```json
{
  "model": "gemini-2.5-pro",
  "insertions": [
    {
      "role": "system",
      "content": "你现在是一个专业的代码审查员。",
      "depth": 1
    },
    {
      "role": "user",
      "content": "请帮我审查以下代码片段...",
      "depth": 0
    }
  ],
  "lifetime": "once"
}
```

*   `insertions`: 要插入的消息列表，遵循 OpenAI 消息格式。每个消息对象可以包含 `depth` 字段，表示插入深度。`0` 表示在历史记录末尾（用户输入前）插入；`1` 表示在倒数第二条消息前插入，以此类推。
*   `lifetime`: 插入消息的生命周期。`"once"` 表示仅对下一次 `/chat/` 请求有效；`"permanent"` 表示在清除历史记录前一直有效。

在调用此端点后，紧接着的 `/chat/` 请求将使用包含这些插入消息的完整上下文进行调用。插入的消息不会被保存到永久历史记录中。