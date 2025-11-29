# Auto-Integration Feature - One-Click Tracing Setup

## Overview

The **Auto-Integration** feature allows you to add tracing to any Python repository with just a few clicks - no manual configuration required!

## How to Use

### Step 1: Open Auto-Integration Dialog

**Three ways to access:**

1. **Toolbar Button** (Easiest)
   - Open "Learning Flow Visualizer" tool window
   - Click green "Auto-Integrate into Repo" button in toolbar

2. **Menu**
   - Go to `Tools` → `Learning Flow` → `Auto-Integrate into Repo`

3. **Keyboard Shortcut**
   - Press `Ctrl+Shift+I` (Windows/Linux) or `Cmd+Shift+I` (Mac)

### Step 2: Select Entry Point

1. Click "Browse..." next to "Entry Point"
2. Navigate to your main Python file:
   - `main.py`
   - `app.py`
   - `manage.py` (Django)
   - `run.py`
   - Any file you run to start your application

### Step 3: Choose Integration Method

Three methods available:

#### Method 1: Environment Variable (Recommended) ⭐

**Zero code changes!**

- Adds `CRAWL4AI_AUTO_TRACE=1` to environment
- No modifications to your source files
- Easiest to remove later
- Perfect for trying out tracing

#### Method 2: Single-Line Import

**Minimal code change:**

Adds one line to top of your entry point:
```python
from crawl4ai.embodied_ai.monitoring.auto_instrumentor import enable_auto_tracing; enable_auto_tracing(output_dir='./traces')
```

- Automatic instrumentation
- Easy to remove (just delete one line)
- Good for permanent integration

#### Method 3: Run Configuration Only

**No file changes:**

- Creates PyCharm run configuration with environment variables
- Tracing only active when using that run config
- Easy on/off switching

### Step 4: Configure (Optional)

**Trace Directory:**
- Default: `./traces`
- Change if you want traces elsewhere

**Modules to Trace:**
- Leave empty to trace everything
- Or specify: `myapp,mylib` to trace only those modules

**Exclude Modules:**
- Default: `test,tests,pytest,unittest`
- Add more if needed: `test,docs,migrations`

**Checkboxes:**
- ✅ Create PyCharm run configuration - Recommended!
- ✅ Open trace directory after integration - See traces immediately

### Step 5: Click OK!

That's it! The dialog will:

1. ✅ Create trace directory
2. ✅ Add environment variable or import (based on method chosen)
3. ✅ Create run configuration (if checked)
4. ✅ Open tool window to trace directory (if checked)
5. ✅ Show success message with next steps

---

## What Gets Created

### Trace Directory

```
your-project/
├── traces/               # New directory created
│   ├── session_*.puml   # PlantUML diagrams
│   ├── session_*_performance.json
│   └── session_*_dead_code.json
├── main.py              # Your entry point (optionally modified)
└── ...
```

### Environment Variables (Method 1 & 3)

```bash
CRAWL4AI_AUTO_TRACE=1
CRAWL4AI_TRACE_DIR=./traces
CRAWL4AI_TRACE_MODULES=myapp  # If specified
CRAWL4AI_EXCLUDE_MODULES=test,pytest  # If specified
```

### Import Statement (Method 2)

```python
# Auto-instrumentation - Added by Learning Flow Visualizer
from crawl4ai.embodied_ai.monitoring.auto_instrumentor import enable_auto_tracing; enable_auto_tracing(output_dir='./traces', modules_to_trace=['myapp'], exclude_modules=['test', 'pytest'])

# Rest of your code...
```

### Run Configuration

A new run configuration named "Trace: your_entry_point" with:
- Script path: `/path/to/your/main.py`
- Environment variables: Set automatically
- Working directory: Your project root

---

## Example Workflows

### Example 1: Trying Tracing for First Time

**Goal:** Just want to see what tracing looks like

**Steps:**
1. Click "Auto-Integrate into Repo"
2. Select `main.py`
3. Choose "Environment Variable (Recommended)"
4. Click OK
5. Run your app normally
6. Open "Learning Flow Visualizer" → see traces!

**To Remove Later:**
- Just uncheck "Enable Auto-Tracing" in toolbar
- Or remove environment variable

### Example 2: Adding Tracing to Existing Django Project

**Goal:** Permanent tracing for development

**Steps:**
1. Click "Auto-Integrate into Repo"
2. Select `manage.py`
3. Choose "Single-Line Import"
4. Modules to trace: `myapp,api,core`
5. Exclude: `test,migrations`
6. Check "Create run configuration"
7. Click OK

**Result:**
- One line added to `manage.py`
- Run config "Trace: manage" created
- Traces only when using that run config
- Easy to commit to version control

### Example 3: FastAPI Production App

**Goal:** Optional tracing, no code changes

**Steps:**
1. Click "Auto-Integrate into Repo"
2. Select `app.py`
3. Choose "Run Configuration Only"
4. Modules to trace: `api,services`
5. Exclude: `test,docs`
6. Click OK

**Result:**
- No code changes
- Run config "Trace: app" created
- Normal run = no tracing
- "Trace: app" run = full tracing
- Perfect for production debugging

---

## Advanced Configuration

### Custom Trace Directory

Want traces in a specific location?

1. In Auto-Integration dialog
2. Click "Browse..." next to "Trace Directory"
3. Select custom folder (e.g., `/logs/traces`)
4. Click OK

### Multiple Entry Points

Have multiple entry points (CLI, web server, worker)?

**Option 1: Integrate each separately**
- Auto-integrate for `main.py` → creates "Trace: main"
- Auto-integrate for `worker.py` → creates "Trace: worker"
- Auto-integrate for `api.py` → creates "Trace: api"
- Switch between run configs as needed

**Option 2: Single import in shared module**
- Create `tracing_setup.py`:
  ```python
  from crawl4ai.embodied_ai.monitoring.auto_instrumentor import enable_auto_tracing
  enable_auto_tracing()
  ```
- Import in each entry point:
  ```python
  import tracing_setup  # Enables tracing
  ```

### Trace Only Specific Modules

Large codebase? Don't want to trace everything?

1. In "Modules to Trace" field, enter: `myapp.api,myapp.core`
2. This traces ONLY those modules
3. Everything else ignored = lower overhead

### Exclude Test Code

Don't want test code in traces?

1. "Exclude Modules": `test,tests,pytest,unittest,mock`
2. All test-related code excluded
3. Cleaner traces

---

## Troubleshooting

### Issue: No traces generated after integration

**Solution 1: Check trace directory**
```bash
ls traces/
# Should see session_*.puml files after running app
```

**Solution 2: Check environment variable is set**
- Open run configuration: `Run` → `Edit Configurations`
- Verify `CRAWL4AI_AUTO_TRACE=1` is present
- If not, rerun auto-integration

**Solution 3: Check import was added (Method 2)**
- Open your entry point file
- Look for import at top
- If missing, rerun auto-integration

### Issue: "Import error: No module named 'crawl4ai'"

**Solution:** Install crawl4ai package
```bash
pip install crawl4ai
# or
conda install crawl4ai
```

### Issue: Tracing slows down app too much

**Solution 1: Reduce scope**
- Rerun auto-integration
- Set "Modules to Trace" to specific modules only
- Example: `myapp.api` instead of tracing everything

**Solution 2: Exclude more modules**
- Add to "Exclude Modules": `vendor,third_party,lib`

**Solution 3: Disable stdlib tracing**
- Edit import (Method 2):
  ```python
  enable_auto_tracing(trace_stdlib=False)
  ```

### Issue: Want to remove tracing

**Method 1 (Environment Variable):**
- Uncheck "Enable Auto-Tracing" in toolbar
- OR delete environment variable from run config

**Method 2 (Single-Line Import):**
- Open entry point file
- Delete the import line
- Done!

**Method 3 (Run Configuration Only):**
- Use normal run config instead of "Trace: ..." config
- OR delete "Trace: ..." config

---

## Comparison of Integration Methods

| Feature | Environment Variable | Single-Line Import | Run Config Only |
|---------|---------------------|-------------------|-----------------|
| **Code Changes** | None | One line | None |
| **Easy to Remove** | Very easy | Easy | Very easy |
| **Permanent** | No | Yes (if committed) | No |
| **Version Control** | Not committed | Can commit | Not committed |
| **Team Sharing** | Everyone must set | Automatic for team | Everyone must create |
| **Production Safe** | Yes (just don't set var) | Yes (conditional) | Yes |
| **Recommended For** | Trying out, debugging | Permanent dev setup | Optional tracing |

---

## Best Practices

### 1. Start with Environment Variable

- Try tracing first without code changes
- See if it's useful for your project
- Easy to remove if you don't like it

### 2. Commit Single-Line Import for Team

- If everyone on team wants tracing
- Add import to main entry point
- Commit to version control
- Everyone gets tracing automatically

### 3. Use Run Configs for Different Scenarios

- "Normal Run" - no tracing
- "Trace: full" - trace everything
- "Trace: api-only" - trace only API modules
- Switch based on what you're debugging

### 4. Exclude Tests and Migrations

- Always exclude `test,tests,pytest,unittest`
- For Django: also exclude `migrations`
- Cleaner traces, better performance

### 5. Archive Traces

- Traces can get large over time
- Periodically archive: `mv traces traces_archive_2025_01`
- Or add `traces/` to `.gitignore`

---

## Summary

**Auto-Integration makes tracing effortless:**

1. ⚡ Click "Auto-Integrate into Repo"
2. 📂 Select your `main.py` (or any entry point)
3. 🎯 Choose integration method (Environment Variable recommended)
4. ✅ Click OK
5. 🚀 Run your app - traces appear automatically!

**No manual configuration. No reading docs. Just works!**

---

**Plugin complete with one-click auto-integration!**
