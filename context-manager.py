#!/usr/bin/env python3
"""
CDP Chrome Pro Context Manager
管理多个 Agent 的 Context 和 Profile
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
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import psutil

app = FastAPI(title="CDP Chrome Pro Context Manager")

PROFILES_DIR = Path("/profiles")
STATE_FILE = Path("/profiles/state.json")
DEFAULT_TIMEOUT = 3600  # 1 hour

# Context 状态存储
contexts: Dict[str, dict] = {}


class ContextCreate(BaseModel):
    agent_id: str
    timeout: Optional[int] = DEFAULT_TIMEOUT


class ContextInfo(BaseModel):
    agent_id: str
    created_at: str
    last_accessed: str
    profile_path: str
    status: str


def load_state():
    """加载 Context 状态"""
    global contexts
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                contexts = json.load(f)
        except Exception as e:
            print(f"Failed to load state: {e}")
            contexts = {}


async def save_state():
    """保存 Context 状态"""
    try:
        async with aiofiles.open(STATE_FILE, 'w') as f:
            await f.write(json.dumps(contexts, indent=2))
    except Exception as e:
        print(f"Failed to save state: {e}")


async def cleanup_expired_contexts():
    """清理超时的 Context"""
    now = datetime.now().timestamp()
    expired = []

    for agent_id, ctx in contexts.items():
        if now - ctx.get('last_accessed', 0) > ctx.get('timeout', DEFAULT_TIMEOUT):
            expired.append(agent_id)

    for agent_id in expired:
        await delete_context(agent_id, background=False)

    if expired:
        print(f"Cleaned up {len(expired)} expired contexts")


async def delete_context(agent_id: str, background: bool = True):
    """删除 Context"""
    if agent_id not in contexts:
        return

    profile_path = Path(contexts[agent_id]['profile_path'])

    # 删除 profile 目录
    if profile_path.exists() and profile_path != PROFILES_DIR / "default":
        try:
            shutil.rmtree(profile_path)
            print(f"Deleted profile: {profile_path}")
        except Exception as e:
            print(f"Failed to delete profile {profile_path}: {e}")

    # 从状态中移除
    del contexts[agent_id]

    if background:
        await save_state()


@app.on_event("startup")
async def startup_event():
    """启动时加载状态并清理过期 Context"""
    PROFILES_DIR.mkdir(exist_ok=True)
    load_state()
    await cleanup_expired_contexts()


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时保存状态"""
    await save_state()


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "contexts_count": len(contexts),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent
    }


@app.post("/contexts/create")
async def create_context(request: ContextCreate):
    """创建 Context"""
    agent_id = request.agent_id

    if agent_id in contexts:
        # 复用已有 Context
        contexts[agent_id]['last_accessed'] = datetime.now().timestamp()
        await save_state()
        return {
            "agent_id": agent_id,
            "status": "reused",
            "profile_path": contexts[agent_id]['profile_path']
        }

    # 创建新的 profile 目录
    profile_path = PROFILES_DIR / agent_id
    profile_path.mkdir(exist_ok=True)

    # 读取 antibot.js 内容
    antibot_path = Path("/opt/antibot.js")
    antibot_content = ""
    if antibot_path.exists():
        with open(antibot_path, 'r') as f:
            antibot_content = f.read()

    # 保存 Context 状态
    contexts[agent_id] = {
        "agent_id": agent_id,
        "created_at": datetime.now().isoformat(),
        "last_accessed": datetime.now().timestamp(),
        "profile_path": str(profile_path),
        "status": "active",
        "timeout": request.timeout
    }

    await save_state()

    return {
        "agent_id": agent_id,
        "status": "created",
        "profile_path": str(profile_path),
        "antibot_enabled": bool(antibot_content)
    }


@app.get("/contexts/{agent_id}")
async def get_context(agent_id: str):
    """获取 Context 信息"""
    if agent_id not in contexts:
        raise HTTPException(status_code=404, detail="Context not found")

    # 更新访问时间
    contexts[agent_id]['last_accessed'] = datetime.now().timestamp()
    await save_state()

    return contexts[agent_id]


@app.delete("/contexts/{agent_id}")
async def delete_context_endpoint(agent_id: str, background_tasks: BackgroundTasks):
    """删除 Context"""
    if agent_id not in contexts:
        raise HTTPException(status_code=404, detail="Context not found")

    background_tasks.add_task(delete_context, agent_id)

    return {"agent_id": agent_id, "status": "deleting"}


@app.get("/contexts")
async def list_contexts():
    """列出所有 Context"""
    return {
        "total": len(contexts),
        "contexts": list(contexts.values())
    }


@app.post("/contexts/cleanup")
async def cleanup_contexts(background_tasks: BackgroundTasks):
    """清理超时的 Context"""
    background_tasks.add_task(cleanup_expired_contexts)
    return {"status": "cleanup_started"}


@app.get("/antibot/script")
async def get_antibot_script():
    """获取反爬脚本"""
    antibot_path = Path("/opt/antibot.js")
    if not antibot_path.exists():
        raise HTTPException(status_code=404, detail="Antibot script not found")

    with open(antibot_path, 'r') as f:
        content = f.read()

    return {"script": content}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)