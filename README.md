# Roots
Repository for the VS Code extension: Roots

## Description
Roots is a VS Code extension for visualizing project structures, files, and dependencies. 

As project scope and codebase size increase over time, it becomes increasingly difficult to trace the dependencies between files without manually parsing through each one. Whether you are starting a new project, revisiting an old repository, or onboarding as a new team member to a legacy codebase, you can easily visualize and interact with the architecture using Roots.

## Core Features
- **Multi-Layer Visualizations:** Toggle seamlessly between a high-level Directory/File overview and a granular Class/Method dependency graph.
- **Dynamic Targeting HUD:** Interactive Breadth-First Search (BFS) tracing that maps cascading downstream impacts and upstream dependencies.
- **Intelligent Physics Engine:** Custom D3.js force-directed clustering with "Orphan Invites" to tether isolated modules into the main directory structures.
- **Deep Introspection Tooltips:** Hover states that reveal exact function arguments, return variables, and nested class methods without opening the file.

## Installation

### VS Code
In VS Code, open the **Extensions** view (`Cmd+Shift+X` on macOS, `Ctrl+Shift+X` on Windows), search for "Roots: Architecture Visualizer", and install. Open any Python project folder and press `Cmd+Shift+P` (`Ctrl+Shift+P` on Windows) to launch the command palette, type "Roots: Architecture Visualizer" and hit enter.

## Usage

### Interact
- **Hover** over nodes in the network to see tracebacks, dependencies, and tooltips.
- **Press** a node to lock its position, tooltip, and tracebacks/dependencies.
- **Double-click** on a node to drill down to the next network layer—double-click again anywhere on screen to return to the parent layer.
- **Edit** a file and position your cursor within it to highlight the current file or class within the node network.

### Buttons
- **Theme:** Toggles theme of original black or Maven blue.
- **Color Map:** Toggles on and off a color map of nodes by cluster, with a legend.
- **Orphans:** Toggles any files or methods not in network connection to be in a cluster.
- **Direction:** Toggles arrows of tracebacks and dependencies.

### Config
Roots allows you to customize directory filtering and file ingestion directly through VS Code Settings.

**Option 1: Via the Settings UI**
1. Open Settings (`Cmd+,` on macOS or `Ctrl+,` on Windows/Linux).
2. Search for **"Roots: Architecture Visualizer"**.
3. Add or remove items from the respective filter lists:
   * **Ignored Directories:** Folders skipped during workspace scanning (e.g., `venv`, `__pycache__`, `.git`).
   * **Allowed Extensions:** File types parsed into the graph (defaults to `.py`, `.json`, `.env`).
   * **Allowed Hidden Files:** Dotfiles explicitly allowed past the hidden-file filter (defaults to `.env`).

**Option 2: Via `.vscode/settings.json`**
To commit project-specific visualization rules to your repository, add the following to your workspace's `.vscode/settings.json`:

```json
{
  "roots.ignoredDirectories": [
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules",
    "build",
    "dist"
  ],
  "roots.allowedExtensions": [
    ".py",
    ".json",
    ".env"
  ],
  "roots.allowedHiddenFiles": [
    ".env"
  ]
}
```

## System Architecture & AI Collaboration:
This project was developed using a modern, AI-assisted architecture model. Operating as the Lead Systems Architect, I defined the core logic, UI/UX guardrails, and Breadth-First Search dependency tracing requirements. The underlying syntax and boilerplate were generated iteratively via LLM (AI) collaboration. This approach allowed a complex, hybrid Python/D3.js system to be rapidly prototyped and deployed, demonstrating the power of human-led system orchestration combined with AI execution.

## Future Work & Collaboration:
Collaboration is welcome through issues raised or reviews written for bugs found or potential improvements to the tool.
