import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from openai_chat import OpenAIChat, ChatSessionManager

API_BASE = os.getenv("API_BASE", "https://api.openai.com")
API_KEY = os.getenv("API_KEY", "YOUR_API_KEY_HERE")
MODEL_NAMES = ["gemini-flash-latest", "gemini-2.5-pro"]

app = FastAPI(title="Fluxar Chat API")
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

chat_clients = {m: OpenAIChat(API_BASE, API_KEY, m) for m in MODEL_NAMES}
chat_session_manager = ChatSessionManager(MODEL_NAMES)

# --- Updated Models ---

class InsertionItem(BaseModel):
    role: str
    content: str
    depth: int = 0  # 深度现在属于每一条消息

class InsertRequest(BaseModel):
    session_id: str
    model: str
    insertions: List[InsertionItem]
    lifetime: Literal['once', 'permanent'] = 'once'

class ChatRequest(BaseModel):
    session_id: str
    message: str
    model: str
    use_history: bool = True
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    stream: bool = False

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "model_names": MODEL_NAMES})

@app.post("/chat/")
async def chat_endpoint(request: ChatRequest):
    client = chat_clients.get(request.model)
    if not client: client = OpenAIChat(API_BASE, API_KEY, request.model)

    try:
        history = chat_session_manager.get_history(request.model, request.session_id)
        insertion_data = chat_session_manager.get_pending_insertion(request.model, request.session_id)
        
        # 准备参数
        kwargs = {
            "user_input": request.message,
            "history": history,
            "system_input": request.system_prompt,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "stream": request.stream
        }

        # 调用逻辑
        if insertion_data:
            # 这里的 insertion_data['messages'] 已经是一个包含 depth 的字典列表
            # 我们将 dict 转换回普通 dict 传给 client (如果它是 pydantic 对象)
            msgs = insertion_data['messages']
            if msgs and hasattr(msgs[0], 'dict'): msgs = [m.dict() for m in msgs]
            
            response_result = client.chat_with_insertion(**kwargs, insertion_content=msgs)
            
            if insertion_data['lifetime'] == 'once':
                chat_session_manager.clear_pending_insertion(request.model, request.session_id)
        else:
            response_result = client.chat_with_history(**kwargs)
        
        # 流式处理
        if request.stream:
            if isinstance(response_result, dict) and "error" in response_result:
                 return StreamingResponse(iter([f"data: {json.dumps({'content': 'Error: ' + response_result['error']['message']})}\n\n"]), media_type="text/event-stream")

            async def generate():
                full_response = ""
                for chunk in response_result:
                    if "error" in chunk:
                        yield f"data: {json.dumps({'content': f' Error: {chunk["error"]["message"]}'})}\n\n"
                        break
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            content = delta["content"]
                            full_response += content
                            yield f"data: {json.dumps({'content': content})}\n\n"
                
                if request.use_history:
                    final_history = chat_session_manager.get_history(request.model, request.session_id)
                    final_history.append({"role": "user", "content": request.message})
                    final_history.append({"role": "assistant", "content": full_response})
                    chat_session_manager.update_history(request.model, request.session_id, final_history)
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(generate(), media_type="text/event-stream")
        
        else:
            response_data, new_history = response_result
            if "error" in response_data: return {"reply": "", "error": response_data["error"]["message"]}
            
            if request.use_history:
                chat_session_manager.update_history(request.model, request.session_id, new_history)
            return {"reply": response_data["choices"][0]["message"]["content"]}

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"reply": "", "error": str(e)}

@app.post("/insert-message/")
async def insert_message_endpoint(request: InsertRequest):
    try:
        # 直接存储 InsertRequest 中的 insertions 列表（每个元素都含 depth）
        # 将 Pydantic 模型转为 dict 列表存储
        insertions_data = [i.dict() for i in request.insertions]
        
        chat_session_manager.set_pending_insertion(
            model=request.model,
            session_id=request.session_id,
            # depth 参数已移除
            insertions=insertions_data,
            lifetime=request.lifetime
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/clear-history/")
async def clear_history_endpoint(model: str, session_id: str):
    chat_session_manager.clear_history(model, session_id)
    return {"status": "cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)