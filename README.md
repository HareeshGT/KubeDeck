# KubeDeck

<p align="center">
  <strong>A powerful desktop control center for AWS EC2, Kubernetes, SSH, SFTP, FTP, and cloud operations.</strong>
</p>

<p align="center">
  Manage your infrastructure from a single desktop application instead of jumping between terminals, SSH clients, file managers, and Kubernetes tools.
</p>

<p align="center">
  <a href="https://github.com/HareeshGT/KubeDeck">
    <img src="https://img.shields.io/github/stars/HareeshGT/KubeDeck?style=for-the-badge" alt="GitHub Stars">
  </a>
  <a href="https://github.com/HareeshGT/KubeDeck">
    <img src="https://img.shields.io/github/forks/HareeshGT/KubeDeck?style=for-the-badge" alt="GitHub Forks">
  </a>
  <a href="https://github.com/HareeshGT/KubeDeck">
    <img src="https://img.shields.io/github/last-commit/HareeshGT/KubeDeck?style=for-the-badge" alt="Last Commit">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-purple?style=for-the-badge" alt="MIT License">
  </a>
</p>

---

## Overview

**KubeDeck** is a desktop infrastructure management application designed to bring common cloud and DevOps workflows into a single interface.

Instead of using separate applications for:

- AWS EC2 management
- SSH
- SFTP
- FTP
- Remote file management
- Kubernetes
- Terminal sessions
- Port forwarding
- Logs
- Cluster dashboards
- Infrastructure troubleshooting

KubeDeck provides a unified desktop experience.

It is particularly useful for developers, DevOps engineers, SREs, platform engineers, and anyone who regularly works with remote Linux systems and Kubernetes clusters.

---

# ✨ Features

## ☁️ AWS EC2 Management

Connect to and work with remote EC2 instances from a desktop interface.

Features include:

- EC2 instance connections
- SSH connectivity
- SFTP file management
- Recent instance tracking
- Remote filesystem browsing
- Remote command execution
- Integrated terminal
- File upload/download
- Remote file editing
- Search
- Media/file handling
- Sudo filesystem access

KubeDeck is designed to make an EC2 instance feel more like a local workstation.

---

## 🖥️ Integrated SSH Terminal

KubeDeck includes an integrated terminal for remote systems.

Instead of opening a separate terminal application for every server, you can work directly inside KubeDeck.

Use it for:

```bash
kubectl get pods
systemctl status nginx
journalctl -u my-service
df -h
top
```

and other normal Linux workflows.

---

## 📁 Remote File Manager

KubeDeck provides a Finder-style remote filesystem interface.

You can:

- Browse directories
- Create files
- Create directories
- Rename files
- Delete files
- Upload files
- Download files
- Search files
- Edit files
- Execute files
- Open remote media
- Work with privileged directories

The interface is designed to reduce the need for repeated commands such as:

```text
scp
sftp
ssh
cp
mv
rm
vim
nano
```

---

## 🔐 Sudo Filesystem Access

Many production systems restrict important directories to `root`.

KubeDeck supports switching into a privileged filesystem context when required.

This makes it possible to work with protected paths without manually performing repetitive privilege escalation operations.

---

# ☸️ Kubernetes Management

KubeDeck includes a dedicated Kubernetes management interface.

It works with clusters accessible through your local Kubernetes configuration and provides a graphical interface for common Kubernetes operations.

### Supported resources

The Kubernetes interface includes views for resources such as:

- Pods
- Deployments
- StatefulSets
- DaemonSets
- Services
- Ingress
- Jobs
- CronJobs
- Horizontal Pod Autoscalers
- Persistent Volumes
- Persistent Volume Claims
- ConfigMaps
- Secrets
- Events
- Storage resources

---

## 📊 Kubernetes Dashboard

The dashboard provides a high-level view of cluster activity.

You can inspect:

- Cluster resources
- Workloads
- Pods
- Services
- Storage
- Resource usage
- Kubernetes objects
- Events
- Workload health

The goal is to provide useful operational information without requiring every action to begin with:

```bash
kubectl get ...
```

---

## 📦 Pod Management

KubeDeck provides operational tools for Kubernetes pods.

You can inspect:

- Pod status
- Pod details
- Container information
- Pod logs
- Events
- Container execution

You can also open an interactive terminal inside containers where supported.

---

## 📜 Kubernetes Logs

Inspect pod and container logs directly from the application.

This is useful for quickly investigating:

- Application failures
- CrashLoopBackOff
- Startup errors
- API failures
- Configuration problems
- Container errors

---

## 🖥️ Kubernetes Exec

Open an interactive shell inside a running container.

Typical workflows such as:

```bash
kubectl exec -it <pod> -- /bin/bash
```

or:

```bash
kubectl exec -it <pod> -- /bin/sh
```

can be performed from the application.

---

## 🔀 Port Forwarding & Tunnels

KubeDeck provides support for Kubernetes port-forwarding and remote tunnels.

This is useful for accessing internal services such as:

- Grafana
- Prometheus
- Kibana
- Internal APIs
- Databases
- Development services
- Kubernetes dashboards

without exposing those services publicly.


---

# 📡 FTP

KubeDeck also includes FTP functionality for working with FTP-connected systems.

The FTP interface provides a graphical file-management experience for connected devices and remote filesystems.

---

# 🧠 AI / Ops Assistant

KubeDeck includes AI-assisted operational functionality.

The goal is to make infrastructure troubleshooting more accessible by combining infrastructure context with an AI assistant.

Depending on the configured provider, AI functionality can be used to help with:

- Troubleshooting
- Understanding errors
- Explaining infrastructure output
- Kubernetes investigation
- Log analysis
- Command assistance
- Operational questions

The AI functionality is designed as an assistant rather than a replacement for normal infrastructure controls.

---

# 🔒 Security

Security is an important part of KubeDeck.

## Application Lock

KubeDeck supports application locking using a PIN.

The application can automatically lock after inactivity.

---

## PIN Security

The application lock uses password-derived cryptographic storage rather than storing the PIN as plain text.

PBKDF2-SHA256 is used for PIN-related security.

---

## SSH Credentials

KubeDeck is designed to work with SSH credentials without requiring credentials to be embedded directly into application source code.

Users should still follow normal credential-management practices and avoid committing private keys, passwords, tokens, or other secrets to Git repositories.

---

# 🎨 Themes

KubeDeck supports a customizable desktop interface with persistent theme settings.

The application includes a dark, infrastructure-oriented visual design and supports configurable themes.

Settings are persisted so that the application can retain user preferences between sessions.

---

# 🧩 Architecture

KubeDeck is a Python desktop application built around a modular UI architecture.

The application separates major infrastructure functions into dedicated components.

Some of the major areas include:

```text
KubeDeck/
│
├── main.py
├── main_window.py
│
├── dashboard_tab.py
├── kubernetes_tab.py
├── k8s_cards.py
│
├── terminal_widget.py
├── editor_widgets.py
│
├── dialogs.py
├── workers.py
│
├── settings_dialog.py
├── themes.py
│
├── security.py
├── lock_screen.py
├── sudo_fs.py
│
├── ftp_fs.py
├── ai_assist.py
│
└── ...
```

The project is being actively modularized so that individual infrastructure features can evolve independently instead of placing all application functionality into a single monolithic file.

---

# 🛠️ Technology Stack

KubeDeck is primarily built with:

- Python
- Qt / PyQt
- SSH/SFTP tooling
- Kubernetes tooling
- AWS infrastructure
- FTP
- AI APIs
- Shell commands
- JSON-based application settings

The application integrates with existing infrastructure tools rather than attempting to replace the underlying platforms.

For example:

```text
KubeDeck
   │
   ├── AWS / EC2
   │
   ├── SSH / SFTP
   │
   ├── FTP
   │
   ├── kubectl
   │
   ├── Kubernetes
   │
   └── AI providers
```

---

# 💻 Requirements

KubeDeck is primarily developed and tested on macOS.

Depending on the features being used, you may need:

- Python 3
- SSH client
- `kubectl`
- Kubernetes credentials / kubeconfig
- AWS credentials where required
- Appropriate SSH keys
- Network access to the target systems

For Kubernetes functionality, a working Kubernetes configuration is expected.

Verify your Kubernetes configuration with:

```bash
kubectl config get-contexts
```

and:

```bash
kubectl cluster-info
```

---

# 🚀 Installation

## 1. Clone the repository

```bash
git clone https://github.com/HareeshGT/KubeDeck.git
cd KubeDeck
```

---

## 2. Create a virtual environment

```bash
python3 -m venv .venv
```

Activate it:

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows

```powershell
.venv\Scripts\activate
```

---

## 3. Install dependencies

If the repository contains a `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

# ▶️ Running KubeDeck

From the project directory:

```bash
python3 main.py
```

If your environment uses a specific Python executable:

```bash
/usr/bin/python3 main.py
```

or:

```bash
python main.py
```

depending on your environment.

---

# ☸️ Kubernetes Setup

KubeDeck uses your Kubernetes configuration for cluster access.

Check your available contexts:

```bash
kubectl config get-contexts
```

Select the required context:

```bash
kubectl config use-context <context-name>
```

Verify access:

```bash
kubectl get nodes
```

Once `kubectl` can communicate with the cluster, KubeDeck can use the same Kubernetes environment.

---

# ☁️ AWS Setup

For EC2 workflows, configure AWS credentials using the standard AWS credential mechanisms supported by your environment.

For example:

```bash
aws configure
```

Verify:

```bash
aws sts get-caller-identity
```

KubeDeck can then work with EC2 infrastructure using the credentials available to the environment.

---

# 🔑 SSH Setup

For SSH-based EC2 connections, ensure that the required SSH credentials are available.

Example:

```bash
chmod 600 ~/.ssh/my-key.pem
```

You should be able to connect to the target instance normally:

```bash
ssh -i ~/.ssh/my-key.pem ubuntu@<EC2-IP>
```

Once SSH access works, the same connection information can be configured in KubeDeck.

---

# ⚙️ Application Settings

KubeDeck stores application preferences locally.

Settings can include:

- Theme
- UI preferences
- Recent connections
- Application behavior
- Download locations
- Other persistent configuration

Downloads default to the user's:

```text
~/Downloads
```

---

# 🗂️ Typical Workflows

## Manage an EC2 server

```text
Launch KubeDeck
      ↓
Connect to EC2
      ↓
SSH / SFTP
      ↓
Browse filesystem
      ↓
Open terminal
      ↓
Inspect logs
      ↓
Edit / transfer files
```

---

## Troubleshoot Kubernetes

```text
Open Kubernetes
      ↓
Select cluster
      ↓
Inspect namespace
      ↓
Check pods
      ↓
Open pod logs
      ↓
Inspect events
      ↓
Exec into container
      ↓
Investigate / fix
```

---

## Access an internal service

```text
Kubernetes
    ↓
Select service
    ↓
Create port-forward
    ↓
localhost:<port>
    ↓
Open service locally
```

---

# 🔄 Remote File Workflow

A typical remote-file workflow looks like:

```text
EC2
 │
 ├── Connect
 │
 ├── Browse
 │
 ├── Search
 │
 ├── Edit
 │
 ├── Upload
 │
 ├── Download
 │
 └── Execute
```

This allows common server administration tasks to be performed without repeatedly switching applications.

---

# 🧪 Development

Clone the project:

```bash
git clone https://github.com/HareeshGT/KubeDeck.git
cd KubeDeck
```

Create a development environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python3 main.py
```

---

# 📦 Building a macOS Application

KubeDeck can be packaged as a standalone macOS application using Python application-packaging tooling.

A typical packaging workflow is:

```text
Python source
     ↓
Dependency collection
     ↓
Application packaging
     ↓
macOS application
     ↓
DMG distribution
```

The exact build command should follow the packaging configuration currently included in the repository.

---

# 🐛 Troubleshooting

## Kubernetes is not showing

Verify:

```bash
kubectl config get-contexts
```

Then:

```bash
kubectl cluster-info
```

Finally:

```bash
kubectl get nodes
```

If these commands fail outside KubeDeck, fix the Kubernetes configuration first.

---

## SSH connection fails

Test the connection outside KubeDeck:

```bash
ssh -i <key> <user>@<host>
```

Check:

- Host/IP
- Username
- SSH key
- File permissions
- Security groups
- Network connectivity
- SSH server availability

---

## Permission denied on SSH key

Use:

```bash
chmod 600 <private-key>
```

---

## Port forwarding does not work

Check:

```bash
kubectl get pods
kubectl get svc
```

Then verify that the target service and port actually exist.

---

# 🔐 Security Recommendations

Never commit secrets to this repository.

Do not commit:

```text
*.pem
*.key
.env
.env.*
credentials
tokens
passwords
API keys
private keys
```

Use environment variables, OS credential stores, SSH agents, or other secure credential-management mechanisms where appropriate.

Before publishing changes, check:

```bash
git status
```

and:

```bash
git diff
```

---

# 🗺️ Roadmap

Potential future improvements include:

- Improved multi-cluster management
- More Kubernetes resource actions
- Better remote filesystem operations
- Additional cloud-provider integrations
- Enhanced AI-assisted troubleshooting
- Improved log analysis
- Better connection management
- More automation workflows
- Performance improvements
- Additional platform support
- More extensive testing

The project is actively evolving, and the roadmap may change as new infrastructure-management requirements are added.

---

# 🤝 Contributing

Contributions are welcome.

## Development workflow

Fork the repository:

https://github.com/HareeshGT/KubeDeck

Create a branch:

```bash
git checkout -b feature/my-feature
```

Make your changes.

Test the application.

Review the changes:

```bash
git diff
```

Commit:

```bash
git add .
git commit -m "Add my feature"
```

Push:

```bash
git push origin feature/my-feature
```

Then open a Pull Request.

---

# 🐞 Bug Reports

When reporting a bug, include:

- Operating system
- Python version
- KubeDeck version/commit
- Relevant logs
- Steps to reproduce
- Expected behavior
- Actual behavior
- Kubernetes version, if applicable

Avoid posting credentials, tokens, private keys, passwords, or other sensitive information.

---

# 📸 Screenshots

Screenshots and demonstrations can be added here as the project UI evolves.

Suggested sections:

- Main dashboard
- EC2 manager
- Remote file manager
- SSH terminal
- Kubernetes dashboard
- Kubernetes resource view
- FTP manager
- AI/Ops assistant
- Settings and themes

---

# 📜 License

KubeDeck is licensed under the MIT License.

Copyright (c) 2026 Hareesh GT

See [`LICENSE`](LICENSE) for the complete license text.

---

# 👤 Author

**Hareesh GT**

GitHub:

https://github.com/HareeshGT

Project:

https://github.com/HareeshGT/KubeDeck

---

# ⭐ Support the Project

If KubeDeck is useful to you:

- ⭐ Star the repository
- 🐛 Report bugs
- 💡 Suggest improvements
- 🔧 Contribute code
- 📖 Improve documentation
- 🔀 Submit pull requests

---

<p align="center">

**KubeDeck**

A unified desktop workspace for cloud and Kubernetes operations.

Built for developers, DevOps engineers, SREs, and infrastructure teams.

</p>
