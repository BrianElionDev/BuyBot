#!/bin/bash

# Rubicon Trading Bot Deployment Script
# This script automates the deployment process

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="buybot"
APP_DIR="/home/dev/opt/BuyBot"
IMAGE_NAME="ghcr.io/brianeliondev/buybot:latest"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_docker() {
    log_info "Checking Docker installation..."
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not available. Please install Docker Compose first."
        exit 1
    fi

    log_success "Docker and Docker Compose are installed"
}

check_environment() {
    log_info "Checking environment file..."
    if [ ! -f "${APP_DIR}/.env" ]; then
        log_warning "Environment file not found at ${APP_DIR}/.env"
        log_info "Please create the environment file with your configuration"
        log_info "You can copy from example.env and update with your values"
        exit 1
    fi
    log_success "Environment file found"
}

create_directories() {
    log_info "Ensuring application directories exist..."
    mkdir -p "${APP_DIR}/logs"
    # Set permissions for container to write logs
    sudo chmod 777 "${APP_DIR}/logs"
    log_success "Directories ready"
}

deploy_application() {
    log_info "Deploying application..."

    # Pull latest image
    log_info "Pulling latest Docker image..."
    docker pull ${IMAGE_NAME}

    # Stop and remove existing containers using docker compose
    log_info "Stopping existing containers..."
    cd ${APP_DIR}
    docker compose -f docker-compose.yml down || true

    # Wait for port to be released
    log_info "Waiting for port 8080 to be released..."
    while netstat -tuln | grep -q :8080; do
        echo "Port 8080 still in use, waiting..."
        sleep 2
    done

    # Start new container using docker compose
    log_info "Starting new container..."
    docker compose -f docker-compose.yml up -d

    log_success "Application deployed successfully"
}

verify_deployment() {
    log_info "Verifying deployment..."

    # Wait for container to start
    sleep 10

    # Check if container is running using docker compose
    cd ${APP_DIR}
    if docker compose -f docker-compose.yml ps | grep -q "Up"; then
        log_success "Container is running"
    else
        log_error "Container is not running"
        docker compose -f docker-compose.yml logs
        exit 1
    fi

    # Check health endpoint
    if curl -f http://localhost:8080/health > /dev/null 2>&1; then
        log_success "Health check passed"
    else
        log_warning "Health check failed, but container is running"
    fi

    # Show container status
    log_info "Container status:"
    docker compose -f docker-compose.yml ps
}

show_logs() {
    log_info "Showing recent logs..."
    cd ${APP_DIR}
    docker compose -f docker-compose.yml logs --tail 50
}

show_access_info() {
    log_success "Deployment completed successfully!"
    echo ""
    log_info "Access Information:"
    echo "  - Application: http://$(hostname -I | awk '{print $1}'):8080"
    echo "  - Health Check: http://$(hostname -I | awk '{print $1}'):8080/health"
    echo ""
    log_info "Log Files Location:"
    echo "  - ${APP_DIR}/logs/"
    echo ""
    log_info "Useful Commands:"
    echo "  - View logs: docker compose -f docker-compose.yml logs -f"
    echo "  - Restart: docker compose -f docker-compose.yml restart"
    echo "  - Stop: docker compose -f docker-compose.yml down"
    echo "  - Update: ./deploy.sh update"
}

# Main deployment function
deploy() {
    log_info "Starting Rubicon Trading Bot deployment..."

    check_docker
    create_directories
    check_environment
    deploy_application
    verify_deployment
    show_access_info
}

# Update function
update() {
    log_info "Updating Rubicon Trading Bot..."

    check_docker
    check_environment
    deploy_application
    verify_deployment
    show_access_info
}

# Logs function
logs() {
    show_logs
}

# Status function
status() {
    log_info "Checking application status..."
    cd ${APP_DIR}

    if docker compose -f docker-compose.yml ps | grep -q "Up"; then
        log_success "Application is running"
        docker compose -f docker-compose.yml ps
        echo ""
        log_info "Health check:"
        curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "Health check failed"
    else
        log_error "Application is not running"
    fi
}

# Help function
help() {
    echo "Rubicon Trading Bot Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  deploy    Deploy the application (default)"
    echo "  update    Update the application"
    echo "  logs      Show application logs"
    echo "  status    Show application status"
    echo "  help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 deploy"
    echo "  $0 update"
    echo "  $0 logs"
    echo "  $0 status"
}

# Main script logic
case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    update)
        update
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    help|--help|-h)
        help
        ;;
    *)
        log_error "Unknown command: $1"
        help
        exit 1
        ;;
esac

