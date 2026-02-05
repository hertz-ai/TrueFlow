/**
 * Framework auto-detection and instrumentation.
 * Automatically patches popular frameworks when detected.
 */

import type { Instrumentor } from '../instrumentor';
import { instrumentExpress } from './express';
import { instrumentFastify } from './fastify';
import { instrumentNestJS } from './nestjs';

interface FrameworkDetector {
    name: string;
    detect: () => boolean;
    instrument: (instrumentor: Instrumentor) => void;
}

const frameworks: FrameworkDetector[] = [
    {
        name: 'Express',
        detect: () => {
            try {
                require.resolve('express');
                return true;
            } catch {
                return false;
            }
        },
        instrument: instrumentExpress
    },
    {
        name: 'Fastify',
        detect: () => {
            try {
                require.resolve('fastify');
                return true;
            } catch {
                return false;
            }
        },
        instrument: instrumentFastify
    },
    {
        name: 'NestJS',
        detect: () => {
            try {
                require.resolve('@nestjs/core');
                return true;
            } catch {
                return false;
            }
        },
        instrument: instrumentNestJS
    }
];

/**
 * Detect and instrument all available frameworks.
 */
export function detectAndInstrumentFrameworks(instrumentor: Instrumentor): void {
    const detected: string[] = [];

    for (const framework of frameworks) {
        if (framework.detect()) {
            try {
                framework.instrument(instrumentor);
                detected.push(framework.name);
            } catch (error) {
                console.log(`[TrueFlow] Failed to instrument ${framework.name}:`, error);
            }
        }
    }

    if (detected.length > 0) {
        console.log(`[TrueFlow] Auto-instrumented frameworks: ${detected.join(', ')}`);
    }
}
