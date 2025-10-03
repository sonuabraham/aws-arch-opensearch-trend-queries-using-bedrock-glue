# Sample Data Generation and Testing Guide

This guide covers the sample data generation utilities and end-to-end testing workflow for the OpenSearch Trending Queries system.

## Overview

The testing utilities provide:
- **Sample Data Generator**: Create realistic search query logs
- **Data Ingestion Utility**: Ingest data to Kinesis or S3
- **Data Validation Utility**: Verify data in the pipeline
- **Cleanup Utility**: Remove test data
- **E2E Test Workflow**: Complete pipeline testing with benchmarking

## Sample Data Generator

### Basic Usage

Generate 1000 sample records and ingest to Kinesis:
```bash
python scripts/generate_sample_data.py --env dev --count 1000
```

### Time Series Data

Generate data spread over multiple hours:
```bash
# 24 hours of data, 500 queries per hour
python scripts/generate_sample_data.py --env dev --hours 24 --queries-per-hour 500

# 7 days of data, 100 queries per hour
python scripts/generate_sample_data.py --env dev --hours 168 --queries-per-hour 100
```

### Data Validation

Validate data after ingestion:
```bash
python scripts/generate_sample_data.py --env dev --count 1000 --validate
```

### Direct S3 Upload

Bypass Kinesis and upload directly to S3:
```bash
python scripts/generate_sample_data.py --env dev --count 1000 \
  --s3-bucket opensearch-trending-queries-dev-raw-logs
```

### Reproducible Data

Use a seed for reproducible data generation:
```bash
python scripts/generate_sample_data.py --env dev --count 1000 --seed 42
```

### Custom Stream Name

Specify a custom Kinesis stream:
```bash
python scripts/generate_sample_data.py --env dev --count 1000 \
  --stream-name my-custom-stream
```

### Cleanup Test Data

Preview cleanup (dry run):
```bash
python scripts/generate_sample_data.py --env dev --cleanup --dry-run \
  --s3-bucket opensearch-trending-queries-dev-raw-logs
```

Execute cleanup:
```bash
python scripts/generate_sample_data.py --env dev --cleanup \
  --s3-bucket opensearch-trending-queries-dev-raw-logs
```

## End-to-End Test Workflow

### Complete Pipeline Test

Run full end-to-end test:
```bash
python scripts/e2e_test_workflow.py --env dev \
  --api-url https://abc123.execute-api.us-east-1.amazonaws.com/prod
```

### Test Steps

The E2E workflow executes these steps:

1. **Data Ingestion**: Generate and ingest sample data
2. **Workflow Execution**: Trigger Step Functions state machine
3. **Result Verification**: Validate DynamoDB data
4. **API Testing**: Test GET endpoints
5. **Performance Benchmark**: Load test API
6. **Cost Monitoring**: Report costs by service

### Skip Specific Steps

Skip data ingestion (use existing data):
```bash
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com \
  --skip-ingestion
```

Skip workflow execution:
```bash
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com \
  --skip-workflow
```

Skip API tests:
```bash
python scripts/e2e_test_workflow.py --env dev --skip-api
```

Skip performance benchmark:
```bash
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com \
  --skip-benchmark
```

Skip cost monitoring:
```bash
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com \
  --skip-cost
```

### Custom Benchmark Settings

Run longer benchmark with higher load:
```bash
python scripts/e2e_test_workflow.py --env staging \
  --api-url https://api.example.com \
  --benchmark-duration 300 \
  --benchmark-rps 50
```

### Save Test Report

Generate detailed JSON report:
```bash
python scripts/e2e_test_workflow.py --env dev \
  --api-url https://api.example.com \
  --output e2e-test-results-dev.json
```

## Makefile Commands

### Sample Data Generation

```bash
# Generate 1000 sample records
make generate-data ENV=dev

# Generate large dataset (12k records over 24 hours)
make generate-data-large ENV=dev

# Clean up test data (with confirmation)
make cleanup-data ENV=dev
```

### End-to-End Testing

```bash
# Run complete E2E test
make test-e2e ENV=dev

# Run all test suites
make test-all ENV=dev
```

## Data Characteristics

### Query Distribution

The sample data generator creates realistic search queries with:

- **30% trending queries**: High-frequency queries that appear more often
- **70% regular queries**: Normal distribution across categories

### Query Categories

- **Technology**: ML, programming, cloud services, containers
- **Education**: Courses, certifications, tutorials
- **Business**: DevOps, project management, analytics
- **Tools**: Git, CI/CD, infrastructure, monitoring

### Realistic Metrics

Each query log includes:
- `timestamp`: ISO 8601 format with timezone
- `user_id`: Random user identifier
- `session_id`: Random session identifier
- `query`: Search query text
- `results_count`: 0-500 results
- `click_through`: Boolean (70% true when results > 0)
- `source`: "sample_data_generator"

## Testing Scenarios

### Scenario 1: Initial Deployment Test

Test a fresh deployment:
```bash
# 1. Generate and ingest data
make generate-data ENV=dev

# 2. Wait for data to flow through Kinesis to S3 (5-10 minutes)

# 3. Manually trigger Step Functions workflow in AWS Console

# 4. Run E2E test (skip ingestion and workflow)
python scripts/e2e_test_workflow.py --env dev \
  --api-url https://api.example.com \
  --skip-ingestion --skip-workflow
```

### Scenario 2: Performance Testing

Test system under load:
```bash
# 1. Generate large dataset
make generate-data-large ENV=staging

# 2. Run E2E test with extended benchmark
python scripts/e2e_test_workflow.py --env staging \
  --api-url https://api.example.com \
  --benchmark-duration 600 \
  --benchmark-rps 100
```

### Scenario 3: Data Quality Validation

Validate data quality after workflow execution:
```bash
# 1. Generate time series data
python scripts/generate_sample_data.py --env dev \
  --hours 48 --queries-per-hour 200

# 2. Wait for workflow execution

# 3. Run data quality tests
make test-data-quality ENV=dev

# 4. Verify results
python scripts/e2e_test_workflow.py --env dev \
  --skip-ingestion --skip-workflow --skip-api --skip-benchmark
```

### Scenario 4: Cost Analysis

Monitor costs during testing:
```bash
# 1. Run E2E test with cost monitoring
python scripts/e2e_test_workflow.py --env dev \
  --api-url https://api.example.com \
  --output cost-analysis.json

# 2. Review cost breakdown
cat cost-analysis.json | python -m json.tool
```

## Troubleshooting

### Data Not Appearing in S3

**Issue**: Generated data not visible in S3 after ingestion.

**Solution**:
- Check Kinesis stream status: `aws kinesis describe-stream --stream-name <name>`
- Verify Kinesis Firehose delivery stream (if configured)
- Wait 5-10 minutes for buffering
- Check CloudWatch logs for errors

### Workflow Execution Timeout

**Issue**: Step Functions workflow times out during E2E test.

**Solution**:
- Check Glue job status in AWS Console
- Review Glue job logs in CloudWatch
- Increase workflow timeout in E2E script
- Verify sufficient data exists for processing

### API Tests Return 404

**Issue**: API endpoints return 404 during testing.

**Solution**:
- Normal for new deployments with no data
- Run workflow to generate trending queries
- Check DynamoDB table for data
- Verify API Gateway deployment

### Cost Monitoring Fails

**Issue**: Cost monitoring step fails with permissions error.

**Solution**:
- Cost Explorer API may not be enabled
- Add `ce:GetCostAndUsage` permission to IAM role
- Use `--skip-cost` flag to skip this step
- Check costs manually in AWS Console

### Cleanup Removes Production Data

**Issue**: Concerned about accidentally deleting production data.

**Solution**:
- Always use `--dry-run` first
- Cleanup only removes data with `source="sample_data_generator"`
- Use environment-specific buckets
- Never run cleanup on prod without review

## Best Practices

### Development Testing

1. Use small datasets (1000-5000 records)
2. Run E2E tests after every deployment
3. Clean up test data regularly
4. Use `--seed` for reproducible tests

### Staging Testing

1. Use realistic data volumes (10k-100k records)
2. Run performance benchmarks
3. Test with time series data
4. Validate data quality thoroughly

### Production Testing

1. Use read-only tests only
2. Never generate sample data in production
3. Monitor costs during tests
4. Schedule tests during low-traffic periods

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Run E2E Tests
  run: |
    # Deploy to staging
    make deploy ENV=staging --no-approval
    
    # Generate test data
    make generate-data ENV=staging
    
    # Wait for data processing
    sleep 600
    
    # Run E2E tests
    python scripts/e2e_test_workflow.py \
      --env staging \
      --api-url ${{ secrets.STAGING_API_URL }} \
      --skip-ingestion \
      --output e2e-results.json
    
    # Upload results
    - uses: actions/upload-artifact@v2
      with:
        name: e2e-test-results
        path: e2e-results.json
```

## Performance Benchmarks

### Expected Metrics

**Kinesis Ingestion**:
- Throughput: 1000+ records/second
- Latency: < 100ms average

**API Performance**:
- Response time: < 500ms (p95)
- Throughput: 100+ RPS
- Error rate: < 1%

**Workflow Execution**:
- Duration: 5-15 minutes (depends on data volume)
- Success rate: > 99%

### Interpreting Results

Good performance:
- API p95 latency < 200ms
- API p99 latency < 500ms
- Kinesis write success rate > 99%
- Workflow completion < 10 minutes

Needs optimization:
- API p95 latency > 500ms
- API error rate > 5%
- Kinesis throttling errors
- Workflow duration > 20 minutes

## Cost Estimates

### Sample Data Generation

- 1000 records: < $0.01
- 10k records: < $0.05
- 100k records: < $0.50

### E2E Test Execution

- Complete test: $0.10 - $0.50
- With benchmark (60s): $0.20 - $0.75
- With benchmark (300s): $0.50 - $2.00

### Daily Testing

- Dev environment: $1-5/day
- Staging environment: $5-20/day
- Production testing: Minimal (read-only)

## Additional Resources

- [Integration Tests README](../tests/README.md)
- [Deployment Guide](../DEPLOYMENT.md)
- [Testing Guide](../TESTING.md)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Step Functions Best Practices](https://docs.aws.amazon.com/step-functions/latest/dg/best-practices.html)
