/**
 * TrueFlow Node.js Agent - Zero-code runtime instrumentation
 *
 * Usage: TRUEFLOW_ENABLED=1 node --require @trueflow/nodejs-agent app.js
 *
 * Environment variables:
 *   TRUEFLOW_ENABLED=1        - Enable tracing
 *   TRUEFLOW_PORT=5680        - Socket server port (default: 5680)
 *   TRUEFLOW_HOST=127.0.0.1   - Socket server host
 *   TRUEFLOW_INCLUDES=src,lib - Paths to instrument (comma-separated)
 *   TRUEFLOW_EXCLUDES=node_modules,dist - Paths to exclude
 *   TRUEFLOW_MAX_DEPTH=1000   - Maximum call stack depth
 *   TRUEFLOW_SAMPLE_RATE=1    - Sample 1 in N calls
 */

import { Instrumentor } from './instrumentor';
import { patchRequire } from './require-hook';
import { detectAndInstrumentFrameworks } from './framework-detectors';

// Check if tracing is enabled
const enabled = process.env.TRUEFLOW_ENABLED === '1' || process.env.TRUEFLOW_ENABLED === 'true';

if (enabled) {
    console.log('[TrueFlow] Initializing Node.js runtime instrumentor...');

    const config = {
        host: process.env.TRUEFLOW_HOST || '127.0.0.1',
        port: parseInt(process.env.TRUEFLOW_PORT || '5680', 10),
        includes: (process.env.TRUEFLOW_INCLUDES || '').split(',').filter(Boolean),
        excludes: (process.env.TRUEFLOW_EXCLUDES || 'node_modules,dist,.git').split(',').filter(Boolean),
        maxDepth: parseInt(process.env.TRUEFLOW_MAX_DEPTH || '1000', 10),
        maxCalls: parseInt(process.env.TRUEFLOW_MAX_CALLS || '100000', 10),
        sampleRate: parseInt(process.env.TRUEFLOW_SAMPLE_RATE || '1', 10)
    };

    // Create instrumentor
    const instrumentor = new Instrumentor(config);

    // Patch require to instrument loaded modules
    patchRequire(instrumentor);

    // Detect and instrument popular frameworks
    detectAndInstrumentFrameworks(instrumentor);

    // Start socket server
    instrumentor.start();

    console.log(`[TrueFlow] Socket server listening on ${config.host}:${config.port}`);
    console.log(`[TrueFlow] Tracing paths: ${config.includes.length > 0 ? config.includes.join(', ') : '(all)'}`);
    console.log(`[TrueFlow] Excluding paths: ${config.excludes.join(', ')}`);

    // Graceful shutdown
    process.on('beforeExit', () => {
        instrumentor.finalize();
    });

    process.on('SIGINT', () => {
        instrumentor.finalize();
        process.exit(0);
    });

    process.on('SIGTERM', () => {
        instrumentor.finalize();
        process.exit(0);
    });
} else {
    // Tracing disabled - no-op
    if (process.env.TRUEFLOW_DEBUG === '1') {
        console.log('[TrueFlow] Tracing disabled (set TRUEFLOW_ENABLED=1 to enable)');
    }
}

// Export for programmatic use
export { Instrumentor } from './instrumentor';
export { TraceSocketServer } from './socket-server';
