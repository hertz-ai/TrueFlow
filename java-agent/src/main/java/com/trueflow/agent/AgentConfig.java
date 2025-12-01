package com.trueflow.agent;

import java.util.*;

/**
 * Configuration for the TrueFlow Java agent.
 * Parsed from agent arguments and environment variables.
 */
public class AgentConfig {
    private String host = "127.0.0.1";
    private int port = 5679;  // Different from Python's 5678
    private Set<String> includes = new HashSet<>();
    private Set<String> excludes = new HashSet<>();
    private int maxDepth = 1000;
    private int maxCalls = 100000;
    private int sampleRate = 1;
    private String traceDir = "./.trueflow/traces";
    private boolean socketEnabled = true;
    private boolean retransformEnabled = true;
    private boolean enabled = true;

    // Default excludes - JDK internals and common frameworks
    private static final Set<String> DEFAULT_EXCLUDES = Set.of(
            "java.",
            "javax.",
            "jdk.",
            "sun.",
            "com.sun.",
            "org.apache.logging.",
            "org.slf4j.",
            "ch.qos.logback.",
            "org.objectweb.asm.",
            "com.trueflow.agent.",
            "kotlin.",
            "kotlinx.",
            "scala.",
            "groovy.",
            "org.codehaus.groovy.",
            "org.gradle.",
            "com.intellij.",
            "org.jetbrains.",
            "org.junit.",
            "org.testng.",
            "org.mockito.",
            "org.hamcrest."
    );

    public AgentConfig() {
        // Load defaults from environment
        loadFromEnvironment();
        // Add default excludes
        excludes.addAll(DEFAULT_EXCLUDES);
    }

    private void loadFromEnvironment() {
        String envPort = System.getenv("TRUEFLOW_PORT");
        if (envPort != null) {
            try {
                port = Integer.parseInt(envPort);
            } catch (NumberFormatException ignored) {}
        }

        String envHost = System.getenv("TRUEFLOW_HOST");
        if (envHost != null) {
            host = envHost;
        }

        String envIncludes = System.getenv("TRUEFLOW_INCLUDES");
        if (envIncludes != null && !envIncludes.isEmpty()) {
            includes.addAll(Arrays.asList(envIncludes.split(",")));
        }

        String envExcludes = System.getenv("TRUEFLOW_EXCLUDES");
        if (envExcludes != null && !envExcludes.isEmpty()) {
            excludes.addAll(Arrays.asList(envExcludes.split(",")));
        }

        String envTraceDir = System.getenv("TRUEFLOW_TRACE_DIR");
        if (envTraceDir != null && !envTraceDir.isEmpty()) {
            traceDir = envTraceDir;
        }

        String envMaxDepth = System.getenv("TRUEFLOW_MAX_DEPTH");
        if (envMaxDepth != null) {
            try {
                maxDepth = Integer.parseInt(envMaxDepth);
            } catch (NumberFormatException ignored) {}
        }

        String envMaxCalls = System.getenv("TRUEFLOW_MAX_CALLS");
        if (envMaxCalls != null) {
            try {
                maxCalls = Integer.parseInt(envMaxCalls);
            } catch (NumberFormatException ignored) {}
        }

        String envSampleRate = System.getenv("TRUEFLOW_SAMPLE_RATE");
        if (envSampleRate != null) {
            try {
                sampleRate = Integer.parseInt(envSampleRate);
            } catch (NumberFormatException ignored) {}
        }
    }

    /**
     * Parse agent arguments string.
     * Format: key1=value1,key2=value2,...
     */
    public static AgentConfig parse(String agentArgs) {
        AgentConfig config = new AgentConfig();

        if (agentArgs == null || agentArgs.isEmpty()) {
            return config;
        }

        for (String arg : agentArgs.split(",")) {
            String[] parts = arg.split("=", 2);
            if (parts.length != 2) continue;

            String key = parts[0].trim().toLowerCase();
            String value = parts[1].trim();

            switch (key) {
                case "host":
                    config.host = value;
                    break;
                case "port":
                    try {
                        config.port = Integer.parseInt(value);
                    } catch (NumberFormatException ignored) {}
                    break;
                case "includes":
                    config.includes.addAll(Arrays.asList(value.split(";")));
                    break;
                case "excludes":
                    config.excludes.addAll(Arrays.asList(value.split(";")));
                    break;
                case "maxdepth":
                    try {
                        config.maxDepth = Integer.parseInt(value);
                    } catch (NumberFormatException ignored) {}
                    break;
                case "maxcalls":
                    try {
                        config.maxCalls = Integer.parseInt(value);
                    } catch (NumberFormatException ignored) {}
                    break;
                case "samplerate":
                    try {
                        config.sampleRate = Integer.parseInt(value);
                    } catch (NumberFormatException ignored) {}
                    break;
                case "tracedir":
                    config.traceDir = value;
                    break;
                case "socket":
                    config.socketEnabled = Boolean.parseBoolean(value);
                    break;
                case "retransform":
                    config.retransformEnabled = Boolean.parseBoolean(value);
                    break;
                case "enabled":
                    config.enabled = Boolean.parseBoolean(value);
                    break;
            }
        }

        return config;
    }

    /**
     * Check if a class should be instrumented based on includes/excludes.
     */
    public boolean shouldInstrument(String className) {
        if (className == null) return false;

        // Convert internal name to package format
        String packageName = className.replace('/', '.');

        // Check excludes first
        for (String exclude : excludes) {
            if (packageName.startsWith(exclude)) {
                return false;
            }
        }

        // If includes is empty, instrument everything not excluded
        if (includes.isEmpty()) {
            return true;
        }

        // Check includes
        for (String include : includes) {
            if (packageName.startsWith(include)) {
                return true;
            }
        }

        return false;
    }

    // Getters
    public String getHost() { return host; }
    public int getPort() { return port; }
    public Set<String> getIncludes() { return includes; }
    public Set<String> getExcludes() { return excludes; }
    public int getMaxDepth() { return maxDepth; }
    public int getMaxCalls() { return maxCalls; }
    public int getSampleRate() { return sampleRate; }
    public String getTraceDir() { return traceDir; }
    public boolean isSocketEnabled() { return socketEnabled; }
    public boolean isRetransformEnabled() { return retransformEnabled; }
    public boolean isEnabled() { return enabled; }
}
