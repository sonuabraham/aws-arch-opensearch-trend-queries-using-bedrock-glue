"""
Storage Construct - S3 buckets and DynamoDB tables
"""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_s3_notifications as s3n,
    aws_logs as logs,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig
from typing import Optional
import os


class StorageConstruct(Construct):
    """Construct for storage components"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig,
        s3_kms_key: Optional[kms.Key] = None,
        dynamodb_kms_key: Optional[kms.Key] = None,
        logs_kms_key: Optional[kms.Key] = None,
        compression_lambda_role: Optional[iam.Role] = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.s3_kms_key = s3_kms_key
        self.dynamodb_kms_key = dynamodb_kms_key
        self.logs_kms_key = logs_kms_key
        self.compression_lambda_role = compression_lambda_role
        
        # Create S3 buckets for data lake
        self._create_s3_buckets()
        
        # Create DynamoDB table for trending queries
        self._create_trending_queries_table()
        
        # Create Lambda function for log compression
        self._create_compression_lambda()
    
    def _create_s3_buckets(self) -> None:
        """Create S3 buckets for raw logs and processed data with partitioning strategy"""
        
        # Get lifecycle configuration
        lifecycle_transition_days = self.config.get("s3", "lifecycle_transition_days")
        glacier_transition_days = self.config.get("s3", "glacier_transition_days")
        
        # Determine encryption configuration
        encryption_config = s3.BucketEncryption.KMS if self.s3_kms_key else s3.BucketEncryption.S3_MANAGED
        
        # Raw data bucket for search query logs
        self.raw_data_bucket = s3.Bucket(
            self, "RawDataBucket",
            bucket_name=f"{self.config.resource_prefix}-raw-data",
            encryption=encryption_config,
            encryption_key=self.s3_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="RawDataLifecycle",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(lifecycle_transition_days)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(glacier_transition_days)
                        )
                    ],
                    expiration=Duration.days(2555) if self.config.is_production else Duration.days(90)  # 7 years for prod, 90 days for dev
                )
            ],
            removal_policy=RemovalPolicy.DESTROY if not self.config.is_production else RemovalPolicy.RETAIN
        )
        
        # Processed data bucket for consolidated and analyzed data
        self.processed_data_bucket = s3.Bucket(
            self, "ProcessedDataBucket",
            bucket_name=f"{self.config.resource_prefix}-processed-data",
            encryption=encryption_config,
            encryption_key=self.s3_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ProcessedDataLifecycle",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(lifecycle_transition_days)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(glacier_transition_days)
                        )
                    ],
                    expiration=Duration.days(1825) if self.config.is_production else Duration.days(60)  # 5 years for prod, 60 days for dev
                )
            ],
            removal_policy=RemovalPolicy.DESTROY if not self.config.is_production else RemovalPolicy.RETAIN
        )
        
        # Query results bucket for Athena
        self.query_results_bucket = s3.Bucket(
            self, "QueryResultsBucket",
            bucket_name=f"{self.config.resource_prefix}-query-results",
            encryption=encryption_config,
            encryption_key=self.s3_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="QueryResultsLifecycle",
                    enabled=True,
                    expiration=Duration.days(7)  # Clean up query results after 7 days
                )
            ],
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Configure bucket policies for secure access
        self._configure_bucket_policies()
        
        # Set up cross-region replication if in production
        if self.config.is_production:
            self._setup_cross_region_replication()
    
    def _configure_bucket_policies(self) -> None:
        """Configure bucket policies and encryption settings"""
        
        # Policies are now configured in the SecurityConstruct
        # This method is kept for backward compatibility but can be removed
        pass
    
    def _setup_cross_region_replication(self) -> None:
        """Set up cross-region replication for production environments"""
        
        # Create replication role
        replication_role = iam.Role(
            self, "ReplicationRole",
            role_name=f"{self.config.resource_prefix}-s3-replication",
            assumed_by=iam.ServicePrincipal("s3.amazonaws.com"),
            description="Role for S3 cross-region replication"
        )
        
        # Grant replication permissions
        replication_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObjectVersionForReplication",
                    "s3:GetObjectVersionAcl",
                    "s3:GetObjectVersionTagging"
                ],
                resources=[
                    f"{self.raw_data_bucket.bucket_arn}/*",
                    f"{self.processed_data_bucket.bucket_arn}/*"
                ]
            )
        )
        
        replication_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:ReplicateObject",
                    "s3:ReplicateDelete",
                    "s3:ReplicateTags"
                ],
                resources=[
                    f"arn:aws:s3:::{self.config.resource_prefix}-raw-data-replica/*",
                    f"arn:aws:s3:::{self.config.resource_prefix}-processed-data-replica/*"
                ]
            )
        )
        
        # Grant KMS permissions for replication
        self.s3_kms_key.grant_encrypt_decrypt(replication_role)
        
        # Note: Actual replication configuration would be done via CfnBucket
        # or custom resource as CDK doesn't fully support replication configuration
        # This is a placeholder for the replication setup
    
    def _create_trending_queries_table(self) -> None:
        """Create DynamoDB table for trending queries with appropriate indexes and configuration"""
        
        # Get TTL configuration from environment config
        ttl_days = self.config.get("dynamodb", "ttl_days", default=30)
        
        # Determine encryption configuration
        if self.dynamodb_kms_key:
            encryption_config = dynamodb.TableEncryption.CUSTOMER_MANAGED
            encryption_key = self.dynamodb_kms_key
        else:
            encryption_config = dynamodb.TableEncryption.AWS_MANAGED
            encryption_key = None
        
        # Create DynamoDB table
        self.trending_queries_table = dynamodb.Table(
            self, "TrendingQueriesTable",
            table_name=f"{self.config.resource_prefix}-trending-queries",
            partition_key=dynamodb.Attribute(
                name="date",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="query_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST if not self.config.is_production 
                         else dynamodb.BillingMode.PROVISIONED,
            # Provisioned capacity for production (with auto-scaling)
            read_capacity=5 if self.config.is_production else None,
            write_capacity=5 if self.config.is_production else None,
            # Enable TTL for automatic data cleanup
            time_to_live_attribute="ttl",
            # Enable point-in-time recovery for production
            point_in_time_recovery=self.config.is_production,
            # Enable encryption at rest with customer-managed key if available
            encryption=encryption_config,
            encryption_key=encryption_key,
            # Removal policy
            removal_policy=RemovalPolicy.DESTROY if not self.config.is_production else RemovalPolicy.RETAIN,
            # Enable streams for potential future use (e.g., analytics, replication)
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES if self.config.is_production else None
        )
        
        # Add Global Secondary Index for querying by category
        self.trending_queries_table.add_global_secondary_index(
            index_name="CategoryIndex",
            partition_key=dynamodb.Attribute(
                name="category",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="rank",
                type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )
        
        # Add Global Secondary Index for querying by cluster
        self.trending_queries_table.add_global_secondary_index(
            index_name="ClusterIndex",
            partition_key=dynamodb.Attribute(
                name="cluster_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="count",
                type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )
        
        # Configure auto-scaling for production
        if self.config.is_production:
            self._configure_table_autoscaling()
        
        # Enable continuous backups for production
        if self.config.is_production:
            self._enable_table_backups()
    
    def _configure_table_autoscaling(self) -> None:
        """Configure auto-scaling for DynamoDB table capacity"""
        
        # Configure read capacity auto-scaling
        read_scaling = self.trending_queries_table.auto_scale_read_capacity(
            min_capacity=5,
            max_capacity=100
        )
        
        read_scaling.scale_on_utilization(
            target_utilization_percent=70
        )
        
        # Configure write capacity auto-scaling
        write_scaling = self.trending_queries_table.auto_scale_write_capacity(
            min_capacity=5,
            max_capacity=100
        )
        
        write_scaling.scale_on_utilization(
            target_utilization_percent=70
        )
        
        # Configure auto-scaling for GSIs
        for index_name in ["CategoryIndex", "ClusterIndex"]:
            # Read capacity auto-scaling for GSI
            gsi_read_scaling = self.trending_queries_table.auto_scale_global_secondary_index_read_capacity(
                index_name=index_name,
                min_capacity=5,
                max_capacity=50
            )
            
            gsi_read_scaling.scale_on_utilization(
                target_utilization_percent=70
            )
            
            # Write capacity auto-scaling for GSI
            gsi_write_scaling = self.trending_queries_table.auto_scale_global_secondary_index_write_capacity(
                index_name=index_name,
                min_capacity=5,
                max_capacity=50
            )
            
            gsi_write_scaling.scale_on_utilization(
                target_utilization_percent=70
            )
    
    def _enable_table_backups(self) -> None:
        """Enable continuous backups for DynamoDB table"""
        
        # Note: Point-in-time recovery is already enabled via the table configuration
        # Additional backup configuration can be done via AWS Backup service
        # This is a placeholder for any additional backup logic
        pass

    
    def _create_compression_lambda(self) -> None:
        """Create Lambda function for compressing search query logs"""
        
        # Get Lambda configuration
        timeout_seconds = self.config.get("lambda", "timeout_seconds")
        memory_mb = self.config.get("lambda", "memory_mb")
        
        # Create CloudWatch log group for Lambda with encryption
        log_group_kwargs = {
            "log_group_name": f"/aws/lambda/{self.config.resource_prefix}-log-compression",
            "retention": logs.RetentionDays.TWO_WEEKS,
            "removal_policy": RemovalPolicy.DESTROY
        }
        
        # Add KMS encryption if available
        if self.logs_kms_key:
            log_group_kwargs["encryption_key"] = self.logs_kms_key
        
        log_group = logs.LogGroup(self, "CompressionLambdaLogGroup", **log_group_kwargs)
        
        # Use provided IAM role or create a basic one
        if self.compression_lambda_role:
            lambda_role = self.compression_lambda_role
        else:
            lambda_role = iam.Role(
                self, "CompressionLambdaRole",
                role_name=f"{self.config.resource_prefix}-log-compression-lambda",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                description="Role for log compression Lambda function",
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
                ]
            )
            
            # Grant S3 permissions
            self.raw_data_bucket.grant_read_write(lambda_role)
            
            # Grant KMS permissions for encryption
            if self.s3_kms_key:
                self.s3_kms_key.grant_encrypt_decrypt(lambda_role)
            
            # Grant CloudWatch metrics permissions
            lambda_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["cloudwatch:PutMetricData"],
                    resources=["*"]
                )
            )
        
        # Create Lambda function
        self.compression_function = lambda_.Function(
            self, "CompressionFunction",
            function_name=f"{self.config.resource_prefix}-log-compression",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="log_compression.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda")
            ),
            role=lambda_role,
            timeout=Duration.seconds(timeout_seconds),
            memory_size=memory_mb,
            environment={
                "COMPRESSED_PREFIX": "compressed/",
                "COMPRESSION_LEVEL": "6",
                "DELETE_ORIGINAL": "true"
            },
            log_group=log_group,
            description="Compresses search query logs in S3 for storage optimization",
            tracing=lambda_.Tracing.ACTIVE  # Enable X-Ray tracing
        )
        
        # Configure S3 event notifications to trigger Lambda
        # Only trigger for new objects in raw-data prefix, not already compressed files
        self.raw_data_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.compression_function),
            s3.NotificationKeyFilter(
                prefix="raw-data/",
                suffix=".json"
            )
        )
        
        # Add additional notification for log files
        self.raw_data_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.compression_function),
            s3.NotificationKeyFilter(
                prefix="logs/",
                suffix=".log"
            )
        )
