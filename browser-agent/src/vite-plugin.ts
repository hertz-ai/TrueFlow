/**
 * TrueFlow Vite Plugin
 *
 * Integrates TrueFlow instrumentation into Vite builds.
 * Uses the Babel plugin under the hood.
 *
 * Usage in vite.config.js:
 *   import trueflow from '@trueflow/browser-agent/vite-plugin';
 *   export default {
 *     plugins: [trueflow()]
 *   };
 */

import type { Plugin } from 'vite';
import * as babel from '@babel/core';
import babelPlugin from './babel-plugin';

interface TrueFlowViteOptions {
    include?: string[];           // File patterns to include
    exclude?: string[];           // File patterns to exclude
    injectRuntime?: boolean;      // Auto-inject runtime (default: true)
    port?: number;                // WebSocket port (default: 8765)
}

export default function trueflowVitePlugin(options: TrueFlowViteOptions = {}): Plugin {
    const {
        include = ['src/**/*.{js,jsx,ts,tsx}'],
        exclude = ['node_modules', '**/*.test.*', '**/*.spec.*'],
        injectRuntime = true,
        port = 8765
    } = options;

    let isDev = false;

    return {
        name: 'trueflow',

        configResolved(config: { command: string }) {
            isDev = config.command === 'serve';
        },

        // Inject runtime script in dev mode
        transformIndexHtml(html: string) {
            if (!isDev || !injectRuntime) return html;

            const runtimeScript = `
<script>
  // TrueFlow Browser Runtime
  (function() {
    if (window.__trueflow__) return;

    const script = document.createElement('script');
    script.src = '/@trueflow/runtime.js';
    script.onload = function() {
      if (window.__trueflow__) {
        window.__trueflow__.connect(${port});
      }
    };
    document.head.appendChild(script);
  })();
</script>`;

            return html.replace('</head>', `${runtimeScript}\n</head>`);
        },

        // Serve runtime file
        configureServer(server: { middlewares: { use: (path: string, handler: (req: unknown, res: { setHeader: (name: string, value: string) => void; end: (content: string) => void }) => void) => void } }) {
            server.middlewares.use('/@trueflow/runtime.js', (_req: unknown, res: { setHeader: (name: string, value: string) => void; end: (content: string) => void }) => {
                res.setHeader('Content-Type', 'application/javascript');
                res.end(`
// TrueFlow Browser Runtime (inline)
(function() {
  if (window.__trueflow__) return;

  class TrueFlowBrowser {
    constructor() {
      this.ws = null;
      this.callStack = [];
      this.callCounter = 0;
      this.sessionId = 'browser_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
      this.connected = false;
      this.buffer = [];
      console.log('[TrueFlow] Browser agent initialized');
    }

    connect(port) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

      try {
        this.ws = new WebSocket('ws://localhost:' + port + '/trace');
        this.ws.onopen = () => {
          console.log('[TrueFlow] Connected to IDE');
          this.connected = true;
          this.flushBuffer();
        };
        this.ws.onclose = () => {
          console.log('[TrueFlow] Disconnected');
          this.connected = false;
        };
      } catch (e) {
        console.log('[TrueFlow] Connection failed:', e);
      }
    }

    enter(file, func, line) {
      const callId = 'call_' + (++this.callCounter);
      const parentId = this.callStack.length > 0 ? this.callStack[this.callStack.length - 1].callId : null;

      this.callStack.push({ callId, startTime: performance.now(), file, func, line });

      this.emit({
        type: 'call',
        timestamp: Date.now() / 1000,
        call_id: callId,
        module: file,
        function: func,
        line: line,
        depth: this.callStack.length - 1,
        parent_id: parentId,
        language: 'javascript',
        session_id: this.sessionId
      });

      return callId;
    }

    exit(error) {
      const ctx = this.callStack.pop();
      if (!ctx) return;

      this.emit({
        type: 'return',
        timestamp: Date.now() / 1000,
        call_id: ctx.callId,
        module: ctx.file,
        function: ctx.func,
        depth: this.callStack.length,
        parent_id: this.callStack.length > 0 ? this.callStack[this.callStack.length - 1].callId : null,
        duration_ms: performance.now() - ctx.startTime,
        language: 'javascript',
        session_id: this.sessionId,
        exception: error ? error.name + ': ' + error.message : undefined
      });
    }

    emit(event) {
      if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(event));
      } else {
        this.buffer.push(event);
        if (this.buffer.length > 1000) this.buffer.shift();
      }
    }

    flushBuffer() {
      while (this.buffer.length > 0 && this.connected) {
        this.ws.send(JSON.stringify(this.buffer.shift()));
      }
    }
  }

  window.__trueflow__ = new TrueFlowBrowser();
})();
`);
            });
        },

        // Transform source files
        async transform(code: string, id: string) {
            // Skip excluded files
            if (exclude.some(pattern => id.includes(pattern))) {
                return null;
            }

            // Skip non-matching files
            if (!include.some(pattern => {
                const regex = new RegExp(pattern.replace(/\*\*/g, '.*').replace(/\*/g, '[^/]*'));
                return regex.test(id);
            })) {
                return null;
            }

            // Skip non-JS/TS files
            if (!/\.(js|jsx|ts|tsx)$/.test(id)) {
                return null;
            }

            try {
                const result = await babel.transformAsync(code, {
                    filename: id,
                    plugins: [[babelPlugin, { include, exclude }]],
                    parserOpts: {
                        plugins: ['jsx', 'typescript']
                    },
                    sourceMaps: true
                });

                if (result?.code) {
                    return {
                        code: result.code,
                        map: result.map
                    };
                }
            } catch (error) {
                console.error('[TrueFlow] Transform error:', id, error);
            }

            return null;
        }
    };
}

// CommonJS export
module.exports = trueflowVitePlugin;
module.exports.default = trueflowVitePlugin;
