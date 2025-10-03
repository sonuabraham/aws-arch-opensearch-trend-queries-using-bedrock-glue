# OpenSearch Trending Queries Architecture

This project implements an AWS architecture for identifying and analyzing trending search queries using Amazon OpenSearch Service, AWS Glue, Amazon Bedrock, and other AWS services.

## Architecture Overview

The system processes search query logs through a comprehensive data pipeline that includes:

- **Data Ingestion**: Amazon Kinesis Data Streams for real-time log ingestion
- **Storage**: Amazon S3 data lake with lifecycle policies
- **Processing**: AWS Glue for ETL and data cataloging
- **Analytics**: K-means clustering and Amazon Bedrock for query classification
- **Orchestration**: AWS Step Functions for workflow management
- **API**: Amazon API Gateway and Lambda for data access
- **Monitoring**: CloudWatch dashboards and X-Ray tracing

## Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.8 or later
- Node.js 14.x or later (for CDK CLI)
- AWS CDK CLI installed (`npm install -g aws-cdk`)

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Bootstrap CDK** (first time only):
   ```bash
   cdk bootstrap
   ```

3. **Deploy the stack**:
   ```bash
   # Deploy to development environment
   cdk deploy --context env=dev
   
   # Deploy to production environment
   cdk deploy --context env=prod
   ```

## Project Structure

```
├── app.py                          # CDK app entry point
├── cdk.json                        # CDK configuration
├── requirements.txt                # Python dependencies
├── opensearch_trending_queries/    # Main package
│   ├── config/                     # Environment configuration
│   ├── constructs/                 # CDK constructs
│   └── lambda/                     # Lambda function code
└── tests/                          # Test files
```

## Environment Configuration

The system supports multiple environments (dev, staging, prod) with different configurations:

- **Development**: Minimal resources for testing
- **Staging**: Production-like setup for validation
- **Production**: Full-scale deployment with high availability

## Deployment Commands

```bash
# Synthesize CloudFormation template
cdk synth

# Deploy with specific environment
cdk deploy --context env=dev

# Destroy stack
cdk destroy --context env=dev
```

## Monitoring

The system includes comprehensive monitoring with:

### CloudWatch Dashboards

The monitoring construct creates a unified dashboard that displays:

- **Kinesis Metrics**: Incoming records, bytes, and iterator age
- **Step Functions Metrics**: Execution status, duration, and failures
- **API Gateway Metrics**: Request count, error rates (4XX/5XX), and latency
- **Lambda Metrics**: Invocations, errors, duration, and throttles
- **DynamoDB Metrics**: Consumed capacity and throttled requests
- **Glue Job Metrics**: Job status and completion metrics

Access the dashboard in the AWS Console under CloudWatch > Dashboards.

### CloudWatch Alarms

Critical alarms are configured for:

- Step Functions workflow failures and timeouts
- API Gateway high error rates (4XX/5XX) and latency
- Lambda function errors and throttling
- DynamoDB throttling and system errors

All alarms send notifications to an SNS topic. Configure the alert email in the environment config:

```python
"monitoring": {
    "alert_email": "your-email@example.com"
}
```

### AWS X-Ray Tracing

X-Ray distributed tracing is enabled for:

- **API Gateway**: Full request tracing from client to backend
- **Lambda Functions**: Automatic instrumentation with custom subsegments
- **Step Functions**: Workflow execution tracing
- **AWS SDK Calls**: DynamoDB, S3, Bedrock, and other service calls

#### Custom Trace Segments

Lambda functions include custom subsegments for business logic:

- Parameter parsing and validation
- DynamoDB queries
- Response formatting
- Bedrock API calls
- S3 data retrieval

View traces in the AWS Console under X-Ray > Traces or X-Ray > Service Map.

#### X-Ray Service Map

The service map provides a visual representation of:
- Request flow through the system
- Service dependencies
- Latency at each hop
- Error rates by service

### Cost Monitoring

Monitor costs using:
- AWS Cost Explorer
- CloudWatch billing alarms
- Resource tagging for cost allocation

## Security

- All data encrypted at rest and in transit
- Least-privilege IAM roles and policies
- VPC endpoints for private service access
- API authentication and rate limiting

## Contributing

1. Follow the implementation tasks in `.kiro/specs/opensearch-trending-queries/tasks.md`
2. Implement one task at a time
3. Test changes in development environment
4. Update documentation as needed