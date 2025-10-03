# Deployment Scripts

This directory contains scripts for deploying and managing the OpenSearch Trending Queries infrastructure.

## Scripts Overview

### deploy.py
Main deployment script that handles CDK operations with environment-specific configuration.

**Features:**
- Environment validation (dev, staging, prod)
- Pre-deployment validation
- Post-deployment validation
- Automatic rollback guidance on failure
- Stack dependency management

**Usage:**
```bash
# Bootstrap CDK (first time only)
python scripts/deploy.py bootstrap --env dev --region us-east-1

# Synthesize CloudFormation templates
python scripts/deploy.py synth --env dev

# Show differences
python scripts/deploy.py diff --env staging

# Deploy to environment
python scripts/deploy.py deploy --env dev
python scripts/deploy.py deploy --env prod --profile production

# Deploy without approval (CI/CD)
python scripts/deploy.py deploy --env dev --no-approval

# Fast deploy for development (hotswap)
python scripts/deploy.py deploy --env dev --hotswap --no-approval

# Destroy stack
python scripts/deploy.py destroy --env dev
python scripts/deploy.py destroy --env prod --force
```

### validate_deployment.py
Post-deployment validation script that checks all infrastructure components.

**Validates:**
- S3 buckets (existence, encryption, versioning)
- DynamoDB table (status, billing mode, TTL)
- Kinesis stream (status, shard count, retention)
- Glue resources (database, crawler, jobs)
- Step Functions (state machine status)
- API Gateway (endpoints, configuration)
- Lambda functions (state, runtime, memory)

**Usage:**
```bash
# Validate deployment
python scripts/validate_deployment.py --env dev
python scripts/validate_deployment.py --env prod --region us-west-2 --profile production
```

### run_integration_tests.py
Integration test runner that validates the complete data pipeline and API functionality.

**Usage:**
```bash
python scripts/run_integration_tests.py --env dev
```

### generate_sample_data.py
Sample data generator for testing the system with realistic search query logs.

**Features:**
- Generate realistic search queries with proper distribution
- Ingest to Kinesis or S3
- Validate data ingestion
- Clean up test data

**Usage:**
```bash
# Generate 1000 sample records
python scripts/generate_sample_data.py --env dev --count 1000

# Generate time series data
python scripts/generate_sample_data.py --env dev --hours 24 --queries-per-hour 500

# Clean up test data
python scripts/generate_sample_data.py --env dev --cleanup --dry-run
```

### e2e_test_workflow.py
End-to-end testing workflow that exercises the complete pipeline from ingestion to API.

**Features:**
- Automated data generation and ingestion
- Workflow execution and monitoring
- Result verification
- API endpoint testing
- Performance benchmarking
- Cost monitoring

**Usage:**
```bash
# Full E2E test
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com

# Custom benchmark
python scripts/e2e_test_workflow.py --env staging --api-url https://api.example.com \
  --benchmark-duration 300 --benchmark-rps 50
```

See [SAMPLE_DATA_GUIDE.md](SAMPLE_DATA_GUIDE.md) for detailed documentation.

## Using the Makefile

The Makefile provides convenient shortcuts for common operations:

```bash
# Show help
make help

# Install dependencies
make install

# Bootstrap CDK
make bootstrap ENV=dev

# Deploy to environment
make deploy ENV=dev
make deploy ENV=staging REGION=us-west-2
make deploy ENV=prod PROFILE=production

# Fast deploy (dev only)
make deploy-fast ENV=dev

# Show differences
make diff ENV=staging

# Validate deployment
make validate ENV=dev

# Run integration tests
make test ENV=dev

# Run all tests
make test-all ENV=dev

# Run E2E workflow test
make test-e2e ENV=dev

# Generate sample data
make generate-data ENV=dev
make generate-data-large ENV=dev

# Clean up test data
make cleanup-data ENV=dev

# Show stack outputs
make outputs ENV=dev

# Destroy stack
make destroy ENV=dev

# Clean generated files
make clean
```

## Environment-Specific Shortcuts

```bash
# Development
make dev-deploy
make dev-validate

# Staging
make staging-deploy
make staging-validate

# Production
make prod-deploy
make prod-validate
```

## Deployment Workflow

### Initial Setup
1. Install dependencies: `make install`
2. Bootstrap CDK: `make bootstrap ENV=dev`

### Development Deployment
1. Make code changes
2. Show differences: `make diff ENV=dev`
3. Deploy: `make deploy-fast ENV=dev` (or `make deploy ENV=dev`)
4. Validate: `make validate ENV=dev`
5. Test: `make test ENV=dev`

### Production Deployment
1. Deploy to staging: `make deploy ENV=staging`
2. Validate staging: `make validate ENV=staging`
3. Run tests: `make test ENV=staging`
4. Deploy to production: `make deploy ENV=prod PROFILE=production`
5. Validate production: `make validate ENV=prod PROFILE=production`

## CI/CD Integration

For automated deployments in CI/CD pipelines:

```bash
# Non-interactive deployment
python scripts/deploy.py deploy --env staging --no-approval

# With validation
python scripts/deploy.py deploy --env staging --no-approval && \
python scripts/validate_deployment.py --env staging
```

## Rollback Procedures

### Automatic Rollback
If deployment fails, CloudFormation automatically rolls back changes.

### Manual Rollback
```bash
# Check stack events
aws cloudformation describe-stack-events --stack-name OpenSearchTrendingQueries-prod

# Rollback to previous version
aws cloudformation rollback-stack --stack-name OpenSearchTrendingQueries-prod

# Or destroy and redeploy previous version
make destroy ENV=prod
git checkout <previous-commit>
make deploy ENV=prod
```

## Troubleshooting

### Deployment Fails
1. Check CloudFormation events in AWS Console
2. Review error messages in deployment output
3. Validate AWS credentials: `aws sts get-caller-identity`
4. Check CDK version: `cdk --version`

### Validation Fails
1. Check specific component that failed
2. Review CloudWatch logs for the component
3. Verify IAM permissions
4. Check resource quotas in AWS account

### Stack Stuck in UPDATE_ROLLBACK_FAILED
```bash
# Continue rollback
aws cloudformation continue-update-rollback --stack-name OpenSearchTrendingQueries-<env>

# Or delete and redeploy
make destroy ENV=<env> --force
make deploy ENV=<env>
```

## Best Practices

1. **Always validate before production**: Run validation and tests in staging before deploying to production
2. **Use profiles for production**: Keep production credentials separate with AWS profiles
3. **Review diffs**: Always review `make diff` output before deploying
4. **Tag deployments**: Use git tags for production deployments
5. **Monitor deployments**: Watch CloudWatch during and after deployment
6. **Keep outputs**: Save `cdk-outputs-*.json` files for reference
7. **Test rollback**: Periodically test rollback procedures in dev/staging

## Environment Variables

The following environment variables can be used:

- `CDK_DEFAULT_ACCOUNT`: AWS account ID (auto-detected if not set)
- `CDK_DEFAULT_REGION`: AWS region (default: us-east-1)
- `AWS_PROFILE`: AWS profile to use
- `AWS_REGION`: AWS region (alternative to CDK_DEFAULT_REGION)

## Requirements

- Python 3.9+
- AWS CDK 2.x
- AWS CLI v2
- boto3
- Valid AWS credentials configured
