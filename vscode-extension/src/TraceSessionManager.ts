import * as fs from 'fs';
import * as path from 'path';
import * as zlib from 'zlib';
import * as vscode from 'vscode';

export interface SessionInfo {
    name: string;
    timestamp: string;
    file: string;
    sizeMB: number;
}

/**
 * Manages saving and restoring TrueFlow runtime trace sessions.
 * Sessions are stored as gzipped JSON in <project>/.trueflow/sessions/
 * Compatible with the PyCharm plugin's .trueflow format.
 */
export class TraceSessionManager {
    private sessionsDir: string;

    constructor() {
        const folders = vscode.workspace.workspaceFolders;
        const workspaceRoot = folders ? folders[0].uri.fsPath : '';
        this.sessionsDir = path.join(workspaceRoot, '.trueflow', 'sessions');

        if (!fs.existsSync(this.sessionsDir)) {
            fs.mkdirSync(this.sessionsDir, { recursive: true });
        }
    }

    /**
     * Save a trace session as gzipped JSON.
     */
    saveSession(name: string, state: any): string {
        const now = new Date();
        const timestamp = now.toISOString()
            .replace(/[-:]/g, '')
            .replace('T', '_')
            .substring(0, 15);
        const sanitizedName = name.replace(/[^a-zA-Z0-9_\-]/g, '_');
        const fileName = `${sanitizedName}_${timestamp}.trueflow`;
        const filePath = path.join(this.sessionsDir, fileName);

        // Add metadata
        state._session_name = name;
        state._session_timestamp = timestamp;
        state._project_path = vscode.workspace.workspaceFolders?.[0].uri.fsPath || '';
        state._plugin_version = 'vscode';

        // Write gzipped JSON (same format as PyCharm)
        const jsonData = JSON.stringify(state);
        const compressed = zlib.gzipSync(Buffer.from(jsonData, 'utf-8'));
        fs.writeFileSync(filePath, compressed);

        console.log(`[TraceSessionManager] Saved '${name}' to ${fileName} (${Math.round(compressed.length / 1024)}KB)`);
        return filePath;
    }

    /**
     * Restore a session from a gzipped JSON file.
     */
    restoreSession(filePath: string): any {
        const compressed = fs.readFileSync(filePath);
        const jsonData = zlib.gunzipSync(compressed).toString('utf-8');
        const state = JSON.parse(jsonData);

        console.log(`[TraceSessionManager] Restored from ${path.basename(filePath)}`);
        return state;
    }

    /**
     * List all saved sessions, newest first.
     */
    listSessions(): SessionInfo[] {
        if (!fs.existsSync(this.sessionsDir)) { return []; }

        return fs.readdirSync(this.sessionsDir)
            .filter(f => f.endsWith('.trueflow'))
            .map(fileName => {
                const filePath = path.join(this.sessionsDir, fileName);
                const stats = fs.statSync(filePath);
                const name = fileName
                    .replace(/\.trueflow$/, '')
                    .replace(/_\d{8}_\d{6}$/, '')
                    .replace(/_/g, ' ');

                return {
                    name,
                    timestamp: new Date(stats.mtimeMs).toISOString().replace('T', ' ').substring(0, 19),
                    file: filePath,
                    sizeMB: stats.size / (1024 * 1024)
                };
            })
            .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    }

    /**
     * Delete a saved session file.
     */
    deleteSession(filePath: string): boolean {
        try {
            fs.unlinkSync(filePath);
            console.log(`[TraceSessionManager] Deleted: ${path.basename(filePath)}`);
            return true;
        } catch {
            return false;
        }
    }
}
