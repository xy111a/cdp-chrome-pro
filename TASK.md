# CDP Chrome Pro 镜像开发任务

## 目标
增强现有 CDP Chrome 镜像，支持多 Agent 共享、Context 隔离、内置反爬。

## 架构
```
单容器多 Context:
- Chromium 单进程
- 每个 Agent 独立 Context
- Profile 目录隔离
- 内置反爬脚本
```

## 功能需求

### 1. Context 管理脚本
文件: /opt/context-manager.py
- 创建 Context（指定 agent_id）
- 获取 Context（复用已有）
- 销毁 Context（清理资源）
- 列出 Context（状态查看）
- 超时清理（自动回收）

### 2. 反爬脚本内置
文件: /opt/antibot.js
- WebGL 指纹随机
- Canvas 噪声注入
- Navigator 属性伪装
- 行为模拟（随机延迟、滚动）

### 3. Profile 管理
目录: /profiles/{agent_id}/
- Cookies 持久化
- LocalStorage 隔离
- 登录态保存

### 4. Docker 增强
文件: Dockerfile
- 基于 zenika/alpine-chrome
- 安装 Python（Context 管理）
- 复制脚本
- 健康检查

### 5. Docker Compose
文件: docker-compose.yml
- 资源限制（CPU 2核，内存 2G）
- Profile 目录挂载
- 端口映射

## 文件结构
```
cdp-chrome-pro/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── context-manager.py
├── antibot.js
├── antibot.py
└── TASK.md
```

## 验收标准
1. docker-compose up -d 成功启动
2. Context 创建 API 可用
3. 多 Agent 可同时连接
4. Profile 持久化正常
5. 反爬脚本生效

## 参考
现有镜像: /volume1/docker/cdp-browser/
