package com.trueflow.agent;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.stmt.*;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import java.io.File;
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.logging.Logger;

/**
 * Analyzes Java source files to extract branch information for "Why Not Covered" analysis.
 * Uses JavaParser to parse AST and identify:
 * - All branches (if/else, switch, try/catch, for, while, do-while)
 * - All method call sites with their containing branch context
 *
 * This enables showing ACTUAL branch conditions like "if (config.isEnabled() && user.isAdmin())"
 * instead of generic "condition was False".
 */
public class JavaBranchAnalyzer {
    private static final Logger LOGGER = Logger.getLogger(JavaBranchAnalyzer.class.getName());

    private final JavaParser parser;
    private final Path projectRoot;
    private final List<CallSiteInfo> callSites = new ArrayList<>();
    private final Map<String, List<BranchInfo>> methodBranches = new HashMap<>();
    private final Set<String> analyzedMethods = new HashSet<>();

    /**
     * Information about a branch in the code.
     */
    public static class BranchInfo {
        public final String type;        // "if", "else", "switch", "case", "try", "catch", "for", "while", "do"
        public final String condition;   // The actual condition text
        public final int line;           // Line number of branch
        public final int endLine;        // End line of branch block

        public BranchInfo(String type, String condition, int line, int endLine) {
            this.type = type;
            this.condition = condition;
            this.line = line;
            this.endLine = endLine;
        }

        public JsonObject toJson() {
            JsonObject json = new JsonObject();
            json.addProperty("type", type);
            json.addProperty("condition", condition);
            json.addProperty("line", line);
            json.addProperty("end_line", endLine);
            return json;
        }
    }

    /**
     * Information about a method call site.
     */
    public static class CallSiteInfo {
        public final String callee;          // Method being called
        public final String caller;          // Method containing the call
        public final String callerClass;     // Class containing the call
        public final String file;            // File path
        public final int line;               // Line number of the call
        public final BranchInfo inBranch;    // Branch info if call is inside a branch (null if unconditional)

        public CallSiteInfo(String callee, String caller, String callerClass, String file, int line, BranchInfo inBranch) {
            this.callee = callee;
            this.caller = caller;
            this.callerClass = callerClass;
            this.file = file;
            this.line = line;
            this.inBranch = inBranch;
        }

        public JsonObject toJson() {
            JsonObject json = new JsonObject();
            json.addProperty("callee", callee);
            json.addProperty("caller", caller);
            json.addProperty("caller_module", callerClass);
            json.addProperty("file", file);
            json.addProperty("line", line);

            if (inBranch != null) {
                json.add("in_branch", inBranch.toJson());
            } else {
                json.add("in_branch", null);
            }

            return json;
        }
    }

    public JavaBranchAnalyzer(Path projectRoot) {
        this.projectRoot = projectRoot;
        this.parser = new JavaParser();
    }

    /**
     * Scan the project for Java source files and analyze them.
     */
    public void scan() {
        LOGGER.info("[TrueFlow] Scanning Java source files in: " + projectRoot);

        try {
            Files.walkFileTree(projectRoot, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (file.toString().endsWith(".java") && !isExcluded(file)) {
                        analyzeFile(file);
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    String name = dir.getFileName().toString();
                    // Skip common non-source directories
                    if (name.equals("build") || name.equals("target") || name.equals(".git") ||
                        name.equals("node_modules") || name.equals(".gradle") || name.equals(".idea")) {
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException e) {
            LOGGER.warning("[TrueFlow] Error scanning project: " + e.getMessage());
        }

        LOGGER.info("[TrueFlow] Branch analysis complete: " + callSites.size() + " call sites, " +
                   methodBranches.size() + " methods with branches");
    }

    private boolean isExcluded(Path file) {
        String path = file.toString();
        return path.contains("test") || path.contains("Test") ||
               path.contains("generated") || path.contains("build");
    }

    /**
     * Analyze a single Java source file.
     */
    private void analyzeFile(Path file) {
        try {
            ParseResult<CompilationUnit> result = parser.parse(file);

            if (result.isSuccessful() && result.getResult().isPresent()) {
                CompilationUnit cu = result.getResult().get();
                String filePath = projectRoot.relativize(file).toString().replace('\\', '/');

                // Visit all classes
                cu.findAll(ClassOrInterfaceDeclaration.class).forEach(classDecl -> {
                    String className = classDecl.getFullyQualifiedName().orElse(classDecl.getNameAsString());

                    // Visit all methods
                    classDecl.findAll(MethodDeclaration.class).forEach(method -> {
                        analyzeMethod(method, className, filePath);
                    });
                });
            }
        } catch (Exception e) {
            LOGGER.fine("[TrueFlow] Could not parse: " + file + " - " + e.getMessage());
        }
    }

    /**
     * Analyze a method to extract branches and call sites.
     */
    private void analyzeMethod(MethodDeclaration method, String className, String filePath) {
        String methodName = method.getNameAsString();
        String methodKey = className + "." + methodName;
        analyzedMethods.add(methodKey);

        List<BranchInfo> branches = new ArrayList<>();

        // Stack to track current branch context
        Deque<BranchInfo> branchStack = new ArrayDeque<>();

        // Visit all statements to find branches and calls
        method.accept(new VoidVisitorAdapter<Void>() {

            @Override
            public void visit(IfStmt n, Void arg) {
                String condition = n.getCondition().toString();
                int line = n.getBegin().map(p -> p.line).orElse(0);
                int endLine = n.getEnd().map(p -> p.line).orElse(line);

                BranchInfo branch = new BranchInfo("if", condition, line, endLine);
                branches.add(branch);

                branchStack.push(branch);
                super.visit(n, arg);
                branchStack.pop();
            }

            @Override
            public void visit(SwitchStmt n, Void arg) {
                String condition = n.getSelector().toString();
                int line = n.getBegin().map(p -> p.line).orElse(0);
                int endLine = n.getEnd().map(p -> p.line).orElse(line);

                BranchInfo branch = new BranchInfo("switch", condition, line, endLine);
                branches.add(branch);

                branchStack.push(branch);
                super.visit(n, arg);
                branchStack.pop();
            }

            @Override
            public void visit(TryStmt n, Void arg) {
                int line = n.getBegin().map(p -> p.line).orElse(0);
                int endLine = n.getEnd().map(p -> p.line).orElse(line);

                BranchInfo branch = new BranchInfo("try", "try block", line, endLine);
                branches.add(branch);

                branchStack.push(branch);
                n.getTryBlock().accept(this, arg);
                branchStack.pop();

                // Handle catch blocks
                n.getCatchClauses().forEach(catchClause -> {
                    String exceptionType = catchClause.getParameter().getTypeAsString();
                    int catchLine = catchClause.getBegin().map(p -> p.line).orElse(0);
                    int catchEndLine = catchClause.getEnd().map(p -> p.line).orElse(catchLine);

                    BranchInfo catchBranch = new BranchInfo("catch", exceptionType, catchLine, catchEndLine);
                    branches.add(catchBranch);

                    branchStack.push(catchBranch);
                    catchClause.getBody().accept(this, arg);
                    branchStack.pop();
                });

                // Handle finally block
                n.getFinallyBlock().ifPresent(finallyBlock -> {
                    int finallyLine = finallyBlock.getBegin().map(p -> p.line).orElse(0);
                    int finallyEndLine = finallyBlock.getEnd().map(p -> p.line).orElse(finallyLine);

                    BranchInfo finallyBranch = new BranchInfo("finally", "finally block", finallyLine, finallyEndLine);
                    branches.add(finallyBranch);

                    branchStack.push(finallyBranch);
                    finallyBlock.accept(this, arg);
                    branchStack.pop();
                });
            }

            @Override
            public void visit(ForStmt n, Void arg) {
                String condition = n.getCompare().map(Object::toString).orElse("true");
                int line = n.getBegin().map(p -> p.line).orElse(0);
                int endLine = n.getEnd().map(p -> p.line).orElse(line);

                BranchInfo branch = new BranchInfo("for", condition, line, endLine);
                branches.add(branch);

                branchStack.push(branch);
                super.visit(n, arg);
                branchStack.pop();
            }

            @Override
            public void visit(ForEachStmt n, Void arg) {
                String condition = n.getVariable().toString() + " : " + n.getIterable().toString();
                int line = n.getBegin().map(p -> p.line).orElse(0);
                int endLine = n.getEnd().map(p -> p.line).orElse(line);

                BranchInfo branch = new BranchInfo("for-each", condition, line, endLine);
                branches.add(branch);

                branchStack.push(branch);
                super.visit(n, arg);
                branchStack.pop();
            }

            @Override
            public void visit(WhileStmt n, Void arg) {
                String condition = n.getCondition().toString();
                int line = n.getBegin().map(p -> p.line).orElse(0);
                int endLine = n.getEnd().map(p -> p.line).orElse(line);

                BranchInfo branch = new BranchInfo("while", condition, line, endLine);
                branches.add(branch);

                branchStack.push(branch);
                super.visit(n, arg);
                branchStack.pop();
            }

            @Override
            public void visit(DoStmt n, Void arg) {
                String condition = n.getCondition().toString();
                int line = n.getBegin().map(p -> p.line).orElse(0);
                int endLine = n.getEnd().map(p -> p.line).orElse(line);

                BranchInfo branch = new BranchInfo("do-while", condition, line, endLine);
                branches.add(branch);

                branchStack.push(branch);
                super.visit(n, arg);
                branchStack.pop();
            }

            @Override
            public void visit(MethodCallExpr n, Void arg) {
                String callee = n.getNameAsString();
                int line = n.getBegin().map(p -> p.line).orElse(0);

                // Get current branch context (innermost branch containing this call)
                BranchInfo currentBranch = branchStack.peek();

                CallSiteInfo callSite = new CallSiteInfo(
                    callee, methodName, className, filePath, line, currentBranch
                );
                callSites.add(callSite);

                super.visit(n, arg);
            }

        }, null);

        if (!branches.isEmpty()) {
            methodBranches.put(methodKey, branches);
        }
    }

    /**
     * Get all call sites.
     */
    public List<CallSiteInfo> getCallSites() {
        return callSites;
    }

    /**
     * Get branches for a specific method.
     */
    public List<BranchInfo> getBranchesForMethod(String methodKey) {
        return methodBranches.getOrDefault(methodKey, Collections.emptyList());
    }

    /**
     * Get all method branches.
     */
    public Map<String, List<BranchInfo>> getMethodBranches() {
        return methodBranches;
    }

    /**
     * Generate branch registry JSON for sending to IDE.
     */
    public String toBranchRegistryJson(String sessionId) {
        JsonObject registry = new JsonObject();
        registry.addProperty("type", "branch_registry");
        registry.addProperty("timestamp", System.currentTimeMillis() / 1000.0);
        registry.addProperty("session_id", sessionId);
        registry.addProperty("language", "java");

        // Add standard fields for compatibility
        registry.addProperty("call_id", "branch_registry_event");
        registry.addProperty("module", "__branch_registry__");
        registry.addProperty("function", "__branch_registry__");
        registry.addProperty("file", "");
        registry.addProperty("line", 0);
        registry.addProperty("depth", 0);
        registry.add("parent_id", null);
        registry.add("correlation_id", null);
        registry.add("learning_phase", null);

        JsonObject traceData = new JsonObject();
        traceData.addProperty("total_call_sites", callSites.size());

        // Add call sites
        JsonArray callSitesJson = new JsonArray();
        for (CallSiteInfo site : callSites) {
            callSitesJson.add(site.toJson());
        }
        traceData.add("call_sites", callSitesJson);

        // Add function branches
        JsonObject funcBranchesJson = new JsonObject();
        for (Map.Entry<String, List<BranchInfo>> entry : methodBranches.entrySet()) {
            JsonObject funcInfo = new JsonObject();
            JsonArray branchesArray = new JsonArray();
            for (BranchInfo branch : entry.getValue()) {
                branchesArray.add(branch.toJson());
            }
            funcInfo.add("branches", branchesArray);
            funcBranchesJson.add(entry.getKey(), funcInfo);
        }
        traceData.add("function_branches", funcBranchesJson);

        registry.add("trace_data", traceData);

        return registry.toString();
    }
}
