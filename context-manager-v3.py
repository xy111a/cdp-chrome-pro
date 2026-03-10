#!/usr/bin/env python3
"""
CDP Chrome Pro Context Manager v3
支持 3 并发 + 排队协调 + 生产环境增强

修复：
- 竞态条件：使用单一的锁保护所有状态
- 状态持久化：Slot 状态保存到文件
- 优雅关闭：关闭时清理所有等待者
- 监控指标：添加 Prometheus metrics
"""

import os
import signal
import json
import time
import asyncio
import aiofiles
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from collections import deque
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import psutil

app = FastAPI(title="CDP Chrome Pro - Coordinated Context Manager v3")

PROFILES_DIR = Path("/profiles")
STATE_FILE = Path("/profiles/slot_state.json")
DEFAULT_TIMEOUT = 3600  # 1 hour
MAX_CONCURRENT = 3  # 最大并发槽位数
DEFAULT_SLOT_TIMEOUT = 300  # 默认等待槽位超时 5分钟

# ============ 全局状态 ============
shutdown_event = asyncio.Event()

# ============ 槽位管理器（线程安全） ============
class SlotManager:
    """并发槽位管理器：3并发 + 排队 + 状态持久化"""
    
    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        self.active_slots: Dict[str, dict] = {}
        self.available_slots = list(range(max_concurrent))
        self._lock = asyncio.Lock()  # 单一锁保护所有状态
        self.queue = deque()
        self.queue_events: Dict[str, asyncio.Event] = {}
        self._state_loaded = False
    
    async def load_state(self):
        """从文件加载状态"""
        if STATE_FILE.exists():
            try:
                async with aiofiles.open(STATE_FILE, 'r') as f:
                    content = await f.read()
                    state = json.loads(content)
                    # 只恢复活跃槽位，队列在重启时清空
                    for slot_id, info in state.get("active_slots", {}).items():
                        self.active_slots[slot_id] = info
                        slot_num = info["slot_num"]
                        if slot_num in self.available_slots:
                            self.available_slots.remove(slot_num)
                self._state_loaded = True
            except Exception as e:
                print(f"Failed to load state: {e}")
    
    async def save_state(self):
        """保存状态到文件"""
        try:
            state = {
                "active_slots": self.active_slots,
                "saved_at": datetime.now().isoformat()
            }
            async with aiofiles.open(STATE_FILE, 'w') as f:
                await f.write(json.dumps(state, indent=2))
        except Exception as e:
            print(f"Failed to save state: {e}")
    
    async def acquire(self, agent_id: str, timeout: int = DEFAULT_SLOT_TIMEOUT) -> dict:
        """获取槽位，如果没有则等待（线程安全）"""
        queue_id = None
        event = None
        
        async with self._lock:
            # 检查是否正在关闭
            if shutdown_event.is_set():
                raise HTTPException(503, "Server is shutting down")
            
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
                await self.save_state()
                return {
                    "slot_id": slot_id,
                    "status": "acquired",
                    "profile_path": f"/profiles/{agent_id}",
                    "queue_position": 0
                }
            
            # 无可用槽位，加入队列
            queue_id = str(uuid.uuid4())
            event = asyncio.Event()
            self.queue_events[queue_id] = event
            self.queue.append({
                "queue_id": queue_id,
                "agent_id": agent_id,
                "enqueued_at": time.time()
            })
        
        # 在锁外等待（避免阻塞其他操作）
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            # 超时，清理
            async with self._lock:
                self.queue = deque([q for q in self.queue if q["queue_id"] != queue_id])
                self.queue_events.pop(queue_id, None)
            raise HTTPException(503, f"Timeout waiting for slot. Queue length: {len(self.queue)}")
        
        # 被唤醒，获取槽位
        async with self._lock:
            if not self.available_slots:
                # 异常情况：被唤醒但没有槽位
                raise HTTPException(503, "No slot available after wake up")
            
            slot_num = self.available_slots.pop(0)
            slot_id = f"slot_{slot_num}"
            self.active_slots[slot_id] = {
                "agent_id": agent_id,
                "slot_num": slot_num,
                "started_at": time.time(),
                "profile_path": f"/profiles/{agent_id}"
            }
            await self.save_state()
            return {
                "slot_id": slot_id,
                "status": "acquired",
                "profile_path": f"/profiles/{agent_id}",
                "queue_position": 0
            }
    
    async def release(self, slot_id: str) -> dict:
        """释放槽位，自动唤醒下一个等待者"""
        async with self._lock:
            if slot_id not in self.active_slots:
                raise HTTPException(404, f"Slot {slot_id} not found")
            
            info = self.active_slots.pop(slot_id)
            slot_num = info["slot_num"]
            agent_id = info["agent_id"]
            running_time = int(time.time() - info["started_at"])
            
            self.available_slots.append(slot_num)
            await self.save_state()
            
            # 唤醒下一个等待者（在锁内设置 event，但不会阻塞）
            next_agent = None
            if self.queue:
                next_item = self.queue.popleft()
                queue_id = next_item["queue_id"]
                next_agent = next_item["agent_id"]
                if queue_id in self.queue_events:
                    self.queue_events[queue_id].set()
                    del self.queue_events[queue_id]
        
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
    
    async def shutdown(self):
        """优雅关闭：清理所有等待者"""
        async with self._lock:
            # 唤醒所有等待者（他们会收到 503）
            for queue_id, event in self.queue_events.items():
                event.set()
            self.queue_events.clear()
            self.queue.clear()
            await self.save_state()

slot_manager = SlotManager(MAX_CONCURRENT)

# ============ Context 管理 ============

contexts: Dict[str, dict] = {}

class ContextInfo(BaseModel):
    agent_id: str
    profile_path: str
    created_at: datetime
    last_accessed: float
    timeout: int = DEFAULT_TIMEOUT

class ContextCreate(BaseModel):
    agent_id: str
    timeout: Optional[int] = DEFAULT_TIMEOUT

class ExecuteStartRequest(BaseModel):
    agent_id: str
    timeout: Optional[int] = DEFAULT_SLOT_TIMEOUT

class ExecuteEndRequest(BaseModel):
    slot_id: str

# ============ API 端点 ============

@app.post("/execute/start")
async def start_execution(request: ExecuteStartRequest):
    """获取槽位（自动排队）"""
    timeout = request.timeout or DEFAULT_SLOT_TIMEOUT
    result = await slot_manager.acquire(request.agent_id, timeout)
    return JSONResponse(result)

@app.post("/execute/end")
async def end_execution(request: ExecuteEndRequest):
    """释放槽位（自动唤醒下一个）"""
    result = await slot_manager.release(request.slot_id)
    return JSONResponse(result)

@app.get("/execute/status")
async def get_execution_status():
    """获取当前状态"""
    return slot_manager.get_status()

@app.post("/contexts/create")
async def create_context(request: ContextCreate):
    """创建 Context"""
    agent_id = request.agent_id
    timeout = request.timeout or DEFAULT_TIMEOUT
    
    if agent_id in contexts:
        contexts[agent_id]["last_accessed"] = time.time()
        return {
            "agent_id": agent_id,
            "status": "exists",
            "profile_path": contexts[agent_id]["profile_path"],
            "antibot_enabled": True
        }
    
    profile_path = PROFILES_DIR / agent_id
    profile_path.mkdir(parents=True, exist_ok=True)
    
    contexts[agent_id] = {
        "agent_id": agent_id,
        "profile_path": str(profile_path),
        "created_at": datetime.now(),
        "last_accessed": time.time(),
        "timeout": timeout
    }
    
    return {
        "agent_id": agent_id,
        "status": "created",
        "profile_path": str(profile_path),
        "antibot_enabled": True
    }

@app.get("/contexts")
async def list_contexts():
    """列出所有 Context"""
    return {
        "total": len(contexts),
        "contexts": list(contexts.values())
    }

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

@app.get("/metrics")
async def metrics():
    """Prometheus 指标"""
    status = slot_manager.get_status()
    return JSONResponse(
        content={
            "slot_max": status["max_concurrent"],
            "slot_active": status["active_count"],
            "slot_available": status["available_count"],
            "queue_length": status["queue_length"],
            "contexts_total": len(contexts)
        },
        media_type="application/json"
    )

@app.get("/antibot/script")
async def get_antibot_script():
    """获取反爬脚本"""
    antibot_path = Path("/opt/antibot.js")
    if not antibot_path.exists():
        raise HTTPException(status_code=404, detail="Antibot script not found")
    
    async with aiofiles.open(antibot_path, 'r') as f:
        content = await f.read()
    
    # 提取版本号
    version = "unknown"
    for line in content.split('\n')[:20]:
        if '版本:' in line or 'version:' in line.lower():
            version = line.split(':')[-1].strip().strip("'\"")
            break
    
    return {
        "script": content,
        "version": version,
        "size": len(content)
    }

# ============ 生命周期 ============

@app.on_event("startup")
async def startup():
    """启动时加载状态"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    await slot_manager.load_state()

@app.on_event("shutdown")
async def shutdown():
    """优雅关闭"""
    shutdown_event.set()
    await slot_manager.shutdown()

# ============ 信号处理 ============

def signal_handler(sig, frame):
    """处理终止信号"""
    print(f"Received signal {sig}, shutting down...")
    shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
