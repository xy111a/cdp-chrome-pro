/**
 * CDP Chrome Pro - Anti-Bot Detection Script
 * 通用反检测脚本，支持平台特定功能隔离
 * 
 * 设计原则：
 * - 通用功能：对所有站点生效
 * - 平台特定功能：通过域名检测自动启用
 * - 导出 API：供外部调用的人类行为模拟
 * 
 * 版本: 2.0.0
 */

(function() {
    'use strict';

    // ============ 配置 ============
    const CONFIG = {
        debug: false,  // 是否输出调试日志
        platformSpecific: {
            'xiaohongshu.com': {
                enabled: true,
                features: ['xhsGlobals', 'scriptBlocking']
            },
            'www.xiaohongshu.com': {
                enabled: true,
                features: ['xhsGlobals', 'scriptBlocking']
            },
            'creator.xiaohongshu.com': {
                enabled: true,
                features: ['xhsGlobals', 'scriptBlocking']
            }
            // 可扩展其他平台
        }
    };

    // 日志函数
    const log = (...args) => {
        if (CONFIG.debug) {
            console.log('[AntiBot]', ...args);
        }
    };

    // 工具函数
    const random = (min, max) => Math.random() * (max - min) + min;
    const randomString = (length) => {
        const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        let result = '';
        for (let i = 0; i < length; i++) {
            result += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return result;
    };

    // 检测当前平台
    const detectPlatform = () => {
        const hostname = window.location.hostname;
        for (const [domain, config] of Object.entries(CONFIG.platformSpecific)) {
            if (hostname === domain || hostname.endsWith('.' + domain)) {
                return { domain, ...config };
            }
        }
        return null;
    };

    // ============ 通用反检测功能（所有站点） ============

    /**
     * WebGL 指纹随机化
     * 防止通过 WebGL 指纹追踪
     */
    const randomizeWebGL = () => {
        try {
            // WebGL 1
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // UNMASKED_VENDOR_WEBGL
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                // UNMASKED_RENDERER_WEBGL
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.call(this, parameter);
            };

            // WebGL 2
            if (typeof WebGL2RenderingContext !== 'undefined') {
                const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                    return getParameter2.call(this, parameter);
                };
            }

            log('WebGL fingerprint randomized');
        } catch (e) {
            log('WebGL randomization failed:', e.message);
        }
    };

    /**
     * Canvas 噪声注入
     * 防止 Canvas 指纹追踪
     */
    const addCanvasNoise = () => {
        try {
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                const context = this.getContext('2d');
                if (context && this.width > 0 && this.height > 0) {
                    try {
                        const imageData = context.getImageData(0, 0, this.width, this.height);
                        const data = imageData.data;
                        // 添加轻微噪声，每次不同
                        for (let i = 0; i < data.length; i += 4) {
                            data[i] = Math.min(255, Math.max(0, data[i] + (Math.random() * 2 - 1)));
                            data[i + 1] = Math.min(255, Math.max(0, data[i + 1] + (Math.random() * 2 - 1)));
                            data[i + 2] = Math.min(255, Math.max(0, data[i + 2] + (Math.random() * 2 - 1)));
                        }
                        context.putImageData(imageData, 0, 0);
                    } catch (e) {
                        // tainted canvas, skip
                    }
                }
                return originalToDataURL.apply(this, arguments);
            };

            log('Canvas noise injection enabled');
        } catch (e) {
            log('Canvas noise failed:', e.message);
        }
    };

    /**
     * Navigator 属性伪装
     * 移除自动化特征
     */
    const maskNavigator = () => {
        try {
            // 移除 webdriver 标记 - 最重要的反检测
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
                configurable: false
            });

            // 伪装 plugins
            const fakePlugins = [
                { 
                    name: 'Chrome PDF Plugin', 
                    filename: 'internal-pdf-viewer',
                    description: 'Portable Document Format',
                    length: 1
                },
                { 
                    name: 'Chrome PDF Viewer', 
                    filename: '',
                    description: '',
                    length: 1
                },
                { 
                    name: 'Native Client', 
                    filename: '',
                    description: '',
                    length: 2
                }
            ];
            Object.defineProperty(fakePlugins, 'length', { get: () => 3, configurable: false });
            Object.defineProperty(fakePlugins, 'item', { 
                value: (index) => fakePlugins[index] || null,
                configurable: false 
            });
            Object.defineProperty(fakePlugins, 'namedItem', { 
                value: (name) => fakePlugins.find(p => p.name === name) || null,
                configurable: false 
            });

            Object.defineProperty(navigator, 'plugins', {
                get: () => fakePlugins,
                configurable: false
            });

            // 伪装 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en'],
                configurable: false
            });

            // 伪装 platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'MacIntel',
                configurable: false
            });

            // 伪装 hardwareConcurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: false
            });

            // 伪装 deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: false
            });

            log('Navigator properties masked');
        } catch (e) {
            log('Navigator masking failed:', e.message);
        }
    };

    /**
     * CDP 连接特征隐藏
     * 移除所有 webdriver 和 CDP 相关的全局变量
     */
    const hideCDPFeatures = () => {
        try {
            // 需要删除的属性列表
            const cdpProps = [
                '__webdriver_script_fn',
                '__driver_evaluate',
                '__webdriver_evaluate',
                '__selenium_evaluate',
                '__fxdriver_evaluate',
                '__driver_unwrapped',
                '__webdriver_unwrapped',
                '__selenium_unwrapped',
                '__fxdriver_unwrapped',
                '__lastWatirAlert',
                '__lastWatirConfirm',
                '__lastWatirPrompt',
                '_Selenium_IDE_Recorder',
                '_selenium',
                'calledSelenium',
                '$cdc_asdjflasutopfhvcZLmcfl_',
                '$chrome_asyncScriptInfo',
                '__$webdriverAsyncExecutor',
                '__nightmare',
                '__phantomas',
                '_phantom',
                'callPhantom',
                '__puppeteer_evaluation_script__'
            ];

            cdpProps.forEach(prop => {
                try {
                    delete window[prop];
                    delete navigator[prop];
                    delete document[prop];
                } catch (e) {
                    // 某些属性可能不可删除
                }
            });

            // 覆盖 navigator.webdriver（再次确保）
            try {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: false
                });
            } catch (e) {
                // 已定义，忽略
            }

            // 隐藏 chrome.runtime（但保留 chrome 对象，因为正常浏览器也有）
            if (window.chrome && window.chrome.runtime) {
                try {
                    Object.defineProperty(window.chrome, 'runtime', {
                        get: () => undefined,
                        configurable: false
                    });
                } catch (e) {}
            }

            log('CDP features hidden');
        } catch (e) {
            log('CDP hiding failed:', e.message);
        }
    };

    /**
     * 时间戳一致性修复
     * 确保 performance.now() 和 Date.now() 保持一致
     */
    const fixTimestampConsistency = () => {
        try {
            const now = Date.now();
            const performanceNow = performance.now();
            const offset = now - Math.round(performanceNow);

            // 覆盖 performance.now()
            Object.defineProperty(performance, 'now', {
                get: () => {
                    return () => {
                        const base = Date.now() - offset;
                        // 添加微小随机性模拟真实情况
                        return base + (Math.random() - 0.5) * 0.1;
                    };
                },
                configurable: false
            });

            log('Timestamp consistency fixed');
        } catch (e) {
            log('Timestamp fix failed:', e.message);
        }
    };

    /**
     * 权限 API 伪装
     */
    const maskPermissions = () => {
        try {
            if (navigator.permissions && navigator.permissions.query) {
                const originalQuery = navigator.permissions.query.bind(navigator.permissions);
                navigator.permissions.query = (parameters) => {
                    return originalQuery(parameters).then(result => {
                        // 对于 notifications，返回当前实际权限状态
                        if (parameters.name === 'notifications') {
                            return { 
                                state: Notification.permission,
                                onchange: null 
                            };
                        }
                        // 对于其他权限，返回 prompt
                        return { 
                            state: 'prompt',
                            onchange: null 
                        };
                    }).catch(() => ({
                        state: 'prompt',
                        onchange: null
                    }));
                };
            }
            log('Permissions API masked');
        } catch (e) {
            log('Permissions masking failed:', e.message);
        }
    };

    /**
     * Screen 属性伪装
     */
    const maskScreen = () => {
        try {
            Object.defineProperty(screen, 'width', { get: () => 1920, configurable: false });
            Object.defineProperty(screen, 'height', { get: () => 1080, configurable: false });
            Object.defineProperty(screen, 'availWidth', { get: () => 1920, configurable: false });
            Object.defineProperty(screen, 'availHeight', { get: () => 1055, configurable: false });
            Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: false });
            Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: false });

            log('Screen properties masked');
        } catch (e) {
            log('Screen masking failed:', e.message);
        }
    };

    // ============ 平台特定功能 ============

    /**
     * 小红书特定检测绕过
     * 仅在 xiaohongshu.com 域名下启用
     */
    const bypassXHSDetection = () => {
        try {
            // 覆盖可能用于检测的全局变量
            const xhsGlobals = ['_xcs', '_xmta', '_xhs_tracker'];
            xhsGlobals.forEach(prop => {
                try {
                    Object.defineProperty(window, prop, {
                        get: () => undefined,
                        set: () => {},
                        configurable: true
                    });
                } catch (e) {}
            });

            // 监控并阻止可疑的检测脚本
            const originalAppendChild = Element.prototype.appendChild;
            Element.prototype.appendChild = function(child) {
                if (child instanceof HTMLScriptElement) {
                    const src = child.src || '';
                    const content = child.textContent || '';
                    // 阻止已知的检测脚本
                    if (src.includes('detect') || 
                        src.includes('antibot') || 
                        src.includes('security-check') ||
                        content.includes('webdriver') ||
                        content.includes('__selenium')) {
                        log('Blocked suspicious script:', src || 'inline');
                        return child;
                    }
                }
                return originalAppendChild.call(this, child);
            };

            const originalCreateElement = document.createElement.bind(document);
            document.createElement = function(tagName) {
                const element = originalCreateElement(tagName);
                if (tagName.toLowerCase() === 'script') {
                    const originalSetAttribute = element.setAttribute.bind(element);
                    element.setAttribute = function(name, value) {
                        if (name === 'src' && (
                            value.includes('detect') || 
                            value.includes('antibot') ||
                            value.includes('security-check')
                        )) {
                            log('Blocked script src:', value);
                            return;
                        }
                        return originalSetAttribute(name, value);
                    };
                }
                return element;
            };

            log('XHS detection bypassed');
        } catch (e) {
            log('XHS bypass failed:', e.message);
        }
    };

    /**
     * 平台特定功能调度器
     */
    const applyPlatformSpecific = (platform) => {
        if (!platform || !platform.enabled) return;

        log(`Applying platform-specific features for: ${platform.domain}`);

        if (platform.features.includes('xhsGlobals')) {
            bypassXHSDetection();
        }
        // 可扩展其他平台特定功能
    };

    // ============ 人类行为模拟 API（供外部调用）============

    /**
     * 人类行为模拟 API
     * 挂载到 window.humanAPI 供 Playwright 等外部调用
     */
    const HumanAPI = {
        /**
         * 模拟人类鼠标移动（贝塞尔曲线）
         * @param {number} targetX - 目标 X 坐标
         * @param {number} targetY - 目标 Y 坐标
         * @param {Object} options - 选项 { duration: ms }
         */
        async moveTo(targetX, targetY, options = {}) {
            const duration = options.duration || 300 + Math.random() * 400;
            const startX = this._lastX || Math.random() * window.innerWidth;
            const startY = this._lastY || Math.random() * window.innerHeight;
            const steps = Math.max(10, Math.floor(duration / 16));

            // 贝塞尔曲线控制点
            const cp1x = startX + (targetX - startX) * (0.2 + Math.random() * 0.3);
            const cp1y = startY + (targetY - startY) * (0.1 + Math.random() * 0.4);
            const cp2x = startX + (targetX - startX) * (0.6 + Math.random() * 0.2);
            const cp2y = startY + (targetY - startY) * (0.5 + Math.random() * 0.4);

            for (let i = 0; i <= steps; i++) {
                const t = i / steps;
                const x = Math.pow(1-t, 3) * startX + 
                         3 * Math.pow(1-t, 2) * t * cp1x + 
                         3 * (1-t) * Math.pow(t, 2) * cp2x + 
                         Math.pow(t, 3) * targetX;
                const y = Math.pow(1-t, 3) * startY + 
                         3 * Math.pow(1-t, 2) * t * cp1y + 
                         3 * (1-t) * Math.pow(t, 2) * cp2y + 
                         Math.pow(t, 3) * targetY;

                // 添加随机抖动
                const jitterX = (Math.random() - 0.5) * 2;
                const jitterY = (Math.random() - 0.5) * 2;

                const element = document.elementFromPoint(x + jitterX, y + jitterY);
                if (element) {
                    element.dispatchEvent(new MouseEvent('mousemove', {
                        bubbles: true,
                        cancelable: true,
                        clientX: x + jitterX,
                        clientY: y + jitterY,
                        movementX: (x - (this._lastX || startX)) + jitterX,
                        movementY: (y - (this._lastY || startY)) + jitterY
                    }));
                }

                this._lastX = x;
                this._lastY = y;
                await new Promise(r => setTimeout(r, 16 + Math.random() * 8));
            }
        },

        /**
         * 模拟人类点击
         * @param {Element} element - 目标元素
         * @param {Object} options - 选项
         */
        async click(element, options = {}) {
            if (!element) return;

            const rect = element.getBoundingClientRect();
            const x = rect.left + rect.width * (0.3 + Math.random() * 0.4);
            const y = rect.top + rect.height * (0.3 + Math.random() * 0.4);

            // 先移动到元素
            await this.moveTo(x, y, { duration: 200 + Math.random() * 200 });

            // 短暂停留
            await new Promise(r => setTimeout(r, 50 + Math.random() * 100));

            // 模拟 mousedown -> mouseup -> click 序列
            element.dispatchEvent(new MouseEvent('mousedown', {
                bubbles: true, cancelable: true, clientX: x, clientY: y
            }));

            await new Promise(r => setTimeout(r, 50 + Math.random() * 50));

            element.dispatchEvent(new MouseEvent('mouseup', {
                bubbles: true, cancelable: true, clientX: x, clientY: y
            }));

            element.dispatchEvent(new MouseEvent('click', {
                bubbles: true, cancelable: true, clientX: x, clientY: y
            }));
        },

        /**
         * 模拟人类输入
         * @param {Element} element - 目标输入框
         * @param {string} text - 要输入的文本
         * @param {Object} options - 选项 { minDelay, maxDelay }
         */
        async type(element, text, options = {}) {
            if (!element) return;

            const minDelay = options.minDelay || 30;
            const maxDelay = options.maxDelay || 120;

            element.focus();

            for (const char of text) {
                const key = char;
                const keyCode = char.charCodeAt(0);

                element.dispatchEvent(new KeyboardEvent('keydown', {
                    bubbles: true, key, keyCode, which: keyCode
                }));

                element.dispatchEvent(new KeyboardEvent('keypress', {
                    bubbles: true, key, keyCode, which: keyCode
                }));

                element.value += char;
                element.dispatchEvent(new Event('input', { bubbles: true }));

                element.dispatchEvent(new KeyboardEvent('keyup', {
                    bubbles: true, key, keyCode, which: keyCode
                }));

                await new Promise(r => setTimeout(r, minDelay + Math.random() * (maxDelay - minDelay)));
            }

            element.dispatchEvent(new Event('change', { bubbles: true }));
        },

        /**
         * 模拟人类滚动
         * @param {string} direction - 'down' 或 'up'
         * @param {number} distance - 滚动距离（像素）
         */
        async scroll(direction = 'down', distance = 500) {
            const steps = 8 + Math.floor(Math.random() * 5);
            const stepDistance = distance / steps;

            for (let i = 0; i < steps; i++) {
                window.scrollBy({
                    top: direction === 'down' ? stepDistance : -stepDistance,
                    left: 0,
                    behavior: 'instant'
                });

                await new Promise(r => setTimeout(r, 80 + Math.random() * 120));
            }
        },

        /**
         * 等待随机时间
         * @param {number} min - 最小毫秒
         * @param {number} max - 最大毫秒
         */
        async randomDelay(min, max) {
            await new Promise(r => setTimeout(r, random(min, max)));
        },

        // 内部状态
        _lastX: null,
        _lastY: null
    };

    // ============ 后台行为模拟（可选，轻量级）============

    /**
     * 轻量级后台行为模拟
     * 仅在空闲时随机触发，不干扰正常操作
     */
    const initBackgroundBehavior = () => {
        let lastActivity = Date.now();

        // 监听用户活动
        ['mousemove', 'click', 'keydown', 'scroll'].forEach(event => {
            document.addEventListener(event, () => {
                lastActivity = Date.now();
            }, { passive: true });
        });

        // 仅在长时间无活动时模拟
        setInterval(() => {
            if (Date.now() - lastActivity > 30000) { // 30秒无活动
                // 随机滚动一点
                if (Math.random() > 0.7) {
                    window.scrollBy(0, random(-50, 50));
                }
            }
        }, 10000); // 每10秒检查一次

        log('Background behavior initialized');
    };

    // ============ 初始化 ============

    const init = () => {
        try {
            // 1. 通用反检测功能（所有站点）
            randomizeWebGL();
            addCanvasNoise();
            maskNavigator();
            hideCDPFeatures();
            fixTimestampConsistency();
            maskPermissions();
            maskScreen();

            // 2. 平台特定功能
            const platform = detectPlatform();
            if (platform) {
                applyPlatformSpecific(platform);
            }

            // 3. 挂载人类行为 API
            window.humanAPI = HumanAPI;

            // 4. 导出工具函数
            window.antiBot = {
                version: '2.0.0',
                platform: platform ? platform.domain : 'generic',
                features: [
                    'webgl', 'canvas', 'navigator', 'cdp', 'timestamp', 
                    'permissions', 'screen', 'humanAPI'
                ],
                utils: {
                    random,
                    randomString
                }
            };

            // 5. 可选：轻量级后台行为
            initBackgroundBehavior();

            log('Anti-bot initialized successfully', {
                platform: platform ? platform.domain : 'generic'
            });

        } catch (e) {
            console.error('[AntiBot] Initialization failed:', e);
        }
    };

    // DOM 加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
