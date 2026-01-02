// TrueFlow Export Templates
// Externalized to avoid script tag escaping issues in template literals

window.TrueFlowExportTemplates = {

    // Generate standalone HTML export
    generateStandaloneHTML: function(data, watchArch) {
        const metadata = data.metadata || {};
        const functionsHTML = this.generateFunctionListHTML(data);
        const timelineHTML = this.generateTimelineHTML(data);
        const dataSourcesHTML = this.generateDataSourcesHTML(data);

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrueFlow Visualization - ${metadata.app_name || 'Unknown App'}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3a 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            text-align: center;
            padding: 30px;
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            margin-bottom: 20px;
        }
        .header h1 { color: #7dd3fc; font-size: 2.5em; margin-bottom: 10px; }
        .header .subtitle { color: #888; font-size: 1.2em; }
        .stats-row {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin: 20px 0;
        }
        .stat-card {
            background: rgba(74, 222, 128, 0.1);
            border: 1px solid rgba(74, 222, 128, 0.3);
            border-radius: 12px;
            padding: 20px 40px;
            text-align: center;
        }
        .stat-card.dead {
            background: rgba(239, 68, 68, 0.1);
            border-color: rgba(239, 68, 68, 0.3);
        }
        .stat-value { font-size: 2.5em; font-weight: bold; color: #4ade80; }
        .stat-card.dead .stat-value { color: #ef4444; }
        .stat-label { color: #888; margin-top: 5px; }
        .section {
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .section h2 { color: #7dd3fc; margin-bottom: 15px; border-bottom: 1px solid #3a3a5a; padding-bottom: 10px; }
        .func-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
        .func-item {
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 12px;
            cursor: pointer;
            transition: all 0.2s;
            border-left: 4px solid #4ade80;
        }
        .func-item:hover { background: rgba(255,255,255,0.1); transform: translateX(5px); }
        .func-item.dead { border-left-color: #ef4444; opacity: 0.7; }
        .func-name { font-weight: 600; color: #e0e0e0; }
        .func-info { font-size: 0.85em; color: #888; margin-top: 5px; }
        .timeline {
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: 400px;
            overflow-y: auto;
        }
        .timeline-event {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 10px 15px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            border-left: 3px solid #60a5fa;
        }
        .timeline-event.return { border-left-color: #a78bfa; }
        .event-time { font-family: monospace; color: #888; min-width: 80px; }
        .event-func { flex: 1; }
        .event-type {
            font-size: 0.75em;
            padding: 2px 8px;
            border-radius: 4px;
            background: rgba(96, 165, 250, 0.2);
        }
        .summary-section { margin-top: 20px; }
        .summary-section h3 { color: #a78bfa; margin-bottom: 10px; }
        .rationale-card, .missing-card {
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .rationale-card h4, .missing-card h4 { color: #fbbf24; margin-bottom: 8px; }
        .data-sources { display: flex; gap: 15px; flex-wrap: wrap; }
        .source-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
        }
        .source-badge.video { background: rgba(244, 114, 182, 0.2); color: #f472b6; }
        .source-badge.api { background: rgba(96, 165, 250, 0.2); color: #60a5fa; }
        .source-badge.audio { background: rgba(251, 191, 36, 0.2); color: #fbbf24; }
        .source-badge.screen { background: rgba(167, 139, 250, 0.2); color: #a78bfa; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>TrueFlow Visualization</h1>
            <div class="subtitle">${metadata.app_name || 'Python Application'} - ${metadata.timestamp || new Date().toISOString()}</div>
        </div>

        <div class="stats-row">
            <div class="stat-card">
                <div class="stat-value">${Object.keys(data.functions || {}).length}</div>
                <div class="stat-label">Total Functions</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${(data.covered_functions || []).length}</div>
                <div class="stat-label">Covered</div>
            </div>
            <div class="stat-card dead">
                <div class="stat-value">${(data.dead_functions || []).length}</div>
                <div class="stat-label">Dead Code</div>
            </div>
        </div>

        <div class="section">
            <h2>Functions</h2>
            <div class="func-list">
                ${functionsHTML}
            </div>
        </div>

        ${data.recorded_events?.length ? `
        <div class="section">
            <h2>Execution Timeline</h2>
            <div class="timeline">
                ${timelineHTML}
            </div>
        </div>
        ` : ''}

        ${data.rationales?.length ? `
        <div class="summary-section">
            <h3>AI Analysis</h3>
            ${data.rationales.map(r => `
                <div class="rationale-card">
                    <h4>${r.function}</h4>
                    <p>${r.rationale}</p>
                </div>
            `).join('')}
        </div>
        ` : ''}

        ${data.missing_calls?.length ? `
        <div class="summary-section">
            <h3>Missing Calls Analysis</h3>
            ${data.missing_calls.map(m => `
                <div class="missing-card">
                    <h4>Warning: ${m.function}</h4>
                    <p>Expected from: ${m.expected_caller || 'Unknown'}</p>
                    <p>Reason: ${m.reason}</p>
                </div>
            `).join('')}
        </div>
        ` : ''}

        <div class="summary-section">
            <h3>Data Sources</h3>
            ${dataSourcesHTML}
        </div>
    </div>
</body>
</html>`;
    },

    generateFunctionListHTML: function(data) {
        const functions = Object.entries(data.functions || {});
        const coveredSet = new Set(data.covered_functions || []);
        const deadSet = new Set(data.dead_functions || []);
        const importanceScores = data.importance_scores || {};

        return functions
            .sort((a, b) => (importanceScores[b[0]] || 0) - (importanceScores[a[0]] || 0))
            .map(([name, info]) => {
                const isDead = deadSet.has(name);
                const isCovered = coveredSet.has(name);
                return `
                    <div class="func-item ${isDead ? 'dead' : ''}" data-func="${name}">
                        <div class="func-name">${isDead ? '💀 ' : isCovered ? '✓ ' : ''}${name}</div>
                        <div class="func-info">Line ${info.line || '?'} ${info.file ? '• ' + info.file : ''}</div>
                    </div>
                `;
            }).join('');
    },

    generateTimelineHTML: function(data) {
        const events = data.recorded_events || [];
        return events.slice(0, 100).map(event => `
            <div class="timeline-event ${event.type}">
                <span class="event-time">${(event.timestamp / 1000).toFixed(3)}s</span>
                <span class="event-func">${event.function || event.name}</span>
                <span class="event-type">${event.type}</span>
            </div>
        `).join('');
    },

    generateDataSourcesHTML: function(data) {
        const sources = data.data_sources || ['api'];
        return `<div class="data-sources">
            ${sources.map(s => `<span class="source-badge ${s}">${s.toUpperCase()}</span>`).join('')}
        </div>`;
    },

    // Simple debug export
    generateDebugHTML: function(data, watchArch) {
        return `<!DOCTYPE html>
<html>
<head>
    <title>TrueFlow Debug Export</title>
    <style>
        body { font-family: monospace; background: #1a1a2e; color: #e0e0e0; padding: 20px; }
        pre { background: #0a0a1a; padding: 20px; border-radius: 8px; overflow: auto; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat { background: #2a2a4a; padding: 15px 25px; border-radius: 8px; }
        .stat-value { font-size: 24px; color: #4ade80; }
        .stat-label { color: #888; font-size: 12px; }
    </style>
</head>
<body>
    <h1>TrueFlow Debug Export</h1>
    <div class="stats">
        <div class="stat">
            <div class="stat-value">${Object.keys(data.functions || {}).length}</div>
            <div class="stat-label">Functions</div>
        </div>
        <div class="stat">
            <div class="stat-value">${(data.recorded_events || []).length}</div>
            <div class="stat-label">Events</div>
        </div>
        <div class="stat">
            <div class="stat-value">${watchArch ? watchArch.getRecordingDurationFormatted() : 'N/A'}</div>
            <div class="stat-label">Duration</div>
        </div>
    </div>
    <pre>${JSON.stringify(data, null, 2)}</pre>
</body>
</html>`;
    }
};
