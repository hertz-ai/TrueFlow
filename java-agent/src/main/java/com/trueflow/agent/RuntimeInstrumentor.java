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
    private final Set<String> registeredMethods = ConcurrentHashMap.newKeySet();

    // Counters
    private final AtomicLong callIdCounter = new AtomicLong(0);
    private final AtomicInteger totalCalls = new AtomicInteger(0);
    private final AtomicInteger sampleCounter = new AtomicInteger(0);

    // Event listeners (for socket streaming)
    private final List<Consumer<String>> eventListeners = new ArrayList<>();

    // State flags
    private volatile boolean enabled = true;
    private volatile boolean finalized = false;

    public RuntimeInstrumentor(AgentConfig config) {
        this.config = config;
        this.sessionId = "session_" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        LOGGER.info("[TrueFlow] Session ID: " + sessionId);
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

            // Register method for function registry
            String methodKey = className + "." + methodName;
            registeredMethods.add(methodKey);

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
        for (String method : registeredMethods) {
            String[] parts = method.split("\\.", 2);
            JsonObject func = new JsonObject();
            func.addProperty("module", parts.length > 0 ? parts[0] : "");
            func.addProperty("function", parts.length > 1 ? parts[1] : method);
            functions.add(func);
        }
        traceData.add("functions", functions);
        registry.add("trace_data", traceData);

        return registry.toString();
    }

    /**
     * Finalize tracing and export results.
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

            try (FileWriter writer = new FileWriter(outputFile)) {
                GSON.toJson(output, writer);
            }

            LOGGER.info("[TrueFlow] Trace exported to: " + outputFile.getAbsolutePath());

        } catch (IOException e) {
            LOGGER.severe("[TrueFlow] Failed to export trace: " + e.getMessage());
        }
    }

    // Getters
    public boolean isEnabled() { return enabled; }
    public String getSessionId() { return sessionId; }
    public int getTotalCalls() { return totalCalls.get(); }
    public int getRegisteredMethodCount() { return registeredMethods.size(); }

    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
