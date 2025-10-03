# Monitoring and Observability Guide

This document provides detailed information about the monitoring and observability features implemented in the OpenSearch Trending Queries system.

## Overview

The system includes comprehensive monitoring using:
- **CloudWatch Dashboards**: Unified view of system health
- **CloudWatch Alarms**: Proactive alerting for critical issues
- **AWS X-Ray**: Distributed tracing for debugging and performance analysis

## CloudWatch Dashboard

### Accessing the Dashboard

1. Navigate to AWS Console > CloudWatch > Dashboards
2. Select the dashboard named `opensearch-trending-{env}-dashboard`
3. The dashboard displays real-time metrics across all system components

### Dashboard Widgets

#### Kinesis Metrics
- **Incoming Records**: Number of records ingested per 5-minute period
- **Incoming Bytes**: Volume of data ingested
- **Iterator Age**: Lag in processing (should be low)

#### Step Functions Metrics
- **Executions**: Started, succeeded, failed, and timed-out executions
- **Duration**: Average and maximum execution time

#### API Gateway Metrics
- **Requests**: Total API requests per 5-minute period
- **Errors**: 4XX (client errors) and 5XX (server errors)
- **Latency**: Average and P99 response times

#### Lambda Metrics
- **Invocations**: Function invocation counts by function
- **Errors**: Error counts by function
- **Duration**: Average execution time by function

#### DynamoDB Metrics
- **Consumed Capacity**: Read and write capacity units consumed
- **Throttled Requests**: User errors and system errors

#### Glue Job Metrics
- **Job Status**: Completed tasks by job

## CloudWatch Alarms

### Configured Alarms

#### Step Functions Alarms
1. **Workflow Failures**
   - Threshold: ≥1 failure in 5 minutes
   - Action: SNS notification
   - Description: Alerts when the daily workflow fails

2. **Workflow Timeouts**
   - Threshold: ≥1 timeout in 5 minutes
   - Action: SNS notification
   - Description: Alerts when workflow exceeds 2-hour timeout

#### API Gateway Alarms
1. **High 5XX Error Rate**
   - Threshold: ≥10 errors in 10 minutes (2 evaluation periods)
   - Action: SNS notification
   - Description: Alerts on server-side errors

2. **High 4XX Error Rate**
   - Threshold: ≥50 errors in 10 minutes (2 evaluation periods)
   - Action: SNS notification
   - Description: Alerts on client-side errors

3. **High Latency**
   - Threshold: P99 latency ≥3000ms for 15 minutes (3 evaluation periods)
   - Action: SNS notification
   - Description: Alerts on slow API responses

#### Lambda Alarms
For each Lambda function:
1. **Function Errors**
   - Threshold: ≥5 errors in 10 minutes (2 evaluation periods)
   - Action: SNS notification
   - Description: Alerts on Lambda execution errors

2. **Function Throttling**
   - Threshold: ≥10 throttles in 10 minutes (2 evaluation periods)
   - Action: SNS notification
   - Description: Alerts when Lambda is throttled

#### DynamoDB Alarms
1. **User Errors (Throttling)**
   - Threshold: ≥10 errors in 10 minutes (2 evaluation periods)
   - Action: SNS notification
   - Description: Alerts on DynamoDB throttling

2. **System Errors**
   - Threshold: ≥5 errors in 10 minutes (2 evaluation periods)
   - Action: SNS notification
   - Description: Alerts on DynamoDB system errors

### Configuring Alert Email

To receive alarm notifications, configure the alert email in the environment config:

```python
# In opensearch_trending_queries/config/environment_config.py
"monitoring": {
    "alert_email": "your-team@example.com"
}
```

After deployment, confirm the SNS subscription by clicking the link in the confirmation email.

## AWS X-Ray Tracing

### Overview

X-Ray provides distributed tracing across the entire system, allowing you to:
- Visualize request flow through services
- Identify performance bottlenecks
- Debug errors with detailed trace data
- Analyze service dependencies

### Enabled Components

#### API Gateway
- Full request tracing from client to backend
- Automatic integration with downstream Lambda functions
- Trace ID propagation through the request chain

#### Lambda Functions
All Lambda functions have X-Ray tracing enabled:
- `get_trending_queries`: API endpoint for current trending queries
- `get_trending_queries_by_date`: API endpoint for historical queries
- `bedrock_classification`: Bedrock LLM classification
- `log_compression`: S3 log compression

#### Step Functions
- Workflow execution tracing
- Integration with Lambda and Glue service calls
- State transition tracking

#### AWS SDK Calls
Automatic instrumentation for:
- DynamoDB queries and scans
- S3 object operations
- Bedrock model invocations
- CloudWatch metrics

### Custom Trace Segments

Lambda functions include custom subsegments for detailed tracing:

#### API Lambda Functions
- `parse_parameters`: Request parameter parsing and validation
- `query_dynamodb`: DynamoDB query execution
- `format_response`: Response formatting

#### Bedrock Classification Lambda
- `parse_event`: Event parsing
- `read_s3_data`: S3 data retrieval
- `group_by_cluster`: Query clustering
- `bedrock_classification`: Bedrock API calls
- `calculate_metrics`: Metrics calculation
- `store_results`: DynamoDB write operations

### Viewing Traces

#### X-Ray Console
1. Navigate to AWS Console > X-Ray > Traces
2. Filter traces by:
   - Time range
   - HTTP status code
   - Annotations (e.g., `query_date`)
   - Response time
3. Click on a trace to view detailed timeline

#### Service Map
1. Navigate to AWS Console > X-Ray > Service Map
2. View visual representation of:
   - Service dependencies
   - Request flow
   - Error rates by service
   - Average latency per service

#### Trace Analysis
1. Navigate to AWS Console > X-Ray > Analytics
2. Create custom queries to analyze:
   - Response time distribution
   - Error patterns
   - Service performance trends

### Custom Annotations and Metadata

#### Annotations (Indexed)
- `query_date`: Date being queried
- `target_date`: Date being processed

#### Metadata (Not Indexed)
- `limit`: Query limit parameter
- `items_returned`: Number of items returned
- `queries_count`: Number of queries processed
- `cluster_count`: Number of clusters
- `classified_count`: Number of classified queries

### Troubleshooting with X-Ray

#### High Latency
1. Open the trace with high latency
2. Identify the subsegment with the longest duration
3. Check for:
   - Slow DynamoDB queries (add indexes if needed)
   - Bedrock API throttling (implement backoff)
   - Large S3 objects (optimize data size)

#### Errors
1. Filter traces by error status
2. View exception details in the trace
3. Check subsegment where error occurred
4. Review CloudWatch Logs for detailed error messages

#### Throttling
1. Look for throttling errors in traces
2. Check service quotas in Service Quotas console
3. Implement exponential backoff in code
4. Request quota increases if needed

## Best Practices

### Monitoring
1. **Review dashboards daily** to identify trends
2. **Set up alarm notifications** to appropriate channels (email, Slack, PagerDuty)
3. **Adjust alarm thresholds** based on actual traffic patterns
4. **Create custom dashboards** for specific use cases

### Tracing
1. **Use annotations** for filterable data (dates, IDs)
2. **Use metadata** for detailed context (counts, configurations)
3. **Keep subsegments focused** on specific operations
4. **Review traces regularly** to identify optimization opportunities

### Cost Optimization
1. **X-Ray sampling**: Default sampling is 1 request per second + 5% of additional requests
2. **Log retention**: Logs are retained for 2 weeks (configurable)
3. **Dashboard refresh**: Set appropriate refresh intervals
4. **Alarm evaluation**: Use appropriate evaluation periods to reduce false positives

## Metrics Reference

### Custom Metrics
The system publishes custom CloudWatch metrics:

#### Namespace: `OpenSearchTrendingQueries`
- `ProcessedQueries`: Number of queries processed
- `ClusterCount`: Number of clusters identified
- `ClassificationLatency`: Time to classify queries
- `CompressionRatio`: Compression ratio achieved

### AWS Service Metrics
Standard AWS service metrics are automatically collected:
- Kinesis: `IncomingRecords`, `IncomingBytes`, `GetRecords.IteratorAgeMilliseconds`
- Lambda: `Invocations`, `Errors`, `Duration`, `Throttles`
- DynamoDB: `ConsumedReadCapacityUnits`, `ConsumedWriteCapacityUnits`, `UserErrors`
- API Gateway: `Count`, `4XXError`, `5XXError`, `Latency`
- Step Functions: `ExecutionsStarted`, `ExecutionsSucceeded`, `ExecutionsFailed`

## Additional Resources

- [AWS CloudWatch Documentation](https://docs.aws.amazon.com/cloudwatch/)
- [AWS X-Ray Documentation](https://docs.aws.amazon.com/xray/)
- [CloudWatch Alarms Best Practices](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Best_Practice_Recommended_Alarms_AWS_Services.html)
- [X-Ray SDK for Python](https://docs.aws.amazon.com/xray-sdk-for-python/latest/reference/)
