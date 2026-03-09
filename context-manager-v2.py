#!/usr/bin/env python3
"""
CDP Chrome Pro Context Manager v2
支持 3 并发 + 排队协调
"""

import os
import shutil
import json
import time
import asyncio
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from collections import deque
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import psutil

app = FastAPI(title="CDP Chrome Pro - Coordinated Context Manager v2")

PROFILES_DIR = Path("/profiles")
STATE_FILE = Path("/profiles/state.json")
DEFAULT_TIMEOUT = 3600  # 1 hour

# ============ 配置 ============
MAX_CONCURRENT = 3  # 最大并发槽位数
DEFAULT_SLOT_TIMEOUT = 300  # 默认等待槽位超时 5分钟

# ============ 槽位管理器 ============
class SlotManager:
    """并发槽位管理器：3并发 + 排队"""
    
    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        self.active_slots: Dict[str, dict] = {}  # slot_id -> info
        self.available_slots = list(range(max_concurrent))  # [0, 1, 2]
        self.lock = asyncio.Lock()
        self.queue = deque()  # 等待队列
        self.queue_events: Dict[str, asyncio.Event] = {}  # queue_id -> Event
    
    async def acquire(self, agent_id: str, timeout: int = DEFAULT_SLOT_TIMEOUT) -> dict:
        """获取槽位，如果没有则等待"""
        async with self.lock:
            if self.available_slots:
                # 有可用槽位，立即分配
                slot_num = self.available_slots.pop(0)
                slot_id = f"slot_{slot_num}"
                self.active_slots[slot_id] = {
                    "agent_id": agent_id,
                    "slot_num": slot_num,
                    "started_at": time.time(),
                    "profile_path": f"/profiles/{agent_id}"
                }
                return {
                    "slot_id": slot_id,
                    "status": "acquired",
                    "profile_path": f"/profiles/{agent_id}",
                    "queue_position": 0  # 立即执行
                }
            
            # 无可用槽位，加入队列
            queue_id = str(uuid.uuid4())
            event = asyncio.Event()
            self.queue_events[queue_id] = event
            queue_position = len(self.queue) + 1
            self.queue.append({
                "queue_id": queue_id,
                "agent_id": agent_id,
                "enqueued_at": time.time()
            })
        
        # 等待槽位释放
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            # 被唤醒后获取槽位
            async with self.lock:
                slot_num = self.available_slots.pop(0)
                slot_id = f"slot_{slot_num}"
                self.active_slots[slot_id] = {
                    "agent_id": agent_id,
                    "slot_num": slot_num,
                    "started_at": time.time(),
                    "profile_path": f"/profiles/{agent_id}"
                }
                return {
                    "slot_id": slot_id,
                    "status": "acquired",
                    "profile_path": f"/profiles/{agent_id}",
                    "queue_position": 0  # 已获得槽位
                }
        except asyncio.TimeoutError:
            # 超时，从队列移除
            async with self.lock:
                self.queue = deque([q for q in self.queue if q["queue_id"] != queue_id])
                self.queue_events.pop(queue_id, None)
                queue_length = len(self.queue)
            raise HTTPException(503, f"Timeout waiting for slot. Queue length: {queue_length}")
    
    async def release(self, slot_id: str) -> dict:
        """释放槽位，自动唤醒下一个等待者"""
        async with self.lock:
            if slot_id not in self.active_slots:
                raise HTTPException(404, f"Slot {slot_id} not found")
            
            info = self.active_slots.pop(slot_id)
            slot_num = info["slot_num"]
            agent_id = info["agent_id"]
            running_time = int(time.time() - info["started_at"])
            
            self.available_slots.append(slot_num)
            
            # 唤醒下一个等待者
            next_agent = None
            if self.queue:
                next_item = self.queue.popleft()
                queue_id = next_item["queue_id"]
                next_agent = next_item["agent_id"]
                if queue_id in self.queue_events:
                    self.queue_events[queue_id].set()
                    self.queue_events.pop(queue_id)
        
        return {
            "status": "released",
            "slot_id": slot_id,
            "agent_id": agent_id,
            "running_time": running_time,
            "next_agent": next_agent
        }
    
    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            "max_concurrent": self.max_concurrent,
            "active_count": len(self.active_slots),
            "available_count": len(self.available_slots),
            "queue_length": len(self.queue),
            "active_slots": {
                slot_id: {
                    "agent_id": info["agent_id"],
                    "slot_num": info["slot_num"],
                    "running_for": int(time.time() - info["started_at"]),
                    "profile_path": info["profile_path"]
                }
                for slot_id, info in self.active_slots.items()
            },
            "queued_agents": [
                {
                    "agent_id": q["agent_id"],
                    "queue_id": q["queue_id"],
                    "waiting_for": int(time.time() - q["enqueued_at"])
                }
                for q in self.queue
            ]
        }

slot_manager = SlotManager(MAX_CONCURRENT)

# ============ Context 管理（原有功能） ============

class ContextInfo(BaseModel):
    agent_id: str
    profile_path: str
    created_at: datetime
    last_accessed: float
    timeout: int = DEFAULT_TIMEOUT

class ContextCreate(BaseModel):
    agent_id: str
    timeout: Optional[int] = DEFAULT_TIMEOUT

contexts: Dict[str, ContextInfo] = {}

async def save_state():
    """保存状态到文件"""
    state = {
        "contexts": {
            agent_id: {
                "profile_path": ctx.profile_path,
                "created_at": ctx.created_at.isoformat(),
                "last_accessed": ctx.last_accessed,
                "timeout": ctx.timeout
            }
            for agent_id, ctx in contexts.items()
        }
    }
    async with aiofiles.open(STATE_FILE, 'w') as f:
        await f.write(json.dumps(state, indent=2))

async def load_state():
    """从文件加载状态"""
    if STATE_FILE.exists():
        async with aiofiles.open(STATE_FILE, 'r') as f:
            content = await f.read()
            state = json.loads(content)
            for agent_id, data in state.get("contexts", {}).items():
                contexts[agent_id] = ContextInfo(
                    agent_id=agent_id,
                    profile_path=data["profile_path"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    last_accessed=data["last_accessed"],
                    timeout=data.get("timeout", DEFAULT_TIMEOUT)
                )

# ============ 执行 API（新增） ============

class ExecuteStartRequest(BaseModel):
    agent_id: str
    timeout: Optional[int] = DEFAULT_SLOT_TIMEOUT

class ExecuteEndRequest(BaseModel):
    slot_id: str

@app.post("/execute/start")
async def start_execution(request: ExecuteStartRequest):
    """
    开始执行（统一入口）
    
    - 有可用槽位：立即返回 slot_id
    - 无可用槽位：自动排队等待
    - 超时：返回 503
    
    Returns:
        {
            "slot_id": "slot_0",
            "status": "acquired",
            "profile_path": "/profiles/heming",
            "queue_position": 0  // 0=立即执行, >0=排队位置
        }
    """
    try:
        result = await slot_manager.acquire(request.agent_id, request.timeout)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/execute/end")
async def end_execution(request: ExecuteEndRequest):
    """
    结束执行（释放槽位）
    
    - 释放槽位
    - 自动唤醒下一个等待者
    
    Returns:
        {
            "status": "released",
            "slot_id": "slot_0",
            "agent_id": "heming",
            "running_time": 120,
            "next_agent": "lingxi"  // 被唤醒的下一个 agent
        }
    """
    result = await slot_manager.release(request.slot_id)
    return JSONResponse(result)

@app.get("/execute/status")
async def get_execution_status():
    """
    获取当前执行状态
    
    Returns:
        {
            "max_concurrent": 3,
            "active_count": 2,
            "available_count": 1,
            "queue_length": 3,
            "active_slots": {...},
            "queued_agents": [...]
        }
    """
    return slot_manager.get_status()

# ============ Context API（原有） ============

@app.post("/contexts/create")
async def create_context(request: ContextCreate):
    """创建 Context（兼容旧 API）"""
    agent_id = request.agent_id
    timeout = request.timeout or DEFAULT_TIMEOUT
    
    if agent_id in contexts:
        ctx = contexts[agent_id]
        ctx.last_accessed = time.time()
        return {
            "agent_id": agent_id,
            "status": "exists",
            "profile_path": ctx.profile_path,
            "antibot_enabled": True
        }
    
    profile_path = PROFILES_DIR / agent_id
    profile_path.mkdir(parents=True, exist_ok=True)
    
    contexts[agent_id] = ContextInfo(
        agent_id=agent_id,
        profile_path=str(profile_path),
        created_at=datetime.now(),
        last_accessed=time.time(),
        timeout=timeout
    )
    
    await save_state()
    
    return {
        "agent_id": agent_id,
        "status": "created",
        "profile_path": str(profile_path),
        "antibot_enabled": True
    }

@app.get("/contexts/{agent_id}")
async def get_context(agent_id: str):
    """获取 Context 信息"""
    if agent_id not in contexts:
        raise HTTPException(404, f"Context {agent_id} not found")
    
    ctx = contexts[agent_id]
    ctx.last_accessed = time.time()
    
    return {
        "agent_id": agent_id,
        "profile_path": ctx.profile_path,
        "created_at": ctx.created_at.isoformat(),
        "last_accessed": ctx.last_accessed,
        "status": "active",
        "timeout": ctx.timeout
    }

@app.delete("/contexts/{agent_id}")
async def delete_context(agent_id: str):
    """删除 Context"""
    if agent_id not in contexts:
        raise HTTPException(404, f"Context {agent_id} not found")
    
    ctx = contexts.pop(agent_id)
    
    # 可选：删除 profile 目录
    # shutil.rmtree(ctx.profile_path, ignore_errors=True)
    
    await save_state()
    
    return {"status": "deleted", "agent_id": agent_id}

@app.get("/contexts")
async def list_contexts():
    """列出所有 Context"""
    return {
        "total": len(contexts),
        "contexts": [
            {
                "agent_id": ctx.agent_id,
                "created_at": ctx.created_at.isoformat(),
                "last_accessed": ctx.last_accessed,
                "profile_path": ctx.profile_path,
                "status": "active",
                "timeout": ctx.timeout
            }
            for ctx in contexts.values()
        ]
    }

@app.post("/contexts/cleanup")
async def cleanup_contexts():
    """清理超时的 Context"""
    now = time.time()
    cleaned = []
    
    for agent_id, ctx in list(contexts.items()):
        if now - ctx.last_accessed > ctx.timeout:
            contexts.pop(agent_id)
            cleaned.append(agent_id)
    
    if cleaned:
        await save_state()
    
    return {"cleaned": cleaned, "count": len(cleaned)}

@app.get("/antibot/script")
async def get_antibot_script():
    """获取反爬脚本"""
    script_path = Path("/opt/antibot.js")
    if script_path.exists():
        async with aiofiles.open(script_path, 'r') as f:
            script = await f.read()
        return {"script": script}
    return {"error": "Antibot script not found"}

@app.get("/health")
async def health():
    """健康检查"""
    status = slot_manager.get_status()
    return {
        "status": "healthy",
        "contexts_count": len(contexts),
        "active_operations": status["active_count"],
        "queued_operations": status["queue_length"],
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent
    }

@app.on_event("startup")
async def startup():
    """启动时加载状态"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    await load_state()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
