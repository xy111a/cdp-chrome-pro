FROM zenika/alpine-chrome:latest

USER root

# 安装 Python 和依赖
RUN apk add --no-cache python3 py3-pip xvfb socat x11vnc novnc websockify curl

# 安装 Python 包 (使用 pip with --break-system-packages)
RUN pip3 install --no-cache-dir --break-system-packages fastapi uvicorn[standard] psutil aiofiles

# 创建工作目录
RUN mkdir -p /opt /profiles
RUN chown chrome:chrome /opt /profiles

# 复制脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY context-manager.py /opt/context-manager.py
RUN chmod +x /opt/context-manager.py

COPY antibot.js /opt/antibot.js

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

USER chrome

WORKDIR /opt

# 暴露端口
# 6080: noVNC
# 8000: Context Manager API
# 9333: CDP Proxy
EXPOSE 6080 8000 9333

ENTRYPOINT ["/entrypoint.sh"]