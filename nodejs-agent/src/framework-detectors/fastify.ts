/**
 * Fastify instrumentation.
 * Hooks into Fastify lifecycle to trace request handling.
 */

import type { Instrumentor } from '../instrumentor';

/**
 * Instrument Fastify framework.
 */
export function instrumentFastify(instrumentor: Instrumentor): void {
    try {
        const fastify = require('fastify');

        // Store original
        const originalFastify = fastify;

        // Wrap Fastify factory
        const wrappedFastify = function (opts?: any) {
            const app = originalFastify(opts);
            return wrapFastifyApp(app, instrumentor);
        };

        // Copy static properties
        Object.assign(wrappedFastify, originalFastify);

        console.log('[TrueFlow] Fastify instrumentation installed');

    } catch (error) {
        console.log('[TrueFlow] Fastify not found or failed to instrument');
    }
}

/**
 * Wrap a Fastify app instance.
 */
function wrapFastifyApp(app: any, instrumentor: Instrumentor): any {
    const methods = ['get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'all'];

    for (const method of methods) {
        const original = app[method];
        if (typeof original !== 'function') continue;

        app[method] = function (path: string, opts: any, handler?: any) {
            // Handle different argument patterns
            let actualHandler = handler || opts;
            let actualOpts = handler ? opts : {};

            if (typeof actualHandler === 'function' && !(actualHandler as any).__trueflow_wrapped__) {
                const routeName = `${method.toUpperCase()} ${path}`;
                const handlerName = actualHandler.name || 'handler';

                actualHandler = instrumentor.wrapFunction(
                    actualHandler,
                    'fastify/route',
                    `${routeName} [${handlerName}]`
                );
            }

            if (handler) {
                return original.call(this, path, actualOpts, actualHandler);
            } else {
                return original.call(this, path, actualHandler);
            }
        };
    }

    // Wrap hooks
    const originalAddHook = app.addHook;
    if (typeof originalAddHook === 'function') {
        app.addHook = function (name: string, fn: any) {
            if (typeof fn === 'function' && !(fn as any).__trueflow_wrapped__) {
                fn = instrumentor.wrapFunction(fn, 'fastify/hook', `hook:${name}`);
            }
            return originalAddHook.call(this, name, fn);
        };
    }

    // Wrap register for plugins
    const originalRegister = app.register;
    if (typeof originalRegister === 'function') {
        app.register = function (plugin: any, opts?: any) {
            if (typeof plugin === 'function' && !(plugin as any).__trueflow_wrapped__) {
                const pluginName = plugin.name || 'plugin';
                plugin = instrumentor.wrapFunction(plugin, 'fastify/plugin', pluginName);
            }
            return originalRegister.call(this, plugin, opts);
        };
    }

    // Wrap listen
    const originalListen = app.listen;
    if (typeof originalListen === 'function') {
        app.listen = function (...args: any[]) {
            const opts = args[0];
            const port = typeof opts === 'object' ? opts.port : opts;
            console.log(`[TrueFlow] Fastify app listening on port ${port}`);
            return originalListen.apply(this, args);
        };
    }

    return app;
}
