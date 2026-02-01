package com.trueflow.agent;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import java.util.logging.Logger;
import java.util.stream.Collectors;

/**
 * Core runtime instrumentor that tracks method calls.
 * Equivalent to Python's RuntimeInstrumentor class.
 *
 * Thread-safe design using:
 * - ThreadLocal for per-thread call stacks
 * - ConcurrentHashMap for global call registry
 * - Atomic counters for IDs and limits
 */
public class RuntimeInstrumentor {
    private static final Logger LOGGER = Logger.getLogger(RuntimeInstrumentor.class.getName());
    private static final Gson GSON = new GsonBuilder().create();

    private final AgentConfig config;
    private final String sessionId;

    // Per-thread call stack for hierarchy tracking
    private final ThreadLocal<Deque<MethodCall>> callStack = ThreadLocal.withInitial(ArrayDeque::new);
    private final ThreadLocal<Integer> currentDepth = ThreadLocal.withInitial(() -> 0);

    // Global state
    private final ConcurrentHashMap<String, MethodCall> activeCalls = new ConcurrentHashMap<>();
    private final List<MethodCall> completedCalls = Collections.synchronizedList(new ArrayList<>());
    // methodKey -> [sourceFile, lineNumber]
    private final ConcurrentHashMap<String, String[]> registeredMethods = new ConcurrentHashMap<>();

    // Counters
    private final AtomicLong callIdCounter = new AtomicLong(0);
    private final AtomicInteger totalCalls = new AtomicInteger(0);
    private final AtomicInteger sampleCounter = new AtomicInteger(0);

    // Event listeners (for socket streaming)
    private final List<Consumer<String>> eventListeners = new ArrayList<>();

    // State flags
    private volatile boolean enabled = true;
    private volatile boolean finalized = false;

    // Branch analyzer for "Why Not Covered" feature
    private JavaBranchAnalyzer branchAnalyzer;
    private volatile boolean branchAnalysisComplete = false;

    public RuntimeInstrumentor(AgentConfig config) {
        this.config = config;
        this.sessionId = "session_" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        LOGGER.info("[TrueFlow] Session ID: " + sessionId);

        // Start branch analysis in background
        startBranchAnalysis();
    }

    /**
     * Start branch analysis in a background thread.
     */
    private void startBranchAnalysis() {
        Thread analyzerThread = new Thread(() -> {
            try {
                // Get project root from working directory or source path
                String workingDir = System.getProperty("user.dir");
                java.nio.file.Path projectRoot = java.nio.file.Paths.get(workingDir);

                LOGGER.info("[TrueFlow] Starting branch analysis from: " + projectRoot);
                branchAnalyzer = new JavaBranchAnalyzer(projectRoot);
                branchAnalyzer.scan();
                branchAnalysisComplete = true;
                LOGGER.info("[TrueFlow] Branch analysis complete");

            } catch (Exception e) {
                LOGGER.warning("[TrueFlow] Branch analysis failed (non-critical): " + e.getMessage());
            }
        }, "TrueFlow-BranchAnalyzer");
        analyzerThread.setDaemon(true);
        analyzerThread.start();
    }

    /**
     * Called at method entry - creates and tracks a new MethodCall.
     */
    public String onMethodEnter(String className, String methodName, String signature,
                                 String sourceFile, int lineNumber) {
        if (!enabled || finalized) return null;

        // Check call limit
        if (totalCalls.get() >= config.getMaxCalls()) {
            if (enabled) {
                LOGGER.warning("[TrueFlow] Max calls reached (" + config.getMaxCalls() + "), disabling tracing");
                enabled = false;
            }
            return null;
        }

        // Sampling
        if (config.getSampleRate() > 1) {
            if (sampleCounter.incrementAndGet() % config.getSampleRate() != 0) {
                return null;
            }
        }

        try {
            // Check depth limit
            int depth = currentDepth.get();
            if (depth >= config.getMaxDepth()) {
                return null;
            }

            // Generate call ID
            String callId = "call_" + callIdCounter.incrementAndGet();

            // Get parent ID from current stack
            Deque<MethodCall> stack = callStack.get();
            String parentId = stack.isEmpty() ? null : stack.peek().getCallId();

            // Create method call
            Thread currentThread = Thread.currentThread();
            MethodCall call = new MethodCall(
                    callId, className, methodName, signature,
                    sourceFile, lineNumber, depth, parentId,
                    currentThread.getId(), currentThread.getName()
            );

            // Push to stack and register
            stack.push(call);
            activeCalls.put(callId, call);
            currentDepth.set(depth + 1);
            totalCalls.incrementAndGet();

            // Register method for function registry (with file/line for dead code detection)
            String methodKey = className + "." + methodName;
            registeredMethods.putIfAbsent(methodKey, new String[]{sourceFile, String.valueOf(lineNumber)});

            // Emit call event
            emitEvent(call.toCallJson(sessionId).toString());

            return callId;

        } catch (Exception e) {
            LOGGER.fine("[TrueFlow] Error in onMethodEnter: " + e.getMessage());
            return null;
        }
    }

    /**
     * Called at method exit (normal return).
     */
    public void onMethodExit(String callId) {
        if (callId == null || !enabled || finalized) return;

        try {
            MethodCall call = activeCalls.remove(callId);
            if (call == null) return;

            call.markReturned();

            // Pop from stack
            Deque<MethodCall> stack = callStack.get();
            if (!stack.isEmpty() && stack.peek().getCallId().equals(callId)) {
                stack.pop();
            }
            currentDepth.set(Math.max(0, currentDepth.get() - 1));

            // Store completed call
            completedCalls.add(call);

            // Emit return event
            emitEvent(call.toReturnJson(sessionId).toString());

        } catch (Exception e) {
            LOGGER.fine("[TrueFlow] Error in onMethodExit: " + e.getMessage());
        }
    }

    /**
     * Called when a method exits with an exception.
     */
    public void onMethodException(String callId, String exceptionClass, String message) {
        if (callId == null || !enabled || finalized) return;

        try {
            MethodCall call = activeCalls.remove(callId);
            if (call == null) return;

            call.markException(exceptionClass, message);

            // Pop from stack
            Deque<MethodCall> stack = callStack.get();
            if (!stack.isEmpty() && stack.peek().getCallId().equals(callId)) {
                stack.pop();
            }
            currentDepth.set(Math.max(0, currentDepth.get() - 1));

            // Store completed call
            completedCalls.add(call);

            // Emit return event with exception
            emitEvent(call.toReturnJson(sessionId).toString());

        } catch (Exception e) {
            LOGGER.fine("[TrueFlow] Error in onMethodException: " + e.getMessage());
        }
    }

    /**
     * Register an event listener for real-time streaming.
     */
    public void addEventListener(Consumer<String> listener) {
        eventListeners.add(listener);
    }

    /**
     * Remove an event listener.
     */
    public void removeEventListener(Consumer<String> listener) {
        eventListeners.remove(listener);
    }

    /**
     * Emit an event to all listeners.
     */
    private void emitEvent(String json) {
        for (Consumer<String> listener : eventListeners) {
            try {
                listener.accept(json);
            } catch (Exception e) {
                LOGGER.fine("[TrueFlow] Error emitting event: " + e.getMessage());
            }
        }
    }

    /**
     * Get the function registry JSON for new socket clients.
     */
    public String getFunctionRegistryJson() {
        JsonObject registry = new JsonObject();
        registry.addProperty("type", "function_registry");
        registry.addProperty("timestamp", System.currentTimeMillis() / 1000.0);
        registry.addProperty("session_id", sessionId);
        registry.addProperty("language", "java");

        JsonObject traceData = new JsonObject();
        traceData.addProperty("total_functions", registeredMethods.size());

        JsonArray functions = new JsonArray();
        for (Map.Entry<String, String[]> entry : registeredMethods.entrySet()) {
            String method = entry.getKey();
            String[] info = entry.getValue();
            String[] parts = method.split("\\.", 2);
            JsonObject func = new JsonObject();
            func.addProperty("module", parts.length > 0 ? parts[0] : "");
            func.addProperty("function", parts.length > 1 ? parts[1] : method);
            func.addProperty("file", info[0] != null ? info[0] : "");
            func.addProperty("line", Integer.parseInt(info[1]));
            functions.add(func);
        }
        traceData.add("functions", functions);
        registry.add("trace_data", traceData);

        return registry.toString();
    }

    /**
     * Finalize tracing and export all report formats.
     */
    public void finalize(String outputDir) {
        if (finalized) return;
        finalized = true;
        enabled = false;

        LOGGER.info("[TrueFlow] Finalizing trace with " + completedCalls.size() + " calls");

        try {
            File dir = new File(outputDir);
            if (!dir.exists()) {
                dir.mkdirs();
            }

            // Export all report types - each wrapped in try-catch for graceful degradation
            Map<String, Runnable> exportMethods = new LinkedHashMap<>();
            exportMethods.put("JSON Trace", () -> exportJsonTrace(dir));
            exportMethods.put("PlantUML", () -> exportPlantUML(dir));
            exportMethods.put("Performance JSON", () -> exportPerformanceJson(dir));
            exportMethods.put("Flamegraph JSON", () -> exportFlamegraphJson(dir));
            exportMethods.put("SQL Analysis", () -> exportSqlAnalysisJson(dir));
            exportMethods.put("Live Metrics", () -> exportLiveMetricsJson(dir));
            exportMethods.put("Mermaid Diagram", () -> exportMermaidDiagram(dir));
            exportMethods.put("D2 Diagram", () -> exportD2Diagram(dir));
            exportMethods.put("LLM Summary", () -> exportLlmTextSummary(dir));
            exportMethods.put("Markdown Summary", () -> exportMarkdownSummary(dir));
            exportMethods.put("ASCII Art", () -> exportAsciiArt(dir));

            List<String> failedExports = new ArrayList<>();
            for (Map.Entry<String, Runnable> entry : exportMethods.entrySet()) {
                try {
                    entry.getValue().run();
                } catch (Exception e) {
                    failedExports.add(entry.getKey() + ": " + e.getMessage());
                }
            }

            // Log summary
            int successCount = exportMethods.size() - failedExports.size();
            LOGGER.info("[TrueFlow] Exported " + successCount + "/" + exportMethods.size() + " report formats");
            if (!failedExports.isEmpty()) {
                LOGGER.warning("[TrueFlow] Some exports failed:");
                for (String failure : failedExports) {
                    LOGGER.warning("  - " + failure);
                }
            }

        } catch (Exception e) {
            LOGGER.severe("[TrueFlow] Failed to export traces: " + e.getMessage());
        }
    }

    /**
     * Export basic JSON trace (original format).
     */
    private void exportJsonTrace(File dir) {
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        String filename = "java_trace_" + timestamp + ".json";
        File outputFile = new File(dir, filename);

        JsonObject output = new JsonObject();
        output.addProperty("session_id", sessionId);
        output.addProperty("timestamp", timestamp);
        output.addProperty("language", "java");
        output.addProperty("total_calls", completedCalls.size());
        output.addProperty("total_methods", registeredMethods.size());

        JsonArray calls = new JsonArray();
        for (MethodCall call : completedCalls) {
            JsonObject callJson = new JsonObject();
            callJson.addProperty("call_id", call.getCallId());
            callJson.addProperty("class", call.getClassName());
            callJson.addProperty("method", call.getMethodName());
            callJson.addProperty("signature", call.getSignature());
            callJson.addProperty("file", call.getSourceFile());
            callJson.addProperty("line", call.getLineNumber());
            callJson.addProperty("depth", call.getDepth());
            callJson.addProperty("parent_id", call.getParentId());
            callJson.addProperty("duration_ms", call.getDurationMs());
            callJson.addProperty("thread_id", call.getThreadId());
            callJson.addProperty("thread_name", call.getThreadName());

            if (call.getException() != null) {
                callJson.addProperty("exception", call.getException());
            }
            if (call.getProtocol() != null) {
                callJson.addProperty("protocol", call.getProtocol());
            }
            if (call.getInvocationType() != null) {
                callJson.addProperty("invocation_type", call.getInvocationType());
            }

            calls.add(callJson);
        }
        output.add("calls", calls);

        writeJsonFile(outputFile, output);
        LOGGER.info("[TrueFlow] JSON trace exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export PlantUML sequence diagram.
     */
    private void exportPlantUML(File dir) {
        File outputFile = new File(dir, sessionId + ".puml");
        StringBuilder sb = new StringBuilder();

        sb.append("@startuml\n");
        sb.append("autonumber\n");
        sb.append("skinparam backgroundColor #FEFEFE\n\n");

        // Add participants (unique classes)
        Set<String> classes = new LinkedHashSet<>();
        for (MethodCall call : completedCalls) {
            classes.add(call.getClassName());
        }

        for (String className : classes) {
            String cleanName = className.replace(".", "_");
            String shortName = className.contains(".") ?
                className.substring(className.lastIndexOf('.') + 1) : className;

            // Determine icon based on protocol/type
            String icon = "entity";
            for (MethodCall call : completedCalls) {
                if (call.getClassName().equals(className)) {
                    if ("API_ENTRY".equals(call.getInvocationType())) {
                        icon = "control";
                        break;
                    } else if ("SQL".equals(call.getProtocol())) {
                        icon = "database";
                        break;
                    }
                }
            }
            sb.append(icon).append(" \"").append(shortName).append("\" as ").append(cleanName).append("\n");
        }
        sb.append("\n");

        // Add calls
        for (MethodCall call : completedCalls) {
            if (call.getDurationMs() <= 0) continue;

            String src = call.getClassName().replace(".", "_");
            String label = call.getMethodName();

            if ("Async".equals(call.getProtocol())) {
                label = "<<async>> " + label;
            }

            sb.append(src).append(" -> ").append(src).append(": ").append(label).append("\n");
            sb.append(String.format("note right: %.1fms\n", call.getDurationMs()));

            if (call.getException() != null) {
                sb.append("note over ").append(src).append(" #FF6B6B: ")
                  .append(call.getException().substring(0, Math.min(50, call.getException().length())))
                  .append("\n");
            }
            sb.append("\n");
        }

        sb.append("@enduml\n");
        writeTextFile(outputFile, sb.toString());
        LOGGER.info("[TrueFlow] PlantUML exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export performance metrics as JSON.
     */
    private void exportPerformanceJson(File dir) {
        File outputFile = new File(dir, sessionId + "_performance.json");

        // Calculate metrics per method
        Map<String, JsonObject> methodMetrics = new LinkedHashMap<>();
        for (MethodCall call : completedCalls) {
            String key = call.getClassName() + "." + call.getMethodName();
            if (!methodMetrics.containsKey(key)) {
                JsonObject metrics = new JsonObject();
                metrics.addProperty("class", call.getClassName());
                metrics.addProperty("method", call.getMethodName());
                metrics.addProperty("call_count", 0);
                metrics.addProperty("total_time_ms", 0.0);
                metrics.addProperty("protocol", call.getProtocol());
                metrics.addProperty("invocation_type", call.getInvocationType());
                methodMetrics.put(key, metrics);
            }

            JsonObject metrics = methodMetrics.get(key);
            metrics.addProperty("call_count", metrics.get("call_count").getAsInt() + 1);
            metrics.addProperty("total_time_ms",
                metrics.get("total_time_ms").getAsDouble() + call.getDurationMs());
        }

        // Sort by total time
        List<JsonObject> sortedMetrics = new ArrayList<>(methodMetrics.values());
        sortedMetrics.sort((a, b) ->
            Double.compare(b.get("total_time_ms").getAsDouble(), a.get("total_time_ms").getAsDouble()));

        // Calculate avg time
        for (JsonObject metrics : sortedMetrics) {
            int count = metrics.get("call_count").getAsInt();
            double totalTime = metrics.get("total_time_ms").getAsDouble();
            metrics.addProperty("avg_time_ms", count > 0 ? totalTime / count : 0);
        }

        JsonObject report = new JsonObject();
        report.addProperty("session_id", sessionId);
        report.addProperty("language", "java");
        report.addProperty("process_id", ProcessHandle.current().pid());

        JsonObject statistics = new JsonObject();
        statistics.addProperty("total_calls", completedCalls.size());
        statistics.addProperty("total_methods", methodMetrics.size());
        double totalDuration = completedCalls.stream().mapToDouble(MethodCall::getDurationMs).sum();
        statistics.addProperty("total_duration_ms", totalDuration);
        report.add("statistics", statistics);

        JsonArray metricsArray = new JsonArray();
        for (JsonObject m : sortedMetrics) {
            metricsArray.add(m);
        }
        report.add("function_metrics", metricsArray);

        writeJsonFile(outputFile, report);
        LOGGER.info("[TrueFlow] Performance JSON exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export flamegraph data in speedscope.app compatible format.
     */
    private void exportFlamegraphJson(File dir) {
        File outputFile = new File(dir, sessionId + "_flamegraph.json");

        JsonArray frames = new JsonArray();
        for (MethodCall call : completedCalls) {
            if (call.getDurationMs() <= 0) continue;

            JsonObject frame = new JsonObject();
            frame.addProperty("name", call.getClassName() + "." + call.getMethodName());
            frame.addProperty("value", call.getDurationMs());
            frame.addProperty("file", call.getSourceFile());
            frame.addProperty("line", call.getLineNumber());
            frame.addProperty("parent_id", call.getParentId());
            frame.addProperty("call_id", call.getCallId());
            frame.addProperty("depth", call.getDepth());
            frame.addProperty("protocol", call.getProtocol());
            frame.addProperty("invocation_type", call.getInvocationType());
            frames.add(frame);
        }

        JsonObject flamegraph = new JsonObject();
        flamegraph.addProperty("session_id", sessionId);
        flamegraph.addProperty("type", "flamegraph");
        flamegraph.addProperty("language", "java");
        flamegraph.add("frames", frames);

        JsonObject statistics = new JsonObject();
        double totalDuration = completedCalls.stream()
            .filter(c -> c.getParentId() == null)
            .mapToDouble(MethodCall::getDurationMs).sum();
        int maxDepth = completedCalls.stream().mapToInt(MethodCall::getDepth).max().orElse(0);
        statistics.addProperty("total_duration_ms", totalDuration);
        statistics.addProperty("max_depth", maxDepth);
        statistics.addProperty("total_calls", completedCalls.size());
        flamegraph.add("statistics", statistics);

        writeJsonFile(outputFile, flamegraph);
        LOGGER.info("[TrueFlow] Flamegraph JSON exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export SQL query analysis with N+1 detection.
     */
    private void exportSqlAnalysisJson(File dir) {
        File outputFile = new File(dir, sessionId + "_sql_analysis.json");

        // Track SQL-related calls and patterns
        Map<String, JsonObject> queryPatterns = new LinkedHashMap<>();
        List<JsonObject> allQueries = new ArrayList<>();

        for (MethodCall call : completedCalls) {
            if (!"SQL".equals(call.getProtocol())) continue;

            String key = call.getClassName() + "." + call.getMethodName();
            if (!queryPatterns.containsKey(key)) {
                JsonObject pattern = new JsonObject();
                pattern.addProperty("pattern", key);
                pattern.addProperty("count", 0);
                pattern.add("locations", new JsonArray());
                queryPatterns.put(key, pattern);
            }

            JsonObject pattern = queryPatterns.get(key);
            pattern.addProperty("count", pattern.get("count").getAsInt() + 1);

            JsonObject location = new JsonObject();
            location.addProperty("class", call.getClassName());
            location.addProperty("method", call.getMethodName());
            location.addProperty("line", call.getLineNumber());
            location.addProperty("duration_ms", call.getDurationMs());
            pattern.get("locations").getAsJsonArray().add(location);

            JsonObject query = new JsonObject();
            query.addProperty("class", call.getClassName());
            query.addProperty("method", call.getMethodName());
            query.addProperty("file", call.getSourceFile());
            query.addProperty("line", call.getLineNumber());
            query.addProperty("duration_ms", call.getDurationMs());
            allQueries.add(query);
        }

        // Detect N+1 patterns (same method called many times)
        JsonArray nPlus1Issues = new JsonArray();
        for (JsonObject pattern : queryPatterns.values()) {
            int count = pattern.get("count").getAsInt();
            if (count > 10) {
                JsonObject issue = new JsonObject();
                issue.addProperty("severity", count > 50 ? "high" : "medium");
                issue.addProperty("pattern", pattern.get("pattern").getAsString());
                issue.addProperty("count", count);
                issue.addProperty("suggestion", "Consider using batch queries or eager loading");

                // Add first 5 locations
                JsonArray locations = pattern.get("locations").getAsJsonArray();
                JsonArray limitedLocations = new JsonArray();
                for (int i = 0; i < Math.min(5, locations.size()); i++) {
                    limitedLocations.add(locations.get(i));
                }
                issue.add("locations", limitedLocations);
                nPlus1Issues.add(issue);
            }
        }

        JsonObject report = new JsonObject();
        report.addProperty("session_id", sessionId);
        report.addProperty("language", "java");

        JsonObject statistics = new JsonObject();
        statistics.addProperty("total_sql_calls", allQueries.size());
        statistics.addProperty("unique_patterns", queryPatterns.size());
        statistics.addProperty("n_plus_1_issues", nPlus1Issues.size());
        report.add("statistics", statistics);
        report.add("n_plus_1_issues", nPlus1Issues);

        // Limit to first 100 queries
        JsonArray queriesArray = new JsonArray();
        for (int i = 0; i < Math.min(100, allQueries.size()); i++) {
            queriesArray.add(allQueries.get(i));
        }
        report.add("all_queries", queriesArray);

        writeJsonFile(outputFile, report);
        LOGGER.info("[TrueFlow] SQL Analysis exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export live metrics JSON.
     */
    private void exportLiveMetricsJson(File dir) {
        File outputFile = new File(dir, sessionId + "_live_metrics.json");

        // Group calls by thread for concurrency analysis
        Map<Long, List<MethodCall>> callsByThread = new LinkedHashMap<>();
        for (MethodCall call : completedCalls) {
            callsByThread.computeIfAbsent(call.getThreadId(), k -> new ArrayList<>()).add(call);
        }

        // Calculate metrics
        long startTimeNanos = completedCalls.isEmpty() ? 0 : completedCalls.get(0).getStartTime();
        long endTimeNanos = completedCalls.isEmpty() ? 0 :
            completedCalls.get(completedCalls.size() - 1).getEndTime();
        double totalDurationSec = (endTimeNanos - startTimeNanos) / 1_000_000_000.0;
        double requestsPerSec = totalDurationSec > 0 ? completedCalls.size() / totalDurationSec : 0;

        // Calculate latency percentiles
        List<Double> durations = completedCalls.stream()
            .map(MethodCall::getDurationMs)
            .sorted()
            .collect(java.util.stream.Collectors.toList());

        double p50 = getPercentile(durations, 50);
        double p95 = getPercentile(durations, 95);
        double p99 = getPercentile(durations, 99);
        double avgLatency = durations.stream().mapToDouble(d -> d).average().orElse(0);

        // Count errors
        long errorCount = completedCalls.stream().filter(c -> c.getException() != null).count();
        double errorRate = completedCalls.isEmpty() ? 0 : (errorCount * 100.0) / completedCalls.size();

        JsonObject report = new JsonObject();
        report.addProperty("session_id", sessionId);
        report.addProperty("language", "java");
        report.addProperty("timestamp", System.currentTimeMillis() / 1000.0);

        JsonObject metrics = new JsonObject();
        metrics.addProperty("requests_per_second", requestsPerSec);
        metrics.addProperty("avg_latency_ms", avgLatency);
        metrics.addProperty("p50_latency_ms", p50);
        metrics.addProperty("p95_latency_ms", p95);
        metrics.addProperty("p99_latency_ms", p99);
        metrics.addProperty("error_rate_percent", errorRate);
        metrics.addProperty("total_requests", completedCalls.size());
        metrics.addProperty("total_errors", errorCount);
        metrics.addProperty("active_threads", callsByThread.size());
        report.add("metrics", metrics);

        // Thread breakdown
        JsonArray threadsArray = new JsonArray();
        for (Map.Entry<Long, List<MethodCall>> entry : callsByThread.entrySet()) {
            JsonObject thread = new JsonObject();
            thread.addProperty("thread_id", entry.getKey());
            thread.addProperty("thread_name", entry.getValue().get(0).getThreadName());
            thread.addProperty("call_count", entry.getValue().size());
            double threadTotal = entry.getValue().stream().mapToDouble(MethodCall::getDurationMs).sum();
            thread.addProperty("total_time_ms", threadTotal);
            threadsArray.add(thread);
        }
        report.add("threads", threadsArray);

        writeJsonFile(outputFile, report);
        LOGGER.info("[TrueFlow] Live Metrics exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export Mermaid sequence diagram.
     */
    private void exportMermaidDiagram(File dir) {
        File outputFile = new File(dir, sessionId + "_mermaid.md");
        StringBuilder sb = new StringBuilder();

        sb.append("```mermaid\n");
        sb.append("sequenceDiagram\n");
        sb.append("    autonumber\n");

        // Add participants
        Set<String> classes = new LinkedHashSet<>();
        for (MethodCall call : completedCalls) {
            String shortName = call.getClassName().contains(".") ?
                call.getClassName().substring(call.getClassName().lastIndexOf('.') + 1) : call.getClassName();
            classes.add(shortName);
        }

        for (String className : classes) {
            sb.append("    participant ").append(className).append("\n");
        }

        // Add calls (limit to avoid huge diagrams)
        int callCount = 0;
        for (MethodCall call : completedCalls) {
            if (callCount++ > 100) {
                sb.append("    Note over ").append(classes.iterator().next())
                  .append(": ... and ").append(completedCalls.size() - 100).append(" more calls\n");
                break;
            }

            String shortName = call.getClassName().contains(".") ?
                call.getClassName().substring(call.getClassName().lastIndexOf('.') + 1) : call.getClassName();

            sb.append("    ").append(shortName).append("->>").append(shortName)
              .append(": ").append(call.getMethodName());
            if (call.getDurationMs() > 0) {
                sb.append(String.format(" (%.1fms)", call.getDurationMs()));
            }
            sb.append("\n");

            if (call.getException() != null) {
                sb.append("    Note right of ").append(shortName).append(": ERROR: ")
                  .append(call.getException().substring(0, Math.min(30, call.getException().length()))).append("\n");
            }
        }

        sb.append("```\n");
        writeTextFile(outputFile, sb.toString());
        LOGGER.info("[TrueFlow] Mermaid diagram exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export D2 diagram.
     */
    private void exportD2Diagram(File dir) {
        File outputFile = new File(dir, sessionId + ".d2");
        StringBuilder sb = new StringBuilder();

        sb.append("# TrueFlow Java Execution Trace\n");
        sb.append("# Session: ").append(sessionId).append("\n\n");

        // Group by class
        Map<String, List<MethodCall>> callsByClass = new LinkedHashMap<>();
        for (MethodCall call : completedCalls) {
            callsByClass.computeIfAbsent(call.getClassName(), k -> new ArrayList<>()).add(call);
        }

        // Create class nodes
        for (String className : callsByClass.keySet()) {
            String shortName = className.contains(".") ?
                className.substring(className.lastIndexOf('.') + 1) : className;
            String safeName = shortName.replaceAll("[^a-zA-Z0-9]", "_");
            sb.append(safeName).append(": ").append(shortName).append(" {\n");
            sb.append("  shape: class\n");

            // Add unique methods
            Set<String> methods = new LinkedHashSet<>();
            for (MethodCall call : callsByClass.get(className)) {
                methods.add(call.getMethodName());
            }
            for (String method : methods) {
                sb.append("  ").append(method).append("\n");
            }
            sb.append("}\n\n");
        }

        // Add call relationships
        Set<String> edges = new LinkedHashSet<>();
        for (MethodCall call : completedCalls) {
            if (call.getParentId() != null) {
                // Find parent call
                for (MethodCall parent : completedCalls) {
                    if (parent.getCallId().equals(call.getParentId())) {
                        String fromClass = parent.getClassName().contains(".") ?
                            parent.getClassName().substring(parent.getClassName().lastIndexOf('.') + 1) : parent.getClassName();
                        String toClass = call.getClassName().contains(".") ?
                            call.getClassName().substring(call.getClassName().lastIndexOf('.') + 1) : call.getClassName();
                        String fromSafe = fromClass.replaceAll("[^a-zA-Z0-9]", "_");
                        String toSafe = toClass.replaceAll("[^a-zA-Z0-9]", "_");
                        if (!fromSafe.equals(toSafe)) {
                            edges.add(fromSafe + " -> " + toSafe);
                        }
                        break;
                    }
                }
            }
        }

        for (String edge : edges) {
            sb.append(edge).append("\n");
        }

        writeTextFile(outputFile, sb.toString());
        LOGGER.info("[TrueFlow] D2 diagram exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export LLM-friendly text summary.
     */
    private void exportLlmTextSummary(File dir) {
        File outputFile = new File(dir, sessionId + "_llm_summary.txt");
        StringBuilder sb = new StringBuilder();

        sb.append("=== JAVA EXECUTION TRACE SUMMARY ===\n\n");
        sb.append("Session ID: ").append(sessionId).append("\n");
        sb.append("Total Method Calls: ").append(completedCalls.size()).append("\n");
        sb.append("Unique Methods: ").append(registeredMethods.size()).append("\n\n");

        // Top slowest methods
        sb.append("=== SLOWEST METHODS (Top 10) ===\n");
        completedCalls.stream()
            .sorted((a, b) -> Double.compare(b.getDurationMs(), a.getDurationMs()))
            .limit(10)
            .forEach(call -> sb.append(String.format("- %s.%s: %.2fms\n",
                call.getClassName(), call.getMethodName(), call.getDurationMs())));
        sb.append("\n");

        // Methods by protocol
        sb.append("=== CALLS BY PROTOCOL ===\n");
        Map<String, Long> byProtocol = completedCalls.stream()
            .filter(c -> c.getProtocol() != null)
            .collect(java.util.stream.Collectors.groupingBy(MethodCall::getProtocol, java.util.stream.Collectors.counting()));
        for (Map.Entry<String, Long> entry : byProtocol.entrySet()) {
            sb.append("- ").append(entry.getKey()).append(": ").append(entry.getValue()).append(" calls\n");
        }
        sb.append("\n");

        // Exceptions
        long errorCount = completedCalls.stream().filter(c -> c.getException() != null).count();
        if (errorCount > 0) {
            sb.append("=== EXCEPTIONS (").append(errorCount).append(" total) ===\n");
            completedCalls.stream()
                .filter(c -> c.getException() != null)
                .limit(5)
                .forEach(call -> sb.append("- ").append(call.getClassName()).append(".")
                    .append(call.getMethodName()).append(": ")
                    .append(call.getException()).append("\n"));
            sb.append("\n");
        }

        // Entry points
        sb.append("=== API ENTRY POINTS ===\n");
        completedCalls.stream()
            .filter(c -> "API_ENTRY".equals(c.getInvocationType()))
            .forEach(call -> sb.append("- ").append(call.getClassName()).append(".")
                .append(call.getMethodName()).append("\n"));

        writeTextFile(outputFile, sb.toString());
        LOGGER.info("[TrueFlow] LLM Summary exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export Markdown summary.
     */
    private void exportMarkdownSummary(File dir) {
        File outputFile = new File(dir, sessionId + "_summary.md");
        StringBuilder sb = new StringBuilder();

        sb.append("# TrueFlow Java Execution Trace\n\n");
        sb.append("## Overview\n\n");
        sb.append("| Metric | Value |\n");
        sb.append("|--------|-------|\n");
        sb.append("| Session ID | `").append(sessionId).append("` |\n");
        sb.append("| Total Calls | ").append(completedCalls.size()).append(" |\n");
        sb.append("| Unique Methods | ").append(registeredMethods.size()).append(" |\n");
        double totalTime = completedCalls.stream().mapToDouble(MethodCall::getDurationMs).sum();
        sb.append("| Total Duration | ").append(String.format("%.2f", totalTime)).append("ms |\n");
        long errors = completedCalls.stream().filter(c -> c.getException() != null).count();
        sb.append("| Errors | ").append(errors).append(" |\n\n");

        // Top 10 slowest
        sb.append("## Slowest Methods\n\n");
        sb.append("| Method | Duration | Calls |\n");
        sb.append("|--------|----------|-------|\n");

        Map<String, double[]> methodStats = new LinkedHashMap<>();
        for (MethodCall call : completedCalls) {
            String key = call.getClassName() + "." + call.getMethodName();
            methodStats.computeIfAbsent(key, k -> new double[]{0, 0});
            methodStats.get(key)[0] += call.getDurationMs();
            methodStats.get(key)[1]++;
        }

        methodStats.entrySet().stream()
            .sorted((a, b) -> Double.compare(b.getValue()[0], a.getValue()[0]))
            .limit(10)
            .forEach(e -> sb.append("| `").append(e.getKey()).append("` | ")
                .append(String.format("%.2f", e.getValue()[0])).append("ms | ")
                .append((int) e.getValue()[1]).append(" |\n"));
        sb.append("\n");

        // Exceptions
        if (errors > 0) {
            sb.append("## Exceptions\n\n");
            completedCalls.stream()
                .filter(c -> c.getException() != null)
                .limit(10)
                .forEach(call -> sb.append("- **").append(call.getClassName()).append(".")
                    .append(call.getMethodName()).append("**: `")
                    .append(call.getException()).append("`\n"));
            sb.append("\n");
        }

        sb.append("---\n*Generated by TrueFlow*\n");
        writeTextFile(outputFile, sb.toString());
        LOGGER.info("[TrueFlow] Markdown Summary exported to: " + outputFile.getAbsolutePath());
    }

    /**
     * Export ASCII art visualization.
     */
    private void exportAsciiArt(File dir) {
        File outputFile = new File(dir, sessionId + "_ascii.txt");
        StringBuilder sb = new StringBuilder();

        sb.append("+==============================================================================+\n");
        sb.append("|                          TRUEFLOW JAVA EXECUTION TRACE                        |\n");
        sb.append("+==============================================================================+\n");
        sb.append("| Session: ").append(String.format("%-68s", sessionId)).append(" |\n");
        sb.append("| Total Calls: ").append(String.format("%-64d", completedCalls.size())).append(" |\n");
        sb.append("+==============================================================================+\n\n");

        // Call tree (limited depth view)
        sb.append("CALL TREE:\n");
        sb.append("==========\n\n");

        int count = 0;
        for (MethodCall call : completedCalls) {
            if (count++ > 50) {
                sb.append("  ... and ").append(completedCalls.size() - 50).append(" more calls\n");
                break;
            }

            // Indent based on depth
            for (int i = 0; i < call.getDepth(); i++) {
                sb.append("  ");
            }

            String shortClass = call.getClassName().contains(".") ?
                call.getClassName().substring(call.getClassName().lastIndexOf('.') + 1) : call.getClassName();

            if (call.getDepth() > 0) {
                sb.append("+-- ");
            }

            sb.append(shortClass).append(".").append(call.getMethodName());
            if (call.getDurationMs() > 0) {
                sb.append(String.format(" [%.1fms]", call.getDurationMs()));
            }
            if (call.getException() != null) {
                sb.append(" [ERROR]");
            }
            if (call.getProtocol() != null) {
                sb.append(" (").append(call.getProtocol()).append(")");
            }
            sb.append("\n");
        }

        writeTextFile(outputFile, sb.toString());
        LOGGER.info("[TrueFlow] ASCII Art exported to: " + outputFile.getAbsolutePath());
    }

    // Helper methods
    private void writeJsonFile(File file, JsonObject json) {
        try (FileWriter writer = new FileWriter(file)) {
            GSON.toJson(json, writer);
        } catch (IOException e) {
            throw new RuntimeException("Failed to write JSON file: " + file.getAbsolutePath(), e);
        }
    }

    private void writeTextFile(File file, String content) {
        try (FileWriter writer = new FileWriter(file)) {
            writer.write(content);
        } catch (IOException e) {
            throw new RuntimeException("Failed to write file: " + file.getAbsolutePath(), e);
        }
    }

    private double getPercentile(List<Double> sortedValues, int percentile) {
        if (sortedValues.isEmpty()) return 0;
        int index = (int) Math.ceil(percentile / 100.0 * sortedValues.size()) - 1;
        return sortedValues.get(Math.max(0, Math.min(index, sortedValues.size() - 1)));
    }

    /**
     * Get the branch registry JSON for "Why Not Covered" analysis.
     * Returns null if branch analysis is not complete yet.
     */
    public String getBranchRegistryJson() {
        if (!branchAnalysisComplete || branchAnalyzer == null) {
            return null;
        }
        return branchAnalyzer.toBranchRegistryJson(sessionId);
    }

    /**
     * Check if branch analysis is complete.
     */
    public boolean isBranchAnalysisComplete() {
        return branchAnalysisComplete;
    }

    // Getters
    public boolean isEnabled() { return enabled; }
    public String getSessionId() { return sessionId; }
    public int getTotalCalls() { return totalCalls.get(); }
    public int getRegisteredMethodCount() { return registeredMethods.size(); }

    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
