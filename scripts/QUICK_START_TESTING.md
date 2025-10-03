# Quick Start: Testing Guide

This guide helps you quickly get started with testing the OpenSearch Trending Queries system.

## Prerequisites

- AWS CDK deployed to target environment
- Python 3.9+ installed
- AWS credentials configured
- Dependencies installed: `make install`

## Quick Test Commands

### 1. Generate Sample Data (1 minute)

```bash
# Generate 1000 sample search queries
make generate-data ENV=dev
```

This creates realistic search query logs and ingests them into Kinesis.

### 2. Wait for Data Processing (5-10 minutes)

Data flows through:
- Kinesis → S3 (5-10 minutes buffering)
- Glue Crawler (scheduled or manual trigger)
- Step Functions workflow (scheduled or manual trigger)

### 3. Run Integration Tests (2 minutes)

```bash
# Validate infrastructure and data
make test ENV=dev
```

### 4. Run End-to-End Test (10-15 minutes)

```bash
# Get your API URL from stack outputs
make outputs ENV=dev

# Run complete E2E test
python scripts/e2e_test_workflow.py --env dev \
  --api-url https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod
```

## Common Testing Workflows

### After Fresh Deployment

```bash
# 1. Deploy
make deploy ENV=dev

# 2. Validate deployment
make validate ENV=dev

# 3. Generate test data
make generate-data ENV=dev

# 4. Wait 10 minutes, then trigger Step Functions manually in AWS Console

# 5. Run tests
make test ENV=dev
```

### Before Production Deployment

```bash
# 1. Deploy to staging
make deploy ENV=staging

# 2. Generate realistic data volume
make generate-data-large ENV=staging

# 3. Wait for processing

# 4. Run all tests
make test-all ENV=staging

# 5. Run E2E test with benchmarking
make test-e2e ENV=staging
```

### Performance Testing

```bash
# Generate large dataset
python scripts/generate_sample_data.py --env staging \
  --hours 48 --queries-per-hour 500

# Run extended benchmark
python scripts/e2e_test_workflow.py --env staging \
  --api-url https://api.example.com \
  --benchmark-duration 300 \
  --benchmark-rps 50 \
  --output perf-test-results.json
```

### Data Quality Validation

```bash
# Run data quality tests
make test-data-quality ENV=dev

# Verify results in DynamoDB
python scripts/e2e_test_workflow.py --env dev \
  --skip-ingestion --skip-workflow --skip-api --skip-benchmark
```

## Troubleshooting

### No Data in DynamoDB

**Symptoms**: API returns 404, DynamoDB table is empty

**Solutions**:
1. Check if Step Functions workflow has run: AWS Console → Step Functions
2. Manually trigger workflow if needed
3. Check Glue job logs: AWS Console → Glue → Jobs
4. Verify S3 has data: `aws s3 ls s3://your-bucket/`

### Kinesis Throttling

**Symptoms**: Data ingestion fails with throttling errors

**Solutions**:
1. Reduce ingestion rate: use smaller `--count` or `--queries-per-hour`
2. Increase Kinesis shard count in environment config
3. Add delays between batches

### API Tests Fail

**Symptoms**: E2E test fails at API testing step

**Solutions**:
1. Verify API URL is correct: `make outputs ENV=dev`
2. Check API Gateway deployment: AWS Console → API Gateway
3. Verify Lambda functions are active: `make validate ENV=dev`
4. Check Lambda logs: AWS Console → CloudWatch → Log Groups

### Workflow Timeout

**Symptoms**: Step Functions execution times out

**Solutions**:
1. Check Glue job status: AWS Console → Glue → Jobs
2. Review CloudWatch logs for errors
3. Verify sufficient data exists for processing
4. Increase timeout in E2E script: `--skip-workflow`

## Test Data Cleanup

### Preview Cleanup

```bash
# See what would be deleted
python scripts/generate_sample_data.py --env dev --cleanup --dry-run \
  --s3-bucket opensearch-trending-queries-dev-raw-logs
```

### Execute Cleanup

```bash
# Clean up test data
make cleanup-data ENV=dev
```

## Getting Help

- **Detailed Testing Guide**: See [SAMPLE_DATA_GUIDE.md](SAMPLE_DATA_GUIDE.md)
- **Integration Tests**: See [../tests/README.md](../tests/README.md)
- **Deployment Guide**: See [../DEPLOYMENT.md](../DEPLOYMENT.md)
- **Makefile Help**: Run `make help`

## Quick Reference

| Command | Purpose | Duration |
|---------|---------|----------|
| `make generate-data ENV=dev` | Generate 1k sample records | 1 min |
| `make generate-data-large ENV=dev` | Generate 12k sample records | 2-3 min |
| `make test ENV=dev` | Run integration tests | 2 min |
| `make test-all ENV=dev` | Run all test suites | 5-10 min |
| `make test-e2e ENV=dev` | Run E2E workflow test | 10-15 min |
| `make validate ENV=dev` | Validate infrastructure | 1 min |
| `make cleanup-data ENV=dev` | Clean up test data | 1-2 min |

## Next Steps

1. Review [SAMPLE_DATA_GUIDE.md](SAMPLE_DATA_GUIDE.md) for advanced usage
2. Set up CI/CD pipeline with automated testing
3. Configure CloudWatch alarms for monitoring
4. Schedule regular E2E tests in staging
5. Document environment-specific test procedures
