# Rubicon Trading Bot - Complete Deployment Guide

This guide provides step-by-step instructions for dockerizing, setting up GitHub Actions, and deploying the Rubicon Trading Bot to production using Portainer.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Docker Configuration](#docker-configuration)
4. [GitHub Actions Setup](#github-actions-setup)
5. [Server Preparation](#server-preparation)
6. [Portainer Installation](#portainer-installation)
7. [Production Deployment](#production-deployment)
8. [Log Access Setup](#log-access-setup)
9. [Monitoring & Maintenance](#monitoring--maintenance)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

- Docker and Docker Compose installed locally
- GitHub repository with the trading bot code
- Linux server (Ubuntu 20.04+ recommended) with Docker installed
- Domain name (optional, for SSL)
- Basic knowledge of Docker, Git, and Linux

## Local Development Setup

### 1. Environment Configuration

Create a `.env` file in the project root:

```bash
cp example.env .env
```

Edit the `.env` file with your actual configuration values:

```env
# Binance Configuration
BINANCE_API_KEY=your_actual_binance_api_key
BINANCE_API_SECRET=your_actual_binance_api_secret
BINANCE_TESTNET=True

# KuCoin Configuration
KUCOIN_API_KEY=your_actual_kucoin_api_key
KUCOIN_API_SECRET=your_actual_kucoin_api_secret
KUCOIN_API_PASSPHRASE=your_actual_kucoin_passphrase
KUCOIN_TESTNET=True

# Supabase Configuration
SUPABASE_URL=your_actual_supabase_url
SUPABASE_KEY=your_actual_supabase_key

# OpenAI Configuration
OPENAI_API_KEY=your_actual_openai_api_key

# Trading Parameters
RISK_PERCENTAGE=2.0
TRADE_AMOUNT=101.0
TRADE_AMOUNT_PERCENTAGE=0
MIN_TRADE_AMOUNT=10.0
MAX_TRADE_AMOUNT=1000.0
PRICE_THRESHOLD=25.0
MEMECOIN_PRICE_THRESHOLD=100.0
LOW_LIQUIDITY_PRICE_THRESHOLD=50.0
SLIPPAGE_PERCENTAGE=1.0
TRADE_COOLDOWN=300
LIMIT_ORDER_PRICE_THRESHOLD=10.0

# Take Profit Configuration
DEFAULT_TP_PERCENTAGE=5.0
SIGNAL_TP_POSITION_PERCENTAGE=50.0
TP_AUDIT_INTERVAL=30

# Telegram Bot Configuration (for notifications)
TELEGRAM_BOT_TOKEN=your_actual_telegram_bot_token
TELEGRAM_NOTIFICATION_CHAT_ID=your_actual_notification_chat_id

# Minimum ETH balance to maintain for gas fees
MIN_ETH_BALANCE=0.01

# Trading Leverage Configuration
LEVERAGE=1
```

### 2. Build and Test Locally

```bash
# Build the Docker image
docker build -t rubicon-trading-bot .

# Run with docker-compose
docker-compose up -d

# Check logs
docker-compose logs -f rubicon-trading-bot

# Test the application
curl http://localhost:8080/health
curl http://localhost:8080/
```

### 3. Access Logs Locally

The logs are mounted to the `./logs` directory on your host machine. You can access them directly:

```bash
# View real-time logs
tail -f logs/trading_bot_$(date +%Y%m%d).log

# View specific log types
tail -f logs/endpoints_$(date +%Y%m%d).log
tail -f logs/trade_processing_$(date +%Y%m%d).log
tail -f logs/errors_$(date +%Y%m%d).log
```

## Docker Configuration

### Key Features

- **Multi-stage build** for optimized image size
- **Non-root user** for security
- **Health checks** for container monitoring
- **Volume mounting** for log persistence
- **Environment variable** support

### Dockerfile Highlights

```dockerfile
# Uses Python 3.11 slim for smaller size
FROM python:3.11-slim

# Security: Non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=10)" || exit 1

# Runs on port 8080 as requested
EXPOSE 8080
```

## GitHub Actions Setup

### 1. Repository Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- `SERVER_HOST` - Your server's IP address or hostname
- `SERVER_PORT` - SSH port (usually 22)
- `SERVER_USER` - Username for SSH connection
- `SERVER_SSH` - Your private SSH key content

### 2. Workflow Features

The CI/CD pipeline includes:

- **Testing**: Linting, formatting, and unit tests
- **Security**: Code quality checks
- **Multi-architecture builds**: AMD64 and ARM64 support
- **Container registry**: Automatic push to GitHub Container Registry
- **Deployment**: SSH deployment to production server

### 3. Manual Deployment Trigger

To manually trigger deployment:

```bash
# Push to main branch
git push origin main

# Or create a release
git tag v1.0.0
git push origin v1.0.0
```

## Server Preparation

### 1. Server Requirements

- **OS**: Ubuntu 20.04+ or similar Linux distribution
- **RAM**: Minimum 2GB, recommended 4GB+
- **Storage**: Minimum 20GB free space
- **Network**: Open ports 22 (SSH), 8080 (application)

### 2. Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Logout and login again to apply group changes
```

### 3. Create Application Directory

```bash
# Create application directory
sudo mkdir -p /opt/rubicon
sudo chown $USER:$USER /opt/rubicon

# Create subdirectories
mkdir -p /opt/rubicon/logs
```

## Manual Deployment (Alternative to GitHub Actions)

If you prefer manual deployment instead of GitHub Actions:

## Production Deployment

### 1. Prepare Environment File

Create `/opt/rubicon/.env` on your server:

```bash
sudo nano /opt/rubicon/.env
```

Add your production environment variables (same format as local `.env` but with production values).

### 2. Deploy Using Deploy Script

```bash
# Set GitHub credentials for container registry
export GITHUB_TOKEN=your_github_token
export GITHUB_ACTOR=your_github_username

# Clone your repository
cd /opt/rubicon
git clone https://github.com/ngigin/rubicon-trading-bot.git .

# Make deploy script executable
chmod +x deploy.sh

# Deploy the application
./deploy.sh deploy
```

### 4. Verify Deployment

```bash
# Check container status
docker ps

# Check logs
docker logs rubicon-trading-bot

# Test health endpoint
curl http://localhost:8080/health
```

## Log Access Setup

### 1. Direct File Access

Logs are mounted to `/opt/rubicon/logs/` on your server:

```bash
# View real-time logs
tail -f /opt/rubicon/logs/trading_bot_$(date +%Y%m%d).log

# View all log files
ls -la /opt/rubicon/logs/

# Search logs
grep "ERROR" /opt/rubicon/logs/errors_$(date +%Y%m%d).log
```

### 2. Remote Log Access

For remote log access without SSH, you can set up a simple log server:

```bash
# Install a simple log server (optional)
docker run -d --name log-server \
    -p 8081:80 \
    -v /opt/rubicon/logs:/usr/share/nginx/html/logs:ro \
    nginx:alpine
```

Access logs at `http://your-server-ip:8081/logs/`

### 3. Log Rotation Setup

Create a log rotation configuration:

```bash
sudo nano /etc/logrotate.d/rubicon
```

Add:

```
/opt/rubicon/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        docker restart rubicon-trading-bot
    endscript
}
```


## Monitoring & Maintenance

### 1. Health Monitoring

The application includes health checks accessible at:
- `http://your-server-ip:8080/health`
- `http://your-server-ip:8080/websocket/status`
- `http://your-server-ip:8080/scheduler/status`

### 2. Container Monitoring

```bash
# Monitor resource usage
docker stats rubicon-trading-bot

# View container logs
docker logs -f rubicon-trading-bot

# Restart container
docker restart rubicon-trading-bot
```

### 3. Automated Updates

Set up automated updates using a cron job:

```bash
# Create update script
sudo nano /opt/rubicon/update.sh
```

Add:

```bash
#!/bin/bash
export GITHUB_TOKEN=your_github_token
export GITHUB_ACTOR=your_github_username
cd /opt/rubicon
./deploy.sh update
docker system prune -f
```

```bash
# Make executable
sudo chmod +x /opt/rubicon/update.sh

# Add to crontab (daily at 2 AM)
sudo crontab -e
```

Add:

```
0 2 * * * /opt/rubicon/update.sh >> /var/log/rubicon-update.log 2>&1
```

### 4. Backup Strategy

```bash
# Create backup script
sudo nano /opt/rubicon/backup.sh
```

Add:

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/rubicon"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup logs
tar -czf $BACKUP_DIR/logs_$DATE.tar.gz /opt/rubicon/logs/

# Backup environment
cp /opt/rubicon/.env $BACKUP_DIR/env_$DATE

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
find $BACKUP_DIR -name "env_*" -mtime +30 -delete
```

## Troubleshooting

### Common Issues

#### 1. Container Won't Start

```bash
# Check logs
docker logs rubicon-trading-bot

# Check environment file
cat /opt/rubicon/.env

# Verify image exists
docker images | grep rubicon
```

#### 2. Health Check Failing

```bash
# Test health endpoint manually
curl -v http://localhost:8080/health

# Check if application is running
docker exec rubicon-trading-bot ps aux
```

#### 3. Log Files Not Accessible

```bash
# Check volume mounts
docker inspect rubicon-trading-bot | grep -A 10 "Mounts"

# Check permissions
ls -la /opt/rubicon/logs/
```

#### 4. Memory Issues

```bash
# Check memory usage
docker stats rubicon-trading-bot

# Increase memory limits in portainer-stack.yml
```

### Performance Optimization

#### 1. Resource Limits

Adjust resource limits in `portainer-stack.yml`:

```yaml
deploy:
  resources:
    limits:
      memory: 4G      # Increase if needed
      cpus: '2.0'     # Increase if needed
```

#### 2. Log Level Optimization

Modify logging configuration in `config/logging_config.py` to reduce log verbosity in production.

#### 3. Database Connection Pooling

Ensure your Supabase connection is properly configured for production load.

## Security Considerations

### 1. Environment Variables

- Never commit `.env` files to version control
- Use strong, unique API keys
- Rotate API keys regularly
- Use testnet for development

### 2. Network Security

- Use firewall rules to restrict access
- Consider using a VPN for server access
- Enable SSL/TLS for production

### 3. Container Security

- Run containers as non-root user (already configured)
- Keep base images updated
- Scan images for vulnerabilities

## Support

For issues or questions:

1. Check the logs first: `/opt/rubicon/logs/`
2. Review this deployment guide
3. Check GitHub Issues for known problems
4. Contact the development team

## Conclusion

This deployment setup provides:

- ✅ **Dockerized application** with proper security
- ✅ **Automated CI/CD** with GitHub Actions
- ✅ **Easy log access** without SSH
- ✅ **Production-ready** configuration
- ✅ **Monitoring and health checks**
- ✅ **Automated updates and backups**

The application is now ready for production deployment with full monitoring and maintenance capabilities.
