const vscode = require('vscode');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let currentPanel = undefined;

function activate(context) {
  let disposable = vscode.commands.registerCommand('pyGraph.visualize', () => {

    if (currentPanel) {
      currentPanel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    // Automatically forces the panel to open in a split view
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

    // Standardized broadcast function for the active file
    const broadcastActiveFile = (editor) => {
      if (editor && editor.document.uri.scheme === 'file' && currentPanel && rootPath) {
        const relPath = path.relative(rootPath, editor.document.fileName);
        currentPanel.webview.postMessage({ command: 'activeFileChanged', filename: relPath });
      }
    };

    const runAnalysis = () => {
      if (!workspaceFolders) return;
      const scriptPath = path.join(context.extensionPath, 'parser.py');
      const pyProcess = spawn('python3', [scriptPath, rootPath]);

      let resultData = '';
      pyProcess.stdout.on('data', (data) => resultData += data.toString());
      pyProcess.stderr.on('data', (data) => console.error('Parser Error:', data.toString()));

      pyProcess.stdout.on('end', () => {
        try {
          if (!resultData.trim()) return;
          const parsed = JSON.parse(resultData);
          if (currentPanel) {
            currentPanel.webview.postMessage({ command: 'updateGraph', payload: parsed });
            // Re-apply cursor highlight immediately after D3 redraws
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

    // Triggers when switching tabs entirely
    vscode.window.onDidChangeActiveTextEditor(editor => {
      broadcastActiveFile(editor);
    }, null, context.subscriptions);

    // Triggers when clicking or moving the cursor inside an already open file
    vscode.window.onDidChangeTextEditorSelection(event => {
      broadcastActiveFile(event.textEditor);
    }, null, context.subscriptions);

    currentPanel.onDidDispose(() => {
      currentPanel = undefined;
      watcher.dispose();
    }, null, context.subscriptions);
  });

  context.subscriptions.push(disposable);
}

function deactivate() {}

module.exports = { activate, deactivate };