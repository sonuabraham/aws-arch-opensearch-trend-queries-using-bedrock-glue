"""
Security Construct - Centralized IAM roles, policies, and security controls
"""
from aws_cdk import (
    aws_iam as iam,
    aws_kms as kms,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_ec2 as ec2,
    RemovalPolicy,
    Stack,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig
from typing import List, Dict, Optional


class SecurityConstruct(Construct):
    """Construct for centralized security and IAM configurations"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig,
        raw_data_bucket: Optional[s3.Bucket] = None,
        processed_data_bucket: Optional[s3.Bucket] = None,
        query_results_bucket: Optional[s3.Bucket] = None,
        trending_queries_table: Optional[dynamodb.Table] = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.raw_data_bucket = raw_data_bucket
        self.processed_data_bucket = processed_data_bucket
        self.query_results_bucket = query_results_bucket
        self.trending_queries_table = trending_queries_table
        
        # Create KMS keys for encryption
        self._create_kms_keys()
        
        # Create service roles with least-privilege policies
        self._create_lambda_execution_roles()
        self._create_glue_service_roles()
        self._create_step_functions_role()
        self._create_api_gateway_role()
        self._create_kinesis_roles()
        
        # Create resource-based policies
        self._configure_resource_policies()
        
        # Create VPC endpoints for private service access (if VPC is configured)
        if self.config.get("vpc", "enabled", default=False):
            self._create_vpc_endpoints()
    
    def _create_kms_keys(self) -> None:
        """Create KMS keys for encryption at rest"""
        
        # KMS key for S3 bucket encryption
        self.s3_kms_key = kms.Key(
            self, "S3EncryptionKey",
            description=f"KMS key for {self.config.resource_prefix} S3 bucket encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY if not self.config.is_production else RemovalPolicy.RETAIN,
            alias=f"alias/{self.config.resource_prefix}-s3"
        )
        
        # KMS key for DynamoDB encryption
        self.dynamodb_kms_key = kms.Key(
            self, "DynamoDBEncryptionKey",
            description=f"KMS key for {self.config.resource_prefix} DynamoDB encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY if not self.config.is_production else RemovalPolicy.RETAIN,
            alias=f"alias/{self.config.resource_prefix}-dynamodb"
        )
        
        # KMS key for Kinesis encryption
        self.kinesis_kms_key = kms.Key(
            self, "KinesisEncryptionKey",
            description=f"KMS key for {self.config.resource_prefix} Kinesis stream encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY if not self.config.is_production else RemovalPolicy.RETAIN,
            alias=f"alias/{self.config.resource_prefix}-kinesis"
        )
        
        # KMS key for CloudWatch Logs encryption
        self.logs_kms_key = kms.Key(
            self, "LogsEncryptionKey",
            description=f"KMS key for {self.config.resource_prefix} CloudWatch Logs encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY if not self.config.is_production else RemovalPolicy.RETAIN,
            alias=f"alias/{self.config.resource_prefix}-logs"
        )
        
        # Grant CloudWatch Logs service permission to use the key
        self.logs_kms_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowCloudWatchLogs",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal(f"logs.{Stack.of(self).region}.amazonaws.com")],
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:CreateGrant",
                    "kms:DescribeKey"
                ],
                resources=["*"],
                conditions={
                    "ArnLike": {
                        "kms:EncryptionContext:aws:logs:arn": f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:*"
                    }
                }
            )
        )

    
    def _create_lambda_execution_roles(self) -> None:
        """Create least-privilege IAM roles for Lambda functions"""
        
        # Base Lambda execution role with CloudWatch Logs permissions
        base_lambda_policy = iam.ManagedPolicy.from_aws_managed_policy_name(
            "service-role/AWSLambdaBasicExecutionRole"
        )
        
        # Role for API Lambda functions (read-only DynamoDB access)
        self.api_lambda_role = iam.Role(
            self, "ApiLambdaRole",
            role_name=f"{self.config.resource_prefix}-api-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least-privilege role for API Lambda functions",
            managed_policies=[base_lambda_policy]
        )
        
        # Grant specific DynamoDB read permissions
        if self.trending_queries_table:
            self.api_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    sid="DynamoDBReadAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:Query",
                        "dynamodb:Scan"
                    ],
                    resources=[
                        self.trending_queries_table.table_arn,
                        f"{self.trending_queries_table.table_arn}/index/*"
                    ]
                )
            )
        
        # Grant X-Ray tracing permissions
        self.api_lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayTracingAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords"
                ],
                resources=["*"]
            )
        )
        
        # Grant CloudWatch metrics permissions
        self.api_lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchMetricsAccess",
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": f"{self.config.resource_prefix}/API"
                    }
                }
            )
        )
        
        # Role for Bedrock classification Lambda
        self.bedrock_lambda_role = iam.Role(
            self, "BedrockLambdaRole",
            role_name=f"{self.config.resource_prefix}-bedrock-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least-privilege role for Bedrock classification Lambda",
            managed_policies=[base_lambda_policy]
        )
        
        # Grant Bedrock model invocation permissions
        self.bedrock_lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockModelAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    f"arn:aws:bedrock:{Stack.of(self).region}::foundation-model/*"
                ]
            )
        )
        
        # Grant S3 read access to processed data
        if self.processed_data_bucket:
            self.bedrock_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3ReadAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:ListBucket"
                    ],
                    resources=[
                        self.processed_data_bucket.bucket_arn,
                        f"{self.processed_data_bucket.bucket_arn}/*"
                    ]
                )
            )
        
        # Grant DynamoDB write access
        if self.trending_queries_table:
            self.bedrock_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    sid="DynamoDBWriteAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:BatchWriteItem"
                    ],
                    resources=[self.trending_queries_table.table_arn]
                )
            )
        
        # Grant X-Ray tracing permissions
        self.bedrock_lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayTracingAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords"
                ],
                resources=["*"]
            )
        )
        
        # Role for log compression Lambda
        self.compression_lambda_role = iam.Role(
            self, "CompressionLambdaRole",
            role_name=f"{self.config.resource_prefix}-compression-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least-privilege role for log compression Lambda",
            managed_policies=[base_lambda_policy]
        )
        
        # Grant S3 read/write access to raw data bucket
        if self.raw_data_bucket:
            self.compression_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3ReadWriteAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject"
                    ],
                    resources=[f"{self.raw_data_bucket.bucket_arn}/*"]
                )
            )
            
            self.compression_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3ListAccess",
                    effect=iam.Effect.ALLOW,
                    actions=["s3:ListBucket"],
                    resources=[self.raw_data_bucket.bucket_arn]
                )
            )
        
        # Grant KMS permissions for S3 encryption
        if self.s3_kms_key:
            self.s3_kms_key.grant_encrypt_decrypt(self.compression_lambda_role)
    
    def _create_glue_service_roles(self) -> None:
        """Create least-privilege IAM roles for Glue services"""
        
        # Role for Glue Crawler
        self.glue_crawler_role = iam.Role(
            self, "GlueCrawlerRole",
            role_name=f"{self.config.resource_prefix}-glue-crawler",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            description="Least-privilege role for Glue crawler",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
            ]
        )
        
        # Grant S3 read access to raw data
        if self.raw_data_bucket:
            self.glue_crawler_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3RawDataReadAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:ListBucket"
                    ],
                    resources=[
                        self.raw_data_bucket.bucket_arn,
                        f"{self.raw_data_bucket.bucket_arn}/*"
                    ]
                )
            )
        
        # Grant S3 read/write access to processed data
        if self.processed_data_bucket:
            self.glue_crawler_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3ProcessedDataAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:ListBucket"
                    ],
                    resources=[
                        self.processed_data_bucket.bucket_arn,
                        f"{self.processed_data_bucket.bucket_arn}/*"
                    ]
                )
            )
        
        # Grant KMS permissions
        if self.s3_kms_key:
            self.s3_kms_key.grant_decrypt(self.glue_crawler_role)
        
        # Role for Glue ETL Jobs
        self.glue_job_role = iam.Role(
            self, "GlueJobRole",
            role_name=f"{self.config.resource_prefix}-glue-job",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            description="Least-privilege role for Glue ETL jobs",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
            ]
        )
        
        # Grant S3 read access to raw data
        if self.raw_data_bucket:
            self.glue_job_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3RawDataReadAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:ListBucket"
                    ],
                    resources=[
                        self.raw_data_bucket.bucket_arn,
                        f"{self.raw_data_bucket.bucket_arn}/*"
                    ]
                )
            )
        
        # Grant S3 read/write access to processed data
        if self.processed_data_bucket:
            self.glue_job_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3ProcessedDataAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket"
                    ],
                    resources=[
                        self.processed_data_bucket.bucket_arn,
                        f"{self.processed_data_bucket.bucket_arn}/*"
                    ]
                )
            )
        
        # Grant KMS permissions
        if self.s3_kms_key:
            self.s3_kms_key.grant_encrypt_decrypt(self.glue_job_role)
        
        # Grant CloudWatch Logs permissions
        self.glue_job_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchLogsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=[
                    f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:/aws-glue/*"
                ]
            )
        )

    
    def _create_step_functions_role(self) -> None:
        """Create least-privilege IAM role for Step Functions"""
        
        self.step_functions_role = iam.Role(
            self, "StepFunctionsRole",
            role_name=f"{self.config.resource_prefix}-stepfunctions",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            description="Least-privilege role for Step Functions workflow orchestration"
        )
        
        # Grant permissions to start Glue crawler
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                sid="GlueCrawlerAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "glue:StartCrawler",
                    "glue:GetCrawler"
                ],
                resources=[
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:crawler/{self.config.resource_prefix}-*"
                ]
            )
        )
        
        # Grant permissions to start Glue jobs
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                sid="GlueJobAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "glue:StartJobRun",
                    "glue:GetJobRun",
                    "glue:GetJobRuns",
                    "glue:BatchStopJobRun"
                ],
                resources=[
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:job/{self.config.resource_prefix}-*"
                ]
            )
        )
        
        # Grant permissions to invoke Lambda functions
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                sid="LambdaInvokeAccess",
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{Stack.of(self).region}:{Stack.of(self).account}:function:{self.config.resource_prefix}-*"
                ]
            )
        )
        
        # Grant CloudWatch Logs permissions
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchLogsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogDelivery",
                    "logs:GetLogDelivery",
                    "logs:UpdateLogDelivery",
                    "logs:DeleteLogDelivery",
                    "logs:ListLogDeliveries",
                    "logs:PutResourcePolicy",
                    "logs:DescribeResourcePolicies",
                    "logs:DescribeLogGroups"
                ],
                resources=["*"]
            )
        )
        
        # Grant X-Ray tracing permissions
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayTracingAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets"
                ],
                resources=["*"]
            )
        )
    
    def _create_api_gateway_role(self) -> None:
        """Create IAM role for API Gateway CloudWatch logging"""
        
        self.api_gateway_role = iam.Role(
            self, "ApiGatewayRole",
            role_name=f"{self.config.resource_prefix}-apigateway",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            description="Role for API Gateway to write logs to CloudWatch",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ]
        )
    
    def _create_kinesis_roles(self) -> None:
        """Create IAM roles for Kinesis data ingestion"""
        
        # Role for applications to write to Kinesis
        self.kinesis_producer_role = iam.Role(
            self, "KinesisProducerRole",
            role_name=f"{self.config.resource_prefix}-kinesis-producer",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Least-privilege role for applications to write to Kinesis"
        )
        
        # Grant Kinesis write permissions
        self.kinesis_producer_role.add_to_policy(
            iam.PolicyStatement(
                sid="KinesisWriteAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "kinesis:PutRecord",
                    "kinesis:PutRecords"
                ],
                resources=[
                    f"arn:aws:kinesis:{Stack.of(self).region}:{Stack.of(self).account}:stream/{self.config.resource_prefix}-*"
                ]
            )
        )
        
        # Grant KMS permissions for Kinesis encryption
        if self.kinesis_kms_key:
            self.kinesis_kms_key.grant_encrypt(self.kinesis_producer_role)
        
        # Role for Kinesis Data Firehose
        self.firehose_delivery_role = iam.Role(
            self, "FirehoseDeliveryRole",
            role_name=f"{self.config.resource_prefix}-firehose-delivery",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            description="Least-privilege role for Kinesis Data Firehose to deliver data to S3"
        )
        
        # Grant Kinesis read permissions
        self.firehose_delivery_role.add_to_policy(
            iam.PolicyStatement(
                sid="KinesisReadAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "kinesis:DescribeStream",
                    "kinesis:GetShardIterator",
                    "kinesis:GetRecords",
                    "kinesis:ListShards"
                ],
                resources=[
                    f"arn:aws:kinesis:{Stack.of(self).region}:{Stack.of(self).account}:stream/{self.config.resource_prefix}-*"
                ]
            )
        )
        
        # Grant S3 write permissions
        if self.raw_data_bucket:
            self.firehose_delivery_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3WriteAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:PutObject",
                        "s3:PutObjectAcl"
                    ],
                    resources=[f"{self.raw_data_bucket.bucket_arn}/*"]
                )
            )
            
            self.firehose_delivery_role.add_to_policy(
                iam.PolicyStatement(
                    sid="S3ListAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:ListBucket",
                        "s3:GetBucketLocation"
                    ],
                    resources=[self.raw_data_bucket.bucket_arn]
                )
            )
        
        # Grant KMS permissions
        if self.kinesis_kms_key:
            self.kinesis_kms_key.grant_decrypt(self.firehose_delivery_role)
        if self.s3_kms_key:
            self.s3_kms_key.grant_encrypt(self.firehose_delivery_role)
        
        # Grant CloudWatch Logs permissions
        self.firehose_delivery_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchLogsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:PutLogEvents",
                    "logs:CreateLogStream"
                ],
                resources=[
                    f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:/aws/kinesisfirehose/*"
                ]
            )
        )
        
        # Grant Glue Data Catalog permissions for schema conversion
        self.firehose_delivery_role.add_to_policy(
            iam.PolicyStatement(
                sid="GlueDataCatalogAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "glue:GetTable",
                    "glue:GetTableVersion",
                    "glue:GetTableVersions"
                ],
                resources=[
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:catalog",
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:database/*",
                    f"arn:aws:glue:{Stack.of(self).region}:{Stack.of(self).account}:table/*/*"
                ]
            )
        )
    
    def _configure_resource_policies(self) -> None:
        """Configure resource-based policies for S3 buckets and other resources"""
        
        # S3 bucket policies to deny unencrypted uploads
        deny_unencrypted_policy = iam.PolicyStatement(
            sid="DenyUnencryptedUploads",
            effect=iam.Effect.DENY,
            principals=[iam.AnyPrincipal()],
            actions=["s3:PutObject"],
            resources=["*"],
            conditions={
                "StringNotEquals": {
                    "s3:x-amz-server-side-encryption": "aws:kms"
                }
            }
        )
        
        # S3 bucket policy to deny insecure transport
        deny_insecure_transport_policy = iam.PolicyStatement(
            sid="DenyInsecureTransport",
            effect=iam.Effect.DENY,
            principals=[iam.AnyPrincipal()],
            actions=["s3:*"],
            resources=["*"],
            conditions={
                "Bool": {
                    "aws:SecureTransport": "false"
                }
            }
        )
        
        # Apply policies to all buckets
        for bucket in [self.raw_data_bucket, self.processed_data_bucket, self.query_results_bucket]:
            if bucket:
                bucket.add_to_resource_policy(deny_unencrypted_policy)
                bucket.add_to_resource_policy(deny_insecure_transport_policy)
        
        # DynamoDB table policy (if needed for cross-account access)
        # This is typically not needed for single-account deployments
        pass
    
    def _create_vpc_endpoints(self) -> None:
        """Create VPC endpoints for private service access"""
        
        # Get VPC configuration
        vpc_id = self.config.get("vpc", "vpc_id")
        subnet_ids = self.config.get("vpc", "subnet_ids", default=[])
        
        if not vpc_id or not subnet_ids:
            return
        
        # Import existing VPC
        vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_id=vpc_id)
        
        # Create security group for VPC endpoints
        endpoint_security_group = ec2.SecurityGroup(
            self, "VpcEndpointSecurityGroup",
            vpc=vpc,
            description="Security group for VPC endpoints",
            allow_all_outbound=False
        )
        
        # Allow HTTPS inbound from VPC CIDR
        endpoint_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS from VPC"
        )
        
        # Create VPC endpoint for S3 (Gateway endpoint)
        self.s3_vpc_endpoint = ec2.GatewayVpcEndpoint(
            self, "S3VpcEndpoint",
            vpc=vpc,
            service=ec2.GatewayVpcEndpointAwsService.S3
        )
        
        # Create VPC endpoint for DynamoDB (Gateway endpoint)
        self.dynamodb_vpc_endpoint = ec2.GatewayVpcEndpoint(
            self, "DynamoDBVpcEndpoint",
            vpc=vpc,
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB
        )
        
        # Create VPC endpoint for Lambda (Interface endpoint)
        self.lambda_vpc_endpoint = ec2.InterfaceVpcEndpoint(
            self, "LambdaVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointAwsService.LAMBDA,
            security_groups=[endpoint_security_group],
            private_dns_enabled=True
        )
        
        # Create VPC endpoint for Step Functions (Interface endpoint)
        self.stepfunctions_vpc_endpoint = ec2.InterfaceVpcEndpoint(
            self, "StepFunctionsVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointAwsService.STEP_FUNCTIONS,
            security_groups=[endpoint_security_group],
            private_dns_enabled=True
        )
        
        # Create VPC endpoint for Glue (Interface endpoint)
        self.glue_vpc_endpoint = ec2.InterfaceVpcEndpoint(
            self, "GlueVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointAwsService.GLUE,
            security_groups=[endpoint_security_group],
            private_dns_enabled=True
        )
        
        # Create VPC endpoint for Kinesis Streams (Interface endpoint)
        self.kinesis_streams_vpc_endpoint = ec2.InterfaceVpcEndpoint(
            self, "KinesisStreamsVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointAwsService.KINESIS_STREAMS,
            security_groups=[endpoint_security_group],
            private_dns_enabled=True
        )
        
        # Create VPC endpoint for Kinesis Firehose (Interface endpoint)
        self.kinesis_firehose_vpc_endpoint = ec2.InterfaceVpcEndpoint(
            self, "KinesisFirehoseVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointAwsService.KINESIS_FIREHOSE,
            security_groups=[endpoint_security_group],
            private_dns_enabled=True
        )
        
        # Create VPC endpoint for CloudWatch Logs (Interface endpoint)
        self.logs_vpc_endpoint = ec2.InterfaceVpcEndpoint(
            self, "LogsVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            security_groups=[endpoint_security_group],
            private_dns_enabled=True
        )
        
        # Create VPC endpoint for Bedrock (Interface endpoint)
        # Note: Bedrock VPC endpoint service name may vary by region
        self.bedrock_vpc_endpoint = ec2.InterfaceVpcEndpoint(
            self, "BedrockVpcEndpoint",
            vpc=vpc,
            service=ec2.InterfaceVpcEndpointService(
                f"com.amazonaws.{Stack.of(self).region}.bedrock-runtime",
                443
            ),
            security_groups=[endpoint_security_group],
            private_dns_enabled=True
        )
