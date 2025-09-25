# Docker Deployment Files

This directory contains all the necessary files for dockerizing and deploying the Rubicon Trading Bot.

## Files Overview

### Core Docker Files
- `Dockerfile` - Main Docker image configuration
- `docker-compose.yml` - Local development and testing
- `.dockerignore` - Files to exclude from Docker build
- `portainer-stack.yml` - Production deployment stack for Portainer

### Configuration Files
- `nginx.conf` - Nginx reverse proxy configuration
- `deploy.sh` - Automated deployment script

### Documentation
- `DEPLOYMENT_GUIDE.md` - Complete deployment instructions
- `DOCKER_README.md` - This file

## Quick Start

### Local Development
```bash
# Build and run locally
docker-compose up -d

# View logs
docker-compose logs -f rubicon-trading-bot

# Test application
curl http://localhost:8080/health
```

### Production Deployment
```bash
# Set GitHub credentials for container registry
export GITHUB_TOKEN=your_github_token
export GITHUB_ACTOR=your_github_username

# Make deployment script executable
chmod +x deploy.sh

# Deploy to production
./deploy.sh deploy

# Check status
./deploy.sh status

# View logs
./deploy.sh logs
```

## Key Features

### Log Access
- Logs are mounted to `./logs` directory locally
- Logs are accessible at `/opt/rubicon/logs/` on production server
- Log rotation configured automatically

### Health Monitoring
- Health check endpoint: `/health`
- WebSocket status: `/websocket/status`
- Scheduler status: `/scheduler/status`
- Docker health checks configured

### Security
- Non-root user in container
- Environment variables for sensitive data
- Nginx reverse proxy with rate limiting
- Security headers configured

### CI/CD
- GitHub Actions workflow for automated builds
- Multi-architecture support (AMD64, ARM64)
- Automatic GitHub Container Registry publishing
- Automated testing and linting

## Port Configuration

- **8080**: Main application (FastAPI)
- **80/443**: Nginx reverse proxy (optional)

## Environment Variables

Copy `example.env` to `.env` and configure:
- API keys (Binance, KuCoin)
- Database credentials (Supabase)
- Trading parameters
- Notification settings

## Troubleshooting

### Common Issues
1. **Container won't start**: Check environment file and logs
2. **Health check fails**: Verify application is responding on port 8080
3. **Logs not accessible**: Check volume mounts and permissions
4. **Memory issues**: Adjust resource limits in stack configuration

### Useful Commands
```bash
# Check container status
docker ps

# View container logs
docker logs rubicon-trading-bot

# Restart container
docker restart rubicon-trading-bot

# Check resource usage
docker stats rubicon-trading-bot

# Access container shell
docker exec -it rubicon-trading-bot /bin/bash
```

## Support

For deployment issues:
1. Check the comprehensive `DEPLOYMENT_GUIDE.md`
2. Review container logs
3. Verify environment configuration
4. Check GitHub Actions workflow status
