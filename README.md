# Roots
Repository for the VSCode extension: Roots

## Description:
Roots is a VSCode extention for visualizing project structures, files, and dependancies. 

As project scope and codebase size increase over time, it becomes increasingly difficult to trace the dependencies between files without manually parsing through each one. Whether you are starting a new project, revisiting an old repository, or onboarding as a new team member to a legacy codebase, you can easily visualize and interact with the architecture using Roots.

## Core Features:
- **Multi-Layer Visualizations:** Toggle seamlessly between a high-level Directory/File overview and a granular Class/Method dependency graph.
- **Dynamic Targeting HUD:** Interactive Breadth-First Search (BFS) tracing that maps cascading downstream impacts and upstream dependencies.
- **Intelligent Physics Engine:** Custom D3.js force-directed clustering with "Orphan Invites" to tether isolated modules into the main directory structures.
- **Deep Introspection Tooltips:** Hover states that reveal exact function arguments, return variables, and nested class methods without opening the file.

## Installation:
#### VSCode
Open Extensions and download...

#### GitHub
Clone repo...F5...open

## Usage:
#### Interact
- ***Hover*** over nodes in the network to see tracebacks, dependencies, and tooltips
- ***Press*** a node to lock its position, tooltip, and tracebacks/dependencies
- ***Double-click*** on a node to drill down to the next network layer - double-click again anywhere on screen to return to parent layer
- ***Edit*** a file and position your cursor within it to highlight the current file or class within the node network

#### Buttons
- ***Theme*** toggles theme of original black or maven blue
- ***Color Map*** toggles on and off a color map of nodes by cluster, with legend
- ***Orphans*** toggles any files or methods not in network connection to be in cluster
- ***Direction*** toggles arrows of tracebacks and dependencies

## System Architecture & AI Collaboration:
This project was developed using a modern, AI-assisted architecture model. Operating as the Lead Systems Architect, I defined the core logic, UI/UX guardrails, and Breadth-First Search dependency tracing requirements. The underlying syntax and boilerplate were generated iteratively via LLM (AI) collaboration. This approach allowed a complex, hybrid Python/D3.js system to be rapidly prototyped and deployed, demonstrating the power of human-led system orchestration combined with AI execution.

## Future Work & Collaboration:
Collaboration is welcome through issues raised or reviews written for bugs found or potential improvements to the tool.

Future work consists of expanding to more programming languages...