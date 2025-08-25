# ==============================================================================
# Makefile for Project Automation
#
# Provides a unified interface for common development tasks, abstracting away
# the underlying Docker Compose commands for a better Developer Experience (DX).
#
# Inspired by the self-documenting Makefile pattern.
# See: https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
# ==============================================================================

# Ensure that the targets are always run
.PHONY: help setup up down logs shell format format-check lint lint-check test migrate

# Default target executed when 'make' is run without arguments
.DEFAULT_GOAL := help

# Define the project name based on the directory name for dynamic container naming
PROJECT_NAME := $(shell basename $(CURDIR))

# Use sudo if the user is not root, to handle Docker permissions
SUDO := $(shell if [ $$(id -u) -ne 0 ]; then echo "sudo"; fi)

# Define project names for different environments
DEV_PROJECT_NAME := $(PROJECT_NAME)-dev
PROD_PROJECT_NAME := $(PROJECT_NAME)-prod
TEST_PROJECT_NAME := $(PROJECT_NAME)-test

# ==============================================================================
# HELP
# ==============================================================================

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ==============================================================================
# PROJECT SETUP & ENVIRONMENT
# ==============================================================================

setup: ## Initialize project: create .env files and pull required Docker images.
	@if [ ! -f .env.dev ]; then \
		echo "Creating .env.dev from .env.example..."; \
		cp .env.example .env.dev; \
	else \
		echo ".env.dev already exists. Skipping creation."; \
	fi
	@if [ ! -f .env.prod ]; then \
		echo "Creating .env.prod from .env.example..."; \
		cp .env.example .env.prod; \
	else \
		echo ".env.prod already exists. Skipping creation."; \
	fi
	@echo "Pulling PostgreSQL image for tests..."
	$(SUDO) docker pull postgres:16-alpine

up: ## Start all development containers in detached mode
	@echo "Starting up development services..."
	@ln -sf .env.dev .env
	$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) up -d

down: ## Stop and remove all development containers
	@echo "Shutting down development services..."
	@ln -sf .env.dev .env
	$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) down --remove-orphans

clean: ## Stop and remove all dev containers, networks, and volumes
	@echo "Cleaning up all development Docker resources (including volumes)..."
	@ln -sf .env.dev .env
	$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) down --volumes --remove-orphans

rebuild: ## Rebuild the api service without cache and restart it
	@echo "Rebuilding api service with --no-cache..."
	@ln -sf .env.dev .env
	$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) build --no-cache api
	$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) up -d api

up-prod: ## Start all production-like containers
	@echo "Starting up production-like services..."
	@ln -sf .env.prod .env
	$(SUDO) docker compose -f docker-compose.yml --project-name $(PROD_PROJECT_NAME) up -d --build --pull always --remove-orphans

down-prod: ## Stop and remove all production-like containers
	@echo "Shutting down production-like services..."
	@ln -sf .env.prod .env
	$(SUDO) docker compose -f docker-compose.yml --project-name $(PROD_PROJECT_NAME) down --remove-orphans

logs: ## View the logs for the development API service
	@echo "Following logs for the dev api service..."
	@ln -sf .env.dev .env
	$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) logs -f api

shell: ## Open a shell inside the running development API container
	@echo "Opening shell in dev api container..."
	@ln -sf .env.dev .env
	@$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) exec api /bin/sh || \
		(echo "Failed to open shell. Is the container running? Try 'make up'" && exit 1)

migrate: ## Run database migrations against the development database
	@echo "Running database migrations for dev environment..."
	@ln -sf .env.dev .env
	$(SUDO) docker compose -f docker-compose.yml -f docker-compose.override.yml --project-name $(DEV_PROJECT_NAME) exec api sh -c ". /app/.venv/bin/activate && alembic upgrade head"

# ==============================================================================
# CODE QUALITY & TESTING
# ==============================================================================

format: ## Format the code using Black
	@echo "Formatting code with Black..."
	poetry run black src/ tests/

format-check: ## Check if the code is formatted with Black
	@echo "Checking code format with Black..."
	poetry run black --check src/ tests/

lint: ## Lint and fix the code with Ruff automatically
	@echo "Linting and fixing code with Ruff..."
	poetry run ruff check src/ tests/ --fix

lint-check: ## Check the code for issues with Ruff
	@echo "Checking code with Ruff..."
	poetry run ruff check src/ tests/

test: ## Run the test suite
	@echo "Running test suite..."
	@VENV_PATH=$$(poetry env info -p); \
	$(SUDO) $$VENV_PATH/bin/pytest