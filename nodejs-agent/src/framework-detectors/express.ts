/**
 * Express.js instrumentation.
 * Wraps route handlers and middleware for automatic tracing.
 */

import type { Instrumentor } from '../instrumentor';

/**
 * Instrument Express.js framework.
 */
export function instrumentExpress(instrumentor: Instrumentor): void {
    try {
        const express = require('express');

        // Patch express.Router
        const originalRouter = express.Router;

        express.Router = function (this: any, ...args: any[]) {
            const router = originalRouter.apply(this, args);
            return wrapRouter(router, instrumentor);
        };

        // Patch express() app creation
        const originalExpress = express;
        const wrappedExpress = function (this: any, ...args: any[]) {
            const app = originalExpress.apply(this, args);
            return wrapApp(app, instrumentor);
        };

        // Copy static properties
        Object.assign(wrappedExpress, originalExpress);
        wrappedExpress.Router = express.Router;

        // Note: We can't fully replace the module, but hooks will catch new routers

        console.log('[TrueFlow] Express instrumentation installed');

    } catch (error) {
        console.log('[TrueFlow] Express not found or failed to instrument');
    }
}

/**
 * Wrap an Express router to instrument all route handlers.
 */
function wrapRouter(router: any, instrumentor: Instrumentor): any {
    const methods = ['get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'all'];

    for (const method of methods) {
        const original = router[method];
        if (typeof original !== 'function') continue;

        router[method] = function (path: string, ...handlers: any[]) {
            const wrappedHandlers = handlers.map((handler, index) => {
                if (typeof handler !== 'function') return handler;

                // Skip if already wrapped
                if ((handler as any).__trueflow_wrapped__) return handler;

                const handlerName = handler.name || `handler_${index}`;
                const routeName = `${method.toUpperCase()} ${path}`;

                return instrumentor.wrapFunction(
                    handler,
                    'express/route',
                    `${routeName} [${handlerName}]`
                );
            });

            return original.call(this, path, ...wrappedHandlers);
        };
    }

    // Wrap use() for middleware
    const originalUse = router.use;
    if (typeof originalUse === 'function') {
        router.use = function (...args: any[]) {
            const wrappedArgs = args.map((arg, index) => {
                if (typeof arg !== 'function') return arg;
                if ((arg as any).__trueflow_wrapped__) return arg;

                const name = arg.name || `middleware_${index}`;
                return instrumentor.wrapFunction(arg, 'express/middleware', name);
            });

            return originalUse.apply(this, wrappedArgs);
        };
    }

    return router;
}

/**
 * Wrap an Express app to instrument routes and middleware.
 */
function wrapApp(app: any, instrumentor: Instrumentor): any {
    // Wrap the app as a router (it has the same methods)
    wrapRouter(app, instrumentor);

    // Also wrap app.listen to log when server starts
    const originalListen = app.listen;
    if (typeof originalListen === 'function') {
        app.listen = function (...args: any[]) {
            const port = typeof args[0] === 'number' ? args[0] : 'unknown';
            console.log(`[TrueFlow] Express app listening on port ${port}`);
            return originalListen.apply(this, args);
        };
    }

    return app;
}
