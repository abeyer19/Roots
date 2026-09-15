const vscode = require('vscode');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let currentPanel = undefined;
let cachedGraphData = null; // NEW: Global cache for cross-window persistence

function activate(context) {
  let disposable = vscode.commands.registerCommand('pyGraph.visualize', () => {
    if (currentPanel) {
      currentPanel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    currentPanel = vscode.window.createWebviewPanel(
      'pyDependencyGraph',
      'Architecture Visualizer',
      vscode.ViewColumn.Beside, 
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'media'))]
      }
    );

    const htmlPath = path.join(context.extensionPath, 'media', 'visualizer.html');
    currentPanel.webview.html = fs.readFileSync(htmlPath, 'utf8');

    const workspaceFolders = vscode.workspace.workspaceFolders;
    const rootPath = workspaceFolders ? workspaceFolders[0].uri.fsPath : '';

    const broadcastActiveFile = (editor) => {
      if (editor && editor.document.uri.scheme === 'file' && currentPanel && rootPath) {
        const relPath = path.relative(rootPath, editor.document.fileName);
        const activeLine = editor.selection.active.line + 1; 
        currentPanel.webview.postMessage({ 
            command: 'activeFileChanged', 
            filename: relPath, 
            line: activeLine 
        });
      }
    };

    // NEW: Listen for window drags, tab switches, and panel visibility changes
    currentPanel.onDidChangeViewState(
      e => {
        // Instantly re-inject the cached data when the panel respawns in a new window
        if (e.webviewPanel.visible && cachedGraphData) {
          currentPanel.webview.postMessage({ command: 'updateGraph', payload: cachedGraphData });
          broadcastActiveFile(vscode.window.activeTextEditor);
        }
      },
      null,
      context.subscriptions
    );

    const runAnalysis = () => {
      if (!workspaceFolders) return;
      
      // Extract configuration directly from VS Code user settings
      const config = vscode.workspace.getConfiguration('roots');
      const ignoredDirs = config.get('ignoredDirectories').join(',');
      const allowedExts = config.get('allowedExtensions').join(',');
      const allowedHidden = config.get('allowedHiddenFiles').join(',');

      const scriptPath = path.join(context.extensionPath, 'parser.py');
      // Pass the configurations as string arguments to Python
      const pyProcess = spawn('python3', [scriptPath, rootPath, ignoredDirs, allowedExts, allowedHidden]);

      let resultData = '';
      pyProcess.stdout.on('data', (data) => resultData += data.toString());
      pyProcess.stderr.on('data', (data) => console.error('Parser Error:', data.toString()));

      pyProcess.stdout.on('end', () => {
        try {
          if (!resultData.trim()) return;
          const parsed = JSON.parse(resultData);
          
          cachedGraphData = parsed;
          
          if (currentPanel) {
            currentPanel.webview.postMessage({ command: 'updateGraph', payload: cachedGraphData });
            broadcastActiveFile(vscode.window.activeTextEditor);
          }
        } catch (err) {
          console.error('Failed to parse graph payload:', err);
        }
      });
    };

    runAnalysis();

    const watcher = vscode.workspace.createFileSystemWatcher('**/*.py');
    watcher.onDidChange(runAnalysis);
    watcher.onDidCreate(runAnalysis);
    watcher.onDidDelete(runAnalysis);

    vscode.window.onDidChangeActiveTextEditor(editor => broadcastActiveFile(editor), null, context.subscriptions);
    vscode.window.onDidChangeTextEditorSelection(event => broadcastActiveFile(event.textEditor), null, context.subscriptions);

    currentPanel.onDidDispose(() => {
      currentPanel = undefined;
      watcher.dispose();
    }, null, context.subscriptions);
  });

  context.subscriptions.push(disposable);
}

function deactivate() {}
module.exports = { activate, deactivate };