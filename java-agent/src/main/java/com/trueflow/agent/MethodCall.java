package com.trueflow.agent;

import com.google.gson.JsonObject;

/**
 * Represents a single method call with timing and context information.
 * Equivalent to Python's FunctionCall class.
 */
public class MethodCall {
    private final String callId;
    private final String className;
    private final String methodName;
    private final String signature;
    private final String sourceFile;
    private final int lineNumber;
    private final long startTime;
    private final int depth;
    private final String parentId;
    private final long threadId;
    private final String threadName;

    private long endTime;
    private double durationMs;
    private String returnType;
    private String exception;
    private String protocol;
    private String invocationType;

    public MethodCall(String callId, String className, String methodName, String signature,
                      String sourceFile, int lineNumber, int depth, String parentId,
                      long threadId, String threadName) {
        this.callId = callId;
        this.className = className;
        this.methodName = methodName;
        this.signature = signature;
        this.sourceFile = sourceFile;
        this.lineNumber = lineNumber;
        this.startTime = System.nanoTime();
        this.depth = depth;
        this.parentId = parentId;
        this.threadId = threadId;
        this.threadName = threadName;
        this.protocol = detectProtocol(className, methodName);
        this.invocationType = detectInvocationType(className, methodName);
    }

    /**
     * Mark the method as returned and calculate duration.
     */
    public void markReturned() {
        this.endTime = System.nanoTime();
        this.durationMs = (endTime - startTime) / 1_000_000.0;
    }

    /**
     * Mark the method as exited with an exception.
     */
    public void markException(String exceptionClass, String message) {
        this.endTime = System.nanoTime();
        this.durationMs = (endTime - startTime) / 1_000_000.0;
        this.exception = exceptionClass + ": " + (message != null ? message : "");
    }

    /**
     * Detect the protocol type based on class/method patterns.
     */
    private String detectProtocol(String className, String methodName) {
        String lowerClass = className.toLowerCase();
        String lowerMethod = methodName.toLowerCase();

        // SQL/Database
        if (lowerClass.contains("jdbc") || lowerClass.contains("datasource") ||
                lowerClass.contains("connection") || lowerClass.contains("statement") ||
                lowerClass.contains("resultset") || lowerClass.contains("repository") ||
                lowerClass.contains("hibernate") || lowerClass.contains("jpa") ||
                lowerClass.contains("mybatis")) {
            return "SQL";
        }

        // HTTP/REST
        if (lowerClass.contains("httpclient") || lowerClass.contains("resttemplate") ||
                lowerClass.contains("webclient") || lowerClass.contains("controller") ||
                lowerClass.contains("servlet") || lowerClass.contains("feign") ||
                lowerMethod.contains("doget") || lowerMethod.contains("dopost") ||
                lowerMethod.contains("dorequest")) {
            return "HTTP";
        }

        // gRPC
        if (lowerClass.contains("grpc") || lowerClass.contains("protobuf") ||
                lowerClass.contains("stub")) {
            return "gRPC";
        }

        // Kafka
        if (lowerClass.contains("kafka") || lowerClass.contains("producer") ||
                lowerClass.contains("consumer")) {
            return "Kafka";
        }

        // RabbitMQ/AMQP
        if (lowerClass.contains("rabbit") || lowerClass.contains("amqp")) {
            return "AMQP";
        }

        // Redis
        if (lowerClass.contains("redis") || lowerClass.contains("jedis") ||
                lowerClass.contains("lettuce")) {
            return "Redis";
        }

        // WebSocket
        if (lowerClass.contains("websocket") || lowerClass.contains("stomp")) {
            return "WebSocket";
        }

        // Async
        if (lowerClass.contains("completablefuture") || lowerClass.contains("async") ||
                lowerClass.contains("reactive") || lowerClass.contains("flux") ||
                lowerClass.contains("mono") || lowerMethod.contains("subscribe")) {
            return "Async";
        }

        return null;
    }

    /**
     * Detect the invocation type (entry point, callback, etc.)
     */
    private String detectInvocationType(String className, String methodName) {
        String lowerClass = className.toLowerCase();
        String lowerMethod = methodName.toLowerCase();

        // API entry points
        if (lowerClass.contains("controller") || lowerClass.contains("resource") ||
                lowerClass.contains("endpoint")) {
            return "API_ENTRY";
        }

        // Event handlers
        if (lowerMethod.contains("handle") || lowerMethod.contains("process") ||
                lowerMethod.contains("on") || lowerMethod.contains("listener")) {
            return "EVENT_HANDLER";
        }

        // Scheduled tasks
        if (lowerClass.contains("scheduled") || lowerClass.contains("cron") ||
                lowerClass.contains("timer") || lowerMethod.contains("scheduled")) {
            return "SCHEDULED";
        }

        // Callbacks
        if (lowerMethod.contains("callback") || lowerMethod.contains("complete") ||
                lowerMethod.contains("accept") || lowerMethod.contains("apply")) {
            return "CALLBACK";
        }

        return "INTERNAL";
    }

    /**
     * Convert to JSON for call event.
     */
    public JsonObject toCallJson(String sessionId) {
        JsonObject json = new JsonObject();
        json.addProperty("type", "call");
        json.addProperty("timestamp", System.currentTimeMillis() / 1000.0);
        json.addProperty("call_id", callId);
        json.addProperty("module", className);
        json.addProperty("function", methodName);
        json.addProperty("signature", signature);
        json.addProperty("file", sourceFile);
        json.addProperty("line", lineNumber);
        json.addProperty("depth", depth);
        json.addProperty("parent_id", parentId);
        json.addProperty("thread_id", threadId);
        json.addProperty("thread_name", threadName);
        json.addProperty("session_id", sessionId);
        json.addProperty("process_id", ProcessHandle.current().pid());
        json.addProperty("language", "java");

        if (protocol != null) {
            json.addProperty("protocol", protocol);
        }
        if (invocationType != null) {
            json.addProperty("invocation_type", invocationType);
        }

        return json;
    }

    /**
     * Convert to JSON for return event.
     */
    public JsonObject toReturnJson(String sessionId) {
        JsonObject json = new JsonObject();
        json.addProperty("type", "return");
        json.addProperty("timestamp", System.currentTimeMillis() / 1000.0);
        json.addProperty("call_id", callId);
        json.addProperty("module", className);
        json.addProperty("function", methodName);
        json.addProperty("file", sourceFile);
        json.addProperty("line", lineNumber);
        json.addProperty("depth", depth);
        json.addProperty("parent_id", parentId);
        json.addProperty("duration_ms", durationMs);
        json.addProperty("thread_id", threadId);
        json.addProperty("session_id", sessionId);
        json.addProperty("process_id", ProcessHandle.current().pid());
        json.addProperty("language", "java");

        if (exception != null) {
            json.addProperty("exception", exception);
        }
        if (returnType != null) {
            json.addProperty("return_type", returnType);
        }

        return json;
    }

    // Getters
    public String getCallId() { return callId; }
    public String getClassName() { return className; }
    public String getMethodName() { return methodName; }
    public String getSignature() { return signature; }
    public String getSourceFile() { return sourceFile; }
    public int getLineNumber() { return lineNumber; }
    public long getStartTime() { return startTime; }
    public long getEndTime() { return endTime; }
    public double getDurationMs() { return durationMs; }
    public int getDepth() { return depth; }
    public String getParentId() { return parentId; }
    public long getThreadId() { return threadId; }
    public String getThreadName() { return threadName; }
    public String getException() { return exception; }
    public String getProtocol() { return protocol; }
    public String getInvocationType() { return invocationType; }

    public void setReturnType(String returnType) { this.returnType = returnType; }
}
