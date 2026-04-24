# EMFILE Error Fix

## Problem
Application failed to start with "EMFILE: too many open files" error due to excessive file descriptors being consumed by the system.

## Root Cause
System had over 1 million open file descriptors, causing new file operations to fail.

## Solution Applied

### 1. Updated vite.config.ts
Configured file watching to explicitly ignore data directory:
```typescript
server: {
  watch: {
    ignored: ['**/data/**', '**/node_modules/**', '**/.git/**'],
    usePolling: false,
  },
}
```

### 2. Updated start.sh
Added file descriptor limit increase and process cleanup:
```bash
ulimit -n 65536
pkill -f "vite|offline_server|ssh_bridge|pcl_proxy"
```

### 3. Added data/ to .gitignore
Ensures data directory is properly excluded from version control and file watching.

## Verification
- Server starts successfully on port 5173
- Backend API responds correctly on port 8769
- All services running: Vite, offline_server.py, pcl_proxy.mjs
- No EMFILE errors in console

## Usage
Run `bash start.sh` to start the development server with proper configuration.
