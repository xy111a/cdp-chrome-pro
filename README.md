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

镜像内置 `antibot.js` 反爬脚本（v2.0.0），支持平台特定功能隔离：

### 设计原则

- **通用功能**：对所有站点生效，不影响正常浏览
- **平台特定功能**：通过域名检测自动启用，避免对其他站点造成影响
- **人类行为 API**：供外部调用的高级行为模拟

### 通用反检测功能（所有站点）

| 功能 | 说明 |
|------|------|
| WebGL 指纹随机 | 伪装显卡信息 (Intel Iris OpenGL Engine) |
| Canvas 噪声注入 | 防止 Canvas 指纹追踪 |
| Navigator 伪装 | 移除 webdriver 标记，伪装 plugins/languages |
| CDP 特征隐藏 | 删除所有 Selenium/Puppeteer 特征变量 |
| 时间戳一致性 | 确保 performance.now() 和 Date.now() 一致 |
| 权限 API 伪装 | 模拟真实浏览器的权限响应 |
| Screen 属性伪装 | 固定屏幕分辨率 1920x1080 |

### 平台特定功能

通过域名检测自动启用，当前支持：

| 平台 | 域名 | 功能 |
|------|------|------|
| 小红书 | xiaohongshu.com, *.xiaohongshu.com | 检测脚本拦截、全局变量覆盖 |

#### 小红书特定功能

- 覆盖检测相关全局变量 (`_xcs`, `_xmta`, `_xhs_tracker`)
- 拦截可疑检测脚本（含 `detect`, `antibot`, `security-check` 关键字）
- 阻止 webdriver 检测脚本注入

### 扩展其他平台

在 `antibot.js` 中添加新平台配置：

```javascript
const CONFIG = {
    platformSpecific: {
        'xiaohongshu.com': {
            enabled: true,
            features: ['xhsGlobals', 'scriptBlocking']
        },
        // 添加新平台
        'example.com': {
            enabled: true,
            features: ['customFeature1', 'customFeature2']
        }
    }
};

// 实现平台特定功能
const applyPlatformSpecific = (platform) => {
    // ...
    if (platform.features.includes('customFeature1')) {
        // 你的自定义逻辑
    }
};
```

### 人类行为模拟 API

脚本自动挂载 `window.humanAPI`，供 Playwright 等外部调用：

```javascript
// 鼠标移动（贝塞尔曲线轨迹）
await window.humanAPI.moveTo(500, 300, { duration: 500 });

// 点击元素（先移动再点击）
await window.humanAPI.click(element);

// 模拟输入（随机延迟）
await window.humanAPI.type(inputElement, 'Hello World', {
    minDelay: 30,
    maxDelay: 120
});

// 滚动
await window.humanAPI.scroll('down', 500);

// 随机等待
await window.humanAPI.randomDelay(1000, 3000);
```

#### Playwright 集成示例

```python
# 在 Playwright 中使用 humanAPI
page.goto("https://xiaohongshu.com")

# 获取元素并模拟人类点击
element = page.query_selector(".search-input")
page.evaluate("""
    (el) => window.humanAPI.click(el)
""", element)

# 模拟人类输入
page.evaluate("""
    (el) => window.humanAPI.type(el, '搜索关键词', { minDelay: 50, maxDelay: 150 })
""", element)
```

### 调试模式

启用调试日志：

```javascript
// 在 antibot.js 中修改
const CONFIG = {
    debug: true,  // 开启调试日志
    // ...
};
```

控制台将输出 `[AntiBot]` 前缀的日志信息。

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

- **2026-03-10**: v2.0.0 antibot.js 重构，支持平台特定功能隔离、人类行为 API
- **2026-03-08**: v3 版本，修复竞态条件，添加状态持久化
- **2026-03-08**: v2 版本，3 并发 + 排队协调
- **2026-03-08**: v1 版本，基础 Context 管理
