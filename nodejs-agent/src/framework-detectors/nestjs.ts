/**
 * NestJS instrumentation.
 * Patches NestJS decorators and core components.
 */

import type { Instrumentor } from '../instrumentor';

/**
 * Instrument NestJS framework.
 */
export function instrumentNestJS(instrumentor: Instrumentor): void {
    try {
        // Try to patch @nestjs/common decorators
        const common = require('@nestjs/common');

        // Wrap controller method decorators
        const methodDecorators = ['Get', 'Post', 'Put', 'Delete', 'Patch', 'Options', 'Head', 'All'];

        for (const name of methodDecorators) {
            const original = common[name];
            if (typeof original !== 'function') continue;

            common[name] = function (...args: any[]) {
                const decorator = original.apply(this, args);

                // Return a wrapped decorator
                return function (target: any, propertyKey: string, descriptor: PropertyDescriptor) {
                    // Apply original decorator first
                    const result = decorator(target, propertyKey, descriptor);

                    // Wrap the method
                    const originalMethod = descriptor.value;
                    if (typeof originalMethod === 'function' && !(originalMethod as any).__trueflow_wrapped__) {
                        const className = target.constructor.name;
                        const routePath = args[0] || '/';
                        const routeName = `${name.toUpperCase()} ${routePath}`;

                        descriptor.value = instrumentor.wrapFunction(
                            originalMethod,
                            `nestjs/${className}`,
                            `${routeName} [${propertyKey}]`
                        );
                    }

                    return result;
                };
            };
        }

        // Wrap Injectable decorator to track services
        const originalInjectable = common.Injectable;
        if (typeof originalInjectable === 'function') {
            common.Injectable = function (options?: any) {
                const decorator = originalInjectable(options);

                return function (target: any) {
                    // Apply original decorator
                    const result = decorator(target);

                    // Wrap all methods on the prototype
                    const prototype = target.prototype;
                    if (prototype) {
                        for (const key of Object.getOwnPropertyNames(prototype)) {
                            if (key === 'constructor') continue;

                            const descriptor = Object.getOwnPropertyDescriptor(prototype, key);
                            if (descriptor && typeof descriptor.value === 'function') {
                                const original = descriptor.value;
                                if (!(original as any).__trueflow_wrapped__) {
                                    Object.defineProperty(prototype, key, {
                                        ...descriptor,
                                        value: instrumentor.wrapFunction(
                                            original,
                                            `nestjs/${target.name}`,
                                            key
                                        )
                                    });
                                }
                            }
                        }
                    }

                    return result;
                };
            };
        }

        // Try to patch interceptors, guards, pipes
        const patterns = ['UseInterceptors', 'UseGuards', 'UsePipes'];
        for (const pattern of patterns) {
            const original = common[pattern];
            if (typeof original !== 'function') continue;

            common[pattern] = function (...args: any[]) {
                // Wrap each interceptor/guard/pipe
                const wrappedArgs = args.map((arg) => {
                    if (typeof arg === 'function' && !(arg as any).__trueflow_wrapped__) {
                        // This is a class, wrap its intercept/canActivate/transform method
                        const prototype = arg.prototype;
                        if (prototype) {
                            const methodNames = ['intercept', 'canActivate', 'transform'];
                            for (const methodName of methodNames) {
                                const method = prototype[methodName];
                                if (typeof method === 'function' && !(method as any).__trueflow_wrapped__) {
                                    prototype[methodName] = instrumentor.wrapFunction(
                                        method,
                                        `nestjs/${arg.name || pattern}`,
                                        methodName
                                    );
                                }
                            }
                        }
                    }
                    return arg;
                });

                return original.apply(this, wrappedArgs);
            };
        }

        console.log('[TrueFlow] NestJS instrumentation installed');

    } catch (error) {
        console.log('[TrueFlow] NestJS not found or failed to instrument');
    }
}
