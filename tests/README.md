# Integration and Performance Tests

This directory contains integration tests, performance tests, and data quality validation tests for the OpenSearch Trending Queries system.

## Test Suites

### 1. Integration Tests (`run_integration_tests.py`)

End-to-end tests that validate the complete data pipeline and API functionality.

**What it tests:**
- Data ingestion through Kinesis
- API endpoints (GET /trending-queries, GET /trending-queries/{date})
- Lambda function health and configuration
- Step Functions state machine
- Data quality in DynamoDB and S3

**Usage:**
```bash
# Run integration tests
python scripts/run_integration_tests.py --env dev

# With specific region and profile
python scripts/run_integration_tests.py --env prod --region us-west-2 --profile production

# Using Makefile
make test ENV=dev
```

**Expected Results:**
- All Lambda functions should be in "Active" state
- API endpoints should return 200 or 404 (if no data yet)
- Kinesis stream should accept records successfully
- Step Functions state machine should be "ACTIVE"

### 2. Performance Tests (`performance_tests.py`)

Load and performance tests that measure system throughput and latency under various conditions.

**What it tests:**
- Kinesis ingestion throughput (records per second)
- Kinesis write latency (avg, median, p95, p99, max)
- API endpoint latency under load
- API throughput (requests per second)

**Usage:**
```bash
# Run with default settings (60s duration, 10 RPS)
python tests/performance_tests.py --env dev

# Custom duration and load
python tests/performance_tests.py --env staging --duration 300 --rps 50

# High load test
python tests/performance_tests.py --env prod --duration 600 --rps 100 --profile production
```

**Interpreting Results:**
- **Kinesis Throughput**: Should handle target RPS with low error rate
- **Latency Metrics**:
  - Avg latency: < 100ms is good
  - P95 latency: < 200ms is acceptable
  - P99 latency: < 500ms is acceptable
- **API Performance**: Should maintain < 500ms response time under load

### 3. Data Quality Tests (`data_quality_tests.py`)

Validates data integrity and quality throughout the pipeline.

**What it tests:**
- S3 data structure and partitioning
- DynamoDB data schema and completeness
- Glue catalog table schemas
- Data freshness (age of most recent data)
- Required field presence
- Data format validation

**Usage:**
```bash
# Run data quality validations
python tests/data_quality_tests.py --env dev

# With specific region and profile
python tests/data_quality_tests.py --env prod --region us-west-2 --profile production
```

**Expected Results:**
- S3 data should follow year/month/day/hour partitioning
- DynamoDB items should have required fields (date, trending_queries)
- Glue tables should have defined schemas
- Data should be fresh (< 24 hours old for active systems)

## Running All Tests

### Sequential Execution
```bash
# Run all test suites
python scripts/run_integration_tests.py --env dev
python tests/performance_tests.py --env dev --duration 60 --rps 10
python tests/data_quality_tests.py --env dev
```

### Using Makefile
```bash
# Integration tests
make test ENV=dev

# Add performance and data quality tests to Makefile as needed
```

## Test Environments

### Development (dev)
- Use for rapid iteration and testing
- Lower resource limits
- Safe for destructive tests
- Can use `--hotswap` for faster deployments

### Staging (staging)
- Production-like environment
- Full integration and performance testing
- Validate before production deployment
- Test with realistic data volumes

### Production (prod)
- Run read-only tests only
- Monitor performance metrics
- Validate after deployments
- Use with caution for load tests

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Integration Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Deploy to staging
        run: |
          python scripts/deploy.py deploy --env staging --no-approval
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      
      - name: Run integration tests
        run: |
          python scripts/run_integration_tests.py --env staging
      
      - name: Run data quality tests
        run: |
          python tests/data_quality_tests.py --env staging
      
      - name: Run performance tests
        run: |
          python tests/performance_tests.py --env staging --duration 60 --rps 10
```

## Test Data Generation

### Sample Data Generator (`scripts/generate_sample_data.py`)

Automated utility for generating realistic search query logs for testing.

**Features:**
- Generate realistic search queries with proper distribution
- Ingest data to Kinesis or S3
- Validate data ingestion
- Clean up test data
- Time series data generation

**Usage:**
```bash
# Generate 1000 sample records
python scripts/generate_sample_data.py --env dev --count 1000

# Generate time series data (24 hours, 500 queries/hour)
python scripts/generate_sample_data.py --env dev --hours 24 --queries-per-hour 500

# Generate and validate
python scripts/generate_sample_data.py --env dev --count 1000 --validate

# Direct S3 upload (bypass Kinesis)
python scripts/generate_sample_data.py --env dev --count 1000 --s3-bucket my-bucket

# Clean up test data
python scripts/generate_sample_data.py --env dev --cleanup --dry-run
python scripts/generate_sample_data.py --env dev --cleanup

# Using Makefile
make generate-data ENV=dev
make generate-data-large ENV=dev
make cleanup-data ENV=dev
```

### End-to-End Test Workflow (`scripts/e2e_test_workflow.py`)

Complete pipeline testing from data ingestion to API verification.

**Features:**
- Automated data generation and ingestion
- Workflow execution and monitoring
- Result verification in DynamoDB
- API endpoint testing
- Performance benchmarking
- Cost monitoring and reporting

**Usage:**
```bash
# Full end-to-end test
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com

# Skip specific steps
python scripts/e2e_test_workflow.py --env dev --skip-ingestion --skip-workflow

# Custom benchmark settings
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com \
  --benchmark-duration 300 --benchmark-rps 50

# Save detailed report
python scripts/e2e_test_workflow.py --env dev --api-url https://api.example.com \
  --output e2e-test-results.json

# Using Makefile
make test-e2e ENV=dev
```

**Test Steps:**
1. Data Ingestion: Generate and ingest sample data to Kinesis
2. Workflow Execution: Trigger Step Functions workflow
3. Result Verification: Validate trending queries in DynamoDB
4. API Testing: Test GET endpoints
5. Performance Benchmark: Load test API endpoints
6. Cost Monitoring: Report costs by service

## Monitoring Test Results

### CloudWatch Metrics
Monitor these metrics during tests:
- Kinesis: IncomingRecords, WriteProvisionedThroughputExceeded
- Lambda: Invocations, Errors, Duration, Throttles
- API Gateway: Count, Latency, 4XXError, 5XXError
- DynamoDB: ConsumedReadCapacityUnits, ConsumedWriteCapacityUnits

### X-Ray Traces
Use AWS X-Ray to trace requests through the system:
```bash
# View traces in AWS Console
aws xray get-trace-summaries --start-time <timestamp> --end-time <timestamp>
```

## Troubleshooting

### Tests Fail with "Stack not found"
- Ensure the stack is deployed: `make deploy ENV=dev`
- Check stack name matches environment

### Kinesis Tests Fail with Throttling
- Increase shard count in environment config
- Reduce test RPS
- Check Kinesis metrics in CloudWatch

### API Tests Return 404
- Normal for new deployments with no data
- Run Step Functions workflow to generate data
- Check DynamoDB table for data

### Performance Tests Show High Latency
- Check CloudWatch metrics for bottlenecks
- Review Lambda function memory/timeout settings
- Check DynamoDB capacity settings
- Review API Gateway throttling limits

## Best Practices

1. **Run tests after every deployment** to catch issues early
2. **Baseline performance metrics** in dev/staging before production
3. **Monitor CloudWatch** during performance tests
4. **Use realistic data volumes** in staging
5. **Clean up test data** after tests complete
6. **Document test failures** and resolutions
7. **Automate tests** in CI/CD pipeline
8. **Set up alerts** for test failures in production

## Test Coverage

Current test coverage includes:
- ✓ Data ingestion (Kinesis)
- ✓ API endpoints
- ✓ Lambda functions
- ✓ Step Functions
- ✓ Data quality
- ✓ Performance/load testing
- ✓ S3 data structure
- ✓ DynamoDB data validation
- ✓ Glue catalog validation

## Future Enhancements

Potential additions:
- End-to-end workflow tests (full pipeline execution)
- Chaos engineering tests (failure injection)
- Security tests (IAM, encryption validation)
- Cost optimization tests
- Multi-region tests
- Disaster recovery tests
