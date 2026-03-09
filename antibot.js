/**
 * CDP Chrome Pro - Anti-Bot Detection Script
 * 注入到页面以绕过自动化检测
 */

(function() {
    'use strict';

    // 随机数生成器
    const random = (min, max) => Math.random() * (max - min) + min;

    // 随机字符串生成
    const randomString = (length) => {
        const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        let result = '';
        for (let i = 0; i < length; i++) {
            result += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return result;
    };

    // WebGL 指纹随机化
    const randomizeWebGL = () => {
        try {
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) { // UNMASKED_VENDOR_WEBGL
                    return 'Intel Inc.';
                }
                if (parameter === 37446) { // UNMASKED_RENDERER_WEBGL
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.call(this, parameter);
            };
        } catch (e) {
            console.log('WebGL randomization failed:', e);
        }
    };

    // Canvas 噪声注入
    const addCanvasNoise = () => {
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            const context = this.getContext('2d');
            if (context) {
                const imageData = context.getImageData(0, 0, this.width, this.height);
                const data = imageData.data;
                for (let i = 0; i < data.length; i += 4) {
                    // 添加轻微噪声
                    data[i] += Math.random() * 2 - 1;
                    data[i + 1] += Math.random() * 2 - 1;
                    data[i + 2] += Math.random() * 2 - 1;
                }
                context.putImageData(imageData, 0, 0);
            }
            return originalToDataURL.apply(this, arguments);
        };
    };

    // Navigator 属性伪装
    const伪装Navigator = () => {
        // 移除 webdriver 标记
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false
        });

        // 随机化 plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', description: '' },
                    { name: 'Native Client', description: '' }
                ];
                return plugins;
            }
        });

        // 随机化 languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en']
        });

        // 添加 plugins 长度
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', description: '' },
                    { name: 'Native Client', description: '' }
                ];
                Object.defineProperty(plugins, 'length', { get: () => 3 });
                return plugins;
            }
        });
    };

    // 行为模拟 - 随机鼠标移动
    const simulateMouseMove = () => {
        let lastMove = Date.now();
        document.addEventListener('mousemove', (e) => {
            lastMove = Date.now();
        });

        // 随机触发鼠标移动
        setInterval(() => {
            if (Date.now() - lastMove > random(5000, 15000)) {
                const event = new MouseEvent('mousemove', {
                    bubbles: true,
                    cancelable: true,
                    clientX: random(100, window.innerWidth - 100),
                    clientY: random(100, window.innerHeight - 100)
                });
                document.dispatchEvent(event);
                lastMove = Date.now();
            }
        }, random(2000, 5000));
    };

    // 行为模拟 - 随机滚动
    const simulateScroll = () => {
        setInterval(() => {
            if (Math.random() > 0.7) {
                const scrollAmount = random(-200, 200);
                window.scrollBy(0, scrollAmount);
            }
        }, random(3000, 8000));
    };

    // 随机延迟函数
    const randomDelay = (min, max) => {
        return new Promise(resolve => {
            setTimeout(resolve, random(min, max));
        });
    };

    // 覆盖 Chrome 运行时检测
    const hideChromeRuntime = () => {
        if (window.chrome && window.chrome.runtime) {
            Object.defineProperty(window.chrome, 'runtime', {
                get: () => undefined
            });
        }
    };

    // 权限 API 伪装
    const伪装Permissions = () => {
        const originalQuery = navigator.permissions.query;
        navigator.permissions.query = (parameters) => {
            const result = originalQuery.call(navigator.permissions, parameters);
            return result.then(() => ({
                ...result,
                state: 'prompt',
                onchange: null
            }));
        };
    };

    // 初始化所有反爬措施
    const initAntiBot = () => {
        try {
            randomizeWebGL();
            addCanvasNoise();
            伪装Navigator();
            simulateMouseMove();
            simulateScroll();
            hideChromeRuntime();
            伪装Permissions();
            console.log('Anti-bot measures initialized');
        } catch (e) {
            console.error('Anti-bot initialization failed:', e);
        }
    };

    // 等待页面加载完成
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAntiBot);
    } else {
        initAntiBot();
    }

    // 导出工具函数供外部调用
    window.antiBot = {
        randomDelay,
        randomString,
        random
    };
})();