# Testing Documentation

Comprehensive testing infrastructure for the OpenSearch Trending Queries system.

## Overview

This project includes a complete testing suite covering:
- Integration testing (end-to-end pipeline validation)
- Performance testing (load and throughput testing)
- Data quality validation (schema and integrity checks)
- Deployment validation (infrastructure verification)

## Quick Start

```bash
# Install dependencies
make install

# Deploy to dev
make deploy ENV=dev

# Run all tests
make test-all ENV=dev
```

## Test Suites

### 1. Integration Tests

**Location**: `scripts/run_integration_tests.py`

**Purpose**: Validate end-to-end functionality of the deployed system.

**Coverage**:
- ✓ Data ingestion through Kinesis
- ✓ API endpoints (GET /trending-queries, GET /trending-queries/{date})
- ✓ Lambda function health
- ✓ Step Functions state machine
- ✓ DynamoDB data presence
- ✓ S3 bucket accessibility

**Run**:
```bash
make test ENV=dev
python scripts/run_integration_tests.py --env dev
```

**Expected Output**:
```
=== Testing Data Ingestion ===
✓ PASS | Kinesis Put Record | Shard: shardId-000000000000, Sequence: 49...
✓ PASS | Kinesis Stream Status | Status: ACTIVE

=== Testing API Endpoints ===
✓ PASS | GET /trending-queries | Status: 200, Items: 0
✓ PASS | GET /trending-queries/2025-10-03 | No data for date (404 expected)

Results: 15/15 tests passed
```

### 2. Performance Tests

**Location**: `tests/performance_tests.py`

**Purpose**: Measure system performance under load.

**Metrics Collected**:
- Throughput (requests/records per second)
- Latency (avg, median, p95, p99, max)
- Error rates
- Status code distribution

**Run**:
```bash
# Standard test (60s, 10 RPS)
make test-performance ENV=dev

# Load test (300s, 50 RPS)
make test-performance-load ENV=staging

# Custom test
python tests/performance_tests.py --env dev --duration 120 --rps 25
```

**Expected Output**:
```
=== Testing Kinesis Throughput ===
Sending records to Kinesis for 60 seconds...
Completed: 600 records, 0 errors

=== Testing API Latency ===
Testing API for 60 seconds...
Completed: 600 successful, 0 errors

PERFORMANCE TEST RESULTS
Kinesis Throughput:
  Total Records:    600
  Errors:           0
  Actual RPS:       10.02
  Avg Latency:      45.23ms
  P95 Latency:      78.45ms
  P99 Latency:      95.12ms

API Latency:
  Total Requests:   600
  Successful:       598
  Errors:           2
  Actual RPS:       10.01
  Avg Latency:      125.34ms
  P95 Latency:      245.67ms
  P99 Latency:      389.23ms
```

### 3. Data Quality Tests

**Location**: `tests/data_quality_tests.py`

**Purpose**: Validate data integrity and schema compliance.

**Validations**:
- S3 data structure and partitioning
- DynamoDB schema compliance
- Required field presence
- Data freshness
- Glue catalog schemas

**Run**:
```bash
make test-data-quality ENV=dev
python tests/data_quality_tests.py --env dev
```

**Expected Output**:
```
=== Validating S3 Data Structure ===
✓ PASS | S3 Raw Data Partitioning | Partitions found: True, Prefixes: 4
✓ PASS | S3 Raw Data Files | Sample file: year=2025/month=10/day=03/data.json, Size: 1024 bytes

=== Validating DynamoDB Data ===
✓ PASS | DynamoDB Data Structure | Items: 5, Errors: 0
✓ PASS | DynamoDB Data Freshness | Latest date: 2025-10-03, Age: 0 days

Results: 12/12 validations passed
```

### 4. Deployment Validation

**Location**: `scripts/validate_deployment.py`

**Purpose**: Verify infrastructure is correctly deployed.

**Checks**:
- CloudFormation stack status
- S3 buckets (encryption, versioning)
- DynamoDB table (status, TTL)
- Kinesis stream (status, shards)
- Glue resources (database, crawler)
- Lambda functions (state, configuration)
- API Gateway (endpoints)
- Step Functions (state machine)

**Run**:
```bash
make validate ENV=dev
python scripts/validate_deployment.py --env dev
```

**Expected Output**:
```
VALIDATION RESULTS
✓ PASS | Stack Outputs | Retrieved 20 outputs
✓ PASS | S3 Bucket (raw-data) | Encryption: True, Versioning: True
✓ PASS | DynamoDB Table (trending-queries) | Status: ACTIVE, Billing: PAY_PER_REQUEST, TTL: True
✓ PASS | Kinesis Stream (search-logs) | Status: ACTIVE, Shards: 1, Retention: 24h
✓ PASS | Lambda (GetTrendingQueries) | State: Active, Runtime: python3.9, Memory: 512MB

Results: 25/25 checks passed
```

## Test Execution Workflow

### Development Workflow

```bash
# 1. Make code changes
# 2. Deploy to dev
make deploy-fast ENV=dev

# 3. Validate deployment
make validate ENV=dev

# 4. Run integration tests
make test ENV=dev

# 5. If tests pass, commit changes
git add .
git commit -m "Feature: description"
```

### Staging Workflow

```bash
# 1. Deploy to staging
make deploy ENV=staging

# 2. Validate deployment
make validate ENV=staging

# 3. Run all tests
make test-all ENV=staging

# 4. If all pass, proceed to production
```

### Production Workflow

```bash
# 1. Review changes
make diff ENV=prod PROFILE=production

# 2. Deploy to production
make deploy ENV=prod PROFILE=production

# 3. Validate deployment
make validate ENV=prod PROFILE=production

# 4. Run read-only tests
make test ENV=prod PROFILE=production

# 5. Monitor CloudWatch for 30 minutes
```

## CI/CD Integration

### Automated Testing Pipeline

```yaml
# .github/workflows/test.yml
name: Test Pipeline

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: make install
      
      - name: Deploy to staging
        run: make deploy-no-approval ENV=staging
      
      - name: Validate deployment
        run: make validate ENV=staging
      
      - name: Run integration tests
        run: make test ENV=staging
      
      - name: Run data quality tests
        run: make test-data-quality ENV=staging
      
      - name: Run performance tests
        run: make test-performance ENV=staging
```

## Test Data Generation

### Generate Sample Data

```python
import boto3
import json
import random
from datetime import datetime

kinesis = boto3.client('kinesis')
stream_name = 'your-kinesis-stream-name'

queries = [
    "machine learning tutorial",
    "python programming",
    "aws cloud services",
    "data science course",
    "web development"
]

# Generate 1000 test records
for i in range(1000):
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": f"user_{i % 100}",
        "session_id": f"session_{i}",
        "query": random.choice(queries),
        "results_count": random.randint(0, 500),
        "click_through": random.choice([True, False]),
        "source": "test_data"
    }
    
    kinesis.put_record(
        StreamName=stream_name,
        Data=json.dumps(record),
        PartitionKey=record["user_id"]
    )
    
    if i % 100 == 0:
        print(f"Sent {i} records...")

print("Test data generation complete!")
```

## Performance Benchmarks

### Expected Performance (by Environment)

#### Development
- Kinesis Throughput: 10-50 RPS
- API Latency (p95): < 500ms
- Lambda Cold Start: < 3s
- Lambda Warm: < 200ms

#### Staging
- Kinesis Throughput: 50-200 RPS
- API Latency (p95): < 300ms
- Lambda Cold Start: < 2s
- Lambda Warm: < 150ms

#### Production
- Kinesis Throughput: 200-1000 RPS
- API Latency (p95): < 200ms
- Lambda Cold Start: < 2s
- Lambda Warm: < 100ms

## Troubleshooting Tests

### Integration Tests Fail

**Issue**: Tests fail with "Stack not found"
```bash
# Solution: Deploy the stack first
make deploy ENV=dev
```

**Issue**: API returns 404
```bash
# Solution: This is expected if no data exists yet
# Generate test data or run the Step Functions workflow
```

**Issue**: Kinesis throttling errors
```bash
# Solution: Increase shard count or reduce test RPS
# Edit environment_config.py and redeploy
```

### Performance Tests Show High Latency

**Issue**: Lambda cold starts affecting results
```bash
# Solution: Run a warm-up phase before measuring
# Or increase Lambda memory to reduce cold start time
```

**Issue**: DynamoDB throttling
```bash
# Solution: Check CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name UserErrors \
  --dimensions Name=TableName,Value=<table-name> \
  --start-time 2025-10-03T00:00:00Z \
  --end-time 2025-10-03T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

### Data Quality Tests Fail

**Issue**: Missing required fields
```bash
# Solution: Check data ingestion format
# Verify Kinesis records match expected schema
```

**Issue**: Data not fresh
```bash
# Solution: Check Step Functions execution
aws stepfunctions list-executions \
  --state-machine-arn <state-machine-arn> \
  --max-results 10
```

## Monitoring During Tests

### CloudWatch Metrics to Watch

```bash
# Lambda errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=<function-name> \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# API Gateway latency
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Latency \
  --dimensions Name=ApiName,Value=<api-name> \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

### X-Ray Traces

```bash
# Get trace summaries
aws xray get-trace-summaries \
  --start-time $(date -u -d '1 hour ago' +%s) \
  --end-time $(date -u +%s) \
  --filter-expression 'service("opensearch-trending-queries")'
```

## Best Practices

1. **Test After Every Deployment**: Always run tests after deploying
2. **Baseline Performance**: Establish performance baselines in each environment
3. **Monitor During Tests**: Watch CloudWatch metrics during performance tests
4. **Clean Up Test Data**: Remove test data after tests complete
5. **Document Failures**: Record test failures and resolutions
6. **Automate in CI/CD**: Run tests automatically in pipelines
7. **Test Rollback**: Periodically test rollback procedures
8. **Security Testing**: Include security validation in test suite

## Additional Resources

- **Deployment Guide**: See DEPLOYMENT.md for deployment procedures
- **Monitoring Guide**: See MONITORING.md for observability setup
- **Security Guide**: See SECURITY.md for security best practices
- **Test Scripts**: See tests/README.md for detailed test documentation
- **Deployment Scripts**: See scripts/README.md for deployment script usage
