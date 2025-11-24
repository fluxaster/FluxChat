import json
import requests
from typing import List, Dict, Optional, Union, Generator, Literal
import uuid

# 定义插入消息的结构: {'role': str, 'content': str, 'depth': int}
InsertionMessage = List[Dict[str, Union[str, int]]]

class OpenAIChat:
    def __init__(self, api_base: str, api_key: str, model: str):
        self.api_base = api_base.strip().rstrip('/')
        self.api_key = api_key
        self.model = model
    
    def _get_endpoint(self):
        if self.api_base.endswith("/chat/completions"): return self.api_base
        if self.api_base.endswith("/v1"): return f"{self.api_base}/chat/completions"
        return f"{self.api_base}/v1/chat/completions"

    def _send_request(self, messages: List[Dict], temperature: float = 0.7,
                     top_p: float = 1.0, max_tokens: Optional[int] = None,
                     stream: bool = False, **kwargs) -> Union[Dict, Generator]:
        
        url = self._get_endpoint()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model, "messages": messages, "temperature": temperature,
            "top_p": top_p, "stream": stream
        }
        if max_tokens is not None: payload["max_tokens"] = max_tokens
        for key, value in kwargs.items(): payload[key] = value
            
        try:
            response = requests.post(url, headers=headers, json=payload, stream=stream)
            if response.status_code != 200:
                try: err = response.json()
                except: err = response.text
                return {"error": {"message": f"HTTP {response.status_code}: {err}", "type": "api_error"}}
            
            if stream: return self._process_stream_response(response)
            else: return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": {"message": str(e), "type": "network_error"}}
    
    def _process_stream_response(self, response) -> Generator:
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data.strip() == '[DONE]': break
                    try: yield json.loads(data)
                    except json.JSONDecodeError: continue
    
    def chat_with_history(self, user_input: str, history: List[Dict], system_input: Optional[str] = None,
                         temperature: float = 0.7, top_p: float = 1.0,
                         max_tokens: Optional[int] = None, stream: bool = False, **kwargs):
        # 简化的复用逻辑：直接调用 chat_with_insertion，传空插入列表即可
        return self.chat_with_insertion(
            user_input, history, system_input, 
            insertion_content=[], # 空列表
            temperature=temperature, top_p=top_p, max_tokens=max_tokens, stream=stream, **kwargs
        )
    
    def chat_with_insertion(self, user_input: str, history: List[Dict], system_input: Optional[str] = None,
                           insertion_content: Optional[List[Dict]] = None, # 改动：这里不再需要 insertion_depth
                           temperature: float = 0.7, top_p: float = 1.0,
                           max_tokens: Optional[int] = None, stream: bool = False, **kwargs):
        
        messages = []
        
        # 1. 处理 System Prompt
        need_sys = True
        if history and history[0].get("role") == "system":
            if system_input is None or history[0].get("content") == system_input: need_sys = False
        if need_sys and system_input: messages.append({"role": "system", "content": system_input})
        
        # 2. 加入历史记录
        messages.extend(history)
        
        # 3. 处理独立深度的插入消息
        if insertion_content:
            # 注意：每次 insert 都会改变数组长度，所以 index 计算是动态的
            for item in insertion_content:
                role = item.get('role', 'system')
                content = item.get('content', '')
                depth = int(item.get('depth', 0))
                
                # 计算位置：depth 0 = 末尾 (Current Context)，depth 1 = 倒数第1条之前...
                # 注意：我们要把它们插在 User Input 之前
                current_len = len(messages)
                if depth < 0: insert_pos = 0
                else:
                    insert_pos = current_len - depth
                    if insert_pos < 0: insert_pos = 0
                messages.insert(insert_pos, {"role": role, "content": content})
        
        # 4. 最后加入当前用户输入
        messages.append({"role": "user", "content": user_input})
        
        # 5. 发送
        response = self._send_request(messages, temperature, top_p, max_tokens, stream, **kwargs)
        
        if not stream:
            new_history = history.copy()
            if isinstance(response, dict) and "error" not in response and "choices" in response:
                new_history.append({"role": "user", "content": user_input})
                new_history.append(response["choices"][0]["message"])
            return response, new_history
        
        return response

class ChatSessionManager:
    def __init__(self, model_names: List[str]):
        self.sessions = {m: {} for m in model_names}

    def _get_session_data(self, model: str, session_id: str):
        if model not in self.sessions: self.sessions[model] = {}
        if session_id not in self.sessions[model]:
            self.sessions[model][session_id] = {'history': [], 'pending_insertion': None}
        return self.sessions[model][session_id]

    def get_history(self, model: str, session_id: str) -> List[Dict]:
        return self._get_session_data(model, session_id)['history']

    def update_history(self, model: str, session_id: str, new_history: List[Dict]):
        self._get_session_data(model, session_id)['history'] = new_history

    def clear_history(self, model: str, session_id: str):
        data = self._get_session_data(model, session_id)
        data['history'] = []
        data['pending_insertion'] = None

    def set_pending_insertion(self, model: str, session_id: str, insertions: List[Dict], lifetime: str):
        self._get_session_data(model, session_id)['pending_insertion'] = {
            'messages': insertions, # [{'role':.., 'content':.., 'depth':..}, ...]
            'lifetime': lifetime
        }

    def get_pending_insertion(self, model: str, session_id: str):
        return self._get_session_data(model, session_id)['pending_insertion']

    def clear_pending_insertion(self, model: str, session_id: str):
        self._get_session_data(model, session_id)['pending_insertion'] = None