package com.trueflow.agent;

import java.lang.instrument.Instrumentation;
import java.util.logging.Logger;

/**
 * TrueFlow Java Agent - Zero-code runtime instrumentation for Java applications.
 *
 * Usage: java -javaagent:trueflow-agent.jar[=options] -jar your-app.jar
 *
 * Options (comma-separated):
 *   - port=5679          : Socket server port (default: 5679, different from Python's 5678)
 *   - host=127.0.0.1     : Socket server host
 *   - includes=com.myapp : Packages to instrument (comma-separated)
 *   - excludes=com.test  : Packages to exclude (comma-separated)
 *   - maxDepth=1000      : Maximum call stack depth
 *   - maxCalls=100000    : Maximum calls to track
 *   - sampleRate=1       : Sample 1 in N calls (1 = all calls)
 *   - traceDir=./traces  : Directory for trace file output
 *
 * Environment variables:
 *   - TRUEFLOW_ENABLED=1        : Enable tracing
 *   - TRUEFLOW_PORT=5679        : Socket server port
 *   - TRUEFLOW_INCLUDES=com.app : Packages to instrument
 *   - TRUEFLOW_EXCLUDES=com.test: Packages to exclude
 *   - TRUEFLOW_TRACE_DIR=./traces: Trace output directory
 */
public class TrueFlowAgent {
    private static final Logger LOGGER = Logger.getLogger(TrueFlowAgent.class.getName());
    private static RuntimeInstrumentor instrumentor;
    private static TraceSocketServer socketServer;
    private static volatile boolean initialized = false;

    /**
     * Premain entry point - called when agent is loaded at JVM startup.
     * Usage: java -javaagent:trueflow-agent.jar[=options] ...
     */
    public static void premain(String agentArgs, Instrumentation inst) {
        initialize(agentArgs, inst, false);
    }

    /**
     * Agentmain entry point - called when agent is attached to running JVM.
     * Usage: Attach API or jcmd <pid> JVMTI.agent_load /path/to/trueflow-agent.jar[=options]
     */
    public static void agentmain(String agentArgs, Instrumentation inst) {
        initialize(agentArgs, inst, true);
    }

    private static synchronized void initialize(String agentArgs, Instrumentation inst, boolean isAttach) {
        if (initialized) {
            LOGGER.warning("[TrueFlow] Agent already initialized, skipping");
            return;
        }

        // Check if tracing is enabled
        String enabled = System.getenv("TRUEFLOW_ENABLED");
        if (enabled == null || !enabled.equals("1")) {
            // Check for agent args that explicitly enable
            if (agentArgs == null || !agentArgs.contains("enabled=true")) {
                LOGGER.info("[TrueFlow] Tracing disabled (set TRUEFLOW_ENABLED=1 to enable)");
                return;
            }
        }

        LOGGER.info("[TrueFlow] Initializing Java runtime instrumentor...");

        try {
            // Parse agent arguments
            AgentConfig config = AgentConfig.parse(agentArgs);

            // Create the instrumentor
            instrumentor = new RuntimeInstrumentor(config);

            // Register the class transformer
            inst.addTransformer(new TracingClassTransformer(instrumentor, config), true);

            // Start socket server for IDE communication
            if (config.isSocketEnabled()) {
                socketServer = new TraceSocketServer(config.getHost(), config.getPort(), instrumentor);
                socketServer.start();
                LOGGER.info("[TrueFlow] Socket server started on " + config.getHost() + ":" + config.getPort());
            }

            // Register shutdown hook for cleanup
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                LOGGER.info("[TrueFlow] Shutting down...");
                if (socketServer != null) {
                    socketServer.stop();
                }
                if (instrumentor != null) {
                    instrumentor.finalize(config.getTraceDir());
                }
            }));

            // If attached to running JVM, retransform already loaded classes
            if (isAttach && config.isRetransformEnabled()) {
                retransformLoadedClasses(inst, config);
            }

            initialized = true;
            LOGGER.info("[TrueFlow] Java agent initialized successfully");
            LOGGER.info("[TrueFlow] Tracing packages: " + config.getIncludes());
            LOGGER.info("[TrueFlow] Excluding packages: " + config.getExcludes());

        } catch (Exception e) {
            LOGGER.severe("[TrueFlow] Failed to initialize agent: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private static void retransformLoadedClasses(Instrumentation inst, AgentConfig config) {
        LOGGER.info("[TrueFlow] Retransforming already loaded classes...");
        int transformed = 0;
        for (Class<?> clazz : inst.getAllLoadedClasses()) {
            if (inst.isModifiableClass(clazz) && config.shouldInstrument(clazz.getName())) {
                try {
                    inst.retransformClasses(clazz);
                    transformed++;
                } catch (Exception e) {
                    LOGGER.fine("[TrueFlow] Could not retransform: " + clazz.getName());
                }
            }
        }
        LOGGER.info("[TrueFlow] Retransformed " + transformed + " classes");
    }

    /**
     * Get the current instrumentor instance for programmatic access.
     */
    public static RuntimeInstrumentor getInstrumentor() {
        return instrumentor;
    }

    /**
     * Check if tracing is currently active.
     */
    public static boolean isActive() {
        return initialized && instrumentor != null && instrumentor.isEnabled();
    }

    /**
     * Manually trigger trace finalization and export.
     */
    public static void finalizeTrace(String outputDir) {
        if (instrumentor != null) {
            instrumentor.finalize(outputDir);
        }
    }
}
