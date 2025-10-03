# Makefile for OpenSearch Trending Queries CDK Deployment
# Provides convenient commands for deployment and testing

.PHONY: help install bootstrap synth diff deploy destroy validate test clean

# Default environment
ENV ?= dev
REGION ?= us-east-1
PROFILE ?=

# Python and CDK commands
PYTHON := python
PIP := pip
CDK := cdk

# Build command arguments
DEPLOY_SCRIPT := $(PYTHON) scripts/deploy.py
VALIDATE_SCRIPT := $(PYTHON) scripts/validate_deployment.py
TEST_SCRIPT := $(PYTHON) scripts/run_integration_tests.py

# Add profile if specified
ifdef PROFILE
	PROFILE_ARG := --profile $(PROFILE)
else
	PROFILE_ARG :=
endif

help:
	@echo "OpenSearch Trending Queries - Deployment Commands"
	@echo ""
	@echo "Usage: make [target] ENV=[dev|staging|prod] REGION=[region] PROFILE=[profile]"
	@echo ""
	@echo "Setup Commands:"
	@echo "  install       Install Python dependencies"
	@echo "  bootstrap     Bootstrap CDK in target account/region"
	@echo ""
	@echo "Deployment Commands:"
	@echo "  synth         Synthesize CloudFormation templates"
	@echo "  diff          Show differences between deployed and local"
	@echo "  deploy        Deploy stack to specified environment"
	@echo "  deploy-fast   Deploy with hotswap (dev only, faster)"
	@echo "  destroy       Destroy stack in specified environment"
	@echo ""
	@echo "Validation Commands:"
	@echo "  validate            Validate deployed infrastructure"
	@echo "  test                Run integration tests"
	@echo "  test-performance    Run performance tests (60s, 10 RPS)"
	@echo "  test-performance-load  Run load tests (300s, 50 RPS)"
	@echo "  test-data-quality   Run data quality validation"
	@echo "  test-all            Run all test suites"
	@echo "  test-e2e            Run end-to-end workflow test"
	@echo ""
	@echo "Sample Data Commands:"
	@echo "  generate-data       Generate and ingest sample data"
	@echo "  generate-data-large Generate large dataset (10k records)"
	@echo "  cleanup-data        Clean up test data"
	@echo ""
	@echo "Utility Commands:"
	@echo "  clean         Clean generated files"
	@echo "  outputs       Show stack outputs"
	@echo ""
	@echo "Examples:"
	@echo "  make deploy ENV=dev"
	@echo "  make deploy ENV=prod REGION=us-west-2 PROFILE=production"
	@echo "  make validate ENV=staging"

install:
	@echo "Installing dependencies..."
	$(PIP) install -r requirements.txt
	@echo "Dependencies installed!"

bootstrap:
	@echo "Bootstrapping CDK for $(ENV) in $(REGION)..."
	$(DEPLOY_SCRIPT) bootstrap --env $(ENV) --region $(REGION) $(PROFILE_ARG)

synth:
	@echo "Synthesizing CDK stack for $(ENV)..."
	$(DEPLOY_SCRIPT) synth --env $(ENV) --region $(REGION) $(PROFILE_ARG)

diff:
	@echo "Showing diff for $(ENV)..."
	$(DEPLOY_SCRIPT) diff --env $(ENV) --region $(REGION) $(PROFILE_ARG)

deploy:
	@echo "Deploying to $(ENV) environment..."
	$(DEPLOY_SCRIPT) deploy --env $(ENV) --region $(REGION) $(PROFILE_ARG)

deploy-fast:
	@echo "Deploying to $(ENV) with hotswap..."
	@if [ "$(ENV)" != "dev" ]; then \
		echo "Error: Fast deploy only available for dev environment"; \
		exit 1; \
	fi
	$(DEPLOY_SCRIPT) deploy --env $(ENV) --region $(REGION) $(PROFILE_ARG) --hotswap --no-approval

deploy-no-approval:
	@echo "Deploying to $(ENV) without approval..."
	$(DEPLOY_SCRIPT) deploy --env $(ENV) --region $(REGION) $(PROFILE_ARG) --no-approval

destroy:
	@echo "Destroying $(ENV) stack..."
	$(DEPLOY_SCRIPT) destroy --env $(ENV) --region $(REGION) $(PROFILE_ARG)

destroy-force:
	@echo "Force destroying $(ENV) stack..."
	$(DEPLOY_SCRIPT) destroy --env $(ENV) --region $(REGION) $(PROFILE_ARG) --force

validate:
	@echo "Validating $(ENV) deployment..."
	$(VALIDATE_SCRIPT) --env $(ENV) --region $(REGION) $(PROFILE_ARG)

test:
	@echo "Running integration tests for $(ENV)..."
	$(TEST_SCRIPT) --env $(ENV) --region $(REGION) $(PROFILE_ARG)

test-performance:
	@echo "Running performance tests for $(ENV)..."
	$(PYTHON) tests/performance_tests.py --env $(ENV) --region $(REGION) $(PROFILE_ARG) --duration 60 --rps 10

test-performance-load:
	@echo "Running load tests for $(ENV)..."
	$(PYTHON) tests/performance_tests.py --env $(ENV) --region $(REGION) $(PROFILE_ARG) --duration 300 --rps 50

test-data-quality:
	@echo "Running data quality tests for $(ENV)..."
	$(PYTHON) tests/data_quality_tests.py --env $(ENV) --region $(REGION) $(PROFILE_ARG)

test-all:
	@echo "Running all tests for $(ENV)..."
	@$(MAKE) test ENV=$(ENV) REGION=$(REGION) PROFILE=$(PROFILE)
	@$(MAKE) test-data-quality ENV=$(ENV) REGION=$(REGION) PROFILE=$(PROFILE)
	@$(MAKE) test-performance ENV=$(ENV) REGION=$(REGION) PROFILE=$(PROFILE)

test-e2e:
	@echo "Running end-to-end workflow test for $(ENV)..."
	$(PYTHON) scripts/e2e_test_workflow.py --env $(ENV) --region $(REGION) $(PROFILE_ARG) --output e2e-test-results-$(ENV).json

generate-data:
	@echo "Generating sample data for $(ENV)..."
	$(PYTHON) scripts/generate_sample_data.py --env $(ENV) --region $(REGION) $(PROFILE_ARG) --count 1000 --validate

generate-data-large:
	@echo "Generating large dataset for $(ENV)..."
	$(PYTHON) scripts/generate_sample_data.py --env $(ENV) --region $(REGION) $(PROFILE_ARG) --hours 24 --queries-per-hour 500 --validate

cleanup-data:
	@echo "Cleaning up test data for $(ENV)..."
	$(PYTHON) scripts/generate_sample_data.py --env $(ENV) --region $(REGION) $(PROFILE_ARG) --cleanup --dry-run
	@echo ""
	@read -p "Proceed with cleanup? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		$(PYTHON) scripts/generate_sample_data.py --env $(ENV) --region $(REGION) $(PROFILE_ARG) --cleanup; \
	else \
		echo "Cleanup cancelled."; \
	fi

outputs:
	@echo "Stack outputs for $(ENV):"
	@if [ -f "cdk-outputs-$(ENV).json" ]; then \
		cat cdk-outputs-$(ENV).json | $(PYTHON) -m json.tool; \
	else \
		echo "No outputs file found. Run 'make deploy ENV=$(ENV)' first."; \
	fi

clean:
	@echo "Cleaning generated files..."
	rm -rf cdk.out
	rm -f cdk-outputs-*.json
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete!"

# Environment-specific shortcuts
dev-deploy:
	@$(MAKE) deploy ENV=dev

staging-deploy:
	@$(MAKE) deploy ENV=staging

prod-deploy:
	@$(MAKE) deploy ENV=prod

dev-validate:
	@$(MAKE) validate ENV=dev

staging-validate:
	@$(MAKE) validate ENV=staging

prod-validate:
	@$(MAKE) validate ENV=prod
