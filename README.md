# CDP Chrome Pro

多 Agent 共享浏览器容器，支持 3 并发 + 排队协调。

## 特性

- ✅ **多 Agent 共享**：单个 Chromium 进程，多 Context 隔离
- ✅ **3 并发 + 排队**：超过 3 个请求自动排队等待
- ✅ **登录态持久化**：每个 Agent 独立 Profile 目录
- ✅ **反爬内置**：WebGL/Canvas/Navigator 伪装
- ✅ **VNC 可视化**：noVNC 支持，可查看浏览器操作
- ✅ **健康检查**：自动监控 CPU/内存/槽位状态

## 部署位置

- **镜像**：`cdp-chrome-pro:latest`
- **目录**：`/volume1/docker/cdp-chrome-pro/`
- **NAS IP**：192.168.88.247

## 端口映射

| 端口 | 服务 | 说明 |
|------|------|------|
| 6081 | noVNC | 浏览器可视化 |
| 8002 | Context API | 槽位管理 |
| 9334 | CDP | Playwright 连接 |

## 快速开始

### 1. 查看状态

```bash
# 健康检查
curl http://192.168.88.247:8002/health

# 查看槽位状态
curl http://192.168.88.247:8002/execute/status
```

### 2. 获取槽位（自动排队）

```bash
# 获取槽位
curl -X POST http://192.168.88.247:8002/execute/start \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "heming", "timeout": 300}'

# 返回
# {"slot_id": "slot_0", "status": "acquired", "profile_path": "/profiles/heming", "queue_position": 0}

# 释放槽位
curl -X POST http://192.168.88.247:8002/execute/end \
  -H "Content-Type: application/json" \
  -d '{"slot_id": "slot_0"}'
```

### 3. Playwright 连接

```python
from playwright.sync_api import sync_playwright
import httpx

class CoordinatedCrawler:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.api_url = "http://192.168.88.247:8002"
        self.cdp_url = "http://192.168.88.247:9334"
        self.slot_id = None
    
    def __enter__(self):
        # 获取槽位
        resp = httpx.post(f"{self.api_url}/execute/start", json={
            "agent_id": self.agent_id,
            "timeout": 300
        }, timeout=310)
        
        if resp.status_code == 503:
            raise Exception("All slots busy, please retry later")
        
        data = resp.json()
        self.slot_id = data["slot_id"]
        self.profile_path = data["profile_path"]
        
        # 连接浏览器
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
        self.context = self.browser.new_context(user_data_dir=self.profile_path)
        self.page = self.context.new_page()
        
        return self
    
    def __exit__(self, *args):
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        
        # 释放槽位
        if self.slot_id:
            httpx.post(f"{self.api_url}/execute/end", json={
                "slot_id": self.slot_id
            })

# 使用
with CoordinatedCrawler("heming") as crawler:
    crawler.page.goto("https://xiaohongshu.com")
    # ... 爬虫逻辑 ...
```

## API 文档

### POST /execute/start

获取槽位，自动排队。

**请求**:
```json
{
  "agent_id": "heming",
  "timeout": 300  // 可选，默认 300 秒
}
```

**响应**:
```json
{
  "slot_id": "slot_0",
  "status": "acquired",
  "profile_path": "/profiles/heming",
  "queue_position": 0  // 0=立即执行, >0=排队位置
}
```

**错误**:
- 503: 所有槽位忙碌，超时返回

### POST /execute/end

释放槽位，自动唤醒下一个等待者。

**请求**:
```json
{
  "slot_id": "slot_0"
}
```

**响应**:
```json
{
  "status": "released",
  "slot_id": "slot_0",
  "agent_id": "heming",
  "running_time": 120,
  "next_agent": "lingxi"  // 被唤醒的下一个 agent
}
```

### GET /execute/status

查看当前状态。

**响应**:
```json
{
  "max_concurrent": 3,
  "active_count": 2,
  "available_count": 1,
  "queue_length": 3,
  "active_slots": {
    "slot_0": {
      "agent_id": "heming",
      "running_for": 60,
      "profile_path": "/profiles/heming"
    }
  },
  "queued_agents": [
    {"agent_id": "shanhai", "waiting_for": 30}
  ]
}
```

### GET /health

健康检查。

**响应**:
```json
{
  "status": "healthy",
  "contexts_count": 2,
  "active_operations": 2,
  "queued_operations": 3,
  "cpu_percent": 9.5,
  "memory_percent": 53.5
}
```

## VNC 访问

浏览器可视化界面：

```
http://192.168.88.247:6081/vnc.html
```

完整 URL（自动连接）：

```
http://192.168.88.247:6081/vnc.html?autoconnect=true&host=192.168.88.247&port=6081&path=websockify
```

## 文件结构

```
/volume1/docker/cdp-chrome-pro/
├── Dockerfile           # 镜像定义
├── docker-compose.yml   # 容器编排
├── entrypoint.sh        # 启动脚本
├── context-manager.py   # Context 管理服务
├── antibot.js           # 反爬脚本
└── profiles/            # Agent Profile 目录
    ├── heming/
    ├── lingxi/
    └── shanhai/
```

## 反爬能力

镜像内置反爬脚本，自动注入：

| 功能 | 说明 |
|------|------|
| WebGL 指纹随机 | 伪装显卡信息 |
| Canvas 噪声 | 防止指纹追踪 |
| Navigator 伪装 | 移除 webdriver 标记 |
| 行为模拟 | 随机鼠标移动、滚动 |

## 代码审核

详见 [CODE_REVIEW.md](./CODE_REVIEW.md)

- v2: ⭐⭐⭐☆☆ (功能正确但缺少生产环境保护)
- v3: ⭐⭐⭐⭐☆ (已修复主要问题)

## 常见问题

### Q: 如何查看当前有哪些 Agent 在使用？

```bash
curl http://192.168.88.247:8002/execute/status
```

### Q: 排队后如何知道轮到自己？

API 会阻塞等待，直到获取槽位或超时。建议使用 context manager 自动管理。

### Q: 登录态如何持久化？

每个 Agent 使用独立 Profile 目录 `/profiles/{agent_id}/`，登录态自动保存。

### Q: 如何重启容器？

```bash
ssh huajun@192.168.88.247 'cd /volume1/docker/cdp-chrome-pro && docker compose restart'
```

## 更新日志

- **2026-03-08**: v3 版本，修复竞态条件，添加状态持久化
- **2026-03-08**: v2 版本，3 并发 + 排队协调
- **2026-03-08**: v1 版本，基础 Context 管理
