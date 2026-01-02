/**
 * TrueFlow Rendering Monitor
 * Detects white screens, rendering issues, and logs them to console/file
 * Include this script in watch_architecture.html or interactive_flow_explorer.html
 */

class RenderingMonitor {
    constructor() {
        this.logFile = [];
        this.whiteScreenCount = 0;
        this.lastFrameTime = 0;
        this.frameDrops = 0;
        this.glErrors = [];
        this.isMonitoring = false;

        this.init();
    }

    init() {
        this.log('INFO', 'Rendering Monitor initialized');
        this.hookWebGLErrors();
        this.startFrameMonitor();
        this.startWhiteScreenDetector();
        this.hookThreeJSErrors();
        this.isMonitoring = true;

        // Auto-save logs every 5 seconds
        setInterval(() => this.saveLogsToStorage(), 5000);

        // Log summary every 10 seconds
        setInterval(() => this.logSummary(), 10000);
    }

    log(level, message, data = null) {
        const timestamp = new Date().toISOString();
        const entry = { timestamp, level, message, data };
        this.logFile.push(entry);

        // Also console log with color
        const colors = {
            'ERROR': 'color: red; font-weight: bold',
            'WARN': 'color: orange',
            'INFO': 'color: cyan',
            'DEBUG': 'color: gray'
        };
        console.log(`%c[${level}] ${timestamp}: ${message}`, colors[level] || '', data || '');

        // Keep log file manageable
        if (this.logFile.length > 1000) {
            this.logFile = this.logFile.slice(-500);
        }
    }

    hookWebGLErrors() {
        // Hook into WebGL context to catch errors
        const originalGetContext = HTMLCanvasElement.prototype.getContext;
        const monitor = this;

        HTMLCanvasElement.prototype.getContext = function(type, attrs) {
            const ctx = originalGetContext.call(this, type, attrs);

            if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
                if (!ctx) {
                    monitor.log('ERROR', 'WebGL context creation FAILED', { type, attrs });
                    return ctx;
                }

                monitor.log('INFO', 'WebGL context created', { type });

                // Hook getError
                const originalGetError = ctx.getError.bind(ctx);
                ctx.getError = function() {
                    const error = originalGetError();
                    if (error !== ctx.NO_ERROR) {
                        const errorName = monitor.getGLErrorName(ctx, error);
                        monitor.log('ERROR', `WebGL Error: ${errorName}`, { error });
                        monitor.glErrors.push({ time: Date.now(), error: errorName });
                    }
                    return error;
                };

                // Monitor context loss
                this.addEventListener('webglcontextlost', (e) => {
                    monitor.log('ERROR', 'WebGL CONTEXT LOST - This causes white screen!', e);
                    monitor.whiteScreenCount++;
                });

                this.addEventListener('webglcontextrestored', (e) => {
                    monitor.log('WARN', 'WebGL context restored', e);
                });
            }

            return ctx;
        };
    }

    getGLErrorName(gl, error) {
        const errors = {
            [gl.NO_ERROR]: 'NO_ERROR',
            [gl.INVALID_ENUM]: 'INVALID_ENUM',
            [gl.INVALID_VALUE]: 'INVALID_VALUE',
            [gl.INVALID_OPERATION]: 'INVALID_OPERATION',
            [gl.INVALID_FRAMEBUFFER_OPERATION]: 'INVALID_FRAMEBUFFER_OPERATION',
            [gl.OUT_OF_MEMORY]: 'OUT_OF_MEMORY - Can cause white screen!',
            [gl.CONTEXT_LOST_WEBGL]: 'CONTEXT_LOST_WEBGL - Causes white screen!'
        };
        return errors[error] || `UNKNOWN(${error})`;
    }

    startFrameMonitor() {
        let frameCount = 0;
        let lastSecond = performance.now();
        let consecutiveLowFrames = 0;

        const checkFrame = () => {
            const now = performance.now();
            frameCount++;

            // Check for frame drops (>50ms between frames = dropped frame)
            if (this.lastFrameTime && (now - this.lastFrameTime) > 50) {
                this.frameDrops++;
                if ((now - this.lastFrameTime) > 200) {
                    this.log('WARN', `Major frame drop: ${(now - this.lastFrameTime).toFixed(0)}ms gap`);
                }
            }
            this.lastFrameTime = now;

            // Calculate FPS every second
            if (now - lastSecond >= 1000) {
                const fps = frameCount;
                frameCount = 0;
                lastSecond = now;

                if (fps < 10) {
                    consecutiveLowFrames++;
                    this.log('ERROR', `Very low FPS: ${fps} - Possible freeze/white screen`);
                    if (consecutiveLowFrames >= 3) {
                        this.log('ERROR', 'CRITICAL: 3+ seconds of very low FPS - likely rendering issue');
                    }
                } else if (fps < 20) {
                    this.log('WARN', `Low FPS: ${fps}`);
                    consecutiveLowFrames = 0;
                } else {
                    consecutiveLowFrames = 0;
                }
            }

            if (this.isMonitoring) {
                requestAnimationFrame(checkFrame);
            }
        };

        requestAnimationFrame(checkFrame);
    }

    startWhiteScreenDetector() {
        // Check canvas pixels periodically for all-white condition
        setInterval(() => {
            const canvases = document.querySelectorAll('canvas');
            canvases.forEach((canvas, index) => {
                try {
                    const ctx = canvas.getContext('2d', { willReadFrequently: true });
                    if (!ctx) {
                        // It's a WebGL canvas, check differently
                        this.checkWebGLCanvasForWhite(canvas, index);
                        return;
                    }

                    // Sample pixels
                    const imageData = ctx.getImageData(0, 0, Math.min(canvas.width, 100), Math.min(canvas.height, 100));
                    const isWhite = this.checkIfMostlyWhite(imageData.data);

                    if (isWhite) {
                        this.log('ERROR', `Canvas ${index} appears WHITE/BLANK`, {
                            width: canvas.width,
                            height: canvas.height
                        });
                        this.whiteScreenCount++;
                    }
                } catch (e) {
                    // Can't read pixels (cross-origin or WebGL)
                }
            });
        }, 2000);
    }

    checkWebGLCanvasForWhite(canvas, index) {
        // For WebGL, check if canvas has valid dimensions and is visible
        if (canvas.width === 0 || canvas.height === 0) {
            this.log('ERROR', `WebGL Canvas ${index} has ZERO dimensions - causes white screen!`, {
                width: canvas.width,
                height: canvas.height
            });
            this.whiteScreenCount++;
        }

        // Check if canvas style makes it invisible
        const style = getComputedStyle(canvas);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            this.log('WARN', `WebGL Canvas ${index} is hidden by CSS`);
        }
    }

    checkIfMostlyWhite(pixels) {
        let whitePixels = 0;
        const totalPixels = pixels.length / 4;

        for (let i = 0; i < pixels.length; i += 4) {
            const r = pixels[i];
            const g = pixels[i + 1];
            const b = pixels[i + 2];
            // Check if pixel is near white (>250 for all channels)
            if (r > 250 && g > 250 && b > 250) {
                whitePixels++;
            }
        }

        // If more than 95% pixels are white, flag it
        return (whitePixels / totalPixels) > 0.95;
    }

    hookThreeJSErrors() {
        // Wait for THREE to be available
        const checkThree = () => {
            if (typeof THREE !== 'undefined') {
                this.log('INFO', 'Three.js detected, hooking error handlers');

                // Monitor renderer creation
                const originalWebGLRenderer = THREE.WebGLRenderer;
                const monitor = this;

                THREE.WebGLRenderer = function(params) {
                    monitor.log('INFO', 'THREE.WebGLRenderer created', params);

                    try {
                        const renderer = new originalWebGLRenderer(params);

                        // Hook setPixelRatio - this can cause white screens!
                        const originalSetPixelRatio = renderer.setPixelRatio.bind(renderer);
                        renderer.setPixelRatio = function(ratio) {
                            monitor.log('WARN', `setPixelRatio called with ${ratio} - can cause white screen flash!`);
                            return originalSetPixelRatio(ratio);
                        };

                        // Hook setSize
                        const originalSetSize = renderer.setSize.bind(renderer);
                        renderer.setSize = function(w, h, updateStyle) {
                            if (w <= 0 || h <= 0) {
                                monitor.log('ERROR', `setSize called with invalid dimensions: ${w}x${h} - causes white screen!`);
                            }
                            return originalSetSize(w, h, updateStyle);
                        };

                        return renderer;
                    } catch (e) {
                        monitor.log('ERROR', 'THREE.WebGLRenderer creation FAILED', e.message);
                        throw e;
                    }
                };
                THREE.WebGLRenderer.prototype = originalWebGLRenderer.prototype;

            } else {
                setTimeout(checkThree, 100);
            }
        };
        checkThree();
    }

    logSummary() {
        const summary = {
            whiteScreenEvents: this.whiteScreenCount,
            frameDrops: this.frameDrops,
            glErrors: this.glErrors.length,
            totalLogEntries: this.logFile.length,
            recentErrors: this.logFile.filter(l => l.level === 'ERROR').slice(-5)
        };

        console.log('%c=== Rendering Monitor Summary ===', 'color: cyan; font-weight: bold');
        console.table(summary);

        if (this.whiteScreenCount > 0 || this.glErrors.length > 0) {
            this.log('WARN', 'Issues detected in summary', summary);
        }
    }

    saveLogsToStorage() {
        try {
            localStorage.setItem('trueflow_render_log', JSON.stringify(this.logFile.slice(-200)));
        } catch (e) {
            // localStorage might be full
        }
    }

    exportLogs() {
        const blob = new Blob([JSON.stringify(this.logFile, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trueflow_render_log_${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }

    stop() {
        this.isMonitoring = false;
        this.log('INFO', 'Rendering Monitor stopped');
    }
}

// Auto-start monitor
window.renderingMonitor = new RenderingMonitor();

// Expose export function globally
window.exportRenderLogs = () => window.renderingMonitor.exportLogs();

console.log('%c🔍 TrueFlow Rendering Monitor Active', 'color: lime; font-size: 14px; font-weight: bold');
console.log('Call exportRenderLogs() to save logs to file');
