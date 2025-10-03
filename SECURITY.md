# Security Implementation

This document describes the security and IAM configurations implemented for the OpenSearch Trending Queries system.

## Overview

The security implementation follows AWS best practices for least-privilege access, encryption at rest and in transit, and defense in depth. All security configurations are centralized in the `SecurityConstruct` for easier management and auditing.

## Key Security Features

### 1. Encryption at Rest

All data is encrypted at rest using AWS KMS customer-managed keys with automatic key rotation enabled:

- **S3 Buckets**: All S3 buckets (raw data, processed data, query results) use KMS encryption
- **DynamoDB**: Trending queries table uses customer-managed KMS encryption
- **Kinesis Streams**: Data streams use KMS encryption for data at rest
- **CloudWatch Logs**: All log groups use KMS encryption

### 2. Encryption in Transit

All service communications use encrypted connections:

- **S3**: SSL/TLS enforcement via bucket policies (deny non-HTTPS requests)
- **API Gateway**: HTTPS-only endpoints
- **Kinesis**: Encrypted data streams
- **DynamoDB**: Encrypted connections by default

### 3. IAM Roles and Policies

All IAM roles follow the principle of least privilege:

#### Lambda Execution Roles

- **API Lambda Role**: Read-only access to DynamoDB, CloudWatch metrics, X-Ray tracing
- **Bedrock Lambda Role**: Bedrock model invocation, S3 read (processed data), DynamoDB write
- **Compression Lambda Role**: S3 read/write (raw data bucket only), KMS encrypt/decrypt

#### Service Roles

- **Glue Crawler Role**: S3 read access, Glue Data Catalog write access
- **Glue Job Role**: S3 read/write access, CloudWatch Logs write access
- **Step Functions Role**: Glue crawler/job start permissions, Lambda invoke permissions
- **Kinesis Producer Role**: Kinesis write permissions only
- **Firehose Delivery Role**: Kinesis read, S3 write, Glue Data Catalog read

### 4. Resource-Based Policies

S3 buckets have resource-based policies that:

- Deny unencrypted uploads (require KMS encryption)
- Deny insecure transport (require HTTPS)
- Block all public access

### 5. VPC Endpoints (Optional)

When VPC is enabled, private VPC endpoints are created for:

- S3 (Gateway endpoint)
- DynamoDB (Gateway endpoint)
- Lambda (Interface endpoint)
- Step Functions (Interface endpoint)
- Glue (Interface endpoint)
- Kinesis Streams (Interface endpoint)
- Kinesis Firehose (Interface endpoint)
- CloudWatch Logs (Interface endpoint)
- Bedrock Runtime (Interface endpoint)

This ensures all service communications remain within the AWS network without traversing the public internet.

### 6. API Security

API Gateway implements multiple security layers:

- **API Key Authentication**: Required for all API endpoints
- **Usage Plans**: Rate limiting and quota management
- **Request Validation**: Input validation for all requests
- **CORS Configuration**: Configurable allowed origins (restrictive in production)
- **CloudWatch Logging**: Full request/response logging for audit trails
- **X-Ray Tracing**: Distributed tracing for security analysis

### 7. Monitoring and Auditing

Security monitoring is enabled through:

- **CloudWatch Logs**: All service logs encrypted and retained
- **X-Ray Tracing**: Distributed tracing for Lambda and Step Functions
- **CloudWatch Metrics**: Custom metrics for security events
- **API Gateway Access Logs**: Full audit trail of API requests

## KMS Key Management

Four separate KMS keys are created for different purposes:

1. **S3 Encryption Key**: Used for all S3 bucket encryption
2. **DynamoDB Encryption Key**: Used for DynamoDB table encryption
3. **Kinesis Encryption Key**: Used for Kinesis stream encryption
4. **Logs Encryption Key**: Used for CloudWatch Logs encryption

All keys have:
- Automatic key rotation enabled
- Appropriate key policies for service access
- Aliases for easy identification
- Retention policies based on environment (destroy in dev, retain in prod)

## Security Best Practices Implemented

1. **Least Privilege**: All IAM roles have minimal permissions required for their function
2. **Defense in Depth**: Multiple layers of security controls
3. **Encryption Everywhere**: Data encrypted at rest and in transit
4. **Audit Logging**: Comprehensive logging for security analysis
5. **Network Isolation**: Optional VPC endpoints for private connectivity
6. **Key Rotation**: Automatic KMS key rotation
7. **Resource Policies**: Deny-by-default policies on S3 buckets
8. **Secure Defaults**: SSL enforcement, public access blocking

## Configuration

Security settings can be configured via the environment configuration:

```python
# Enable VPC endpoints for private service access
config.set("vpc", "enabled", True)
config.set("vpc", "vpc_id", "vpc-xxxxx")
config.set("vpc", "subnet_ids", ["subnet-xxxxx", "subnet-yyyyy"])
```

## Compliance Considerations

This implementation supports compliance with:

- **GDPR**: Encryption at rest and in transit, audit logging
- **HIPAA**: Encryption, access controls, audit trails
- **PCI DSS**: Network isolation, encryption, access controls
- **SOC 2**: Security controls, monitoring, audit logging

## Security Checklist

- [x] All data encrypted at rest with KMS
- [x] All data encrypted in transit (HTTPS/TLS)
- [x] Least-privilege IAM roles
- [x] Resource-based policies on S3
- [x] API authentication and authorization
- [x] CloudWatch logging enabled
- [x] X-Ray tracing enabled
- [x] KMS key rotation enabled
- [x] VPC endpoints support (optional)
- [x] Public access blocked on S3
- [x] SSL enforcement on S3
- [x] API rate limiting and quotas

## Future Enhancements

Potential security enhancements for future implementation:

1. **AWS WAF**: Web Application Firewall for API Gateway
2. **GuardDuty**: Threat detection for AWS accounts
3. **Security Hub**: Centralized security findings
4. **Config Rules**: Automated compliance checking
5. **Secrets Manager**: Secure storage for API keys and credentials
6. **CloudTrail**: API call logging for audit trails
7. **VPC Flow Logs**: Network traffic analysis
8. **AWS Shield**: DDoS protection for API endpoints
