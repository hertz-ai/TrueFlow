/**
 * Patches Node.js require() to instrument loaded modules.
 * Similar to Python's sitecustomize.py approach.
 */

import Module from 'module';
import * as path from 'path';
import type { Instrumentor } from './instrumentor';

// Store the original require
const originalRequire = (Module.prototype as any).require;

/**
 * Patch the require function to wrap exported functions.
 */
export function patchRequire(instrumentor: Instrumentor): void {
    (Module.prototype as any).require = function (this: NodeModule, id: string): any {
        const exports = originalRequire.call(this, id);

        // Resolve the full path
        let resolvedPath: string;
        try {
            resolvedPath = require.resolve(id, { paths: [path.dirname(this.filename)] });
        } catch {
            resolvedPath = id;
        }

        // Check if this module should be instrumented
        if (instrumentor.shouldInstrument(resolvedPath)) {
            return wrapExports(exports, resolvedPath, instrumentor);
        }

        return exports;
    };

    console.log('[TrueFlow] Require hook installed');
}

/**
 * Wrap all exported functions in a module.
 */
function wrapExports(exports: any, modulePath: string, instrumentor: Instrumentor): any {
    if (!exports) return exports;

    // Handle default export function
    if (typeof exports === 'function') {
        return instrumentor.wrapFunction(
            exports,
            getModuleName(modulePath),
            exports.name || 'default'
        );
    }

    // Handle object with multiple exports
    if (typeof exports === 'object') {
        // Don't modify frozen or sealed objects
        if (Object.isFrozen(exports) || Object.isSealed(exports)) {
            return exports;
        }

        const moduleName = getModuleName(modulePath);

        for (const key of Object.keys(exports)) {
            try {
                const value = exports[key];

                if (typeof value === 'function' && !isBuiltIn(value)) {
                    // Check if property is writable
                    const descriptor = Object.getOwnPropertyDescriptor(exports, key);
                    if (descriptor && descriptor.writable !== false) {
                        exports[key] = instrumentor.wrapFunction(
                            value,
                            moduleName,
                            value.name || key
                        );
                    }
                }
            } catch (error) {
                // Skip properties that can't be accessed or modified
            }
        }

        // Also wrap prototype methods for classes
        if (exports.prototype && typeof exports.prototype === 'object') {
            wrapPrototype(exports.prototype, moduleName, instrumentor);
        }
    }

    return exports;
}

/**
 * Wrap methods on a prototype object.
 */
function wrapPrototype(prototype: any, moduleName: string, instrumentor: Instrumentor): void {
    if (!prototype || typeof prototype !== 'object') return;

    // Don't modify built-in prototypes
    if (prototype === Object.prototype || prototype === Function.prototype) {
        return;
    }

    for (const key of Object.getOwnPropertyNames(prototype)) {
        // Skip constructor and internal properties
        if (key === 'constructor' || key.startsWith('_')) continue;

        try {
            const descriptor = Object.getOwnPropertyDescriptor(prototype, key);
            if (descriptor && typeof descriptor.value === 'function') {
                const original = descriptor.value;

                // Check if writable
                if (descriptor.writable !== false && descriptor.configurable !== false) {
                    Object.defineProperty(prototype, key, {
                        ...descriptor,
                        value: instrumentor.wrapFunction(original, moduleName, key)
                    });
                }
            }
        } catch (error) {
            // Skip properties that can't be modified
        }
    }
}

/**
 * Extract a clean module name from the path.
 */
function getModuleName(modulePath: string): string {
    // Remove common path prefixes
    let name = modulePath.replace(/\\/g, '/');

    // Remove node_modules prefix
    const nodeModulesIndex = name.lastIndexOf('node_modules/');
    if (nodeModulesIndex !== -1) {
        name = name.substring(nodeModulesIndex + 'node_modules/'.length);
    }

    // Remove file extension
    name = name.replace(/\.(js|ts|mjs|cjs)$/, '');

    // Remove /index suffix
    name = name.replace(/\/index$/, '');

    // Take last few path segments
    const segments = name.split('/');
    if (segments.length > 3) {
        name = segments.slice(-3).join('/');
    }

    return name;
}

/**
 * Check if a function is a built-in.
 */
function isBuiltIn(fn: Function): boolean {
    const str = fn.toString();
    return str.includes('[native code]');
}

/**
 * Restore the original require function.
 */
export function unpatchRequire(): void {
    (Module.prototype as any).require = originalRequire;
    console.log('[TrueFlow] Require hook removed');
}
