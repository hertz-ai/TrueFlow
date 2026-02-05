/**
 * TrueFlow Babel Plugin
 *
 * Transforms JavaScript/TypeScript code to add tracing instrumentation.
 * Works with React, Vue, and vanilla JS applications.
 *
 * Usage in babel.config.js:
 *   module.exports = {
 *     plugins: ['@trueflow/browser-agent/babel-plugin']
 *   };
 */

import type { PluginObj, NodePath, types as t } from '@babel/core';

interface PluginOptions {
    include?: string[];   // File patterns to include
    exclude?: string[];   // File patterns to exclude
    runtime?: string;     // Custom runtime import path
}

export default function trueflowBabelPlugin(
    { types: t }: { types: typeof import('@babel/core').types }
): PluginObj {
    let hasRuntimeImport = false;
    let currentFile = '';

    return {
        name: 'trueflow-instrumentor',

        visitor: {
            Program: {
                enter(path, state) {
                    hasRuntimeImport = false;
                    currentFile = state.filename || 'unknown';

                    // Check if we should process this file
                    const opts = state.opts as PluginOptions;
                    if (opts.exclude?.some(pattern => currentFile.includes(pattern))) {
                        return;
                    }
                    if (opts.include && !opts.include.some(pattern => currentFile.includes(pattern))) {
                        return;
                    }
                },
                exit(path, state) {
                    // Add runtime import if we instrumented anything
                    if (hasRuntimeImport) {
                        const opts = state.opts as PluginOptions;
                        const runtimePath = opts.runtime || '@trueflow/browser-agent';

                        const importDecl = t.importDeclaration(
                            [],
                            t.stringLiteral(runtimePath)
                        );

                        path.unshiftContainer('body', importDecl);
                    }
                }
            },

            // Instrument function declarations
            FunctionDeclaration(path, state) {
                if (!shouldInstrument(path, state)) return;

                const name = path.node.id?.name || 'anonymous';
                const line = path.node.loc?.start.line || 0;

                instrumentFunction(path, t, currentFile, name, line);
                hasRuntimeImport = true;
            },

            // Instrument function expressions
            FunctionExpression(path, state) {
                if (!shouldInstrument(path, state)) return;

                const parent = path.parent;
                let name = 'anonymous';

                // Try to get name from variable declaration
                if (t.isVariableDeclarator(parent) && t.isIdentifier(parent.id)) {
                    name = parent.id.name;
                }
                // Try to get name from assignment
                else if (t.isAssignmentExpression(parent) && t.isIdentifier(parent.left)) {
                    name = parent.left.name;
                }
                // Try to get name from object property
                else if (t.isObjectProperty(parent) && t.isIdentifier(parent.key)) {
                    name = parent.key.name;
                }

                const line = path.node.loc?.start.line || 0;

                instrumentFunction(path, t, currentFile, name, line);
                hasRuntimeImport = true;
            },

            // Instrument arrow functions
            ArrowFunctionExpression(path, state) {
                if (!shouldInstrument(path, state)) return;

                const parent = path.parent;
                let name = 'arrow';

                // Try to get name from variable declaration
                if (t.isVariableDeclarator(parent) && t.isIdentifier(parent.id)) {
                    name = parent.id.name;
                }
                // Try to get name from assignment
                else if (t.isAssignmentExpression(parent) && t.isIdentifier(parent.left)) {
                    name = parent.left.name;
                }
                // Try to get name from object property
                else if (t.isObjectProperty(parent) && t.isIdentifier(parent.key)) {
                    name = parent.key.name;
                }

                const line = path.node.loc?.start.line || 0;

                instrumentArrowFunction(path, t, currentFile, name, line);
                hasRuntimeImport = true;
            },

            // Instrument class methods
            ClassMethod(path, state) {
                if (!shouldInstrument(path, state)) return;

                const name = t.isIdentifier(path.node.key)
                    ? path.node.key.name
                    : 'method';

                const className = getClassName(path);
                const fullName = className ? `${className}.${name}` : name;
                const line = path.node.loc?.start.line || 0;

                instrumentMethod(path, t, currentFile, fullName, line);
                hasRuntimeImport = true;
            }
        }
    };
}

/**
 * Check if we should instrument this function.
 */
function shouldInstrument(path: NodePath<any>, state: any): boolean {
    // Skip if already instrumented
    if (path.node.__trueflow_instrumented__) {
        return false;
    }

    // Skip getters/setters
    if (path.isClassMethod() && (path.node.kind === 'get' || path.node.kind === 'set')) {
        return false;
    }

    // Skip constructor
    if (path.isClassMethod() && path.node.kind === 'constructor') {
        return false;
    }

    // Skip very short functions (likely just return statements)
    const body = path.node.body;
    if (body && 'body' in body && Array.isArray(body.body) && body.body.length === 0) {
        return false;
    }

    return true;
}

/**
 * Get the class name for a method.
 */
function getClassName(path: NodePath<any>): string | null {
    let current = path.parentPath;
    while (current) {
        if (current.isClassDeclaration() || current.isClassExpression()) {
            const id = (current.node as any).id;
            return id?.name || null;
        }
        current = current.parentPath;
    }
    return null;
}

/**
 * Instrument a regular function.
 */
function instrumentFunction(
    path: NodePath<t.FunctionDeclaration | t.FunctionExpression>,
    t: typeof import('@babel/core').types,
    file: string,
    name: string,
    line: number
): void {
    const body = path.node.body;
    if (!t.isBlockStatement(body)) return;

    // Mark as instrumented
    (path.node as any).__trueflow_instrumented__ = true;

    // Create enter call: __trueflow__.enter(file, name, line)
    const enterCall = t.expressionStatement(
        t.callExpression(
            t.memberExpression(
                t.identifier('__trueflow__'),
                t.identifier('enter')
            ),
            [
                t.stringLiteral(file),
                t.stringLiteral(name),
                t.numericLiteral(line)
            ]
        )
    );

    // Create exit call: __trueflow__.exit()
    const exitCall = t.expressionStatement(
        t.callExpression(
            t.memberExpression(
                t.identifier('__trueflow__'),
                t.identifier('exit')
            ),
            []
        )
    );

    // Wrap body in try-finally
    const tryStatement = t.tryStatement(
        t.blockStatement(body.body),
        null,
        t.blockStatement([exitCall])
    );

    body.body = [enterCall, tryStatement];
}

/**
 * Instrument an arrow function.
 */
function instrumentArrowFunction(
    path: NodePath<t.ArrowFunctionExpression>,
    t: typeof import('@babel/core').types,
    file: string,
    name: string,
    line: number
): void {
    const body = path.node.body;

    // Mark as instrumented
    (path.node as any).__trueflow_instrumented__ = true;

    // Create enter call
    const enterCall = t.callExpression(
        t.memberExpression(
            t.identifier('__trueflow__'),
            t.identifier('enter')
        ),
        [
            t.stringLiteral(file),
            t.stringLiteral(name),
            t.numericLiteral(line)
        ]
    );

    // Create exit call
    const exitCall = t.callExpression(
        t.memberExpression(
            t.identifier('__trueflow__'),
            t.identifier('exit')
        ),
        []
    );

    if (t.isBlockStatement(body)) {
        // Block body - wrap in try-finally
        const tryStatement = t.tryStatement(
            t.blockStatement(body.body),
            null,
            t.blockStatement([t.expressionStatement(exitCall)])
        );

        body.body = [t.expressionStatement(enterCall), tryStatement];
    } else {
        // Expression body - convert to block
        const resultVar = path.scope.generateUidIdentifier('result');

        const newBody = t.blockStatement([
            t.expressionStatement(enterCall),
            t.tryStatement(
                t.blockStatement([
                    t.variableDeclaration('const', [
                        t.variableDeclarator(resultVar, body)
                    ]),
                    t.returnStatement(resultVar)
                ]),
                null,
                t.blockStatement([t.expressionStatement(exitCall)])
            )
        ]);

        path.node.body = newBody;
    }
}

/**
 * Instrument a class method.
 */
function instrumentMethod(
    path: NodePath<t.ClassMethod>,
    t: typeof import('@babel/core').types,
    file: string,
    name: string,
    line: number
): void {
    const body = path.node.body;

    // Mark as instrumented
    (path.node as any).__trueflow_instrumented__ = true;

    // Create enter call
    const enterCall = t.expressionStatement(
        t.callExpression(
            t.memberExpression(
                t.identifier('__trueflow__'),
                t.identifier('enter')
            ),
            [
                t.stringLiteral(file),
                t.stringLiteral(name),
                t.numericLiteral(line)
            ]
        )
    );

    // Create exit call
    const exitCall = t.expressionStatement(
        t.callExpression(
            t.memberExpression(
                t.identifier('__trueflow__'),
                t.identifier('exit')
            ),
            []
        )
    );

    // Wrap body in try-finally
    const tryStatement = t.tryStatement(
        t.blockStatement(body.body),
        null,
        t.blockStatement([exitCall])
    );

    body.body = [enterCall, tryStatement];
}

// Export the plugin
module.exports = trueflowBabelPlugin;
module.exports.default = trueflowBabelPlugin;
