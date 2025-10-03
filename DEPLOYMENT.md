# Deployment Guide

Complete guide for deploying and managing the OpenSearch Trending Queries infrastructure.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Deployment Process](#deployment-process)
4. [Validation and Testing](#validation-and-testing)
5. [Environment Management](#environment-management)
6. [Rollback Procedures](#rollback-procedures)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

## Prerequisites

### Required Tools
- Python 3.9 or higher
- AWS CDK 2.x (`npm install -g aws-cdk`)
- AWS CLI v2
- Make (optional, for convenience commands)
- Git

### AWS Account Setup
- AWS account with appropriate permissions
- AWS credentials configured (`aws configure`)
- Sufficient service quotas for:
  - Lambda functions
  - Kinesis shards
  - DynamoDB tables
  - S3 buckets
  - API Gateway APIs

### IAM Permissions Required
The deploying user/role needs permissions for:
- CloudFormation (full access)
- IAM (role and policy creation)
- S3 (bucket creation and management)
- DynamoDB (table creation)
- Lambda (function creation)
- Kinesis (stream creation)
- Glue (database, crawler, job creation)
- Step Functions (state machine creation)
- API Gateway (API creation)
- CloudWatch (logs, metrics, alarms)
- EventBridge (rule creation)
- KMS (key creation)

## Initial Setup

### 1. Clone Repository
```bash
git clone <repository-url>
cd opensearch-trending-queries
```

### 2. Install Dependencies
```bash
# Using pip
pip install -r requirements.txt

# Or using Make
make install
```

### 3. Configure AWS Credentials
```bash
# Configure default profile
aws configure

# Or configure named profile for production
aws configure --profile production
```

### 4. Bootstrap CDK (First Time Only)
```bash
# Bootstrap default region
make bootstrap ENV=dev

# Bootstrap specific region
make bootstrap ENV=prod REGION=us-west-2 PROFILE=production

# Or using script directly
python scripts/deploy.py bootstrap --env dev --region us-east-1
```

## Deployment Process

### Development Environment

#### Quick Deploy (with hotswap)
```bash
# Fast deployment for development (skips CloudFormation for compatible changes)
make deploy-fast ENV=dev
```

#### Standard Deploy
```bash
# Show what will change
make diff ENV=dev

# Deploy with approval prompt
make deploy ENV=dev

# Deploy without approval (CI/CD)
make deploy-no-approval ENV=dev
```

### Staging Environment

```bash
# Review changes
make diff ENV=staging

# Deploy
make deploy ENV=staging

# Validate deployment
make validate ENV=staging

# Run tests
make test-all ENV=staging
```

### Production Environment

```bash
# IMPORTANT: Always test in staging first!

# Review changes carefully
make diff ENV=prod PROFILE=production

# Deploy with approval
make deploy ENV=prod PROFILE=production

# Validate deployment
make validate ENV=prod PROFILE=production

# Run integration tests (read-only)
make test ENV=prod PROFILE=production

# Monitor CloudWatch dashboard
# Check for errors in logs
```

## Validation and Testing

### Post-Deployment Validation

```bash
# Validate infrastructure
make validate ENV=dev

# Check specific components
python scripts/validate_deployment.py --env dev
```

### Integration Tests

```bash
# Run integration tests
make test ENV=dev

# View detailed output
python scripts/run_integration_tests.py --env dev
```

### Performance Tests

```bash
# Standard performance test (60s, 10 RPS)
make test-performance ENV=dev

# Load test (300s, 50 RPS)
make test-performance-load ENV=staging

# Custom load test
python tests/performance_tests.py --env staging --duration 600 --rps 100
```

### Data Quality Tests

```bash
# Validate data quality
make test-data-quality ENV=dev

# Detailed validation
python tests/data_quality_tests.py --env dev
```

### Run All Tests

```bash
# Run complete test suite
make test-all ENV=staging
```

## Environment Management

### Environment Configuration

Environments are configured in `opensearch_trending_queries/config/environment_config.py`:

- **dev**: Development environment with minimal resources
- **staging**: Production-like environment for testing
- **prod**: Production environment with full resources

### Viewing Stack Outputs

```bash
# View outputs for environment
make outputs ENV=dev

# Or directly from AWS
aws cloudformation describe-stacks --stack-name OpenSearchTrendingQueries-dev --query 'Stacks[0].Outputs'
```

### Updating Configuration

1. Edit `opensearch_trending_queries/config/environment_config.py`
2. Review changes: `make diff ENV=<env>`
3. Deploy: `make deploy ENV=<env>`
4. Validate: `make validate ENV=<env>`

## Rollback Procedures

### Automatic Rollback

CloudFormation automatically rolls back failed deployments. Monitor the CloudFormation console during deployment.

### Manual Rollback

#### Option 1: CloudFormation Rollback
```bash
# Rollback to previous version
aws cloudformation rollback-stack --stack-name OpenSearchTrendingQueries-<env>

# Monitor rollback
aws cloudformation describe-stack-events --stack-name OpenSearchTrendingQueries-<env>
```

#### Option 2: Redeploy Previous Version
```bash
# Checkout previous version
git log --oneline  # Find previous commit
git checkout <previous-commit>

# Deploy previous version
make deploy ENV=<env>

# Return to latest
git checkout main
```

#### Option 3: Destroy and Recreate
```bash
# Destroy stack
make destroy ENV=<env>

# Checkout working version
git checkout <working-commit>

# Redeploy
make deploy ENV=<env>
```

### Emergency Rollback (Production)

```bash
# 1. Identify issue
aws cloudformation describe-stack-events --stack-name OpenSearchTrendingQueries-prod

# 2. Initiate rollback
aws cloudformation rollback-stack --stack-name OpenSearchTrendingQueries-prod

# 3. Monitor rollback progress
watch -n 10 'aws cloudformation describe-stacks --stack-name OpenSearchTrendingQueries-prod --query "Stacks[0].StackStatus"'

# 4. Validate after rollback
make validate ENV=prod PROFILE=production
```

## Troubleshooting

### Deployment Failures

#### Stack Stuck in UPDATE_ROLLBACK_FAILED
```bash
# Continue rollback
aws cloudformation continue-update-rollback --stack-name OpenSearchTrendingQueries-<env>

# If that fails, delete and redeploy
make destroy ENV=<env> --force
make deploy ENV=<env>
```

#### Resource Already Exists
```bash
# Check for orphaned resources
aws cloudformation list-stacks --stack-status-filter DELETE_FAILED

# Delete specific resource manually
aws <service> delete-<resource> --<resource-name> <name>

# Retry deployment
make deploy ENV=<env>
```

#### Insufficient Permissions
```bash
# Check current identity
aws sts get-caller-identity

# Verify permissions
aws iam get-user-policy --user-name <username> --policy-name <policy-name>

# Add required permissions and retry
```

### Validation Failures

#### S3 Bucket Not Found
- Check bucket was created: `aws s3 ls | grep opensearch-trending`
- Verify region: `aws s3api get-bucket-location --bucket <bucket-name>`
- Check CloudFormation events for creation errors

#### Lambda Function Not Active
- Check function status: `aws lambda get-function --function-name <name>`
- Review CloudWatch logs: `aws logs tail /aws/lambda/<function-name>`
- Verify IAM role permissions

#### API Gateway Returns 403
- Check API Gateway deployment stage
- Verify API key/authorization configuration
- Check CloudWatch logs for API Gateway

### Test Failures

#### Integration Tests Fail
```bash
# Check stack status
aws cloudformation describe-stacks --stack-name OpenSearchTrendingQueries-<env>

# Verify all resources exist
make validate ENV=<env>

# Check CloudWatch logs
aws logs tail /aws/lambda/<function-name> --follow
```

#### Performance Tests Show High Latency
- Check CloudWatch metrics for bottlenecks
- Review Lambda concurrent executions
- Check DynamoDB throttling metrics
- Verify Kinesis shard count

## Best Practices

### Pre-Deployment

1. **Review Changes**: Always run `make diff` before deploying
2. **Test in Dev**: Test changes in dev environment first
3. **Validate in Staging**: Full validation in staging before production
4. **Backup Data**: Ensure DynamoDB backups are enabled
5. **Tag Releases**: Use git tags for production deployments

### During Deployment

1. **Monitor CloudFormation**: Watch stack events in AWS Console
2. **Check CloudWatch**: Monitor metrics and logs during deployment
3. **Staged Rollout**: Deploy to dev → staging → production
4. **Communication**: Notify team of production deployments
5. **Rollback Plan**: Have rollback procedure ready

### Post-Deployment

1. **Validate**: Run validation script immediately
2. **Test**: Execute integration tests
3. **Monitor**: Watch CloudWatch dashboard for 15-30 minutes
4. **Document**: Record deployment notes and any issues
5. **Cleanup**: Remove old resources if applicable

### Security

1. **Use IAM Roles**: Never hardcode credentials
2. **Enable Encryption**: Verify KMS encryption is enabled
3. **Least Privilege**: Use minimal IAM permissions
4. **Audit Logs**: Enable CloudTrail for all environments
5. **Secrets Management**: Use AWS Secrets Manager for sensitive data

### Cost Optimization

1. **Right-Size Resources**: Adjust Lambda memory and DynamoDB capacity
2. **Lifecycle Policies**: Configure S3 lifecycle rules
3. **Reserved Capacity**: Consider reserved capacity for production
4. **Monitor Costs**: Set up billing alerts
5. **Clean Up**: Remove unused resources in dev/staging

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy to Staging

on:
  push:
    branches: [develop]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: make install
      
      - name: Deploy to staging
        run: make deploy-no-approval ENV=staging
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      
      - name: Validate deployment
        run: make validate ENV=staging
      
      - name: Run tests
        run: make test-all ENV=staging
```

## Monitoring and Maintenance

### Regular Tasks

- **Daily**: Check CloudWatch dashboard for errors
- **Weekly**: Review cost reports and optimize
- **Monthly**: Update dependencies and redeploy
- **Quarterly**: Review and update IAM policies

### Health Checks

```bash
# Quick health check
make validate ENV=prod PROFILE=production

# Detailed check
make test ENV=prod PROFILE=production
```

## Support and Resources

- **AWS Documentation**: https://docs.aws.amazon.com/
- **CDK Documentation**: https://docs.aws.amazon.com/cdk/
- **Project README**: See README.md for architecture details
- **Monitoring Guide**: See MONITORING.md for observability
- **Security Guide**: See SECURITY.md for security best practices

## Appendix

### Useful Commands

```bash
# List all stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE

# Get stack outputs
aws cloudformation describe-stacks --stack-name OpenSearchTrendingQueries-dev --query 'Stacks[0].Outputs'

# View CloudWatch logs
aws logs tail /aws/lambda/<function-name> --follow

# Check Kinesis stream
aws kinesis describe-stream --stream-name <stream-name>

# Query DynamoDB
aws dynamodb scan --table-name <table-name> --limit 10

# List S3 objects
aws s3 ls s3://<bucket-name>/ --recursive --human-readable
```

### Environment Variables

```bash
# Set default region
export AWS_DEFAULT_REGION=us-east-1

# Set profile
export AWS_PROFILE=production

# Set CDK context
export CDK_DEFAULT_ACCOUNT=123456789012
export CDK_DEFAULT_REGION=us-east-1
```
